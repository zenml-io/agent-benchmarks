# Expert-deciders benchmark: API spend

No GPU time is used.

## Offline (labels, arms, rubric)

| item | tokens | USD |
|---|---|---|
| expert labels: claude (3468 answers) | 14,181,290 in / 1,341,777 out | 2.09 |
| expert labels: gpt (1500 answers) | 4,315,958 in / 543,967 out | 2.17 |
| judge D offline (GPT-6.1 Sol), 1,500 decisions | 15,230,206 in / 40,883 out | 30.87 |
| interview rubric (GPT-6.1 Sol, 3 calls, estimated) | ~60k in / ~15k out | 0.27 |
| Jev offline arm B, 1,500 decisions | 3,124,803 in | 0.13 |
| Jev offline arm C, 1,500 decisions | 5,016,013 in | 0.21 |
| Jev offline arm G, 1,500 decisions | 3,346,303 in | 0.14 |
| embeddings (text-embedding-3-small, ~4 chars/token) | ~6,549,948 in | 0.13 |
| **offline total** | | **36.01** |

## Live runs (bank hidden set x2)

| run | conversations | agent + check USD | customer simulator USD |
|---|---|---|---|
| A_C | 480 | 12.38 | 0.52 |
| A_D | 480 | 29.02 | 0.53 |
| A_G | 480 | 11.65 | 0.47 |
| A_H | 480 | 11.32 | 0.47 |
| A_none | 480 | 11.22 | 0.46 |
| B_C | 480 | 12.08 | 0.52 |
| B_D | 480 | 32.46 | 0.53 |
| B_G | 480 | 11.25 | 0.47 |
| B_H | 480 | 11.09 | 0.49 |
| B_none | 480 | 6.61 | 0.45 |
| R_gpt5 | 480 | 36.54 | 0.49 |
| A_B (dropped) | 22 | 0.66 | 0.02 |
| A_E (dropped) | 22 | 0.65 | 0.02 |
| B_E (dropped) | 7 | 0.19 | 0.01 |
| B_C (another provider, set aside) | 42 | 1.19 | 0.02 |
| B_D (another provider, set aside) | 33 | 1.99 | 0.02 |
| B_G (another provider, set aside) | 54 | 1.35 | 0.03 |
| B_H (another provider, set aside) | 43 | 1.10 | 0.02 |
| B_none (another provider, set aside) | 81 | 0.25 | 0.06 |
| **live total** | | | **198.63** |

**Benchmark total: $234.64**.
