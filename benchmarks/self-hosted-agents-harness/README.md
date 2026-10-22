# Self-hosted agents harness (shared)

The code that ran three benchmarks in this repo: [agentperf-infra](../agentperf-infra/), [ml-training-ops](../ml-training-ops/) (its self-hosted runs) and [sglang-vs-vllm](../sglang-vs-vllm/) (its servers). It is not a benchmark by itself; it has no results of its own.

One run = deploy one open model on one Modal GPU with one set of vLLM flags, point one agent harness at it through [Harbor](https://github.com/harbor-framework/harbor), run every task in a task list, stop the server, and append one row to `attempts.jsonl`.

## Files

| file | what it does |
|---|---|
| `experiment.py` | the runner: `run` (one run), `matrix` (harness x config x concurrency x repeat, resumable), `quickcheck`, `report`, `--dry-run`. Holds the serving configs (`CONFIGS`), the harness pins (`HARNESSES`), GPU prices (`GPU_PRICES`) and the cost model. |
| `serve_vllm.py` | the Modal app: vLLM 0.31.0 on a CUDA 13 devel image, one container, flags held constant in `COMMON`, per-config flags from `VLLM_ARGS`. |
| `serve_sglang.py` | the same for SGLang 0.5.20 (used only by sglang-vs-vllm). |
| `vllm_metrics.py` | scrapes vLLM's `/metrics` every 10 s during a run; the summary goes into each row's `vllm` field. |
| `test_experiment.py` | offline tests (parsing, report, dry-run commands, endpoint parsing). No Modal, no Harbor, no GPU. |
| `plan_rerun.py` | prints the exact `experiment.py` command for every recorded run in a rows file, with its recorded cost and wall time. Runs nothing. |
| `make_public_rows.py` | how the published rows were made from the private `attempts.jsonl` + raw job folders (error strings scrubbed, per-trial failure class added). |
| `backfill_trials.py` | brings rows written by older code up to date from `jobs/` (used once during the original runs). |
| `archive_jobs.sh` | uploads finished raw run folders to a private Modal volume (`MODAL_RAW_VOLUME`). |
| `setup.sh` | installs the pinned Modal and Harbor CLIs and runs the offline tests. |

## How Harbor is used (all three benchmarks are Harbor-native)

`experiment.py` builds and runs exactly this (see `harbor_cmd`; `--dry-run` prints it):

```
OPENAI_BASE_URL=<server>/v1 OPENAI_API_BASE=<server>/v1 OPENAI_API_KEY=not-used MODAL_ENVIRONMENT=<env> \
harbor run -y (-d terminal-bench@2.0 | -d gaia/gaia | -p <local task dir>) -a <harness> -m openai/agent-model \
  -e modal -n <concurrency> [-k <attempts>] [--agent-timeout-multiplier <x>] \
  -o <bench>/jobs --job-name <task_set>__<harness>__<config>__c<N>__r<rep>__<time> \
  --ek sandbox_timeout_secs=7200 --ak <harness kwargs: api_base / model_info / version ...> -i <task> ...
```

- Harbor 0.24.0 with the `[modal]` extra; every task runs in a Modal sandbox (`-e modal`) with internet access (in-sandbox harnesses need it to reach the server).
- Harnesses are Harbor's built-in agents, pinned: `terminus-2` (Harbor 0.24.0's own, runs on the machine that runs Harbor), `mini-swe-agent` 2.4.6, `opencode` 1.18.35, `pi` 1.1.0 (installed inside each sandbox). All call the model as an OpenAI-compatible endpoint named `agent-model`.
- Solved = Harbor's `verifier_result.rewards.reward >= 1`. A trial whose tool calls name the benchmark (cloning its repo, searching for it) is never counted as solved (`peeked`).
- The model server is not a Harbor component: it is a separate Modal app deployed before `harbor run` and stopped after it.

## Cost model (read this before trusting any cost number)

- `cost` in a row = **GPU time while the agents ran** (`run_s` x $/GPU-hour from `GPU_PRICES`: H100 $3.95, H200 $4.54, B200 $6.25, Modal list prices in Oct 2026). Server startup (`startup_cost`, typically 2-4 minutes, more on a first weight download) is recorded separately and is not in `cost`.
- **Harbor's task sandboxes bill on top and `experiment.py` cannot see them.** `sandbox_cost_est` estimates them per trial as sandbox lifetime x the task's requested CPUs x $0.1419/core-hour + GiB x $0.024/GiB-hour, reading the requested resources from Harbor's local task cache (`~/.cache/harbor/tasks`). A task not found there (any local `-p` task, e.g. all ML-ops tasks) is priced as 1 CPU + 2 GiB, whatever it requests.
- Checked against the real Modal bill only twice in the original runs: for one window the estimate was $38 against $48 billed (orphaned, aborted and in-flight sandboxes are not in it), and sandboxes added about 30% on top of GPU at 16 agents and about 70% at 32 agents with parallel streams. The agentperf study's whole real bill was about $390, $218 of it GPU (rounded figures; no bill export is in the repo).
- `--budget` (default 560) stops starting new runs past that much **GPU** spend from `attempts.jsonl` plus `SPENT_BEFORE`; it does not see sandboxes. Check `modal billing report` yourself during long runs.

