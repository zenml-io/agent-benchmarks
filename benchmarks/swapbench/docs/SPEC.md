# SwapBench v1 specification (draft, Oct 13 2026)

**The task given to an agent:** here is a production agent running on a frontier model, plus its
recorded traces. Cut its serving cost by at least 50% (cheaper API model, open model, prompt change
or distilled model) without regressing it. Then **declare** whether the swap is safe.

**The score:** we replay the submitted configuration on a hidden set of scenarios and check both
the savings and the declaration.

v1 scope: 12 tasks (plus 2 stretch), two arms, about 4 weeks for a small team.

## 1. Tasks

Every task is a multi-turn, tool-using agent. A task ships:
- **Agent code:** system prompt, tool schemas, loop.
- **Mock layer:** see section 3.
- **Visible traces:** the incumbent on scenarios the agent may see.
- **Hidden scenarios:** they never enter the sandbox, and each has ground truth.
- **Incumbent baseline:** quality and $/episode on the hidden set.

| # | Task | Source (license) | Agent / tools | User | Ground truth |
|---|---|---|---|---|---|
| 1 | `retail-refunds`: cancel, return, exchange, modify orders | tau2-bench retail (MIT) | 16 tools over an order DB | LLM sim | Final DB state + required actions |
| 2 | `airline-changes`: rebook, cancel, baggage, compensation | tau2 airline (MIT) | 14 tools | LLM sim | Final DB state |
| 3 | `telecom-troubleshoot`: dual control, the user acts on their own device | tau2 telecom (MIT) | Agent and user tools | LLM sim | Final device + DB state |
| 4 | `bank-policy-support`: answers need policy retrieval | tau2 banking_knowledge (MIT); we define the split | Retrieval + account tools | LLM sim | DB state + required facts |
| 5 | `workplace-ops`: email, calendar, CRM, analytics | WorkBench (MIT) | 26 tools, 5 sandbox DBs | none | Final sandbox state; harmful side effects counted |
| 6 | `sql-analyst`: answer business questions over SQLite | BIRD mini-dev (CC-BY-SA) + local Spider2 subset (MIT) | `list_tables`, `describe`, `run_sql`, `answer` | none | Execution match |
| 7 | `deep-research`: multi-hop questions over a frozen corpus | BrowseComp-Plus (MIT) | BM25 `search`, `open_doc`, `answer` | none | Exact answer. Shipped frontier trajectories serve as incumbent traces. |
| 8 | `invoice-extraction`: extract, validate, fix fields, submit | CORD v2 (CC-BY-4.0) | `ocr_text`, `lookup_vendor`, `validate_schema`, `submit` | none | Field-level F1 |
| 9 | `contract-review`: find and classify risky clauses | CUAD (CC-BY-4.0) | `search_contract`, `get_section`, `flag_clause` | none | Clause span F1 |
| 10 | `ticket-triage`: route, enrich, escalate | Banking77 + CLINC150 OOS (CC-BY) wrapped as tools | `lookup_customer`, `route`, `escalate`, `reply` | scripted | Route label + escalation correctness |
| 11 | `booking-voice`: appointment/restaurant booking with ASR-noisy turns | tau2 voice task variants, text mode (MIT); alt: SGD (CC-BY-SA) | Booking tools | LLM sim with ASR noise | Final booking state |
| 12 | `multi-api`: long multi-turn API sessions with missing parameters | BFCL v3 multi_turn_base + miss_param (Apache-2.0) | Simulated file system, trading, travel APIs | scripted turns | State + response checks |
| S1 | `app-assistant`: cross-app personal tasks | AppWorld test_normal (Apache-2.0, encrypted redistribution) | 457 APIs | none | State unit tests |
| S2 | `travel-booking`: complex nested calls | ComplexFuncBench (Apache-2.0); responses recorded once, then replayed | Booking API | none | Call match |

Excluded from v1:
- CRMArena: non-commercial license, needs a live org.
- WorkArena: needs a live ServiceNow.
- SROIE, FUNSD, DocVQA: licenses unclear.

**Contamination.** Tasks 1-3, 6, 10 and 12 are public and heavily trained on. We report
incumbent-vs-candidate **deltas**, never absolute scores. Hidden sets are freshly generated (section 5),
so knowing the public test split doesn't help.

**Incumbents.** One frontier model per task, chosen from what teams actually run:
- `gpt-5-2025-08-07`: scheduled for removal Dec 11 2026, which matches the forced-migration story;
- Claude Sonnet 5.5;
- GPT-6.1 Sol.

## 2. Trace format: OpenTelemetry GenAI conventions, as OTLP-JSON lines

