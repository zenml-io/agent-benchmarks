"""Models, endpoints and list prices for the underwriting benchmark.

Vendored from the Haiku Tax benchmark's harness (models.py), reduced to the 12 models this benchmark ran. Prices are
USD per 1M tokens: (input, cached input, output), checked on 2026-10-19:
- Anthropic: claude.com/pricing.
- OpenAI: developers.openai.com/api/docs/pricing (standard tier, short context).
- provider-a (the commercial inference provider that served every open-weight model): its price page needs a login;
  prices are from an earlier pinned table and third-party listings and are UNVERIFIED. Cached input is billed at the
  full input price unless confirmed otherwise.
Reasoning tokens bill as output everywhere.

Endpoints come from the environment only (see .env.example):
- Anthropic models: EVAL_ANTHROPIC_API_KEY.
- OpenAI models: OPENAI_API_KEY.
- Open-weight models (keys ending in "@provider-a"): any OpenAI-compatible chat-completions endpoint, configured with
  OPENAI_COMPAT_BASE_URL_PROVIDER_A (for example https://host/v1) and OPENAI_COMPAT_API_KEY_PROVIDER_A.
"""
import os

OPENAI = ("https://api.openai.com/v1", "OPENAI_API_KEY", "Bearer ")
ANTHROPIC = ("https://api.anthropic.com/v1", "EVAL_ANTHROPIC_API_KEY", None)
PROVIDER_A = "provider-a"  # resolved from the environment at call time

# key: (api, endpoint or provider label, model id, price, tier label)
MODELS = {
    # closed
    "opus-5.5": ("anthropic", None, "claude-opus-5-5", (4.00, 0.20, 20.00), "closed-top"),
    "sonnet-5.5": ("anthropic", None, "claude-sonnet-5-5", (2.00, 0.10, 10.00), "closed-mid"),
    "haiku-5.5": ("anthropic", None, "claude-haiku-5-5", (0.10, 0.01, 0.50), "closed-cheap"),
    "gpt-6.1-sol": ("openai", OPENAI, "gpt-6.1-sol", (2.00, 0.10, 10.00), "closed-mid"),
    "gpt-6-luna": ("openai", OPENAI, "gpt-6-luna", (0.10, 0.01, 0.50), "closed-cheap"),
    # open weights, one commercial inference provider
    "deepseek-v4.1-flash@provider-a": ("openai", PROVIDER_A, "deepseek-ai/DeepSeek-V4.1-Flash", (0.30, 0.30, 1.20), "open"),
    "deepseek-v4-pro@provider-a": ("openai", PROVIDER_A, "deepseek-ai/DeepSeek-V4-Pro-0813", (1.75, 0.15, 3.50), "open"),
    "glm-5.3@provider-a": ("openai", PROVIDER_A, "zai-org/GLM-5.3", (1.40, 1.40, 4.40), "open"),
    "glm-5.3-flash@provider-a": ("openai", PROVIDER_A, "zai-org/GLM-5.3-Flash", (0.15, 0.15, 0.50), "open"),
    "gpt-oss-120b@provider-a": ("openai", PROVIDER_A, "openai/gpt-oss-120b", (0.15, 0.15, 0.60), "open"),
    "qwen3.8-27b@provider-a": ("openai", PROVIDER_A, "Qwen/Qwen3.8-27B", (0.45, 0.45, 3.00), "open"),
    "minimax-m3@provider-a": ("openai", PROVIDER_A, "MiniMaxAI/MiniMax-M3", (0.30, 0.30, 1.20), "open"),
}

JEV_PRICE_IN = 0.042  # Jev judge, per 1M input tokens, output free (list price given to us; re-check on the day)


def cost(key, inp, cached, out):
    p_in, p_cached, p_out = MODELS[key][3]
    fresh = max(inp - cached, 0)
    return (fresh * p_in + cached * p_cached + out * p_out) / 1e6


def _compat(label):
    suffix = label.upper().replace("-", "_")
    base_env = f"OPENAI_COMPAT_BASE_URL_{suffix}"
    base = os.environ.get(base_env)
    if not base:
        # A KeyError, like a missing API key: harness/run.py records the case as harness_error (excluded, re-run).
        raise KeyError(f"set {base_env} (and OPENAI_COMPAT_API_KEY_{suffix}) for {label} models")
    return (base.rstrip("/"), f"OPENAI_COMPAT_API_KEY_{suffix}", "Bearer ")


def endpoint(key):
    """(api, (base URL, key env var name, auth prefix), model id)."""
    api, ep, model, _, _ = MODELS[key]
    if api == "anthropic":
        return api, ANTHROPIC, model
    if isinstance(ep, str):
        ep = _compat(ep)
    return api, ep, model


def api_key(env_name):
    return os.environ[env_name]
