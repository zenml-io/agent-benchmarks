# tau2-bench Telecom: public traces and Kitaru replays

Two connected studies on the Telecom domain of [tau2-bench](https://github.com/sierra-research/tau2-bench): a customer-service agent with 13 account tools helps a simulated customer, who runs the device actions (toggles, reboots, APN resets) on the agent's instructions. tau2 grades each conversation from the final environment state.

- **Part A, public traces** (`results/tau2-telecom-public-traces.json`): Exgentic's public recordings of tau2-bench Telecom (499 runs, 5 models, their `tool_calling` harness), plus a Kitaru model-swap step check that resent 160 recorded GPT-5.2 calls to GPT-5.2 itself and 7 newer models.
- **Part B, live Kitaru replay** (`results/tau2-telecom-kitaru-replay.json`): our own agent (PydanticAI, wrapped in Kitaru's `KitaruAgent`) recorded live with GPT-5.2 on tau2's 40-task Telecom test split, then replayed through Kitaru experiments: 7 model overrides, a no-override rerun (the noise floor) and a prompt-audit agent version.

## Question

If you swap the model behind a tau2-bench Telecom support agent, or fix its prompt, does it solve more tasks end to end, and does a cheap step-level screen on recorded calls predict which swaps will?

## Status

Complete (2026-10-22). Exgentic recorded Part A's runs between 2026-01-28 and 2026-04-21; we analyzed them and ran the step check on 2026-10-22. Part B was recorded and replayed on 2026-10-22.

Total spend is not known exactly. What was recorded:

| part | recorded spend (USD) | not recorded |
|---|---|---|
| A, step check (2 batches) | 9.30090395 (8.30271325 + 0.99819070) | one earlier run of the same step check as a Kitaru worker task (its result was discarded; spend unknown) |
| B, live runs and replays | 37.32938177 (OpenAI agent calls and the gpt-4.1 user simulator, all arms and setup sessions) | the open-weight arms' agent calls (Kitaru could not price them; tokens x unverified list prices give 34.124704 for the 4 arms) and some setup sessions |

Using the public recordings cost nothing. Sources: `results/costs/public_traces_step_check.json`, `results/costs/replay.json`.

## Results

All numbers below are copied from the two files in `results/`; each has its n. Accuracy is solved / n; intervals are Wilson 95%; paired differences are per-task bootstrap 95% intervals (10000 resamples, seed 0).

### Part A: Exgentic's recorded runs (tool_calling harness)

| model | n | solved | accuracy | 95% CI | cost per solved task (cents) | unsolved runs that ended in a transfer to a human |
|---|---|---|---|---|---|---|
| Kimi K2.5 | 100 | 83 | 0.8300 | 0.7445-0.8911 | 11.1763 | 11 of 17 |
| Claude Opus 4.5 | 99 | 75 | 0.7576 | 0.6646-0.8313 | 120.9685 | 23 of 24 |
| Gemini 3 Pro (preview) | 99 | 73 | 0.7374 | 0.6430-0.8140 | 40.3457 | 25 of 26 |
| DeepSeek V3.2 | 100 | 71 | 0.7100 | 0.6146-0.7899 | 6.9584 | 26 of 29 |
| GPT-5.2 | 101 | 54 | 0.5347 | 0.4379-0.6289 | 28.1922 | 32 of 47 |

One run per task per model; runs can't be paired across models (the dataset has no task id). Cost per solved task uses Exgentic's recorded `agent_cost` over all runs.

### Part A: step check on 160 recorded GPT-5.2 calls

Each sampled call was resent as recorded; "tool choice" is the share of calls where GPT-5.2 had called a tool and the candidate called the same tool. The paired difference is candidate minus GPT-5.2's own repeat, clustered over the 19 recorded runs the 75 shared calls come from.

| candidate | answered | tool choice (n) | rate | 95% CI | paired vs GPT-5.2 repeat (points) | 95% CI |
|---|---|---|---|---|---|---|
| GPT-5.2 (repeat of itself) | 141 | 63 / 75 | 0.8400 | 0.7408-0.9060 | reference | |
| GPT-5.6 Luna | 141 | 66 / 75 | 0.8800 | 0.7874-0.9356 | +3.5526 | -2.3684 to +10.5263 |
| Qwen3.8 27B | 160 | 72 / 86 | 0.8372 | 0.7451-0.9005 | -0.2632 | -7.2368 to +5.3947 |
| GPT-5.6 Sol | 141 | 62 / 75 | 0.8267 | 0.7257-0.8958 | -0.0940 | -3.5714 to +3.9474 |
| Kimi K3 | 160 | 67 / 86 | 0.7791 | 0.6805-0.8538 | -4.0789 | -9.6053 to +1.3158 |
| GLM-5.3 | 160 | 66 / 86 | 0.7674 | 0.6679-0.8441 | -6.5789 | -14.4737 to 0.0000 |
| GPT-5.4 mini | 141 | 57 / 75 | 0.7600 | 0.6522-0.8425 | -0.5326 | -11.1466 to +13.4586 |
| DeepSeek V4.1 Flash | 160 | 50 / 86 | 0.5814 | 0.4758-0.6800 | -25.3195 | -38.0702 to -13.2519 |

OpenAI rejected 19 of the 160 calls for every OpenAI model (a recorded tool-call id over its 64-character limit), so OpenAI candidates are scored on 141 calls and the others on 160.

### Part B: live agent on tau2's 40 test tasks, replayed through Kitaru

| arm | model | n | solved | accuracy | 95% CI | paired vs baseline (points) | 95% CI | gained / lost | agent cost per solved task (cents) |
|---|---|---|---|---|---|---|---|---|---|
| baseline (recorded live) | GPT-5.2 | 40 | 27 | 0.6750 | 0.5202-0.7992 | | | | 8.7168 |
| noise floor (replay, no override) | GPT-5.2 | 40 | 27 | 0.6750 | 0.5202-0.7992 | 0.0 | -17.5 to +17.5 | 6 / 6 | 9.8785 |
| prompt-audit rule | GPT-5.2 | 40 | 29 | 0.7250 | 0.5716-0.8389 | +5.0 | -12.5 to +22.5 | 8 / 6 | 9.0142 |
| override | GLM-5.3 | 40 | 39 | 0.9750 | 0.8712-0.9956 | +30.0 | +17.5 to +45.0 | 12 / 0 | 20.6809* |
| override | Qwen3.8 27B | 40 | 36 | 0.9000 | 0.7695-0.9604 | +22.5 | +7.5 to +37.5 | 10 / 1 | 9.0878* |
| override | DeepSeek V4.1 Flash | 40 | 35 | 0.8750 | 0.7389-0.9454 | +20.0 | +7.5 to +32.5 | 8 / 0 | 6.1307* |
| override | GPT-5.6 Sol | 40 | 33 | 0.8250 | 0.6805-0.9125 | +15.0 | 0.0 to +32.5 | 9 / 3 | 12.3138 |
| override | Kimi K3 | 40 | 32 | 0.8000 | 0.6524-0.8950 | +12.5 | -2.5 to +27.5 | 7 / 2 | 64.5057* |
| override | GPT-5.6 Luna | 40 | 22 | 0.5500 | 0.3983-0.6929 | -12.5 | -30.0 to +5.0 | 5 / 10 | 0.7922 |
| override | GPT-5.4 mini | 40 | 19 | 0.4750 | 0.3294-0.6250 | -20.0 | -37.5 to -2.5 | 3 / 11 | 3.6496 |

\* tokens x unverified third-party list prices (Kitaru recorded these sessions' cost as 0; see Trust status). OpenAI costs are Kitaru's recorded session cost. The gpt-4.1 user simulator's cost is excluded from cost per solved task.

Unsolved episodes that ended in a transfer to a human: baseline 10 of 13, GPT-5.6 Luna 18 of 18, GPT-5.4 mini 14 of 21. Does the step screen predict the replay ranking? Spearman between Part A tool-choice rate and Part B accuracy over the 7 override models: -0.0714 (n = 7).

## Trust status

**Reproduced on 2026-10-22, by running the commands in RERUN.md from this directory in a fresh uv environment:**

- Part A, every table: fetched the 9 public shards (checksums in `scripts/data.sha256`), ran `scripts/build_tau2_public.py`, and compared with the original export. All numbers match exactly; the only differences are the provider label and the commit field listed under "Changes from the original run" in RERUN.md. A separate 10-line count straight from the Parquet files (success by model) gives the same 499 runs and solve counts.
- Part A step check: the rates and paired intervals are rebuilt from the per-call rows in `results/runs/step_check/` (the build recomputes each rate and compares it with the analyzer's own report: they agree to the 4th decimal).
- Part B, every table: rebuilt from the 400 per-episode rows in `results/runs/replay/replays.jsonl` with `scripts/build_tau2_replay.py`; identical to the original export. The 40 baseline rewards in the run log (`baseline.jsonl`) match the rewards Kitaru stored. Every row's tau2 task id matches the task at that index of tau2's test split at commit 05736c2 (checked by loading the split with the pinned tau2).

**Not reproduced:** nothing that calls a model was re-run, so the outcomes themselves (Exgentic's success labels, our 400 episodes, the step-check replies) are taken as recorded. The Kitaru server state behind `replays.jsonl` (sessions, experiments) is not public; the rows are what `collect_replays.py` read from it.

**Known inconsistencies** (from the export's `inconsistencies`, plus ones found while porting):

- Exgentic's dataset card says 10,057 runs; the 9 shards hold 10,056 rows. The card says model names in spans are canonical with zero mismatches; in this slice 1,633 Claude spans and 1,410 Gemini spans have no response model and 74 Claude spans carry a Bedrock model id.
- Two GPT-5.2 rows carry a Claude or Gemini `config_path`; they are counted under the model their spans name. 288 rows have status `unknown` while `success` is set (195 true, 93 false); `success` is used.
- Kitaru's post-import insights card on a 125-run sample claimed 6 models (there are 5) and "100% of sessions include correction language" (the policy text in the first message matches the pattern). The model-swap report says the calls have no system prompt; the policy arrives as the first user message.
- An earlier chat summary said GPT-5.2 solved 15 of 25 sampled runs (0.6000); on all 101 runs it solved 54 (0.5347).
- GPT-5.2 scores 0.5347 (54/101) in Exgentic's harness and 0.6750 (27/40) in ours: different harness, user simulator (theirs unknown, ours gpt-4.1) and task set. Harbor's tau3-bench adapter reports pass^1 0.8275 for GPT-5.2 on all 114 Telecom tasks with yet another agent and a GPT-5.2 user simulator. These numbers are not comparable to each other.
- Kitaru recorded session cost 0 for the open-weight arms although every model call's cost was null (unpriced calls roll up as 0); the export recomputes those costs from tokens.
- Found while porting: arms are not identical apart from the model. The baseline ran agent version 1 (direct to OpenAI, chat completions); the noise and model arms ran version 3 (through `model_router.py`); the prompt arm ran version 2; and the GPT-5.6 and GPT-5.4 mini overrides used PydanticAI's `openai-responses:` model prefix (the Responses API) while GPT-5.2 used `openai:` (chat completions). The noise arm (version 3, GPT-5.2) matching the baseline's accuracy suggests the router itself changes little, but that rests on one rerun.
- Found while porting: the export says the prompt-audit rule was written before any test-split episode ran. The data can't confirm this: the prompt arm's sessions start about 23 minutes after the baseline's, and the rule's authoring time is not recorded.

**How far to trust each claim:**

- The noise floor is wide: GPT-5.2 rerun with nothing changed gained 6 tasks and lost 6. Any arm within about +/-17.5 points of the baseline is not distinguishable from rerun noise on 40 tasks. The prompt-audit rule (+5.0) and GPT-5.6 Luna (-12.5) are inside it; GPT-5.6 Sol's interval touches 0.
- GLM-5.3, Qwen3.8 27B and DeepSeek V4.1 Flash beat the baseline with intervals clear of zero, but each is one episode per task on 40 tasks, against one baseline recording.
- The step-screen vs replay comparison has n = 7 and uses different recordings (Exgentic's harness) from the replays; read it as "no evidence the screen ranks models", not as evidence against it.
- Open-weight costs use unverified third-party list prices.

**Steps that would vet it further:**

1. Rerun the baseline and the noise arm 2 more times each (about $22 at the recorded per-arm spend, agent plus user simulator) to see how far GPT-5.2's 27/40 moves; report pass^k per task.
2. Rerun the GLM-5.3 and Qwen3.8 27B arms twice each (about $32 at the recorded tokens and list prices), on a second provider too, with pinned model versions, to check the +30 and +22.5 point gains are not provider- or sample-specific.
3. Hand-read 20 transfer-to-human episodes across arms and check that tau2's reward 0 reflects a solvable task the agent gave up on, not a simulator error.
4. Rerun the GPT-5.2 arms through the same agent version and API (one version, all through the router, chat completions for every OpenAI model) to remove the version and API confounds.
5. Run the step check on recordings from our own harness (Part B's baseline sessions) so the screen and the replays share a harness, with all 7 candidates on the same call set.
6. Spot-check 10 Exgentic runs per model by reading the conversation against the `success` label.

## Harbor status

**Partly native** (Part B). `harbor/` runs Part B as a Harbor job; see [harbor/README.md](harbor/README.md) for commands, cost and how results map to the tables above.

- **Tasks:** the 40 test-split tasks (`harbor/tasks/`, dataset `zenml/tau2-telecom-test40` in the repository's `registry.json`), generated from Harbor's `adapters/tau3-bench` (the source of `sierra-research/tau3-bench` on the Harbor hub) with tau2-bench pinned to 05736c2, the gpt-4.1 user simulator, tau2's 100-step limit and the original's substring communicate scoring. tau2's tools and simulated user run in an MCP sidecar; tau2's `evaluate_simulation` grades. The generator also fixes a grader failure in the adapter as published: against tau2-bench from 2026-10-19 on, its grader raises on every attempt (a newly required `communicate_scoring` argument) and scores 0.
- **Agent:** the original PydanticAI agent as a custom Harbor agent (`import_path: tau2_kitaru_harbor.agent:Tau2KitaruAgent`), model and prompt rule as settings, tools from the task's MCP sidecar. Kitaru records inside the trial to a local sink whose files Harbor collects with the trial (the pinned Kitaru can only record to a server; `harbor/scripts/upload_recordings.py` loads the recordings into one later). Arms are config files; Kitaru replays are replaced by Harbor running every arm fresh, with one agent version for all arms.
- **Checked (free):** oracle 5/5, nop 0, shortcuts 0 and one alternative solution 1 through Harbor on Modal for all 40 tasks; 89 offline tests (grader on all 40 tasks, the agent end to end with a scripted model and customer, the recording). Details in harbor/README.md.
- **Left:** no arm has run with a model. The first paid comparison (GPT-5.2 baseline and rerun, GLM-5.3, Qwen3.8 27B, GPT-5.6 Sol on the 40 tasks) is one command in harbor/README.md, about $40 and 2.5 hours (estimated). The graded conversation log sits in a folder the agent's container can write, which is safe for this agent (MCP tools only) but not for shell agents.

Part A (the public traces and the step check) has no agent run to port: it analyzes recordings.

## Limitations

- 40 tasks per arm and one episode per task in Part B; one run per task per model in Part A. Intervals are wide.
- Part A's runs can't be paired by task across models (no task id in the public data).
- The step check measures similarity to GPT-5.2's recorded replies, not correctness. Recorded tool definitions have empty parameter schemas, so candidates saw tool names and descriptions only. 9 of 1,057 recorded GPT-5.2 calls were skipped for a missing tool schema. The recorded GPT-5.2 settings are not in the data; the step check used provider defaults.
- Only GPT-5.2 among the recorded models could be resent, so step agreement could not be compared with recorded outcomes for the other four.
- Issue types (Part A) and the `claimed_no_device_access` category come from text matching, not human labels.
- Part B's agent is ours (PydanticAI with a `send_message_to_user` tool), not tau2's built-in agent; numbers are not comparable to the tau2 leaderboard. The user simulator is an LLM (gpt-4.1). Model settings are provider defaults. Replays start each task fresh (a new full run), they do not continue the recorded conversation.
- Open-weight models ran on one commercial provider (here `provider-a`) through a local router that strips one provider-specific response field; their costs use unverified prices.
- Kitaru (server, worker, the PydanticAI adapter and the model-swap analyzer) ran from an unreleased branch; see Provenance.

What is not in this repository and why:

- The Exgentic Parquet shards (about 232 MB): the dataset declares no license, so `scripts/fetch_data.py` downloads them and they stay git-ignored. For the same reason, the committed step-check rows keep only tool names, agreement labels, costs and latencies: recorded arguments and text, the candidates' reply text, the analyzer's disagreement examples and its `insights.json` are left out (`scripts/strip_step_check.py` shows exactly what was kept).
- Part B's transcripts and the Kitaru server database: the rows in `results/runs/replay/` hold per-episode outcomes, tool names, token counts and costs, not conversations.
- The private script importer that loaded Exgentic runs into Kitaru for the step check (one Kitaru session per run, one `llm_call` node per chat span): not published, so the step check's first step (import) can't be rerun from this repository.

## Provenance

- Original code: `benchmarks/tau2-telecom-public/` in the private research repository, commits c2bb92e93b865db6ae686adff8bc0281a79c4d31 (Part A, 2026-10-22) and b6ed9ae92115616fd69dbe50a0fe995a49c6b6a6 (Part B, 2026-10-22); exports built by `benchmarks-export/scripts/build_tau2_public.py` and `build_tau2_replay.py` there.
- Run by Hamza Tahir (ZenML), with Claude Code agents.
- Kitaru: [zenml-io/kitaru](https://github.com/zenml-io/kitaru) branch `feature/model-swap-analyzer` at 0217140c9bd6fc1b0569abefbaea30be20a6fde4 (kitaru 0.27.2+dev; plugins kitaru-pydantic-ai 0.3.1 and kitaru-model-swap 0.1.0 from `plugins/packages/` in the same commit; the analyzer came from the then-unmerged zenml-io/kitaru#1327). PydanticAI 2.51.0.
- tau2-bench: [sierra-research/tau2-bench](https://github.com/sierra-research/tau2-bench) at 05736c27219b769d0be507574dd3135010916644 (2026-10-21, package `tau2` 2.0.0), MIT license.
- Public traces: [Exgentic/agent-llm-traces-v2](https://huggingface.co/datasets/Exgentic/agent-llm-traces-v2) at revision 4b8ad4ab198438e5a170f9171c19c6a2cf7c1814, no license declared.
