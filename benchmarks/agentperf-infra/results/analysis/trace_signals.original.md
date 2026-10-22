# Can traces alone see the infrastructure?

47 Terminal-Bench runs that change only the infrastructure (same agent, model and time budget).

## 1. Flag runs served with a saturated KV cache

AUC of each trace-only feature for separating saturated runs (server KV peak >= 99%) from the rest, within each harness (1.0 = perfect, 0.5 = chance).

| harness | runs (saturated) | slower steps | lower generation rate | lower cache reuse |
|---|---|---|---|---|
| terminus-2 | 24 (12) | 0.92 | 0.94 | n/a |
| mini-swe-agent | 23 (13) | 0.98 | 0.95 | 1.00 |

Client-side cache reuse vs the server's prefix-cache hit rate (mini-swe-agent, 21 runs): Spearman +1.00.

## 2. Explain score changes between two runs of the same agent

Every pair of runs of the same harness: does the change in trace-only step time predict the change in solve rate? Pairs are what an eval tool compares (baseline vs new run).

| harness | pairs | Spearman: step-time ratio vs score change | score change when steps got >=1.3x slower | when within 1.3x |
|---|---|---|---|---|
| terminus-2 | 276 | -0.57 | -10.3 pts (n=169) | -1.6 pts (n=107) |
| mini-swe-agent | 253 | -0.61 | -10.3 pts (n=189) | -2.2 pts (n=64) |

## 3. Predict a run's score from its traces

Leave-one-run-out: predict each run's solve rate from the other runs of the same harness, by a linear fit on log step time (trace-only), versus predicting the harness average.

| harness | runs | mean abs. error, trace-only | mean abs. error, average | correlation |
|---|---|---|---|---|
| terminus-2 | 24 | 4.4 pts | 6.5 pts | +0.73 |
| mini-swe-agent | 23 | 3.7 pts | 7.4 pts | +0.79 |

## Runs

