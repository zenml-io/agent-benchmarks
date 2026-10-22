# Decision agents on real public decisions

## Question

Are tool-using decision agents accurate against real outcomes, stable across reruns, replayable from recorded tool answers, and which cheap signals catch their wrong decisions?

Three domains, same agent design: California Independent Medical Review health appeals (`claims`), US Board of Veterans' Appeals decisions (`bva`), and German first-instance social court health-insurance suits (`de_kr`, German-language prompts and tools). In each case the agent reads a case file through tools, can search a library of past decisions, and must submit a binary decision (uphold/overturn the denial, grant/deny the benefit, dismiss/allow the suit) with a confidence and cited precedents. It is graded against the real reviewer's, Board's or court's outcome.

## Status

Complete. Run on 2026-10-09 and 2026-10-10 (claims 17:27-21:08 UTC on Oct 9; bva and de_kr finished 01:37 and 02:04 UTC on Oct 10). Two open models served by us with vLLM 0.31.0, one H100 each: Qwen3.8-27B (dense, `dense`) and Qwen3.6-35B-A3B-FP8 (MoE, 3B active, `moe`). Total spend: not recorded (GPU time was not logged per run, and the bill was not split for these runs). No API models, no paid APIs.

## Results

All numbers are from [`results/decision-agents.json`](results/decision-agents.json) and were recomputed from the committed rows in `results/runs/` (see Trust status). n = sessions (cases x attempts). **A session with no decision (the agent never called the submit tool in 12 model turns) counts as wrong.** The earlier write-ups (`claims.md`, `bva.md`, `de_kr.md`, FINDINGS sections 12-14 in the original repo) reported accuracy over decided sessions only; that column is shown too.

### Accuracy (base condition, 2 attempts per case, temperature 0.6)

| domain | model | n | correct | accuracy (95% CI) | decided | accuracy of decided | no decision |
|---|---|---|---|---|---|---|---|
| claims (150 cases, 75/75) | dense | 300 | 228 | 0.7600 (0.6967-0.8200) | 292 | 0.7808 | 8 |
| claims | MoE | 300 | 210 | 0.7000 (0.6367-0.7633) | 263 | 0.7985 | 37 |
| bva (124 cases, 70 grant / 54 deny) | dense | 248 | 199 | 0.8024 (0.7379-0.8629) | 239 | 0.8326 | 9 |
| bva | MoE | 248 | 209 | 0.8427 (0.7863-0.8992) | 246 | 0.8496 | 2 |
| de_kr (150 cases, 75/75) | dense | 300 | 183 | 0.6100 (0.5433-0.6767) | 240 | 0.7625 | 60 |
| de_kr | MoE | 300 | 195 | 0.6500 (0.5833-0.7167) | 293 | 0.6655 | 7 |

CI: bootstrap over cases with all their sessions, 2000 resamples, seed 0. In de_kr, counting no-decision as wrong reverses the dense-vs-MoE order of the decided-only figures.

No-AI baselines (n = cases): claims, majority outcome of past decisions for the same treatment: 103/150 = 0.6867 (always overturn: 0.5000). Agent minus baseline, paired by case, all sessions: dense +7 pts (CI -3 to +17), MoE +1 pt (CI -7 to +11). bva, majority outcome of past decisions sharing the issue's first distinctive word: 77/124 = 0.6210 (always grant: 70/124 = 0.5645). de_kr, majority outcome of library cases sharing a distinctive word: not reproducible to one value (depends on Python's hash seed; see Trust status); always dismiss: 0.5000.

### Stability: how often the decision changes (pairs where both sessions decided)

| domain | rerun, dense | rerun, MoE | model change (dense vs MoE) |
|---|---|---|---|
| claims | 13/143 = 0.0909 | 18/123 = 0.1463 | 49/258 = 0.1899 |
| bva | 13/117 = 0.1111 | 13/122 = 0.1066 | 30/237 = 0.1266 |
| de_kr | 10/103 = 0.0971 | 28/143 = 0.1958 | 46/237 = 0.1941 |

### Replay: share of a second run's tool calls (name + normalized arguments, submit excluded) already in the first run

| domain | comparison | pairs | mean share of calls recorded | fully answerable from the recording | identical call sequence |
|---|---|---|---|---|---|
| claims | rerun, dense | 150 | 0.7522 | 32 (0.2133) | 0.0400 |
| claims | rerun, MoE | 150 | 0.7457 | 48 (0.3200) | 0.1667 |
| claims | model change | 300 | 0.7836 | 109 (0.3633) | 0.0067 |
| bva | rerun, dense | 124 | 0.7525 | 26 (0.2097) | 0.0806 |
| bva | rerun, MoE | 124 | 0.7236 | 32 (0.2581) | 0.1290 |
| bva | model change | 248 | 0.7962 | 107 (0.4315) | 0.0282 |
| de_kr | rerun, dense | 150 | 0.6748 | 15 (0.1000) | 0.0267 |
| de_kr | rerun, MoE | 150 | 0.7341 | 39 (0.2600) | 0.1200 |
| de_kr | model change | 300 | 0.7712 | 98 (0.3267) | 0.0000 |

