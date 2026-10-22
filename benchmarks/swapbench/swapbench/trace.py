"""Convert episodes to OpenTelemetry GenAI traces (OTLP-JSON), one file per episode, plus index.jsonl.

Follows the OTel GenAI semantic conventions (github.com/open-telemetry/semantic-conventions-genai,
status Development). Spans:
  invoke_agent <agent>   root; scenario, split, trial, reward, outcome; system instructions and tool
                         definitions are stored here once
  chat <model>           one per model call (agent or simulated user); usage, cost, output messages
  execute_tool <name>    one per tool call; arguments, result, read/write kind, mock source

To keep files small, chat spans carry gen_ai.output.messages but not the full input history:
swapbench.input.message_count says how many earlier messages were in the prompt, and the history is
the concatenation of the preceding spans' outputs.

  python -m swapbench.trace <results.json> <out_dir> --split visible [--domain retail]
"""
import argparse
import hashlib
import json
import os
from datetime import datetime

from . import pricing, tau2_adapter


def _id(text, n):
    return hashlib.sha256(text.encode()).hexdigest()[:n]


def _ns(ts):
    return int(datetime.fromisoformat(ts).timestamp() * 1e9) if ts else 0


def _attr(k, v):
    if isinstance(v, bool):
        return {"key": k, "value": {"boolValue": v}}
    if isinstance(v, int):
        return {"key": k, "value": {"intValue": str(v)}}
    if isinstance(v, float):
        return {"key": k, "value": {"doubleValue": v}}
    if not isinstance(v, str):
        v = json.dumps(v, ensure_ascii=False)
    return {"key": k, "value": {"stringValue": v}}


def _span(trace_id, span_id, parent, name, start, end, attrs, kind=1):
    s = {"traceId": trace_id, "spanId": span_id, "name": name, "kind": kind,
         "startTimeUnixNano": str(start), "endTimeUnixNano": str(max(end, start)),
         "attributes": [_attr(k, v) for k, v in attrs.items() if v is not None]}
    if parent:
        s["parentSpanId"] = parent
    return s


def _provider(model):
    return "anthropic" if "claude" in model else "openai"


