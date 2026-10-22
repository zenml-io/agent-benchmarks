# Can a few expert answers beat a frontier judge? (Oct 15)

**Short answer.** Yes, on our bank set: a rubric written from about 400 expert answers per decision, checked by Jev
on each risky action, is as safe as GPT-6.1 Sol checking the same rubric. It also resolves more conversations on
both agents, and its check costs about 1/170th as much. On the swap test (DeepSeek-V4.1-Flash, nothing re-tuned), it
lifts resolution by 12 points, 12 points past GPT-5, at a third of GPT-5's cost. Every check we tried removes the hidden-rule violations: from 37% of
conversations to under 1%. But only a *precise* rulebook also raises resolution. The interview rubric found all five
hidden rules, and it also invented six. Those extra rules block valid actions and cancel the gain.

Files:
- offline results: `expert_deciders_offline.md`;
- rubric vs hidden rules: `expert_deciders_rubric_check.md`;
- spend: `expert_deciders_costs.md`;
- live table: `expert_deciders_online.md`.

## Setup

**Scenarios.**
- Our own bank (fintech) set has 500 generated scenarios: 60 visible, 240 hidden and 200 pool.
- Everything below is the **240 hidden scenarios, run twice: 480 conversations per run**.
- This is not tau2-bench's public task set. We use tau2 only as the harness: user simulator, tools, end-state grading.
- The customer is Claude Haiku 5.5.

**Hidden rules** (`swapbench/hidden_rules.py`). The bank has five working rules that the agent's written policy does
not mention:
- H1: credit-limit requests go to the app, not a human;
- H2: after two failed identity checks, send the customer to a branch, no handoff;
- R1: duplicate refunds over $300 go to a human;
- R2: fee refunds only for fees from the last 30 days;
- C1: no card freeze for an unauthorized charge under $150.

The gold end state is adjusted for these rules: 88 of the 240 hidden scenarios change. So no agent, GPT-5
included, can resolve those scenarios without being told. That is why resolution here is around 50–60% rather than
the ~94% GPT-5 gets on the written-policy gold.

**Experts.** Two simulated experts, Claude Haiku 5.5 and GPT-5 mini, each answer "should this go ahead?" with one
sentence of why. Each knows the written policy and the hidden rules, and 10% of answers are flipped at random to
mimic disagreement. Without the flips they agree well (kappa 0.84 / 0.75 / 0.91 by decision point). With them, kappa
is 0.47–0.68, so the brief's agreement gate (kappa ≥ 0.7) fails by construction. We went ahead and graded against both
the hidden-rule truth and the experts' consensus.

**Live arms.** Each check sits in front of the three risky actions: handoff, refund and card freeze. When it says
"should not" (p > 0.5), the action is withheld and the agent is told it was blocked, at most twice per turn.

