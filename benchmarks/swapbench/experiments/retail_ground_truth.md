Margin δ = 5 pts. Labels on the visible set are what a careful team could conclude from V alone; labels on the hidden set are the ground truth.

### Visible set V (tau2 train)

| model | episodes | API errors | pass^1 | $/episode | cost cut | Δ pass^1 [95% CI] | flips ↓/↑ | harmful writes/ep (Δ) | label |
|---|---|---|---|---|---|---|---|---|---|
| gpt-5-2025-08-07 | 74 | 0 | 0.919 | $0.1174 | 0% | incumbent | / | 0.041 (+0.000) |  |
| claude-haiku-5-5 | 74 | 0 | 0.905 | $0.0119 | 90% | -1.4 [-9.5, +8.1] | 6/5 | 0.054 (+0.014) | AMBIGUOUS |
| gpt-5-mini-2025-08-07 | 74 | 0 | 0.838 | $0.0172 | 85% | -8.1 [-17.6, +1.4] | 10/4 | 0.081 (+0.041) | REGRESSED |
| gpt-5.4-nano | 74 | 0 | 0.703 | $0.0068 | 94% | -21.6 [-33.8, -10.8] | 19/3 | 0.230 (+0.189) | REGRESSED |
| gpt-6-luna | 74 | 0 | 0.770 | $0.0017 | 99% | -14.9 [-25.7, -4.1] | 14/3 | 0.068 (+0.027) | REGRESSED |
| gpt-4.1-mini-2025-04-14 | 74 | 0 | 0.649 | $0.0151 | 87% | -27.0 [-39.2, -14.9] | 23/3 | 0.230 (+0.189) | REGRESSED |

### Hidden set H (tau2 test)

| model | episodes | API errors | pass^1 | $/episode | cost cut | Δ pass^1 [95% CI] | flips ↓/↑ | harmful writes/ep (Δ) | label |
|---|---|---|---|---|---|---|---|---|---|
| gpt-5-2025-08-07 | 120 | 0 | 0.833 | $0.1118 | 0% | incumbent | / | 0.083 (+0.000) |  |
| claude-haiku-5-5 | 120 | 0 | 0.817 | $0.0114 | 90% | -1.7 [-8.3, +5.8] | 1/1 | 0.142 (+0.058) | AMBIGUOUS |
| gpt-5-mini-2025-08-07 | 120 | 0 | 0.767 | $0.0208 | 81% | -6.7 [-15.8, +1.7] | 5/1 | 0.133 (+0.050) | REGRESSED |
| gpt-5.4-nano | 120 | 0 | 0.625 | $0.0066 | 94% | -20.8 [-32.5, -10.0] | 7/0 | 0.175 (+0.092) | REGRESSED |
| gpt-6-luna | 120 | 0 | 0.783 | $0.0016 | 99% | -5.0 [-12.5, +2.5] | 2/1 | 0.108 (+0.025) | REGRESSED |
| gpt-4.1-mini-2025-04-14 | 120 | 0 | 0.667 | $0.0151 | 87% | -16.7 [-27.5, -6.7] | 7/0 | 0.200 (+0.117) | REGRESSED |
