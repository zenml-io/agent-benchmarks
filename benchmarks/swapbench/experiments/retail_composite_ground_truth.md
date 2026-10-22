Margin δ = 5 pts. Labels on the visible set are what a careful team could conclude from V alone; labels on the hidden set are the ground truth.

### Visible set V (tau2 train)

| model | episodes | API errors | pass^1 | $/episode | cost cut | Δ pass^1 [95% CI] | flips ↓/↑ | harmful writes/ep (Δ) | label |
|---|---|---|---|---|---|---|---|---|---|
| gpt-5-2025-08-07 | 60 | 0 | 0.883 | $0.1342 | 0% | incumbent | / | 0.050 (+0.000) |  |
| claude-haiku-5-5 | 60 | 0 | 0.933 | $0.0175 | 87% | +5.0 [-5.0, +15.0] | 3/6 | 0.000 (-0.050) | AMBIGUOUS |
| gpt-5-mini-2025-08-07 | 60 | 0 | 0.900 | $0.0216 | 84% | +1.7 [-10.0, +11.7] | 5/6 | 0.000 (-0.050) | AMBIGUOUS |
| gpt-5.4-nano | 60 | 0 | 0.833 | $0.0093 | 93% | -5.0 [-16.7, +6.7] | 7/4 | 0.100 (+0.050) | REGRESSED |
| gpt-6-luna | 60 | 0 | 0.883 | $0.0022 | 98% | +0.0 [-10.0, +10.0] | 5/5 | 0.017 (-0.033) | AMBIGUOUS |

### Hidden set H (tau2 test)

| model | episodes | API errors | pass^1 | $/episode | cost cut | Δ pass^1 [95% CI] | flips ↓/↑ | harmful writes/ep (Δ) | label |
|---|---|---|---|---|---|---|---|---|---|
| gpt-5-2025-08-07 | 240 | 0 | 0.954 | $0.1321 | 0% | incumbent | / | 0.008 (+0.000) |  |
| claude-haiku-5-5 | 240 | 0 | 0.958 | $0.0178 | 87% | +0.4 [-2.9, +3.8] | 8/9 | 0.013 (+0.004) | NON-INFERIOR |
| gpt-5-mini-2025-08-07 | 240 | 0 | 0.921 | $0.0270 | 80% | -3.3 [-7.5, +0.4] | 16/8 | 0.008 (+0.000) | AMBIGUOUS |
| gpt-5.4-nano | 240 | 0 | 0.812 | $0.0093 | 93% | -14.2 [-20.0, -8.3] | 45/11 | 0.067 (+0.058) | REGRESSED |
| gpt-6-luna | 240 | 0 | 0.887 | $0.0022 | 98% | -6.7 [-11.2, -2.1] | 23/7 | 0.017 (+0.008) | REGRESSED |