One trace per episode. We follow the OTel GenAI semantic conventions
(<https://github.com/open-telemetry/semantic-conventions-genai>). These are still marked
*Development*, so we pin the commit. A converter (`swapbench/trace.py`) emits them from the native
logs of each environment. Teams can ingest their own production traces with any OTel exporter.

Spans:
- `invoke_agent <agent>`, the root. Attributes:
  - `gen_ai.agent.name`, `gen_ai.conversation.id`
  - `swapbench.task`, `swapbench.scenario_id`, `swapbench.split`, `swapbench.trial`
  - `swapbench.reward` (0 to 1), `swapbench.outcome.*` (e.g. `db_match`, `harmful_writes`)
- `chat <model>`, one per model call. Attributes:
  - `gen_ai.operation.name=chat`, `gen_ai.provider.name`, `gen_ai.request.model`, `gen_ai.response.model`
  - `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read.input_tokens`, `gen_ai.usage.reasoning.output_tokens`
  - `gen_ai.input.messages`, `gen_ai.output.messages`, `gen_ai.system_instructions`, `gen_ai.tool.definitions`
  - `swapbench.cost_usd` (from a pinned price table)
- `execute_tool <name>`. Attributes: `gen_ai.tool.name`, `gen_ai.tool.call.id`,
  `gen_ai.tool.call.arguments`, `gen_ai.tool.call.result`, `swapbench.tool.kind` (read/write),
  `swapbench.mock.source` (simulator | recorded | synthesized).
- Simulated-user turns are `chat` spans with `gen_ai.agent.name=user_simulator`. They are excluded from the agent's cost.

Files are `traces/<split>/<scenario>__t<trial>.otlp.json`. An `index.jsonl` holds one summary line
per episode: reward, cost, turns, tool calls, termination.

## 3. Mock layer (tools)

Three tiers, from most to least preferred:
1. **Stateful simulator.** Tools are deterministic functions over a seeded DB, as in tau2, WorkBench and BFCL. Any call sequence is valid, so a candidate may take paths the incumbent never took.
2. **Record-replay.** Responses are keyed by canonical `(tool, sorted-args)` and recorded from the real tool once (tasks 7 and S2).
3. **Synthesized.** An LLM fabricates the response for an unseen call. It is flagged `mock.source=synthesized`. Such episodes are reported but **excluded** from scoring. v1 tasks are chosen so tier 3 is rare.

The simulated user is pinned per task: model, prompt and decoding. It comes from a different vendor
than the incumbent and the candidates, so it can't favour its own family. In v1 that is Claude Haiku
5.5 for OpenAI incumbents.

## 4. What the agent submits

`submission/config.yaml` defines the new production agent:
- `model`, `provider`/`base_url`, decoding params;
- optional system-prompt or tool-description edits;
- optional weights URI plus a serving recipe, for distilled or open models served on a GPU.

`submission/verdict.json` has these fields:
- `decision`: `SAFE`, `UNSAFE` or `INSUFFICIENT_EVIDENCE`
- `expected_cost_reduction`
- `expected_quality_delta` with an interval
- `known_breakages`: what they found
- `evidence`: free text

Both files are written before grading and are immutable afterwards.

## 5. Holdout protocol

Each task has four scenario sets, all drawn from the same distribution:

| Set | Size | Who sees it |
|---|---|---|
| **V** (visible) | ~30% | Incumbent traces, k=1-2 per scenario. The agent may run candidates on V through the mock layer. |
| **S** (sealed) | ~20% | Only through arm 2's holdout-vault tool: aggregate deltas with CIs, at most 3 queries. Never part of the score. |
| **H** (hidden) | ≥200 scenarios | Grader only. Never in the sandbox, never queryable. |
| **H-tail** | ≥50 | Grader only. Rare intents, long conversations, adversarial users. Reported as "what breaks", not used for the verdict truth. |

**Fresh scenarios.**
- **tau2 domains:** we generate new scenarios by re-instantiating task templates over new DB entities. The expected end state comes from executing the gold action sequence, so ground truth holds by construction.
- **Other sources:** we use the unreleased splits, plus perturbations.
- **Canaries:** every hidden file carries a canary GUID.

**Isolation.**
- The sandbox's network egress is limited to the metered model gateway (section 7), a package mirror and, if the run has GPU budget, a GPU allocation. There is no route to GitHub, so the public benchmark repos can't be cloned.
- All model calls go through the gateway, which logs them. Any request that matches a hidden scenario is flagged as a leak.

**Ground truth per submission.**
- The grader runs the submitted config on H with k=4 trials per scenario and compares it with the incumbent on H (k=4, precomputed).
- **Quality delta** Δ = pass^1(candidate) − pass^1(incumbent). The CI is a paired bootstrap, resampling scenarios with their trials (cluster bootstrap).
- **Truth label**, with non-inferiority margin δ = 3 points:

| Label | Condition |
|---|---|
| **REGRESSED** | Δ̂ ≤ −δ, **or** harmful-write rate (a write the gold sequence doesn't contain, e.g. a refund to the wrong method) rises by more than 1 point with 95% confidence |
| **NON-INFERIOR** | lower 95% bound of Δ > −δ, and no harm increase |
| **AMBIGUOUS** | neither: the CI straddles. Reported, and excluded from false-safe denominators. Large H keeps this rare. With n=200 scenarios and k=4, the SE of Δ is about 2 points. |

## 6. Scoring

Per run:
- **cost_reduction** = 1 − ($/episode of the submission on H) / ($/episode of the incumbent on H).
  - API models: token usage × the pinned price table.
  - Self-hosted models: GPU $/h × wall time ÷ episodes, at a stated concurrency. Training cost is reported separately and amortized over 100k episodes.
- **declaration vs truth.**
  - **False-safe:** declared SAFE, truth REGRESSED.
  - **Missed savings:** declared UNSAFE or INSUFFICIENT, truth NON-INFERIOR with cost reduction ≥ 50%.

Per arm (over runs and tasks):
- **False-safe rate (headline)** = #(SAFE ∧ REGRESSED) / #(SAFE ∧ not AMBIGUOUS). This is the probability that a "safe to switch" answer is wrong. We also report #(SAFE ∧ REGRESSED) / #runs.
- **Realized savings** = mean over runs of:
  - cost_reduction, if SAFE ∧ NON-INFERIOR;
  - −1, if SAFE ∧ REGRESSED (a bad ship costs as much as running the incumbent for the period);
  - 0, otherwise (the team stays on the incumbent).
- **Calibration:** coverage of true Δ by the claimed interval; ECE of the claimed decision.
- **Effort:** coding-agent tokens ($), candidate-inference $, GPU-hours, wall time.

Reference strategies are computed once per task:
- *keep*: always INSUFFICIENT;
- *naive*: the cheapest model with ≥50% savings, always SAFE;
- *oracle*: the best non-inferior config from the reference sweep.

Statistics:
- At least 4 runs per arm × agent × task.
- Arm differences use a paired bootstrap over tasks and runs.
- We publish every run, including those where arm 2 loses.

## 7. The two arms

Shared across both arms:
- **Agents:** the same coding agent and model (Claude Code + Sonnet/Opus 5.5; Codex + GPT-6.1 Sol), the same instruction, 4 h wall.
- **Inference budget:** $25 of candidate inference through the **metered gateway**, an OpenAI-compatible proxy. It holds the real keys outside the sandbox, enforces the budget, logs every call, and serves open models from a GPU pool.
- **GPU budget:** 4 H100-hours, available as a GPU attached to the sandbox.
- **Agent code and traces:** a runnable copy of the agent and the mock layer for V.

Arm 1 (agent alone) gets nothing more: terminal, files, gateway, GPU.

Arm 2 (agent + verification toolkit) also gets MCP tools:
- `replay(config, set=V, k)`: multi-turn replay with mocked tools; returns per-scenario outcomes and cost.
- `vault_eval(config)`: sealed set S, aggregate Δ with CI, at most 3 calls.
- `stats_gate(results)`: returns SAFE / UNSAFE / INSUFFICIENT_EVIDENCE under δ, using a cluster bootstrap and an item-level regression check (FDR-controlled, after arXiv 2608.17719).
- `judge_calibrate(judge, labeled_sample)`: for tasks graded by a judge.
- `train(recipe)`: SFT/LoRA on any cloud, with an open-teacher data generator. Customer traces are used as test data, never as a training target from closed models.
- `endpoint_verify(base_url, model)`: tool-call schema compliance, determinism and multi-turn sanity on a fixed probe set, for when the same weights are served by different providers.

**Ablations, later:** arm 1 + `stats_gate` only; arm 1 + `replay` only. These attribute any gain to specific tools.

## 8. Compute estimate (v1)

| Item | Unit cost | Count | Total |
|---|---|---|---|
| Incumbent on H + H-tail, k=4 (~1,000 episodes at ~$0.10, GPT-5-class, measured on retail) | ~$100 / task | 12 | ~$1.2k |
| Reference candidates on H (6 per task: API ~$10, open models ~1 H100-h) | ~$70 / task | 12 | ~$0.8k |
| User simulator (Haiku 5.5, ~$0.002 / episode) | | ~100k episodes | ~$0.2k |
| Arm runs: coding agent $5-40 + inference ≤$25 + GPU ≤4 H100-h (~$16) + grading on H ~$15 | ~$60-100 / run | 12 tasks × 2 arms × 2 agents × 4 runs = 192 | ~$12-19k |
| **Total** | | | **~$15-21k** |

The GPU share, about $4-6k, is what a neocloud could sponsor. The API share is credits from labs.

A pilot with 3 tasks × 2 arms × 1 agent × 4 runs costs about $2k.

## 9. Build plan (4 weeks)

| Week | Work |
|---|---|
| 1 | Harness: trace converter, gateway, replay runner, grader, stats. Task 1 end to end. Riskiest-assumption experiment (`RISK_EXPERIMENT.md`). |
| 2 | Tasks 2-6, plus fresh-scenario generators for the tau2 domains. |
| 3 | Tasks 7-12, the arm 2 MCP server, reference sweeps. |
| 4 | Pilot runs, adversarial review (leak checks, judge audits), write-up. |
