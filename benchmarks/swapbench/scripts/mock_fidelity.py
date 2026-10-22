"""Score a generated tool mock against the hand-written tools, offline, on recorded conversations.

  python scripts/mock_fidelity.py --domain fintech|retail --mock <mock.py> NAME=<results.json> ... \
      [--incumbent NAME] [--margin 5] [--out rows.jsonl] [--cache <dir>] [--procs 4]          (tau2 venv)
  (fintech: SWAPBENCH_FINTECH_DIR, retail: TAU2_DATA_DIR point at the scenario world)

A generated mock is a file defining `class Mock(data: dict)` with one method per tool (keyword arguments,
JSON-serializable return, raise on error) and `state() -> dict`; it may keep a `flags` list of the guessed
behaviors it used. For every recorded episode we replay its tool calls, in order, on a fresh hand-written
toolkit and a fresh generated mock and compare each call's outcome (both error, or the same normalized
output). Then we grade the episode the way tau2 does: on a fresh instance of each backend, replay only the
calls tau2 re-executes during evaluation (tools marked mutates_state in the hand-written toolkit; e.g. tau2
skips `transfer_to_human_agents`), and pass if that final state equals the state after the scenario's gold
actions, replayed the same way. Hand-written results are
cached per run (--cache), so scoring further mocks only replays the generated one.

Report per run: call agreement; episodes whose every call agrees (where the offline replay is exact, since
the conversation would have unfolded identically); final-grade agreement with the hand-written tools;
calls that hit a guessed path; and the truth verdict per candidate under each backend.
"""
import argparse
import hashlib
import importlib.util
import json
import os
import pickle
import sys
from multiprocessing import Pool

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench import stats, tau2_adapter  # noqa: E402

G = {}


def norm(x):
    if isinstance(x, str):
        try:
            x = json.loads(x)
        except ValueError:
            return x.strip()
    if hasattr(x, "model_dump"):
        x = x.model_dump()
    x = json.loads(json.dumps(x, default=str))

    def fix(v):  # bools vs "True"/"true", ints vs floats
        if isinstance(v, dict):
            return {k: fix(w) for k, w in v.items()}
        if isinstance(v, list):
            return [fix(w) for w in v]
        if isinstance(v, bool):
            return str(v).lower()
        if isinstance(v, (int, float)):
            return round(float(v), 2)
        if isinstance(v, str) and v.lower() in ("true", "false"):
            return v.lower()
        return v
    return fix(x)


def h(x):
    return hashlib.sha1(json.dumps(x, sort_keys=True).encode()).hexdigest()


def init(domain, mock_path):
    G["domain"] = domain
    if domain == "fintech":
        from swapbench.fintech import domain as d
        G["Real"], db = d.FintechTools, d.FintechDB.load(os.path.join(d.data_dir(), "db.json"))
    else:
        from tau2.domains.retail.data_model import RetailDB
        from tau2.domains.retail.tools import RetailTools
        from tau2.domains.retail.utils import RETAIL_DB_PATH
        G["Real"], db = RetailTools, RetailDB.load(RETAIL_DB_PATH)
    G["real_db"] = pickle.dumps(db)
    from tau2.environment.toolkit import MUTATES_STATE_ATTR
    G["mutating"] = {n for n, f in G["Real"].__dict__.items() if getattr(f, MUTATES_STATE_ATTR, False)}
    if mock_path:
        from swapbench.genmock import load_mock_class, snapshot
        G["Mock"], G["data"] = load_mock_class(mock_path), pickle.dumps(snapshot(domain))


def real():
    t = G["Real"](pickle.loads(G["real_db"]))
    t.state = lambda: t.db.model_dump()
    return t


def gen():
    return G["Mock"](pickle.loads(G["data"]))


def call(obj, name, args):
    try:
        return True, norm(getattr(obj, name)(**(args or {})))
    except Exception as e:  # noqa: BLE001
        return False, type(e).__name__


def state_hash(obj):
    try:
        return h(norm(obj.state()))
    except Exception as e:  # noqa: BLE001
        return f"state() raised {type(e).__name__}"


def replay(make, calls, gold):
    """Per-call outputs from one pass over every call; the grade from tau2-style replays of mutating calls only."""
    obj = make()
    outs = [call(obj, n, a) for n, a in calls]
    flags = len(getattr(obj, "flags", []) or [])
    pred, ref = make(), make()
    for n, a in calls:
        if n in G["mutating"]:
            call(pred, n, a)
    for n, a in gold:
        if n in G["mutating"]:
            call(ref, n, a)
    return outs, float(state_hash(pred) == state_hash(ref)), flags


def real_job(job):
    calls, gold = job
    outs, reward, _ = replay(real, calls, gold)
    return {"outs": [[ok, h(v)] for ok, v in outs], "reward": reward}


