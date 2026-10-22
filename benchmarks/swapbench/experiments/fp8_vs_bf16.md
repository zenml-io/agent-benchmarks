# Is the FP8 drop a configuration bug? (Oct 14)

**Question.** In retail, Qwen3.8-27B served from the official FP8 checkpoint lost 9.8 points against the Haiku 5.5
incumbent. Is that the FP8 checkpoint, a serving misconfiguration, or the model?

**Method.**
1. Ran the BF16 checkpoint on the same 240 hidden retail scenarios × 2 trials (plus visible, pool and next-step). The serving
   configuration was identical to the FP8 run: vLLM, qwen3_coder tool parser, qwen3 reasoning parser, one H100, concurrency 16.
   Only the checkpoint differs.
2. Checked every transcript for serving failures, using the Swap Report's endpoint checks.

**Results.**

| retail, 240 hidden × 2 | success | Δ vs Haiku [95% CI] | harm Δ |
|---|---|---|---|
| Qwen3.8-27B BF16 | 87.3% | −8.1 [−12.1, −4.4] | +0.015 [−0.006, +0.037] |
| Qwen3.8-27B FP8 | 85.6% | −9.8 [−13.8, −6.0] | +0.006 [−0.013, +0.023] |
| **FP8 vs BF16** | | **−1.7 [−5.4, +2.1]** | −0.008 [−0.027, +0.008] |

- **Transcripts (FP8):** no tool calls left as text, no empty replies and no abnormal endings. Tool errors were 2 of 4,256 calls; Haiku had 11 of 4,438.
- **Fintech agrees:** FP8 −6.0 vs BF16 −5.6 against GPT-5.

**Answer.** Not a configuration bug, and mostly not FP8. The regression is Qwen3.8-27B itself on these tasks. FP8 costs
another 1.7 points (CI includes 0).

Two serving changes *did* matter, and both are documented elsewhere:
- **The generic `hermes` tool parser** broke 95% of conversations.
- **About 1.4 of FP8's 9.8 points** come from the flawed "cancel a delivered order" scenarios (`scenario_review.md`).

**Also:** the next-step check called the BF16 swap SAFE (92.4% agreement vs 97.3% self-agreement), another false safe.
Replay-260 said NOT ENOUGH EVIDENCE. Its truth is −8.1, so it is regressed, but replay-260's CI over the visible and pool
scenarios reached the margin only partly.

*Correction to earlier informal summaries:* we said the same weights lost about 10 points just from the FP8 checkpoint.
That was wrong. The FP8 checkpoint costs about 1.7 points here, not significant; the base model accounts for the rest.
