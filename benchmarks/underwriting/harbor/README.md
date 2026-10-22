# Underwriting on Harbor

The underwriting benchmark as Harbor tasks: one task per case, the benchmark's tools and simulated underwriter served by an MCP server next to the agent, and the original two-judge panel as the hidden grader. It runs the benchmark's own agent loop as a Harbor agent (so the published conditions can be rerun) and any off-the-shelf harness that speaks MCP (Claude Code, Codex, ...).

Status: **native**, checked on a 12-case sample on 2026-10-22 (oracle 60/60, nop 0/12, three shortcuts 0/36, alternative 12/12; details below). No model agent has been run through it yet.

## What is in this folder

| Path | What it is |
|---|---|
| `generate_tasks.py` | Builds one task per case from the rebuilt environment (`../env/`), for all 252 cases, one split, a list of ids, or the sample. |
| `tasks/` | The committed sample: 12 cases, 2 per question type (both answers where a type has two, e.g. in and out of appetite). `dataset.toml` and the repo-root `registry.json` (`underwriting-sample`) list them. |
| `runtime/server.py` | The MCP server (one per trial, in the `uw-runtime` sidecar). |
| `grader/` | `test.sh` and `grade.py`, copied into each task's `tests/`. |
| `underwriting_agent/` | The Harbor agent `underwriting_agent.agent:UnderwritingCopilot`: the original loop (`copilot.py`) and a standard-library MCP client. |
| `setups/` | Job configs. Conditions differ only in their setup file. |
| `scripts/verify_tasks.py` | The four checks through Harbor, one job per check. |
| `scripts/summarize.py` | Accuracy per setup from job folders, infrastructure errors apart, optional paired interval against a baseline. |
| `tests/test_port.py` | Offline tests (judges, simulator and models mocked). |

## How a task works

```
main container (python:3.12-slim, empty)          uw-runtime sidecar
  the agent under test  ── MCP over HTTP ──────▶   runtime/server.py
                                                   - list_tables, get_table_descriptions, get_table_schema,
                                                     get_table_data_dictionary, read_query, get_underwriting_guidelines
                                                     (harness/run.py Env over env/insurance.db and guidelines.txt)
                                                   - ask_underwriter (harness/run.py underwriter_reply: Claude Haiku 5.5
                                                     with the application in its prompt, at most 12 replies)
                                                   - submit_final_answer (first submission only; closes the case)
                                                   - GET /state (status, final answer, transcript, counters, simulator cost)
```

- `instruction.md` gives the copilot's role, the tools, and the underwriter's opening request between `<request>` tags (the same opening line per question type as the original).
- The sidecar holds the question type and the application (`case.json`), never the reference answer, the oracle's structured answer or its NAICS code. The main container holds nothing. The reference lives only in `tests/` (uploaded after the agent finishes) and `solution/` (uploaded for the oracle only).
- The sidecar runs the benchmark's own code (`harness/run.py`, `llm.py`, `judge.py`, `src/models_client`, copied in by the generator), so tool outputs, error texts, the 200-row cap, the 20,000-character cap and the simulator prompt are the original ones. Tests compare the MCP tools with `run.TOOLS` and `run.Env`.
- Grading (`tests/test.sh` → `grade.py`): delete any reward file, read the final answer from the sidecar's `/state` (never from a file the agent could write), and if there is one, run `harness/judge.py` with GPT-6 Luna and Claude Haiku 5.5, GPT-6.1 Sol on a disagreement or unparseable verdict, and `run.run_task`'s pass rule (a test checks it against the original expression for all 27 verdict combinations). No answer: reward 0 and no judge call. `reward.json` holds only `reward`; `grading.json` has the verdicts, costs and counters; `runtime_state.json` the transcript.
- Infrastructure errors (sidecar unreachable, simulator or judge API failure) write reward 0 and `infra_error` in `grading.json`; `scripts/summarize.py` counts them apart from wrong answers.
- The learning / held-out split (`../env/split.json`) is in each task's `[metadata] split`; `generate_tasks.py --split held` builds the held-out set alone, so tuning never touches it.

The judges' keys reach only the verifier (`[verifier] env`); the simulator's key only the sidecar (compose `environment`).

## Setup

From `benchmarks/underwriting`, after [RERUN.md](../RERUN.md) steps 3-4 (`scripts/fetch_data.sh` rebuilds `env/`):

```bash
uv tool install "harbor[modal]==0.24.0"      # or local Docker instead of Modal
cp .env.example .env                          # fill EVAL_ANTHROPIC_API_KEY, OPENAI_API_KEY (+ provider-a vars for open models)
cd harbor
python generate_tasks.py --out tasks-held --split held     # 168 held-out tasks (~1.3 MB each, ~220 MB)
python generate_tasks.py --out tasks-full                  # or all 252
```

Run every Harbor command from `benchmarks/underwriting/harbor` with `PYTHONPATH=.` (Harbor imports the custom agent from there) and `HARBOR_TELEMETRY=off`. Keys: `--env-file ../.env`; every `harbor run` gets `-y` (the verifier reads host keys, which otherwise stops at a `Proceed?` prompt), a new `--job-name`, and `-o` outside the checkout.

