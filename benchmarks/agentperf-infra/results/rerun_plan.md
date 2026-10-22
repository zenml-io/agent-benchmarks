
## task set `quick` (8 runs)

| command | trials | GPU $ | sandbox est. $ | wall min |
|---|---|---|---|---|
| `experiment.py --harnesses terminus-2 -- quickcheck` (its defaults run) | 8 | 1.06 | 0.30 | 19 |
| `experiment.py --harnesses terminus-2 -- quickcheck` (its no-prefix-cache run) | 8 | 1.47 | 0.35 | 26 |
| `experiment.py --harnesses mini-swe-agent -- quickcheck` (its defaults run) | 8 | 1.08 | 0.25 | 19 |
| `experiment.py --harnesses mini-swe-agent -- quickcheck` (its no-prefix-cache run) | 8 | 1.41 | 0.27 | 24 |
| `experiment.py --harnesses opencode -- quickcheck` (its defaults run) | 8 | 1.57 | 0.27 | 28 |
| `experiment.py --harnesses opencode -- quickcheck` (its no-prefix-cache run) | 8 | 1.60 | 0.30 | 28 |
| `experiment.py --harnesses pi -- quickcheck` (its defaults run) | 8 | 1.39 | 0.24 | 24 |
| `experiment.py --harnesses pi -- quickcheck` (its no-prefix-cache run) | 8 | 1.40 | 0.23 | 24 |

## task set `full` (48 runs)

