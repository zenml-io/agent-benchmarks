# Trace-only early warning on the hard ML-ops runs

536 trials with at least 3 agent steps, all hard-set runs (both harnesses, every setup).
Features use only the first 5 agent steps of a trial, i.e. the first few minutes.

## Does the early trace predict a timeout or a failure? (AUC; 0.5 = no signal)

| harness | trials | timeouts | AUC slow steps -> timeout | AUC low generation rate -> timeout | AUC low generation rate -> unsolved |
|---|---|---|---|---|---|
| terminus-2 | 275 | 39 | 0.52 | 0.62 | 0.59 |
| mini-swe-agent | 261 | 36 | 0.59 | 0.68 | 0.63 |

## Generation rate seen in the trace vs the server's real load

Median early generation rate (tokens/s per agent) by setup. Server KV-cache mean from vLLM metrics (not visible to a tracer).

| harness | setup | agents | median gen rate (tok/s) | server KV mean | timeouts / trials | solved / trials |
|---|---|---|---|---|---|---|
| mini-swe-agent | H100, vLLM defaults | 8 | 36 | 31% | 4/45 | 43/45 |
| mini-swe-agent | H200, vLLM defaults | 24 | 34 | 13% | 0/44 | 40/44 |
| mini-swe-agent | H100, vLLM defaults | 24 | 22 | 66% | 11/38 | 31/38 |
| mini-swe-agent | H100, defaults, 60 min per task instead of 30 | 24 | 20 | 39% | 6/40 | 34/40 |
| mini-swe-agent | H100, server caps output at 8k tokens/call | 24 | 19 | 73% | 10/46 | 38/46 |
| mini-swe-agent | H100, reasoning off | 24 | 18 | 49% | 5/48 | 23/48 |
| terminus-2 | H200, vLLM defaults | 24 | 34 | 12% | 3/47 | 44/47 |
| terminus-2 | H100, vLLM defaults | 8 | 33 | 28% | 5/44 | 40/44 |
| terminus-2 | H100, vLLM defaults | 24 | 24 | 73% | 11/41 | 34/41 |
| terminus-2 | H100, defaults, 60 min per task instead of 30 | 24 | 23 | 52% | 3/47 | 46/47 |
| terminus-2 | H100, server caps output at 8k tokens/call | 24 | 22 | 72% | 11/48 | 43/48 |
| terminus-2 | H100, reasoning off | 24 | 21 | 46% | 6/48 | 30/48 |

## An alarm rule an eval tool could ship

Flag a trial when its early generation rate falls below a threshold. Counts over all trials.

| threshold (tok/s) | trials flagged | of which timed out | of all timeouts caught | flagged trials that were solved anyway |
|---|---|---|---|---|
| 10 | 24 | 6 (25%) | 8% | 21 |
| 15 | 70 | 19 (27%) | 25% | 54 |
| 20 | 169 | 37 (22%) | 49% | 131 |
| 25 | 286 | 54 (19%) | 72% | 223 |
| 30 | 382 | 66 (17%) | 88% | 303 |
| 40 | 522 | 75 (14%) | 100% | 436 |
