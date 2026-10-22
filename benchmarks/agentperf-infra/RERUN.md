# Rerunning agentperf-infra

Commands in sections 3-5 were run while writing this file, from a clean checkout of this directory, on 2026-10-22 (Linux, Python 3.13 system / uv-managed 3.12 venvs, uv 0.11). Sections 6-7 cost money and were **not re-run**; their costs and times are the recorded ones from `results/runs/attempts.jsonl`.

## 1. Prerequisites

- Linux or macOS, Python 3.11+, [uv](https://docs.astral.sh/uv/).
- Free checks: nothing else (network only to download the public task sets).
- Paid runs: a Modal account with GPU access (H100, H200, B200) and sandboxes; the Modal and Harbor CLIs (section 3). The machine that runs Harbor must stay awake for the whole run (terminus-2 runs locally).

## 2. Credentials

| variable | for | steps |
|---|---|---|
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | deploying the vLLM server and Harbor's sandboxes | 6, 7 |
| `MODAL_ENVIRONMENT` | which Modal environment to use (default `main`) | 6, 7 |
| `MODAL_APP_PREFIX`, `MODAL_HF_CACHE_VOLUME`, `MODAL_VLLM_CACHE_VOLUME`, `MODAL_FLASHINFER_CACHE_VOLUME` | optional names for the server apps and volumes (defaults `agent`, `hf-cache`, `vllm-cache`, `flashinfer-cache`) | 6, 7 |
| `SPENT_BEFORE` | dollars already spent outside `attempts.jsonl`, counted by the `--budget` guard (default 0) | 6, 7 |

No model API keys: the agents call your own vLLM server. No Hugging Face token: both checkpoints are public. Names only in `.env.example`.

## 3. Install (verified on 2026-10-22)

```bash
cd benchmarks/agentperf-infra
uv sync                                   # no dependencies; creates .venv
uv tool install 'modal[api-proxy-support]==1.6.1'                                   # paid steps only
uv tool install 'harbor[modal]==0.24.0' --with 'modal[api-proxy-support]==1.6.1'   # paid steps only; also used in section 4
modal --version && harbor --version       # "modal client version: 1.6.1", "0.24.0"
```

## 4. Get the data (verified on 2026-10-22)

The task lists are committed (`data/tasks.json`: 36 Terminal-Bench 2.0 task names; `data/tasks_gaia.json`: 60 GAIA task ids, levels 19/31/10, seed 0). The tasks themselves are fetched by Harbor at run time. For the free checks only the Terminal-Bench `task.toml` files are needed (task difficulty):

```bash
mkdir -p /tmp/tb && harbor download terminal-bench@2.0 -o /tmp/tb     # "Successfully downloaded 89 task(s)", a few seconds
```

- Terminal-Bench 2.0: Harbor registry `terminal-bench@2.0`, from github.com/laude-institute/terminal-bench, Apache-2.0. The 36 downloaded `task.toml` files were byte-identical to the ones cached during the original runs.
- GAIA: Harbor registry `gaia/gaia` (165 validation tasks, from huggingface.co/datasets/gaia-benchmark/GAIA, gated; its terms ask you not to reshare the data outside gated or private repos, so nothing from it is committed here, only task ids). `harbor download gaia/gaia -o /tmp/gaia` worked on the second try (the first hit a transient proxy error); the 60 tasks used were identical to the cached ones. Not needed for the free checks.

## 5. Free checks (verified on 2026-10-22)

```bash
uv run python ../self-hosted-agents-harness/test_experiment.py   # 11 lines "ok test_..."
uv run python tests/test_analysis.py                             # ok test_analysis_paired_and_interaction, ok test_confirmatory_helpers
uv run python scripts/rebuild_export.py --tb-tasks /tmp/tb       # rebuilds every table of results/agentperf-infra.json
```

Expected last lines of `rebuild_export.py`:

```
conditions rebuilt: 42 (48 condition x benchmark cells); trials: 3744; paired rows: 15 TB + 2 GAIA; cost ratios: 6; recorded spend: {'gpu_cost_all_infra_records_usd': 194.5856, 'startup_cost_all_infra_records_usd': 18.6399, 'sandbox_est_all_infra_records_usd': 165.2641}
ALL MATCH
```

Regenerate the original reports from the rows and compare (each `diff` prints nothing):

```bash
D=results/analysis
uv run python src/analysis.py               > $D/analysis.regenerated.md;      diff $D/analysis.original.md $D/analysis.regenerated.md
uv run python src/analysis.py gaia gaia-k2  > $D/analysis_gaia.regenerated.md; diff $D/analysis_gaia.original.md $D/analysis_gaia.regenerated.md
uv run python src/confirmatory.py           > $D/confirmatory.regenerated.md;  diff $D/confirmatory.original.md $D/confirmatory.regenerated.md
uv run python src/mechanisms.py             > $D/mechanisms.regenerated.md;    diff $D/mechanisms.original.md $D/mechanisms.regenerated.md
uv run python src/reliability.py            > $D/reliability.regenerated.md;   diff $D/reliability.original.md $D/reliability.regenerated.md
uv run python src/trajectories.py           > $D/trajectories.regenerated.md;  diff $D/trajectories.original.md $D/trajectories.regenerated.md
```

All six were identical on 2026-10-22. `src/trace_signals.py` and `src/divergence.py` need the raw trajectories (`jobs/`, private archive) and cannot run from the public rows.

Print every recorded run as a command with its cost (free; output committed as `results/rerun_plan.md`):

```bash
python ../self-hosted-agents-harness/plan_rerun.py results/runs/attempts.jsonl
# last line: Total over 85 runs: GPU $194.56 + startup $17.94 + sandbox estimate $165.26; 52.4 server-hours if run one after another.
```

Dry runs print the deploy / harbor / stop commands without spending anything:

```bash
python ../self-hosted-agents-harness/experiment.py --dry-run --harnesses terminus-2 -- quickcheck
```

## 6. Smoke test (paid, not re-run)

```bash
cd benchmarks/agentperf-infra
python ../self-hosted-agents-harness/experiment.py --harnesses terminus-2 -- quickcheck
python ../self-hosted-agents-harness/experiment.py report      # writes report.md
```

Two runs (vLLM defaults and prefix caching off), 8 tasks each, 16 agents, one H100. Recorded: 4/8 and 5/8 solved, $3.59 in total (GPU run time $2.53 + startup + sandbox estimate $0.65), 19 and 26 minutes of server time. Success looks like: both rows in `attempts.jsonl` with `"valid": true`, `attempted` 8, `vllm.busy_frac` > 0; the server is gone afterwards (`modal app list --env $MODAL_ENVIRONMENT`). The first start in a new Modal environment downloads about 55 GB of weights and compiles kernels (several extra minutes, reported as startup).

## 7. Full rerun (paid, not re-run)

The original ran as parallel streams, each with its own `--slot` so app names don't collide. The scripts are kept as they were run (only paths changed), each resumable (completed runs in `attempts.jsonl` are skipped):

| script | what | recorded cost and time |
|---|---|---|
| `scripts/run_infra.sh` | both main harnesses, 36 tasks, 1 rep: c=16, c=32 defaults; c=32 no-prefix-cache, spec-mtp, kv-fp8, weights-fp8; c=8 defaults | per run 21-100 min, GPU $1.29-6.43, sandboxes $0.68-4.56 |
| `scripts/run_streams.sh` | B: c=32 no-thinking, h200, defaults-2x-time; C: second repeat of the c=32 configs | same range |
| `scripts/run_d.sh` | D1: 2 attempts per task (task set `full-k2`) at c=32 defaults, defaults-2x-time, spec-mtp, then c=16 defaults; D2: pi + opencode at c=16/32, then c=48/64 with 2 attempts | k2 runs 34-83 min, GPU $2.08-5.29, sandboxes $1.52-6.02 |
| `scripts/run_i.sh` | pre-registered C1-C3 runs (k2, c=32: h200, no-thinking; terminus-2 defaults repeat) | as k2 above |
| `scripts/run_j.sh` | GAIA, 60 tasks: c=16/32 defaults and c=32 h200 for both harnesses | 23-43 min, GPU $1.37-2.57, sandboxes $1.45-1.80 |

Streams E-M of the original plan (b200, h200, h200-spec-mtp, spec-mtp c=16, defaults-4x-time, moe-a3b, k2 repeats) were started by hand, not by a script. `results/rerun_plan.md` lists **every** recorded run as one `experiment.py ... matrix` command restricted to that harness, config, concurrency, repeat and attempt count, with its recorded GPU cost, sandbox estimate and server minutes; run them from this directory.

Totals recorded for all 85 valid runs: GPU run time $194.56, startup $17.94, sandbox estimate $165.26, 52.4 server-hours if run one after another (the original took about 10 hours of wall clock with several parallel streams). The real bill for the study was about $390 (about $218 GPU): plan on 1.3x-1.7x the GPU figure for sandboxes, more under heavy load. Outputs land in this directory: `attempts.jsonl` (one row per run), `jobs/<job-name>/` (Harbor's per-trial results and trajectories), `jobs/<job-name>.log`, `jobs/<job-name>.metrics.jsonl`. Archive raw runs with `MODAL_RAW_VOLUME=... ../self-hosted-agents-harness/archive_jobs.sh` from this directory.

## 8. Compare with the published results

```bash
python ../self-hosted-agents-harness/make_public_rows.py --task-sets full full-k2 gaia quick --classify > /tmp/new_rows.jsonl   # BENCH_DIR=. (needs jobs/)
ATTEMPTS_FILE=/tmp/new_rows.jsonl uv run python src/analysis.py        # paired CIs on your rows
ATTEMPTS_FILE=/tmp/new_rows.jsonl uv run python src/confirmatory.py
```

To get the full export tables for new rows, point `scripts/rebuild_export.py` at them (`ATTEMPTS_FILE=/tmp/new_rows.jsonl`); it will list every value that differs from the published JSON. How to read differences: identical conditions differed by up to 16.67 points between runs, and a plain rerun flips pass/fail on 17-20% of tasks, so compare cells through paired-by-task CIs (`analysis.py`), not single solve rates. Treat a difference whose paired 95% CI includes 0 as no difference. Your cost numbers will differ with Modal's current prices and with how loaded the platform is (slower steps keep sandboxes alive longer).

## 9. Troubleshooting

- Server never ready / crash loop: check `modal app logs`; stop it (`modal app stop --env $MODAL_ENVIRONMENT -y <prefix>-<config>`), it bills while looping. Common causes in the original run: `--max-num-seqs` too high for the hybrid model (fixed in `COMMON`), JSON-valued flags arriving broken (fixed by `_unnest`).
- Every trial fails instantly: Harbor installed without the `[modal]` extra.
- "ready after 0s": the previous run's server answered; `wait_ready` rejects servers that already served tokens, wait for the old app to drain.
- Leftover sandboxes after killing Harbor keep calling the server: stop Harbor's sandbox app in Modal when no run is active.
- In-sandbox harnesses never start on `qemu-startup` (mirror 404): expected, counted unsolved.
- `harbor download` fails with a protocol error behind a proxy: retry.
- argparse eats the subcommand: put `--` after `--harnesses a b`.

## Changes from the original run

- Code moved from the private repo root into `src/` (analysis) and `../self-hosted-agents-harness/` (runner); see the harness README for its changes (Modal names as env vars, `BENCH_DIR`).
- `src/_paths.py` (new) puts the harness on `sys.path` and makes the analysis read `results/runs/attempts.jsonl` (override with `ATTEMPTS_FILE`).
- `src/trajectories.py` and `src/confirmatory.py`: when `jobs/` is absent they read each trial's precomputed `failure_class` (and `loop_share` for the sensitivity table) from the rows instead of re-classifying trajectories. With `jobs/` present the behavior is unchanged. The sensitivity loop was restructured to work from the three precomputed shares; output is byte-identical.
- `scripts/run_*.sh`: `cd` to the benchmark dir, call the harness by relative path, and `SPENT_BEFORE` defaults to 0 instead of the original 2.5 (dollars spent outside the rows in the original study).
- `data/`: task lists unchanged; `experiment.py` finds them in `data/`.
- Published rows (`results/runs/attempts.jsonl`, the 94 rows of task sets `full`, `full-k2`, `gaia`, `quick` from the original 133-row file): `error` keeps only its first line with deploy output, URLs and local paths removed; each trial gained `failure_class` and, for timed-out trials, `loop_share`. Nothing measured changed.
- `results/agentperf-infra.json`: the export, with its `public_safety` entries reworded so they no longer spell out the internal Modal names they warn about.
- `tests/test_analysis.py`: two tests moved out of the harness's test file.
- New: `scripts/rebuild_export.py` (the export's computation, reading failure classes from the rows), `results/rerun_plan.md`.
