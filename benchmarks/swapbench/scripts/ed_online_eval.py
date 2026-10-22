"""Expert-deciders benchmark, step 5: the live test.

  python scripts/ed_online_eval.py <edon-dir> <fin-hidden-dir> > experiments/expert_deciders_online.md   (tau2 venv)

Runs (each the bank hidden set x2, graded against the hidden-rule gold): A_<arm> = Qwen3.8-27B with that arm's
check (none, C, D, G, H), B_<arm> = DeepSeek-V4.1-Flash (swap test), R_gpt5 = GPT-5 with no check (reference).
Per run: resolved (tau2 reward under hidden-rule gold), hidden-rule violations per conversation among executed actions,
handoffs not in the gold, handoffs per conversation, checks and blocks, and cost per conversation (agent + checks;
the judge's tokens at GPT-6.1 Sol prices; Jev at $0.042 per 1M input tokens). Judge and Jev tokens are not in the live
decision log, so they are estimated per decision from the offline run's mean input (judge D 10,153 in / ~200 out;
Jev C 3,344, Jev G 2,231; arm H asks Jev only for refunds and card actions). Paired 95% CIs vs the same agent with
no check and vs GPT-5. Conversations where the model returned an empty message
count as unresolved (column "empty").
"""
import ast
import glob
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench import pricing, stats, tau2_adapter  # noqa: E402
from swapbench.hidden_rules import POINT, violations  # noqa: E402


EMPTY = "must have either content or tool_calls"
JEV_PRICE = 0.042 / 1e6
JEV_TOK = {"C": 3344, "G": 2231, "H": 3344}


def load(d):
    p = glob.glob(os.path.join(d, "*", "test", "results.json"))
    return json.load(open(p[0]))["simulations"] if p else []


def episodes(sims, db, tasks):
    out = []
    for s in sims:
        ri = s.get("reward_info")
        if not ri:
            # the model returned an empty message: tau2 calls it an infrastructure error, but it is the agent's
            # failure, so it counts as unresolved (provider outages and rate limits stay excluded)
            if EMPTY not in str((s.get("info") or {}).get("error")):
                continue
            ri = {"reward": 0.0, "empty": True}
        msgs, viol, esc, esc_bad = s["messages"], 0, 0, 0
        gold = {a["name"] for a in tasks[s["task_id"]]["evaluation_criteria"].get("actions") or []}
        for i, m in enumerate(msgs):
            for t in (m.get("tool_calls") or []) if m["role"] == "assistant" else []:
                if t["name"] in POINT:
                    viol += bool(violations(msgs[:i], t["name"], t["arguments"], db))
                if t["name"] == "escalate_to_human":
                    esc += 1
                    esc_bad += "escalate_to_human" not in gold
        out.append(dict(scenario=s["task_id"], trial=s["trial"], reward=float(ri.get("reward") or 0),
                        violations=viol, viol_any=float(viol > 0), handoffs=esc, bad_handoffs=esc_bad,
                        empty=float(bool(ri.get("empty")))))
    return out


def cost(d, eps, sims):
    tot = 0.0
    calls = d + ".calls"
    if os.path.exists(calls):
        for l in open(calls):
            r = json.loads(l)
            u = r.get("usage") or {}
            if isinstance(u, str):
                u = ast.literal_eval(u)
            tot += pricing.cost(r["model"], u.get("prompt_tokens", 0), 0, u.get("completion_tokens", 0))
    else:
        tot = sum(e["cost_usd"] for e in tau2_adapter.load(glob.glob(os.path.join(d, "*", "test", "results.json"))[0],
                                                           domain="fintech"))
    log, arm = d + ".log", os.path.basename(d).split("_", 1)[1]
    check = 0.0
    if os.path.exists(log):
        L = [json.loads(l) for l in open(log)]
        if arm == "D":
            check = len(L) * pricing.cost("gpt-6.1-sol", 10153, 0, 200)
        elif arm in JEV_TOK:
            n = sum(1 for x in L if not (arm == "H" and x["tool"] == "escalate_to_human"))
            check = n * JEV_TOK[arm] * JEV_PRICE
    return (tot + check) / max(len(eps), 1), check / max(len(eps), 1)


