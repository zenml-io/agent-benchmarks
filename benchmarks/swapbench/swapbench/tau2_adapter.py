"""Read tau2-bench results.json files into SwapBench episode records.

An episode record is a plain dict:
  scenario, trial, model, reward, cost_usd, input_tokens, cached_tokens, output_tokens,
  reasoning_tokens, agent_calls, tool_calls, writes, harmful_writes, termination, duration_s
plus 'messages' (tau2's native messages) and 'task' (the scenario definition), used by trace.py.

A *harmful write* is a successful write-tool call whose (name, arguments) matches no write action
in the scenario's gold action list: e.g. refunding to the wrong payment method or cancelling the
wrong order. It is an approximation of tau2's own checks, made explicit so it can be reported as
"what breaks" separately from the pass/fail reward.
"""
import json

from . import pricing

WRITE_TOOLS = {
    "fintech": {"issue_refund", "open_dispute", "freeze_card", "escalate_to_human"},
    "retail": {
        "cancel_pending_order", "exchange_delivered_order_items", "modify_pending_order_address",
        "modify_pending_order_items", "modify_pending_order_payment", "modify_user_address",
        "return_delivered_order_items",
    },
}


# arguments that define a write for "harmful write" matching (others, like free-text summaries, are ignored)
KEY_ARGS = {"escalate_to_human": ("reason",)}


def _canon_write(name, args):
    keep = KEY_ARGS.get(name)
    args = {k: v for k, v in (args or {}).items() if keep is None or k in keep}
    return name, _canon_args(args)


def _canon_args(args):
    def norm(v):
        if isinstance(v, list):
            return sorted((norm(x) for x in v), key=json.dumps)
        if isinstance(v, dict):
            return {k: norm(x) for k, x in sorted(v.items())}
        if isinstance(v, (int, float)) and not isinstance(v, bool):
            return round(float(v), 2)  # 35 and 35.0 are the same amount
        return v
    return json.dumps(norm(args or {}), sort_keys=True)


def _usage(msg):
    raw = (msg.get("raw_data") or {}).get("usage") or {}
    u = msg.get("usage") or {}
    inp = raw.get("prompt_tokens", u.get("prompt_tokens", 0)) or 0
    out = raw.get("completion_tokens", u.get("completion_tokens", 0)) or 0
    cached = ((raw.get("prompt_tokens_details") or {}).get("cached_tokens")) or 0
    reasoning = ((raw.get("completion_tokens_details") or {}).get("reasoning_tokens")) or 0
    return inp, cached, out, reasoning


def load(results_path, domain=None):
    r = json.load(open(results_path))
    if domain is None:  # take it from the run's own metadata
        env_info = r["info"].get("environment_info") or {}
        env_info = eval_literal(env_info) if isinstance(env_info, str) else env_info
        domain = env_info.get("domain_name", "retail")
    agent_model = eval_literal(r["info"]["agent_info"])["llm"]
    tasks = {t["id"]: t for t in r["tasks"]}
    writes_set = WRITE_TOOLS[domain]
    episodes = []
    for s in r["simulations"]:
        task = tasks[s["task_id"]]
        gold_writes = {_canon_write(a["name"], a.get("arguments"))
                       for a in (task.get("evaluation_criteria") or {}).get("actions") or []
                       if a["name"] in writes_set}
        msgs = s["messages"]
        # tool results, to know which writes succeeded
        errored = {m.get("id") for m in msgs if m["role"] == "tool" and m.get("error")}
        inp = cached = out = reasoning = calls = tool_calls = writes = harmful = 0
        cost = 0.0
        for m in msgs:
            if m["role"] != "assistant" or m.get("cost") is None and not m.get("usage"):
                continue
            i, c, o, rz = _usage(m)
            if i == 0 and o == 0:
                continue  # the scripted greeting
            calls += 1
            inp, cached, out, reasoning = inp + i, cached + c, out + o, reasoning + rz
            cost += pricing.cost(agent_model, i, c, o)
            for tc in m.get("tool_calls") or []:
                tool_calls += 1
                if tc["name"] in writes_set and tc.get("id") not in errored:
                    writes += 1
                    if _canon_write(tc["name"], tc.get("arguments")) not in gold_writes:
                        harmful += 1
        ri = s.get("reward_info") or {}
        episodes.append(dict(
            scenario=str(s["task_id"]), trial=s.get("trial", 0), model=pricing.canonical(agent_model),
            reward=float(ri.get("reward") or 0.0), cost_usd=cost, input_tokens=inp, cached_tokens=cached,
            output_tokens=out, reasoning_tokens=reasoning, agent_calls=calls, tool_calls=tool_calls,
            writes=writes, harmful_writes=harmful, termination=s.get("termination_reason"),
            duration_s=s.get("duration"), infra_error=not ri,
            messages=msgs, task=task, sim_id=s["id"], user_model=eval_literal(r["info"]["user_info"])["llm"],
            policy=s.get("policy"),
        ))
    return episodes


def eval_literal(text):
    """tau2 stores some info fields as Python reprs of dicts."""
    import ast
    return text if isinstance(text, dict) else ast.literal_eval(text)
