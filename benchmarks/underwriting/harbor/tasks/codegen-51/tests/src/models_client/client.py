"""The agent's chat call: Anthropic Messages (prompt caching), OpenAI Responses (reasoning passed back), and
OpenAI-compatible chat completions for open-weight models.

Vendored unchanged in behavior from the Haiku Tax benchmark's harness/run.py (call_model, _anthropic, _responses and
the EXTRA request fields); its Haiku-Tax-only parts (task loop, policy check, hash-seed re-exec) are left out.
Keys come from the environment only (models.py).
"""
import json
import time
import urllib.error
import urllib.request

from . import models as M

UA = {"User-Agent": "underwriting-bench/0.1", "Content-Type": "application/json"}
MAX_OUT = 8192
# Extra request fields per API ("anthropic", "responses", "chat"), e.g. an effort level; empty by default. The
# underwriting effort arms set it per run (harness/run.py --effort).
EXTRA = {"anthropic": {}, "responses": {}, "chat": {}}

def http(url, body, headers, timeout=300):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={**UA, **headers})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def call_model(key, messages, tools):
    """One chat call with retries. Returns (msg dict in OpenAI format, usage dict, latency_s, n_retries)."""
    api, (base, key_env, auth), model = M.endpoint(key)
    retries = 0
    while True:
        t0 = time.time()
        try:
            if api == "anthropic":
                r = _anthropic(base, M.api_key(key_env), model, messages, tools)
            elif base.endswith("openai.com/v1"):
                r = _responses(base, M.api_key(key_env), model, messages, tools)
            else:
                clean = [{k: v for k, v in m.items() if not k.startswith("_")} for m in messages]
                body = {"model": model, "messages": clean, "tools": tools, "max_tokens": MAX_OUT, **EXTRA["chat"]}
                raw = http(base + "/chat/completions", body, {"Authorization": auth + M.api_key(key_env)})
                u = raw.get("usage") or {}
                det = u.get("prompt_tokens_details") or {}
                cached = det.get("cached_tokens") or u.get("prompt_cache_hit_tokens") or 0
                rz = (u.get("completion_tokens_details") or {}).get("reasoning_tokens") or u.get("reasoning_tokens") or 0
                ch = raw["choices"][0]
                ch["message"]["_finish"] = ch.get("finish_reason")
                r = (ch["message"], dict(input=u.get("prompt_tokens", 0), cached=cached,
                                                         output=u.get("completion_tokens", 0), reasoning=rz))
            return r[0], r[1], time.time() - t0, retries
        except urllib.error.HTTPError as e:
            msg = e.read().decode()[:300]
            if e.code in (402, 412) or "suspended" in msg or "Credit limit" in msg:
                raise RuntimeError(f"account_blocked {e.code}: {msg}")
            if e.code in (408, 409, 429, 500, 502, 503, 504, 529) and retries < 6:
                retries += 1
                time.sleep(min(2 ** retries, 60))
                continue
            raise RuntimeError(f"api_error {e.code}: {msg}")
        except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
            if retries < 4:
                retries += 1
                time.sleep(2 ** retries)
                continue
            raise RuntimeError(f"timeout: {e}")