def main(root, data):
    db = json.load(open(os.path.join(data, "db.json")))
    tasks = {t["id"]: t for t in json.load(open(os.path.join(data, "tasks.json")))}
    runs = sorted(os.path.basename(d) for d in glob.glob(os.path.join(root, "[ABR]_*")) if os.path.isdir(d))
    E = {r: episodes(load(os.path.join(root, r)), db, tasks) for r in runs}
    ref = E.get("R_gpt5", [])
    print("# Expert-deciders benchmark: live test (bank hidden set x2, hidden-rule grading)\n")
    print("| run | conversations (empty) | resolved | vs same agent, no check [95% CI] | vs GPT-5 [95% CI] | rule violations / conv. | "
          "conv. with a violation | handoffs / conv. | unneeded handoffs / conv. | checks (blocked) | cost / conv. (check) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|")
    for r in runs:
        e = E[r]
        if not e:
            continue
        base = E.get(r.split("_")[0] + "_none", [])
        fmt = lambda d: f"{d['delta'] * 100:+.1f} [{d['lo'] * 100:+.1f}, {d['hi'] * 100:+.1f}]"  # noqa: E731
        vs_base = fmt(stats.paired_delta(e, base)) if base and r != r.split("_")[0] + "_none" else "—"
        vs_ref = fmt(stats.paired_delta(e, ref)) if ref and r != "R_gpt5" else "—"
        logp = os.path.join(root, r + ".log")
        checks = [json.loads(l) for l in open(logp)] if os.path.exists(logp) else []
        c, cj = cost(os.path.join(root, r), e, None)
        n = len(e)
        print(f"| {r} | {n} ({int(sum(x['empty'] for x in e))}) | {sum(x['reward'] for x in e) / n * 100:.1f}% | {vs_base} | {vs_ref} | "
              f"{sum(x['violations'] for x in e) / n:.3f} | {sum(x['viol_any'] for x in e) / n * 100:.1f}% | "
              f"{sum(x['handoffs'] for x in e) / n:.3f} | {sum(x['bad_handoffs'] for x in e) / n:.3f} | {len(checks)} ({sum(c_['blocked'] for c_ in checks)}) | "
              f"{c * 100:.3f}¢{f' ({cj * 100:.4f}¢)' if cj else ''} |")
    print("\nPaired difference in rule violations per conversation vs the same agent with no check:\n")
    for r in runs:
        base = E.get(r.split("_")[0] + "_none", [])
        if base and not r.endswith("_none") and E[r]:
            d = stats.paired_delta(E[r], base, "violations")
            print(f"- {r}: {d['delta']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]")
    for col, name in (("bad_handoffs", "unneeded handoffs"), ("handoffs", "handoffs")):
        print(f"\nPaired difference in {name} per conversation vs the same agent with no check:\n")
        for r in runs:
            base = E.get(r.split("_")[0] + "_none", [])
            if base and not r.endswith("_none") and E[r]:
                d = stats.paired_delta(E[r], base, col)
                print(f"- {r}: {d['delta']:+.3f} [{d['lo']:+.3f}, {d['hi']:+.3f}]")
    print("\nBlocked decisions by hidden-rule truth (precision of the live check):\n")
    for r in runs:
        logp = os.path.join(root, r + ".log")
        if os.path.exists(logp):
            L = [json.loads(l) for l in open(logp)]
            b = [x for x in L if x["blocked"]]
            allowed_bad = sum(1 for x in L if not x["blocked"] and x["truth"])
            print(f"- {r}: blocked {len(b)}, of which breaking a hidden rule {sum(bool(x['truth']) for x in b)}; "
                  f"allowed but breaking a rule {allowed_bad}; by action {dict(Counter(x['tool'] for x in b))}")


if __name__ == "__main__":
    main(*sys.argv[1:3])
