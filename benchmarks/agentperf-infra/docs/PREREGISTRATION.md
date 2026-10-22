# Confirmatory claims (written Oct 9 2026, ~07:15 UTC, before the data that tests them)

Everything in `analysis.md` / `trajectories.md` is exploratory: dozens of comparisons on mostly
single runs, so some "significant" intervals are expected by chance. Only the claims below are
confirmatory. They were suggested by the first runs (listed per claim) and are re-tested on
**new runs only** (runs recorded after this file was committed), with the analysis fixed here.

## Claims

All on Terminal-Bench 2.0 (the 36 tasks in `tasks.json`), Qwen3.8-27B, vLLM 0.31, H100 unless
stated, paired by task. "Interaction" = (change in success for mini-swe-agent) minus (change for
terminus-2) from the same infra change, with the other settings fixed.

- **C1 (GPU x harness).** Replacing the H100 with an H200 at 32 agents raises mini-swe-agent's
  success more than terminus-2's (interaction > 0). Suggested by: +18 pts (CI +1 to +38).
- **C2 (load x harness).** Going from 16 to 32 agents on an H100 lowers mini-swe-agent's success
  more than terminus-2's (interaction < 0). Suggested by: -12 pts (CI -31 to +3).
- **C3 (reasoning x harness).** Turning thinking off at 32 agents on an H100 raises
  mini-swe-agent's success more than terminus-2's (interaction > 0). Suggested by: +23 pts
  (CI +7 to +40).
- **C4 (failure mix follows server speed).** Across harness x config cells, the share of trials
  that run out of time while still issuing new actions rises with the cell's median seconds per
  agent step (Spearman rho > 0), while the "finished wrong" share does not.

## Analysis (fixed)

- Success per task = share of that task's trials solved (pooled over repeats/attempts).
- C1-C3: paired bootstrap over tasks (2000 resamples, seed 0) of the difference-in-differences;
  one-sided test in the stated direction; Holm correction across C1-C3 at alpha = 0.05.
- C4: Spearman correlation over cells with >= 36 trials; permutation p-value (one-sided).
- New data only: runs whose `ts` is after this file's commit time. If a cell has no new runs,
  the claim is "not yet tested", not confirmed.
- Solves where the agent looked up the benchmark never count (as everywhere in this repo).

## Runs planned to test them

`full-k2` (72 trials) runs of: defaults c=16 and c=32, h200 c=32, no-thinking c=32 for both
terminus-2 and mini-swe-agent (some already queued in stream D1).