def _anthropic(base, key, model, messages, tools):
    """OpenAI-format messages and tools -> Anthropic Messages API, with prompt caching on the system prompt, tools and
    the latest turn (the vendor's recommended setup for multi-turn agents)."""
    system = [{"type": "text", "text": messages[0]["content"], "cache_control": {"type": "ephemeral"}}]
    conv = []
    for m in messages[1:]:
        if m["role"] == "user":
            conv.append({"role": "user", "content": [{"type": "text", "text": m["content"]}]})
        elif m["role"] == "assistant":
            c = [{"type": "text", "text": m["content"]}] if m.get("content") else []
            for t in m.get("tool_calls") or []:
                try:
                    args = json.loads(t["function"]["arguments"] or "{}")
                except json.JSONDecodeError:
                    args = {}
                c.append({"type": "tool_use", "id": t["id"], "name": t["function"]["name"], "input": args})
            conv.append({"role": "assistant", "content": c or [{"type": "text", "text": "(no reply)"}]})
        elif m["role"] == "tool":
            block = {"type": "tool_result", "tool_use_id": m["tool_call_id"], "content": m["content"]}
            if conv and conv[-1]["role"] == "user" and conv[-1]["content"][0].get("type") == "tool_result":
                conv[-1]["content"].append(block)
            else:
                conv.append({"role": "user", "content": [block]})
    if conv:
        conv[-1]["content"][-1] = {**conv[-1]["content"][-1], "cache_control": {"type": "ephemeral"}}
    atools = [{"name": t["function"]["name"], "description": t["function"].get("description", ""),
               "input_schema": t["function"]["parameters"]} for t in tools]
    atools[-1] = {**atools[-1], "cache_control": {"type": "ephemeral"}}
    raw = http(base + "/messages", {"model": model, "max_tokens": MAX_OUT, "system": system, "tools": atools,
                                    "messages": conv, **EXTRA["anthropic"]},
               {"x-api-key": key, "anthropic-version": "2023-06-01"})
    text = "".join(b.get("text", "") for b in raw["content"] if b["type"] == "text")
    calls = [{"id": b["id"], "type": "function", "function": {"name": b["name"], "arguments": json.dumps(b["input"])}}
             for b in raw["content"] if b["type"] == "tool_use"]
    u = raw.get("usage", {})
    cached = u.get("cache_read_input_tokens", 0)
    written = u.get("cache_creation_input_tokens", 0)
    # cache writes bill at 1.25x input: count them as input plus a quarter extra
    inp = u.get("input_tokens", 0) + cached + written + written // 4
    return ({"role": "assistant", "content": text or None, "tool_calls": calls or None},
            dict(input=inp, cached=cached, output=u.get("output_tokens", 0), reasoning=0))


def _responses(base, key, model, messages, tools):
    """OpenAI Responses API (needed for GPT-6 models to use tools with reasoning). Stateless: earlier output items,
    including encrypted reasoning, are replayed as input."""
    items = []
    for m in messages[1:]:
        if m["role"] == "user":
            items.append({"role": "user", "content": m["content"]})
        elif m["role"] == "assistant":
            if m.get("_items"):
                items.extend(m["_items"])
            else:
                if m.get("content"):
                    items.append({"role": "assistant", "content": m["content"]})
                for t in m.get("tool_calls") or []:
                    items.append({"type": "function_call", "call_id": t["id"], "name": t["function"]["name"],
                                  "arguments": t["function"]["arguments"]})
        elif m["role"] == "tool":
            items.append({"type": "function_call_output", "call_id": m["tool_call_id"], "output": m["content"]})
    rtools = [{"type": "function", "name": t["function"]["name"], "description": t["function"].get("description", ""),
               "parameters": t["function"]["parameters"]} for t in tools]
    raw = http(base + "/responses", {"model": model, "instructions": messages[0]["content"], "input": items,
                                     "tools": rtools, "max_output_tokens": MAX_OUT, "store": False,
                                     "include": ["reasoning.encrypted_content"], **EXTRA["responses"]},
               {"Authorization": "Bearer " + key})
    out = raw.get("output") or []
    text = "".join(c.get("text", "") for o in out if o.get("type") == "message" for c in o.get("content") or []
                   if c.get("type") == "output_text")
    calls = [{"id": o["call_id"], "type": "function", "function": {"name": o["name"], "arguments": o.get("arguments") or "{}"}}
             for o in out if o.get("type") == "function_call"]
    keep = [{k: v for k, v in o.items() if k not in ("status",)} for o in out if o.get("type") in ("reasoning", "function_call", "message")]
    u = raw.get("usage") or {}
    return ({"role": "assistant", "content": text or None, "tool_calls": calls or None, "_items": keep},
            dict(input=u.get("input_tokens", 0), cached=(u.get("input_tokens_details") or {}).get("cached_tokens", 0),
                 output=u.get("output_tokens", 0), reasoning=(u.get("output_tokens_details") or {}).get("reasoning_tokens", 0)))


