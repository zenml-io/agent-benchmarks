# Adversarial checks

Ways our results could be wrong or biased, and what we checked. Updated as the study runs.

## Confounds in how runs were executed

- **Parallel streams interfering.** Up to 10 runs ran at once, each with its own GPU server, so
  they share no GPU. terminus-2 drives its agents from the session container; load average stayed
  under 1 on 4 cores and memory under 3 of 16 GB (Oct 9, 07:20, 9 streams). Not a bottleneck.
- **Sandbox speed drifting over time or with load.** Median per-run sandbox setup (1-2 s), harness
  install (12-48 s, by harness) and verifier time (9-15 s) were flat across 23 runs from 03:46 to
  06:57 UTC, including while 7-9 streams ran. No sign of Modal-side contention.
- **terminus-2's model calls go through the session's egress proxy** (the other harnesses call the
  server from Modal sandboxes). The added round trip is well under a second per call against 30-80 s
  agent steps (<1%). A few proxy connections dropped early on; no trial failed from it.
- **Stale or shared servers.** Each run's server must report zero tokens served before the run
  starts (`wait_ready`), and the previous run's URL must go quiet first. Introduced after one
  contaminated run, which was aborted and rerun; earlier runs were checked (all startups 150-234 s).
- **Orphaned agents from killed runs** kept calling a server once; sandboxes are now capped at 2 h
  and were terminated by hand that time. The affected run was aborted and is recorded as invalid.

## Measurement and statistics

- **Multiple comparisons.** `analysis.md` reports dozens of paired comparisons; some "significant"
  intervals are expected by chance. Only `PREREGISTRATION.md` claims are confirmatory (fixed
  analysis, Holm-corrected, new runs only).
- **Single runs.** Run-to-run time varies ~20% for identical configs (stragglers), so cost per
  solve from one run is noisy; server-side metrics (preemptions, inter-token latency, cache hit
  rate) repeat closely. Claims rest on paired task-level CIs, not on cost differences alone.
- **Benchmark lookups** (agents fetching answers) never count as solved; detection is a regex over
  tool calls and misses lookups that never name the benchmark.
- **Install failures** (one Terminal-Bench task's Debian mirror, for in-sandbox harnesses) count as
  unsolved for every config equally; they don't affect within-harness comparisons.

## Scope and selection

- **Task selection favours tight time limits.** Our 36 Terminal-Bench 2.0 tasks all have agent
  limits <= 20 min (63% of the benchmark does; median 15 min; 14 of 89 tasks allow >= 1 h). Effects
  that work through the time limit are larger here than on the full benchmark. The leaderboard does
  fix the limits (tbench.ai, Sep 2025), but step- or cost-limited benchmarks (SWE-bench setups,
  Terminal-Bench 4.0's 8 h) would show the effect as time and cost, not score.
- **One model** (Qwen3.8-27B, thinking on by default), one serving engine (vLLM 0.31), Modal GPUs
  and prices as of Oct 2026. Coding (Terminal-Bench) plus a GAIA generalization test.
- **Spec decoding is lossless by design**, so any change in solves from it must come through time
  (steps per time limit), memory pressure, or noise, not output quality.

## Claims we tested and had to narrow

- **"On a time-limited benchmark, the score is the server's speed."** A speed-only model (each
  task's uncapped solve time, rescaled by the setup's measured agent step time, against the task's
  limit) predicts GPU swaps well (H200, B200: within 0-2 tasks), but over all 11 terminus-2 setups it
  is worse than predicting the mean (mean error 2.4 vs 1.8 tasks, r = 0.44). It over-predicts
  no-thinking (faster steps, but the agent needs more of them) and under-predicts the overloaded
  H100 by 3-5 tasks (steps average 1.3-1.6x slower, but solves hold up better). Narrowed claim: GPU
  changes move the score roughly as their speed predicts; overload costs less than its average
  slowdown implies; settings that change agent behaviour don't follow speed.
- **"Agents that ran out of time were still working, so they'd have solved it."** 77-99% of
  timed-out trials were still issuing new actions, but with 4x the time only 6 of 16 timed-out
  terminus-2 tasks (c=16) were solved. "Still working" is not "nearly done"; about 4 in 10 are.
- **"Speculative decoding hurts on a full H100."** Two runs: server metrics much worse (5-8x
  preemptions, 30+ s to first token) but solves 17 and 18 vs ~15 for defaults. Corrected to: it
  hurts the server's metrics, not (measurably) the outcome.
- **"Cost per solved task" from GPU time alone.** The real Modal bill (through Oct 9, 07:00 UTC)
  was $70 GPU + $48 Harbor sandboxes, 1.7x the GPU cost. Sandboxes are 33-55% of the real cost per
  solve, more on an overloaded GPU (slow steps keep each sandbox alive longer) and less on fast
  GPUs. Counting them, going from 16 to 32 agents on an H100 saves terminus-2 almost nothing and
  makes mini-swe-agent ~47% more expensive per solve. Records now carry `sandbox_cost_est` and
  `total_cost_per_solved` (estimate: $38 vs $48 billed for the same window; the gap is in-flight,
  aborted and orphaned sandboxes, so it slightly understates).
- **"The payoff from an infra change depends on the harness" generalizes beyond coding.** On GAIA
  (60 tasks, 10-min limit), H200 vs H100 at 32 agents gives +13 pts for both terminus-2 (CI +3 to
  +25) and mini-swe-agent (CI 0 to +27): interaction 0 (CI -18 to +18). Load (32 vs 16 agents):
  -3 and -8, interaction -5 (CI -22 to +10). So infra moving outcomes generalizes (strongly);
  the harness-specific payoff is shown on Terminal-Bench, not on GAIA. It depends on the workload.
- **Repeated looks at the pre-registered tests.** `confirmatory.py` was re-run after every new
  run, and the pre-registration did not fix when to evaluate; repeated looks inflate false
  positives. C4's p-value moved 0.105 -> 0.103 -> 0.017 as cells were added. The verdicts we report
  are the values on all data at the end of the night, with this caveat stated.
- **"The pricier GPU is cheaper per solved task."** With a task bootstrap on real cost per solve
  (GPU + sandboxes) at 32 agents: mini-swe-agent H200/H100 0.60 (CI 0.44-0.76), B200/H100 0.53
  (0.35-0.72), both clearly cheaper; terminus-2 0.88 (0.73-1.09) and 0.96 (0.73-1.24), no clear
  difference. Robust for the memory-hungry harness only.
- **"More time rescues mini-swe-agent under overload."** One run with 2x the time at 32 agents
  solved 16 of 36 vs 8-10 for defaults. Repeated with 2 attempts per task on both sides: 26 of 72
  (2x time) vs 25 of 72 (defaults), at about 1.7x the real cost per solve. With 4x the time: 14 of
  36 at $0.65 per solve, about twice defaults. Extra time on an overloaded H100 brings both
  harnesses back to roughly what 16 agents with normal limits reach, and costs more per solve.
- **"A bigger GPU helps the large-prompt harness more" (C1).** Exploratory, on all data: +12 pts
  (CI 0 to +24). Pre-registered, on runs recorded after the pre-registration only: +9 (CI -7 to
  +24), Holm p = 0.25, not confirmed. The direction holds; the evidence for a harness-specific
  payoff from the GPU is not strong enough to claim.
