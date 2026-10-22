# Expert deciders (built on SwapBench)

## Question

Can a few hundred expert answers, turned into a rubric and checked by Jev on each risky action, beat a frontier judge at keeping a cheap agent to a bank's unwritten rules?

## Status

**Complete.** Labels, offline arms and live runs: 2026-10-15 to 2026-10-16. **Spend: $234.64** at list prices (offline $36.01 + live $198.63, from [`docs/expert_deciders_costs.md`](docs/expert_deciders_costs.md); it includes estimated lines for the rubric calls, embeddings and the Jev/judge checks, and the dropped and set-aside runs).

## What it is

The bank is SwapBench's fintech domain ("Northbank", see [`../swapbench`](../swapbench)). It gets five **hidden working rules** that the agent's written policy does not mention (`swapbench/hidden_rules.py` in the SwapBench directory):

| id | decision | rule |
|---|---|---|
| H1 | handoff | Credit-limit increase requests are never handed to a human; send the customer to the mobile app. |
| H2 | handoff | After two failed identity checks, no handoff; send the customer to a branch with photo ID. |
| R1 | refund | Duplicate-charge refunds over $300 go to a human (`refund_over_limit`); the written limit is $500. |
| R2 | refund | Fee refunds only for fees from the last 30 days (on or after 2026-09-01). |
| C1 | card | No card freeze for an unauthorized charge under $150; dispute only. |

The gold end states of the 240 hidden bank scenarios are adjusted for these rules (88 change), so no agent can resolve those 88 without knowing the rules; resolution here is about 50-70%, not SwapBench's ~94%.

