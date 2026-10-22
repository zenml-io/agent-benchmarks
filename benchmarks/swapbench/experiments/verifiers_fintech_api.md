Margin 5 pts. Incumbent next-step self-agreement: tool calls 90.0%, all steps 95.0%.

| candidate | truth: Δ on 240 hidden [95% CI] | truth | next-step tool agreement | nextstep verdict | replay-60 Δ [CI] | replay-60 verdict | replay-260 Δ [CI] | replay-260 verdict |
|---|---|---|---|---|---|---|---|---|
| gpt-5-mini | +0.2 [-2.5, +2.9] | NON-INFERIOR | 84.9% | UNSAFE | +1.7 [-3.3, +6.7] (n=60) | SAFE | -1.9 [-5.4, +1.5] (n=260) | INSUFFICIENT_EVIDENCE |
| gpt-6-luna | -2.5 [-5.4, +0.4] | REGRESSED | 87.6% | SAFE | -1.7 [-8.3, +5.0] (n=60) | INSUFFICIENT_EVIDENCE | -2.3 [-6.5, +1.5] (n=260) | INSUFFICIENT_EVIDENCE |
| gpt-5.4-nano | -37.5 [-42.9, -32.1] | REGRESSED | 75.3% | UNSAFE | -38.3 [-51.7, -25.0] (n=60) | UNSAFE | -40.4 [-46.5, -34.2] (n=260) | UNSAFE |

| verifier | gpt-5-mini | gpt-6-luna | gpt-5.4-nano |
|---|---|---|---|
| nextstep | false alarm | FALSE SAFE | correct |
| replay-60 | correct | abstain | correct |
| replay-260 | abstain | abstain | correct |

## Reading (fintech, API candidates, Oct 14)

**Setup.**
- Incumbent: GPT-5. Candidates: OpenAI models. Simulated customer: Haiku 5.5.
- Truth: 240 hidden scenarios × 2 trials, margin 5 points; any significant rise in unintended actions also counts as a regression.
- Next-step check: GPT-5 agrees with its own recorded next tool call 90.0% of the time, so SAFE needs at least 85.0%.

| Candidate | Cost cut | Truth | Next-step check | Replay 60 | Replay 260 |
|---|---|---|---|---|---|
| **gpt-5-mini** | 82% | **safe**: +0.2 pts [−2.5, +2.9], unintended actions not significantly up | UNSAFE (84.9%, 0.1 pt short) → **false alarm** | SAFE, correct | abstains |
| **GPT-6 Luna** | 99% | **regressed**: −2.5 pts [−5.4, +0.4], unintended actions +0.042/conv [+0.013, +0.071] | SAFE → **false safe** | abstains | abstains |
| **gpt-5.4-nano** | 94% | **regressed**: −37.5 pts, 0.45 unintended actions/conv | UNSAFE, correct | UNSAFE, correct | UNSAFE, correct |

Of Luna's 35 unintended actions on the hidden set:
- 30 are needless escalations to a human;
- 5 are wrong money moves or disputes.

**Same pattern as retail.** Next-step replay produced one false safe and one false alarm, and caught only the gross regression. Full replay was never wrong; it abstained when the evidence was thin.
