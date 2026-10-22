# Agents are systems: findings (sections 1-9, 11)

*Copied from FINDINGS.md in the original private repository (commit 0d1500e2), with the decision-agent sections (12-14) and the SGLang section (10, now in ../../sglang-vs-vllm/docs/FINDINGS-section10.md) removed. Text is unchanged otherwise; file references point to the original repo (`analysis.md` etc. are in ../results/analysis/*.original.md; `site/index.html` is not ported). Where this text and results/agentperf-infra.json disagree, the JSON is computed from the rows and wins; see README.md, Trust status.*

## The question

When a team runs a coding agent on an open model on its own GPUs, the agent team picks the
model, harness, prompts and reasoning settings and judges success by tasks solved. The platform
team picks the GPU, how many agents share it and the serving settings, and judges success by
throughput, latency and utilization. The two meet at an OpenAI-compatible endpoint. We measured
what happens across that line.

## Setup

- **Model:** Qwen3.8-27B (dense, hybrid attention, thinking on by default) on vLLM 0.31.0. A second
  model for contrast: Qwen3.6-35B-A3B (mixture of experts, 3B active, FP8).
- **GPUs (Modal):** H100 ($3.95/h), H200 ($4.54/h), B200 ($6.25/h). Agents run in Modal sandboxes
  through Harbor 0.24.
- **Harnesses:** terminus-2 (lean prompts), mini-swe-agent (large prompts), pi, opencode.
- **Tasks:** 36 Terminal-Bench 2.0 tasks (agent limits of 15-20 minutes, as on the official
  leaderboard), and 60 GAIA research tasks (10-minute limit) as a non-coding check.
- **Per run:** every trial's outcome and trajectory, vLLM server metrics every 10 seconds, GPU
  cost, and the sandbox cost (estimated per trial, checked against the Modal bill).
- **Scale:** 77 runs and 3,744 agent trials; the main comparisons have 108-216 trials per cell.
  Comparisons are paired by task with bootstrap confidence intervals.
- **Spend:** about $390 on the real Modal bill (GPUs and sandboxes), $218 of it GPU time.

## Findings

### 1. Infrastructure choices move outcomes a lot

On one H100 at 32 agents, changing the GPU, the load or the model's serving footprint changes the
share of tasks solved by up to 19 points (paired over 36 tasks, 95% CI):

| change, vs H100 defaults at 32 agents | mini-swe-agent | terminus-2 | difference |
|---|---|---|---|
| B200 instead of H100 | **+19** (+9 to +31) | **+14** (+7 to +23) | +5 (-8 to +17) |
| H200 instead of H100 | **+16** (+6 to +26) | +3 (-5 to +11) | +12 (0 to +24) |
| 16 instead of 32 agents | **+14** (+6 to +22) | +3 (-2 to +9) | **+10** (+2 to +19) |
| FP8 KV cache | **+8** (+1 to +15) | **+9** (+1 to +17) | -1 (-13 to +11) |
| MoE model instead of the dense 27B | **+19** (+4 to +35) | +1 (-11 to +15) | **+18** (+5 to +32) |

Some changes help both harnesses alike (B200, FP8 KV cache). Others matter mainly to the
large-prompt harness (less load, a model with a smaller KV cache). These harness differences are
exploratory: the three pre-registered versions, tested only on runs collected after they were
written down, pointed the same way but did not clear the bar (below). On GAIA the GPU effect holds
just as strongly (H200: +13 pts for both harnesses) and the harness difference does not.

### 2. Ranked by cost per solved task, the GPUs come out in reverse price order

Counting the GPU and the agents' sandboxes, at 32 agents the cheapest GPU per hour is the most
expensive per solved task for both harnesses. Real cost per solve relative to the H100:

| | H200 | B200 |
|---|---|---|
| mini-swe-agent | **0.60x** (CI 0.43-0.77) | **0.60x** (0.42-0.79) |
| terminus-2 | 0.87x (0.73-1.04) | **0.80x** (0.64-0.92) |

The saving is large for the large-prompt harness and modest for the lean one.

### 3. The server's dashboard and the agents disagree

- Speculative decoding on a full H100 produced the worst server metrics we saw (5-8x the
  preempted requests, 30+ seconds to first token) and no loss of solved tasks (terminus-2: 44% vs
  41% over 144 and 216 trials; mini-swe-agent +6 pts, CI 0 to +13).
- Packing more agents on a GPU raises throughput and utilization while lowering solved tasks.
  On one H100, terminus-2 solves 53% at 8 agents, 44% at 16, 41% at 32, 33% at 48 and 22% at 64;
  mini-swe-agent 50%, 44%, 30%, 35% and 26%. The large-prompt harness hits its cliff at 32 agents,
  the lean one at 48.
- Real cost per solve is U-shaped in load (terminus-2: $0.29, $0.24, $0.20, $0.23, $0.36 from 8 to
  64 agents): too few agents pay for an idle GPU, too many for congestion. The cheapest load is
  not the best-scoring one.
- The same knob can flip sign with context. Speculative decoding made agent steps about 10%
  slower on a full H100 and 29% faster on an H200 with memory to spare.

### 4. The real cost is about 1.7x the GPU bill, and a slow server inflates the rest

Harbor's per-agent sandboxes were 25% of the real cost at 8 agents and 63% at 64 agents. They
grow on a loaded GPU because slow steps keep every sandbox alive longer. Any cost-per-solve
figure that only counts the GPU understates the cost of overload.

### 5. Most failures are the clock, and more time doesn't buy them back cheaply

On time-limited tasks, most failed trials hit the limit while still issuing new commands (77-99%
of time-outs); wrong final answers stay at 3-8% on every GPU and load. Server speed moves trials
between "solved" and "timed out": across 37 configurations, the slower the median agent step, the
larger the share of time-outs (pre-registered C4, Spearman rho +0.65, p < 0.001), while the
share of wrong answers does not follow.

But "still working" is not "nearly done". With four times the limit, only about 4 in 10
time-outs were solved. On an overloaded H100 (32 agents), extra time brought solves back to about
the level of 16 agents with normal limits, at roughly twice the real cost per solve
(mini-swe-agent with 4x the time: 39% at $0.65 per solve, vs 30% at $0.30 with defaults; with 2x,
on two identical attempts per task: 26 vs 25 of 72).

### 6. Which model is "better" depends on the harness and the load

The mixture-of-experts model writes about three times faster and uses a fraction of the KV memory.
On one H100 (108-216 trials per cell):

| | dense 27B, 16 agents | dense, 32 | MoE, 16 | MoE, 32 |
|---|---|---|---|---|
| mini-swe-agent: solved | 44% | 30% | 49% | 49% |
| real cost per solve | $0.25 | $0.30 | $0.13 | $0.13 |
| terminus-2: solved | 44% | 41% | 47% | 43% |
| real cost per solve | $0.24 | $0.20 | $0.18 | $0.15 |

The MoE model removes the large-prompt harness's load penalty and halves its cost per solve. For
the lean harness the two models solve about the same, and the MoE is moderately cheaper. Published
results with 3-hour limits rank comparable dense models higher; under Terminal-Bench's own limits
and real serving load, the ranking depends on the harness.

### 7. One mechanism behind most of it: whether the KV cache fills

Every change that raised solves on a loaded H100 (fewer agents, FP8 weights, FP8 KV cache, H200,
B200, the MoE model) kept the KV cache from saturating (`mechanisms.md`):

| mini-swe-agent, 32 agents | KV peak | prefix-cache hits | preemptions | solved |
|---|---|---|---|---|
| H100 defaults | 100% | 31% | 258 | 30% |
| FP8 weights | 87% | 69% | 0 | 40% |
| FP8 KV cache | 91% | 55% | 0 | 38% |
| H200 / B200 | 56% / 43% | 90% / 92% | 0 | 45% / 49% |
| MoE model | 32% | 94% | 0 | 49% |

When the cache is full, agents' earlier turns are evicted between steps and recomputed, and steps
slow down. The large-prompt harness filled it already at 16 agents (terminus-2 peaked at 75%),
which is where its cliff starts. Prefix-cache thrashing under concurrency is known (Yuan et al.);
what this adds is that platform-only changes that free memory restore both the cache and the
solved tasks. It is not a universal rule: speculative decoding also caused heavy preemptions and
lost no solves.

Request time is not where the tokens are. Agents send 4-58 times more prompt tokens than they
generate, but 93-98% of each request's server time is generation (mostly thinking), not prefill.
Settings aimed at prefill (prefix caching, FP8) matter through the memory they free, not by making
prefill faster.

### 8. An overloaded setup's score is fragile

On the loaded H100, solves crowd against the deadline: 70% of mini-swe-agent's solves at 32 agents
finished in the last quarter of the time limit (median: 92% of the limit), against 17% on a B200
and 8% with the MoE model (terminus-2: 34% vs 10%). A slightly busier minute turns these into
time-outs, which fits how much our single runs varied. The two attempts per task disagreed on 25%
of tasks for mini-swe-agent at 32 agents vs 8-11% on B200 or at 16 agents (small samples; not
seen for terminus-2).

Two consequences for anyone reading or acting on these runs:

- **Killing long trials to save money backfires.** Failed trials take 62-81% of sandbox time,
  but solves come late: capping every trial at 75% of its limit raises cost per solve 1.3x for
  terminus-2 and 2.7x for mini-swe-agent (at 50%: 1.5x and 4.8x).
- **"Timed out" is not "failed".** 12% of terminus-2's solves and 20% of mini-swe-agent's came
  from trials that hit the limit after the tests already passed: the agent had done the work and
  did not stop.

### 9. The agent's own traces are enough to see it

An eval tool usually sees only what agent tracing records: when each model call happened and its
token usage, not the server's metrics. Over the 47 Terminal-Bench runs that change only the
infrastructure (`trace_signals.md`):

- **Flagging a saturated KV cache from traces alone** works almost perfectly within a harness:
  slower steps separate saturated from unsaturated runs with AUC 0.92 (terminus-2) and 0.98
  (mini-swe-agent); a lower generation rate (completion tokens per second) with 0.94 and 0.95;
  lower cache reuse (cached / prompt tokens, which the API reports per call) with 1.00.
- **Explaining score changes between two runs of the same agent:** when steps got at least 1.3x
  slower, the score fell by 10 points on average; when step times stayed within 1.3x, by 2
  (both harnesses; 529 run pairs; pairs share runs, so no significance claimed).
- **Predicting a run's score from its step time** (leave-one-run-out) halves the error of
  predicting the average: 3.7 vs 7.4 points (mini-swe-agent), 4.4 vs 6.5 (terminus-2).

So a regression that is really the serving infrastructure is visible in ordinary traces, with no
GPU telemetry. Limits: one model, time-limited tasks (where slower steps cost solves directly;
without a limit the same signal shows up as cost and latency); step time also changes when the
agent or model changes, so generation rate and cache reuse are the cleaner infrastructure
signals; and not every alarm is real (speculative decoding saturated the cache at 16 agents
and still solved 47%).


### 11. Coding-agent runs are not replayable, and one run in five flips on its own

Replay-based evaluation (re-run the agent, answer its tool calls from an earlier run's
recordings) only works while the new run asks for what the recorded run did. Over 3,082
trajectories (`divergence.md`), comparing two runs of the same task:

- **Paths split immediately.** Even a plain rerun with nothing changed takes a different first
  action in 80-92% of pairs (61-77% allowing near-identical commands), and in 96-100% by step 3.
- **Order-free lookup barely helps.** Only 12-16% of a rerun's shell commands appear anywhere in
  the recorded run (10-14% after an infrastructure change, 3-10% after a model or thinking
  change); 99% of runs need at least one answer that was never recorded.
- **Outcomes flip by chance.** Two runs of the same task with nothing changed disagree on
  pass/fail 17-20% of the time; across a model change, 31-41%.

For free-form tool use (shell commands, sampled at the harness's default temperature), replay
from recorded tool answers cannot evaluate a changed agent; it needs live or simulated tools,
and a per-session regression signal has a noise floor of about one flip in five. Agents with
structured tools (fixed lookups by ID) should replay far better; that is the thing to measure
on such an agent's own traces.

### Things that did not hold up

Effects measured on a single run of 36 tasks shrank repeatedly when repeated:

- "The GPU payoff depends on the harness" (C1): +13 pts on early runs, +9 (CI -7 to +24) on fresh
  runs, not confirmed. B200, first run +26 vs +13, now +19 vs +14.
- "16 agents instead of 32 matters for both harnesses": the first 16-agent reference run of
  terminus-2 solved 50%; three of them average 44%, and terminus-2 barely notices 32 agents.
- "Twice the time rescues mini-swe-agent under overload": 16 vs ~10 of 36 on one run, 26 vs 25 of
  72 on two identical attempts per task.
- "The MoE model solves more for terminus-2": 58% on the first run, 47% over three.
- "Turning reasoning off doesn't save money": with more trials it is neutral to slightly positive
  for solves and cheaper per solve for both harnesses.
- "Prefix caching off helps under overload": small and non-significant on more data.
- "The score is just the server's speed": a speed-only model predicts GPU swaps well but not
  settings that change agent behaviour (`ADVERSARIAL_CHECKS.md`).

## Pre-registered tests

Four claims were written down before the final runs (`PREREGISTRATION.md`) and tested only on
data collected afterwards (`confirmatory.md`):

| claim | effect on new runs | Holm-adjusted p | verdict |
|---|---|---|---|
| C1 a bigger GPU (H200) helps mini-swe-agent more than terminus-2 | +9 pts (-7 to +24) | 0.29 | not confirmed |
| C2 more load (32 vs 16 agents) hurts mini-swe-agent more | -9 pts (-24 to +5) | 0.29 | not confirmed |
| C3 thinking off interacts with the harness | -3 pts (-17 to +10) | 0.69 | not confirmed |
| C4 the time-out share follows server speed | rho +0.65, 37 cells | p < 0.001 | confirmed |

C1 and C2 point the predicted way but the fresh data alone is too small to confirm them. The
tests were re-run as data arrived (repeated looks inflate false positives); these are the final
values on all post-registration runs.

## Prior work

AgBench (arXiv 2609.38652) showed concurrency collapsing solves on the same model; Aries
(2607.29069) that harness context sets KV capacity; Yuan et al. (2605.26297) prefix-cache
thrashing with concurrency on Harbor + vLLM + Terminal-Bench; Anthropic (Feb 2026) that sandbox
resources move Terminal-Bench scores; Scaffold Effect (2607.22585) and HarnessTax that harnesses
change cost per solve. What this study adds: paired, outcome-level comparisons of serving settings,
GPUs and models across harnesses, cost per solve from the real bill including sandboxes, and
failure analysis from trajectories.

## Limitations

- Two models and one serving engine; Modal GPUs and prices as of October 2026.
- Our Terminal-Bench tasks all have limits of 20 minutes or less (63% of the benchmark does), so
  effects through the time limit are larger than on the full benchmark.
- Some cells are still one run of 36 tasks; identical runs differed by up to 17 points. Claims
  rest on paired intervals and on the cells with 108+ trials.
- Benchmark-lookup detection only catches lookups that name the benchmark.
- Sandbox cost is an estimate that slightly under-counts the bill.
