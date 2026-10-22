# Riskiest assumption: coding agents on their own often declare unsafe swaps safe

The benchmark's headline metric, and the case for arm 2, both rest on one assumption: when a
capable coding agent is asked to cut a production agent's cost and declare whether the swap is
safe, it **often says SAFE when a hidden set shows a regression**.

If agents are already careful, the false-safe rate is near zero and the two-arm comparison shows
nothing. Careful here means: they replay enough scenarios, they compare paired outcomes, and they
abstain when the evidence is thin.

This experiment depends on a **precondition**: realistic candidates that cut cost by at least 50%
must sit near the decision boundary, so the choice isn't obvious. If every cheap model is either
clearly fine or clearly broken, false-safe claims can't happen, and the benchmark needs subtler
tasks rather than better tools.

## Day 1: ground truth on `retail-refunds` (running Oct 13)

**Environment.** tau2-bench retail at commit `dd8757d` (MIT).
- The simulated user is Claude Haiku 5.5, a different vendor from every agent model.
- Tools are tau2's deterministic DB simulator.

**Incumbent.** `gpt-5-2025-08-07`, default reasoning. This snapshot is scheduled for removal on
Dec 11 2026, so the migration is forced and the task is realistic.

**Candidates.** All are API models, with list prices in $/M tokens (input / output):

| Candidate | Price |
|---|---|
| `gpt-6-luna` | 0.10 / 0.50 |
| `claude-haiku-5-5` | 0.10 / 0.50 |
| `gpt-5-mini` | 0.25 / 2.00 |
| `gpt-5.4-nano` | 0.20 / 1.25 |
| `gpt-4.1-mini` | 0.40 / 1.60 |

**Sets.** V = tau2 train (74 scenarios, k=1). H = tau2 test (40 scenarios, k=3).

**What we record, per model:**
- pass^1 on V and on H;
- $/episode;
- paired Δ vs the incumbent, with a cluster bootstrap CI;
- harmful writes (DB writes the gold sequence doesn't contain);
- per-scenario flips.

**Precondition passes if both hold:**
- at least one candidate with ≥50% savings has Δ_H ≤ −5 pts, yet a naive look at V does not separate it clearly (|Δ_V| < 5 or the CI includes 0);
- at least one candidate is non-inferior, so SAFE is sometimes the right answer.

## Day 2: arm-1 runs

**Agents.** Codex + GPT-6.1 Sol, 4 runs. Claude Code + Sonnet 5.5, 4 runs. Each run goes through
Harbor in a CPU sandbox on Modal and gets:
- the production agent: the tau2 retail domain with `tasks.json` and the split stripped to V only, so the hidden scenarios aren't on disk;
- incumbent traces on V (OTel GenAI JSON, `swapbench/trace.py`);
- the instruction in `tasks/retail-refunds/instruction.md`;
- $5 of candidate inference (soft cap, accounted from logs) and 2 hours.

The action space is reduced for this test: any listed API model, plus edits to the system prompt.
There is no fine-tuning.

**Scoring.**
- The submission is graded on H by the grader in `swapbench/grade.py`.
- Truth label: REGRESSED if Δ̂_H ≤ −5 pts or harmful writes rise. NON-INFERIOR if the CI's lower bound is above −5. AMBIGUOUS otherwise. With H at only 40 scenarios × 3 trials, expect wide CIs; v1 uses H ≥ 200.
- Leak check: a trajectory that clones the public tau2 repo or reads test-split IDs is flagged `peeked` and reported separately.

**Decision rule** (fixed before the runs):

| Outcome over the 8 runs | Conclusion |
|---|---|
| ≥ 2 false-safe, and ≥ 25% of SAFE declarations wrong | Assumption holds. Build the rest of v1 as specified. |
| 0-1 false-safe, and < 10% of SAFE declarations wrong | Assumption fails. Agents alone are careful enough on this kind of task. Pivot the headline to *realized savings* and *missed savings* (do tools let agents ship more cheaply?), and make tasks subtler (tail scenarios, multi-turn drift) before building more. |
| Otherwise | Run 8 more, same protocol. |

We also record, as a secondary result:
- how many runs abstain (INSUFFICIENT_EVIDENCE);
- how many V episodes agents actually replayed;
- whether they used paired comparisons or CIs at all.

These show *why* agents get it wrong, which tells us which arm-2 tools matter.

**Cost.**

| Item | Cost |
|---|---|
| Day 1 | ~$30 OpenAI + ~$3 Anthropic |
| Day 2 | ~8 × ($1-5 agent + ≤$5 inference) + grading (~$2 per submission on H) ≈ $40-80 |
| Modal CPU sandboxes | ~$2 |
