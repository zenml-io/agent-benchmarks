# Model swap on recorded traffic

## Question

Can a step-level replay of an agent's recorded model calls (Kitaru's model-swap analyzer) pick replacement models that keep full-run task success?

## Status

Complete, with the full-run ground truth withheld. The step checks ran on 2026-10-21. The ground truth is the [Haiku Tax](../haiku-tax) full runs of 2026-10-19 and 2026-10-20, which are withheld pending provider review.

Spend for this study: **$74.07**. That is $6.55 to re-record Sonnet 5.5 with transcripts, $65.06 for eight analyzer runs plus the judge, about $0.25 for smoke tests, and $2.21 for the GPT-6 Responses API reruns. Reusing the Haiku Tax full runs cost nothing extra.

## Results

All numbers are copied from [`results/model-swap-on-recorded-traffic.json`](results/model-swap-on-recorded-traffic.json). The incumbent is Claude Sonnet 5.5. For each use case the analyzer sampled 250 of Sonnet's recorded model calls (n = 250 per model). It sent each rebuilt request to 11 candidates once and compared the candidate's next step with Sonnet's.

The use cases are bank support (tau2-bench, private hidden split), invoice extraction, insurance claims triage and KYC checks; the last three are synthetic Haiku Tax environments. Open-weight models ran on one commercial inference provider, labeled `provider-a`.

### What is withheld, and why

Every per-candidate full-run number is withheld: success rate, the paired difference against Sonnet, cost per correct task, whether the candidate "holds" (at most 5 points below Sonnet), and full-run failure counts. They come from the Haiku Tax runs, which providers have not yet seen.

This file publishes:

- the step-check results;
- the analyzer's verdicts and picks;
- **aggregate** calibration counts, which name no candidate.

The aggregates rest on the withheld runs and cannot be recomputed from this repository.

### Step checks: tool-choice agreement with Sonnet

The cell values are tool-choice rates: among the sampled calls where Sonnet called a tool, the share where the candidate called the same tools. The denominators are support 120, invoice 248, claims 246 and KYC 250 calls. Fewer calls are answered where the failure rate is above 0. The Sonnet row is Sonnet replayed against its own recording, which is the noise floor.

| model | bank support | invoice | claims | KYC |
|---|---|---|---|---|
| Sonnet 5.5 (own replay) | 0.9917 | 0.9234 | 0.9268 | 1.0000 |
| Opus 5.5 | 0.9750 | 0.8710 | 0.8374 | 0.9720 |
| Haiku 5.5 | 0.9917 | 0.8024 | 0.8130 | 0.9680 |
| GPT-6 Luna | 0.9583 | 0.7218 | 0.7276 | 0.9200 |
| GPT-6.1 Sol | 0.9083 | 0.8185 | 0.5813 | 0.9680 |
| DeepSeek V4.1 Flash @ provider-a | 0.9667 | 0.7287 | 0.7869 | 0.8635 |
| DeepSeek V4 Pro @ provider-a | 0.9333 | 0.7764 | 0.8286 | 0.9558 |
| GLM 5.3 @ provider-a | 0.9667 | 0.7530 | 0.7724 | 0.9798 |
| GLM 5.3 Flash @ provider-a | 0.9524 | 0.7830 | 0.7354 | 0.9736 |
| gpt-oss-120b @ provider-a | 0.8500 | 0.3158 | 0.4408 | 0.4960 |
| Qwen3.8-27B @ provider-a | 0.9583 | 0.7419 | 0.7805 | 0.8920 |
| MiniMax-M3 @ provider-a | 0.9167 | 0.7773 | 0.7918 | 0.8560 |

The JSON also has exact agreement, judged agreement (exact, or ruled equivalent by the Jev judge), agreement on state-changing steps, failure rates and per-call cost. Every one of them has a Wilson 95% interval. Some reference points:

- Sonnet repeats its own exact step 0.48 (n = 250) of the time on bank support, and 0.592, 0.712 and 0.668 on the other three use cases.
- GLM 5.3 Flash lost 9.2% to 17.2% of its calls to rate limits.

### Analyzer verdicts and picks

