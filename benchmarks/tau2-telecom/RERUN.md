# Rerun: tau2-bench Telecom (public traces and Kitaru replays)

All commands run from `benchmarks/tau2-telecom/` unless they say otherwise. Sections 3-5 were run while writing this file (verified on 2026-10-22, Linux x86_64, uv 0.11.32, CPython 3.12.3); sections 6-7 cost money and were not re-run.

## 1. Prerequisites

- Linux or macOS, Python 3.12 (the project pins `>=3.12,<3.13`), [uv](https://docs.astral.sh/uv/), git.
- About 250 MB of disk for the public traces, about 100 MB for a sparse tau2-bench checkout (section 3), about 1 GB for the full environment with the replay extras.
- Paid steps only: Docker (for a local Kitaru server), an OpenAI account, and an account with an OpenAI-compatible provider serving the four open-weight models (`provider-a`).

## 2. Credentials

None of the free steps (3-5) needs a credential. Names are listed in `.env.example`.

| variable | used for | steps |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI agent models, GPT-5.2 step-check reference, tau2's gpt-4.1 user simulator | 6, 7 |
| `OPENAI_COMPAT_BASE_URL_PROVIDER_A` | base URL (ending in `/v1`) of the OpenAI-compatible provider for Qwen3.8 27B, Kimi K3, GLM-5.3, DeepSeek V4.1 Flash | 6, 7 (step check, router) |
| `OPENAI_COMPAT_API_KEY_PROVIDER_A` | key for that provider | 6, 7 |
| `KITARU_API_URL`, `KITARU_API_KEY` | the Kitaru server (key only when its auth scheme is `local`) | 6, 7 |
| `TAU2_DATA_DIR` | tau2-bench's `data/` directory | 5 (harness check), 6, 7 |
| `TAU2_AGENT_VERSION_ID` | Kitaru agent version that `run_baseline.py` records against | 7 |
| `TAU2_KITARU_AGENT_ID` | Kitaru agent id that `collect_replays.py` reads | 7 |

## 3. Install

```bash
uv sync --locked                                   # base: pyarrow only; enough for sections 4-5 except the harness check
```

Verified on 2026-10-22: installs `pyarrow==22.0.0` in about 4 s.

The replay and step-check code needs the extras, which pull Kitaru and tau2 from git at pinned commits (see `pyproject.toml`):

```bash
uv sync --locked --extra replay --extra step-check
```

Verified on 2026-10-22: resolves 93 packages; kitaru 0.27.2+dev, kitaru-pydantic-ai 0.3.1 and kitaru-model-swap 0.1.0 from zenml-io/kitaru at 0217140c9bd6fc1b0569abefbaea30be20a6fde4, tau2 2.0.0 from sierra-research/tau2-bench at 05736c27219b769d0be507574dd3135010916644, pydantic-ai-slim 2.51.0, openai 3.36.1. Every third-party version is the same as in the original run's lockfile (`[tool.uv] constraint-dependencies` pins them).

tau2 reads its task data from a checkout, not from the installed package. Only the Telecom domain is needed:

```bash
git clone --filter=blob:none --no-checkout https://github.com/sierra-research/tau2-bench /path/to/tau2-bench
git -C /path/to/tau2-bench sparse-checkout set --no-cone /data/tau2/domains/telecom/
git -C /path/to/tau2-bench checkout 05736c27219b769d0be507574dd3135010916644
export TAU2_DATA_DIR=/path/to/tau2-bench/data
```

Verified on 2026-10-22 (93 MB). A full clone is about 1.4 GB.

## 4. Get the data

```bash
uv run python scripts/fetch_data.py
sha256sum -c scripts/data.sha256
```

Downloads the 9 shards of [Exgentic/agent-llm-traces-v2](https://huggingface.co/datasets/Exgentic/agent-llm-traces-v2) at revision 4b8ad4ab198438e5a170f9171c19c6a2cf7c1814 into `data/` (git-ignored), about 232 MB. **License: none declared** on the dataset card or repository metadata (checked 2026-10-22), so the data is used locally and is not redistributed here. Verified on 2026-10-22: 13 s, all 9 checksums `OK`.

tau2-bench (section 3) is MIT licensed.

## 5. Free checks

**Rebuild Part A** (public traces and step check) from the fetched shards and the committed step-check rows:

```bash
uv run python scripts/build_tau2_public.py --out /tmp/tau2-public.json
cmp /tmp/tau2-public.json results/tau2-telecom-public-traces.json && echo identical
```

Expected: `wrote /tmp/tau2-public.json` then `identical`. Verified on 2026-10-22 (13 s). Without `--out` it overwrites `results/tau2-telecom-public-traces.json`. The build also recomputes every step-check rate from `results/runs/step_check/*/calls.jsonl` and checks it against the analyzer's `report.json`; the result is recorded in the output (`replays_and_step_checks[0].recompute_check`: "rates recomputed from calls.jsonl match ...").

**Rebuild Part B** (live replays) from the committed per-episode rows:

```bash
uv run python scripts/build_tau2_replay.py --out /tmp/tau2-replay.json
cmp /tmp/tau2-replay.json results/tau2-telecom-kitaru-replay.json && echo identical
```

Expected: `identical`. Verified on 2026-10-22 (3 s). The build also compares the run log `results/runs/replay/baseline.jsonl` with the rewards stored in Kitaru and adds any mismatch to `inconsistencies` (there are none).

**Check the harness environment offline** (imports every harness module, loads tau2's Telecom test split, checks each committed row's task id against the task at that case index):

```bash
TAU2_DATA_DIR=/path/to/tau2-bench/data uv run --locked --extra replay --extra step-check python scripts/check_harness.py
```

Expected output (verified on 2026-10-22):

```
test tasks: 40 | agent tools: 13
replay rows: 400 | task id mismatches: 0
baseline log rows: 40 | task id mismatches: 0
kitaru 0.27.2+dev
kitaru-pydantic-ai 0.3.1
kitaru-model-swap 0.1.0
tau2 2.0.0
pydantic-ai-slim 2.51.0
openai 3.36.1
genai-prices 0.1.13
```

## 6. Smoke test (paid, not re-run)

**Kitaru server.** The run used Kitaru from an unreleased branch, so build the server from that commit instead of `kitaru login --local` (which pulls the published image for the CLI's version, and no image exists for `0.27.2+dev`). Not verified while writing this file.

```bash
git clone https://github.com/zenml-io/kitaru /path/to/kitaru
git -C /path/to/kitaru checkout 0217140c9bd6fc1b0569abefbaea30be20a6fde4
cd /path/to/kitaru
docker compose up -d                 # Postgres 16 (host port 5433) + the server built from source (port 8000), auth scheme `none`
curl http://localhost:8000/health    # wait until healthy; database migrations run at startup
cd -                                 # back to benchmarks/tau2-telecom
export KITARU_API_URL=http://localhost:8000
```

The shipped Compose file is for a laptop only (no auth, dev keys). `docker compose down -v` deletes the database.

**Workers.** Nothing runs on the server; workers run the agent and the evaluator. Start them from this directory, in the environment with the extras, with the model credentials exported:

```bash
uv run --extra replay kitaru worker start --claim evaluator &
uv run --extra replay kitaru worker start --claim agent --concurrency 8 &
```

On this Kitaru commit, workers must be restarted at least hourly (zenml-io/kitaru#1339). The worker concurrency the original run used was not recorded; `run_baseline.py` defaults to 8 parallel episodes.

**Step check smoke** (Part A): needs the Exgentic runs imported into Kitaru, which used a private script importer that is not published (one Kitaru session per Exgentic run, one `llm_call` node per OTel chat span; GPT-5.2 runs of the `tool_calling` harness on `tau2_telecom`). With an equivalent import:

```bash
uv run --extra step-check python harness/step_check/swap_run.py --import-id <IMPORT_ID> --dry-run
uv run --extra step-check python harness/step_check/swap_run.py --import-id <IMPORT_ID> --max-calls 20 --cap 2 --out harness/step_check/out-smoke
```

The dry run sends nothing. 20 calls x 8 candidates should cost about $1 (the full 160-call batch cost $8.30271325).

**Replay smoke** (Part B): register the agent (step 1 of section 7) and record two episodes:

```bash
TAU2_AGENT_VERSION_ID=<v1> uv run --extra replay python harness/replay/run_baseline.py --tag smoke --cases 0-1
```

Rows land in `harness/replay/results/smoke.jsonl`; success is a row per case with `tau2.reward` set (0.0 or 1.0) and `run_error: null`. Cost: about $0.13 per GPT-5.2 episode (the baseline arm's $5.063571 over 40 episodes, agent plus user simulator).

## 7. Full rerun (paid, not re-run)

Part B can also run as a Harbor job, one config file per arm, without a Kitaru server: see [harbor/README.md](harbor/README.md). The steps below are the original Kitaru path.

Wall times below come from the Kitaru session ids (UUIDv7, which encode each session's start time): they are the spread of session start times per arm, not exact durations. Costs are from `results/costs/replay.json` and the export (`agent_cost_usd`, `user_simulator_cost_usd`).

### Part A: step check

Two batches against the same 160 sampled calls (the analyzer's sample is deterministic):

```bash
uv run --extra step-check python harness/step_check/swap_run.py --import-id <IMPORT_ID> --max-calls 160 --cap 20 \
    --candidates harness/step_check/candidates.json --out harness/step_check/out
uv run --extra step-check python harness/step_check/swap_run.py --import-id <IMPORT_ID> --max-calls 160 --cap 8 \
    --candidates harness/step_check/candidates_responses.json --out harness/step_check/out_responses
```

Batch 1: 8 candidates, $8.30271325 (GPT-5.6 Sol and Luna failed every call there; Chat Completions rejects function tools with reasoning for them). Batch 2: those two through the Responses API, $0.99819070. Wall time was not logged; the summed call latency is 33.1 and 10.3 minutes at concurrency 16, so a few minutes each. Then strip the outputs before publishing (`python scripts/strip_step_check.py harness/step_check/out results/runs/step_check/out`, same for `out_responses`).

### Part B: record and replay

1. Register the agent and its three versions (one `kitaru agent register` per version; each call adds a version):

   ```bash
   kitaru agent register tau2-telecom-live --command "uv run --quiet --extra replay python -m tau2_kitaru_agent.episode" \
       --working-dir "$PWD/harness/replay" --env TAU2_DATA_DIR=$TAU2_DATA_DIR                              # version 1
   kitaru agent register tau2-telecom-live --command "uv run --quiet --extra replay python -m tau2_kitaru_agent.episode" \
       --working-dir "$PWD/harness/replay" --env TAU2_DATA_DIR=$TAU2_DATA_DIR \
       --env TAU2_INSTRUCTION_ADDENDUM="$(cat harness/replay/prompt_addendum.txt)"                         # version 2: prompt audit
   kitaru agent register tau2-telecom-live --command "uv run --quiet --extra replay python -m tau2_kitaru_agent.episode" \
       --working-dir "$PWD/harness/replay" --env TAU2_DATA_DIR=$TAU2_DATA_DIR \
       --env OPENAI_BASE_URL=http://127.0.0.1:8766/v1                                                      # version 3: routed
   ```

   Version 3 needs the router running on the worker host: `uv run python harness/replay/model_router.py --port 8766` (with `OPENAI_API_KEY` and the two `PROVIDER_A` variables).
2. Register the evaluator: `kitaru evaluator register tau2-task-success --script harness/replay/tau2_reward_evaluator.py --entrypoint evaluate --agent-id <agent id>`.
3. Record the baseline (40 episodes, GPT-5.2 direct, agent version 1): `TAU2_AGENT_VERSION_ID=<v1> uv run --extra replay python harness/replay/run_baseline.py --tag baseline`. Cost $5.063571 (agent $2.353543, user simulator $2.710028); about 4 minutes of session starts at concurrency 8. A rerun resumes: cases already in `harness/replay/results/baseline.jsonl` are skipped.
4. Make a cohort of the 40 baseline sessions: `kitaru cohort create tau2-telecom-baseline --agent tau2-telecom-live --sessions-file <file with the 40 session ids>`.
5. Per arm, create an experiment and start a run (arms ran one after another, in the order below):

   ```bash
   kitaru experiment create tau2-<arm> --agent tau2-telecom-live --evaluator tau2-task-success@1 \
       [--override '{"model":"<override>"}'] --tool-policy '{"default":{"type":"passthrough"}}'
   kitaru experiment run start tau2-<arm> --cohort-version <cohort version id> --agent tau2-telecom-live@<version>
   ```

   | arm (`tau2-<arm>`) | override `model` | agent version | agent cost (USD) | user simulator (USD) | session starts spread over |
   |---|---|---|---|---|---|
   | `kimi-k3` | `openai:moonshotai/Kimi-K3` | 3 | 20.641818 (estimate) | 2.829056 | 3 min |
   | `prompt-escalation-rule` | none | 2 | 2.614121 | 2.762436 | 3 min |
   | `noise_gpt-5_2` | none | 3 | 2.667193 | 3.083490 | 2 min |
   | `gpt-5_6-sol` | `openai-responses:gpt-5.6-sol` | 3 | 4.063544 | 2.339102 | 4 min |
   | `gpt-5_6-luna` | `openai-responses:gpt-5.6-luna` | 3 | 0.174282 | 1.357334 | 2 min |
   | `gpt-5_4-mini` | `openai-responses:gpt-5.4-mini` | 3 | 0.693430 | 1.793804 | 2 min |
   | `qwen3_8-27b` | `openai:Qwen/Qwen3.8-27B` | 3 | 3.271614 (estimate) | 2.258660 | 2 min |
   | `glm-5_3` | `openai:zai-org/GLM-5.3` | 3 | 8.065542 (estimate) | 2.397530 | 11 min |
   | `deepseek-v4_1-flash` | `openai:deepseek-ai/DeepSeek-V4.1-Flash` | 3 | 2.145730 (estimate) | 2.627272 | 2 min |

   "Estimate" = tokens x unverified list price; Kitaru could not price these models. The whole replay phase (9 arms) started its first session at 13:56 and its last at 14:28 UTC on 2026-10-22 (end times were not recorded). Expect roughly $71 for all of Part B including the baseline ($37.33 recorded plus $34.12 estimated open-weight agent cost). Kitaru retries a replay interrupted by a server restart; each task's final replay counts.
6. Collect one row per episode: `TAU2_KITARU_AGENT_ID=<agent id> uv run --extra replay python harness/replay/collect_replays.py` (reads only; writes `harness/replay/results/replays.jsonl`). It picks up experiments whose name starts with `tau2-` and baseline sessions named `tau2 telecom case <n> baseline`.

## 8. Compare with the published results

```bash
uv run python scripts/build_tau2_replay.py --runs-dir harness/replay/results --out /tmp/tau2-replay-new.json
uv run python scripts/build_tau2_public.py --step-check-dir harness/step_check --out /tmp/tau2-public-new.json
```

`build_tau2_replay.py` needs both `replays.jsonl` and `baseline.jsonl` in `--runs-dir` (the baseline log is the one `run_baseline.py --tag baseline` wrote). Compare `results.*` with the committed files. How to read differences:

- The noise floor on 40 tasks is wide: GPT-5.2 rerun unchanged gained 6 tasks and lost 6 (paired difference 0.0, 95% interval -17.5 to +17.5 points). A new run of any arm landing within about +/-17.5 points of the published accuracy is consistent with it.
- Compare arms with the `paired_vs` and `paired_vs_noise` fields (same tasks, bootstrap interval), not with the separate Wilson intervals.
- The step check's paired intervals cluster over only 19 recorded runs; expect them to move by a few points on a new sample.

## 9. Troubleshooting

- **PydanticAI rejects open-weight responses** (validation error on `metadata`): the provider adds `metadata.weight_versions`; run the agent through `model_router.py` (agent version 3), which strips it.
- **GPT-5.6 Sol/Luna fail every call on `/chat/completions`** ("Function tools with reasoning_effort are not supported"): use the Responses API (`"api": "responses"` in the step-check candidate, `openai-responses:` prefix for the agent override).
- **OpenAI HTTP 400 "string too long" on 19 of 160 step-check calls**: some recorded tool-call ids exceed OpenAI's 64-character limit. Those calls are excluded for every OpenAI candidate; there is no fix in this run.
- **Step check as a Kitaru worker task loses its result**: the worker discards task results over 1 MB, which a full report exceeds. Run `swap_run.py` in-process instead (it writes to disk).
- **Open-weight sessions show cost 0**: Kitaru's session rollup counts unpriced calls as 0; the build recomputes these from tokens.
- **Workers stop claiming tasks after about an hour**: restart them (zenml-io/kitaru#1339).
- **Disk fills during the tau2-bench clone**: the full repository with voice data is about 1.4 GB; use the sparse checkout in section 3.

## Changes from the original run

Code and data were moved from `benchmarks/tau2-telecom-public/` (plus `benchmarks-export/scripts/`) of the private research repository. Behavior is unchanged except where noted.

- **Layout.** Harness code in `harness/replay/` and `harness/step_check/`; build scripts, `fetch_data.py` and the stats helper in `scripts/`; result rows in `results/runs/`; cost files in `results/costs/` (`public_traces_step_check.json` was `costs.json`, `replay.json` was `replay/costs.json`). The build scripts read from and write to this directory instead of the research repository root, and gained `--out`, `--runs-dir` and `--step-check-dir` options (defaults reproduce the committed files).
- **Stats helper.** `paired_delta` (and `per_scenario`) copied unchanged from SwapBench's `swapbench/stats.py` into `scripts/stats.py`.
- **Commit field.** `meta.harness_git_commit` is now a constant: the original commit. For Part A this changes the export from `null` ("not committed yet", true when the export was built) to c2bb92e93b865db6ae686adff8bc0281a79c4d31. Text fields such as `code_location` keep the original paths as provenance.
- **Provider names.** The open-weight provider is `provider-a` everywhere: `models[*].provider_private` in both result files, two strings in `results/costs/replay.json`, `candidates.json` (base URL now `${OPENAI_COMPAT_BASE_URL_PROVIDER_A}`, key `OPENAI_COMPAT_API_KEY_PROVIDER_A`; `swap_run.py` expands environment variables in `base_url`), and `model_router.py` (base URL and key from `OPENAI_COMPAT_*_PROVIDER_A` instead of hard-coded). No number changed.
- **Step-check rows stripped** (dataset has no license): `calls.jsonl` keeps `recorded_tools` (tool names) instead of `recorded` (names and arguments) and drops recorded text and reply text; `report.json` drops `disagreements` and `failure_examples`; `insights.json` is not included. The build accepts either `recorded_tools` or `recorded`, so a fresh `swap_run.py` output still works. The rebuilt tables are identical.
- **Data pin.** `fetch_data.py` downloads a fixed dataset revision (the one `main` pointed to on 2026-10-22, unchanged since 2026-07-01) instead of `main`, and `scripts/data.sha256` checks the files.
- **Dependencies.** One `pyproject.toml` with `replay` and `step-check` extras; Kitaru, its plugins and tau2 come from git at the pinned commits instead of local checkouts. The step check originally ran in the Kitaru checkout's own environment with a locally built kitaru-model-swap wheel; here it shares the replay environment (same kitaru commit). Third-party versions match the original replay lockfile exactly.
- **Agent command.** The registered command adds `--extra replay` (`uv run --quiet --extra replay python -m tau2_kitaru_agent.episode`) because the project now has extras.
- **collect_replays.py** reads the agent id from `TAU2_KITARU_AGENT_ID` (the original hard-coded id is the default).
- **New files:** `scripts/strip_step_check.py` (how the step-check rows were stripped), `scripts/check_harness.py` (offline environment check), `scripts/data.sha256`.
