# The claims-review agent

A PydanticAI port of the claims agent in `benchmarks/decision-agents/harness/claims_bench.py` (its base condition), recorded through Kitaru. It reviews one California IMR appeal: it reads the case and the medical records, searches past decisions, and submits `uphold` or `overturn`.

**One directory is one agent version.** To make a new version, copy this directory and edit the copy. Keep the copy's directory name `claims_agent`, because it runs as `python -m claims_agent.episode` from the directory that contains it.

| file | what it holds |
|---|---|
| `prompt.md` | the system prompt, sent exactly as written (its line breaks are part of the prompt) |
| `tools.json` | the four read tools and the final answer `submit_determination`: names, descriptions, argument schemas, in OpenAI function format |
| `config.toml` | model, model settings (temperature, max tokens), request limit, tool result length, the nudge message |
| `agent.py` | what the tools return (`Env.call`) and how the PydanticAI agent is built |
| `episode.py` | runs one appeal and prints one JSON row; not part of the agent's behavior |

The appeal data is not in this directory. Every copy reads `cases.jsonl` and `precedents.jsonl` from `$CLAIMS_WORK_DIR`, so all versions see the same appeals and the same precedent library.

## Run it

All commands run from `benchmarks/claims-over-time/` with the `agent` extra installed.

| variable | used for |
|---|---|
| `CLAIMS_WORK_DIR` | directory with `cases.jsonl` and `precedents.jsonl` (required) |
| `CLAIMS_AGENT_BASE_URL` | base URL of the OpenAI-compatible server when `config.toml` sets `base_url_env` to this name (the vLLM servers serve `agent-model`) |
| `CLAIMS_AGENT_API_KEY` | key for that server, if it needs one (default `EMPTY`) |
| `OPENAI_API_KEY` | when `config.toml` names an OpenAI model directly, for example `model = "openai-chat:gpt-5-mini"` and `base_url_env = ""` |
| `KITARU_AGENT_ID`, `KITARU_AGENT_VERSION_ID` | record a session outside a worker (a worker supplies both) |

One appeal, no Kitaru (prints the row):

```bash
cd harness && CLAIMS_WORK_DIR=$PWD/../work uv run --extra agent python -m claims_agent.episode MN25-43855 --local
```

A batch, or a list of ids, with any copy of the package (rows go to `$CLAIMS_WORK_DIR/runs/<tag>.jsonl`; a rerun skips appeals that already have a row):

```bash
uv run --extra agent python scripts/run_batch.py --agent-dir harness/claims_agent --tag v1-b1 --batch 1
uv run --extra agent python scripts/run_batch.py --agent-dir path/to/copy/claims_agent --tag v2-revealed --batch 1 --revealed-only
uv run python scripts/score.py $CLAIMS_WORK_DIR/runs/v1-b1.jsonl
```

