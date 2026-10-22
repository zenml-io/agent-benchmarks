# Confirmatory tests (PREREGISTRATION.md)

Runs recorded after 2026-10-09T07:12:08 UTC only: 48 runs.

| claim | effect, pts (95% CI) | one-sided p | Holm-adjusted p | verdict |
|---|---|---|---|---|
| C1 GPU x harness: H200 vs H100 at c=32 | +9 (-7 to +24), 36 tasks | 0.126 | 0.291 | not confirmed |
| C2 load x harness: c=32 vs c=16 on H100 | -9 (-24 to +5), 36 tasks | 0.097 | 0.291 | not confirmed |
| C3 reasoning x harness: no-thinking vs defaults at c=32 | -3 (-17 to +10), 36 tasks | 0.691 | 0.691 | not confirmed |

**C4** (failure mix follows server speed), over cells with >= 36 new trials: 38 cells. Spearman rho with median s/step: 'out of time, working' +0.67 (p = 0.000); 'finished wrong' -0.50 (p = 1.000). Confirmed.