- **Experts:** two simulated experts (Claude Haiku 5.5, GPT-5 mini) who know the policy and the hidden rules answer "should this action go ahead?" with one sentence of why, for decision steps (handoff, refund, card freeze) taken from earlier recorded agent conversations; 10% of answers are flipped at random to mimic disagreement.
- **Checks (arms)** sit in front of the three risky actions and block an action when p(should not happen) > 0.5 (the agent is told and tries again, at most twice per turn):
  - **none:** the cheap agent alone;
  - **C:** Jev (TypeSafe's "System One" decision model) + an *interview rubric* that GPT-6.1 Sol wrote from about 400 expert answers per decision ([`data/rubric.json`](data/rubric.json));
  - **D:** GPT-6.1 Sol as judge + the same rubric + 10 labelled examples;
  - **H:** hybrid: a TF-IDF + logistic model trained on 400 expert labels for handoffs, C for refunds and cards;
  - **G (ceiling):** Jev + the hidden rules written out;
  - **GPT-5, no check:** the reference incumbent.
- **Agents:** A = Qwen3.8-27B; swap test B = DeepSeek-V4.1-Flash with the same checks, nothing re-tuned. Both ran on one commercial inference provider, which is not named (the results are about the checks, not the provider). Customer: Claude Haiku 5.5.
- **Runs:** each arm = the 240 hidden bank scenarios × 2 trials = 480 conversations, graded by tau2's end-state comparison against the hidden-rule gold.

## Results

From [`results/expert-deciders.json`](results/expert-deciders.json), regenerated from [`results/runs/`](results/runs) on 2026-10-22. Resolved = correct / n (no conversation was excluded; empty agent messages count as unresolved), with a 95% cluster-bootstrap CI over scenarios. Δ in points, paired by scenario. Cost per conversation = agent calls (call log, including discarded drafts, for checked arms; trajectory for unchecked runs) + the estimated check cost (in brackets).

### Agent A: Qwen3.8-27B

| check | n (resolved) | resolved [95% CI] | Δ vs Qwen alone [95% CI] | Δ vs GPT-5 [95% CI] | conversations with a rule violation | handoffs / unneeded handoffs per conv. | blocked: rule-breaking / valid; let through | ¢ per conv. (check) |
|---|---|---|---|---|---|---|---|---|
| none | 480 (253) | 52.71 [46.67, 58.54] | | −7.29 [−10.83, −3.96] | 179 (37.29%) | 0.3688 / 0.1625 | | 2.3380 |
| C Jev + rubric | 480 (263) | 54.79 [48.96, 60.42] | +2.08 [−3.75, +8.13] | −5.21 [−11.25, +1.04] | 2 (0.42%) | 0.4042 / 0.1833 | 186 / 238; 1 | 2.5794 (0.0209) |
| D frontier judge + rubric | 480 (222) | 46.25 [40.62, 52.08] | −6.46 [−13.33, +0.63] | −13.75 [−21.04, −6.46] | 1 (0.21%) | 0.4146 / 0.2313 | 185 / 316; 0 | 6.0458 (3.4714) |
| H hybrid | 480 (258) | 53.75 [47.71, 59.79] | +1.04 [−4.58, +6.88] | −6.25 [−12.08, −0.21] | 3 (0.63%) | 0.5083 / 0.2375 | 188 / 137; 2 | 2.3590 (0.0099) |
| G ceiling | 480 (285) | 59.38 [53.54, 65.00] | +6.67 [+1.87, +11.67] | −0.63 [−5.83, +4.58] | 1 (0.21%) | 0.4771 / 0.2188 | 187 / 54; 0 | 2.4277 (0.0121) |
| GPT-5, no check | 480 (288) | 60.00 [53.96, 65.83] | | | 183 (38.12%) | 0.3208 / 0.1187 | | 7.6121 |

### Agent B (swap test): DeepSeek-V4.1-Flash, same checks

| check | n (resolved) | resolved [95% CI] | Δ vs DeepSeek alone [95% CI] | Δ vs GPT-5 [95% CI] | conversations with a rule violation | handoffs / unneeded handoffs per conv. | blocked: rule-breaking / valid; let through | ¢ per conv. (check) | empty messages |
|---|---|---|---|---|---|---|---|---|---|
| none | 480 (286) | 59.58 [53.54, 65.62] | | −0.42 [−2.29, +1.25] | 181 (37.71%) | 0.3375 / 0.1271 | | 1.3779 | 0 |
| C Jev + rubric | 480 (344) | 71.67 [66.25, 76.88] | +12.08 [+6.04, +18.12] | +11.67 [+5.63, +17.71] | 5 (1.04%) | 0.3187 / 0.1083 | 311 / 178; 3 | 2.5176 (0.0233) | 9 |
| D frontier judge + rubric | 480 (300) | 62.50 [56.87, 67.92] | +2.92 [−4.17, +10.00] | +2.50 [−4.58, +9.58] | 2 (0.42%) | 0.3542 / 0.1479 | 318 / 293; 0 | 6.7632 (4.0290) | 11 |
| H hybrid | 480 (321) | 66.87 [61.25, 72.29] | +7.29 [+1.46, +13.13] | +6.88 [+1.04, +12.71] | 2 (0.42%) | 0.4458 / 0.1938 | 290 / 71; 1 | 2.3107 (0.0126) | 5 |
| G ceiling | 480 (343) | 71.46 [66.25, 76.67] | +11.87 [+6.88, +17.08] | +11.46 [+6.46, +16.46] | 5 (1.04%) | 0.4208 / 0.1667 | 333 / 34; 0 | 2.3439 (0.0145) | 12 |

Rule violations per conversation fall by 0.381-0.390 against the same agent alone for every check (paired CIs about [−0.456, −0.319]; `results.*[].rule_violations_per_conversation_delta_vs_agent_alone`).

### Offline: each check on 1,500 held-out labelled decision steps (F1 on "should not go ahead", against the hidden-rule truth)

| check | Qwen steps: handoff / refund / card | DeepSeek steps: handoff / refund / card |
|---|---|---|
| B Jev, written policy only | 0.06 / 0.05 / 0.00 | 0.00 / 0.00 / 0.00 |
| C Jev + rubric | 0.64 / 0.92 / 0.78 | 0.77 / 0.93 / 0.89 |
| D frontier judge + rubric | 0.57 / 0.82 / 0.75 | 0.63 / 0.84 / 0.80 |
| T-400 TF-IDF on 400 labels | 0.91 / 0.68 / 0.65 | 0.95 / 0.70 / 0.72 |
| G Jev + hidden rules | 0.91 / 1.00 / 0.89 | 0.94 / 1.00 / 0.92 |

n per cell 226-275 steps (62-172 positives); every arm, calibration, selective accuracy and the learning curves are in [`docs/expert_deciders_offline.md`](docs/expert_deciders_offline.md). Expert agreement: Cohen's kappa 0.54 / 0.47 / 0.68 (handoff / refund / card), below the planned 0.7 gate by construction (the 10% flips).

**In short:** every check removes almost all hidden-rule breaking (from about 37% of conversations to at most 1.04%). Only a precise rulebook also raises resolution: on Qwen the ceiling G gains +6.67 points while the interview rubric C gains +2.08 (CI includes 0), because C blocks 238 valid actions against G's 54. On the swap test, DeepSeek + Jev + rubric resolves 12.08 points more than DeepSeek alone and 11.67 more than GPT-5, at a third of GPT-5's cost per conversation. The frontier judge is as safe but resolves less on both agents, and its check costs 166-173 times Jev's per conversation (with Jev's price an assumption, see Limitations).

