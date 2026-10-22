"""Models, providers and list prices for the Haiku Tax benchmark.

Prices are USD per 1M tokens: (input, cached input, output), checked on 2026-10-19:
- Anthropic: claude.com/pricing (Haiku 5.5 price applies to prompts up to 100K tokens; ours stay far below).
- OpenAI: developers.openai.com/api/docs/pricing (standard tier, short context).
- provider-b: the provider's public price page (Model APIs). No cache price listed for gpt-oss-120b: cached tokens bill
  as input.
- provider-a: its price page needs a login; prices are from an earlier pinned table and third-party listings and are
  UNVERIFIED. Cached input on provider-a is billed at the full input price unless confirmed otherwise.

Open-weight models run on two OpenAI-compatible inference providers with neutral labels. Configure each with
environment variables (see .env.example):
  OPENAI_COMPAT_BASE_URL_PROVIDER_A, OPENAI_COMPAT_API_KEY_PROVIDER_A[, OPENAI_COMPAT_AUTH_PREFIX_PROVIDER_A]
  OPENAI_COMPAT_BASE_URL_PROVIDER_B, OPENAI_COMPAT_API_KEY_PROVIDER_B[, OPENAI_COMPAT_AUTH_PREFIX_PROVIDER_B]
The auth prefix is the text before the key in the Authorization header (default "Bearer ").
Reasoning tokens bill as output everywhere.
"""
import os


def _compat(label):
    """(base URL, API-key env var, auth prefix) for an OpenAI-compatible provider configured by environment variables."""
    suffix = label.upper().replace("-", "_")
    return (os.environ.get(f"OPENAI_COMPAT_BASE_URL_{suffix}", f"<set OPENAI_COMPAT_BASE_URL_{suffix}>").rstrip("/"),
            f"OPENAI_COMPAT_API_KEY_{suffix}", os.environ.get(f"OPENAI_COMPAT_AUTH_PREFIX_{suffix}", "Bearer "))


PROVIDER_A = _compat("provider-a")
PROVIDER_B = _compat("provider-b")
OPENAI = ("https://api.openai.com/v1", "OPENAI_API_KEY", "Bearer ")

# key: (api, endpoint or None, model id, price, tier label)
MODELS = {
    # closed
    "opus-5.5": ("anthropic", None, "claude-opus-5-5", (4.00, 0.20, 20.00), "closed-top"),
    "sonnet-5.5": ("anthropic", None, "claude-sonnet-5-5", (2.00, 0.10, 10.00), "closed-mid"),
    "haiku-5.5": ("anthropic", None, "claude-haiku-5-5", (0.10, 0.01, 0.50), "closed-cheap"),
    "gpt-6.1-sol": ("openai", OPENAI, "gpt-6.1-sol", (2.00, 0.10, 10.00), "closed-mid"),
    "gpt-6-luna": ("openai", OPENAI, "gpt-6-luna", (0.10, 0.01, 0.50), "closed-cheap"),
    "gpt-6-astra": ("openai", OPENAI, "gpt-6-astra", (10.00, 1.00, 50.00), "closed-top"),
    # open, provider 1 / provider 2
    "deepseek-v4.1-flash@provider-a": ("openai", PROVIDER_A, "deepseek-ai/DeepSeek-V4.1-Flash", (0.30, 0.30, 1.20), "open"),
    "deepseek-v4.1-flash@provider-b": ("openai", PROVIDER_B, "deepseek-ai/DeepSeek-V4.1-Flash", (0.30, 0.007, 1.20), "open"),
    "deepseek-v4-pro@provider-a": ("openai", PROVIDER_A, "deepseek-ai/DeepSeek-V4-Pro-0813", (1.75, 0.15, 3.50), "open"),
    "deepseek-v4-pro@provider-b": ("openai", PROVIDER_B, "deepseek-ai/DeepSeek-V4-Pro-0813", (1.32, 0.132, 3.96), "open"),
    "glm-5.3@provider-a": ("openai", PROVIDER_A, "zai-org/GLM-5.3", (1.40, 1.40, 4.40), "open"),
    "glm-5.3@provider-b": ("openai", PROVIDER_B, "zai-org/GLM-5.3", (1.40, 0.14, 4.40), "open"),
    "glm-5.3-flash@provider-a": ("openai", PROVIDER_A, "zai-org/GLM-5.3-Flash", (0.15, 0.15, 0.50), "open"),
    "glm-5.3-flash@provider-b": ("openai", PROVIDER_B, "zai-org/GLM-5.3-Flash", (0.15, 0.03, 0.50), "open"),
    "gpt-oss-120b@provider-a": ("openai", PROVIDER_A, "openai/gpt-oss-120b", (0.15, 0.15, 0.60), "open"),
    "gpt-oss-120b@provider-b": ("openai", PROVIDER_B, "openai/gpt-oss-120b", (0.10, 0.10, 0.50), "open"),
    "kimi-k3@provider-a": ("openai", PROVIDER_A, "moonshotai/Kimi-K3", (3.00, 3.00, 15.00), "open"),
    "kimi-k3@provider-b": ("openai", PROVIDER_B, "moonshotai/Kimi-K3", (3.00, 0.30, 15.00), "open"),
    "qwen3.8-27b@provider-a": ("openai", PROVIDER_A, "Qwen/Qwen3.8-27B", (0.45, 0.45, 3.00), "open"),
    # added Oct 20 after the first grid (newer open models the inventory had filtered out); provider-b prices from
    # its public price page on Oct 20, provider-a prices from third-party listings (unverified)
    "deepseek-v4.1-flash-1017@provider-b": ("openai", PROVIDER_B, "deepseek-ai/DeepSeek-V4.1-Flash-1017", (0.30, 0.007, 1.20), "open"),
    "nemotron-3-ultra@provider-b": ("openai", PROVIDER_B, "nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B", (0.60, 0.12, 2.40), "open"),
    "nemotron-3.5-super@provider-b": ("openai", PROVIDER_B, "nvidia/NVIDIA-Nemotron-3.5-Super-VL-120B-A12B", (0.20, 0.04, 0.50), "open"),
    "muse-spark-open@provider-b": ("openai", PROVIDER_B, "meta-models/muse-spark-open", (1.25, 0.15, 4.25), "open"),
    "beam-1.0@provider-b": ("openai", PROVIDER_B, "reflection/Beam-1.0", (1.30, 0.13, 4.30), "open"),
    "minimax-m3@provider-a": ("openai", PROVIDER_A, "MiniMaxAI/MiniMax-M3", (0.30, 0.30, 1.20), "open"),
    "qwen3.5-397b@provider-a": ("openai", PROVIDER_A, "Qwen/Qwen3.5-397B-A17B", (0.60, 0.60, 3.60), "open"),
}

JEV_PRICE_IN = 0.042  # per 1M input tokens, output free (Jev pre-action check; price given by the user, re-check on the day)


def cost(key, inp, cached, out):
    p_in, p_cached, p_out = MODELS[key][3]
    fresh = max(inp - cached, 0)
    return (fresh * p_in + cached * p_cached + out * p_out) / 1e6


def endpoint(key):
    api, ep, model, _, _ = MODELS[key]
    if api == "anthropic":
        return api, ("https://api.anthropic.com/v1", "EVAL_ANTHROPIC_API_KEY", None), model
    return api, ep, model


def api_key(env_name):
    return os.environ[env_name]
