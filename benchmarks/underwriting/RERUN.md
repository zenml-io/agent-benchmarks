# Rerunning the underwriting benchmark

Every command below runs from this directory (`benchmarks/underwriting`). Sections 3-5 are free and were run on 2026-10-22 from a clean copy of this directory, in a fresh uv virtualenv; each says "verified on 2026-10-22". Sections 6-7 cost money and were **not re-run**. Their costs come from the original spend log and their wall times from the row timestamps and logs of the original run.

## 1. Prerequisites

- Linux or macOS, Python 3.11+ (verified with 3.12), [uv](https://docs.astral.sh/uv/) (verified with 0.11.32), `curl`, `bash`.
- Paid steps: API accounts for Anthropic and OpenAI, plus an OpenAI-compatible endpoint serving the seven open-weight models (DeepSeek V4 Pro `deepseek-ai/DeepSeek-V4-Pro-0813`, DeepSeek V4.1 Flash, GLM 5.3, GLM 5.3 Flash, gpt-oss-120b, Qwen3.8 27B, MiniMax-M3). The original run used one commercial inference provider, labelled `provider-a`.
- Step-level screen only: a Jev judge key and a checkout of [zenml-io/kitaru](https://github.com/zenml-io/kitaru) branch `feature/model-swap-analyzer` (reference commit `0217140`), with Python 3.13.
- Kitaru full replay only: the same Kitaru checkout, PostgreSQL 16, and enough disk for a small database (under 100 MB).

## 2. Credentials

All are read from the environment; names are in `.env.example`. Never commit values.

| Variable | Used for | Needed by |
|---|---|---|
| `EVAL_ANTHROPIC_API_KEY` | Claude models: agent, simulated underwriter (Haiku 5.5), judge (Haiku 5.5), prompt optimizer (Opus 5.5) | every paid step |
| `OPENAI_API_KEY` | GPT-6 models: agent, judges (GPT-6 Luna, GPT-6.1 Sol tie-break) | every paid step |
| `OPENAI_COMPAT_BASE_URL_PROVIDER_A` | base URL (`https://.../v1`) of the OpenAI-compatible endpoint for models keyed `*@provider-a` | runs of open-weight models |
| `OPENAI_COMPAT_API_KEY_PROVIDER_A` | its key (sent as `Authorization: Bearer ...`) | runs of open-weight models |
| `JEV_API_KEY` | Jev, the step judge inside the Kitaru model-swap analyzer | step-level screen |
| `KVENV` | path of the virtualenv with Kitaru and the model-swap plugin | step-level screen |
| `KITARU_API_URL`, `UW_AGENT_ID`, `UW_HARNESS` | Kitaru server URL, the registered agent's id, absolute path of `harness/` on the worker | Kitaru full replay |

## 3. Install

```bash
uv venv --python 3.12 .venv
uv sync            # pandas 2.3.3, pyarrow 21.0.0, openpyxl 3.1.5 (pinned in uv.lock)
```

Verified on 2026-10-22. The harness itself uses only the standard library; the three packages are for rebuilding the environment and for `harness/validate_judge.py`.

## 4. Get the data

```bash
PYTHON=.venv/bin/python bash scripts/fetch_data.sh
```

Verified on 2026-10-22 (31 s). It downloads:
- [snorkelai/Multi-Turn-Insurance-Underwriting](https://huggingface.co/datasets/snorkelai/Multi-Turn-Insurance-Underwriting) (`data/train-00000-of-00001.parquet`, 380 traces; `insurance_underwriting_train_data.parquet`) and [snorkelai/Multi-Turn-Insurance-Underwriting-Code-Gen](https://huggingface.co/datasets/snorkelai/Multi-Turn-Insurance-Underwriting-Code-Gen), Apache-2.0, into `data_raw/`;
- four US Census Bureau NAICS files (2022 codes and descriptions, 2022→2017 and 2012→2017 concordances; public domain) into `env/census/`.

It then rebuilds the environment: `env/extract.py` (tasks, observed appetite and SBA rows, guidelines), `env/build_db.py` (SQLite database `env/insurance.db`, guidelines `env/guidelines.txt`), and `env/oracle.py` (re-derives each reference answer; keeps the cases it reproduces in `env/tasks.json`).

Expected output (last lines):

```text
observed appetite rows reproduced: 17779/17779
kept 252 of 380
  ...
  dropped codegen: environment cannot resolve 46
  dropped main: company NAICS unknown 26
  dropped codegen: reference unsupported 23
  dropped codegen: company NAICS unknown 18
  dropped main: environment cannot resolve 7
  dropped codegen: oracle disagrees 6
  dropped main: reference unsupported 2
```

The files are byte-identical to the original run's. SHA-256 on 2026-10-22:

```text
55833ec064222f8a98a80af8e9726ad98f8540f8173be97343e50bac3fb37c83  data_raw/data/train-00000-of-00001.parquet
2e9683fd7e73de0b154071c625dc36d854b5d6bf8584f17cd8153ecbda6e6738  data_raw/codegen/train.parquet
c9c7a12eca705c5b6f000ae1cf0aaa3ce564a5aeea848fbe4a20c1db095d9749  data_raw/insurance_underwriting_train_data.parquet
9a04465cd43916dced0c1fca36feb9e96efbce7e1cc53238ba0d2040e22feee9  env/tasks.json
f86f378aa0d71f3c0ce82c6457506a1f84ca37cb30ed1784fb63895f762fdfe1  env/extracted.json
c9b76b825522ec4bd1813b24edaf6844ce27bab6df09dc8d343cc50d4d8a2874  env/guidelines.txt
e19c5858c21c1c774cc70c4d2e2e1b067091f068f82837bfe555b5c26d6bc755  env/insurance.db
```

If Hugging Face or the Census Bureau change these files, the hashes and possibly the kept set will change; compare before trusting a rerun.

## 5. Free checks

All verified on 2026-10-22, no model calls and no network.

```bash
.venv/bin/python scripts/make_split.py
```
Rebuilds the learning / held-out split from its rule (per question type, sort by `sha256("split:" + id)`, first third to learning). Expected: `learn: 84 ...`, `held: 168 ...`, `matches env/split.json`.

```bash
.venv/bin/python scripts/test_offline.py
```
Tools over the rebuilt database, the 200-row cap, read-only SQL, endpoint configuration, the underwriter prompt for all 252 cases, and the price table reproducing the stored agent cost of all 8,735 committed rows. Expected: `all offline checks passed`.

```bash
.venv/bin/python scripts/check_tables.py
```
Regenerates every published table from `results/runs/` and `results/tuned/runs/` in a temporary copy: `harness/report.py --ref opus-5.5` (first run), `harness/tuned_report.py` (held-out arms), `scripts/export.py` (the export), and the spend in the rows. Expected output: one known difference (GPT-6 Luna, see README Trust status), so it exits 1.

```text
[DIFFERS] first prompt, 252 cases: results/tables.md
    @@ -12 +12 @@
    -| gpt-6-luna | 86.5% (218/252) | 82%–90% | 0.17¢ | 0.19¢ | 48s | -10.7 [-15.1, -6.7] | api_error 1 |
    +| gpt-6-luna | 86.9% (219/252) | 82%–91% | 0.17¢ | 0.19¢ | 48s | -10.3 [-14.7, -6.3] | – |
    @@ -29 +29 @@
    -| gpt-6-luna | 93% (85) | 81% (72) | 92% (48) | 71% (17) | 100% (13) | 71% (17) |
    +| gpt-6-luna | 93% (85) | 82% (72) | 92% (48) | 71% (17) | 100% (13) | 71% (17) |
[same] held-out arms: results/tuned/summary.json
[same] export: results/underwriting.json
[same] spend, first run, all rows incl. superseded re-runs: rows $79.49, log $79.49
[same] spend, tuning rounds, tuned, effort, repeat + optimizer: rows $85.63, log $85.63
[same] spend, shared prompt: rows $47.38, log $47.38
[same] spend, self-judge regrade: rows $2.01, log $2.01
[same] spend, memorization probe: rows $1.43, log $1.43
```

`results/summary.json`, `results/tables.md`, `results/tuned/summary.json`, `results/tuned/tables.md` and `results/report.html` are the files as published. Running `harness/report.py` or `harness/tuned_report.py` directly overwrites them, and `report.py`'s intervals then depend on your filesystem's file order (README, inconsistency 2). The HTML report is `.venv/bin/python harness/build_report.py` after `harness/report.py --ref opus-5.5`.

## 6. Smoke test (paid, not re-run)

```bash
set -a; . ./.env; set +a
.venv/bin/python harness/run.py haiku-5.5 --arm smoke --n 6 --workers 6
.venv/bin/python harness/run.py glm-5.3-flash@provider-a --arm smoke --n 6 --workers 6
```

These are the first 6 cases in the fixed hash order, written to `results/tuned/runs/<model>__smoke.jsonl` (ignored by `tuned_report.py` and git), with transcripts in `results/tuned/transcripts/`. Cost: about $0.04 for Haiku 5.5 and $0.06 for GLM 5.3 Flash (from the original per-case spend) (agent + simulator + judges; the original Haiku smoke tests cost $0.10 for 2 × 6 cases plus simulator checks). Success: the script ends with `done: 6 tasks, success ...`; every row has `status: "finished"`, a `final_answer` starting with `FINAL ANSWER:`, and two or three `verdicts`. Compare per case with the same model's rows in `results/runs/`. With one run each, agreement on most of the 6 cases is the expected outcome, not all.

## 7. Full rerun (paid, not re-run)

Load keys first (`set -a; . ./.env; set +a`). Each command skips cases already in its output file, so an interrupted run resumes. Rows with `api_error`, `account_blocked` or `timeout` are re-run on the next invocation, and harness errors are excluded from every table. Costs are the original spend at list prices; wall times are the span of the original rows' timestamps (they include re-runs) at 6-8 workers.

| Step | Command | Output | Cost | Wall time |
|---|---|---|---|---|
| a. Judge validation (needs `data_raw/`) | `.venv/bin/python harness/validate_judge.py data_raw --n 160 --judges gpt-6.1-sol,haiku-5.5,gpt-6-luna` | `results/judge_validation.json` | $0.48 (two passes) | minutes |
| b. First prompt, 12 models × 252 cases | `bash scripts/run_all.sh opus-5.5 sonnet-5.5 haiku-5.5 gpt-6.1-sol gpt-6-luna deepseek-v4-pro@provider-a deepseek-v4.1-flash@provider-a glm-5.3@provider-a glm-5.3-flash@provider-a gpt-oss-120b@provider-a qwen3.8-27b@provider-a minimax-m3@provider-a` (sequential; run models in parallel to save time) | `results/runs/<model>.jsonl`, `results/transcripts/<model>/`, `logs/full_<model>.log` | $79.49 (per model $0.66 GPT-6 Luna to $20.00 GLM 5.3) | 13-77 min per model |
| c. Memorization probe | `.venv/bin/python harness/probe.py` | `results/probe.json` | $1.43 | minutes |
| d. Self-judge regrade (needs b) | `.venv/bin/python harness/regrade_self.py` | `results/regrade_self.json` | $2.01 | minutes |
| e. Per-model prompt tuning + effort + Sonnet repeat (needs b's transcripts) | `bash harness/run_tuned.sh` (7 hill-climbs on the learning split, then each best prompt once on held-out; 9 effort/repeat arms; all in parallel). GPT-6 Luna's hill-climb ran first: `.venv/bin/python harness/hillclimb.py gpt-6-luna --rounds 2` | `results/tuned/{prompts,hillclimb,runs}/`, `logs/tuned/` | $85.63 incl. optimizer $0.89 | about 30 min in parallel (3-18 min per arm) |
| f. Shared prompt (needs e's `results/tuned/prompts/sonnet-5.5/v1.txt`, committed) | `bash harness/run_shared.sh` | `results/tuned/runs/<model>__shared.jsonl` | $47.38 | about 20 min in parallel (6-18 min per model) |
| g. Tables | `.venv/bin/python harness/report.py --ref opus-5.5 && .venv/bin/python harness/tuned_report.py && .venv/bin/python harness/build_report.py && .venv/bin/python scripts/export.py` | `results/` | free | seconds |
| h. Step-level screen | see below | `replay/out/`, `replay/comparison.json` | $15.85 (+$0.36 grading); rerun on updated analyzer $15.62 | about 15 min per batch |
| i. Kitaru full replay | see below | Kitaru server, `kitaru_replay/results.json` | $9.11 (about $1.50 of it estimated) | about 1 h |

A fresh optimizer will write different prompts. To rerun only the held-out arms with the published prompts, skip the hill-climb and pass a committed prompt: `.venv/bin/python harness/run.py <model> --arm tuned --split held --prompt results/tuned/prompts/<model>/v<best_round>.txt --workers 8` (best round per model in `results/tuned/hillclimb/<model>.json`). Effort arms: `--arm effort-<level> --split held --effort <low|medium|high>`. The Sonnet repeat: `--arm repeat --split held`.

### Step-level screen (Kitaru model-swap analyzer)

The screen feeds the 252 recorded Sonnet 5.5 transcripts from step b (`results/transcripts/sonnet-5.5/`) to the analyzer's own code. Sessions are built in memory, so no Kitaru server is needed. It replays up to 250 recorded calls per candidate with Jev as the step judge, in two batches (the analyzer takes at most 8 candidates; Sonnet 5.5 is in both, and batch B's Sonnet is the noise floor).

```bash
git clone https://github.com/zenml-io/kitaru && git -C kitaru checkout 0217140
# not verified in this port; the original used an equivalent editable install
uv venv --python 3.13 kvenv && uv pip install --python kvenv/bin/python -e kitaru -e kitaru/plugins/packages/model-swap
export KVENV=$PWD/kvenv
bash replay/run_all.sh                       # writes replay/out/underwritingA, underwritingB; SUFFIX=2 tags a rerun
$KVENV/bin/python replay/analyze.py --grade  # grades candidate replies at Sonnet's final-answer steps (cached in replay/final_grades.json), writes replay/comparison.json
$KVENV/bin/python replay/jev_sound_step.py   # optional: reference-free Jev judging, replay/jev_sound_summary.json
```

The original run used the branch as it was on 2026-10-21 (kitaru 0.27.2+dev, plugin 0.1.0). Commit `0217140` is a day later, and its report's "Best for" picks differ (README, inconsistency 5). Spend cap is `--cap 25` per batch.

### Kitaru full replay

The original setup, reconstructed from its logs. The exact registration commands were not recorded, so the Kitaru CLI steps follow Kitaru's documentation for the same objects.

1. PostgreSQL 16 as a local cluster with its data directory **outside any temporary directory**, so a container or session restart does not lose the recordings. The original used `/var/lib/pgk/data` on port 5433, listening on 127.0.0.1. Mid-run, the cluster was not shut down cleanly and recovered on restart; the worker was then restarted.
   ```bash
   sudo -u postgres /usr/lib/postgresql/16/bin/initdb -D /var/lib/pgk/data
   sudo -u postgres /usr/lib/postgresql/16/bin/pg_ctl -D /var/lib/pgk/data -o "-p 5433 -k /tmp" -l /var/lib/pgk/log start
   sudo -u postgres createdb -p 5433 -h 127.0.0.1 kitaru
   ```
   (`docker compose up -d db` in the Kitaru checkout is an alternative; it uses a named volume.)
2. The Kitaru server from the checkout above, on 127.0.0.1:8300, with `KITARU_SERVER_DB_HOST=127.0.0.1`, the port, user, password and database name set to match (see the variables in the checkout's `docker-compose.yml`), and auth off for a local run. For example: `uv run --extra server uvicorn kitaru.server.api.main:app --factory --port 8300`. Then `export KITARU_API_URL=http://127.0.0.1:8300`.
3. Register the agent: command `python kitaru_replay/agent.py`, run from this directory with the benchmark's keys in the worker's environment (`kitaru agent register ...`, `kitaru agent version register ...`). Export its id as `UW_AGENT_ID`.
4. Record the 48 baseline cases with Sonnet 5.5. The cohort is the first 48 cases in `harness/run.py`'s hash order, listed in `kitaru_replay/cohort_tasks.json`. The original ran 6 batches of 8:
   `.venv/bin/python kitaru_replay/agent.py --record <8 comma-separated ids>` (one case at a time per process).
5. Register the evaluator `kitaru_replay/evaluator.py`, entrypoint `evaluate`, named `correct_decision`, with `UW_HARNESS=$PWD/harness` in the worker's environment. It uses the benchmark's own two judges plus tie-break.
6. Start a worker that claims agent, evaluator, importer and analyzer tasks (the original: `kitaru worker start`, concurrency 16).
7. For each candidate (`deepseek-v4-pro@provider-a`, `glm-5.3@provider-a`, `gpt-6-luna`, `haiku-5.5`), create an experiment on the 48-session cohort with override `{"model": {"sonnet-5.5": "<candidate>"}}` and the passthrough tool policy (the agent rejects any other: its tools are read-only queries on a fixed file). Start it with baselines evaluated.
8. `KITARU_API_URL=... $KVENV/bin/python kitaru_replay/compare.py` writes `kitaru_replay/results.json`.

### Spend log of the original run

| Date (UTC) | Item | USD | Running total |
|---|---|---|---|
| 2026-10-21 | Judge validation on Snorkel's labeled traces, two passes (`results/judge_validation.json` holds the second) | 0.48 | 0.48 |
| 2026-10-21 | Harness smoke tests: Haiku 5.5 on 6 cases, twice, plus simulator checks | 0.10 | 0.58 |
| 2026-10-21 | First pilot (40 cases × 4 models) before the FINAL ANSWER rule fix | 1.43 | 2.01 |
| 2026-10-21 | Full run: 252 cases × 12 models incl. the second pilot, empty-reply and API-error re-runs (`results/runs`) | 79.49 | 81.50 |
| 2026-10-21 | Superseded first-pass rows of cases re-run after the empty-turn nudge | 0.27 | 81.76 |
| 2026-10-21 | Memorization probe: 24 cases × 12 models, no tools (`results/probe.json`) | 1.43 | 83.19 |
| 2026-10-21 | Step-level screen through the Kitaru model-swap analyzer, two batches | 15.85 | 99.04 |
| 2026-10-21 | Grading candidate replies at Sonnet's final-answer steps, and Jev step judging (list-price estimate) | 0.36 | 99.40 |
| 2026-10-21 | Kitaru full replay: 48 Sonnet baselines plus 4 model swaps; agent calls 7.61 from Kitaru's session costs, simulator and grading about 1.50 (estimated) | 9.11 | 108.51 |
| 2026-10-21 | Self-judge regrade, Opus 5.5 breaking ties (`results/regrade_self.json`) | 2.01 | 110.52 |
| 2026-10-21 | Step-level screen rerun on the updated analyzer | 15.62 | 126.14 |
| 2026-10-21 | Prompt tuning on the 84 learning cases (optimizer Opus 5.5, $0.89), tuned prompts, 8 effort arms and a Sonnet repeat on the 168 held-out cases (`results/tuned`) | 85.63 | 211.77 |
| 2026-10-22 | Shared prompt on the other 11 models' held-out cases (`results/tuned/runs/*__shared`) | 47.38 | 259.15 |

## 8. Compare with the published results

```bash
.venv/bin/python harness/report.py --ref opus-5.5    # first run: results/tables.md, results/summary.json
.venv/bin/python harness/tuned_report.py             # held-out arms: results/tuned/tables.md, results/tuned/summary.json
.venv/bin/python scripts/export.py /tmp/uw.json      # the export, to diff against results/underwriting.json
```

Before a rerun, move the published rows aside, because the run scripts append to files that already exist. To compare one model, pair its new rows with `results/runs/<model>.jsonl` on the same cases. How to read differences:
- The measured noise floor is Sonnet 5.5 rerun unchanged: +2.4 pts [-3.6, +8.3] on 168 cases. Treat single-run differences under about 3 points as noise, and only intervals that exclude 0 as differences.
- Per-question-type numbers rest on 13-85 cases each; policy limits and deductibles (17 and 13 cases) swing by 6-8 points per case.
- Cost per correct decision moves with list prices. Recompute with today's prices in `src/models_client/models.py` before comparing costs.
- Judges and the simulator are models too. A new judge version changes verdicts, so re-validate with step a first.

## 9. Troubleshooting

Problems hit in the original run, and their fixes:
- **Empty agent turns** (GPT-6.1 Sol after reasoning was passed back): the harness sends "Please continue." at most twice for every model, then scores the case `empty_reply`. Earlier rows without the nudge were superseded.
- **`FINAL ANSWER:` on a question**: the first pilot let a question end the case. The system prompt now says the marker goes only on the last message; models that still do it are scored on what they wrote (failure category `final_answer_asks_for_information`).
- **Provider HTTP 520 / API errors**: recorded as `api_error`, scored wrong, and re-run by re-invoking the same command (they are not treated as done).
- **Harness errors (connection reset in our own code)**: recorded as `harness_error`, dropped from n and from every table, and re-run on the next invocation.
- **gpt-oss-120b tool calls with unreadable JSON**: the agent gets "Error: arguments were not valid JSON." and continues (flag `tool_parse_error`). gpt-oss needs its `reasoning_content` passed back, which the harness does for gpt-oss only.
- **Open-weight model missing**: if `OPENAI_COMPAT_BASE_URL_PROVIDER_A` is unset, every case of that model is recorded as `harness_error` (excluded and retried), not as wrong.
- **Analyzer time budget**: the analyzer caps itself at 840 s to fit Kitaru's task timeout; `replay/swap_underwriting.py` lifts it to 3,600 s for this offline run.
- **Kitaru Postgres not shut down cleanly**: it recovers on restart; restart the worker afterwards. Keep the data directory outside temporary directories.
- **Prompt hill-climb rejects a rewrite**: rewrites that copy 3+ digit numbers or learning-case company names into the prompt are rejected and retried once; GPT-6 Luna's only rewrite did not beat 78/84 on learning, so it has no tuned arm.

## Changes from the original run

Code changes are only those needed to remove private names and paths and to run from this directory; behavior is otherwise identical.
- `src/models_client/` (new): the agent client (`call_model`, `_anthropic`, `_responses`, `EXTRA`) and the price table, copied from the Haiku Tax benchmark's harness. Changes: only the 12 models used here; open-weight endpoints come from `OPENAI_COMPAT_BASE_URL_PROVIDER_A` / `OPENAI_COMPAT_API_KEY_PROVIDER_A` instead of a hard-coded provider URL and key name (a missing URL raises `KeyError`, like a missing key); User-Agent `underwriting-bench/0.1`; the Haiku-Tax-only parts (task loop, policy check, hash-seed re-exec) are left out.
- Model keys `*@<provider>` renamed to `*@provider-a` in code, file names, result rows, summaries, prompts directories and the export.
- `harness/llm.py`: imports the vendored client instead of the Haiku Tax directory. `harness/run.py`: `--effort` sets `EXTRA` on the vendored client (same fields).
- `replay/swap_underwriting.py`: price table from `src/models_client`. `replay/run_all.sh`: requires `KVENV` (no default path), runs from the benchmark directory, creates `replay/logs`. `kitaru_replay/evaluator.py`: requires `UW_HARNESS` (no default path).
- `scripts/fetch_data.sh`, `scripts/run_all.sh` (moved from the top level): `cd` to the benchmark directory; `fetch_data.sh` takes `PYTHON` and uses `curl -f` so a failed download stops the script. `scripts/run_all.sh`, `harness/run_tuned.sh`, `harness/run_shared.sh` create their log directories.
- New, free: `scripts/make_split.py` (the split rule, which the original never committed as code), `scripts/test_offline.py`, `scripts/check_tables.py`, and `scripts/export.py` (the original export script, with paths relative to this directory, the neutral provider label, `provider_label` instead of `provider_private`, a fixed original commit, and an `inconsistencies` section).
- `results/underwriting.json` is regenerated by `scripts/export.py`. Compared with the original export, only these changed: the provider label, `meta.code_location` (plus a note), the spend-log reference, two public-safety texts, and the added `inconsistencies`. Every number is identical.
- Not ported: the original's pilot, smoke and superseded first-pass rows, transcripts, logs, the analyzer's raw outputs, and a patch to a skills repository.
