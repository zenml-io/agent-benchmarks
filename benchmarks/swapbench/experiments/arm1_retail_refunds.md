# Arm 1 (coding agent alone) on retail-refunds: graded on the hidden set

Hidden set: tau2 retail test, 40 scenarios × 3 trials, Haiku 5.5 customer. Margin 5 pts. Incumbent GPT-5: 83.3%.

| agent | run | submitted config | declared | expected Δ (agent) | hidden Δ [95% CI] | cost cut | truth | outcome |
|---|---|---|---|---|---|---|---|---|
| Claude Code + Sonnet 5.5 | 5JiN5MA | anthropic/claude-haiku-5-5 + prompt suffix | INSUFFICIENT_EVIDENCE | -2.1 [-9.0, 4.5] | +0.0 [-8.3, +7.5] | 89% | AMBIGUOUS | abstain_other |
| Claude Code + Sonnet 5.5 | HKXNPJc | gpt-5-mini-2025-08-07 | UNSAFE | -16.2 [-27, -6] | -6.7 [-15.8, +1.7] | 81% | REGRESSED | correct_reject |
| Claude Code + Sonnet 5.5 | XvENZZQ | gpt-5-mini-2025-08-07 | UNSAFE | -12.0 [-22.0, -3.0] | -6.7 [-15.8, +1.7] | 81% | REGRESSED | correct_reject |
| Claude Code + Sonnet 5.5 | hTm9NzE | gpt-5-2025-08-07 | UNSAFE | -13.0 [-25.0, -2.0] | +0.0 [+0.0, +0.0] | 0% | NON-INFERIOR | abstain_other |
| Codex + GPT-6.1 Sol | Q6XRoxF | gpt-5-mini-2025-08-07 + prompt suffix | UNSAFE | -12.2 [-18.9, -5.4] | +0.8 [-7.5, +9.2] | 84% | AMBIGUOUS | abstain_other |
| Codex + GPT-6.1 Sol | cjBcfr6 | gpt-5.4-mini + args + prompt suffix | UNSAFE | -13.5 [-24.3, -4.1] | -10.0 [-19.2, -0.8] | 77% | REGRESSED | correct_reject |
| Codex + GPT-6.1 Sol | pszKrTK | gpt-5-mini-2025-08-07 + args + prompt suffix | INSUFFICIENT_EVIDENCE | -8.5 [-17.0, 0.9] | -5.0 [-15.0, +5.0] | 84% | REGRESSED | correct_reject |
| Codex + GPT-6.1 Sol | y3A4MWx | openai/gpt-6-luna + args | UNSAFE | -20.3 [-31.9, -9.1] | -17.5 [-30.0, -5.8] | 99% | REGRESSED | correct_reject |

Decisions: {'INSUFFICIENT_EVIDENCE': 2, 'UNSAFE': 6}  Truth: {'AMBIGUOUS': 2, 'REGRESSED': 5, 'NON-INFERIOR': 1}

False-safe: 0 of 8 runs (no run declared SAFE).