| harness | config | agents | GPU | solved | s/step | gen tok/s | cache reuse | KV peak | prefix hit (server) | preemptions |
|---|---|---|---|---|---|---|---|---|---|---|
| mini-swe-agent | h200-spec-mtp | 32 | H200 | 50% | 20 | 45.0 | 86% | 74% | 87% | 0 |
| mini-swe-agent | b200 | 32 | B200 | 56% | 22 | 43.4 | 92% | 42% | 92% | 0 |
| mini-swe-agent | defaults | 8 | H100 | 50% | 26 | 34.9 | 85% | 88% | 84% | 0 |
| mini-swe-agent | b200 | 32 | B200 | 46% | 26 | 40.7 | 91% | 44% | 92% | 0 |
| mini-swe-agent | weights-fp8 | 32 | H100 | 42% | 28 | 32.9 | 80% | 83% | 80% | 0 |
| mini-swe-agent | h200 | 32 | H200 | 47% | 28 | 32.1 | 90% | 50% | 90% | 0 |
| mini-swe-agent | h200 | 32 | H200 | 44% | 34 | 29.6 | 89% | 62% | 89% | 0 |
| mini-swe-agent | weights-fp8 | 32 | H100 | 39% | 36 | 27.9 | 59% | 90% | 57% | 0 |
| mini-swe-agent | defaults | 16 | H100 | 42% | 39 | 22.6 | 44% | 99% | 44% | 75 |
| mini-swe-agent | kv-fp8 | 32 | H100 | 36% | 40 | 21.5 | 54% | 86% | 54% | 0 |
| mini-swe-agent | spec-mtp | 16 | H100 | 47% | 40 | 25.5 | 23% | 99% | 26% | 712 |
| mini-swe-agent | kv-fp8 | 32 | H100 | 39% | 41 | 19.0 | 57% | 96% | 57% | 0 |
| mini-swe-agent | defaults | 16 | H100 | 44% | 43 | 24.7 | 44% | 100% | 44% | 94 |
| mini-swe-agent | no-prefix-cache | 32 | H100 | 36% | 54 | 16.0 | 0% | 100% |  | 17 |
| mini-swe-agent | defaults | 32 | H100 | 28% | 61 | 14.6 | 39% | 100% | 38% | 174 |
| mini-swe-agent | spec-mtp | 32 | H100 | 47% | 67 | 13.5 | 44% | 100% | 46% | 423 |
| mini-swe-agent | no-prefix-cache | 32 | H100 | 33% | 69 | 14.4 | 0% | 100% |  | 20 |
| mini-swe-agent | defaults | 32 | H100 | 35% | 69 | 14.1 | 23% | 100% | 23% | 431 |
| mini-swe-agent | spec-mtp | 32 | H100 | 33% | 75 | 11.3 | 31% | 100% | 28% | 1122 |
| mini-swe-agent | spec-mtp | 32 | H100 | 31% | 80 | 14.5 | 35% | 99% | 34% | 578 |
| mini-swe-agent | defaults | 32 | H100 | 22% | 82 | 14.5 | 28% | 100% | 32% | 169 |
| mini-swe-agent | defaults | 48 | H100 | 35% | 90 | 11.4 | 5% | 100% | 7% | 471 |
| mini-swe-agent | defaults | 64 | H100 | 26% | 112 | 8.1 | 52% | 100% | 51% | 431 |
| terminus-2 | h200-spec-mtp | 32 | H200 | 58% | 37 | 50.3 |  | 47% | 79% | 0 |
| terminus-2 | spec-mtp | 16 | H100 | 53% | 38 | 45.7 |  | 99% | 27% | 130 |
| terminus-2 | b200 | 32 | B200 | 56% | 47 | 46.3 |  | 22% | 84% | 0 |
| terminus-2 | b200 | 32 | B200 | 56% | 47 | 46.1 |  | 28% | 84% | 0 |
| terminus-2 | defaults | 16 | H100 | 50% | 48 | 29.7 |  | 70% | 71% | 0 |
| terminus-2 | h200 | 32 | H200 | 50% | 52 | 35.8 |  | 30% | 82% | 0 |
| terminus-2 | weights-fp8 | 32 | H100 | 42% | 56 | 29.6 |  | 60% | 74% | 0 |
| terminus-2 | h200 | 32 | H200 | 42% | 59 | 32.5 |  | 41% | 83% | 0 |
| terminus-2 | kv-fp8 | 32 | H100 | 50% | 63 | 23.6 |  | 76% | 52% | 0 |
| terminus-2 | weights-fp8 | 32 | H100 | 42% | 66 | 35.4 |  | 60% | 75% | 0 |
| terminus-2 | defaults | 8 | H100 | 53% | 67 | 34.3 |  | 47% | 82% | 0 |
| terminus-2 | defaults | 16 | H100 | 42% | 68 | 28.4 |  | 80% | 63% | 0 |
| terminus-2 | defaults | 32 | H100 | 42% | 69 | 20.2 |  | 99% | 18% | 208 |
| terminus-2 | kv-fp8 | 32 | H100 | 50% | 69 | 26.1 |  | 66% | 59% | 0 |
| terminus-2 | defaults | 32 | H100 | 42% | 70 | 20.8 |  | 100% | 16% | 126 |
| terminus-2 | defaults | 32 | H100 | 44% | 78 | 21.0 |  | 100% | 20% | 83 |
| terminus-2 | spec-mtp | 32 | H100 | 50% | 82 | 21.4 |  | 100% | 12% | 708 |
| terminus-2 | spec-mtp | 32 | H100 | 47% | 83 | 18.0 |  | 100% | 15% | 572 |
| terminus-2 | spec-mtp | 32 | H100 | 39% | 90 | 18.5 |  | 100% | 11% | 1341 |
| terminus-2 | defaults | 32 | H100 | 39% | 90 | 20.2 |  | 100% | 15% | 292 |
| terminus-2 | no-prefix-cache | 32 | H100 | 44% | 94 | 23.0 |  | 100% |  | 11 |
| terminus-2 | no-prefix-cache | 32 | H100 | 42% | 97 | 22.0 |  | 100% |  | 23 |
| terminus-2 | defaults | 48 | H100 | 33% | 112 | 15.3 |  | 100% | 19% | 447 |
| terminus-2 | defaults | 64 | H100 | 22% | 129 | 10.4 |  | 100% | 21% | 539 |
