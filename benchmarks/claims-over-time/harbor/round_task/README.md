# Round tasks: one improvement round per improver arm

Each round of the experiment gives both improvers the same Harbor task: here is the claims agent, here is how it did on every batch so far, here are the rulings of the revealed appeals, propose one change. `scripts/round.py` generates the task for each round and arm from `template/`, runs both trials, takes the candidate each trial leaves, and applies the approval rule on this machine.

## How a round works

`scripts/round.py` keeps three lines of the agent. Each line's versions are copies of the package directory in `work/rounds/<line>/versions/<n>/claims_agent/`, and `work/rounds/<line>/current.json` names the current one.

| line | how it changes |
|---|---|
| `left_alone` | never, except the model switch |
| `codex` | each round, by Codex in a Harbor trial (Harbor's `codex` agent, `harbor/codex/agent.py`) |
| `pro` | each round, by the ZenML Pro agent in a Harbor trial (`pro_round_agent.py`, on the agent's own Harbor class from `PRO_AGENT_DIR`) |

The `pro` line needs the ZenML Pro agent bundle, which is not public. Without `PRO_AGENT_DIR`, `round.py` says so and runs the `left_alone` and `codex` lines only (no Kitaru workspace is used at all).

Round k runs these steps in order. Each finished step writes `work/rounds/round-<k>/<step>.json`, and a rerun of the script skips it, so a crashed round resumes where it stopped.

1. **switch** (round 4 only, `--switch-round`): every line's current version gets the open model preset as a new version. A preset sets `model`, `base_url_env` and the whole `[model_settings]` table together (`PRESETS` in `round.py`). An improver's change to `[model_settings]` is replaced at this point.
2. **run**: each line's current version decides all 100 appeals of batch k. `left_alone` and `codex` run locally (`run_batch.py --agent-dir`). `pro` runs through the Kitaru workspace: `round.py` registers the version as a version of the Kitaru agent (`claims-agent`, command `python -m claims_agent.episode`, working directory the version's folder), asks for one session run per appeal, and starts one worker on this machine per session run, scoped to that agent version and that job (`--claim agent=<version> --job-id <job>`; it ends when its job settles). A host worker therefore never claims a job the round runner did not create, and never runs an evaluator. Rows go to `work/runs/<line>/batch-<k>.jsonl`.
3. **score**: `score.py` on batch k and on batches 1 to k, per line, on this machine only.
4. **reveal**: the revealed appeals of batches 1 to k get their ruling in `work/rounds/views/round-<k>/cases.jsonl`.
5. **cohort**: a new version of the Kitaru cohort `claims-agent-revealed`, holding the pro line's sessions of every revealed appeal so far.
6. **improve**: `round.py` writes one task per arm into `work/rounds/round-<k>/<arm>/task/` and runs both trials at once. No worker runs on this machine during the trials. The pro trial runs its own worker (see below), so the Pro agent's experiments, on any version it registers, run in the sandbox.
7. **approve**: per arm, `round.py` unpacks the candidate the verifier copied out, then runs the current and the candidate version locally on every revealed appeal so far. Rows are cached by version hash in `work/runs/approval/<hash>.jsonl`, so a version never reruns an appeal it already decided. The candidate ships only if its balanced accuracy is at least as high as the current version's. The decision, the scores, the improver's usage and the rerun count go to `work/rounds/round-<k>/decision-<arm>.json` (see "Reruns and the budget" below).
8. **audit**: for everything created since the run started, `round.py` lists every evaluation and fails loudly if one scored an appeal before it was revealed; lists the agent versions and evaluators that `round.py` did not register; and, for each agent version, which workers claimed its tasks. It fails loudly if a host worker (`claims-host-*`) ever claimed a task of a version `round.py` did not register. Without the pro line it is skipped.

A candidate is not shipped, whatever its score, when the verifier did not pass it, when it is identical to the current version, when it changes `model` or `base_url_env`, or when its Python changes add a line that could read rulings or reach the network (`INTEGRITY` in `round.py`: `truth`, `cases.jsonl`, `os.environ`, `subprocess` and the like). Such a flag needs a person to look; the decision file lists the lines.

## What a trial contains

The trial image is the arm's base image (`build_images.sh`) plus the round's files, added by `environment/Dockerfile`:

| path | what |
|---|---|
| `/claims/agent/claims_agent/` | the arm's current version; the improver edits it in place and writes `CHANGE.md` there |
| `/claims/data/cases.jsonl` | the appeals of batches 1 to k only, with `truth` on the revealed rows and on no other row (`round.py` refuses to build the task otherwise) |
| `/claims/data/precedents.jsonl` | the precedent library, the same file every version reads (in the base image; its sha256 is the image label `claims.precedents_sha256`) |
| `/claims/runs/batch-<k>.jsonl` | Codex arm only: the codex line's rows of batches 1 to k, transcripts included |
| `/claims/round.json` | round, arm, rerun budget, minutes |
| `/claims/bin/` | `verify.py`; Codex arm also `rerun.py` and copies of `scripts/run_batch.py` and `scripts/score.py` |
| `/usr/local/bin/claims-rerun` | Codex arm only (built into its image with `RERUN_TOOL=1`) |
| `/claims/secrets/rerun.env` | Codex arm only: the claims agent's model credentials for `claims-rerun`, written by its agent class at install time, never in the image or the logs |

The pro arm reads the recorded runs as Kitaru sessions instead of files, and reruns the agent only through Kitaru experiments: its trial has no `claims-rerun`, no `rerun.py` and no `run_batch.py`. `pro_round_agent.py` starts a Kitaru worker in the trial before the agent's turn and stops it after (SIGTERM, so it drains and deregisters): `/opt/claims-venv/bin/kitaru worker start --claim agent --claim evaluator --concurrency 4 --name claims-trial-round-<k>`, as the trial's agent user, with `/opt/claims-venv/bin` first on PATH, `CLAIMS_WORK_DIR=/claims/data`, and the claims agent's model credentials in the environment of the one command that starts it (no file in the trial). Its log lands in `<trial>/agent/kitaru-worker/worker.log`. The trial image also holds a read-only copy of the current registered version at its registered working directory (the host path, recreated in the image), so this worker can run the round runner's version too.

Both arms get the same instruction text (`harness/improver_instructions.md`), identical except the `ARM-SPECIFIC` line. That line states facts the improver can check, never how to use a tool. Codex's: the recorded runs are JSONL files in `/claims/runs/`, and `claims-rerun` (what it prints, its options) is how it reruns, one rerun per call. The Pro agent's: the agent and the version it is registered as, the cohort, the evaluator, the worker's name, what it claims and its environment, and that reruns are Kitaru experiment runs, one rerun per experiment run. The Pro agent's own skills, not the instruction, cover how to use Kitaru. Both get the same budget (3 reruns per round) and the same time (45 minutes: Harbor's agent timeout for Codex, `run_timeout_sec` for the Pro agent, whose Harbor timeout is 5 minutes longer for its own start-up).

### Reruns and the budget

Nothing blocks a rerun over budget. After the trial, `approve` counts each arm's reruns on its own path: Codex's `claims-rerun` calls (from the tool's log, copied out as `verifier/reruns.jsonl`), and the pro arm's Kitaru experiment runs created during the trial. It then scans the improver's own command log for runs of the claims agent outside that path: Codex's trajectory (`agent/trajectory.json`, every tool call's arguments) and the Pro agent's `agent/pro/commands.jsonl` (every shell command, written by its Harbor class). A command counts when it runs `python -m claims_agent.episode`, imports `claims_agent` in Python, runs `run_batch.py`, or starts a run outside an experiment (`kitaru ... replay create`, `session_runs.create`); the `--command "..."` of a `kitaru agent version register` is ignored, because registering a version runs nothing. Each such command counts as one rerun over budget, whatever the counted path's total. The decision file records `reruns.counted`, `reruns.outside_counted_path` (`count` and the commands themselves, for a person to check) and `reruns.over_budget`. The scan is a text match: it misses a run started from a script file the improver wrote and then ran by name, and it counts an import that only uses the package's tools without calling the model (the Pro agent did this once in mini round 2's first attempt, to list precedents).

Network: none while the trial is set up. During the agent phase, only `api.openai.com`, plus hosts passed at run time with `--allow-agent-host`: the Kitaru server (pro arm) and the claims agent's model endpoint when the open model is in use (both arms). The verifier (`tests/test.sh`, which runs `verify.py`) has no network: it loads the package with placeholder credentials, builds the agent for a revealed appeal, and writes reward 1 when that works and `CHANGE.md` exists. It copies `candidate.tgz`, `CHANGE.md`, `reruns.jsonl` and `check.json` into the trial's `verifier/` folder. It does not score accuracy.

## Where rulings can and cannot be read

- Every agent version that `round.py` runs locally reads `work/rounds/views/agent/cases.jsonl`, which has no ruling at all. A candidate that tried to read rulings would find none during approval or on a new batch.
- The trial's `cases.jsonl` has rulings for revealed appeals only, and it is the `CLAIMS_WORK_DIR` of the worker in the pro trial. Every version the Pro agent registers, and every evaluator, runs there. The evaluator (`harness/evaluator.py`) raises instead of scoring an appeal without a ruling, so no score of an unrevealed appeal is written to the workspace through it. The host workers read `views/agent/` (no rulings) and run no evaluator.
- Scores of unrevealed appeals exist only in `work/rounds/round-<k>/score.json` on this machine.

Not closed: the round runner's own versions (all three lines, approval and batch runs) run on this machine, as this user. A candidate written to cheat could open `work/cases.jsonl` by its path when it runs for approval or on the next batch. The integrity check on candidates catches the obvious cases; it is not a sandbox. Code the Pro agent registers in Kitaru runs only in its trial: host workers claim only the round runner's own jobs. The worker in the trial claims any agent task in the workspace while it runs, so do not run another round (for example a smoke round) against the same workspace at the same time.

## Build (once, and after Pro agent or dependency changes)

```bash
cd benchmarks/claims-over-time
export DOCKER_CONTEXT=orbstack
harbor/round_task/build_images.sh                            # Codex only: claims-over-time-round-codex:latest
PRO_BASE_IMAGE=<pro trial image> harbor/round_task/build_images.sh   # also claims-over-time-round-pro:latest
```

### The ZenML Pro agent bundle (`PRO_AGENT_DIR`)

The pro arm runs the ZenML Pro agent, whose code is private. It lives in a separate directory that builds the agent's trial image, renders what the agent starts with, and holds the agent's Harbor class. Point `PRO_AGENT_DIR` at that directory. `round.py` relies only on this contract:

| what | used for |
|---|---|
| `$PRO_AGENT_DIR/pro_agent/agent.py`, class `ProAgent` | a Harbor `BaseInstalledAgent`; `round.py` puts `$PRO_AGENT_DIR` on Harbor's `PYTHONPATH`, and `pro_round_agent.py` subclasses it. It takes the kwarg `run_timeout_sec`. |
| `$PRO_AGENT_DIR/prepare` (executable) | run before each round's trials (the agent's prompt carries the date); its last output line, JSON, is recorded in `improve.json` |
| the trial image (`PRO_BASE_IMAGE`) | built by the bundle; `build_images.sh` adds the shared tools on top and runs as its user |
| `<trial>/agent/pro/summary.json` | the agent's usage (`usage`, with `cost`) and how its turn ended (`end`) |
| `<trial>/agent/pro/commands.jsonl` | every shell command the agent ran, `{"command": ...}` per line, for the rerun audit |

`PRO_ROUND_IMAGE` (default `claims-over-time-round-pro:latest`) names the round image on both sides: `build_images.sh` tags it and `round.py` starts the pro trials from it.

`build_images.sh` installs the benchmark's locked `agent` extra (from `uv export`) into `/opt/claims-venv` in both images, so the claims agent in a trial (through `claims-rerun` or the in-trial Kitaru worker) runs the same packages as `round.py` on the host. The Codex base pins the Codex CLI (0.160.1) and uv (0.13.4).

## Run

```bash
cd benchmarks/claims-over-time
set -a; . /path/to/openai.env; set +a            # OPENAI_API_KEY; work/.env (KITARU_API_URL, KITARU_PRO_API_KEY) is read by round.py
export DOCKER_CONTEXT=orbstack CLAIMS_AGENT_BASE_URL=...   # the open model's endpoint, needed from the switch round on
export PRO_AGENT_DIR=/path/to/pro-agent-bundle               # leave unset to run left_alone and codex only
uv run --extra agent python scripts/round.py --frontier-preset gpt-6.1-sol --rounds 1-8
```

Whether the pro line runs is part of the settings: a run started without `PRO_AGENT_DIR` cannot later continue with it, or the other way round.

Settings: `--frontier-preset` (required: the model before the switch), `--open-preset` (default `open`), `--switch-round` (default 4), `--improver-model` (default `gpt-6-luna`), `--rerun-budget` (default 3), `--minutes` (default 45), `--pro-agent` (default `claims-agent`, the Kitaru agent of the pro line), `--stop-after STEP`, `--allow-host HOST` (another host both trials may reach). `round.py` writes its settings to `work/rounds/settings.json` on the first call and refuses to continue with different ones.

The trials run with Harbor's `-m openai/gpt-6-luna`. Codex receives `--model gpt-6-luna` (Harbor drops the provider prefix); Codex CLI 0.160.1 accepts it. The ZenML Pro agent runs with `openai/gpt-6-luna`. Neither arm sets a reasoning effort, so each uses its own default.

## Mini round 1 (verified 2026-10-27, earlier worker layout)

This first run used an earlier layout: one host worker claimed the current version and every evaluator, also during the trials, and the Pro agent could not run versions it registered. Mini round 2 below verifies the current layout. The evidence on truth stripping, the verifier and the approval rule still holds.

`--mini` runs round 1 only, on 10 appeals of batch 1 (4 revealed: two upheld, two overturned, the first of each in filing order; 6 unrevealed), with the state in `work/rounds/mini/` and `work/runs/mini/`, and the Kitaru agent `claims-agent-smoke`, so smoke data never mixes with the real run.

```bash
cd benchmarks/claims-over-time
set -a; . /path/to/openai.env; set +a
export DOCKER_CONTEXT=orbstack
uv run --extra agent python scripts/round.py --mini --frontier-preset smoke-gpt-5-mini --minutes 20
```

Run on 2026-10-27 (macOS arm64, OrbStack, Harbor 0.22.0, Kitaru 0.27.2, Codex CLI 0.160.1, Pro agent bundle at commit 8ee2d3dde039), first in steps with `--stop-after`, then to the end. Output trimmed:

```
left_alone, codex, pro: version 0 (aa642ba28fe9): the frozen package (a893dff4af7e) with model preset smoke-gpt-5-mini
kitaru: registered claims-agent-smoke version None for line version 0   (a parsing bug in the log line, fixed after this run; Kitaru registered version 1)
run: left_alone version 0 on batch 1: 10 appeals, 0 errors, $0.0483
run: codex version 0 on batch 1: 10 appeals, 0 errors, $0.0448
run: pro version 0 on batch 1: 10 appeals, 0 errors, $0.0417      (10 Kitaru sessions, status completed)
score: balanced accuracy on batch 1: left_alone 54.2%, codex 62.5%, pro 62.5% (n = 10 each)
cohort: claims-agent-smoke-revealed@1, 4 sessions
improve: codex trial   Trials 1, Exceptions 0, Mean 1.000, 4 min 18 s
improve: pro trial     Trials 1, Exceptions 0, Mean 1.000, 4 min 34 s (the agent ended its turn normally)
approve: codex: shipped: balanced accuracy on 4 revealed appeals: candidate 0.500 vs current 0.250
approve: pro: shipped: balanced accuracy on 4 revealed appeals: candidate 0.250 vs current 0.250
audit: 0 evaluations on agent sessions
```

What the run showed:

- **Both trials produced a candidate and a CHANGE.md.** Codex added a system prompt instruction for repeat radiofrequency ablation appeals (in `agent.py`, keyed on the appeal's treatment); the Pro agent added a prompt paragraph asking the agent to read precedents on both sides before deciding. Both verifiers wrote reward 1, and both candidates are now version 1 of their line.
- **Both arms used their information.** Codex read `/claims/runs/batch-1.jsonl` and ran `claims-rerun` 3 times. The Pro agent listed the agent's sessions and cohort, read the nodes of single sessions with `kitaru session nodes`, and ran `claims-rerun` once; it ran no Kitaru experiment. Neither went over budget.
- **The approval rule shared its cache.** Both lines' version 0 has the same hash, so the pro decision reused the 4 rows the Codex decision had already run for it.
- **Truth stripping held inside the trial.** The Pro agent's own command in the trial (its command log) printed `total 10 revealed 4` and listed exactly the 4 revealed appeals with a ruling; both tasks' `cases.jsonl` have 10 rows, with `truth` on those 4 only.
- **No unrevealed evaluation reached Kitaru.** After the round, a separate check ran the registered evaluator through the host worker on a cohort of one revealed and one unrevealed session (`claims-agent-smoke-evaluator-check`, baseline evaluation forced). The revealed one was scored (`MN25-43842: decided uphold, truth uphold`, for the baseline and the replay); the unrevealed one failed with `appeal MN25-43789 has no revealed ruling in cases.jsonl; not scored`, and no evaluation was stored for it. The audit then found 2 evaluations in the workspace, both of revealed appeals created after the reveal, no agent versions or evaluators that `round.py` did not register.
- **Resuming works.** Each later call skipped the finished steps (`round 1: run already done`, and so on).
- **Models.** The Codex session files record `"model":"gpt-6-luna"` and `"cli_version":"0.160.1"`; the Pro agent's summary records `openai/gpt-6-luna`.

Spend for the whole mini round, about $0.35: claims agent runs $0.13 (batch), $0.06 (approval), $0.08 (in-trial reruns), $0.01 (evaluator check), from the rows' `cost_usd` (PydanticAI's price table); improvers $0.024 (Codex, as Harbor computes it) and $0.031 (the Pro agent, as its own runtime computes it). Not checked against the OpenAI bill.

Not exercised by the mini round: the model switch (round 4; the presets were checked offline, and the `open` preset reproduces the frozen package's `config.toml` byte for byte), a second round (cohort version deltas, registering a second Kitaru agent version, the Codex arm reading several batch files), a trial reaching the open model's endpoint, the 45-minute limit, a candidate rejected by the integrity check, a reward-0 candidate end to end (the verifier's reward 0 for a syntax error and for a missing CHANGE.md was checked in a container by hand), and a Pro agent experiment run counted against the budget.

## Mini round 2 (verified 2026-10-27, current worker layout)

Same command and settings as mini round 1, on a fresh state folder (the first one is kept as `work/rounds/mini-first-2026-10-27/`). `round.py` adopted the existing smoke agent, evaluator and cohort: it registered `claims-agent-smoke@2` for the pro line, evaluator version 2, and cohort version 2 with this run's 4 revealed sessions in place of the earlier ones. The improve, approve and audit steps ran twice (the first attempt's records are kept as `*-attempt1.json`); between the attempts only the worker's stop signal changed, from SIGINT to SIGTERM, because a process started in the background ignores SIGINT.

```
run: 10 appeals per line, 0 errors; pro: 10 session runs, each claimed by its own job-scoped host worker (claims-host-<job>)
score: balanced accuracy on batch 1: left_alone 37.5%, codex 70.8%, pro 62.5% (n = 10 each)
cohort: claims-agent-smoke-revealed@2, 4 sessions
attempt 1: codex not shipped (candidate 0.500 vs current 0.750); pro: NO CHANGE (claims-rerun 3, Kitaru experiment runs 0)
attempt 2: codex: NO CHANGE (claims-rerun 2); pro shipped (0.750 vs 0.750; claims-rerun 3, Kitaru experiment runs 0)
all four trials: reward 1.0, no exceptions
in-trial worker log: Registered worker claims-trial-mini-round-1 ... Stop requested, ending the claim loop ... stopped   (attempt 2)
```

**Finding: the Pro agent did not use Kitaru to test versions.** In both attempts it read the workspace (`kitaru status`, `agent list`, `session list`, `cohort list`/`get`, `evaluator list`, and in attempt 1 `session nodes`), checked that the worker was running (`pgrep -af 'kitaru.*worker start'`), and looked at the read-only registered copy. It then spent its whole budget on `claims-rerun`. It registered no version and started no experiment. Nothing in the instruction tells it to prefer one or the other, and that was left as is.

**The Kitaru path works when it is used.** To check the mechanism without the agent, a container of the same round-1 pro task image started the worker with the same command as the round agent class (`claims-trial-mechanism-check`). Inside it, as the agent's user, a script copied the agent to `/claims/try`, added one prompt line, and registered it with `kitaru agent version register claims-agent-smoke --command "python -m claims_agent.episode" --working-dir /claims/try` (version 3). It then created the experiment `claims-agent-smoke-mechanism-check` (evaluator `claims-agent-smoke-decision-correct@2`, tool policy passthrough) and ran it on cohort version 2. The run completed with 4 of 4 replays, and the audit afterwards shows:

- 8 evaluations since the run started (4 baselines, 4 replays), all with scores, all of revealed appeals; no violation.
- Version 3 (registered in the sandbox): 4 tasks, all claimed by `claims-trial-mechanism-check`.
- Version 2 (the round runner's): 10 tasks, each claimed by its own `claims-host-<job>` worker.
- No host worker claimed a task of a version `round.py` did not register (`host_workers_on_other_versions` is empty).

That container ran outside Harbor, so with ordinary network access, not the trial's allowlist.

Spend for mini round 2, about $0.52: claims agent runs $0.13 (batch), $0.05 (approval), $0.20 (in-trial reruns), $0.02 (mechanism check replays), from the rows' `cost_usd` and the sessions' Kitaru cost; improvers $0.12 for the four trials (Harbor's and the agent runtime's computation). Not checked against the OpenAI bill.

## Mini round 3 (verified 2026-10-27, Kitaru-only reruns for the pro arm)

What changed since mini round 2: the pro trial has no `claims-rerun` (not installed, not in `/claims/bin`, not in its instruction), so Kitaru experiments are its only rerun path; the line about `claims-rerun` moved from the shared instruction text into Codex's `ARM-SPECIFIC` line; the pro arm's `ARM-SPECIFIC` line says that reruns are Kitaru experiment runs, one rerun each; `approve` scans both improvers' command logs for runs of the claims agent outside the counted path; and the pro arm's code is loaded from `PRO_AGENT_DIR`. The Codex arm's trial is unchanged.

Same smoke settings as mini rounds 1 and 2 (Kitaru agent `claims-agent-smoke`, 10 appeals of batch 1, 4 revealed, rerun budget 3), except the time limit: 45 minutes, the real rounds' limit, so the Pro agent's choice is not shaped by a tighter clock. Fresh state folder (mini round 2's is kept as `work/rounds/mini-second-2026-10-27/` and `work/runs/mini-second-2026-10-27/`). Nothing else used the workspace during the run (a smoke run of the Pro agent bundle a few minutes before it found no live worker).

```bash
cd benchmarks/claims-over-time
set -a; . /path/to/openai.env; set +a
export DOCKER_CONTEXT=orbstack PRO_AGENT_DIR=/path/to/pro-agent-bundle
uv run --extra agent python scripts/round.py --mini --frontier-preset smoke-gpt-5-mini --minutes 45
```

Output, trimmed:

```
left_alone, codex, pro: version 0 (aa642ba28fe9): the frozen package (a893dff4af7e) with model preset smoke-gpt-5-mini
kitaru: registered claims-agent-smoke version 4 for line version 0
run: left_alone $0.0432, codex $0.046, pro $0.0474 (10 appeals each, 0 errors; pro: 10 session runs on job-scoped host workers)
cohort: claims-agent-smoke-revealed, new version with this run's 4 revealed sessions
improve: codex trial reward 1.0, harbor exit 0; pro trial reward 1.0, harbor exit 0
approve: codex: no change to the agent; reruns over budget by 1
approve: pro: no change to the agent
audit: 15 evaluations since the run started, all of revealed appeals; 3 agent versions registered by others, none run by a host worker
```

| | Codex | ZenML Pro agent |
|---|---|---|
| trial wall time (Harbor) | 4 min 9 s | 8 min 41 s |
| agent phase, of its 45 minutes | 3 min 46 s (8%) | 8 min 19 s (18%; includes starting and stopping the in-trial worker) |
| reruns on the counted path | 3 `claims-rerun` calls | 3 Kitaru experiment runs |
| runs found outside the counted path | 1 (see below) | 0 of 49 commands |
| `reruns.over_budget` | 1 | 0 |
| result | `NO CHANGE` (two tried candidates scored 0.50 and 0.00 balanced accuracy) | `NO CHANGE` (three tried candidates: 0.25, 0.50 and an incomplete run, against the baseline's 0.50; prompt restored) |
| improver cost (the arm's own computation) | $0.032 | $0.069 |

**The Pro agent used Kitaru experiments for every rerun.** No `claims-rerun` appears in its trial's instruction or command log. It read the workspace (agent, versions, cohort, evaluator, sessions and their nodes), edited `/claims/agent/claims_agent/prompt.md` in place, and three times registered the directory as a new version (`kitaru agent version register claims-agent-smoke --command 'python -m claims_agent.episode' --working-dir /claims/agent`, versions 5, 6 and 7) and ran it on the revealed cohort with one experiment (`claims-round-1-rfa-evidence`, the round's evaluator, passthrough tool policy, `--baseline-evaluation-mode if-missing`). What the audit and the workspace show:

- All 12 agent tasks of versions 5, 6 and 7 were claimed by the in-trial worker `claims-trial-mini-round-1`; the round runner's version 4 tasks were claimed only by the 10 job-scoped host workers; `host_workers_on_other_versions` is empty. The worker's log shows it registered at the start of the agent phase and stopped (`Stop requested ... stopped`) after it.
- Experiment runs: two `completed` (4 of 4 replays each) and one `failed` (3 of 4: one replay hit the claims agent's 12-request limit and its result session failed, so it got no evaluation).
- 15 evaluations, all with scores, all of the 4 revealed appeals and all created after the reveal: 4 baselines (version 4) and 4 + 4 + 3 replays. No violation.
- `approve` counted the 3 experiment runs (`reruns.kitaru_experiment_runs` = 3), within the budget.

**The new audit on Codex.** Codex used its 3 `claims-rerun` calls, and the scan flagged one more command: a Python snippet that imported `claims_agent.agent.Env` to call the precedent search tool directly, without calling the model. By the rule it counts as a rerun outside the counted path, so `over_budget` is 1. This is the known over-count of the text scan (the Pro agent did the same in mini round 2's first attempt); the decision file lists the command for a person to judge.

**Finding: a registered version can point at a directory that keeps changing.** The Pro agent registered versions 5, 6 and 7 all with the working directory `/claims/agent`, which it then edited and finally reverted. Each experiment ran whatever the directory held at that moment, so the workspace's records of versions 5 to 7 do not by themselves say which code they ran. The candidate the verifier copied out is unaffected.

Spend for mini round 3, about $0.36: claims agent runs $0.137 (batch), $0.049 (Codex's in-trial reruns, from `claims-rerun`'s log), $0.068 (the Pro agent's 12 experiment replays, the sessions' Kitaru cost), $0 (approval: neither arm proposed a change); improvers $0.032 (Codex, as Harbor computes it) and $0.069 (the Pro agent, its own computation); plus $0.007 for two one-minute smoke runs of the Pro agent bundle from its new directory and $0.09 for the check without `PRO_AGENT_DIR` below. Not checked against the OpenAI bill.

Not exercised by mini round 3: an approval run on a pro candidate (neither arm changed the agent), a Pro agent over budget, and a full round without `PRO_AGENT_DIR`. A separate run without it, in a scratch work folder, went to the cohort step: it printed the message, ran only `left_alone` and `codex` ($0.09), recorded the cohort step as skipped, and the same folder then refused to continue with `PRO_AGENT_DIR` set (`settings.json was written with other settings: {'pro_arm': (False, True)}`).
