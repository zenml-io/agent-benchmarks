Margin 5 pts. Incumbent next-step self-agreement: tool calls 97.3%, all steps 98.6%.

| candidate | truth: Δ on 240 hidden [95% CI] | truth | next-step tool agreement | nextstep verdict | replay-60 Δ [CI] | replay-60 verdict | replay-260 Δ [CI] | replay-260 verdict |
|---|---|---|---|---|---|---|---|---|
| haiku-null | -2.5 [-6.2, +1.2] | AMBIGUOUS | (= incumbent) | SAFE | +1.7 [-5.0, +8.3] (n=60) | INSUFFICIENT_EVIDENCE | +0.0 [-2.7, +2.7] (n=260) | SAFE |
| qwen27b-fp8 | -12.1 [-17.1, -6.7] | REGRESSED | 92.6% | SAFE | -5.0 [-15.0, +5.0] (n=60) | INSUFFICIENT_EVIDENCE | -11.2 [-15.8, -6.5] (n=260) | UNSAFE |
| moe-a3b | -2.1 [-5.4, +1.2] | AMBIGUOUS | 91.8% | UNSAFE | +3.3 [-3.3, +10.0] (n=60) | SAFE | -2.3 [-5.8, +0.8] (n=260) | INSUFFICIENT_EVIDENCE |
| qwen27b-nothink | -2.1 [-5.8, +1.7] | AMBIGUOUS | 87.8% | UNSAFE | +5.0 [-1.7, +13.3] (n=60) | SAFE | -3.5 [-6.9, +0.0] (n=260) | INSUFFICIENT_EVIDENCE |

| verifier | haiku-null | qwen27b-fp8 | moe-a3b | qwen27b-nothink |
|---|---|---|---|---|
| nextstep | n/a (truth ambiguous) | FALSE SAFE | n/a (truth ambiguous) | n/a (truth ambiguous) |
| replay-60 | n/a (truth ambiguous) | abstain | n/a (truth ambiguous) | n/a (truth ambiguous) |
| replay-260 | n/a (truth ambiguous) | correct | n/a (truth ambiguous) | n/a (truth ambiguous) |

## Interim reading (Oct 14)

**Setup.**
- Incumbent: Claude Haiku 5.5. Candidates: self-hosted Qwen on Modal.
- Task: the generated multi-request retail task (`retail-composite`).
- Truth: full replay on 240 hidden scenarios, 1 trial.

**Findings.**
- **Next-step replay (smithtune-style) passes a regression.**
  - Qwen3.8-27B-FP8 agrees with the incumbent's next tool call 92.6% of the time, within 5 points of the incumbent's own 97.3%, so the check says SAFE.
  - On full conversations it is **12.1 points worse** (−17.1 to −6.7).
  - The two candidates the check rejects (MoE 91.8%, reasoning-off 87.8%) are only about 2 points worse end to end.
  - Step agreement ranks the candidates in the wrong order.
- **Replay on 60 scenarios** cannot separate −12 from 0 (FP8: −5.0 [−15, +5]). It says SAFE for both −2-point candidates, overstating them by 5–8 points.
- **Replay on 260 scenarios** calls the regression (−11.2 [−15.8, −6.5], UNSAFE). It abstains on the close ones.
- **The truth needs repeats.** The incumbent against itself moves −2.5 [−6.2, +1.2] on 240 scenarios. A second hidden-set trial is scheduled for the ambiguous candidates.
