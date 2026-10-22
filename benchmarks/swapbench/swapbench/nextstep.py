"""Next-step replay verifier (the smithtune-style check): no tools executed, no simulated user.

For every recorded incumbent conversation, at every agent step, the candidate gets the exact recorded
prefix (system prompt, tools, history including tool results) and produces its next message. We
compare it with what the incumbent actually did:
  tool step  -> exact match of tool name + canonical arguments (and name-only match)
  text step  -> the candidate also answered in text (no tool call)
The verdict compares the candidate's agreement with the incumbent's own agreement when re-run on the
same prefixes (its noise floor): SAFE if candidate agreement >= self-agreement - margin.

Runs with tau2's own prompt and tool schemas (needs the tau2 venv):
  python -m swapbench.nextstep <incumbent results.json> --model M [--llm-args JSON] --out out.json [--threads 16]
"""
import argparse
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

from tau2.agent.llm_agent import AGENT_INSTRUCTION, SYSTEM_PROMPT
from tau2.data_model.message import AssistantMessage, SystemMessage
from tau2.data_model.simulation import Results
from tau2.utils.llm_utils import generate

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from swapbench.tau2_adapter import WRITE_TOOLS, _canon_write  # noqa: E402

DOMAIN = "retail"


def steps(results):
    """(scenario, history, recorded assistant message) for every agent step after the scripted greeting."""
    for sim in results.simulations:
        msgs = sim.messages
        for t, m in enumerate(msgs):
            if isinstance(m, AssistantMessage) and t > 0:
                yield sim.task_id, msgs[:t], m


def kind(m):
    return "tool" if m.tool_calls else "text"


def compare(rec, cand):
    out = {"kind": kind(rec), "cand_kind": kind(cand)}
    if rec.tool_calls:
        r = rec.tool_calls[0]
        c = cand.tool_calls[0] if cand.tool_calls else None
        out.update(tool=r.name, write=r.name in WRITE_TOOLS[DOMAIN],
                   name_match=bool(c and c.name == r.name),
                   # same key arguments as the grader uses (free-text fields like summaries are ignored)
                   exact=bool(c and _canon_write(c.name, c.arguments) == _canon_write(r.name, r.arguments)),
                   rec_args=r.arguments, cand_tool=c.name if c else None, cand_args=c.arguments if c else None)
    else:
        out.update(exact=not cand.tool_calls, name_match=not cand.tool_calls, write=False)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("--model", required=True)
    ap.add_argument("--llm-args", default="{}")
    ap.add_argument("--out", required=True)
    ap.add_argument("--domain", default="retail", choices=["retail", "fintech"])
    ap.add_argument("--threads", type=int, default=16)
    a = ap.parse_args()
    res = Results.load(a.results)
    global DOMAIN
    DOMAIN = a.domain
    if a.domain == "fintech":
        from swapbench.fintech.domain import get_environment
    else:
        from tau2.domains.retail.environment import get_environment
    env = get_environment()
    tools = env.get_tools()
    system = SystemMessage(role="system", content=SYSTEM_PROMPT.format(domain_policy=env.policy,
                                                                        agent_instruction=AGENT_INSTRUCTION))
    args = json.loads(a.llm_args)
    todo = list(steps(res))

    def one(item):
        scen, hist, rec = item
        try:
            cand = generate(model=a.model, tools=tools, messages=[system] + list(hist), call_name="nextstep", **args)
            return {"scenario": scen, "step": len(hist), **compare(rec, cand)}
        except Exception as e:  # an endpoint that errors fails the step
            return {"scenario": scen, "step": len(hist), "kind": kind(rec), "error": str(e)[:200], "exact": False,
                    "name_match": False, "write": bool(rec.tool_calls) and rec.tool_calls[0].name in WRITE_TOOLS[DOMAIN]}

    with ThreadPoolExecutor(a.threads) as ex:
        rows = list(ex.map(one, todo))
    tool = [r for r in rows if r["kind"] == "tool"]
    summary = {
        "model": a.model, "steps": len(rows), "errors": sum("error" in r for r in rows),
        "exact_all": sum(r["exact"] for r in rows) / len(rows),
        "tool_exact": sum(r["exact"] for r in tool) / max(len(tool), 1),
        "tool_name": sum(r["name_match"] for r in tool) / max(len(tool), 1),
        "write_exact": sum(r["exact"] for r in tool if r["write"]) / max(sum(r["write"] for r in tool), 1),
    }
    json.dump({"summary": summary, "rows": rows}, open(a.out, "w"))
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