| arm | what checks the action |
|---|---|
| none | nothing (the cheap agent alone) |
| C | Jev + the interview rubric (GPT-6.1 Sol wrote it from the experts' answers on training steps) |
| D | GPT-6.1 Sol as judge + the same rubric + 6 labelled examples |
| H (hybrid) | handoffs: a TF-IDF + logistic model trained on 400 expert labels; refunds and cards: C |
| G (ceiling) | Jev + the hidden rules written out (what a perfect interview would give) |
| GPT-5 | GPT-5 with no check (the incumbent) |

We dropped arm E (small model on 25/100/200 labels) and arm F (outcome labels), as agreed. Offline they were no better
than C, except E/T on handoffs, which is why the hybrid is in.

- **Agent A** (the cheap agent): Qwen3.8-27B on a commercial inference provider (not named).
- **Swap test, agent B:** DeepSeek-V4.1-Flash on the same provider, with the same checks and the same rubric, nothing re-tuned.

**Prices.**
- The agent's own calls are logged, including discarded ones.
- Jev is priced at $0.042 per 1M input tokens. The judge is priced at GPT-6.1 Sol's rates.
- Jev and judge tokens are estimated per decision from the offline mean: C 3,344, G 2,231, D 10,153 in / ~200 out.

## Results: agent A (Qwen3.8-27B)

Paired 95% cluster-bootstrap intervals over scenarios.

| Qwen + check | resolved | vs Qwen alone | vs GPT-5 | conversations with a rule violation | handoffs / conv. | unneeded handoffs / conv. | cost / conv. (of which check) |
|---|---|---|---|---|---|---|---|
| none | 52.7% | — | −7.3 [−10.8, −4.0] | 37.3% | 0.37 | 0.16 | 2.34¢ |
| **C** Jev + rubric | 54.8% | +2.1 [−3.8, +8.1] | −5.2 [−11.2, +1.0] | **0.4%** | 0.40 | 0.18 | 2.58¢ (0.021¢) |
| **D** frontier judge + rubric | 46.2% | −6.5 [−13.3, +0.6] | −13.8 [−21.0, −6.5] | 0.2% | 0.42 | 0.23 | 6.05¢ (3.47¢) |
| **H** hybrid | 53.8% | +1.0 [−4.6, +6.9] | −6.2 [−12.1, −0.2] | 0.6% | 0.51 | 0.24 | 2.36¢ (0.010¢) |
| **G** ceiling | **59.4%** | **+6.7 [+1.9, +11.7]** | −0.6 [−5.8, +4.6] | 0.2% | 0.48 | 0.22 | 2.43¢ (0.012¢) |
| GPT-5, no check | 60.0% | | — | 38.1% | 0.32 | 0.12 | 7.61¢ |

**Violations.** Rule violations per conversation vs Qwen alone are −0.39 [−0.45, −0.33] for every arm.

**Unneeded handoffs** per conversation vs Qwen alone:
- C: +0.02 [−0.04, +0.08];
- D: +0.07 [+0.01, +0.13];
- H: +0.08 [+0.01, +0.14];
- G: +0.06 [−0.00, +0.12].

**Escalations.** Total handoffs rise with G and H: +0.11 and +0.14 per conversation, both intervals above zero. Part of
that is correct: rule R1 sends large duplicate refunds to a human.

What each check blocked. "Breaks a rule" means the action breaks a hidden rule; "valid" means it doesn't, though a
valid action can still break the written policy.

| arm | handoffs blocked: breaks a rule / valid | refunds blocked: breaks a rule / valid | freezes blocked: breaks a rule / valid | rule-breaking actions let through |
|---|---|---|---|---|
| C | 35 / **138** | 116 / 27 | 35 / **73** | 1 |
| D | 35 / **174** | 116 / 59 | 34 / **83** | 0 |
| H | 40 / 38 | 111 / 24 | 37 / **75** | 2 |
| G | 31 / 37 | 120 / 9 | 36 / 8 | 0 |

### What this says

1. **Every check is a safety net.** All four checks stop all but 0–2 of the rule-breaking actions, out of about 650
   checked actions per run. GPT-5 breaks the hidden rules as often as Qwen does (38% of conversations), because it
   wasn't told them either. Qwen + interview rubric + Jev breaks a hidden rule in 0.4% of conversations, at a third
   of GPT-5's cost per conversation.
2. **Resolution needs a precise rubric.** With the rules written out (G), Qwen resolves +6.7 points more than alone
   and is level with GPT-5 (−0.6 [−5.8, +4.6]). With the interview rubric (C), the gain is +2.1, not significant. The
   gap is the rubric's invented rules, which block valid actions: 138 handoffs and 73 freezes, against 37 and 8 for G.
   The rubric check (`expert_deciders_rubric_check.md`) names them: a strict reading of "the customer asked for a
   human", summary wording, and one-cent read-backs.
3. **The frontier judge is worse than Jev with the same rubric.** It is equally safe, but it blocks more valid actions
   (174 handoffs), resolves 6.5 points fewer than Qwen alone, and its check costs 3.5¢ vs 0.02¢ per conversation.
   Brief H2 ("expert rubric + Jev ≥ frontier judge") holds on both quality and cost.
4. **A trained model is an option for text-pattern decisions.** For handoffs, the word-count model trained on 400
   expert labels cuts valid handoffs blocked from 138 to 38. That is as good as the ceiling on this decision, without
   any rubric. It doesn't help refunds and cards, where the decision depends on amounts and dates, which is what Jev
   with a rubric is for. Overall, H isn't better than C because cards stay over-blocked.

## Swap test: agent B (DeepSeek-V4.1-Flash), same checks

Same checks, rubric and thresholds; nothing re-tuned. DeepSeek on the same provider, 480 conversations per run. Conversations
where DeepSeek returned an empty message (5-12 per checked run, none without a check) count as unresolved.

| DeepSeek + check | resolved | vs DeepSeek alone | vs GPT-5 | conversations with a rule violation | handoffs / conv. | unneeded handoffs / conv. | cost / conv. (of which check) |
|---|---|---|---|---|---|---|---|
| none | 59.6% | — | −0.4 [−2.3, +1.2] | 37.7% | 0.34 | 0.13 | 1.38¢ |
| **C** Jev + rubric | **71.7%** | **+12.1 [+6.0, +18.1]** | **+11.7 [+5.6, +17.7]** | **1.0%** | 0.32 | 0.11 | 2.52¢ (0.023¢) |
| **D** frontier judge + rubric | 62.5% | +2.9 [−4.2, +10.0] | +2.5 [−4.6, +9.6] | 0.4% | 0.35 | 0.15 | 6.76¢ (4.03¢) |
| **H** hybrid | 66.9% | +7.3 [+1.5, +13.1] | +6.9 [+1.0, +12.7] | 0.4% | 0.45 | 0.19 | 2.31¢ (0.013¢) |
| **G** ceiling | 71.5% | +11.9 [+6.9, +17.1] | +11.5 [+6.5, +16.5] | 1.0% | 0.42 | 0.17 | 2.34¢ (0.015¢) |
| GPT-5, no check | 60.0% | | — | 38.1% | 0.32 | 0.12 | 7.61¢ |

**Violations.** Rule violations per conversation vs DeepSeek alone are about −0.38 to −0.39 for every arm, with
intervals near [−0.45, −0.32].

**Unneeded handoffs** per conversation:
- C: −0.02 [−0.07, +0.03];
- D: +0.02 [−0.04, +0.08];
- H: +0.07 [+0.00, +0.13];
- G: +0.04 [−0.02, +0.10].

**Total handoffs** per conversation:
- C: −0.02 [−0.08, +0.04];
- G: +0.08 [+0.02, +0.15];
- H: +0.11 [+0.04, +0.18].

| arm | handoffs blocked: breaks a rule / valid | refunds blocked: breaks a rule / valid | freezes blocked: breaks a rule / valid | rule-breaking actions let through |
|---|---|---|---|---|
| C | 54 / **140** | 213 / 29 | 44 / 9 | 3 |
| D | 56 / **168** | 221 / **89** | 41 / 36 | 0 |
| H | 48 / 28 | 198 / 32 | 44 / 11 | 1 |
| G | 57 / 24 | 232 / 0 | 44 / 10 | 0 |

**The swap holds.** The rubric and the handoff model were built only from expert answers on Qwen's conversations (agent B's steps were labelled for testing, never training). With nothing re-tuned, they
carry over. The checked DeepSeek resolves 12 points more than DeepSeek alone and 12 points more than GPT-5, with rule
violations in 1% of conversations against GPT-5's 38%.