### Which signal catches wrong decisions (decided sessions, both models pooled)

| signal | claims: catches wrong / flags right | bva | de_kr |
|---|---|---|---|
| not stated with high confidence | 96/117 (0.8205) / 153/438 (0.3493) | 54/77 (0.7013) / 168/408 (0.4118) | 64/155 (0.4129) / 117/378 (0.3095) |
| the other model disagrees | 49/117 (0.4188) / 49/438 (0.1119) | 30/77 (0.3896) / 30/408 (0.0735) | 46/155 (0.2968) / 46/378 (0.1217) |
| a rerun of the same agent disagrees | 31/117 (0.2650) / 31/438 (0.0708) | 26/77 (0.3377) / 26/408 (0.0637) | 38/155 (0.2452) / 38/378 (0.1005) |
| LLM judge (dense model) says incorrect | 36/116 (0.3103) / 30/429 (0.0699) | 19/54 (0.3519) / 56/307 (0.1824) | 55/138 (0.3986) / 67/319 (0.2100) |

The LLM judge gave no usable verdict on 10 of 555 (claims), 124 of 485 (bva) and 76 of 533 (de_kr) decided sessions; its rates are over the rest. With binary decisions, a disagreeing pair always holds one right and one wrong decision, so the two disagreement signals flag exactly as many right decisions as wrong ones. Citations: no decision in any base session cited a precedent ID that does not exist or that the agent had not retrieved.

### Claims under realistic changes (dense model, 1 attempt per case, n = 150 each, compared case by case with the normal run's attempt 0)

| condition | correct / n | accuracy | accuracy of decided | wrongful denials (overturn cases, decided) | decisions changed vs normal run |
|---|---|---|---|---|---|
| normal run (attempt 0) | 113/150 | 0.7533 | 0.7687 | 24/74 = 0.3243 | rerun noise: 13/143 = 0.0909 |
| cost-pressure paragraph in the system prompt | 109/150 | 0.7267 | 0.7415 | 32/74 = 0.4324 | 20/146 = 0.1370 |
| precedent tools fail (HTTP 503) half the time | 85/150 | 0.5667 | 0.8500 | 10/49 = 0.2041 | 9/100 = 0.0900 |
| precedents shown without their outcome | 120/150 | 0.8000 | 0.8333 | 17/73 = 0.2329 | 15/142 = 0.1056 |
| precedent tools answered by an LLM simulator | 104/150 | 0.6933 | 0.7027 | 33/74 = 0.4459 | 32/145 = 0.2207 |

Cost pressure raised wrongful denials by +11 pts (paired, CI +3 to +20, 74 cases); a regression suite of 30 / 50 / 150 cases would detect it (one-sided 95%) 24% / 37% / 80% of the time (500 simulated suites each). With faulty tools, 50 of 150 sessions ran out of turns. With simulated tools, 132 of 148 decisions cited a precedent ID that does not exist.

## Trust status

**Reproduced on 2026-10-22, from the committed rows (free):** every number in the JSON's `results`, `per_type`, `noise.size` and `additional_measurements.flips` / `replay` / `signals`, plus the claims condition table, the regression-suite power figures and the claims signal and group tables (`claims_conditions.md`, `claims_signals.md` in the original repo), match exactly when recomputed by `scripts/analyze_rows.py --check results/decision-agents.json`. The rows were produced by `scripts/export_rows.py` from the original session files (which stay private); the export script that built the JSON was also re-run on those session files and matched. This shows the published tables follow from the recorded decisions; it says nothing about whether a new run would give the same decisions.

**Reproduced from freshly fetched public data (free):** the California IMR CSV downloads byte-identical to the original run's copy, and `claims_bench.py build` rebuilds the candidate set and the precedent library byte for byte. The BVA index slice is rebuilt byte for byte from the Hugging Face dataset at a pinned revision; `bva_bench.py build` is not deterministic (see below), and `scripts/pin_bva_candidates.py` rebuilds the original candidate and library files byte for byte from va.gov. The claims baseline (103/150) and the agent-vs-baseline differences (+7, CI -3 to +17; +1, CI -7 to +11) and the bva baseline (77/124) reproduce. Re-fetching the 684 German judgments by ID from Open Legal Data gives a byte-identical cases file (every label re-derived from the Tenor matches). The de_kr keyword baseline gave 78, 80, 80, 82, 83 and 83 correct of 150 (0.5200-0.5533) under hash seeds 0-5, so the published 53% is one draw from that range. With the private session files placed in a work directory, the five original `analyze` commands run unchanged from `harness/` and reprint `claims.md`, `claims_conditions.md`, `claims_signals.md` and `bva.md` byte for byte, and `de_kr.md` except the baseline line (53% under 2 of 6 seeds, 52% or 55% under the others).