## Trust status

**Reproduced from committed rows on 2026-10-22** (fresh uv environment, see [`RERUN.md`](RERUN.md)):

- `scripts/ed_compute_rows.py` + `scripts/build_export.py` rebuild [`results/expert-deciders.json`](results/expert-deciders.json) exactly from [`results/runs/`](results/runs): resolved counts, CIs, paired deltas, handoffs, blocked counts, costs.
- The rule-violation counts and paired violation deltas, which the original export copied from the write-up instead of computing, now come from the rows and agree with every copied value.
- `../swapbench/scripts/ed_eval.py` regenerates [`docs/expert_deciders_offline.md`](docs/expert_deciders_offline.md) byte for byte from the stripped offline rows (`results/runs/offline/`).
- The public rows themselves were extracted from the raw runs by `scripts/extract_rows.py` and `scripts/strip_offline.py` (committed; they need the private archive to run).

**Not reproduced here:** no conversation, expert label or check was re-run (all paid). The total spend ($234.64) and the per-item costs in `docs/expert_deciders_costs.md` need the raw logs (private). The rubric-vs-hidden-rules comparison ([`docs/expert_deciders_rubric_check.md`](docs/expert_deciders_rubric_check.md)) was done by an agent and not re-checked.

**Known inconsistencies:**