## Install (verified on 2026-10-22)

```bash
uv tool install 'modal[api-proxy-support]==1.6.1'
uv tool install 'harbor[modal]==0.24.0' --with 'modal[api-proxy-support]==1.6.1'
modal --version     # modal client version: 1.6.1
harbor --version    # 0.24.0
cd benchmarks/self-hosted-agents-harness && uv sync && uv run python test_experiment.py   # 11 x "ok test_..."
```

The `api-proxy-support` extra is only needed behind an HTTP proxy. `setup.sh` does the same and also checks your Modal credentials; it needs `MODAL_TOKEN_ID` / `MODAL_TOKEN_SECRET`.

## Configuration (no values in the repo)

See `.env.example`. Modal names are all env vars: `MODAL_ENVIRONMENT` (default `main`), `MODAL_APP_PREFIX` (default `agent`; apps are `<prefix>-<config>[-s<slot>]`), `MODAL_HF_CACHE_VOLUME` / `MODAL_VLLM_CACHE_VOLUME` / `MODAL_FLASHINFER_CACHE_VOLUME` (defaults `hf-cache`, `vllm-cache`, `flashinfer-cache`, created on first use), `MODAL_RAW_VOLUME` (archive only). `BENCH_DIR` (default: current directory) is where the task lists, `attempts.jsonl`, `jobs/` and `report.md` live; the benchmarks' scripts `cd` there. Both models are public on Hugging Face, so no HF token is needed.

## Lessons from the original runs (still apply)

- Qwen3.8-27B is hybrid (Gated DeltaNet + attention): vLLM's H100 default `max_num_seqs=1024` exceeds its Mamba state blocks and startup fails; `COMMON` sets 128.
- On H100 vLLM JIT-compiles a FlashInfer kernel for this model and needs `nvcc`, hence the CUDA devel base image.
- Without Harbor's `[modal]` extra every trial fails instantly.
- `modal app stop` returns before the container is gone, so a deploy right after can be answered by the previous server; `wait_ready` only accepts a server that has served no tokens and `run_one` waits for the old URL to go quiet.
- Killing Harbor locally does not stop its Modal sandboxes; in-sandbox agents keep calling the server URL. Sandbox lifetime is capped at 2 h (`--ek sandbox_timeout_secs=7200`). Clean up by stopping the sandboxes of Harbor's Modal app when no run is active.
- A crash-looping server keeps billing; after any failure check `modal app list --env $MODAL_ENVIRONMENT`.
- JSON-valued vLLM flags (spec-mtp, no-thinking) crash-looped when passed as strings through the image ENV line; `serve_vllm._unnest` keeps them as nested objects.
- Global options go before the subcommand; after `--harnesses a b` put `--` before the subcommand.
- In-sandbox harnesses fail to install on Terminal-Bench's `qemu-startup` task (a Debian security mirror returns 404), every time; counted unsolved, shown as `setup_failed`.
- Only one runner per Modal environment and app prefix at a time; parallel streams need distinct `--slot`s.

## Changes from the original code

Original: `experiment.py`, `serve_vllm.py`, `serve_sglang.py`, `vllm_metrics.py`, `test_experiment.py`, `setup.sh`, `archive_jobs.sh`, `backfill_trials.py` at the root of the private research repo (commit 0d1500e22533e7f546bc6d8cfe5abe8d976c9868; `experiment.py` last changed in 5b1fdf6e52629c15d27af3125098d10b164c6bf2). Behavior is unchanged except:

- Modal environment, app-name prefix and volume names come from env vars (above); the original hard-coded its own names. The `--modal-env` default is now `$MODAL_ENVIRONMENT` or `main`.
- Task lists, `attempts.jsonl`, `jobs/`, `report.md` and `PAUSE` are read from `BENCH_DIR` (default: current directory) instead of the code's own directory, and `--tasks-file X` also finds `data/X`. `ATTEMPTS_FILE` can point at another rows file.
- `test_experiment.py` runs against a throwaway benchmark dir and expects `--env test-env`; two analysis-helper tests moved to `../agentperf-infra/tests/test_analysis.py`. Example URLs in the tests use a placeholder workspace.
- `setup.sh` no longer checks for a specific Modal environment name; `archive_jobs.sh` needs `MODAL_RAW_VOLUME`.
- Comments that quoted internal budget instructions were reworded; the `--budget` default (560) is unchanged.
- New: `plan_rerun.py`, `make_public_rows.py`.