**Not reproduced:** no agent, extraction or judge call was re-run (they need GPUs). The case files the US agents read were written by the dense model from the decision text and are not public (they paraphrase real case text); nobody has re-checked them for outcome leakage beyond the original regex. Judge verdicts were not re-derived. Transcripts are not public, so the rows cannot be checked against the agents' actual reasoning by outside readers.

**Known inconsistencies between the earlier write-ups and the data:**
- The bva test set is 70 grant / 54 deny, not "half granted, half denied" as `bva.md` and FINDINGS section 14 say; "always grant" scores 0.5645, not 50%. Extraction failed for 151 of 281 candidates and the grants survived more often. `bva/cases.jsonl` has 126 rows with 2 duplicate case IDs; the duplicates come from byte-identical duplicate rows in the upstream index (4,000 sampled rows, 3,901 unique IDs). The analysis dedupes them by ID (124 cases).
- The same upstream duplicates explain "705 library decisions" in `bva.md`: 705 rows, 693 unique IDs. `claims.md` says 19,374 precedents: 19,374 rows, 19,371 unique IDs.
- Prose accuracies (78%/80%, 83%/85%, 76%/67%) are over decided sessions only. Counting undecided sessions as wrong gives 0.76/0.70, 0.8024/0.8427 and 0.61/0.65; in de_kr this reverses which model is better. The dense model left 60 of 300 German sessions undecided.
- The de_kr keyword baseline (53% in `de_kr.md`) depends on Python's hash seed: candidate words come from a set sorted by length only, so ties between equal-length words fall in hash order. Six seeds gave 52-55% in the export; see below for the port's own check.
- FINDINGS section 13's "37% more tool calls" under tool outages holds when counting the submit call and comparing with both normal attempts (1.3733x); excluding submit and comparing with the normal attempt-0 run it is 15.21 vs 10.46 calls per session (1.4544x).
- FINDINGS section 12's "21-36% of reruns fully answerable": the 36% (0.3633) is the model-change pair, not a rerun (reruns: 0.2133 and 0.3200).
- `bva_bench.py build` picks a slightly different candidate set on each run (grant candidates are sampled from decisions fetched on 4 threads, in completion order). A rebuild on 2026-10-22 kept 274 of the original 281 candidate IDs. The test set is therefore pinned by ID in `data/`.

**Steps that would vet it further:**
1. Smoke-rerun 20 de_kr cases (no extraction step) with both models, 2 attempts, and compare accuracy and flip rates with the published rows; then the full de_kr rerun (it needs only the two servers).
2. Hand-check 20 claims and 20 bva case files against the source decision text for leaked outcome cues (the regex only catches wording), and against the rows to see whether wrong decisions cluster on thin case files.
3. Hand-read 20 judge verdicts and 20 "no usable verdict" sessions (bva lost 124 of 485 to server disconnects and unparsable output) and re-judge the missing ones.
4. Rerun the claims base condition with 5 attempts per case to tighten the rerun-flip estimate and the agent-vs-baseline CI, which currently includes 0.
5. Make the de_kr keyword baseline deterministic (sort by `(len, word)`) and report one value; report bva as balanced accuracy or rebalance it to 54/54.
6. Add a stronger non-AI baseline per domain (for example a logistic model on the structured fields) so "beats a lookup table" is tested against something less weak.

## Harbor status

`portable`, not ported. The agents are a bare tool-calling loop (no shell, no files) over an OpenAI-compatible endpoint, so a Harbor port is mostly packaging:

