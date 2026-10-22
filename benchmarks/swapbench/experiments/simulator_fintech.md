# Fintech: does the swap verdict survive a different simulated customer? (Oct 14)

Hidden set, 240 scenarios, 1 trial each, same agents; only the simulated customer changes.

| agent | success, Haiku customer | success, GPT-6.1 Sol customer | Δ vs GPT-5 (Haiku customer) | Δ vs GPT-5 (Sol customer) | unintended actions/conv (Haiku → Sol) |
|---|---|---|---|---|---|
| gpt-5-2025-08-07 | 92.1% (n=240) | 97.1% (n=240) | incumbent | incumbent | 0.037 → 0.000 |
| gpt-5-mini-2025-08-07 | 93.8% (n=240) | 96.2% (n=240) | +1.7 [-2.1, +5.8] | -0.8 [-3.3, +1.7] | 0.054 → 0.025 |
| openai_responses_gpt-6-luna | 91.7% (n=240) | 96.7% (n=240) | -0.4 [-4.6, +3.8] | -0.4 [-3.3, +2.5] | 0.075 → 0.033 |
| gpt-5.4-nano | 54.6% (n=240) | 56.7% (n=240) | -37.5 [-44.2, -30.8] | -40.4 [-46.7, -34.2] | 0.458 → 0.342 |

## Reading

**Two capable simulated customers agree on the verdicts.** Replacing Haiku 5.5 with GPT-6.1 Sol as the customer:

| | Change with Sol as customer |
|---|---|
| Every agent's success rate | up by 2–5 points |
| Unintended actions | about halved (fewer ambiguous turns to over-react to) |
| Gaps that decide the swap | barely move: mini +1.7 → −0.8, Luna −0.4 → −0.4, nano −37.5 → −40.4 |

On retail, a weaker simulator (gpt-4.1-mini) that broke its script flipped a verdict by 17.5 points (`simulator.md`).

So the simulated customer needs to be good enough to follow the scenario. Past that bar, verdicts on these tasks are stable. The level it shifts (absolute success rates) is not what a swap decision depends on.

Caveats:
- Both simulators are strong, general assistants; neither is a purpose-built user model.
- Real customer behaviour is still untested.
