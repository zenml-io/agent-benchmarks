"""Text-only model calls (judge, simulated underwriter) and the shared agent call.

Agent calls use the vendored client in src/models_client (call_model: Anthropic Messages with prompt caching, OpenAI
Responses with reasoning passed back, OpenAI-compatible chat for open models) and its price table, both copied from the
Haiku Tax benchmark's harness. Keys and endpoints come from the environment only.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))
os.environ.setdefault("PYTHONHASHSEED", "0")  # kept from the original run; subprocesses inherit it
from models_client import models as M  # noqa: E402
from models_client.client import call_model  # noqa: E402,F401

UA = {"User-Agent": "underwriting-bench/0.1", "Content-Type": "application/json"}


def _post(url, body, headers, timeout=180):
    req = urllib.request.Request(url, data=json.dumps(body).encode(), headers={**UA, **headers})
    return json.load(urllib.request.urlopen(req, timeout=timeout))


def complete(key, system, messages, max_tokens=2048):
    """One text completion. messages: [{"role": "user"|"assistant", "content": str}].
    Returns (text, usage dict with input/cached/output, cost USD)."""
    api, (base, key_env, auth), model = M.endpoint(key)
    for attempt in range(6):
        try:
            if api == "anthropic":
                raw = _post(base + "/messages", {"model": model, "max_tokens": max_tokens, "system": system,
                                                 "messages": messages},
                            {"x-api-key": M.api_key(key_env), "anthropic-version": "2023-06-01"})
                text = "".join(b.get("text", "") for b in raw.get("content", []) if b.get("type") == "text")
                u = raw.get("usage", {})
                inp = u.get("input_tokens", 0) + u.get("cache_read_input_tokens", 0) + u.get(
                    "cache_creation_input_tokens", 0)
                usage = dict(input=inp, cached=u.get("cache_read_input_tokens", 0), output=u.get("output_tokens", 0))
            elif base.endswith("openai.com/v1"):
                raw = _post(base + "/responses", {"model": model, "instructions": system, "input": messages,
                                                  "max_output_tokens": max_tokens, "store": False},
                            {"Authorization": "Bearer " + M.api_key(key_env)})
                text = "".join(c.get("text", "") for o in raw.get("output", []) if o.get("type") == "message"
                               for c in o.get("content", []) if c.get("type") == "output_text")
                u = raw.get("usage", {})
                usage = dict(input=u.get("input_tokens", 0),
                             cached=(u.get("input_tokens_details") or {}).get("cached_tokens", 0),
                             output=u.get("output_tokens", 0))
            else:
                raw = _post(base + "/chat/completions", {"model": model, "max_tokens": max_tokens,
                                                         "messages": [{"role": "system", "content": system},
                                                                      *messages]},
                            {"Authorization": auth + M.api_key(key_env)})
                text = raw["choices"][0]["message"].get("content") or ""
                u = raw.get("usage", {})
                usage = dict(input=u.get("prompt_tokens", 0),
                             cached=(u.get("prompt_tokens_details") or {}).get("cached_tokens", 0) or 0,
                             output=u.get("completion_tokens", 0))
            return text, usage, M.cost(key, usage["input"], usage["cached"], usage["output"])
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, KeyError) as e:
            code = getattr(e, "code", None)
            if code in (400, 401, 403, 404) or attempt == 5:
                detail = e.read()[:300] if hasattr(e, "read") else str(e)
                raise RuntimeError(f"{key}: {code} {detail}") from e
            time.sleep(min(2 ** attempt, 30))