With `--kitaru-agent-version <id>` instead of `--agent-dir`, `run_batch.py` asks the Kitaru server for one session run per appeal, a worker runs the registered version, and the row comes back as the task result (plus `session_id` and Kitaru's cost).

The row has `case_id`, `final` (the submitted answer, or null), `turns` (model calls), `calls`, `seen_precedents`, `usage`, `cost_usd` (null when no price is known, as for a self-hosted model), `run_error`, `agent_version` (a hash of this directory's files), `agent_dir` and the full `transcript`.

## How faithful the port is

Checked on 2026-10-27 against `claims_bench.py`, with scripted PydanticAI `FunctionModel` runs and a fake OpenAI-compatible server that recorded the request bodies:

- **Same:** the system prompt; the user message `Review appeal <id>.`; the five tool definitions on the wire (compared as JSON with the original `TOOLS`, identical); what the four read tools return, including that `get_case` and `get_medical_records` ignore their `case_id` argument and answer for the appeal under review; tool results as `json.dumps(result)[:6000]`; `seen_precedents` collected from the uncut results; the final answer is the `submit_determination` arguments, not validated, as in the original; at most 12 model calls (a 13th is refused and the appeal is undecided); temperature 0.6 and 4096 max tokens; `tool_choice` left at `auto`; on the self-hosted path, the request sends `max_tokens` (not `max_completion_tokens`) and never sends the server's separate reasoning text back.

Behaviors PydanticAI does not reproduce exactly:

| original | here | effect |
|---|---|---|
| a text answer with no tool call gets the user message `Use the tools, and finish with submit_determination.` | the same text goes back as a PydanticAI retry, which wraps it: `Validation feedback:` + the nudge + `Fix the errors and try again.` | the model sees a slightly longer nudge; it still counts against the 12 calls |
| tool arguments that are not valid JSON become `{}` and the tool runs anyway | PydanticAI sends a retry asking the model to fix the call | one extra model call in that rare case |
| an unknown tool name returns `{"error": "unknown tool X"}` | PydanticAI sends a retry naming the available tools | same, rare |
| tools called after `submit_determination` in the same reply are skipped; tools before it run | PydanticAI's default `graceful` end strategy runs every read tool in that reply, then ends | only `seen_precedents` can gain ids the model never saw before deciding |
| an assistant message with only tool calls has `content: ""` | `content: null` | none expected |
| requests to the vLLM server omit `tool_choice` and `stream` | they send `tool_choice: "auto"` and `stream: false`, the server defaults | none expected |
| the run ends after 12 turns with no error | the run ends with `UsageLimitExceeded`, recorded in `run_error`, and the Kitaru session is marked failed | `final` is null either way; the evaluator scores it 0 |
| one session per call to `session()`; transcript as raw chat messages | one Kitaru session per appeal; transcript as PydanticAI messages | none for scoring |

With an OpenAI reasoning model such as `gpt-5-mini`, OpenAI rejects a temperature other than 1, so PydanticAI drops `temperature` with a warning; `max_tokens` becomes `max_completion_tokens`, which includes reasoning tokens.

Under a Kitaru replay or experiment, the run's prompt is the recorded session input, not what `episode.py` passes, so the user message is part of the protocol and lives in `episode.py`, not in `config.toml`.

## Kitaru: verified command sequence

Run on 2026-10-27 (macOS arm64, Kitaru 0.27.2, kitaru-pydantic-ai 0.3.1, Docker Desktop) against an isolated local server, with the dev fixtures in `work/dev/` and `gpt-5-mini`. `KITARU_CONFIG_DIR` keeps the CLI's server and credentials out of your own Kitaru configuration (the variable is read by `kitaru.client.config`; it is not in the published docs). Output trimmed.

```bash
cd benchmarks/claims-over-time
BENCH=$PWD
export KITARU_CONFIG_DIR=/some/scratch/kitaru-config      # isolated CLI config
export CLAIMS_WORK_DIR=$BENCH/work/dev                    # dev fixtures; the real run uses $BENCH/work
export OPENAI_API_KEY=...                                 # in the shell only

# Two agent versions as two directories: v1 is this package with gpt-5-mini, v2 adds one prompt line.
mkdir -p work/dev/agents/v1 work/dev/agents/v2
cp -R harness/claims_agent work/dev/agents/v1/
sed -i '' 's/^model = "agent-model"/model = "openai-chat:gpt-5-mini"/; s/^base_url_env = .*/base_url_env = ""/' work/dev/agents/v1/claims_agent/config.toml
cp -R work/dev/agents/v1/claims_agent work/dev/agents/v2/
echo "Before deciding, read the full text of at least two precedents for the same treatment." >> work/dev/agents/v2/claims_agent/prompt.md

# Local server (Docker); pick a free port.
uv run --extra agent kitaru login --local --port 8471 --no-browser --non-interactive
#   "server_url":"http://localhost:8471", "server_image":"zenmldocker/kitaru-server:0.27.2", "deployment":"created", "auth_scheme":"none"

# (a) Register the agent; its first version runs the v1 directory.
uv run --extra agent kitaru agent register claims-agent-dev \
    --command "uv run --quiet --project $BENCH --extra agent python -m claims_agent.episode" \
    --working-dir "$BENCH/work/dev/agents/v1" --env CLAIMS_WORK_DIR=$CLAIMS_WORK_DIR
#   agent id 01a17ddc-903e-..., version 1 id 01a17ddc-9055-7d33-94c5-f8d2af541b78

# A worker runs the agent and the evaluator, with the model key and CLAIMS_WORK_DIR in its environment.
uv run --extra agent kitaru worker start --concurrency 3 &

# (b) Record 3 appeals as sessions: one session run per appeal, executed by the worker.
uv run --extra agent python scripts/run_batch.py --tag dev-kitaru-v1 \
    --ids MN25-43855,EI25-43558,MN25-45578 --kitaru-agent-version 01a17ddc-9055-7d33-94c5-f8d2af541b78
#   MN25-45578 uphold 5 / EI25-43558 uphold 7 / MN25-43855 overturn 5     (decision, model calls; 32 s)
uv run --extra agent kitaru session list --agent claims-agent-dev --include-payloads
#   3 sessions, status completed, origin recorded, inputs 'Review appeal <id>.', cost $0.0023-0.0052 each

# (c) Register the evaluator (scoped to the agent).
uv run --extra agent kitaru evaluator register claims-decision-correct --script harness/evaluator.py \
    --entrypoint evaluate --agent-id 01a17ddc-903e-7e30-8d84-9d83d54a2d66
#   version 1

# (d) A cohort of the 3 recorded sessions (session ids from the rows).
python3 -c "import json; print('\n'.join(json.loads(l)['session_id'] for l in open('work/dev/runs/dev-kitaru-v1.jsonl')))" > work/dev/runs/dev-kitaru-v1.sessions
uv run --extra agent kitaru cohort create claims-dev-baseline --agent claims-agent-dev --sessions-file work/dev/runs/dev-kitaru-v1.sessions
#   claims-dev-baseline@1, cohort version id 01a17ddd-d0c2-7ad0-a3f9-e8dccdb80e97, session_count 3

# (e) Register v2 (the copied directory) and run it as an experiment on the cohort.
uv run --extra agent kitaru agent version register claims-agent-dev \
    --command "uv run --quiet --project $BENCH --extra agent python -m claims_agent.episode" \
    --working-dir "$BENCH/work/dev/agents/v2" --env CLAIMS_WORK_DIR=$CLAIMS_WORK_DIR
#   version 2
uv run --extra agent kitaru experiment create claims-dev-v2-prompt --agent claims-agent-dev \
    --evaluator claims-decision-correct@1 --tool-policy '{"default":{"type":"passthrough"}}'
uv run --extra agent kitaru experiment run start claims-dev-v2-prompt --cohort-version 01a17ddd-d0c2-7ad0-a3f9-e8dccdb80e97 \
    --agent claims-agent-dev@2 --baseline-evaluation-mode if_missing --wait --timeout 900
#   "status": "completed", "progress": {"completed": 3, "failed": 0, "total": 3}    (33 s)

# (f) Read the scores back: 3 replays (v2) and the 3 baselines (v1).
uv run --extra agent kitaru evaluation list --size 50
#   claims_decision_correct 1.0 True  MN25-43855: decided overturn, truth overturn   (replay)
#   claims_decision_correct 1.0 True  EI25-43558: decided uphold, truth uphold       (replay)
#   claims_decision_correct 1.0 True  MN25-45578: decided uphold, truth uphold       (replay)
#   ... and the same three lines for the baseline sessions
uv run --extra agent kitaru replay list
#   3 replays, status completed, each baseline session -> a new result session

# Clean up: stop the worker (Ctrl-C, or kill -INT), then stop the server and delete its data.
uv run --extra agent kitaru logout --volumes --non-interactive
```

The replay sessions' first model call carried v2's extra prompt line, and the read tools ran live (`passthrough`); the baselines did not have the line. The 0 branches of the evaluator (wrong decision, no decision) were checked offline, not in this run: all 6 sessions happened to be right.

Notes:

- The worker passes its own environment to the agent and evaluator processes, so `CLAIMS_WORK_DIR` and the model key go in the worker's environment. `--env` on the agent version is stored on the server: never put keys there.
- The tool policy must be `passthrough`: a replay of a changed agent makes tool calls the recording does not have, and the default `history` policy would fail them.
- `kitaru login --local` uses a fixed Docker Compose project name (`kitaru-local`), so only one CLI-owned local server can exist per Docker engine. If you already have one, use it, or log out of it first.
- If Docker's default context is not the engine you want, set `DOCKER_CONTEXT` for the `login` and `logout` commands.

## Dev fixtures

`work/dev/` (not committed) holds 5 eligible 2025 appeals (3 overturned, 2 upheld, picked with `random.Random("dev-fixtures")`) whose case files were extracted with the original `EXTRACT` prompt by `gpt-5-mini`, plus `precedents.jsonl` built with the original logic (identical to `work/precedents.jsonl`). They exist only to test the harness; `work/dev/build_dev_fixtures.py` rebuilds them. The real run uses the case files the Qwen extraction produces.