def episode_to_otlp(ep, split, task_name, agent_name, write_tools, tool_defs=None):
    msgs = ep["messages"]
    trace_id = _id(ep["sim_id"], 32)
    root = _id(ep["sim_id"] + "root", 16)
    spans = []
    prev_ts = msgs[0]["timestamp"] if msgs else None
    agent_model = ep["model"]
    for n, m in enumerate(msgs):
        ts = m.get("timestamp")
        if m["role"] in ("assistant", "user") and (m.get("usage") or m.get("raw_data")):
            is_agent = m["role"] == "assistant"
            model = agent_model if is_agent else pricing.canonical(ep["user_model"])
            inp, cached, out, reasoning = tau2_adapter._usage(m)
            out_msg = {"role": m["role"], "content": m.get("content"),
                       "tool_calls": [{"id": t.get("id"), "name": t["name"], "arguments": t.get("arguments")}
                                      for t in m.get("tool_calls") or []] or None}
            spans.append(_span(trace_id, _id(f"{ep['sim_id']}c{n}", 16), root, f"chat {model}", _ns(prev_ts), _ns(ts), {
                "gen_ai.operation.name": "chat",
                "gen_ai.provider.name": _provider(model),
                "gen_ai.request.model": model,
                "gen_ai.response.model": (m.get("raw_data") or {}).get("model"),
                "gen_ai.response.id": (m.get("raw_data") or {}).get("id"),
                "gen_ai.agent.name": agent_name if is_agent else "user_simulator",
                "gen_ai.usage.input_tokens": inp,
                "gen_ai.usage.cache_read.input_tokens": cached,
                "gen_ai.usage.output_tokens": out,
                "gen_ai.usage.reasoning.output_tokens": reasoning,
                "gen_ai.output.messages": [out_msg],
                "swapbench.input.message_count": n,
                "swapbench.cost_usd": pricing.cost(model, inp, cached, out) if pricing.canonical(model) in pricing.PRICES else None,
            }, kind=3))
        elif m["role"] == "tool":
            call = next((t for mm in msgs[:n] for t in (mm.get("tool_calls") or []) if t.get("id") == m.get("id")), {})
            name = call.get("name", "unknown")
            spans.append(_span(trace_id, _id(f"{ep['sim_id']}t{n}", 16), root, f"execute_tool {name}", _ns(ts), _ns(ts), {
                "gen_ai.operation.name": "execute_tool",
                "gen_ai.tool.name": name,
                "gen_ai.tool.type": "function",
                "gen_ai.tool.call.id": m.get("id"),
                "gen_ai.tool.call.arguments": call.get("arguments"),
                "gen_ai.tool.call.result": m.get("content"),
                "swapbench.tool.kind": "write" if name in write_tools else "read",
                "swapbench.tool.error": bool(m.get("error")),
                "swapbench.tool.requestor": m.get("requestor"),
                "swapbench.mock.source": "simulator",
            }))
        if ts:
            prev_ts = ts
    first = msgs[0]["timestamp"] if msgs else None
    last = msgs[-1]["timestamp"] if msgs else None
    spans.insert(0, _span(trace_id, root, None, f"invoke_agent {agent_name}", _ns(first), _ns(last), {
        "gen_ai.operation.name": "invoke_agent",
        "gen_ai.agent.name": agent_name,
        "gen_ai.conversation.id": ep["sim_id"],
        "gen_ai.request.model": agent_model,
        "gen_ai.system_instructions": ep.get("policy"),
        "gen_ai.tool.definitions": tool_defs,
        "swapbench.task": task_name,
        "swapbench.scenario_id": ep["scenario"],
        "swapbench.split": split,
        "swapbench.trial": ep["trial"],
        "swapbench.reward": ep["reward"],
        "swapbench.cost_usd": ep["cost_usd"],
        "swapbench.outcome.writes": ep["writes"],
        "swapbench.outcome.harmful_writes": ep["harmful_writes"],
        "swapbench.termination": ep["termination"],
        "swapbench.user_simulator.model": pricing.canonical(ep["user_model"]),
    }))
    return {"resourceSpans": [{
        "resource": {"attributes": [_attr("service.name", agent_name)]},
        "scopeSpans": [{"scope": {"name": "swapbench", "version": "0.1"}, "spans": spans}],
    }]}


INDEX_KEYS = ("scenario", "trial", "model", "reward", "cost_usd", "input_tokens", "cached_tokens", "output_tokens",
              "reasoning_tokens", "agent_calls", "tool_calls", "writes", "harmful_writes", "termination", "duration_s",
              "infra_error")


def convert(results, out_dir, split, task_name, agent_name, domain="retail", with_rewards=True):
    os.makedirs(out_dir, exist_ok=True)
    eps = tau2_adapter.load(results, domain)
    with open(os.path.join(out_dir, "index.jsonl"), "w") as idx:
        for ep in eps:
            if not with_rewards:  # production traces carry no grader verdict
                ep = dict(ep, reward=None)
            doc = episode_to_otlp(ep, split, task_name, agent_name, tau2_adapter.WRITE_TOOLS[domain])
            with open(os.path.join(out_dir, f"{ep['scenario']}__t{ep['trial']}.otlp.json"), "w") as f:
                json.dump(doc, f, ensure_ascii=False)
            idx.write(json.dumps({k: ep[k] for k in INDEX_KEYS}) + "\n")
    return len(eps)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("results")
    ap.add_argument("out_dir")
    ap.add_argument("--split", required=True)
    ap.add_argument("--task", default="retail-refunds")
    ap.add_argument("--agent-name", default="retail-support-agent")
    ap.add_argument("--domain", default="retail")
    ap.add_argument("--no-rewards", action="store_true")
    a = ap.parse_args()
    n = convert(a.results, a.out_dir, a.split, a.task, a.agent_name, a.domain, not a.no_rewards)
    print(f"wrote {n} traces to {a.out_dir}")
