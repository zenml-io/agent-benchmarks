# Is the score a time budget set by the server?

Task sets: full, full-k2.

## mini-swe-agent

Reference: defaults at c=16 on H100!. Uncapped run: 36 trials, 17 tasks solved.

| config | c | gpu | trials | speed factor (step time vs ref) | solved (observed) | predicted from speed | success vs ref, pts (95% CI) |
|---|---|---|---|---|---|---|---|
| defaults | 8 | H100! | 36 | 0.69 (31 tasks) | 18.0 of 36 tasks | 16 of 36 | +6 (-5 to +19), 36 tasks |
| defaults | 16 | H100! | 108 | 1.00 (32 tasks) | 15.7 of 36 tasks | 11 of 36 | - |
| defaults | 32 | H100! | 144 | 1.83 (32 tasks) | 10.8 of 36 tasks | 7 of 36 | -14 (-22 to -6), 36 tasks |
| defaults | 48 | H100! | 72 | 1.79 (31 tasks) | 12.5 of 36 tasks | 7 of 36 | -9 (-18 to +0), 36 tasks |
| defaults | 64 | H100! | 72 | 2.15 (32 tasks) | 9.5 of 36 tasks | 6 of 36 | -17 (-29 to -6), 36 tasks |
| defaults-4x-time | 16 | H100! | 36 | 0.93 (32 tasks) | 17.0 of 36 tasks | - | +4 (-10 to +19), 36 tasks |
| moe-a3b | 16 | H100! | 108 | 0.11 (32 tasks) | 17.7 of 36 tasks | 17 of 36 | +6 (-10 to +22), 36 tasks |
| spec-mtp | 16 | H100! | 36 | 0.99 (32 tasks) | 17.0 of 36 tasks | 11 of 36 | +4 (-9 to +16), 36 tasks |
| b200 | 32 | B200 | 108 | 0.61 (32 tasks) | 17.7 of 36 tasks | 16 of 36 | +6 (-4 to +16), 36 tasks |
| defaults-2x-time | 32 | H100! | 108 | 2.07 (31 tasks) | 14.0 of 36 tasks | 11 of 36 | -5 (-13 to +3), 36 tasks |
| defaults-4x-time | 32 | H100! | 36 | 2.17 (31 tasks) | 14.0 of 36 tasks | - | -5 (-17 to +8), 36 tasks |
| h200 | 32 | H200 | 108 | 0.80 (32 tasks) | 16.3 of 36 tasks | 15 of 36 | +2 (-7 to +11), 36 tasks |
| h200-spec-mtp | 32 | H200 | 36 | 0.54 (32 tasks) | 18.0 of 36 tasks | 16 of 36 | +6 (-8 to +21), 36 tasks |
| kv-fp8 | 32 | H100! | 72 | 1.04 (31 tasks) | 13.5 of 36 tasks | 11 of 36 | -6 (-13 to +1), 36 tasks |
| moe-a3b | 32 | H100! | 108 | 0.15 (32 tasks) | 17.7 of 36 tasks | 17 of 36 | +6 (-12 to +24), 36 tasks |
| no-prefix-cache | 32 | H100! | 72 | 1.48 (32 tasks) | 12.5 of 36 tasks | 11 of 36 | -9 (-16 to -1), 36 tasks |
| no-thinking | 32 | H100! | 108 | 0.61 (32 tasks) | 14.3 of 36 tasks | 16 of 36 | -4 (-17 to +8), 36 tasks |
| spec-mtp | 32 | H100! | 144 | 1.66 (32 tasks) | 13.0 of 36 tasks | 9 of 36 | -7 (-17 to +2), 36 tasks |
| weights-fp8 | 32 | H100! | 72 | 0.85 (31 tasks) | 14.5 of 36 tasks | 13 of 36 | -3 (-12 to +5), 36 tasks |

