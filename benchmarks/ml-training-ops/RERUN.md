# Rerunning ml-training-ops

Commands in sections 3-5 were run while writing this file, from this directory, on 2026-10-22 (Linux, 4 CPUs, 15 GB RAM). Sections 6-7 cost money and were **not re-run**; costs and times are the recorded ones from `results/runs/`.

## 1. Prerequisites

- Linux or macOS, Python 3.11+, [uv](https://docs.astral.sh/uv/).
- Local task checks: about 2 GB of disk for CPU torch and ray, 4 CPUs; no Docker.
- Paid runs: a Modal account (GPUs for the self-hosted server, CPU sandboxes for the tasks, 2x L40S sandboxes for the torchtitan tasks), the Modal and Harbor CLIs; for vendor-API runs an OpenAI and/or Anthropic API key.

## 2. Credentials

| variable | for | steps |
|---|---|---|
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | the vLLM server and every task sandbox | 6, 7 |
| `MODAL_ENVIRONMENT` | Modal environment (default `main`) | 6, 7 |
| `MODAL_APP_PREFIX`, `MODAL_HF_CACHE_VOLUME`, `MODAL_VLLM_CACHE_VOLUME`, `MODAL_FLASHINFER_CACHE_VOLUME` | optional server app / volume names | 6, 7 (self-hosted) |
| `OPENAI_API_KEY` | Codex and terminus-2 with OpenAI models (`src/api_runs.py`) | 6, 7 (vendor API) |
| `ANTHROPIC_API_KEY` or `EVAL_ANTHROPIC_API_KEY` | Claude Code runs (`src/api_runs.py`) | 7 (vendor API) |
| `API_LOG` | separate API log file name, to run two sessions in parallel | optional |
| `SPENT_BEFORE` | GPU dollars spent outside `attempts.jsonl`, for the `--budget` guard | optional |

Names only in `.env.example`.

## 3. Install (verified on 2026-10-22)

```bash
cd benchmarks/ml-training-ops
uv sync                                  # analysis and table rebuild: no dependencies
uv sync --group taskcheck                # local task checks: torch 2.5.1 (CPU), numpy 2.1.3, pytest 8.4.1, pyyaml 6.0.2, ray 2.50.1 (same pins as the task images)
uv tool install 'modal[api-proxy-support]==1.6.1'                                   # paid steps
uv tool install 'harbor[modal]==0.24.0' --with 'modal[api-proxy-support]==1.6.1'   # paid steps
```

(On 2026-10-22 the task-check environment was created with `uv venv --python 3.11` and `uv pip install` of the same pins; the group above installs the same versions.)

## 4. Get the data (verified on 2026-10-22)

All tasks are ours and committed as sources. Build the Harbor tasks of the hard / v2 / v3 / torchtitan rounds from `tasks/mlops_hard/src/` (the v1 tasks in `tasks/mlops_tasks/` are committed as built):

```bash
(cd tasks/mlops_hard && python build.py)      # "wrote atomic-checkpoint, corrupt-shard, ..." (18 tasks) into tasks/mlops_hard/tasks/
uv run --with 'harbor==0.24.0' python scripts/validate_tasks.py   # "24 task dirs, 0 problems"
```

- `ray-exactly-once`'s 64 data shards (16 MB) are not committed: its `gen/gen.py` (seeded) writes them at image build, and running it locally reproduced the original shards byte for byte.
- The torchtitan tasks clone `github.com/pytorch/torchtitan` at tag v0.2.2 (BSD-3-Clause) at image build and apply our faults (`gen/make_fork.py`); `titan/` holds the calibration scripts used to set their thresholds (they run on Modal GPUs; not re-run).
- License of our task code: not chosen yet (see the repository's license).

## 5. Free checks (verified on 2026-10-22)

Rebuild every table of the export from the rows:

```bash
uv run python scripts/rebuild_export.py
# conditions rebuilt: 37 (11 vendor-API); paired comparisons: 18; API ${'api_total': 29.2653, 'openai': 29.2477, 'anthropic': 0.0176}; self-hosted GPU $94.0053, recorded sandbox estimate $56.8279, re-priced at requested CPU/memory $223.0465
# ALL MATCH
```

Regenerate the original hard-set report (writes `mlops_hard.md` here) and compare:

```bash
uv run python src/mlops_hard_analysis.py > /dev/null && diff results/mlops_hard.original.md mlops_hard.md   # no output
```

Recorded API runs and the rerun plan (free, print only):

```bash
API_LOG=results/runs/api_attempts.jsonl uv run python src/api_runs.py report   # ends "openai total $29.25"
python ../self-hosted-agents-harness/plan_rerun.py results/runs/attempts.jsonl  # = results/rerun_plan.md
# last line: Total over 38 runs: GPU $94.01 + startup $8.14 + sandbox estimate $56.83; 25.5 server-hours if run one after another.
```

Local fault checks without containers: for each task the original code must FAIL its hidden tests and the reference fix must PASS (torchtitan tasks excluded: they need 2 GPUs):

```bash
cd tasks/mlops_hard && uv run python build.py --check atomic-checkpoint corrupt-shard ddp-replica-drift elastic-churn exact-resume gang-controller \
  k8s-quota-zone k8s-unschedulable memory-leak-oom ray-exactly-once regression-bisect reshard-optimizer straggler-diagnosis throughput-sla two-stragglers uneven-shard-hang
cd ../mlops_tasks && uv run python make_tasks.py --check     # note: also rewrites the six v1 task dirs (identically)
```

Results on 2026-10-22: all 16 CPU hard/v2/v3 tasks OK (original fails, reference passes) and all 6 v1 tasks OK. `throughput-sla` failed its reference check once ("400-step job only 1.0x faster") while the machine was loaded by other processes, and passed when re-run alone (buggy fail in 521 s, fixed pass in 282 s): its test times the job against the original in the same sandbox, so run it on an idle machine. The whole batch took about 70 minutes on 4 CPUs. `elastic-churn`'s test leaves its killed workers' child `train.py` processes running on a local machine (in a sandbox they die with it); kill them afterwards.

## 6. Smoke test (paid, not re-run)

Self-hosted, cheapest recorded run: the v1 pilot with terminus-2 at 30 agents (6 tasks x 5 attempts), recorded $0.95 GPU + $0.45 sandbox estimate, 18 minutes of server time, 30/30 solved:

```bash
python ../self-hosted-agents-harness/experiment.py --tasks-file tasks_mlops.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 30 --rep-from 0 --reps 1 --attempts 5
```

Free Harbor validation on Modal (sandbox cost only, no model): the reference solution must pass and doing nothing must fail.

```bash
harbor run -y -p tasks/mlops_hard/tasks -a oracle -e modal -n 8 -o jobs --job-name hard-oracle $(for t in $(python3 -c "import json;print(' '.join(json.load(open('data/tasks_mlops_hard.json'))['tasks']))"); do echo -i $t; done)
harbor run -y -p tasks/mlops_hard/tasks -a nop    -e modal -n 8 -o jobs --job-name hard-nop    $(for t in $(python3 -c "import json;print(' '.join(json.load(open('data/tasks_mlops_hard.json'))['tasks']))"); do echo -i $t; done)
```

Recorded: oracle 8/8 in 2:24, no-op 0/8 in 2:35 (Harbor's progress lines); their sandbox cost was not recorded separately (the original quotes a $28.35 Modal bill for Oct 10 13:00-15:00 UTC that covered task validation and the first runs).

Vendor API, cheapest recorded run (Codex + GPT-6 Luna on the 8 hard tasks, 1 attempt): $0.07 API, 4 minutes:

```bash
OPENAI_API_KEY=... uv run python src/api_runs.py run --harness codex --model openai/gpt-6-luna --attempts 1 --concurrency 8 --tasks-file data/tasks_mlops_hard.json
```

Success: a row in `api_attempts.jsonl` here with `attempted` 8 and `harbor_rc` 0.

## 7. Full rerun (paid, not re-run)

**Self-hosted** (from this directory; `results/rerun_plan.md` lists all 38 recorded runs as commands with their cost and server minutes). By task set, recorded:

| task set | runs | per run | totals |
|---|---|---|---|
| v1 (`tasks_mlops.json`, 5 attempts, c=6 and c=30) | 4 | 18-42 min, GPU $0.95-2.01 | GPU $6.16, sandbox est. $2.13, startup $1.35 |
| hard (`tasks_mlops_hard.json`, 3 attempts, c=24 and c=8) | 30 | 27-68 min, GPU $1.57-4.29 | GPU $78.98, sandbox est. $46.50, startup $6.09 |
| v2 (`tasks_mlops_hard2.json`, 6 attempts, c=24) | 4 | 34-35 min, GPU $2.05-2.38 | GPU $8.87, sandbox est. $8.20, startup $0.69 |

Example, the hard-set headline pair for one harness: `python ../self-hosted-agents-harness/experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs defaults h200 --concurrency 24 --reps 2 --attempts 3`. Sandbox estimates under-count about 4x for these tasks (README, Trust status); budget the real sandbox cost at roughly GPU + 4x the estimate. Outputs: `attempts.jsonl`, `jobs/` here.

**Vendor API** (`src/api_runs.py run`, each appends to `api_attempts.jsonl`; the provider's recorded spend plus `--estimate` must stay under `--budget`, default $160):

| round | command (add `--tasks <one task>` for the v3 / torchtitan rounds) | recorded |
|---|---|---|
| hard + v2, 11 tasks | `--harness codex --model openai/gpt-6-luna --attempts 3 --concurrency 24 --tasks-file data/tasks_mlops_all.json` | 2 runs, $0.30 + $0.32, 6-12 min |
| same | `--model openai/gpt-6.1-sol` / `openai/gpt-6-astra` (codex), `--harness terminus-2 --model openai/gpt-6.1-sol` | $3.30, $19.76, $2.21; 6-7 min each |
| v3, one task per run (regression-bisect, throughput-sla, ray-exactly-once, gang-controller, elastic-churn) | `--harness codex --model openai/gpt-6-luna` or `openai/gpt-6.1-sol` `--attempts 3 --concurrency 3 --tasks-file data/tasks_mlops_all.json --tasks <task>` | $0.02-0.65 and 4-11 min per run |
| torchtitan (titan-fork-drift, titan-silent-divergence) | same with `--attempts 2 --concurrency 2 --tasks <task>` | $0.03-0.28 and 4-22 min per run (2x L40S sandboxes, cost not recorded) |
| Claude Code + Haiku 5.5, hard 8 | `--harness claude-code --model anthropic/claude-haiku-5-5 --attempts 1 --concurrency 8` | failed in setup on every trial |

Total recorded API cost $29.2653. Codex 0.162.1 and Claude Code 2.1.296 were installed by Harbor in the original runs (not pinned); pin them with Harbor's `--ak version=...` if you add it to `api_runs.py`, or record what you got.

## 8. Compare with the published results

Point the rebuild at your rows: copy your `attempts.jsonl` (made publishable with `BENCH_DIR=. python ../self-hosted-agents-harness/make_public_rows.py --task-sets mlops-k5 mlops_hard-k3 mlops_hard2-k6`) and `api_attempts*.jsonl` over `results/runs/` in a scratch copy and run `scripts/rebuild_export.py`; it lists every value that differs. Compare cells with the paired bootstrap of `src/mlops_hard_analysis.py` (written to `mlops_hard.md`). Identical self-hosted runs differed by up to 7 solves of 24 (mini-swe-agent with thinking off: 8/24 vs 15/24); with 8 tasks only differences of about 20 points or more are distinguishable, and a paired CI that includes 0 means no difference.

## Harbor-native version

`harbor/` holds the tasks as Harbor-native tasks (separate-container grading, shortcuts, alternatives, job configs, dataset manifests); its README has the commands for the free four checks on Modal, a real agent comparison, and the self-hosted harness with `data/tasks_harbor_*.json`. The steps above use the original task folders, which are unchanged.

## 9. Troubleshooting

- Every trial errors instead of scoring: Harbor without the `[modal]` extra, or the hard tasks were not built (`build.py`).
- Harbor's `-t` filter is ignored for local task directories; use `-i` (the original aborted Claude Code smoke test started every task because of this).
- Torchtitan tasks: need Modal GPU sandboxes (2x L40S, 32 GB); image builds take long (torch 2.11 cu128, torchtitan requirements; `torchao` is unpinned, so a rebuild can differ).
- `api_runs.py` refuses to run: the provider's spend in `api_attempts.jsonl` plus `--estimate` exceeds `--budget`.
- A self-hosted cost per solve looks too cheap: see the sandbox under-count in README.md.

## Changes from the original run

- `uneven-shard-hang`'s `app/logs/nightly.log`: the traceback's file paths now read `/app/...` and the interpreter `/usr/local/bin/python`; the original log carried paths from the machine that generated it. The log's content is otherwise unchanged, so the task asks the same thing, but the agent saw the original paths in the published runs.

- Task sources moved under `tasks/` (`tasks/mlops_tasks/`, `tasks/mlops_hard/`, `tasks/titan/`); the task lists in `data/` point to `tasks/mlops_tasks` and `tasks/mlops_hard/tasks` (were `mlops_tasks`, `mlops_hard/tasks`). Task content unchanged, including five `logs/*.log` inputs that the original repo never committed (taken from the working tree that built the tasks). Built `tasks/mlops_hard/tasks/` and the generated `ray-exactly-once` shards are not committed (rebuilt by `build.py` and the task's generator).
- `tasks/titan/*.py` docstrings: `modal run --env $MODAL_ENVIRONMENT` instead of the original environment name.
- `src/api_runs.py`: paths relative to this benchmark dir; `MODAL_ENVIRONMENT` from the environment (default `main`) instead of a hard-coded name; default `--tasks-file data/tasks_mlops_hard.json`; creates `jobs/` if missing.
- `src/mlops_hard_analysis.py`: reads `results/runs/attempts.jsonl` by default (`ATTEMPTS_FILE` overrides); when `jobs/` is absent, per-task solves and time-outs come from the rows' per-trial `ok` / `exc` (identical to `reward.txt` for every run, checked before publishing); writes `mlops_hard.md` in this directory.
- `src/hard_trace_signals.py`: exits with a message when no raw trajectories are present instead of writing an empty report.
- Published rows: `results/runs/attempts.jsonl` is the 39 ML-ops rows of the original file (task sets `mlops-k5`, `mlops_hard-k3`, `mlops_hard2-k6`) with `error` reduced to its first line without paths or URLs; `api_attempts.jsonl` and `api_attempts_anthropic.jsonl` are unchanged.
- `results/ml-training-ops.json`: the export with its `public_safety` wording neutralized.
- New: `scripts/rebuild_export.py`, `scripts/validate_tasks.py`, `results/rerun_plan.md`, `pyproject.toml` (with the `taskcheck` group).
