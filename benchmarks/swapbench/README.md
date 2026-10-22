# SwapBench

## Question

Is it safe to swap the model behind a production customer-service agent, and which checks can tell before customers find out?

## Status

**Complete** for the published scope (Parts A-D of the original study). Runs: 2026-10-13 to 2026-10-15. A "methods v2" re-run (exact intervals, about 35 candidates, a truth from an independent simulator) was planned and not run.

**Spend.** There is no single costs file. What is exact and recomputable: the agent-side token cost recorded in every published result row, **$89.2142 over 11,946 conversations** (list prices pinned in `swapbench/pricing.py`; self-hosted rows count $0). The withheld hosted-provider runs (22 runs, 15,707 conversations) cost a further $323.71 in agent tokens at the providers' list prices, $412.92 in all. Not in that figure and only known approximately from the original notes: the Claude Haiku 5.5 customer simulator (about $0.47 per 480 conversations), Modal GPU time for the self-hosted Qwen configs (one H100 at $3.95/h; about $15 by Oct 13, later runs not tallied), next-step replay calls, the coding-agent arms, the simulator experiments, the inferred-mock live runs and the LoRA training. The expert-deciders study built on this code is separate ([`../expert-deciders`](../expert-deciders), $234.64).

## What it is

A *swap check* is anything that says SAFE, UNSAFE or NOT ENOUGH EVIDENCE about replacing an incumbent model (a verifier, a vendor tool, a coding agent). SwapBench grades those verdicts against ground truth: every candidate and the incumbent run full conversations on hidden, production-like scenarios, and the candidate's success and harm are compared with the incumbent's on the same scenarios. The headline metric is the **false-safe rate**: how often "safe to switch" is wrong.