The analyzer calls a candidate "comparable" when its tool-choice rate is within 0.10 of the best rate in the use case (Sonnet's own replay included) and its failure rate is at most 0.2.

| use case | comparable candidates (of 11) | cheapest pick | best open model pick | fastest pick |
|---|---|---|---|---|
| bank support | 10 (all but gpt-oss-120b) | GPT-6 Luna | DeepSeek V4.1 Flash @ provider-a | Qwen3.8-27B @ provider-a |
| invoice | 1 (Opus 5.5) | Sonnet 5.5 (no swap) | GLM 5.3 Flash @ provider-a | Sonnet 5.5 |
| claims | 2 (Opus 5.5, DeepSeek V4 Pro) | DeepSeek V4 Pro @ provider-a | DeepSeek V4 Pro @ provider-a | Sonnet 5.5 |
| KYC | 7 | GPT-6 Luna | GLM 5.3 @ provider-a | Sonnet 5.5 |

### Calibration against full runs (aggregate only; not reproducible from this repo)

- **Verdicts.** The comparable / not-comparable verdict matched the full-run outcome for 35 of 44 candidate-use-case pairs (0.7955). Of the 9 misses, 4 were called comparable but lost more than 5 points, and 5 were ruled out but held. By use case: 9, 8, 9 and 9 of 11.
- **Filter.** As a filter it worked: in all 4 use cases, at least 2 of the top 3 candidates by tool choice held full-run success, and in 3 of 4 all three did.
- **Picker.** As a picker it did not: in 3 of 4 use cases the cheapest candidate that held was outside the top three by tool choice.
- **Correlation.** Step metrics track full-run success only moderately. The mean within-use-case Spearman correlation over 11 candidates is 0.5434 for tool choice, 0.6287 for exact agreement, 0.5188 for judged agreement and 0.2015 for exact agreement on state-changing steps.

## Trust status

**Reproduced from committed rows (verified 2026-10-22).** `scripts/step_check_tables.py` recomputes every published step-check number from `results/runs/step_calls.jsonl` and compares 556 values with the results file, with **0 mismatches**. That covers:

- 52 model-by-use-case entries: counts, rates, Wilson intervals, judged agreement and state-changing steps;
- the analyzer's comparable verdict for each of the 44 candidate-use-case pairs;
- each pair's rank by tool choice.

**Reproduced privately, not reproducible here.** On 2026-10-22, the ported `src/analyze.py` was run on the original analyzer outputs and the withheld full-run rows. With the analyzer at Kitaru commit `04d52c6`, which batches A and B ran on, it regenerated `calibration.json` identically, including all aggregates above.

At the rerun pin `0217140`, everything is identical except the analyzer's picks. The newer `_best_for` measures picks against Sonnet's own replay ("closest" is never Sonnet) and adds a "worth a full replay" shortlist.

**Not checked:**

- **Full-run ground truth.** It is not public, and its own trust status is in [../haiku-tax](../haiku-tax).
- **Repeat replies.** Every candidate replied once per sampled call; there were no repeats.
- **Judge rulings.** No human checked the judge's equivalence rulings.
- **Live rerun.** The live calls (recording, analyzer runs) were not repeated.

**Known inconsistencies from the internal export:**

- The internal `calibration.json` gives `tool_choice_ci` with all answered calls as n. The tool-choice rate is over calls where Sonnet called a tool (for example 120, not 250, on bank support). The results file recomputes Wilson intervals with the right n, so they are wider.
- Batch A sent GPT-6 models through `/chat/completions` with reasoning off (Luna) and could not run GPT-6.1 Sol at all. Those entries are superseded by batch G (Responses API) and kept only under `superseded_step_checks`.
- Ties in tool-choice rank follow candidate order. On bank support, DeepSeek V4.1 Flash and GLM 5.3 tie at 0.9667, and GPT-6 Luna ties with Qwen3.8-27B at 0.9583.

**Steps that would vet it further:**

1. Rerun one use case (KYC, about $16 for batches A and B) at the same analyzer commit. Then compare tool-choice rates within their Wilson intervals, and check that the same candidates come out comparable.
2. Have a person review 50 judge "equivalent" rulings per use case and record agreement.
3. Repeat each candidate's replies 3 times on 100 calls, to measure how much a single reply moves the rates.
4. Publish the Haiku Tax full runs after provider review, so the aggregate calibration can be recomputed here.
5. Re-record Sonnet on invoice, claims and KYC and rerun the step check, to see how much the specific recording moves the verdicts.

## Harbor status

`not applicable` for the step check, and `portable` for its ground truth.

The step check is not an agent run. It is an offline analysis: the analyzer rebuilds recorded requests and sends each one to a candidate model once, with no environment, task or grader per attempt. It has no Harbor task form.

The ground truth is the Haiku Tax full runs. See [../haiku-tax](../haiku-tax#harbor-status) for what porting those to Harbor tasks would take. Once they run as Harbor jobs, their per-task rewards could replace `HAIKU_TAX_RESULTS` as the ground truth `src/analyze.py` reads.

## Limitations

- Synthetic tasks in simulated environments, plus one tau2-bench domain. One run per task in the full runs.
- Possible authorship and simulator bias toward Claude models:
  - Claude models wrote the environments.
  - The recorded traffic is Sonnet's.
  - Haiku 5.5, which is a candidate, simulates the bank customer.
- Each use case has only 11 candidates, so the rank correlations are rough.
- 250 of 383 to 876 recorded calls per use case were sampled, with one reply per candidate.
- The invoice, claims and KYC recordings come from a fresh Sonnet run on Oct 21, not from the baseline full runs they are compared with.
- The analyzer takes at most 8 candidates per run, so each use case ran as batch A and batch B (Sonnet is the reference in both), plus batch G for GPT-6. `src/analyze.py` merges them.
- "Comparable" is the analyzer's rule at the time of the runs. Later commits on the branch changed how picks are made.
- Costs use list prices from `../haiku-tax/harness/models.py`. provider-a prices there are unverified.
- Step-check costs per call do not get the warm prompt cache that the recorded calls had.
- The analyzer ran offline: sessions were built in memory from transcripts instead of fetched from a Kitaru server, and the time budget was raised to 3600 s. Everything after session loading is the plugin's code.
- The bank support step checks use recorded traffic from a private hidden split. Their rows are published with anonymized task ids and without texts or arguments, and they cannot be rerun from this repository.
- The Kitaru model-swap plugin (0.1.0) is on an unmerged feature branch and is not generally available.

## Provenance

Ported from a private research repository (directory `benchmarks/haiku-tax/calib`, commit `545c38a22f0157ccf69cc96c6af2f1d5273a1bed`; the full-run harness was at `4cb3302e37a5a012e0482e4a028dc20dd8afc0f1`).

- **Analyzer.** [zenml-io/kitaru](https://github.com/zenml-io/kitaru), branch `feature/model-swap-analyzer`, plugin `plugins/packages/model-swap`. Batches A and B ran at `04d52c6`, batch G after `f1b93ee`. The rerun pin is `0217140`.
- **Who ran it.** Hamza Tahir (ZenML), with Claude Code agents, on 2026-10-21.
- **Left out:**
  - full transcripts and raw analyzer outputs, which contain reply texts and the private support traffic;
  - the bank support converter and tool export;
  - the internal blog draft and page builder;
  - Sonnet's re-recording result rows (full-run results).

  These stay in the private archive.
