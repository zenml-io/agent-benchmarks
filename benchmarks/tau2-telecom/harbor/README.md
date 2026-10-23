# tau2 Telecom on Harbor (Part B)

Part B of this benchmark as a Harbor job: tau2-bench's 40 Telecom test-split tasks, each with tau2's tools and simulated customer served by an MCP sidecar and graded by tau2's own evaluator, and the original PydanticAI agent (wrapped in Kitaru's `KitaruAgent`) as a custom Harbor agent whose model is a setting. Arms (baseline, unchanged rerun, model swaps, prompt rule) differ only in their setup file under `configs/arms/`.

Status: **partly native**. The tasks, the grader and the agent run on Harbor, and the four task checks pass (see [Checks](#checks-run)). No arm has been run with a model yet: the commands, cost and time are under [Paid runs](#paid-runs-not-run). Part A (public traces, step check) analyzes recordings and has nothing to port.

## Layout

| path | what |
|---|---|
| `tasks/telecom-test-NN/` | the 40 tasks, NN = the original run's case number: the task's index in tau2's Telecom `test` split as tau2's loader returns it (`tasks.json` order) at tau2-bench 05736c2, checked against the original run's recorded cases by `generate_tasks.py` and `tests/test_tasks.py`; `tasks/index.json` maps each to its tau2 task id and its id in Harbor's `sierra-research/tau3-bench` |
| `generate_tasks.py` | rebuilds `tasks/` from Harbor's tau3-bench adapter (pinned commit) and tau2-bench (pinned commit), then patches each task (below) |
| `task_files/` | files the generator puts in every task: `test.sh` and `build_state.py` (reference solution, alternative and shortcuts) |
| `agent/tau2_kitaru_harbor/` | the custom Harbor agent: `agent.py` (runs on the host, options model, install), `runner.py` (the agent, run inside the trial), `kitaru_sink.py` (local Kitaru recording) |
| `configs/job.yaml`, `configs/arms/*.yaml` | job settings (Modal, the 40 tasks) and one file per arm |
| `scripts/verify_tasks.py` | the four task checks through Harbor (free) |
| `scripts/summarize.py` | per-arm table from Harbor job folders, paired against the baseline |
| `scripts/upload_recordings.py` | sends the Kitaru recordings collected with each trial to a Kitaru server |
| `tests/` | offline tests: grader (all 40 tasks), the agent end to end with a scripted model and customer, the recording |
| `dataset.toml` | Harbor dataset manifest (`zenml/tau2-telecom-test40`); also listed in the repository's `registry.json` |

## How a trial runs

Each trial starts two containers from the task's compose file. `main` (Python 3.12 with tau2-bench installed) is where the agent runs and where the verifier grades. `tau3-runtime` is Harbor's adapter sidecar: it loads the task into tau2's Telecom environment, runs tau2's `UserSimulator` (gpt-4.1-2025-04-14, provider defaults) and serves an MCP server with `start_conversation`, `send_message_to_user`, the 13 agent tools and a few control tools. Every step is written to `/logs/agent/tau3_runtime_state.json`. After the agent finishes, `tests/test.sh` turns that log into a tau2 simulation and calls tau2's `evaluate_simulation` (substring communicate scoring, strict replay): reward 1 or 0, from the environment state (`ENV_ASSERTION`, all 40 tasks) and, for 12 tasks, the expected actions (`ACTION`). No model is called by the grader.

The agent (`runner.py`) is `harness/replay/tau2_kitaru_agent/episode.py` with the conversation moved into the sidecar: the same instructions (tau2's Telecom policy, taken from the task instruction and checked equal to `agent_domain_policy` for all 40 tasks), the same tools with tau2's own schemas, the same output validator (plain text before the customer leaves is a message to the customer), the same limits (100 model requests, 30 retries, tau2's 100 steps and 10 tool errors, 1200 s), the same prompt `Case N: continue the conversation with the user above.` and the same session names. The model sees only the tools the original had; the sidecar's control tools (`configure_run`, `record_termination`, `submit_assistant_tool_calls`, ...) are not offered to it.

Models: `openai:<id>` and `openai-responses:<id>` go to OpenAI, both through the Responses API (`/responses`; pydantic-ai-slim 2.51.0 builds `OpenAIResponsesModel` for either prefix); `provider-a:<id>` goes to an OpenAI-compatible provider, also as `/responses` requests, through `harness/replay/model_router.py`, started inside the trial (it strips the `metadata` field that provider adds, as in the original run).

### Kitaru recording inside the trial

The pinned Kitaru (0.27.2+dev at 0217140c) cannot record to a file: `KitaruAgent` always writes through `KitaruAPIClient` to a server (three calls: create session, ingest node batches, finish session), and the server needs Postgres. What is missing for file recording is a client-side sink or exporter in the adapter (or a pluggable transport for `KitaruAPIClient`); a small server-less mode would also do.

So the runner starts `kitaru_sink.py` on 127.0.0.1 inside the sandbox: it answers those three calls with responses built and validated by Kitaru's own response models, and appends every request body unchanged to `requests.jsonl`. Nothing leaves the sandbox. The files sit in the agent log folder, which Harbor copies out with every trial (also after a timeout):

```
<trial>/agent/
  tau2-kitaru-agent.json      summary: arm, model, case, tokens, agent cost (Kitaru's estimate), termination, tools called
  tau2-kitaru-agent.txt       runner output
  kitaru/requests.jsonl       the recording: every request the adapter sent, in order
  kitaru/session.json         the session and its nodes as a server would store them
  tau3_runtime_state.json     the sidecar's conversation log (what the verifier graded)
```

To load the recordings into a Kitaru server afterwards (one session per trial, under an agent you register first): `KITARU_API_URL=... uv run --extra replay python harbor/scripts/upload_recordings.py <jobs-dir>/<job> --agent-id <uuid> [--agent-version-id <uuid>]`. Harbor grades a trial after the agent finishes, so the recording holds no grade; the script adds the verifier's reward to the session's final outputs as a `tau2` object (reward, tau2 task id, termination reason, `graded_by: harbor verifier`), the shape the original episode wrote. The original harness's `tau2-task-success` evaluator (`harness/replay/tau2_reward_evaluator.py`) then scores uploaded sessions like the original ones; a trial with no verifier reward (an infrastructure error) is uploaded ungraded and that evaluator counts it as failed. Uploading two trials into a Kitaru server worked on 2026-10-23 (before the grade was added, when both scored 0 in Kitaru); the grade itself is checked against the sink and a recording client (`tests/test_agent.py`, `tests/test_upload.py`), not yet against a real server.

Kitaru replays (experiments that rerun a recorded cohort through a Kitaru worker) are not ported: Harbor runs every arm fresh, which is what the original replays did in effect (each replay started the task from scratch, with passthrough tool policies). Kitaru is used here to record.

## What the generator changes in Harbor's adapter tasks

`generate_tasks.py` runs Harbor's `adapters/tau3-bench` (harbor 209a48a7, 2026-10-22) for the 40 test ids, then patches each task; every patch asserts the text it replaces, so a changed adapter fails the build instead of silently producing different tasks.

| change | why |
|---|---|
| both images install tau2-bench at 05736c2 (sparse fetch) instead of cloning the default branch at build time | the original run's commit; the adapter's tasks change whenever tau2-bench does |
| the agent's image drops tau2's Telecom task files (`tasks*.json`, `split_tasks.json`) | they list every task's expected actions; the grader reads its own copy from `/tests/config.json` |
| user simulator pinned in the compose file: gpt-4.1-2025-04-14, no reasoning setting, OpenAI directly | the original user simulator; the adapter defaults to GPT-5.2 with reasoning effort `low` |
| sidecar limits 100 steps, 10 tool errors | tau2's orchestrator defaults, used by the original run; the adapter's sidecar uses 200 |
| grader passes `communicate_scoring=SUBSTRING` to `evaluate_simulation` | tau2 made the argument required on 2026-10-19; without it the adapter's grader raises a TypeError on every attempt and scores it 0 (this affects the adapter as published, whose images clone tau2-bench's default branch). Substring scoring is what the original run used and needs no model |
| no API key in the verifier; no model settings in the main container | the grader never calls a model; agents bring their own keys |
| `test.sh` deletes `/logs/verifier/reward.*` first, and writes 0 if the evaluator crashes | a planted reward file can't stand, and a crash can't leave an attempt without a reward |
| agent timeout 1200 s; 2 CPUs and 4 GB per sandbox | the original episode timeout; the adapter asked for 4 CPUs, 8 GB, 3600 s |
| `solution/` rebuilt as `oracle.json` + `build_state.py` (the adapter's reference logic) with an alternative and shortcuts | for the four checks |
| task names `zenml/tau2-telecom-test-NN`, metadata with the tau2 task id, case, commits and user model | this set differs from the hub's tasks, so it is not named like them |

Regenerating gives byte-identical tasks: checked on 2026-10-22 with `python3 harbor/generate_tasks.py --out /tmp/regen` (standard library only) and `diff -r /tmp/regen harbor/tasks`. Without `--tau2-root`/`--adapter-root` it fetches both pinned sources into a temp folder (about 300 MB, under 10 s). After regenerating, refresh the digests in `dataset.toml` with `cd harbor && harbor add tasks --scan --to .`.

## Checks run

All free: no model and no simulated user (the sidecar starts but `start_conversation` is never called, so the user simulator never runs; the runs below had no OpenAI key at all).

**Offline tests** (`tests/`, 93 tests, about 90 s), run on 2026-10-22 in a Python 3.12 venv with tau2 at 05736c2, pydantic-ai-slim 2.51.0, kitaru and kitaru-pydantic-ai at 0217140c, fastmcp 4.1.3, mcp 2.3.0:

```bash
TAU2_BENCH_ROOT=/path/to/tau2-bench uv run --locked --extra replay --with pytest --with "pydantic-ai-slim[mcp]==2.51.0" --with fastmcp==4.1.3 pytest harbor/tests
```

(`/path/to/tau2-bench` is the sparse checkout from RERUN.md section 3 plus `git -C /path/to/tau2-bench sparse-checkout add /src/ /pyproject.toml /README.md /data/tau2/multilingual/en/`.) This exact `uv run` line was not run while writing (it needs uv to fetch tau2-bench from git, more disk than the machine had); the tests ran in an equivalent venv with the same versions. They were re-run on 2026-10-23 (93 passed) after the renumbering and the upload grade, with kitaru and kitaru-pydantic-ai from 8abc49e9, a later commit of the same Kitaru branch. They check, for every task: the reference scores 1, the alternative scores 1, every shortcut scores 0, a run that never started scores 0; that the 40 tasks share one grader and sidecar; `test.sh`'s reward rules; that the runner's policy equals tau2's; and, through the real sidecar code with a scripted customer and a scripted model playing the reference, that the runner's tool bridge reaches reward 1 on two tasks and that the Kitaru recording holds one completed session with the expected LLM and tool nodes (and survives `upload_recordings.py`, which adds the verifier's grade that the Kitaru evaluator then reads); and that task NN is the original run's case NN.

**The four checks through Harbor on Modal** (`scripts/verify_tasks.py`, 2026-10-22, harbor 0.24.0, Modal sandboxes; run on dataset version 0.1.0, whose tasks have the same contents as 0.2.0 under different numbers):

| check | per task | result |
|---|---|---|
| oracle (`solution/solve.sh`, the reference) scores 1 | 5 attempts | 40/40 tasks pass. 198 of 200 attempts scored 1; 2 (tasks 32, 34) were infrastructure errors (Docker build failed inside the sandbox) and both tasks then passed 5/5 on a rerun |
| `nop` scores 0 | 1 | 40/40 score 0 |
| every shortcut scores 0: `do_nothing` (all 40), `transfer_now` (28 tasks whose answer is not a transfer), `account_side_only` (19 tasks that need both account and device fixes) | 1 each | 87/87 score 0. Two attempts (tasks 02, 08, `transfer_now`) first hit infrastructure errors (a Docker build failure, a Docker Hub 429) and scored 0 on a rerun |
| alternative `rechecks` scores 1: the agent looks the customer up, the customer re-checks the status bar after every device change, both sides talk, the customer ends the call (`user_stop`) | 1 | 40/40 score 1 |

Command (free of model spend; about 70 minutes at `-n 8`, 1.4 minutes per trial, most of it building the two images):

```bash
cd benchmarks/tau2-telecom && env -u OPENAI_API_KEY HARBOR_TELEMETRY=off python3 harbor/scripts/verify_tasks.py --jobs-dir /tmp/tau2-verify -e modal -n 8
```

**The agent's infrastructure, without a model** (`configs/arms/dry-run.yaml`): install in the sandbox, MCP connection to the sidecar (13 tool schemas), the Kitaru recording collected with the trial, grading (0). One trial, about 2 minutes:

```bash
cd benchmarks/tau2-telecom && env -u OPENAI_API_KEY PYTHONPATH=harbor/agent HARBOR_TELEMETRY=off harbor run -y -c harbor/configs/job.yaml -c harbor/configs/arms/dry-run.yaml -p harbor/tasks -i 'telecom-test-05' -o /tmp/tau2-jobs --job-name dry-run-1
```

Spend for everything above (2026-10-22): **$0 of model API** (no key was set) and about **$4 of Modal** (about 9.5 sandbox-hours at roughly $0.38 per sandbox-hour, read off Modal's hourly bill for the app: $0.99 for the first 20 minutes of checks; the rest of the bill was not complete when this was written). Infrastructure errors: 4 of 367 check trials, all at image build, none in grading.

## Paid runs (not run)

Setup once: `uv tool install "harbor[modal]==0.24.0"`, Modal credentials (`modal token new`, or `MODAL_TOKEN_ID`/`MODAL_TOKEN_SECRET`), and a git-ignored `.env` in `benchmarks/tau2-telecom/` with `OPENAI_API_KEY` (agent arms on OpenAI and the gpt-4.1 user simulator in every arm) and, for `provider-a:` arms, `OPENAI_COMPAT_BASE_URL_PROVIDER_A` (ending in `/v1`) and `OPENAI_COMPAT_API_KEY_PROVIDER_A`. Harbor itself runs locally and downloads results; sandboxes run on Modal under the app `tau2-telecom-harbor`.

**First comparison: GPT-5.2 baseline, GPT-5.2 rerun (noise floor), GLM-5.3, Qwen3.8 27B and GPT-5.6 Sol, one attempt per task, all five arms in one job:**

```bash
cd /path/to/agent-benchmarks/benchmarks/tau2-telecom && export HARBOR_TELEMETRY=off PYTHONPATH=harbor/agent; J=tau2-first-comparison-1; harbor run -y --env-file .env -c harbor/configs/job.yaml -c harbor/configs/arms/baseline.yaml -c harbor/configs/arms/rerun.yaml -c harbor/configs/arms/glm-5.3.yaml -c harbor/configs/arms/qwen3.8-27b.yaml -c harbor/configs/arms/gpt-5.6-sol.yaml -k 1 -o ~/tau2-harbor-jobs --job-name $J; python3 harbor/scripts/summarize.py ~/tau2-harbor-jobs/$J --json ~/tau2-harbor-jobs/$J-summary.json | tee ~/tau2-harbor-jobs/$J-summary.md
```

Expected cost about **$40**: about $33 of model spend at the original run's per-arm spend (agent + gpt-4.1 user simulator, USD: baseline 2.35 + 2.71, rerun 2.67 + 3.08, GLM-5.3 8.07 + 2.40, Qwen3.8 27B 3.27 + 2.26, GPT-5.6 Sol 4.06 + 2.34; the two open-weight agent costs are tokens x unverified list prices), plus about $7 of Modal (200 trials of roughly 5-6 sandbox-minutes each at about $0.38 per sandbox-hour: 2 minutes to build the two images and install the agent, measured, then the episode, estimated). Expected time about 2.5 hours at the default 8 concurrent trials, about 1.5 hours with `-n 16`. Pulling `python:3.12-slim` in every sandbox can hit Docker Hub's rate limit at high concurrency; add `-r 1` to retry trials that fail that way (they are infrastructure errors, not wrong answers). Every extra attempt (`-k`) adds the same again. Before the full run, a 2-task pilot of the same command with `-p harbor/tasks -i 'telecom-test-0[01]'` and `J=tau2-pilot-1` costs about $1 (`-i` filters on task folder names and needs `-p`).

Other arms: add `-c harbor/configs/arms/<arm>.yaml` for `prompt-rule`, `gpt-5.6-luna`, `gpt-5.4-mini`, `kimi-k3`, `deepseek-v4.1-flash` (original per-arm spend in RERUN.md section 7). Keep the baseline in the same job as the arms it is compared with. Use `-k 3` or more for anything but large gaps (the summary then adds pass^k); infrastructure errors (a trial with an exception and no reward) are counted apart from failures, and `harbor job resume -p ~/tau2-harbor-jobs/$J` (after exporting the `.env` variables and `PYTHONPATH=harbor/agent`) reruns unfinished trials, plus errored ones with `-f <exception type>`. After an interrupted run, stop leftover sandboxes: `modal app stop -y tau2-telecom-harbor` (sandboxes also end on their own after an hour).

## How the results map to the published numbers

`summarize.py` prints the same columns as the README's Part B table (solved / n, Wilson 95% interval, paired difference against the baseline with a 95% bootstrap interval over tasks, tasks gained / lost), plus infrastructure errors and the user simulator's cost. The published Part B numbers for these arms: baseline 27/40, rerun 27/40, GLM-5.3 39/40, Qwen3.8 27B 36/40, GPT-5.6 Sol 33/40.

Expect differences, for these reasons:

- **Per-task comparisons.** Since dataset version 0.2.0, task `telecom-test-NN` is the original run's case NN. Version 0.1.0 numbered tasks in `split_tasks.json` order, so no number matched; compare any 0.1.0 results with the original by `tau2_task_id` (in `tasks/index.json` and each trial's `task.toml`), not by number.
- **Noise.** GPT-5.2 rerun unchanged moved 6 tasks each way on 40 tasks (interval -17.5 to +17.5 points). A Harbor run landing within that of a published number agrees with it; one attempt per task cannot tell arms apart that are closer than that.
- **One agent version for every arm.** The original baseline ran agent version 1 (OpenAI direct), the rerun and model arms version 3 (through the router), the prompt arm version 2. Here every arm runs the same code; only `provider-a:` models go through the router. That removes a confound the original had, so the baseline-vs-rerun comparison is cleaner, not identical.
- **The conversation loop is the sidecar's, not tau2's Orchestrator.** Same environment, user simulator and grader code from the same tau2 commit, but Harbor's sidecar reimplements the turn loop (step and error counting, the stop rules). Small differences in when an episode hits the 100-step limit are possible.
- **Fresh episodes, no Kitaru replay.** The original arms were Kitaru replays of the baseline cohort; each replay restarted the task from scratch with passthrough tools, as here. Kitaru-specific replay behavior (tool policies, recorded inputs) was not used then and is not available now.
- **Costs.** Agent cost is Kitaru's estimate from its bundled price catalog (empty for the open-weight models, as in the original); user simulator cost is tau2's per-message cost. Neither is a bill.
- Not comparable with Harbor's published tau3-bench numbers (all 114 Telecom tasks, GPT-5.2 as the user, another agent) or with Part A.

## Limits and footguns

- **The graded log is writable from the agent's container.** The sidecar writes `/logs/agent/tau3_runtime_state.json` to a folder `main` shares (the adapter's oracle relies on it), so an agent with a shell could write a passing log. This agent can't: its model has only the MCP tools above, no shell or file access. Don't compare shell agents (codex, claude-code, terminus) on this set without first moving the log out of the agent's reach.
- **The sidecar's control tools** (`configure_run` can change the user simulator's settings, `record_termination` the ending) are reachable by any agent that lists the server's tools; this agent doesn't offer them to its model.
- **The simulated user is a model.** gpt-4.1 answers vary between runs (no seed is set, as in the original), which is part of the noise above.
- **Disk and images.** Each trial builds its two images inside the Modal sandbox (no registry or cache), about 1.5 minutes; that is in the time estimates.
- The agent's install pulls Kitaru from GitHub at the pinned commit and PyPI packages at the original run's versions (the benchmark's `pyproject.toml` constraints, plus `fastmcp-slim` 4.1.3 and `mcp` 2.3.0 for the MCP client).