1. The write-up's arm table says arm D gets "6 labelled examples"; the code (`ed_online_prep.py`: up to 5 "should not" and 5 "go ahead" per decision) and the export say 10.
2. The write-up says every check brings violations "to under 1%"; DeepSeek + C and DeepSeek + G are at 1.04% (5 of 480). The original summary table's "≤1%" has the same issue.
3. The judge-vs-Jev check cost ratio is quoted as "about 1/170th"; the rows give 166× (Qwen) and 173× (DeepSeek).
4. The study notes say agent B ran on the same provider as agent A; the first agent-B runs were on another provider and were set aside (lost to our account's limits); only the re-runs on the first provider are in the tables (they are in the spend).

**Steps that would vet it further:**

1. Re-run arms none, C and G for agent A twice more (about $12.50 per run including the simulator, from `docs/expert_deciders_costs.md`) to get a run-to-run noise floor; there are no repeats now.
2. Hand-check 30 of the 238 valid actions arm C blocked on Qwen against the rubric, to confirm that the over-blocking comes from the rubric's invented rules.
3. Replace the simulated experts with 2-3 real support leads on 100 steps and compare their kappa and the resulting rubric.
4. Price Jev from an actual invoice and log the resolved model version (it was `jev-latest`, unlogged).
5. Run the hidden-rule grading on a second, independently written set of rules to see whether the rubric approach transfers.

## Harbor status

**Portable**, the same way as SwapBench (see [`../swapbench/README.md`](../swapbench/README.md), Harbor status): each bank scenario becomes a task whose environment serves the Northbank tools and the simulated customer through an MCP server, and whose hidden tests compare the tool end state with the hidden-rule gold and count hidden-rule violations among executed actions. The checks are not agents but a gate inside the agent loop (`decider_gate` in `swapbench/hybrid_agent.py`), so in Harbor they would be a custom agent (`import_path: ...:DeciderGateAgent`, with the arm, rubric and model files declared in its options model) or an MCP proxy in front of the write tools; arms then differ only in their setup file. Harbor's hosted `sierra-research/tau3-bench` serves τ tools and the user simulator over MCP in that shape, but this study runs on tau2 (`dd8757d`) with our own bank, so it would need its own domain module. Nop check: 88 of 240 hidden scenarios change under the hidden rules, and in many scenarios the correct end state is "nothing written", so per-task "nop scores 0" does not hold without a second graded fact. The live data (hidden v1 set with the adjusted gold) must stay private.

## Limitations

- The experts are simulated and know the hidden rules exactly; the only noise is 10% random flips. Real experts would be noisier and less complete.
- One synthetic bank, five rules chosen to be checkable from the conversation; small positive sets (fewer than 150 rule-breaking handoff and card steps in the labelled set).
- Check costs are estimates: Jev and judge tokens per decision come from offline means; Jev's price ($0.042 per 1M input tokens) is an internal assumption with no published source, not TypeSafe's list price; the Jev model version was not logged.
- Single run per arm; no noise floor.
- Empty agent messages (DeepSeek, 5-12 per checked run, none unchecked) count as unresolved, which penalizes checked arms.
- Agent B's labelled steps came from four inference providers while its live runs used one.
- Arms E (small model on 25-400 labels) and F (outcome labels) were dropped from the live test after the offline results; arm B (Jev with the written policy only) was dropped early.
- Resolution is against a gold that GPT-5 cannot meet without the rules, so absolute rates are not comparable with SwapBench's main tables.
- **What is left out of this repository:** the hidden v1 bank set and its hidden-rule-adjusted copy (needed for live runs and for recomputing violations from transcripts), conversation transcripts and raw run folders, the decision-step texts and the experts' one-sentence explanations (they quote hidden-set conversations), the judge's 10 examples and the two trained models (`online_E200.pkl`, `online_T400_handoff.pkl`; built from those texts). All are in the private archive. Public rows keep ids, outcomes, counts, labels and scores only.

## Provenance

- Original location: the private research repo, `swapbench/` at commit `6e908568fdb7a8790574d5fe9563aca15d80479d` (2026-10-16): `swapbench/experiments/expert_deciders*.md`, `swapbench/scripts/ed_*.py`, `swapbench/swapbench/hidden_rules.py`, `swapbench/swapbench/hybrid_agent.py`. The export was built by that repo's `benchmarks-export/scripts/ed_compute.py` and `build_ed.py` (ported here as `scripts/ed_compute_rows.py` and `scripts/build_export.py`).
- Run by Hamza Tahir (ZenML) with Claude Code agents. Kitaru was not used.
- **Code dependency:** all runtime code lives in [`../swapbench`](../swapbench) (the `ed_*.py` pipeline scripts, `swapbench/hidden_rules.py`, the `decider_gate` agent, `scripts/tau2x`); this directory holds the write-ups, results, rubric and the scripts that rebuild the tables.
- Access to the hidden set or transcripts: ask the maintainers of this repository; they are shared privately for review.
- Licence: Apache-2.0 (repository root `LICENSE`). The bank data is fully synthetic.
