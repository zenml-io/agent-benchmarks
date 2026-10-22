Margin 5 pts. Incumbent next-step self-agreement: tool calls 97.3%, all steps 98.6%.

| candidate | truth: Δ on 240 hidden [95% CI] | truth | next-step tool agreement | nextstep verdict | replay-60 Δ [CI] | replay-60 verdict | replay-260 Δ [CI] | replay-260 verdict |
|---|---|---|---|---|---|---|---|---|
| haiku-null | -2.1 [-5.4, +1.2] | AMBIGUOUS | (= incumbent) | SAFE | +1.7 [-5.0, +8.3] (n=60) | INSUFFICIENT_EVIDENCE | +0.0 [-2.7, +2.7] (n=260) | SAFE |
| qwen27b-fp8 | -9.8 [-13.8, -6.0] | REGRESSED | 92.6% | SAFE | -5.0 [-15.0, +5.0] (n=60) | INSUFFICIENT_EVIDENCE | -11.2 [-15.8, -6.5] (n=260) | UNSAFE |
| moe-a3b | -0.6 [-3.3, +2.1] | NON-INFERIOR | 91.8% | UNSAFE | +3.3 [-3.3, +10.0] (n=60) | SAFE | -2.3 [-5.8, +0.8] (n=260) | INSUFFICIENT_EVIDENCE |
| qwen27b-nothink | -2.5 [-5.4, +0.2] | AMBIGUOUS | 87.8% | UNSAFE | +5.0 [-1.7, +13.3] (n=60) | SAFE | -3.5 [-6.9, +0.0] (n=260) | INSUFFICIENT_EVIDENCE |
| qwen27b-hermes | -95.0 [-97.1, -92.7] | REGRESSED | 0.0% | UNSAFE | -93.3 [-98.3, -86.7] (n=60) | UNSAFE | -96.5 [-98.5, -94.2] (n=260) | UNSAFE |

| verifier | haiku-null | qwen27b-fp8 | moe-a3b | qwen27b-nothink | qwen27b-hermes |
|---|---|---|---|---|---|
| nextstep | n/a (truth ambiguous) | FALSE SAFE | false alarm | n/a (truth ambiguous) | correct |
| replay-60 | n/a (truth ambiguous) | abstain | correct | n/a (truth ambiguous) | correct |
| replay-260 | n/a (truth ambiguous) | correct | abstain | n/a (truth ambiguous) | correct |

## Reading (final retail run, Oct 14)

**Setup.**
- Incumbent: Claude Haiku 5.5. Candidates: self-hosted Qwen on Modal (vLLM, one H100).
- Task: generated multi-request retail conversations.
- Truth: full replay on 240 hidden scenarios, 2 trials each (incumbent and the three Qwen candidates), margin 5 points.

**Results by verifier.**

| Verifier | Correct | Wrong | Abstained |
|---|---|---|---|
| **Next-step replay** (smithtune-style: agreement with the incumbent's recorded next tool call; tools not executed, no simulated user) | 1: the broken endpoint | 2: approved Qwen FP8 at **−9.8 [−13.8, −6.0]**; rejected the MoE at **−0.6 [−3.3, +2.1]** | 0 |
| **Full replay, 60 scenarios** | 2 | 0 | 1: FP8 |
| **Full replay, 260 scenarios** | 2 | 0 | 1: MoE (would need ~500 scenarios to approve it) |

- **Next-step replay ranks by imitation, not outcome.** FP8 matches the incumbent's next step best among the working candidates (92.6% vs 97.3% self-agreement), yet fails customers most once whole conversations are played out.
- **Replay on 60 scenarios** also called SAFE for the reasoning-off model (+5.0 on 60 vs −2.5 on 480 hidden episodes): small visible samples overstate candidates.

Caveat: one domain and one incumbent. The fintech replication (GPT-5 incumbent, OpenAI and Qwen candidates, and a second simulated customer) is running.
