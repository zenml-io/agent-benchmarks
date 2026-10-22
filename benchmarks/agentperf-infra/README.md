# agentperf-infra: does serving infrastructure change what a self-hosted agent solves?

## Question

Do GPU, load and serving settings change how many tasks a self-hosted agent solves, and what each solved task costs?

## Status

Complete. Runs on 2026-10-08 (failed quickcheck attempts) and 2026-10-09 03:46 to 13:52 UTC (every valid run). 85 valid runs (77 on the full task sets plus 8 quickchecks), 3,744 agent trials in the published tables.

Spend: the real Modal bill for the study was about $390, of which about $218 GPU (rounded figures from the original write-up; no bill export exists). Recorded in the rows for these task sets, including the quickchecks and failed runs: GPU run time $194.5856, GPU startup $18.6399, estimated sandboxes $165.2641 (the sandbox estimate under-counts the bill; see the cost model in [the harness README](../self-hosted-agents-harness/README.md#cost-model-read-this-before-trusting-any-cost-number)).

Setup in one paragraph: Qwen3.8-27B (dense, hybrid attention, thinking on by default) served by vLLM 0.31.0 on one Modal GPU per run (H100 unless the config says H200/B200), a second model Qwen3.6-35B-A3B-FP8 (MoE) as contrast; 36 Terminal-Bench 2.0 tasks (`data/tasks.json`, all with agent limits of 10-20 minutes) and 60 GAIA validation tasks (`data/tasks_gaia.json`, 10-minute limit); harnesses terminus-2, mini-swe-agent, opencode, pi; N agents share one GPU server (`cN`); each serving config changes one thing vs vLLM defaults (full list in `../self-hosted-agents-harness/experiment.py` `CONFIGS` and in `results/agentperf-infra.json` `setup.conditions`).

## Results

All numbers from `results/agentperf-infra.json`, which `scripts/rebuild_export.py` rebuilds from `results/runs/attempts.jsonl` (verified identical, see Trust status). n = trials (tasks x attempts x runs, pooled); every attempted trial counts, crashes, time-outs, harness install failures and benchmark lookups as unsolved. CI = task-clustered bootstrap, 2000 resamples, seed 0. Cost per solve = (GPU run time + estimated sandboxes) / solved trials, in cents.

**Terminal-Bench 2.0 (36 tasks)**

| harness \| config \| agents | GPU | runs | n | solved | accuracy | 95% CI | cents per solve |
|---|---|---|---|---|---|---|---|
| mini-swe-agent \| defaults \| c8 | H100 | 1 | 36 | 18 | 0.5000 | 0.3333-0.6667 | 30.5150 |
| mini-swe-agent \| defaults \| c16 | H100 | 2 | 108 | 47 | 0.4352 | 0.2870-0.5833 | 24.6023 |
| mini-swe-agent \| defaults \| c32 | H100 | 3 | 144 | 43 | 0.2986 | 0.1806-0.4306 | 30.2602 |
| mini-swe-agent \| defaults \| c48 | H100 | 1 | 72 | 25 | 0.3472 | 0.2083-0.4861 | 24.2428 |
| mini-swe-agent \| defaults \| c64 | H100 | 1 | 72 | 19 | 0.2639 | 0.1528-0.3889 | 29.9184 |
| mini-swe-agent \| b200 \| c32 | B200 | 2 | 108 | 53 | 0.4907 | 0.3426-0.6389 | 18.0968 |
| mini-swe-agent \| h200 \| c32 | H200 | 2 | 108 | 49 | 0.4537 | 0.3056-0.6019 | 18.0218 |
| mini-swe-agent \| h200-spec-mtp \| c32 | H200 | 1 | 36 | 18 | 0.5000 | 0.3333-0.6667 | 16.1167 |
| mini-swe-agent \| kv-fp8 \| c32 | H100 | 2 | 72 | 27 | 0.3750 | 0.2222-0.5278 | 22.6419 |
| mini-swe-agent \| weights-fp8 \| c32 | H100 | 2 | 72 | 29 | 0.4028 | 0.2639-0.5556 | 19.7169 |
| mini-swe-agent \| spec-mtp \| c16 | H100 | 1 | 36 | 17 | 0.4722 | 0.3056-0.6389 | 23.9759 |
| mini-swe-agent \| spec-mtp \| c32 | H100 | 3 | 144 | 52 | 0.3611 | 0.2361-0.4931 | 25.2610 |
| mini-swe-agent \| no-prefix-cache \| c32 | H100 | 2 | 72 | 25 | 0.3472 | 0.2083-0.5000 | 25.6844 |
| mini-swe-agent \| no-thinking \| c32 | H100 | 2 | 108 | 43 | 0.3981 | 0.2500-0.5370 | 18.5191 |
| mini-swe-agent \| defaults-2x-time \| c32 | H100 | 2 | 108 | 42 | 0.3889 | 0.2500-0.5370 | 39.8455 |
| mini-swe-agent \| defaults-4x-time \| c16 | H100 | 1 | 36 | 17 | 0.4722 | 0.3056-0.6389 | 57.2012 |
| mini-swe-agent \| defaults-4x-time \| c32 | H100 | 1 | 36 | 14 | 0.3889 | 0.2222-0.5556 | 65.3879 |
| mini-swe-agent \| moe-a3b \| c16 | H100 | 2 | 108 | 53 | 0.4907 | 0.3519-0.6296 | 12.7432 |
| mini-swe-agent \| moe-a3b \| c32 | H100 | 2 | 108 | 53 | 0.4907 | 0.3426-0.6389 | 12.7813 |
| terminus-2 \| defaults \| c8 | H100 | 1 | 36 | 19 | 0.5278 | 0.3611-0.6944 | 28.4563 |
| terminus-2 \| defaults \| c16 | H100 | 2 | 108 | 48 | 0.4444 | 0.2963-0.5926 | 23.7862 |
| terminus-2 \| defaults \| c32 | H100 | 4 | 216 | 89 | 0.4120 | 0.2778-0.5463 | 20.0146 |
| terminus-2 \| defaults \| c48 | H100 | 1 | 72 | 24 | 0.3333 | 0.2083-0.4722 | 23.3004 |
| terminus-2 \| defaults \| c64 | H100 | 1 | 72 | 16 | 0.2222 | 0.1111-0.3472 | 36.2194 |
| terminus-2 \| b200 \| c32 | B200 | 2 | 108 | 60 | 0.5556 | 0.4167-0.6944 | 15.9148 |
| terminus-2 \| h200 \| c32 | H200 | 2 | 108 | 48 | 0.4444 | 0.2963-0.5926 | 17.3175 |
| terminus-2 \| h200-spec-mtp \| c32 | H200 | 1 | 36 | 21 | 0.5833 | 0.4167-0.7500 | 12.1952 |
| terminus-2 \| kv-fp8 \| c32 | H100 | 2 | 72 | 36 | 0.5000 | 0.3611-0.6389 | 16.6817 |
| terminus-2 \| weights-fp8 \| c32 | H100 | 2 | 72 | 30 | 0.4167 | 0.2778-0.5556 | 19.7813 |
| terminus-2 \| spec-mtp \| c16 | H100 | 1 | 36 | 19 | 0.5278 | 0.3611-0.6944 | 18.1426 |
| terminus-2 \| spec-mtp \| c32 | H100 | 3 | 144 | 63 | 0.4375 | 0.3194-0.5625 | 19.0471 |
| terminus-2 \| no-prefix-cache \| c32 | H100 | 2 | 72 | 31 | 0.4306 | 0.2917-0.5833 | 19.5910 |
| terminus-2 \| no-thinking \| c32 | H100 | 2 | 108 | 49 | 0.4537 | 0.2963-0.6111 | 17.1624 |
| terminus-2 \| defaults-2x-time \| c32 | H100 | 2 | 108 | 50 | 0.4630 | 0.3241-0.6019 | 30.6324 |
| terminus-2 \| defaults-4x-time \| c16 | H100 | 1 | 36 | 22 | 0.6111 | 0.4722-0.7778 | 39.4927 |
| terminus-2 \| defaults-4x-time \| c32 | H100 | 1 | 36 | 17 | 0.4722 | 0.3056-0.6389 | 51.3829 |
| terminus-2 \| moe-a3b \| c16 | H100 | 2 | 108 | 51 | 0.4722 | 0.3333-0.6111 | 17.5618 |
| terminus-2 \| moe-a3b \| c32 | H100 | 2 | 108 | 46 | 0.4259 | 0.2963-0.5648 | 15.3900 |
| opencode \| defaults \| c16 | H100 | 1 | 36 | 18 | 0.5000 | 0.3333-0.6667 | 21.1683 |
| opencode \| defaults \| c32 | H100 | 1 | 36 | 16 | 0.4444 | 0.3056-0.6111 | 18.2456 |
| pi \| defaults \| c16 | H100 | 1 | 36 | 15 | 0.4167 | 0.2500-0.5833 | 24.2087 |
| pi \| defaults \| c32 | H100 | 1 | 36 | 14 | 0.3889 | 0.2500-0.5556 | 19.4464 |

**GAIA (60 validation tasks, one run each)**

| harness \| config \| agents | GPU | n | solved | accuracy | 95% CI | cents per solve |
|---|---|---|---|---|---|---|
| mini-swe-agent \| defaults \| c16 | H100 | 60 | 18 | 0.3000 | 0.1833-0.4167 | 23.6283 |
| mini-swe-agent \| defaults \| c32 | H100 | 60 | 13 | 0.2167 | 0.1167-0.3167 | 25.1300 |
| mini-swe-agent \| h200 \| c32 | H200 | 60 | 21 | 0.3500 | 0.2333-0.4667 | 15.9795 |
| terminus-2 \| defaults \| c16 | H100 | 60 | 14 | 0.2333 | 0.1333-0.3333 | 27.9943 |
| terminus-2 \| defaults \| c32 | H100 | 60 | 12 | 0.2000 | 0.1000-0.3000 | 24.4775 |
| terminus-2 \| h200 \| c32 | H200 | 60 | 20 | 0.3333 | 0.2167-0.4500 | 15.1020 |

**Paired differences vs H100 defaults at 32 agents** (percentage points, paired by task, 95% bootstrap CI, 2000 resamples; Terminal-Bench 36 tasks, GAIA 60 tasks; "difference" = mini-swe-agent's change minus terminus-2's; exploratory except the pre-registered tests below)

| change | mini-swe-agent | terminus-2 | difference |
|---|---|---|---|
| B200 | +19.21 (+8.56 to +30.56) | +14.35 (+7.41 to +22.69) | +4.86 (-8.33 to +17.13) |
| H200 | +15.51 (+5.79 to +25.69) | +3.24 (-4.63 to +10.65) | +12.27 (+0.46 to +23.84) |
| H200 + spec-mtp | +20.14 (+6.25 to +35.42) | +17.13 (+8.80 to +25.93) | +3.01 (-13.43 to +19.68) |
| 8 agents | +20.14 (+8.33 to +33.33) | +11.57 (+3.70 to +20.37) | +8.56 (-3.70 to +21.99) |
| 16 agents | +13.66 (+5.79 to +22.22) | +3.24 (-2.31 to +9.26) | +10.42 (+2.31 to +19.44) |
| 48 agents | +4.86 (-1.39 to +11.81) | -7.87 (-14.35 to -1.39) | +12.73 (+2.08 to +23.61) |
| 64 agents | -3.47 (-12.50 to +4.86) | -18.98 (-29.17 to -9.26) | +15.51 (+3.24 to +27.55) |
| FP8 KV cache | +7.64 (+0.69 to +14.58) | +8.80 (+0.93 to +16.67) | -1.16 (-12.73 to +10.65) |
| FP8 weights | +10.42 (+2.78 to +18.75) | +0.46 (-6.94 to +8.33) | +9.95 (-1.16 to +21.06) |
| MoE model | +19.21 (+4.17 to +35.42) | +1.39 (-11.11 to +14.81) | +17.82 (+4.86 to +31.94) |
| spec-mtp | +6.25 (+0.00 to +13.19) | +2.55 (-4.17 to +9.95) | +3.70 (-6.02 to +13.43) |
| prefix cache off | +4.86 (-2.08 to +12.50) | +1.85 (-6.48 to +10.19) | +3.01 (-9.03 to +16.44) |
| thinking off | +9.95 (+0.46 to +20.14) | +4.17 (-5.09 to +13.89) | +5.79 (-6.25 to +17.36) |
| 2x time limit | +9.03 (+2.31 to +16.44) | +5.09 (-1.85 to +13.43) | +3.94 (-6.71 to +14.58) |
| 4x time limit | +9.03 (-2.08 to +21.53) | +6.02 (-6.94 to +18.98) | +3.01 (-14.35 to +20.60) |
| GAIA: H200 | +13.33 (+0.00 to +26.67) | +13.33 (+3.33 to +25.00) | +0.00 (-18.33 to +18.33) |
| GAIA: 16 agents | +8.33 (-3.33 to +20.00) | +3.33 (-5.00 to +13.33) | +5.00 (-10.00 to +21.67) |

**Cost per solve relative to H100 at 32 agents** (GPU + sandbox estimate; ratio with 95% CI): Terminal-Bench mini-swe-agent H200 0.5956 (0.4294-0.7737), B200 0.5980 (0.4235-0.7880); terminus-2 H200 0.8652 (0.7251-1.0438), B200 0.7952 (0.6414-0.9242). GAIA H200: mini-swe-agent 0.6359 (0.3573-1.0272), terminus-2 0.6170 (0.3428-0.9201).

**Pre-registered tests** (`docs/PREREGISTRATION.md`, only the 48 runs recorded after its commit, `results/analysis/confirmatory.original.md`): C1 H200 helps mini-swe-agent more than terminus-2: +9 pts (-7 to +24), Holm p 0.291, not confirmed. C2 32 vs 16 agents hurts mini-swe-agent more: -9 (-24 to +5), Holm p 0.291, not confirmed. C3 thinking off interacts with the harness: -3 (-17 to +10), Holm p 0.691, not confirmed. C4 the share of "out of time, still working" trials rises with median seconds per agent step: Spearman rho +0.67 over 38 cells, permutation p < 0.001 (printed 0.000), confirmed.

Failure classes per condition (out of time while working / looping, finished wrong, never started, looked up the benchmark, other error) are in `results[*].failures`; for example mini-swe-agent at 32 agents on the H100 had 92 "out of time, working" among its 101 unsolved trials. More analyses (KV-cache saturation, deadline fragility, trace-only signals, rerun divergence) are in `results/analysis/` and `docs/FINDINGS.md`.

## Trust status

**Reproduced from the published rows, by running the code from this directory (2026-10-22):**

- Every number in `results`, `per_type`, `excluded_runs`, the paired comparisons and the cost ratios of `results/agentperf-infra.json`, and the recorded-spend totals: `scripts/rebuild_export.py` prints `ALL MATCH`. Task difficulty for `per_type` comes from a fresh `harbor download terminal-bench@2.0`, whose `task.toml` files are byte-identical to the ones cached during the runs; the 60 GAIA tasks downloaded now are identical to the cached ones too.
- The original generated reports `analysis.md`, `analysis_gaia.md`, `confirmatory.md`, `mechanisms.md`, `reliability.md` and `trajectories.md` regenerate byte-identical from the public rows (`results/analysis/*.original.md` vs the regenerated files).
- Offline unit tests of the harness (11) and of the analysis helpers (2) pass.

**Not reproduced, and why:**

- No run was repeated: every row comes from the original runs on Oct 8-9, 2026. Run-to-run noise is large (identical conditions differed by up to 16.67 points; a plain rerun flips pass/fail on 17-20% of tasks).
- The failure class per trial was computed from the raw trajectories before publishing (`../self-hosted-agents-harness/make_public_rows.py`); the trajectories are not published, so the classifier itself (`src/trajectories.py`) cannot be re-run on them here. Its inputs and rule are in the code.
- `trace_signals.md` and `divergence.md` (findings 9 and 11 of `docs/FINDINGS.md`) need the raw trajectories and are only included as original outputs.
- Costs: GPU cost is computed from run time and list prices, not taken from the bill; the sandbox share is an estimate (it was $38 against $48 billed in the one window checked). The "about $390 real bill" is a rounded figure with no bill export behind it.
- The benchmark-lookup filter only catches tool calls that name the benchmark; GAIA tasks allow internet, so an agent could find an answer without naming GAIA.

**Known inconsistencies between earlier write-ups and the data** (from the export; the JSON is computed from the rows):

- `docs/FINDINGS.md` reports C4 as rho +0.65 over 37 cells; the generated `confirmatory.md` (and a rerun from the rows today) gives +0.67 over 38 cells.
- `docs/ADVERSARIAL_CHECKS.md` gives older cost-per-solve ratios (mini-swe-agent B200/H100 0.53 (0.35-0.72); terminus-2 H200 0.88, B200 0.96, "no clear difference") and C1 Holm p = 0.25; the data now give 0.598 (0.4235-0.788), 0.8652, 0.7952 (B200 CI 0.6414-0.9242, i.e. cheaper) and Holm p 0.291.
- FINDINGS section 3 gives terminus-2's real cost per solve at 8 agents as $0.29; the rows give 28.4563 cents.
- FINDINGS says agent limits are 15-20 minutes; the 36 tasks' `task.toml` limits are 600-1200 s (10-20 minutes; 32 tasks at 15 minutes).
- The original README's harness table listed qwen-coder and openhands; the runs used terminus-2, mini-swe-agent, opencode and pi.
- The original README described the model as served on one H100; the study also ran H200 and B200 configs.
- Total spend exists only as an approximate real bill (about $390).

**Steps that would vet it further:**

1. Rerun the four central cells once more (both harnesses x H100 defaults c32 and B200 c32, 2 attempts per task; the same four runs cost $25.32 recorded (GPU + startup + sandbox estimate) and 35-48 minutes of server time each, see RERUN.md) and check the B200 paired difference against the published +19.21 / +14.35 points.
2. Rerun the 8-task quickcheck for terminus-2 ($3.59 recorded: GPU run time + startup + sandbox estimate, two runs) to confirm the harness, Harbor pins and vLLM image still build and produce the same order of solve rate (4-5 of 8).
3. Hand-check 20 trials classed "out of time, working" and 20 "finished wrong" against their trajectories in the private archive, to test the failure classifier that the C4 confirmation rests on.
4. Pull the Modal billing report for 2026-10-08/09 (`modal billing report --start 2026-10-08 --resolution h --show-resources --json`) and replace the rounded $390 / $218 with exact numbers and a measured sandbox share.
5. Search the published trajectories' tool calls for GAIA answer lookups that do not name the benchmark (e.g. fetching the HF dataset), since those would inflate GAIA solves.

## Harbor status

`native`. Every agent trial ran as a Harbor 0.24.0 job on Modal sandboxes: `harbor run -y -d terminal-bench@2.0` (or `-d gaia/gaia`) `-a <terminus-2 | mini-swe-agent | opencode | pi> -m openai/agent-model -e modal -n <agents> [-k 2]` with the task list as `-i` filters, harness versions pinned through `--ak version=...`, and the model endpoint passed as `OPENAI_BASE_URL` plus harness kwargs. Grading is the datasets' own Harbor verifiers (reward >= 1). The exact command per run is printed by `experiment.py --dry-run` and listed in `results/rerun_plan.md`. What is outside Harbor: the vLLM server (a separate Modal app deployed before each job), the serving configs, the per-run cost accounting and the benchmark-lookup filter (`experiment.py`). Toward the repo's Harbor-native target: the setups (harness x serving config) are CLI flags rather than job config files, the GAIA dataset is resolved as `gaia/gaia@latest` (not pinned; it matched the run today), and each condition has 1-4 runs of 1-2 attempts per task rather than 5+.

## Limitations

- Two models (one dense, one MoE), one engine version (vLLM 0.31.0), Modal GPUs and list prices as of October 2026.
- 36 of 89 Terminal-Bench 2.0 tasks, chosen with agent limits of 20 minutes or less, so effects through the time limit are larger than on the full benchmark; 60 of 165 GAIA validation tasks.
- Many cells are one run of 36 tasks; claims rest on the paired intervals and cells with 108+ trials. Most harness-difference results are exploratory; the three pre-registered harness interactions were not confirmed.
- Sandbox cost is an estimate that under-counts the bill; GPU cost excludes startup.
- Agents had internet access; lookups that do not name the benchmark are not caught.
- In-sandbox harnesses (all but terminus-2) never start on `qemu-startup` (a package mirror 404), which costs them one task per run.
- Not published: trajectories, Harbor logs and per-run vLLM metric samples (they contain task content and agent-cloned benchmark answers); they stay in the private archive. The per-run rows keep the per-trial outcome, timing, steps, tokens, exception type and failure class.

## Provenance

Original code and data: private research repo, root directory, commit 0d1500e22533e7f546bc6d8cfe5abe8d976c9868 (rows last changed in 6f799c79b0a774e01af9f8adcc0261fd4b49d702; runner code in 5b1fdf6e52629c15d27af3125098d10b164c6bf2). Run by Hamza Tahir (ZenML) with Claude Code agents. Ported 2026-10-22; every change is listed in RERUN.md.

Files here: `src/` analysis code, `scripts/` the original run scripts (`run_*.sh`) and `rebuild_export.py`, `data/` task lists, `docs/` FINDINGS (sections 1-9, 11), PREREGISTRATION and ADVERSARIAL_CHECKS from the original repo, `results/` the export, the per-run rows, original and regenerated reports and the rerun plan, `tests/`. The runner is in `../self-hosted-agents-harness/`.
