# How many replay scenarios does a verdict need? (offline, Oct 14)

`python scripts/sample_size.py` on data already collected. It pools every scenario that both the incumbent and the candidate ran (60 train + 200 pool + 240 hidden = 500, trials averaged per scenario). Then, using the normal approximation, it asks how many scenarios a 95% CI needs before it clears the 5-point margin. Harm is a separate gate: the lower bound of the harmful-writes delta must clear 0.01 per episode.

## Retail (Haiku 5.5 incumbent)

| candidate | scenarios | Δ success | sd | n for a success verdict | verdict | Δ harmful writes/episode | n to flag harm |
|---|---|---|---|---|---|---|---|
| qwen27b-fp8 | 500 | -10.7 | 0.36 | 152 | UNSAFE | +0.011 | 86144 |
| moe-a3b | 500 | -1.7 | 0.25 | 224 | SAFE | -0.004 | never |
| qwen27b-nothink | 500 | -3.2 | 0.28 | 939 | SAFE | +0.003 | never |

## Fintech (GPT-5 incumbent)

| candidate | scenarios | Δ success | sd | n for a success verdict | verdict | Δ harmful writes/episode | n to flag harm |
|---|---|---|---|---|---|---|---|
| gpt-5-mini-2025-08-07 | 500 | -0.9 | 0.25 | 146 | SAFE | +0.026 | 757 |
| openai_responses_gpt-6-luna | 500 | -2.4 | 0.29 | 470 | SAFE | +0.034 | 501 |
| gpt-5.4-nano | 500 | -39.0 | 0.49 | 8 | UNSAFE | +0.417 | 8 |

## Harm rate per split (harmful writes per episode / task success)

| model | train (60 × 1) | pool (200 × 1) | hidden (240 × 2) |
|---|---|---|---|
| GPT-5 (incumbent) | 0.050 / 95.0% | 0.035 / 93.5% | 0.031 / 94.2% |
| gpt-5-mini | 0.033 / 96.7% | 0.085 / 90.5% | 0.048 / 94.4% |
| GPT-6 Luna | 0.067 / 93.3% | 0.065 / 91.0% | 0.073 / 91.7% |

## What this means

- **The scenario budget a verdict needs depends on how close the candidate sits to the margin, not on the domain.**
  - Clear cases need tens to ~150 scenarios: the broken nano (8), FP8 retail (152), gpt-5-mini on success (146).
  - Close calls need 500–950: Luna (470 on success, ~500 on harm) and nothink (939).
  - This explains why replay-260 abstained on exactly the close calls. A verifier should say how many more scenarios it needs, and a generator makes them cheap. A fixed visible test set cannot do that.
- **Honest correction to the fintech truth labels.**
  - On the hidden 240, gpt-5-mini is NON-INFERIOR and Luna is REGRESSED (harm).
  - Pooled over 500 scenarios, both raise harmful writes: mini +0.026/episode, Luna +0.034/episode.
  - Mini's pool split alone looks worse than Luna's.
  - So mini vs Luna is a close pair. The robust fintech claims are:
    1. next-step agreement called Luna SAFE while full replay shows a harm rise;
    2. replay-260 abstains on both rather than guessing.
  - "mini is safe" holds for the hidden-set success rate, not for harm.
- **Next-step agreement carries no sample-size signal.** It reports a percentage over ~1–2k steps with no notion of how close the candidate is to the decision boundary. It never abstains.
