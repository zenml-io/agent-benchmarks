| config | episodes | pass^1 | Δ vs incumbent [95% CI] | harmful writes/conv | GPU $/conv (c=12) | cost cut | label |
|---|---|---|---|---|---|---|---|
| moe-a3b | 120 | 0.783 | -5.0 [-12.5, +2.5] | 0.125 | $0.0073 | 94% | REGRESSED |
| qwen27b | 120 | 0.817 | -1.7 [-10.0, +6.7] | 0.133 | $0.0139 | 88% | AMBIGUOUS |
| qwen27b-fp8 | 120 | 0.825 | -0.8 [-8.3, +6.7] | 0.100 | $0.0115 | 90% | AMBIGUOUS |
| qwen27b-hermes | 120 | 0.050 | -78.3 [-87.5, -68.3] | 0.000 | $0.0124 | 89% | REGRESSED |

Incumbent: pass^1 0.833, $0.1118/conv, harmful writes 0.083/conv

## Open-weight candidates on retail-refunds (Oct 13)

**Setup.** Hidden set: tau2 retail test, 40 scenarios × 3 trials, Haiku 5.5 as the customer, the
same as the GPT-5 ground truth. Each config is served by vLLM 0.31 on one H100 on Modal
($3.95/h), at 12 concurrent conversations. GPU $/conv = GPU time ÷ conversations; the ~3 min
startup is excluded.

**Findings.**
- **An open model is a credible swap.** Qwen3.8-27B is within noise of GPT-5 (−1.7 pts
  [−10, +6.7]) at 88% lower cost; with the official FP8 weights, −0.8 at 90% lower cost. FP8 vs
  BF16 on the same model: +0.8 [−5, +6.7], no measurable change.
- **The small MoE (3B active) sits on the margin.** −5.0 pts at 94% lower cost, the same position
  as GPT-6 Luna.
- **The endpoint can break the agent silently.** Same weights, but with vLLM's generic `hermes`
  tool parser instead of the model's own `qwen3_coder`: **5% success (−77 pts)**.
  - Zero tool calls get parsed (7.6 per conversation with the right parser).
  - There are no API errors and every conversation ends normally: the agent talks but never acts.
  - On a cost dashboard this config still shows an 89% cut.

  A provider that picks the wrong parser (or template) ships exactly this. A single-call
  tool-format check would catch this case. Subtler endpoint differences (templates, quantization,
  truncation) need the multi-turn replay.
