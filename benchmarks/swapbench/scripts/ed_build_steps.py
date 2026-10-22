"""Expert-deciders benchmark, step 1: the decision steps (handoff, refund, card action) from recorded bank runs.

  python scripts/ed_build_steps.py <raw-root> <fin-data-dir> <out.jsonl>

Agent A = Qwen3.8-27B (hosted on provider-c, self-hosted BF16 and FP8 runs); agent B = DeepSeek-V4.1-Flash (four hosted
providers). Every proposed handoff, refund or card freeze becomes one step: the conversation before it (rendered as
text), the action, the scenario, and the truth from the hidden rules (swapbench/hidden_rules.py). 30% of scenarios are
held out for testing (by a hash of the scenario id), never used for training.
"""
import glob
import hashlib
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench.hidden_rules import POINT, violations  # noqa: E402

AGENTS = {
    # Raw run directories under <raw-root>, named <provider label>_<model> (renamed from the original provider-named
    # directories; the step ids below embed these names).
    "A": ["prov_hidden/provider-c_Qwen_Qwen3.8-27B", "fvc/open/qwen27b", "fvc/comb/qwen27b-fp8", "fvc/open_r/qwen27b-fp8"],
    "B": ["prov_hidden/provider-b_DeepSeek-V4.1-Flash",
          "prov_hidden/provider-c_DeepSeek-V4.1-Flash", "prov_hidden/provider-a_DeepSeek-V4.1-Flash",
          "prov_hidden/provider-d_DeepSeek-V4.1-Flash"],
}


def render(msgs):
    lines = []
    for m in msgs:
        if m["role"] == "user":
            lines.append(f"Customer: {m.get('content')}")
        elif m["role"] == "assistant":
            if m.get("content"):
                lines.append(f"Agent: {m['content']}")
            for t in m.get("tool_calls") or []:
                lines.append(f"Agent calls {t['name']}({json.dumps(t['arguments'])})")
        elif m["role"] == "tool":
            lines.append(f"Tool result: {str(m.get('content'))[:1500]}")
    return "\n".join(lines)


def heldout(scenario):
    return int(hashlib.sha256(scenario.encode()).hexdigest(), 16) % 10 < 3


def main(root, data, out):
    db = json.load(open(os.path.join(data, "db.json")))
    n = 0
    with open(out, "w") as f:
        for agent, runs in AGENTS.items():
            for run in runs:
                for split in ("test", "pool", "train"):
                    p = os.path.join(root, run, split, "results.json")
                    if not os.path.exists(p):
                        continue
                    for s in json.load(open(p))["simulations"]:
                        msgs = s["messages"]
                        for i, m in enumerate(msgs):
                            if m["role"] != "assistant":
                                continue
                            for t in m.get("tool_calls") or []:
                                if t["name"] not in POINT:
                                    continue
                                v = violations(msgs[:i], t["name"], t["arguments"], db)
                                f.write(json.dumps(dict(
                                    id=f"{agent}:{run}:{split}:{s['task_id']}:{s['trial']}:{i}", agent=agent, run=run,
                                    split=split, scenario=s["task_id"], point=POINT[t["name"]], tool=t["name"],
                                    arguments=t["arguments"], state=render(msgs[:i])[-12000:], violations=v,
                                    bad=bool(v), heldout=heldout(s["task_id"]))) + "\n")
                                n += 1
    print("steps:", n)


if __name__ == "__main__":
    main(*sys.argv[1:4])
