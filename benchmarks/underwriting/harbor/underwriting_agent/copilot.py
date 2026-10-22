"""The benchmark's own agent loop (harness/run.py run_task), run inside the task's main container.

  python copilot.py --model <key> --url <mcp url> --request-file F [--prompt-file F] [--effort E] --out F

Same model client, tools, system prompt, limits and episode rules as the original. The only change is where tools
and the underwriter live: tool calls go to the task's MCP server, a plain copilot message goes to `ask_underwriter`,
and a message with "FINAL ANSWER:" is sent to `submit_final_answer`. Copilot text that comes with tool calls is
held and sent with the next message to the underwriter (the original added it to the underwriter's view at once;
the underwriter only reads it at its next reply either way).
"""
import argparse
import json
import os
import re
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "harness"))
sys.path.insert(0, HERE)
import run as uw  # noqa: E402
from llm import M, call_model  # noqa: E402
from mcp_client import MCPClient  # noqa: E402


def run_episode(key, system, request, client, call=call_model):
    msgs = [{"role": "system", "content": system}, {"role": "user", "content": request}]
    calls, failures, tool_calls = [], [], 0
    final, status = None, "unfinished"
    turns = nudges = 0
    held = []
    t0 = time.time()
    for _ in range(uw.MAX_CALLS):
        try:
            msg, usage, lat, retries = call(key, msgs, uw.TOOLS)
        except RuntimeError as e:
            failures.append(str(e).split()[0])
            calls.append(dict(error=str(e)[:300]))
            status = failures[-1]
            break
        calls.append(dict(**usage, latency=round(lat, 3), retries=retries))
        tcs = msg.get("tool_calls") or []
        text = msg.get("content") or ""
        if not tcs and not text.strip():
            nudges += 1
            if nudges <= 2:
                msgs.append({"role": "user", "content": "Please continue."})
                continue
            failures.append("empty_reply")
            status = "empty_reply"
            break
        keep_rz = "gpt-oss" in key and msg.get("reasoning_content")
        msgs.append({"role": "assistant", "content": text or None, **({"tool_calls": tcs} if tcs else {}),
                     **({"reasoning_content": msg["reasoning_content"]} if keep_rz else {}),
                     **({"_items": msg["_items"]} if msg.get("_items") else {})})
        if m := re.search(r"FINAL ANSWER\s*:", text):
            final, status = text[m.start():], "finished"
            client.call("submit_final_answer", {"answer": final})
            break
        if tcs:
            if text.strip():
                held.append(text.strip())
            for tc in tcs:
                tool_calls += 1
                try:
                    args = json.loads(tc["function"].get("arguments") or "{}")
                    out = client.call(tc["function"]["name"], args if isinstance(args, dict) else {})
                except json.JSONDecodeError:
                    failures.append("tool_parse_error")
                    out = "Error: arguments were not valid JSON."
                msgs.append({"role": "tool", "tool_call_id": tc["id"], "content": out[:20000]})
            continue
        turns += 1
        if turns > uw.MAX_TURNS:
            failures.append("turn_limit")
            status = "turn_limit"
            break
        reply = client.call("ask_underwriter", {"message": "\n\n".join([*held, text.strip()])})
        held = []
        msgs.append({"role": "user", "content": reply})
    else:
        failures.append("step_limit")
        status = "step_limit"
    inp = sum(c.get("input", 0) for c in calls)
    cached = sum(c.get("cached", 0) for c in calls)
    out = sum(c.get("output", 0) for c in calls)
    return dict(model=key, status=status, failures=failures, calls=len(calls), tool_calls=tool_calls,
                underwriter_turns=turns, input=inp, cached=cached, output=out,
                reasoning=sum(c.get("reasoning", 0) for c in calls), cost=M.cost(key, inp, cached, out),
                latency=round(time.time() - t0, 2), call_latencies=[c.get("latency") for c in calls],
                errors=[c["error"] for c in calls if "error" in c], final_answer=final,
                messages=[{k: v for k, v in m.items() if not k.startswith("_")} for m in msgs])


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--model", required=True)
    ap.add_argument("--url", required=True)
    ap.add_argument("--request-file", required=True)
    ap.add_argument("--prompt-file", default=None)
    ap.add_argument("--effort", default=None)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()
    client = MCPClient(a.url)
    client.initialize()
    names = {t["name"] for t in client.list_tools()}
    missing = ({t["function"]["name"] for t in uw.TOOLS} | {"ask_underwriter", "submit_final_answer"}) - names
    if missing:
        raise SystemExit(f"the MCP server lacks {sorted(missing)}")
    print(f"connected to {a.url}: {len(names)} tools", flush=True)
    if a.model not in M.MODELS:
        raise SystemExit(f"unknown model key {a.model!r}; use one of {sorted(M.MODELS)}")
    system = open(a.prompt_file).read().strip() if a.prompt_file else uw.SYSTEM
    if a.effort:
        from models_client import client as shared
        shared.EXTRA.update(anthropic={"output_config": {"effort": a.effort}},
                            responses={"reasoning": {"effort": a.effort}},
                            chat={"reasoning_effort": a.effort})
    try:
        row = run_episode(a.model, system, open(a.request_file).read().strip(), client)
    except Exception as e:  # noqa: BLE001 - recorded as a harness error, as in the original
        row = dict(model=a.model, status="harness_error", failures=["harness_error"], errors=[repr(e)[:300]],
                   cost=0.0)
    json.dump(row, open(a.out, "w"), indent=1)
    print(json.dumps({k: row.get(k) for k in ("status", "calls", "tool_calls", "underwriter_turns", "cost")}))


if __name__ == "__main__":
    main()
