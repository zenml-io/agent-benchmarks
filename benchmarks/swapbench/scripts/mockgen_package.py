"""Build the input package for a trace-inferred mock: only what an agent's traces and a data export contain.

  python scripts/mockgen_package.py --domain fintech|retail --out <dir> --n 260 [--seed 0] <results.json> ...
  (tau2 venv; fintech: SWAPBENCH_FINTECH_DIR, retail: TAU2_DATA_DIR)

Writes:
  tools.json    the tool schemas exactly as the agent was prompted with them (OpenAI function format)
  policy.md     the agent's system policy (also part of every trace)
  data.json     the data snapshot each conversation starts from (no internal state such as event logs)
  traces.jsonl  N recorded conversations (messages, tool calls with arguments, tool outputs, error flags);
                a fixed shuffle (--seed) so smaller N are prefixes of larger ones
No tool source code and no tool documentation beyond what the agent itself saw.
"""
import argparse
import json
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+")
    ap.add_argument("--domain", required=True, choices=["fintech", "retail"])
    ap.add_argument("--out", required=True)
    ap.add_argument("--n", type=int, required=True)
    ap.add_argument("--seed", type=int, default=0)
    a = ap.parse_args()
    from swapbench.genmock import snapshot
    if a.domain == "fintech":
        from swapbench.fintech.domain import get_environment
    else:
        from tau2.domains.retail.environment import get_environment
    env = get_environment()
    os.makedirs(a.out, exist_ok=True)
    json.dump([t.openai_schema for t in env.get_tools()], open(os.path.join(a.out, "tools.json"), "w"), indent=1)
    open(os.path.join(a.out, "policy.md"), "w").write(env.policy)
    json.dump(snapshot(a.domain), open(os.path.join(a.out, "data.json"), "w"))
    sims = [s for p in a.results for s in json.load(open(p))["simulations"]]
    random.Random(a.seed).shuffle(sims)
    with open(os.path.join(a.out, "traces.jsonl"), "w") as f:
        for i, s in enumerate(sims[:a.n]):
            msgs = []
            for m in s["messages"]:
                if m["role"] == "tool":
                    msgs.append({"role": "tool", "tool_call_id": m.get("id"), "content": m.get("content"),
                                 "error": bool(m.get("error"))})
                else:
                    x = {"role": m["role"], "content": m.get("content")}
                    if m.get("tool_calls"):
                        x["tool_calls"] = [{"id": t.get("id"), "name": t["name"], "arguments": t.get("arguments")}
                                           for t in m["tool_calls"]]
                    msgs.append(x)
            f.write(json.dumps({"conversation_id": f"c{i}", "messages": msgs}) + "\n")
    print(a.domain, "wrote", min(a.n, len(sims)), "of", len(sims), "conversations to", a.out)


if __name__ == "__main__":
    main()
