# Mechanisms

Terminal-Bench runs (`full`, `full-k2`). Exploratory.

## 1. KV saturation

| harness | config | agents | GPU | trials | KV peak | prefix hit | preemptions | solved |
|---|---|---|---|---|---|---|---|---|
| terminus-2 | defaults | 8 | H100 | 36 | 47% | 82% | 0 | 53% |
| terminus-2 | defaults | 16 | H100 | 108 | 75% | 67% | 0 | 44% |
| terminus-2 | defaults | 32 | H100 | 216 | 100% | 17% | 177 | 41% |
| terminus-2 | defaults | 48 | H100 | 72 | 100% | 19% | 447 | 33% |
| terminus-2 | defaults | 64 | H100 | 72 | 100% | 21% | 539 | 22% |
| terminus-2 | weights-fp8 | 32 | H100 | 72 | 60% | 74% | 0 | 42% |
| terminus-2 | kv-fp8 | 32 | H100 | 72 | 71% | 55% | 0 | 50% |
| terminus-2 | h200 | 32 | H200 | 108 | 36% | 83% | 0 | 44% |
| terminus-2 | b200 | 32 | B200 | 108 | 25% | 84% | 0 | 56% |
| terminus-2 | moe-a3b | 32 | H100 | 108 | 23% | 91% | 0 | 43% |
| mini-swe-agent | defaults | 8 | H100 | 36 | 88% | 84% | 0 | 50% |
| mini-swe-agent | defaults | 16 | H100 | 108 | 100% | 44% | 84 | 44% |
| mini-swe-agent | defaults | 32 | H100 | 144 | 100% | 31% | 258 | 30% |
| mini-swe-agent | defaults | 48 | H100 | 72 | 100% | 7% | 471 | 35% |
| mini-swe-agent | defaults | 64 | H100 | 72 | 100% | 51% | 431 | 26% |
| mini-swe-agent | weights-fp8 | 32 | H100 | 72 | 87% | 69% | 0 | 40% |
| mini-swe-agent | kv-fp8 | 32 | H100 | 72 | 91% | 55% | 0 | 38% |
| mini-swe-agent | h200 | 32 | H200 | 108 | 56% | 90% | 0 | 45% |
| mini-swe-agent | b200 | 32 | B200 | 108 | 43% | 92% | 0 | 49% |
| mini-swe-agent | moe-a3b | 32 | H100 | 108 | 32% | 94% | 0 | 49% |

## 2. Deadline fragility

Solved trials' agent time as a share of the task's limit.

| harness | config | agents | GPU | solves | in last quarter of limit | median |
|---|---|---|---|---|---|---|
| terminus-2 | defaults | 16 | H100 | 48 | 21% | 0.46 |
| terminus-2 | defaults | 32 | H100 | 89 | 34% | 0.55 |
| terminus-2 | h200 | 32 | H200 | 48 | 19% | 0.48 |
| terminus-2 | b200 | 32 | B200 | 60 | 10% | 0.34 |
| terminus-2 | moe-a3b | 32 | H100 | 46 | 2% | 0.19 |
| mini-swe-agent | defaults | 16 | H100 | 47 | 36% | 0.61 |
| mini-swe-agent | defaults | 32 | H100 | 43 | 70% | 0.92 |
| mini-swe-agent | h200 | 32 | H200 | 49 | 31% | 0.54 |
| mini-swe-agent | b200 | 32 | B200 | 53 | 17% | 0.40 |
| mini-swe-agent | moe-a3b | 32 | H100 | 53 | 8% | 0.22 |

Two attempts of the same task disagreeing (k2 runs):

- mini-swe-agent b200 32 B200: 3/36 tasks (8%)
- mini-swe-agent defaults-2x-time 32 H100!: 6/36 tasks (17%)
- mini-swe-agent defaults 16 H100!: 4/36 tasks (11%)
- mini-swe-agent defaults 32 H100!: 9/36 tasks (25%)
- mini-swe-agent defaults 48 H100!: 7/36 tasks (19%)
- mini-swe-agent defaults 64 H100!: 7/36 tasks (19%)
- mini-swe-agent h200 32 H200: 6/36 tasks (17%)
- mini-swe-agent moe-a3b 16 H100!: 6/36 tasks (17%)
- mini-swe-agent moe-a3b 32 H100!: 4/36 tasks (11%)
- mini-swe-agent no-thinking 32 H100!: 6/36 tasks (17%)
- mini-swe-agent spec-mtp 32 H100!: 6/36 tasks (17%)
- terminus-2 b200 32 B200: 8/36 tasks (22%)
- terminus-2 defaults-2x-time 32 H100!: 8/36 tasks (22%)
- terminus-2 defaults 16 H100!: 6/36 tasks (17%)
- terminus-2 defaults 32 H100!: 16/72 tasks (22%)
- terminus-2 defaults 48 H100!: 8/36 tasks (22%)
- terminus-2 defaults 64 H100!: 6/36 tasks (17%)
- terminus-2 h200 32 H200: 6/36 tasks (17%)
- terminus-2 moe-a3b 16 H100!: 8/36 tasks (22%)
- terminus-2 moe-a3b 32 H100!: 6/36 tasks (17%)
- terminus-2 no-thinking 32 H100!: 3/36 tasks (8%)
- terminus-2 spec-mtp 32 H100!: 10/36 tasks (28%)

## 3. Where request time goes

| harness | config | prompt : generated tokens | prefill s | decode s | decode share |
|---|---|---|---|---|---|
| mini-swe-agent | defaults | 14 : 1 | 1.31 | 40.8 | 97% |
| mini-swe-agent | moe-a3b | 53 : 1 | 0.22 | 5.8 | 96% |
| mini-swe-agent | no-thinking | 58 : 1 | 1.39 | 19.2 | 93% |
| terminus-2 | defaults | 4 : 1 | 0.83 | 42.9 | 98% |
| terminus-2 | moe-a3b | 14 : 1 | 0.19 | 8.2 | 98% |
| terminus-2 | no-thinking | 24 : 1 | 1.38 | 24.1 | 95% |

## 4. Early-kill policy (defaults, 32 agents, H100)

| harness | cap | solves kept | agent time used | cost per solve |
|---|---|---|---|---|
| terminus-2 | 50% of limit | 39% | 61% | 1.54x |
| terminus-2 | 75% of limit | 66% | 84% | 1.27x |
| mini-swe-agent | 50% of limit | 12% | 56% | 4.79x |
| mini-swe-agent | 75% of limit | 30% | 82% | 2.70x |

## 5. Timed out but solved

- terminus-2: 90 of 859 time-outs passed the tests (12% of all solves)
- mini-swe-agent: 130 of 820 time-outs passed the tests (20% of all solves)
