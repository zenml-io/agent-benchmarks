# How soon do two runs of the same task diverge?

3082 Terminal-Bench trajectories with recorded actions. Up to 1500 sampled pairs per row.

## Exact match (identical commands)

| harness | pair differs by | pairs | median first differing step | differ at step 1 | by step 3 | share of the shorter run replayable | outcomes differ: diverged by step 3 | after step 3 |
|---|---|---|---|---|---|---|---|---|
| terminus-2 | rerun | 1500 | 1 | 92% | 100% | 2% | 20% (n=1500) | n/a |
| terminus-2 | infra change | 1500 | 1 | 93% | 100% | 1% | 22% (n=1500) | n/a |
| terminus-2 | thinking off | 591 | 1 | 93% | 100% | 1% | 20% (n=591) | n/a |
| terminus-2 | model change | 887 | 1 | 95% | 100% | 1% | 31% (n=887) | n/a |
| mini-swe-agent | rerun | 1194 | 1 | 80% | 98% | 3% | 17% (n=1174) | 15% (n=20) |
| mini-swe-agent | infra change | 1500 | 1 | 86% | 100% | 4% | 21% (n=1498) | 100% (n=2) |
| mini-swe-agent | thinking off | 368 | 1 | 99% | 100% | 0% | 26% (n=368) | n/a |
| mini-swe-agent | model change | 654 | 1 | 100% | 100% | 0% | 41% (n=654) | n/a |

## Near match (>= 80% similar text)

| harness | pair differs by | pairs | median first differing step | differ at step 1 | by step 3 | share of the shorter run replayable | outcomes differ: diverged by step 3 | after step 3 |
|---|---|---|---|---|---|---|---|---|
| terminus-2 | rerun | 1500 | 1 | 77% | 99% | 7% | 20% (n=1487) | 8% (n=13) |
| terminus-2 | infra change | 1500 | 1 | 78% | 99% | 6% | 21% (n=1486) | 0% (n=14) |
| terminus-2 | thinking off | 591 | 1 | 80% | 99% | 6% | 20% (n=584) | 43% (n=7) |
| terminus-2 | model change | 887 | 1 | 84% | 100% | 5% | 31% (n=886) | 0% (n=1) |
| mini-swe-agent | rerun | 1194 | 1 | 61% | 96% | 7% | 17% (n=1152) | 14% (n=42) |
| mini-swe-agent | infra change | 1500 | 1 | 69% | 99% | 7% | 20% (n=1478) | 18% (n=22) |
| mini-swe-agent | thinking off | 368 | 1 | 93% | 100% | 4% | 26% (n=368) | n/a |
| mini-swe-agent | model change | 654 | 1 | 100% | 100% | 0% | 41% (n=654) | n/a |

## Lookup coverage (order-free, exact command text)

| harness | pair differs by | pairs | new run's commands found in the recorded run | leading commands answerable before the first miss (median) | runs with any recorded answer missing |
|---|---|---|---|---|---|
| terminus-2 | rerun | 1500 | 16% | 0 | 99% |
| terminus-2 | infra change | 1500 | 14% | 0 | 100% |
| terminus-2 | thinking off | 591 | 10% | 0 | 100% |
| terminus-2 | model change | 887 | 10% | 0 | 100% |
| mini-swe-agent | rerun | 1194 | 12% | 0 | 99% |
| mini-swe-agent | infra change | 1500 | 11% | 0 | 99% |
| mini-swe-agent | thinking off | 368 | 3% | 0 | 100% |
| mini-swe-agent | model change | 654 | 4% | 0 | 100% |