Free offline tests (no model, judge or network calls; about 40 s):

```bash
cd benchmarks/underwriting
uv run --with "mcp==1.26.0" --with pytest pytest -q harbor/tests
```

Expected: `45 passed, 1 skipped` (the skipped test needs Harbor importable; run it with Harbor's own Python to cover it). They check the MCP tools against the original, the one-shot submit and turn limit, the grader against the original pass rule with mocked judges, the runner's routing and limits, and that the committed sample is what the generator builds and shows the agent no reference answer.

## The four checks

```bash
cd benchmarks/underwriting/harbor
export HARBOR_TELEMETRY=off; set -a; . ../.env; set +a
python scripts/verify_tasks.py tasks --jobs-dir ~/uw-harbor-jobs --job-prefix verify -n 4
```

| Check | What it submits | Expected |
|---|---|---|
| oracle (`solution/solve.sh`), 5 attempts | Snorkel's reference answer | 1 every time |
| nop | nothing | 0, no judge call |
| `tests/shortcuts/hedge.sh` | every plausible option and no decision (for a NAICS case, the right code among its two nearest; for products, all six lines "some or all, or none") | 0 |
| `tests/shortcuts/ask_question.sh` | a final answer that asks the underwriter for revenue, employees and state instead of deciding | 0 |
| `tests/shortcuts/forge_reward.sh` | plants `reward.json` = 1, `reward.txt` and an answer file; submits nothing | 0, no judge call |
| `solution/alternatives/paraphrase.sh` | the reference's conclusion in other words, built from the oracle's structured answer (e.g. "Quote $1,000,000 per occurrence with a $2,000,000 aggregate limit.") | 1 |

Results on the 12-case sample, 2026-10-22 (Harbor 0.24.0, Modal):

| Check | Trials | Matched expected | Notes |
|---|---|---|---|
| oracle, 5 attempts per case | 60 | 60 (reward 1) | both primary judges agreed on every answer; no tie-break call |
| nop | 12 | 12 (reward 0) | no judge call |
| `hedge.sh` | 12 | 12 (reward 0) | both judges: hedging |
| `ask_question.sh` | 12 | 12 (reward 0) | |
| `forge_reward.sh` | 12 | 12 (reward 0) | planted files deleted or ignored; no judge call |
| `paraphrase.sh` | 12 | 12 (reward 1) | |

No infrastructure errors. Each trial took about 33 s end to end on Modal (sandbox start and both image builds about 20 s). The tie-break path (GPT-6.1 Sol) was not exercised live, since the judges never disagreed; the unit tests cover it with mocked judges. The other 240 cases were not run through the four checks; their paraphrase and hedge scripts are generated the same way, and every case's paraphrase and hedge are built by the offline tests.

Not checked as shortcuts, and why: "always in appetite" or "recommend every line" score 1 on the cases where that is the answer (61 of 85 appetite cases are "yes"; 3 product cases have all five other lines), so they are not per-task traps; they are a base rate to compare setups against. Looking up the answer in Snorkel's public dataset needs a network block: on Modal, compose tasks share the sandbox's host network and Harbor does not enforce network policies, so an agent with a shell could reach Hugging Face. The benchmark's own loop has no shell (only the eight MCP tools), so this applies to off-the-shelf harnesses; grep their transcripts for `huggingface` or `snorkel`, or run them on local Docker with an egress allowlist.

## Running a real comparison

Paid; not run while writing this. Setups (`setups/`):

| File | Agent | Matches the original |
|---|---|---|
| `copilot-first.yaml` | the benchmark's loop, first prompt (`harness/run.py` SYSTEM) | first run (table 1) and held-out "first prompt" |
| `copilot-shared.yaml` | the benchmark's loop, `results/tuned/prompts/sonnet-5.5/v1.txt` | held-out "shared prompt" |
| `copilot-effort-{low,medium,high}.yaml` | the benchmark's loop, first prompt, effort set | table 3 |
| `claude-code.yaml`, `codex.yaml` | off-the-shelf harnesses with the MCP server | no original counterpart |

Each setup names its model (`model_name`, a key from `../src/models_client/models.py` for the benchmark's loop). Harbor ignores `-m` when the agent comes from a config file, so for another model copy the setup and change `model_name` (`sed 's/haiku-5.5/glm-5.3-flash@provider-a/' setups/copilot-shared.yaml > setups/copilot-shared-glm.yaml`), and give each model its own job. A model's own rewritten prompt is `kwargs.prompt_file: ../results/tuned/prompts/<model>/<version>.txt`.

Baseline and condition in the same batch, 5 attempts per case, held-out set (Claude Haiku 5.5, first vs shared prompt):

```bash
cd benchmarks/underwriting/harbor && export HARBOR_TELEMETRY=off PYTHONPATH=.; \
harbor run -y -c setups/common.yaml -c setups/modal.yaml -c setups/tasks-held.yaml -c setups/copilot-first.yaml --env-file ../.env -o ~/uw-harbor-jobs --job-name held-haiku-first-$(date +%F); \
harbor run -y -c setups/common.yaml -c setups/modal.yaml -c setups/tasks-held.yaml -c setups/copilot-shared.yaml --env-file ../.env -o ~/uw-harbor-jobs --job-name held-haiku-shared-$(date +%F); \
python scripts/summarize.py ~/uw-harbor-jobs/held-haiku-first-$(date +%F) ~/uw-harbor-jobs/held-haiku-shared-$(date +%F) --by-type --baseline "copilot-first / haiku-5.5" | tee ../results/harbor-held-haiku-$(date +%F).md
```

Expected cost and time per setup on the 168 held-out cases × 5 attempts (840 trials), from the original run's per-case spend: agent $0.0017 (GPT-6 Luna) to $0.078 (GLM 5.3) per case, so about $1.40 to $66 per setup (Claude Haiku 5.5: $3.70; Claude Sonnet 5.5: $30; Claude Opus 5.5: $43); simulated underwriter about $0.0004 and judges about $0.0007 per case ($0.35 + $0.60 per setup); Modal sandboxes roughly $0.003-0.005 per trial of 1-2 minutes ($3-4 per setup; the checks' trials took 33 s each). Episodes took a median 15-48 s and a 95th percentile of 35-141 s per model in the original; with sandbox start-up (about 20-30 s, both images cached after the first build) and grading, plan on about 1 to 1.5 hours per setup at 4 concurrent trials, less at higher concurrency (watch the providers' rate limits). Check provider usage pages: the agent's cost comes from the vendored price table, which is unverified for open-weight models.

## How results map to the original numbers

- The benchmark's loop (`copilot-*` setups) keeps the original's model client, price table, system prompts, tool definitions and outputs, simulator, limits (30 model calls, 12 underwriter replies, two "Please continue." nudges), judges, tie-break and pass rule. Its accuracy over a set is comparable with the README's tables for the same model, prompt and cases: `copilot-first` on `tasks-full` with table 1, `copilot-first` and `copilot-shared` on `tasks-held` with table 2, the effort setups with table 3.
- What won't match exactly, and why:
  - Run-to-run noise: the original ran each case once, and its own repeat moved Sonnet 5.5 by 2.4 points on 168 cases. Harbor runs 5 attempts; compare per case (mean reward per case, paired bootstrap in `summarize.py`), not single numbers.
  - Models and providers change behind the same names, and the open-weight endpoint is whatever `provider-a` points at.
  - Copilot text sent alongside tool calls reaches the underwriter with the next question rather than as its own message (the original appended it to the underwriter's transcript at once; the underwriter reads it at its next reply either way).
  - Infrastructure errors: the original dropped harness errors and re-ran API errors; here they are reported apart by `summarize.py` and should be re-run.
- Off-the-shelf harnesses are new conditions. They get `instruction.md` (no "FINAL ANSWER:" protocol; they call `submit_final_answer`), their own system prompt, and no 30-call cap (only the server's 12-reply limit and the 30-minute agent timeout). Their numbers are a new baseline, not a rerun.
- The rewritten prompts were tuned on the 84 learning cases; report held-out numbers only from `tasks-held`.

## Spend while building this

All on 2026-10-22: 124 Modal trials (122 for the checks and a smoke run, plus two runs of the custom agent stopped before its first model call), about 4,100 sandbox-seconds, roughly $0.25-0.50 of Modal (estimated from sandbox time; the workspace bill is shared with other jobs); judges $0.0114 (about 100 judged answers); no simulator or agent model calls. Total well under $1.

## Limitations of the port

- Graded by LLM judges, as the original (87.5-90.0% agreement with Snorkel's labels per judge); the reward is a judged verdict on prose, not a recorded fact. A structured answer graded against the oracle's `gold` would remove judge noise but change what is measured.
- Shared verifier mode: the grader runs in the agent's container after the agent. Reward files are deleted first and the answer comes from the sidecar, but an agent with root in the main container could in principle tamper with its Python; the benchmark's own loop has no shell.
- Network is not restricted on Modal (see the four checks). Harbor's `--ek modal_vm_runtime=true` runs compose in a VM with a real Docker bridge instead of host networking; it was not tried here.
- Each task carries the database (xz, 1.1 MB); git stores the identical file once. The sidecar image is rebuilt per trial on Modal unless cached.
- No model agent has been run through the port yet; the custom agent was checked up to the first model call (install, upload, MCP connection from the main container, 8 tools listed).

Data: [Snorkel AI Multi-Turn Insurance Underwriting](https://huggingface.co/datasets/snorkelai/Multi-Turn-Insurance-Underwriting) and its Code-Gen variant (Apache-2.0); the database and guidelines in `tasks/` are derived from them and from US Census Bureau NAICS files (public domain) by `../scripts/fetch_data.sh`.
