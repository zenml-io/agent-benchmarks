# Fintech verifiers: open-weight Qwen candidates vs GPT-5 (Oct 14)

`scripts/verifiers.py`, incumbent GPT-5, Haiku 5.5 customer.

- Truth: 240 hidden scenarios, paired cluster bootstrap, 5-point margin.
- Qwen BF16 ran 2 trials per hidden scenario. FP8 and MoE combine a full trial with a second trial cut short by a restart: 205 and 241 extra episodes.
- All candidates were served on one H100 each via vLLM.

Margin 5 pts. Incumbent next-step self-agreement: tool calls 90.0%, all steps 95.0%.

| candidate | truth: Δ on 240 hidden [95% CI] | truth | next-step tool agreement | nextstep verdict | replay-60 Δ [CI] | replay-60 verdict | replay-260 Δ [CI] | replay-260 verdict |
|---|---|---|---|---|---|---|---|---|
| qwen27b | -5.6 [-8.8, -2.5] | REGRESSED | 85.7% | SAFE | -5.0 [-13.3, +3.3] (n=60) | INSUFFICIENT_EVIDENCE | -5.8 [-9.6, -1.9] (n=260) | UNSAFE |
| qwen27b-fp8 | -6.0 [-9.4, -2.9] | REGRESSED | 88.4% | SAFE | -1.7 [-8.3, +5.0] (n=60) | INSUFFICIENT_EVIDENCE | -4.6 [-8.8, -0.4] (n=260) | UNSAFE |
| moe-a3b | -4.2 [-7.9, -0.4] | AMBIGUOUS | 85.3% | SAFE | -1.7 [-8.3, +5.0] (n=60) | INSUFFICIENT_EVIDENCE | -3.1 [-6.9, +0.8] (n=260) | INSUFFICIENT_EVIDENCE |


**Reading.**
- **Next-step agreement:** called all three Qwen candidates SAFE. Their agreement (85–88%) sits within 5 points of GPT-5's self-agreement (90%). Two of them lose 5.6 and 6.0 points of task success on the hidden set: false safes.
- **Replay-60:** abstained on all three.
- **Replay-260:** flagged both regressions, and abstained on the MoE, whose truth is itself ambiguous (−4.2 [−7.9, −0.4]).

This replicates the retail result in a second domain with a different incumbent:
- next-step agreement gives confident wrong answers;
- full replay with enough scenarios is right or abstains.

Across both domains, next-step agreement made 4 false safes and 2 false alarms. Full replay made 0 false safes.