| command | trials | GPU $ | sandbox est. $ | wall min |
|---|---|---|---|---|
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 16 --rep-from 0 --reps 1` | 36 | 2.44 | 1.39 | 40 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 16 --rep-from 0 --reps 1` | 36 | 2.48 | 1.56 | 40 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.74 | 1.57 | 29 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.35 | 1.54 | 23 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs no-thinking --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.51 | 1.48 | 26 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.42 | 1.74 | 24 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs b200 --concurrency 32 --rep-from 0 --reps 1` | 36 | 2.52 | 1.24 | 30 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs spec-mtp --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.60 | 1.66 | 29 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs h200 --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.45 | 1.35 | 23 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs no-prefix-cache --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.43 | 1.57 | 24 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs b200 --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.96 | 1.23 | 21 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults-2x-time --concurrency 32 --rep-from 0 --reps 1` | 36 | 2.37 | 2.78 | 38 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs kv-fp8 --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.39 | 1.52 | 24 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs h200-spec-mtp --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.31 | 1.25 | 22 |
| `experiment.py --tasks-file tasks.json --harnesses pi -- matrix --configs defaults --concurrency 16 --rep-from 0 --reps 1` | 36 | 2.40 | 1.23 | 39 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs h200 --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.55 | 1.39 | 24 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs no-prefix-cache --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.43 | 1.51 | 24 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs no-thinking --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.43 | 1.39 | 24 |
| `experiment.py --tasks-file tasks.json --harnesses pi -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.40 | 1.32 | 25 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs h200-spec-mtp --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.63 | 1.27 | 28 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs weights-fp8 --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.69 | 1.47 | 36 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs spec-mtp --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.34 | 1.58 | 25 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults-4x-time --concurrency 16 --rep-from 0 --reps 1` | 36 | 5.26 | 3.43 | 82 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs no-prefix-cache --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.52 | 1.55 | 26 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults-2x-time --concurrency 32 --rep-from 0 --reps 1` | 36 | 2.74 | 2.69 | 44 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs spec-mtp --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.63 | 1.72 | 28 |
| `experiment.py --tasks-file tasks.json --harnesses opencode -- matrix --configs defaults --concurrency 16 --rep-from 0 --reps 1` | 36 | 2.44 | 1.37 | 40 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs spec-mtp --concurrency 16 --rep-from 0 --reps 1` | 36 | 2.17 | 1.28 | 37 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.73 | 1.72 | 28 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs kv-fp8 --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.65 | 1.45 | 28 |
| `experiment.py --tasks-file tasks.json --harnesses opencode -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.43 | 1.49 | 25 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs spec-mtp --concurrency 16 --rep-from 0 --reps 1` | 36 | 2.54 | 1.54 | 42 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs kv-fp8 --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.55 | 1.60 | 26 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs spec-mtp --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.69 | 1.69 | 31 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults-4x-time --concurrency 32 --rep-from 0 --reps 1` | 36 | 4.33 | 4.41 | 68 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs weights-fp8 --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.29 | 1.48 | 22 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs kv-fp8 --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.44 | 1.53 | 25 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs moe-a3b --concurrency 16 --rep-from 0 --reps 1` | 36 | 2.05 | 0.92 | 40 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs weights-fp8 --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.40 | 1.42 | 26 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs weights-fp8 --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.46 | 1.43 | 25 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs moe-a3b --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.47 | 1.03 | 25 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs no-prefix-cache --concurrency 32 --rep-from 1 --reps 2` | 36 | 1.74 | 1.75 | 29 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs moe-a3b --concurrency 16 --rep-from 0 --reps 1` | 36 | 1.84 | 0.68 | 31 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults-4x-time --concurrency 16 --rep-from 0 --reps 1` | 36 | 6.43 | 3.29 | 100 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 8 --rep-from 0 --reps 1` | 36 | 3.96 | 1.44 | 63 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs moe-a3b --concurrency 32 --rep-from 0 --reps 1` | 36 | 1.43 | 0.81 | 25 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 8 --rep-from 0 --reps 1` | 36 | 4.10 | 1.40 | 64 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults-4x-time --concurrency 32 --rep-from 0 --reps 1` | 36 | 4.59 | 4.56 | 72 |

## task set `full-k2` (23 runs)

| command | trials | GPU $ | sandbox est. $ | wall min |
|---|---|---|---|---|
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.69 | 3.07 | 44 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults-2x-time --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 4.77 | 5.40 | 75 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs h200 --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.56 | 2.95 | 37 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs spec-mtp --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.47 | 3.35 | 40 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 48 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.16 | 3.43 | 37 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs no-thinking --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.51 | 2.92 | 41 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 64 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.17 | 3.62 | 37 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs h200 --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.92 | 2.97 | 42 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.98 | 3.42 | 48 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 48 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.52 | 3.54 | 41 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs no-thinking --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.46 | 2.68 | 40 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 64 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.08 | 3.60 | 34 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults-2x-time --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 5.29 | 6.02 | 83 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 32 --rep-from 1 --reps 2 --attempts 2` | 72 | 2.70 | 3.16 | 45 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs spec-mtp --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.93 | 3.47 | 48 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs moe-a3b --concurrency 16 --rep-from 0 --reps 1 --attempts 2` | 72 | 3.97 | 2.02 | 64 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs moe-a3b --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.40 | 2.17 | 40 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 16 --rep-from 0 --reps 1 --attempts 2` | 72 | 4.47 | 3.12 | 71 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs moe-a3b --concurrency 16 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.71 | 1.52 | 45 |
| `experiment.py --tasks-file tasks.json --harnesses terminus-2 -- matrix --configs b200 --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 3.31 | 2.49 | 35 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs moe-a3b --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 2.40 | 2.14 | 40 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 16 --rep-from 0 --reps 1 --attempts 2` | 72 | 4.54 | 2.98 | 72 |
| `experiment.py --tasks-file tasks.json --harnesses mini-swe-agent -- matrix --configs b200 --concurrency 32 --rep-from 0 --reps 1 --attempts 2` | 72 | 3.81 | 2.60 | 39 |

## task set `gaia` (6 runs)

| command | trials | GPU $ | sandbox est. $ | wall min |
|---|---|---|---|---|
| `experiment.py --tasks-file tasks_gaia.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 16 --rep-from 0 --reps 1` | 60 | 2.38 | 1.54 | 39 |
| `experiment.py --tasks-file tasks_gaia.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 16 --rep-from 0 --reps 1` | 60 | 2.57 | 1.68 | 43 |
| `experiment.py --tasks-file tasks_gaia.json --harnesses terminus-2 -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1` | 60 | 1.37 | 1.56 | 23 |
| `experiment.py --tasks-file tasks_gaia.json --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1` | 60 | 1.46 | 1.80 | 25 |
| `experiment.py --tasks-file tasks_gaia.json --harnesses terminus-2 -- matrix --configs h200 --concurrency 32 --rep-from 0 --reps 1` | 60 | 1.58 | 1.45 | 25 |
| `experiment.py --tasks-file tasks_gaia.json --harnesses mini-swe-agent -- matrix --configs h200 --concurrency 32 --rep-from 0 --reps 1` | 60 | 1.68 | 1.67 | 25 |

Total over 85 runs: GPU $194.56 + startup $17.94 + sandbox estimate $165.26; 52.4 server-hours if run one after another.