Speed-only prediction over 17 cells: mean error 2.7 tasks (predicting every cell's mean instead: 2.3); correlation r = 0.87.

Of 51 reference trials that ran out of time, 15 were solved in the uncapped run (defaults-4x-time).

## opencode

Reference: defaults at c=16 on H100!. Uncapped run: not yet.

| config | c | gpu | trials | speed factor (step time vs ref) | solved (observed) | predicted from speed | success vs ref, pts (95% CI) |
|---|---|---|---|---|---|---|---|
| defaults | 16 | H100! | 36 | 1.00 (34 tasks) | 18.0 of 36 tasks | - | - |
| defaults | 32 | H100! | 36 | 1.34 (34 tasks) | 16.0 of 36 tasks | - | -6 (-19 to +8), 36 tasks |

## pi

Reference: defaults at c=16 on H100!. Uncapped run: not yet.

| config | c | gpu | trials | speed factor (step time vs ref) | solved (observed) | predicted from speed | success vs ref, pts (95% CI) |
|---|---|---|---|---|---|---|---|
| defaults | 16 | H100! | 36 | 1.00 (32 tasks) | 15.0 of 36 tasks | - | - |
| defaults | 32 | H100! | 36 | 1.30 (32 tasks) | 14.0 of 36 tasks | - | -3 (-14 to +11), 36 tasks |

## terminus-2

Reference: defaults at c=16 on H100!. Uncapped run: 36 trials, 22 tasks solved.

| config | c | gpu | trials | speed factor (step time vs ref) | solved (observed) | predicted from speed | success vs ref, pts (95% CI) |
|---|---|---|---|---|---|---|---|
| defaults | 8 | H100! | 36 | 0.92 (34 tasks) | 19.0 of 36 tasks | 14 of 36 | +8 (-1 to +18), 36 tasks |
| defaults | 16 | H100! | 108 | 1.00 (34 tasks) | 16.0 of 36 tasks | 13 of 36 | - |
| defaults | 32 | H100! | 216 | 1.30 (34 tasks) | 14.8 of 36 tasks | 12 of 36 | -3 (-9 to +2), 36 tasks |
| defaults | 48 | H100! | 72 | 1.76 (32 tasks) | 12.0 of 36 tasks | 8 of 36 | -11 (-19 to -3), 36 tasks |
| defaults | 64 | H100! | 72 | 2.34 (34 tasks) | 8.0 of 36 tasks | 5 of 36 | -22 (-33 to -12), 36 tasks |
| defaults-4x-time | 16 | H100! | 36 | 1.05 (34 tasks) | 22.0 of 36 tasks | - | +17 (+4 to +31), 36 tasks |
| moe-a3b | 16 | H100! | 108 | 0.26 (34 tasks) | 17.0 of 36 tasks | 22 of 36 | +3 (-11 to +18), 36 tasks |
| spec-mtp | 16 | H100! | 36 | 0.64 (34 tasks) | 19.0 of 36 tasks | 19 of 36 | +8 (-5 to +24), 36 tasks |
| b200 | 32 | B200 | 108 | 0.71 (34 tasks) | 20.0 of 36 tasks | 17 of 36 | +11 (+3 to +21), 36 tasks |
| defaults-2x-time | 32 | H100! | 108 | 1.78 (34 tasks) | 16.7 of 36 tasks | 15 of 36 | +2 (-6 to +11), 36 tasks |
| defaults-4x-time | 32 | H100! | 36 | 1.72 (34 tasks) | 17.0 of 36 tasks | - | +3 (-12 to +18), 36 tasks |
| h200 | 32 | H200 | 108 | 0.88 (34 tasks) | 16.0 of 36 tasks | 15 of 36 | +0 (-10 to +11), 36 tasks |
| h200-spec-mtp | 32 | H200 | 36 | 0.60 (33 tasks) | 21.0 of 36 tasks | 19 of 36 | +14 (+5 to +24), 36 tasks |
| kv-fp8 | 32 | H100! | 72 | 1.06 (34 tasks) | 18.0 of 36 tasks | 13 of 36 | +6 (-2 to +13), 36 tasks |
| moe-a3b | 32 | H100! | 108 | 0.32 (34 tasks) | 15.3 of 36 tasks | 20 of 36 | -2 (-17 to +13), 36 tasks |
| no-prefix-cache | 32 | H100! | 72 | 1.33 (34 tasks) | 15.5 of 36 tasks | 12 of 36 | -1 (-11 to +7), 36 tasks |
| no-thinking | 32 | H100! | 108 | 0.64 (34 tasks) | 16.3 of 36 tasks | 19 of 36 | +1 (-10 to +13), 36 tasks |
| spec-mtp | 32 | H100! | 144 | 1.43 (33 tasks) | 15.8 of 36 tasks | 11 of 36 | -1 (-10 to +9), 36 tasks |
| weights-fp8 | 32 | H100! | 72 | 0.89 (33 tasks) | 15.0 of 36 tasks | 15 of 36 | -3 (-11 to +6), 36 tasks |

Speed-only prediction over 17 cells: mean error 3.0 tasks (predicting every cell's mean instead: 2.0); correlation r = 0.71.

Of 55 reference trials that ran out of time, 23 were solved in the uncapped run (defaults-4x-time).

## Harness x infra interaction

Change in success from the same infra change (vs the reference) for one harness minus the other, paired by task, bootstrap 95% CI. A CI excluding 0 means the infra change affects the harnesses differently.

| infra change | vs baseline | harnesses | difference of changes, pts (95% CI) |
|---|---|---|---|
| defaults c=32 H100! | defaults c=16 H100! | mini-swe-agent minus opencode | -8 (-22 to +5), 36 tasks |
| defaults c=32 H100! | defaults c=16 H100! | mini-swe-agent minus pi | -11 (-28 to +3), 36 tasks |
| b200 c=32 B200 | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +5 (-8 to +17), 36 tasks |
| b200 c=32 B200 | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -6 (-18 to +6), 36 tasks |
| defaults c=8 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -2 (-14 to +11), 36 tasks |
| defaults c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -10 (-19 to -2), 36 tasks |
| defaults c=48 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | +2 (-9 to +13), 36 tasks |
| defaults c=64 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | +5 (-6 to +16), 36 tasks |
| defaults-2x-time c=32 H100! | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +4 (-7 to +15), 36 tasks |
| defaults-2x-time c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -6 (-19 to +5), 36 tasks |
| h200 c=32 H200 | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +12 (+0 to +24), 36 tasks |
| h200 c=32 H200 | defaults c=16 H100! | mini-swe-agent minus terminus-2 | +2 (-9 to +12), 36 tasks |
| h200-spec-mtp c=32 H200 | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +3 (-13 to +20), 36 tasks |
| h200-spec-mtp c=32 H200 | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -7 (-23 to +9), 36 tasks |
| kv-fp8 c=32 H100! | defaults c=32 H100! | mini-swe-agent minus terminus-2 | -1 (-13 to +11), 36 tasks |
| kv-fp8 c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -12 (-23 to -1), 36 tasks |
| moe-a3b c=16 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | +3 (-11 to +17), 36 tasks |
| moe-a3b c=32 H100! | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +18 (+5 to +32), 36 tasks |
| moe-a3b c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | +7 (-6 to +23), 36 tasks |
| no-prefix-cache c=32 H100! | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +3 (-9 to +16), 36 tasks |
| no-prefix-cache c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -7 (-19 to +4), 36 tasks |
| no-thinking c=32 H100! | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +6 (-6 to +17), 36 tasks |
| no-thinking c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -5 (-20 to +9), 36 tasks |
| spec-mtp c=16 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -5 (-25 to +14), 36 tasks |
| spec-mtp c=32 H100! | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +4 (-6 to +13), 36 tasks |
| spec-mtp c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -7 (-19 to +5), 36 tasks |
| weights-fp8 c=32 H100! | defaults c=32 H100! | mini-swe-agent minus terminus-2 | +10 (-1 to +21), 36 tasks |
| weights-fp8 c=32 H100! | defaults c=16 H100! | mini-swe-agent minus terminus-2 | -0 (-12 to +10), 36 tasks |
| defaults c=32 H100! | defaults c=16 H100! | opencode minus pi | -3 (-19 to +14), 36 tasks |
| defaults c=32 H100! | defaults c=16 H100! | opencode minus terminus-2 | -2 (-17 to +12), 36 tasks |
| defaults c=32 H100! | defaults c=16 H100! | pi minus terminus-2 | +0 (-12 to +15), 36 tasks |

## Real cost per solved task by GPU

Ratio of real cost per solve (GPU + sandboxes) on the bigger GPU to the H100 at the same number of agents; cost per trial fixed, solves resampled by task (2000 resamples, 95% CI).

| harness | GPU | agents | ratio (95% CI) | verdict |
|---|---|---|---|---|
| mini-swe-agent | B200 vs H100 | 32 | 0.60 (0.42 to 0.79) | cheaper |
| mini-swe-agent | H200 vs H100 | 32 | 0.60 (0.43 to 0.77) | cheaper |
| terminus-2 | B200 vs H100 | 32 | 0.80 (0.64 to 0.92) | cheaper |
| terminus-2 | H200 vs H100 | 32 | 0.87 (0.73 to 1.04) | no clear difference |

Solved (observed) counts tasks fractionally when a cell has several trials per task (repeats or 2 attempts). Predicted from speed needs an uncapped run for the harness.