**Here the interview rubric matches the ceiling** (C 71.7% vs G 71.5%). DeepSeek follows the confirmation steps more
carefully than Qwen, so the rubric's invented card rules (exact read-backs, explicit consent) rarely fire on valid
freezes: 9 blocked, against 73 on Qwen. Handoffs are still over-blocked (140 vs 24), but DeepSeek recovers after a
blocked handoff, so it doesn't cost resolution. How much an imperfect rubric costs depends on the agent behind it.

**The frontier judge is again the weakest check** (+2.9, not significant). It blocks the most valid refunds (89) and
handoffs (168), and costs 4.0¢ per conversation, more than DeepSeek itself.

**The hybrid is worse than C on DeepSeek** (+7.3 vs +12.1), even though it blocks far fewer valid handoffs. More
handoffs get through (+0.11 per conversation), some of them unneeded. On this agent, blocking a doubtful handoff
seems to steer DeepSeek to the right action more often than letting it through.

**Cost.** The checks themselves are cheap: Jev is 0.01-0.02¢ per conversation. But a blocked action makes the agent
think again. On DeepSeek those extra, discarded calls carry long reasoning, so a checked conversation costs 2.3-2.5¢
against 1.38¢ unchecked (+70-80%); on Qwen it is +1-10%. Every checked arm is still a third of GPT-5's cost or
less, except the judge. Cost per conversation counts every agent call, including discarded ones (`SWAPBENCH_CALL_LOG`).

## Caveats

- **The experts are simulated.** They know the hidden rules exactly; real experts would be noisier and less complete.
  The 10% flips are the only noise.
- **One domain.** Our bank set; five hidden rules, chosen to be checkable from the conversation.
- **Small positives.** Fewer than 150 rule-breaking handoff and card steps in the labelled set.
- **Judge and Jev costs are estimates** from offline token means. The check is a small share of cost anyway, except
  for the judge.
- **Swap-test provider.** Agent B's labelled steps came from four providers, while the live runs used one
  provider.
- **The first DeepSeek runs were invalid.** They were on another provider and lost 85–95% of
  conversations to our account's limits there, so they were set aside. The swap test was re-run in full on the first provider.
- **Excluded or counted conversations.** Conversations where the agent
  returned an empty message count as unresolved, not dropped.
