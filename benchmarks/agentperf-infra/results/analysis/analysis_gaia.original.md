# Is the score a time budget set by the server?

Task sets: gaia, gaia-k2.

## mini-swe-agent

Reference: defaults at c=16 on H100!. Uncapped run: not yet.

| config | c | gpu | trials | speed factor (step time vs ref) | solved (observed) | predicted from speed | success vs ref, pts (95% CI) |
|---|---|---|---|---|---|---|---|
| defaults | 16 | H100! | 60 | 1.00 (56 tasks) | 18.0 of 60 tasks | - | - |
| defaults | 32 | H100! | 60 | 1.29 (53 tasks) | 13.0 of 60 tasks | - | -8 (-20 to +3), 60 tasks |
| h200 | 32 | H200 | 60 | 0.83 (55 tasks) | 21.0 of 60 tasks | - | +5 (-8 to +18), 60 tasks |

## terminus-2

Reference: defaults at c=16 on H100!. Uncapped run: not yet.

| config | c | gpu | trials | speed factor (step time vs ref) | solved (observed) | predicted from speed | success vs ref, pts (95% CI) |
|---|---|---|---|---|---|---|---|
| defaults | 16 | H100! | 60 | 1.00 (60 tasks) | 14.0 of 60 tasks | - | - |
| defaults | 32 | H100! | 60 | 1.13 (60 tasks) | 12.0 of 60 tasks | - | -3 (-13 to +5), 60 tasks |
| h200 | 32 | H200 | 60 | 0.88 (60 tasks) | 20.0 of 60 tasks | - | +10 (+2 to +20), 60 tasks |

## Harness x infra interaction

Change in success from the same infra change (vs the reference) for one harness minus the other, paired by task, bootstrap 95% CI. A CI excluding 0 means the infra change affects the harnesses differently.

| infra change | vs baseline | harnesses | difference of changes, pts (95% CI) |
|---|---|---|---|
| defaults c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -5 (-22 to +10), 60 tasks |
| h200 c=32 H200 | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +0 (-18 to +18), 60 tasks |
| h200 c=32 H200 | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -5 (-22 to +10), 60 tasks |

## Real cost per solved task by GPU

Ratio of real cost per solve (GPU + sandboxes) on the bigger GPU to the H100 at the same number of agents; cost per trial fixed, solves resampled by task (2000 resamples, 95% CI).

| harness | GPU | agents | ratio (95% CI) | verdict |
|---|---|---|---|---|
| mini-swe-agent | H200 vs H100 | 32 | 0.64 (0.36 to 1.03) | no clear difference |
| terminus-2 | H200 vs H100 | 32 | 0.62 (0.34 to 0.92) | cheaper |

Solved (observed) counts tasks fractionally when a cell has several trials per task (repeats or 2 attempts). Predicted from speed needs an uncapped run for the harness.

