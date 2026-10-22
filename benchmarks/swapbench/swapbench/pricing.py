"""Pinned list prices in USD per 1M tokens: (input, cached input, output). Snapshot of litellm's
model_cost table on 2026-10-13; reasoning tokens bill as output. Change only with a dated note."""

PRICES = {
    "gpt-5-2025-08-07": (1.25, 0.125, 10.0),
    "gpt-5-mini-2025-08-07": (0.25, 0.025, 2.0),
    "gpt-5-nano-2025-08-07": (0.05, 0.005, 0.40),
    "gpt-5.4-mini": (0.75, 0.075, 4.5),
    "gpt-5.4-nano": (0.20, 0.02, 1.25),
    "gpt-4.1-mini-2025-04-14": (0.40, 0.10, 1.60),
    "gpt-4.1-2025-04-14": (2.0, 0.50, 8.0),
    "gpt-6-luna": (0.10, 0.01, 0.50),
    "gpt-6.1-sol": (2.0, 0.10, 10.0),
    "claude-haiku-5-5": (0.10, 0.01, 0.50),
    "claude-sonnet-5-5": (2.0, 0.20, 10.0),
}

# Hosted open models, keyed by the full litellm model string because prices differ by provider. The published runs
# used four commercial providers' list prices checked on 2026-10-15. Provider names and their prices are not in this
# public repository: put them in a JSON file {"<litellm model string>": [input, cached input, output], ...} and point
# SWAPBENCH_PROVIDER_PRICES at it (see providers.example.json). No listed cache price = cached tokens bill as input.
import json as _json
import os as _os

PROVIDER_PRICES = {}
if _os.environ.get("SWAPBENCH_PROVIDER_PRICES"):
    PROVIDER_PRICES = {k: tuple(v) for k, v in _json.load(open(_os.environ["SWAPBENCH_PROVIDER_PRICES"])).items()}


def canonical(model: str) -> str:
    """Strip litellm routing prefixes: 'openai/responses/gpt-6-luna' -> 'gpt-6-luna'."""
    return model.split("/")[-1]


def cost(model: str, input_tokens: int, cached_tokens: int, output_tokens: int) -> float:
    """Token cost of an API model; 0 for self-hosted models (their cost is GPU time, accounted separately)."""
    if model in PROVIDER_PRICES:
        p_in, p_cached, p_out = PROVIDER_PRICES[model]
    elif canonical(model) in PRICES:
        p_in, p_cached, p_out = PRICES[canonical(model)]
    else:
        return 0.0
    fresh = max(input_tokens - cached_tokens, 0)
    return (fresh * p_in + cached_tokens * p_cached + output_tokens * p_out) / 1e6
