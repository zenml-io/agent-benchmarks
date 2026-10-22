
## task set `mlops-k5` (4 runs)

| command | trials | GPU $ | sandbox est. $ | wall min |
|---|---|---|---|---|
| `experiment.py --tasks-file tasks_mlops.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 30 --rep-from 0 --reps 1 --attempts 5` | 30 | 0.95 | 0.45 | 18 |
| `experiment.py --tasks-file tasks_mlops.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 30 --rep-from 0 --reps 1 --attempts 5` | 30 | 1.32 | 0.72 | 23 |
| `experiment.py --tasks-file tasks_mlops.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 6 --rep-from 0 --reps 1 --attempts 5` | 30 | 1.88 | 0.45 | 42 |
| `experiment.py --tasks-file tasks_mlops.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 6 --rep-from 0 --reps 1 --attempts 5` | 30 | 2.01 | 0.51 | 33 |

## task set `mlops_hard-k3` (30 runs)

| command | trials | GPU $ | sandbox est. $ | wall min |
|---|---|---|---|---|
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.08 | 1.92 | 35 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.17 | 1.83 | 36 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 8 --rep-from 0 --reps 1 --attempts 3` | 24 | 4.22 | 1.40 | 66 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 8 --rep-from 0 --reps 1 --attempts 3` | 24 | 4.29 | 1.13 | 68 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs h200 --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.36 | 1.23 | 35 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs max-out-8k --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.05 | 1.61 | 36 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 2.09 | 1.73 | 35 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs no-thinking --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.06 | 1.21 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 2.12 | 2.02 | 35 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs defaults-2x-time --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 4.03 | 2.23 | 64 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs max-out-8k --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.49 | 1.91 | 41 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs h200 --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.33 | 1.00 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs no-thinking --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.08 | 0.90 | 35 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs defaults-2x-time --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 4.11 | 2.66 | 65 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs max-out-8k --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 2.08 | 1.68 | 35 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs h200 --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 2.38 | 1.28 | 36 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 8 --rep-from 1 --reps 2 --attempts 3` | 24 | 4.09 | 1.40 | 65 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs no-thinking --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 2.03 | 0.94 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs defaults-2x-time --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 4.03 | 2.44 | 65 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs max-out-8k --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 2.08 | 1.96 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 8 --rep-from 1 --reps 2 --attempts 3` | 24 | 3.45 | 1.08 | 55 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs h200 --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 2.32 | 1.08 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs no-thinking --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 2.20 | 1.43 | 37 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs defaults-2x-time --concurrency 24 --rep-from 1 --reps 2 --attempts 3` | 24 | 4.05 | 2.69 | 64 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs max-out-4k --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.05 | 1.53 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs max-out-16k --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.08 | 1.84 | 35 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses terminus-2 -- matrix --configs moe-a3b --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.02 | 0.58 | 36 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs max-out-4k --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 1.57 | 1.29 | 27 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs moe-a3b --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.03 | 0.65 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard.json --harnesses mini-swe-agent -- matrix --configs max-out-16k --concurrency 24 --rep-from 0 --reps 1 --attempts 3` | 24 | 2.05 | 1.87 | 34 |

## task set `mlops_hard2-k6` (4 runs)

| command | trials | GPU $ | sandbox est. $ | wall min |
|---|---|---|---|---|
| `experiment.py --tasks-file tasks_mlops_hard2.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 24 --rep-from 0 --reps 1 --attempts 6` | 24 | 2.05 | 2.25 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard2.json --harnesses terminus-2 -- matrix --configs h200 --concurrency 24 --rep-from 0 --reps 1 --attempts 6` | 24 | 2.36 | 2.09 | 35 |
| `experiment.py --tasks-file tasks_mlops_hard2.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 24 --rep-from 0 --reps 1 --attempts 6` | 24 | 2.08 | 2.29 | 34 |
| `experiment.py --tasks-file tasks_mlops_hard2.json --harnesses mini-swe-agent -- matrix --configs h200 --concurrency 24 --rep-from 0 --reps 1 --attempts 6` | 24 | 2.38 | 1.57 | 34 |

Total over 38 runs: GPU $94.01 + startup $8.14 + sandbox estimate $56.83; 25.5 server-hours if run one after another.
