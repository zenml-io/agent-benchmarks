"""Turn the raw live runs of the expert-deciders benchmark into the public per-conversation rows (no text).

  cd ../swapbench && SWAPBENCH_PROVIDER_PRICES=<prices.json> .venv/bin/python ../expert-deciders/scripts/extract_rows.py \
      <edon-dir> <fin-hidden-dir> ../expert-deciders/results/runs

Needs the raw tau2 results, decision logs (<run>.log) and call logs (<run>.calls) of the live runs, and the bank hidden
set with hidden-rule gold (<fin-hidden-dir>: tasks.json, db.json). Both are in the private archive. Writes:
  live_conversations.jsonl  one row per conversation: run, scenario, trial, reward, empty, rule violations, handoffs,
                            unneeded handoffs, agent tokens and calls (from the trajectory)
  live_decisions.jsonl      one row per checked action: run, tool, p, blocked, hidden rules broken (ids only)
  live_runs.json            per run: agent and user model, excluded conversations, agent cost (call log or trajectory),
                            estimated check cost
Same logic as scripts/ed_online_eval.py (violations, handoffs) and the original export's ed_compute.py (costs, tokens).
"""
import ast
import glob
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SB = os.path.join(os.path.dirname(os.path.dirname(HERE)), "swapbench")
sys.path.insert(0, SB)
from swapbench import pricing  # noqa: E402
from swapbench.hidden_rules import POINT, violations  # noqa: E402

EMPTY = "must have either content or tool_calls"
JEV_PRICE = 0.042 / 1e6
JEV_TOK = {"C": 3344, "G": 2231, "H": 3344}
# Agent model strings are recorded without the provider in the public rows.
LABEL = {"A": "Qwen/Qwen3.8-27B", "B": "deepseek-ai/DeepSeek-V4.1-Flash", "R": "gpt-5-2025-08-07"}


def usage(m):
    raw = (m.get("raw_data") or {}).get("usage") or {}
    u = m.get("usage") or {}
    i = raw.get("prompt_tokens", u.get("prompt_tokens", 0)) or 0
    o = raw.get("completion_tokens", u.get("completion_tokens", 0)) or 0
    c = ((raw.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    return i, o, c


def main(edon, data, out):
    os.makedirs(out, exist_ok=True)
    db = json.load(open(os.path.join(data, "db.json")))
    tasks = {t["id"]: t for t in json.load(open(os.path.join(data, "tasks.json")))}
    runs = sorted(os.path.basename(d) for d in glob.glob(os.path.join(edon, "[ABR]_*")) if os.path.isdir(d))
    meta = {}
    with open(os.path.join(out, "live_conversations.jsonl"), "w") as fc, open(os.path.join(out, "live_decisions.jsonl"), "w") as fd:
        for r in runs:
            p = glob.glob(os.path.join(edon, r, "*", "test", "results.json"))
            if not p:
                continue
            R = json.load(open(p[0]))
            info = R["info"]
            agent_llm = (ast.literal_eval(info["agent_info"]) if isinstance(info["agent_info"], str) else info["agent_info"])["llm"]
            user_llm = (ast.literal_eval(info["user_info"]) if isinstance(info["user_info"], str) else info["user_info"])["llm"]
            excluded, reasons, traj_cost = 0, {}, 0.0
            for s in R["simulations"]:
                ri = s.get("reward_info")
                empty = False
                if not ri:
                    err = str((s.get("info") or {}).get("error"))
                    if EMPTY not in err:
                        excluded += 1
                        reasons[err[:60]] = reasons.get(err[:60], 0) + 1
                        continue
                    ri, empty = {"reward": 0.0}, True
                msgs = s["messages"]
                gold = {a["name"] for a in (tasks[s["task_id"]].get("evaluation_criteria") or {}).get("actions") or []}
                viol = esc = esc_bad = tin = tout = calls = 0
                for i, m in enumerate(msgs):
                    if m["role"] != "assistant":
                        continue
                    a, b, c = usage(m)
                    if a or b:
                        tin, tout, calls = tin + a, tout + b, calls + 1
                        traj_cost += pricing.cost(agent_llm, a, c, b)
                    for t in m.get("tool_calls") or []:
                        if t["name"] in POINT:
                            viol += bool(violations(msgs[:i], t["name"], t["arguments"], db))
                        if t["name"] == "escalate_to_human":
                            esc += 1
                            esc_bad += "escalate_to_human" not in gold
                fc.write(json.dumps(dict(run=r, scenario=s["task_id"], trial=s["trial"], reward=float(ri.get("reward") or 0),
                                         empty=int(empty), violations=viol, handoffs=esc, unneeded_handoffs=esc_bad,
                                         input_tokens=tin, output_tokens=tout, agent_calls=calls)) + "\n")
            calls_p = os.path.join(edon, r + ".calls")
            if os.path.exists(calls_p):
                agent_cost, n_log = 0.0, 0
                for line in open(calls_p):
                    x = json.loads(line)
                    u = x.get("usage") or {}
                    if isinstance(u, str):
                        u = ast.literal_eval(u)
                    agent_cost += pricing.cost(x["model"], u.get("prompt_tokens", 0), 0, u.get("completion_tokens", 0))
                    n_log += 1
                src = "call log"
            else:
                agent_cost, n_log, src = traj_cost, 0, "trajectory usage"
            arm = r.split("_", 1)[1]
            logp = os.path.join(edon, r + ".log")
            L = [json.loads(line) for line in open(logp)] if os.path.exists(logp) else []
            for x in L:
                fd.write(json.dumps(dict(run=r, tool=x["tool"], p=x["p"], blocked=x["blocked"], truth=x["truth"])) + "\n")
            check = 0.0
            if arm == "D":
                check = len(L) * pricing.cost("gpt-6.1-sol", 10153, 0, 200)
            elif arm in JEV_TOK:
                check = sum(1 for x in L if not (arm == "H" and x["tool"] == "escalate_to_human")) * JEV_TOK[arm] * JEV_PRICE
            meta[r] = dict(agent_model=LABEL[r[0]], user_model=user_llm, excluded=excluded, excluded_reasons=reasons,
                           agent_cost_usd=agent_cost, agent_cost_source=src, call_log_calls=n_log, check_cost_usd=check)
    json.dump(meta, open(os.path.join(out, "live_runs.json"), "w"), indent=1)
    print("runs:", list(meta))


if __name__ == "__main__":
    main(*sys.argv[1:4])