- **Two support-agent domains on [tau2-bench](https://github.com/sierra-research/tau2-bench)** (pinned at commit `dd8757d`): *fintech*, a fictional bank "Northbank" with 7 tools and a written policy (`swapbench/fintech/`), and *retail*, tau2's store with generated multi-request customer requests (`swapbench/gen_retail.py`).
- **Ground truth by construction.** Each scenario plants a situation in the data and records the exact tool calls a correct agent makes; a conversation passes when the tools' end state equals the gold end state (tau2 `reward_basis: ["DB"]`). A *harmful action* is a successful write that matches no gold write. No LLM judge.
- **Splits per domain:** 60 visible, 200 pool, 240 hidden scenarios. Truth = hidden set, 2 trials per scenario (480 conversations). The simulated customer is Claude Haiku 5.5 in every row.
- **Checks graded:** next-step agreement with the incumbent's recorded steps (5-point threshold), full replay on the 60 visible scenarios (replay-60) and on visible + pool (replay-260), each with a paired 95% CI gate and a 5-point non-inferiority margin.
- **Truth label:** REGRESSED if the success delta is at most −5 points or the harm delta's lower bound is above 0.01 per conversation; NON-INFERIOR if the delta's lower bound is above −5 points and harm doesn't rise; otherwise AMBIGUOUS (not scored).

## Results

All numbers are copied from [`results/swapbench.json`](results/swapbench.json) and were regenerated from [`results/runs/`](results/runs) on 2026-10-22 (see Trust status). n = conversations; success is the mean over scenarios of the per-scenario success (trials averaged first), with a 95% cluster-bootstrap CI over scenarios (10,000 resamples, seed 0). Δ = candidate minus incumbent, paired by scenario, in points. Cost per resolved conversation is the agent's token cost only (no simulator, no GPU); "—" = self-hosted.

### Fintech (bank), hidden set, incumbent GPT-5

| run | n (correct) | success [95% CI] | Δ vs GPT-5, pts [95% CI] | harmful actions / conv. | truth | ¢ per resolved |
|---|---|---|---|---|---|---|
| GPT-5 (incumbent) | 480 (452) | 94.17 [91.67, 96.46] | | 0.0312 | | 7.6937 |
| GPT-5 mini | 480 (453) | 94.37 [92.08, 96.25] | +0.21 [−2.50, +2.92] | 0.0479 | NON-INFERIOR | 1.3779 |
| GPT-6 Luna | 480 (440) | 91.67 [88.96, 94.17] | −2.50 [−5.42, +0.42] | 0.0729 | REGRESSED (harm) | 0.1077 |
| GPT-5.4 nano | 480 (272) | 56.67 [51.46, 61.88] | −37.50 [−42.92, −32.08] | 0.4542 | REGRESSED | 0.8030 |
| Qwen3.8-27B BF16 (self-hosted vLLM) | 480 (425) | 88.54 [85.00, 91.87] | −5.63 [−8.75, −2.50] | 0.0958 | REGRESSED | — |
| Qwen3.8-27B FP8 | 445 (395) | 88.12 [84.58, 91.46] | −6.04 [−9.38, −2.92] | 0.0979 | REGRESSED | — |
| Qwen3.6-35B-A3B MoE | 481 (433) | 90.00 [86.67, 92.92] | −4.17 [−7.92, −0.42] | 0.0604 | AMBIGUOUS | — |
| Qwen3.8-27B + LoRA RFT | 480 (431) | 89.79 [86.67, 92.71] | −4.37 [−7.29, −1.67] | 0.0917 | REGRESSED | — |
| Qwen3.8-27B + tool guardrails | 480 (426) | 88.75 [85.21, 91.87] | −5.42 [−8.75, −2.29] | 0.0979 | REGRESSED | — |
| Qwen3.8-27B + guardrails + 3-line policy fix | 480 (446) | 92.92 [90.21, 95.42] | −1.25 [−3.96, +1.46] | 0.0458 | NON-INFERIOR | — |

### Retail (store), hidden set, incumbent Claude Haiku 5.5

| run | n (correct) | success [95% CI] | Δ vs Haiku, pts [95% CI] | harmful actions / conv. | truth | ¢ per resolved |
|---|---|---|---|---|---|---|
| Claude Haiku 5.5 (incumbent) | 480 (458) | 95.42 [93.33, 97.29] | | 0.0125 | | 1.8804 |
| Claude Haiku 5.5 re-run (noise floor) | 240 (224) | 93.33 [90.00, 96.25] | −2.08 [−5.42, +1.25] | 0.0208 | AMBIGUOUS | 1.9067 |
| Qwen3.6-35B-A3B MoE | 480 (455) | 94.79 [92.08, 97.08] | −0.63 [−3.33, +2.08] | 0.0042 | NON-INFERIOR | — |
| Qwen3.8-27B BF16 | 480 (419) | 87.29 [83.75, 90.62] | −8.13 [−12.08, −4.37] | 0.0271 | REGRESSED | — |
| Qwen3.8-27B FP8 | 480 (411) | 85.62 [81.87, 88.96] | −9.79 [−13.75, −6.04] | 0.0187 | REGRESSED | — |
| Qwen3.8-27B, thinking off | 480 (446) | 92.92 [90.42, 95.21] | −2.50 [−5.42, +0.21] | 0.0104 | AMBIGUOUS | — |
| Qwen3.8-27B, generic hermes tool parser | 240 (1) | 0.42 [0.00, 1.25] | −95.00 [−97.08, −92.71] | 0.0000 | REGRESSED | — |

### How the checks did (13 scored candidate swaps: 8 regressed, 2 non-inferior, 3 ambiguous)

| check | correct | false safe | false unsafe | not enough evidence | decidable |
|---|---|---|---|---|---|
| next-step agreement (5-pt threshold) | 3 | **5 of 8 regressed** | 2 of 2 non-inferior | 0 | 10 |
| replay-60 | 4 | 0 | 0 | 6 | 10 |
| replay-260 | 5 | **0** | 0 | 5 | 10 |

No next-step threshold avoids both errors: at 0-1 points it rejects both safe swaps, and from 2 points up it approves at least one regression (`results.next_step_threshold_sweep`). Per-candidate verdicts: `replays_and_step_checks` in the JSON and [`experiments/headline.md`](experiments/headline.md).

### Same open model on several inference providers: withheld

The original study also ran DeepSeek-V4.1-Flash, gpt-oss-120b, Qwen3.8-2.4T-A95B and Qwen3.8-27B on four commercial inference providers, and tried checks (Jev gate, decomposition, an outcome-trained check) on hosted models. **Those per-provider results are withheld pending review by the providers**; they are not in the rows, the export or the docs. The harness is here so you can run your own providers: `scripts/provider_runs.sh` (neutral labels, endpoints from `OPENAI_COMPAT_BASE_URL_<LABEL>` / `OPENAI_COMPAT_API_KEY_<LABEL>`) and `scripts/providers.py` (paired comparison per provider, same gate as above).

### Other experiments (documented, rows not in this repository)

Simulator swaps, inferred mocks and the retail-refunds open models are copied from the write-ups into `results.documented_only_not_recomputed`; see [`docs/WRITEUP.md`](docs/WRITEUP.md) and [`experiments/`](experiments). The coding-agent arm (Codex with GPT-6.1 Sol and Claude Code with Sonnet 5.5, 13 graded Harbor runs) made 0 SAFE declarations on a regressed swap (`results.coding_agent_arm1`, rows in [`experiments/graded.jsonl`](experiments/graded.jsonl) and [`experiments/graded_retail_composite.jsonl`](experiments/graded_retail_composite.jsonl)).

## Trust status

**Reproduced from committed rows on 2026-10-22, in a fresh uv environment matching the original one (Python 3.12.3, litellm 1.82.6, tau2 `dd8757d`):**

- `scripts/headline.py` regenerates [`experiments/headline.md`](experiments/headline.md) identically (only the "generated from" path in the title changed).
- `scripts/charts.py` regenerates the four SVG charts in [`docs/img`](docs/img) byte for byte.
- `scripts/export/sb_compute.py` + `build_export.py` rebuild [`results/swapbench.json`](results/swapbench.json) exactly, including the $89.2142 recorded agent cost of the published rows. Every number that is also in the original private export is unchanged; only the withheld provider results were removed.
- Both public scenario sets regenerate byte for byte from the generators with seed 31415, and the gold tool calls of all 500 public fintech scenarios execute cleanly (`tests/test_offline.py`).

**Not reproduced here:**

- No conversation was re-run (they cost money). Every number rests on one set of runs; besides the incumbent re-run on retail (−2.08 points, the only noise-floor measurement) there are no repeats.
- The hidden v1 scenario sets behind every number are not in this repository (see Limitations), so a reader can check the statistics but not the conversations or the grading.
- The documented-only results (simulator swaps, inferred mocks, retail-refunds pilot) have no rows here.
- The ground truth was never compared with real customers or a human grader; scenario validity was checked by a separate Claude agent on 50 hidden scenarios (39 pass, 7 minor, 4 fail, all four the retail "cancel a delivered order" kind).

**Known inconsistencies between earlier write-ups and the data:**

1. At the original commit, `results/manifest.json` listed only the hosted-provider runs (the provider export overwrote it), so `scripts/headline.py` at that commit produces a different table than the committed `headline.md`. The manifest from the Oct 14 commit (`a66820c`) reproduces it; it is `results/runs/manifest.json` here.
2. The original README says "results for 12 candidate swaps"; the verdict tally scores 13 (10 decidable).
3. The original export added a `ci95_note` to the pool-confirmation rows by hand; `build_export.py` now writes it.

**Steps that would vet it further:**

1. Rerun the smoke subset (20 public fintech scenarios) on GPT-5 and GPT-5 mini twice each and compare the run-to-run spread with the 5-point margin (about $4).
2. Re-run the incumbents (GPT-5 on fintech, Haiku on retail) on the hidden v1 set to measure the noise floor on both domains (about $45 with the simulator).
3. Hand-grade 30 conversations where the end-state grade and a reading of the transcript might disagree (harmful-action and "cancel a delivered order" cases), from the private archive.
4. Swap the simulated customer for a different model (GPT-6.1 Sol was tried on fintech only) on the retail hidden set for the three REGRESSED Qwen configs, to see whether truth labels hold.
5. Run the planned exact-interval re-analysis (e.g. Clopper-Pearson on the 8 regressed candidates: 0 of 8 vs 5 of 8 false safes) so error rates come with their uncertainty.

## Harbor status

**Portable**, with one part already Harbor-native.

- **Already native:** the coding-agent arms. `scripts/build_harbor_task.py` turns `tasks/retail-refunds` and `tasks/retail-composite` into Harbor task folders (`instruction.md`, `task.toml`, `environment/Dockerfile`, `solution/solve.sh`, `tests/test.sh`), and `scripts/run_arm.sh` ran Codex and Claude Code on them with `harbor run -e modal`. The built folders contain the incumbent's visible traces (from the private archive), so they are not committed; the grader (`swapbench/grade.py`) re-runs the submitted configuration on the hidden scenarios outside the sandbox, which is the part that does not yet follow the task format.
- **What porting the main benchmark would take** (in the terms of the Harbor-native target in [`STANDARD.md`](../../STANDARD.md) and [zenml-bench](https://github.com/zenml-io/zenml-bench)): one task per scenario (or per scenario family) whose `environment/` serves the bank or store tools and the simulated customer as an MCP server next to the agent, and whose hidden `tests/` compare the recorded tool end state with the gold end state and count harmful writes. Harbor already hosts `sierra-research/tau3-bench` (airline, retail, telecom, banking) in exactly that shape, so the retail scenarios could be fed to that adapter as a new task set, and Northbank would need its own domain module behind the same MCP server. SwapBench is pinned to tau2 (`dd8757d`), not tau3: the tool, user-simulator and grading code would have to be re-checked against tau3 before numbers are compared, and Northbank is our own bank, not tau3's banking domain.
- **The four checks:** the oracle is the gold action list (all 500 public fintech scenarios execute cleanly, `tests/test_offline.py`). The "nop scores 0" check fails as things stand: in 88 of 500 public fintech and 88 of 500 public retail scenarios the correct end state equals the initial one (an ineligible request), so doing nothing passes. Those scenarios need a second fact to grade (the customer was told, no handoff), or must be scored only as a set against a nop baseline. Shortcuts to list: writing the gold state directly through a non-agent path, and handing everything to a human.
- **Setups as config:** a model swap is a change of `-m` (and an MCP-server config for the simulator), so incumbent and candidates differ only in the setup file. The swap *verdict* (the thing SwapBench grades) is a job-level comparison, so it needs a results script over two Harbor jobs (paired by scenario, the CI gate in `swapbench/stats.py`), not a per-task reward.
- **Hidden sets:** the leaderboard sets (v2) must stay out of a public `registry.json`; they would run from a private dataset with only the hashes public.

## Limitations

- Simulated customers only (Claude Haiku 5.5). A stronger simulator moved fintech success up 2-5 points but barely moved candidate-vs-incumbent gaps; a weaker one shifted a retail verdict by 17.5 points. No comparison with real customers.
- Ground truth by construction assumes a faithful customer; a simulator that breaks its script corrupts the truth itself.
- One retail scenario kind (cancel an already-delivered order; 50 of 240 hidden retail scenarios) penalizes helpful agents; it was kept so published numbers stay comparable. Removing it changes no truth label.
- Small scale: two domains, one incumbent per domain, 13 scored swaps (10 decidable). Error rates of the checks have wide uncertainty.
- Truth is estimated from 240 scenarios × 2; three candidates are AMBIGUOUS and unscored. The replay checks and the truth share simulator, harness and grader.
- The **hidden v1 sets** behind every number are not public: the seeds sit in the private research repo's history, and the current generators with their documented defaults do not reproduce them. Reviewers can request them (see Provenance). The **leaderboard sets (v2)** come from secret seeds and are kept privately; only their SHA-256 hashes are in [`data/README.md`](data/README.md). Rotate them per leaderboard release.
- Costs use list prices pinned on 2026-10-13/15, not invoices; the simulator, GPU time and check costs are not in the per-row cost.
- Self-hosted FP8 and MoE fintech runs combine one full trial with a partial second trial (445 and 481 conversations).
- Inferred mocks were tested on two simple CRUD domains against hand-written tools that are themselves mocks.
- What is left out of this repository: conversation transcripts and raw tau2 run folders (private archive), the hidden v1 and v2 sets, the 21 conversation pages of the sample Swap Report (`reports/fintech/index.html` links to them; they show hidden-set conversations), the built Harbor arm tasks, all per-provider results (rows, tables, notes, endpoint details) and the experiments on hosted models (Jev gate, decomposition, outcome-trained check), which are withheld pending provider review, and the v2 methods plan (an unrun plan with budget figures).

## Provenance

- Original location: the private research repo, directory `swapbench/`, commit `6e908568fdb7a8790574d5fe9563aca15d80479d` (2026-10-16). The export this README copies was built by that repo's `benchmarks-export/scripts/sb_compute.py` and `build_swapbench.py` (ported here as `scripts/export/`).
- Run by Hamza Tahir (ZenML) with Claude Code agents, 2026-10-13 to 2026-10-15. Kitaru was not used.
- Changes made for this repository are listed in [`RERUN.md`](RERUN.md) ("Changes from the original run"). Earlier documents (original spec, prior-art review, first experiments) are in [`docs/`](docs).
- Access to the hidden v1 sets or raw transcripts: ask the maintainers of this repository (an issue is fine); they are shared privately for review, not published.
- Licences: tau2-bench is MIT (Sierra Research) and its retail store keeps that notice; everything else is under the repository's Apache-2.0 licence (root `LICENSE`).
