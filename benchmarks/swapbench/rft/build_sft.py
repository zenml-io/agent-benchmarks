"""Successful candidate trajectories -> SFT examples (rejection sampling: keep reward 1, no harmful writes).

  python rft/build_sft.py <results.json> [<results.json> ...] --out sft.jsonl \
      [--exclude-data <TAU2_DATA_DIR of eval sets>]   (run with the tau2 venv)

One example per customer turn: prompt = system + history up to that customer message (earlier
reasoning dropped, as at inference); completion = the agent's tool calls, tool results and reply until
the next customer message, with the agent's reasoning kept on assistant messages.
"""
import argparse
import json
import os
import sys

from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench import tau2_adapter  # noqa: E402


def convert(m, keep_reasoning):
    if m["role"] == "user":
        return {"role": "user", "content": m.get("content") or ""}
    if m["role"] == "tool":
        return {"role": "tool", "content": m.get("content") or "", "tool_call_id": m.get("id")}
    out = {"role": "assistant", "content": m.get("content") or ""}
    if m.get("tool_calls"):
        out["tool_calls"] = [{"id": t.get("id"), "type": "function",
                              "function": {"name": t["name"], "arguments": t.get("arguments") or {}}}
                             for t in m["tool_calls"]]
    if keep_reasoning:
        rc = (((m.get("raw_data") or {}).get("choices") or [{}])[0].get("message") or {}).get("reasoning_content")
        if rc:
            out["reasoning_content"] = rc
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results", nargs="+")
    ap.add_argument("--out", required=True)
    ap.add_argument("--domain", default="retail", choices=["retail", "fintech"])
    ap.add_argument("--exclude-data", help="data dir whose retail scenarios must not appear in training")
    a = ap.parse_args()
    if a.domain == "fintech":
        from swapbench.fintech.domain import get_environment
    else:
        from tau2.domains.retail.environment import get_environment
    env = get_environment()
    tools = [t.openai_schema for t in env.get_tools()]
    system = {"role": "system", "content": SYSTEM_PROMPT.format(domain_policy=env.policy, agent_instruction=AGENT_INSTRUCTION)}
    banned = set()
    if a.exclude_data:
        path = (os.path.join(a.exclude_data, "tasks.json") if a.domain == "fintech"
                else os.path.join(a.exclude_data, "tau2", "domains", "retail", "tasks.json"))
        for t in json.load(open(path)):
            banned.add(t["user_scenario"]["instructions"]["reason_for_call"])
    kept = convs = 0
    with open(a.out, "w") as f:
        for path in a.results:
            for ep in tau2_adapter.load(path):
                convs += 1
                if ep["reward"] < 1 or ep["harmful_writes"] or ep["infra_error"]:
                    continue
                if ep["task"]["user_scenario"]["instructions"]["reason_for_call"] in banned:
                    continue
                kept += 1
                msgs = [m for m in ep["messages"] if m["role"] in ("user", "assistant", "tool")]
                user_idx = [i for i, m in enumerate(msgs) if m["role"] == "user"]
                for k, ui in enumerate(user_idx):
                    end = user_idx[k + 1] if k + 1 < len(user_idx) else len(msgs)
                    completion = [convert(m, True) for m in msgs[ui + 1:end]]
                    if not any(m["role"] == "assistant" for m in completion):
                        continue
                    prompt = [system] + [convert(m, False) for m in msgs[:ui + 1]]
                    f.write(json.dumps({"scenario": ep["scenario"], "prompt": prompt, "completion": completion,
                                        "tools": tools}) + "\n")
    print(f"kept {kept} of {convs} conversations -> {a.out}")


if __name__ == "__main__":
    main()