- **Tasks.** One task per case (424 in all; one dataset per domain), `instruction.md` = the case prompt ("Review appeal MN24-41699."). The environment image holds the case file and the precedent library, built at image-build time from the fetch scripts (the case text cannot be committed), with the test case removed from the library.
- **Tools as an MCP server.** The four case and precedent tools plus the submit tool become one MCP server running next to the agent. The submit tool records the decision, confidence and citations to a file; the hidden grader reads that file, never the agent's prose, and compares the decision with the label. The claims conditions (cost-pressure prompt, 50% tool faults, blind precedents, simulated tools) become setup files that differ only in the prompt or the MCP server's mode.
- **Agent.** To keep the published numbers comparable, a custom agent (`import_path: package.module:Class`) has to reproduce this loop exactly: the system prompts, 12 model turns, temperature 0.6, 4096 max tokens, the nudge message after a turn without tool calls, served model name `agent-model`. Running stock coding agents (Claude Code, Codex, Terminus 2) against the same MCP server is possible but is a different benchmark.
- **Four checks.** Oracle: `solve.sh` calls submit with the true label (scores 1). Nop: no submit (scores 0; also how the original counts undecided sessions). Shortcuts that must score 0: submitting the opposite label, and looking the outcome up online, which matters here because every case is a public decision (the IMR CSV, va.gov and Open Legal Data all publish the outcome): the task needs `network_mode = "no-network"` or an allowlist with only the model endpoint. Alternative valid solution: a submit that cites different precedents or uses a different confidence must still pass.
- **Post-processing.** The judge, the confidence and disagreement signals and the replay coverage are computed across attempts, so they stay as analysis scripts over Harbor's trajectories (the rows format in `results/runs/` is the target). Harbor's guidance of 5+ attempts per task would replace the 2 used here.
- **Serving.** The models stay self-hosted (vLLM on one GPU per model, see `../self-hosted-agents-harness`); Harbor only needs the endpoint URL.

## Limitations

- Two open models (Qwen3.8-27B dense, Qwen3.6-35B-A3B MoE) served by us; no frontier models.
- claims covers one state's medical-necessity and experimental-treatment reviews, which are written decisions, not insurers' claim files.
- The US case files are rewritten from the decision text by the dense model; the choice of facts can hint at the outcome even after the regex leak check. The German case files are the court's own statement of facts (Tatbestand).
- One LLM judge (the dense model, which is also one of the agents); it gave no usable verdict on 124 of 485 (bva) and 76 of 533 (de_kr) decided sessions.
- 124-150 cases per domain; group-level fairness gaps cannot be resolved (overlapping CIs).
- The claims experiment conditions are one attempt per case on the dense model only.
- No cost per decision: GPU time was not logged for these runs.
- The bva test set is not balanced (70/54) and 2 cases appear twice in the original case file; analysis dedupes by ID.
- The de_kr keyword baseline depends on Python's hash seed.
- Precedent libraries come from the same sources as the test cases; an agent can find closely related past decisions, which is intended (precedent use) but means results reflect retrieval-augmented decisions.
- Every case is a public decision, and the agents had no web access in the original harness (tools only), but the models may have seen some of these decisions in training.

**What is left out of this repo and why:** the case data (fetched by script; licenses below), the model-written case files and the full session transcripts and judge outputs (they paraphrase or quote real case facts and the agents' reasoning; they stay in the original private repo). `results/runs/` keeps per-session IDs, decisions, confidence, turn counts, tool names, hashed tool calls (so replay coverage can be recomputed without the arguments), seen and cited precedent IDs, and judge verdicts.

**Data licenses.** California IMR determinations (CalHHS Open Data Portal, Department of Managed Health Care): no open license is declared on the dataset; the portal's Terms of Use (last modified 2023-01-27) allow free download and use. BVA research index (`williamTLmiller/BVA-AMA-Era-170KStructured` on Hugging Face): CC-BY-NC-4.0, non-commercial, attribute the dataset; BVA decision text from va.gov is a US government work. German social court decisions via the Open Legal Data API: no content license declared (its terms cover rate limits and liability); German court decisions are official works without copyright (§ 5 UrhG). This repo commits only case IDs, outcome labels, public case metadata (court, file number, date for de_kr) and the agents' decisions.

## Provenance

Built and run by Hamza Tahir (ZenML) with Claude Code agents in the private research repo (files `claims_bench.py`, `claims_signals.py`, `bva_bench.py`, `de_kr_fetch.py`, `de_kr_bench.py`; write-ups `claims.md`, `claims_conditions.md`, `claims_signals.md`, `bva.md`, `de_kr.md`, FINDINGS sections 12-14). Harness commit `4ead7caa65c49ddadaad0d1d846110a9c41613ea` (last change to those files; the agent loop is unchanged since the runs, later commits only made the judge and de_kr resume save progress incrementally). Result directories last committed at claims `4ca75fb1dd5fa7bffb075a3c3a55cde32685d75c`, bva `e2d3cc30880b2bc64218400a7209304d4ec051ac`, de_kr `f39d121153cf8a23168f44f865213098bd98406e`. Ported to this repo on 2026-10-22; code changes are listed in [RERUN.md](RERUN.md#changes-from-the-original-run).
