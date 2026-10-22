# Who plays the customer decides the swap verdict (Oct 13)

**Setup.** 40 generated multi-request retail scenarios (`gen_retail --kinds composite --seed 23`),
3 trials each. Two candidate agent models, and two simulated customers driven by the same script.
Grading is DB-state only.

| Agent | Haiku 5.5 plays the customer | gpt-4.1-mini plays the customer |
|---|---|---|
| claude-haiku-5-5 | 94.2% (harmful writes 0.00/conv) | 81.7% (0.08/conv) |
| gpt-6-luna | 92.5% (0.00/conv) | 62.5% (0.19/conv) |
| **Luna vs Haiku** | **−1.7 pts [−9.2, +5.0]** → passes a 5-pt margin | **−19.2 pts [−31.7, −6.7]** → clearly regressed |

The gap between the two Luna-vs-Haiku deltas is **+17.5 pts [+4.2, +30.8]** (paired cluster
bootstrap over scenarios). Swapping only the simulated customer turns "safe to switch to Luna" into
"Luna is 19 points worse".

## Why

We read the trajectories. gpt-4.1-mini often **breaks its script**. Told "if it can't be
cancelled, accept it and move on", it accepts the return the agent offers instead. Luna offers
alternatives more readily than Haiku. With a compliant customer that becomes an extra database
write, which the by-construction ground truth counts as wrong.

Of Luna's 45 failures under gpt-4.1-mini:
- 21 contain a write outside the gold set;
- 17 have the right kinds of writes but a different final DB;
- 7 never wrote at all.

The failures mix real agent behaviour (pushing alternatives, mis-scoped writes) with simulator
deviations.

## Consequences for a swap referee

1. **The replay harness is part of the verdict.** A "safe to switch" answer is only as good as the
   simulated users and judges behind it. That is the "calibrated judges/simulators" part of the
   product, and it is measurable. We would report simulator fidelity (instruction adherence of user
   turns) next to every verdict.
2. **Ground truth by construction assumes a faithful user.** An unfaithful simulator corrupts the
   ground truth, not just the noise. SwapBench task 2 therefore uses the more faithful simulator
   (Haiku).
3. **Self-preference was not the issue.** The Haiku simulator raised Luna (+30 pts) more than it
   raised Haiku (+12.5 pts). Its effect is fidelity, not favouring its own model family.
4. **Still to check:** whether real customers behave more like the scripted user or like
   gpt-4.1-mini. Accepting an offered alternative is realistic, and then the gold set, not the
   agent, is wrong. A production referee should replay with simulators fitted to the team's own
   customer turns.