def gen_job(job):
    (calls, gold), ref = job
    outs, reward, flags = replay(gen, calls, gold)
    agree = [ok == r_ok and (not ok or h(v) == r_v) for (ok, v), (r_ok, r_v) in zip(outs, ref["outs"])]
    return {"calls": len(calls), "agree": sum(agree), "all_agree": all(agree), "flags": flags,
            "real_reward": ref["reward"], "gen_reward": reward}


def episodes(domain, path):
    eps = tau2_adapter.load(path, domain=domain)
    jobs = []
    for e in eps:
        calls = [(t["name"], t.get("arguments")) for m in e["messages"] if m["role"] == "assistant"
                 for t in (m.get("tool_calls") or [])]
        gold = [(x["name"], x.get("arguments")) for x in (e["task"].get("evaluation_criteria") or {}).get("actions") or []]
        jobs.append((calls, gold))
    return eps, jobs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("runs", nargs="+")
    ap.add_argument("--domain", required=True, choices=["fintech", "retail"])
    ap.add_argument("--mock", required=True)
    ap.add_argument("--incumbent")
    ap.add_argument("--margin", type=float, default=5.0)
    ap.add_argument("--procs", type=int, default=4)
    ap.add_argument("--cache", default=os.path.expanduser("~/.cache/swapbench_fidelity"))
    ap.add_argument("--out")
    a = ap.parse_args()
    os.makedirs(a.cache, exist_ok=True)
    eps_by, jobs_by, ref_by = {}, {}, {}
    for spec in a.runs:
        name, path = spec.split("=", 1)
        eps_by[name], jobs_by[name] = episodes(a.domain, path)
        cache = os.path.join(a.cache, h([a.domain, os.path.abspath(path), os.path.getmtime(path)]) + ".json")
        if os.path.exists(cache):
            ref_by[name] = json.load(open(cache))
        else:
            with Pool(a.procs, initializer=init, initargs=(a.domain, None)) as pool:
                ref_by[name] = pool.map(real_job, jobs_by[name], chunksize=8)
            json.dump(ref_by[name], open(cache, "w"))
    rows = []
    with Pool(a.procs, initializer=init, initargs=(a.domain, a.mock)) as pool:
        for name in eps_by:
            res = pool.map(gen_job, list(zip(jobs_by[name], ref_by[name])), chunksize=8)
            for e, r in zip(eps_by[name], res):
                r.update(run=name, scenario=e["scenario"], trial=e["trial"], recorded=e["reward"],
                         harmful_writes=e["harmful_writes"])
                rows.append(r)
    print("| run | episodes | tool calls agreeing | episodes with every call agreeing | hand-written grade = recorded | "
          "generated grade = hand-written | calls on guessed paths | success hand-written → generated |")
    print("|---|---|---|---|---|---|---|---|")
    for name in eps_by:
        rs = [r for r in rows if r["run"] == name]
        calls = sum(r["calls"] for r in rs) or 1
        print(f"| {name} | {len(rs)} | {sum(r['agree'] for r in rs) / calls:.1%} | {sum(r['all_agree'] for r in rs) / len(rs):.1%} | "
              f"{sum(r['real_reward'] == r['recorded'] for r in rs) / len(rs):.1%} | "
              f"{sum(r['gen_reward'] == r['real_reward'] for r in rs) / len(rs):.1%} | {sum(r['flags'] for r in rs) / calls:.1%} | "
              f"{sum(r['real_reward'] for r in rs) / len(rs):.1%} → {sum(r['gen_reward'] for r in rs) / len(rs):.1%} |")
    if a.out:
        with open(a.out, "w") as f:
            for r in rows:
                f.write(json.dumps(r) + "\n")
    if a.incumbent:
        m = a.margin / 100
        print("\n| candidate | Δ vs incumbent, hand-written | truth | Δ vs incumbent, generated | truth | same? |")
        print("|---|---|---|---|---|---|")
        for name in eps_by:
            if name == a.incumbent:
                continue
            res = []
            for key in ("real_reward", "gen_reward"):
                ep = lambda run: [{"scenario": r["scenario"], "reward": r[key]} for r in rows if r["run"] == run]  # noqa: E731
                harm = lambda run: [{"scenario": r["scenario"], "reward": r["harmful_writes"]} for r in rows if r["run"] == run]  # noqa: E731
                q, hd = stats.paired_delta(ep(name), ep(a.incumbent)), stats.paired_delta(harm(name), harm(a.incumbent))
                res.append((q, stats.truth_label(q, hd, m)))
            (qr, lr), (qg, lg) = res
            print(f"| {name} | {qr['delta']*100:+.1f} [{qr['lo']*100:+.1f}, {qr['hi']*100:+.1f}] | {lr} | "
                  f"{qg['delta']*100:+.1f} [{qg['lo']*100:+.1f}, {qg['hi']*100:+.1f}] | {lg} | {'yes' if lr == lg else 'NO'} |")


if __name__ == "__main__":
    main()
