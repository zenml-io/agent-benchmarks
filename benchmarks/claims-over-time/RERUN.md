# Rerun: claims over time

Each component's README has the full detail; this file gives the order. Commands marked "verified 2026-10-27" were run while building the benchmark; the full run (section 7) ran on 2026-10-27 and 2026-10-28.

## 1. Prerequisites

- macOS or Linux, Python 3.12, uv 0.13 or later.
- Docker with OrbStack on macOS (Harbor's network control needs it; Docker Desktop rejects `no-network`). Use `DOCKER_CONTEXT=orbstack` on Harbor commands.
- Harbor 0.22.0 (`uv tool install harbor==0.22.0`).
- A Modal account (one H100 for the open model, case-file extraction and the classifier).
- An OpenAI account (the claims agent before the switch, both improvers).
- For the ZenML Pro arm only: a Kitaru workspace on ZenML Pro, a ZenML Pro service-account key, and the ZenML Pro agent bundle (not public; see `harbor/round_task/README.md`).

## 2. Credentials

Names only; values go in `work/.env` (gitignored) or the shell. See `.env.example`.

| variable | for | steps |
|---|---|---|
| `OPENAI_API_KEY` | claims agent on OpenAI models, both improvers | 6, 7 |
| `MODAL_ENVIRONMENT` | the Modal environment to deploy into | 4, 6, 7 |
| `CLAIMS_AGENT_BASE_URL` | the open model's endpoint (`.../v1`), from the switch round on | 6, 7 |
| `KITARU_API_URL`, `KITARU_PRO_API_KEY` | the Kitaru workspace for the ZenML Pro arm | 7 |
| `PRO_AGENT_DIR`, `PRO_BASE_IMAGE` | the ZenML Pro agent bundle and its trial image | 7 |
| `CLAIMS_WORK_DIR` | optional; default `./work` | all |

## 3. Install

```bash
uv sync --all-extras    # verified 2026-10-27: kitaru 0.27.2, kitaru-pydantic-ai 0.3.1, modal 1.6.2
```

## 4. Get the data

```bash
uv run python scripts/build_stream.py                                   # free; verified 2026-10-27
uv run --extra modal python harness/extract/extract.py all              # about $3.20 on Modal; verified (as up/run/down)
uv run python scripts/assign_batches.py                                 # free; verified 2026-10-27
```

Expected: 19,374 precedents (same sha256 as `../decision-agents/data/SHA256SUMS`), 3,155 candidates, 3,131 usable case files, 900 appeals in `data/stream.jsonl` (100 per batch, 160 revealed). `assign_batches.py` writes the same `data/stream.jsonl` as the committed one when the extraction matches; vLLM output at temperature 0 can vary slightly between runs, which can change which appeals are usable.

Source: [California IMR determinations](https://data.chhs.ca.gov/dataset/independent-medical-review-imr-determinations-trend), CalHHS Open Data Portal (terms of use allow free download and use).

## 5. Free checks

```bash
uv run --with pytest pytest -q scripts                                  # 14 passed; verified 2026-10-28
uv run python scripts/score.py work/runs/<tag>.jsonl                    # per-batch and cumulative table
```

## 6. Smoke tests (paid, small)

- **Calibration batch on three models** (about $2.50): run `scripts/run_batch.py --batch 0` with the frozen agent on Qwen (`CLAIMS_AGENT_BASE_URL` set, server from `harness/extract/extract.py up`), and with copies whose `config.toml` uses `openai-responses:gpt-6.1-sol` and `openai-responses:gpt-6-luna`. Expected: Qwen 70 to 76% accuracy, Sol about 88% balanced accuracy. Verified 2026-10-27 (table in `README.md`). GPT-6 models need the Responses API (`openai-responses:`); on chat completions they reject tools with reasoning.
- **HICRIC classifier** (about $1.60): `harness/hicric/README.md`, section Rerun. Verified 2026-10-27.
- **Mini round** (about $0.50): `harbor/round_task/README.md`, section Mini round 3. Verified 2026-10-27. With `--frontier-preset smoke-gpt-5-mini-tight` some appeals end undecided at the output limit, which tests whether an improver finds them; verified 2026-10-28. `--pro-gepa` gives the ZenML Pro arm GEPA and a budget of appeal runs; it needs the pro image rebuilt by `build_images.sh` after 2026-10-28. `--no-pro-task-hint` leaves the counting sentence and the list of each batch's recording version out of the ZenML Pro arm's task line, so the agent has only its own prompt and skills for them; verified 2026-10-29.

## 7. Full rerun

```bash
harbor/round_task/build_images.sh                                       # verified 2026-10-27
export DOCKER_CONTEXT=orbstack CLAIMS_AGENT_BASE_URL=... PRO_AGENT_DIR=...
uv run --extra agent python scripts/round.py --frontier-preset gpt-6.1-sol --rounds 1-8 --concurrency 24   # verified 2026-10-28, all eight rounds in one call
```

This command reproduces the second run: approval on held-out appeals, and the ZenML Pro arm's instruction line with the sentence asking it to count how every session ended (README, "Design"). The first run used the approval rule now selected by `--approval-on revealed`, and its ZenML Pro trials had the line without that sentence, so `--approval-on revealed` alone does not reproduce them exactly. The ZenML Pro arm needs a bundle from 2026-10-28 or later, whose trial check reads a login failure only from a command result that reports one (README, "Found while running the second run").

`round.py` is resumable: each finished step writes `work/rounds/round-<k>/<step>.json` and is skipped on rerun. From round 4 the open model's server must be deployed (`harness/extract/extract.py up`); it scales to zero when idle, and `round.py` waits for it before each step that uses it. `--concurrency` sets how many appeals the batch runs and approvals run at once; at the default of 8 the first approval on the open model took over 3 hours, at 24 an approval of both arms took 15 to 101 minutes.

The first run cost about $87 ($54.53 of Modal GPU time for the open model, about $32 of OpenAI usage by the frameworks' estimates) and took about 18 hours from the first batch to the last audit, including four retried ZenML Pro trials. The second run cost $45.61 of Modal GPU time and about $31 of OpenAI usage, and took 11 hours 9 minutes, including one restarted ZenML Pro trial; while `improve` and `approve` run, `round.py`'s pings keep the server's GPU running, so it billed about $4 an hour from round 4 on. A round on the open model took 2 to 2.5 hours without retries: the three batch runs about 17 minutes, both improver trials 30 to 40 minutes in parallel, approval the rest. Stop the open model's server afterwards (`harness/extract/extract.py down`) and check `modal app list`.

To retry an arm whose trial a network failure cut short, set the step's markers aside (`improve`, `approve`, `audit` and that arm's `decision-<arm>.json`), undo the arm's shipped version if the cut trial's candidate shipped (move `work/rounds/<arm>/versions/<n>` aside, copy the previous version's `meta.json` to `current.json`, and add a line saying so to `history.jsonl`), and run the round again with `--retry-improve ARM=REASON`. The restarted trial is told what is left of the arm's budget.

### Interruptions and resuming

If the laptop freezes, the internet drops or `round.py` is killed, run the same command again. Verified 2026-10-27 with `--mini`, `smoke-gpt-5-mini` and the Kitaru agent `claims-agent-smoke`, in scratch state folders:

- **Leftovers.** At startup `round.py` locks its state folder (a second call on the same folder refuses to start), then stops what an earlier call on that folder left running: its Harbor runs and `run_batch.py` runs (matched by their output folders under this state folder) and its host Kitaru workers (matched by the job ids in its journals), with their children, and removes the Docker Compose projects of its Harbor trials (matched by Harbor's working-directory label, which is under this state folder). Nothing else is touched. Seen: after a SIGKILL mid-batch it stopped 2 `run_batch.py` runs and 8 workers and left two look-alike decoy processes alone; after a SIGKILL during `improve` it stopped the orphaned Harbor run; after a simulated freeze (round.py and Harbor killed with SIGKILL) it removed the 2 trial projects left running and left an unrelated stopped container alone. Kitaru keeps the workers' records on the server; they claim nothing once their process is gone, so they only add names to the audit.
- **Infrastructure errors are not scored.** Each row gets `error_kind`: `agent` (request limit, output token limit, retries used up: final, scored as undecided, never retried) or `infra` (network, timeout, HTTP 429 or 5xx, model server down, a Kitaru job or worker failure, or anything not known to be the agent's). `run_batch.py` runs an `infra` appeal again after 30 s, 2 min and 5 min (`CLAIMS_INFRA_BACKOFF`, comma-separated seconds); if it still fails, the step fails without its marker, and the next call reruns just those appeals. Seen: with the network cut after 3 appeals (an HTTPS proxy killed mid-batch), 27 rows across the three lines were tagged `infra` and no `run.json` was written; the rerun ran 7, 10 and 10 appeals and finished with no `infra` row. A copy of the agent with a request limit of 1 got `agent` errors and ran once. A request-limit failure inside a Kitaru session run, where only the message survives, was also tagged `agent`.
- **Kitaru jobs left by a crash.** Before the pro line's batch resumes, and before `improve`, `round.py` settles its own jobs from the journal `work/runs/pro/batch-<k>.jobs.jsonl`: a completed job for an appeal without a row is adopted (its row written, marked `adopted_after_crash`), a pending or running one is canceled, and when the crash came while a job was being created, the pending session-run jobs of its own agent versions that the journal does not name are canceled too. Seen: SIGKILL right after the first job was created left one pending job the journal did not name and one running; the rerun canceled the first, adopted the second, and every appeal had exactly one row, with no pending or running job of the run left.
- **A crash during `improve`.** Every attempt is recorded in `work/rounds/round-<k>/improve-attempts.json` before its trials start, with each arm `ran` or `kept`. An arm whose trial finished in an earlier attempt (its verifier wrote `reward.txt`) is kept; only the other arm restarts. The decision file's `reruns` counts each arm over the attempts in which its trial ran (`per_attempt`), and `per_improve_attempt` says ran or kept for every attempt. Seen: round.py killed after the Codex trial finished (3 `claims-rerun` calls) while the pro trial ran (1 experiment run so far); the rerun logged `attempt 2: codex keeps the trial of attempt 1; pro restarts`, Codex was counted 3 (not over budget) and the pro arm 1 + 3 = 4 experiment runs, the first attempt's included, because its Kitaru versions and experiments stay in the workspace. In an earlier test where no trial had finished (two attempts cut short, the third completed), both arms were counted over all three attempts. A trial cut short is lost, so a crash during `improve` costs that arm budget it did not get to use.
- **The open model scales to zero.** The server stops 20 minutes after its last request, so a dead laptop leaves at most 20 minutes of GPU billing. While `improve` and `approve` run on the open model, `round.py` asks the server for its models every 2 minutes, so an improver that pauses does not meet a cold start mid-trial; the pings stop with the step or the process. Seen with a 5-minute window: zero containers about 5.5 minutes after the last request; `round.py`'s readiness wait then took 140 s and the appeal succeeded. A claims agent call that reaches a cold server without that wait gets HTTP 503 at once (`infra`): once the container took 10.5 minutes to start, longer than the retries, so that appeal was left for the next call, which decided it. Seen with a 3-minute window: the pings kept one container running for 7 minutes, and it scaled to zero about 3.5 minutes after the last ping.

## 8. Compare with the published results

`scripts/score.py` rebuilds every table from the rows in `work/runs/`. Read differences against the 95% intervals it prints: one batch of 100 has an interval 10 to 20 points wide.

## 9. Troubleshooting

- **`Function tools with reasoning_effort are not supported ... in /v1/chat/completions`**: use `openai-responses:<model>` in the agent's `config.toml` for GPT-6 models.
- **Harbor rejects `no-network`**: the Docker context is Docker Desktop; set `DOCKER_CONTEXT=orbstack`.
- **Local Kitaru API keys rejected ("under control plane authentication")**: a ZenML Pro hosted workspace accepts only ZenML Pro credentials; use a service-account key.
- **Qwen appeals end undecided with "Model token limit (4096) exceeded"**: the original agent's output limit; the model's reasoning used it up. Expected for a few appeals per batch.
