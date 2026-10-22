# Expert-deciders benchmark: live test (bank hidden set x2, hidden-rule grading)

| run | conversations (empty) | resolved | vs same agent, no check [95% CI] | vs GPT-5 [95% CI] | rule violations / conv. | conv. with a violation | handoffs / conv. | unneeded handoffs / conv. | checks (blocked) | cost / conv. (check) |
|---|---|---|---|---|---|---|---|---|---|---|
| A_C | 480 (0) | 54.8% | +2.1 [-3.8, +8.1] | -5.2 [-11.2, +1.0] | 0.004 | 0.4% | 0.404 | 0.183 | 714 (424) | 2.579¢ (0.0209¢) |
| A_D | 480 (0) | 46.2% | -6.5 [-13.3, +0.6] | -13.8 [-21.0, -6.5] | 0.002 | 0.2% | 0.415 | 0.231 | 747 (501) | 6.046¢ (3.4714¢) |
| A_G | 480 (0) | 59.4% | +6.7 [+1.9, +11.7] | -0.6 [-5.8, +4.6] | 0.002 | 0.2% | 0.477 | 0.219 | 619 (241) | 2.428¢ (0.0121¢) |
| A_H | 480 (0) | 53.8% | +1.0 [-4.6, +6.9] | -6.2 [-12.1, -0.2] | 0.006 | 0.6% | 0.508 | 0.237 | 657 (325) | 2.359¢ (0.0099¢) |
| A_none | 480 (0) | 52.7% | — | -7.3 [-10.8, -4.0] | 0.392 | 37.3% | 0.369 | 0.163 | 0 (0) | 2.338¢ |
| B_C | 480 (9) | 71.7% | +12.1 [+6.0, +18.1] | +11.7 [+5.6, +17.7] | 0.010 | 1.0% | 0.319 | 0.108 | 795 (489) | 2.518¢ (0.0233¢) |
| B_D | 480 (11) | 62.5% | +2.9 [-4.2, +10.0] | +2.5 [-4.6, +9.6] | 0.004 | 0.4% | 0.354 | 0.148 | 867 (611) | 6.763¢ (4.0290¢) |
| B_G | 480 (12) | 71.5% | +11.9 [+6.9, +17.1] | +11.5 [+6.5, +16.5] | 0.013 | 1.0% | 0.421 | 0.167 | 743 (367) | 2.344¢ (0.0145¢) |
| B_H | 480 (5) | 66.9% | +7.3 [+1.5, +13.1] | +6.9 [+1.0, +12.7] | 0.004 | 0.4% | 0.446 | 0.194 | 718 (361) | 2.311¢ (0.0126¢) |
| B_none | 480 (0) | 59.6% | — | -0.4 [-2.3, +1.2] | 0.394 | 37.7% | 0.338 | 0.127 | 0 (0) | 1.378¢ |
| R_gpt5 | 480 (0) | 60.0% | — | — | 0.398 | 38.1% | 0.321 | 0.119 | 0 (0) | 7.612¢ |

Paired difference in rule violations per conversation vs the same agent with no check:

- A_C: -0.388 [-0.452, -0.325]
- A_D: -0.390 [-0.454, -0.327]
- A_G: -0.390 [-0.454, -0.327]
- A_H: -0.385 [-0.452, -0.323]
- B_C: -0.383 [-0.450, -0.321]
- B_D: -0.390 [-0.456, -0.327]
- B_G: -0.381 [-0.446, -0.319]
- B_H: -0.390 [-0.456, -0.327]

Paired difference in unneeded handoffs per conversation vs the same agent with no check:

- A_C: +0.021 [-0.037, +0.079]
- A_D: +0.069 [+0.008, +0.131]
- A_G: +0.056 [-0.004, +0.115]
- A_H: +0.075 [+0.010, +0.140]
- B_C: -0.019 [-0.071, +0.033]
- B_D: +0.021 [-0.035, +0.077]
- B_G: +0.040 [-0.019, +0.096]
- B_H: +0.067 [+0.004, +0.129]

Paired difference in handoffs per conversation vs the same agent with no check:

- A_C: +0.035 [-0.033, +0.104]
- A_D: +0.046 [-0.025, +0.117]
- A_G: +0.108 [+0.044, +0.173]
- A_H: +0.140 [+0.069, +0.210]
- B_C: -0.019 [-0.077, +0.042]
- B_D: +0.017 [-0.048, +0.079]
- B_G: +0.083 [+0.021, +0.146]
- B_H: +0.108 [+0.044, +0.175]

Blocked decisions by hidden-rule truth (precision of the live check):

- A_C: blocked 424, of which breaking a hidden rule 186; allowed but breaking a rule 1; by action {'escalate_to_human': 173, 'issue_refund': 143, 'freeze_card': 108}
- A_D: blocked 501, of which breaking a hidden rule 185; allowed but breaking a rule 0; by action {'escalate_to_human': 209, 'issue_refund': 175, 'freeze_card': 117}
- A_G: blocked 241, of which breaking a hidden rule 187; allowed but breaking a rule 0; by action {'escalate_to_human': 68, 'issue_refund': 129, 'freeze_card': 44}
- A_H: blocked 325, of which breaking a hidden rule 188; allowed but breaking a rule 2; by action {'escalate_to_human': 78, 'issue_refund': 135, 'freeze_card': 112}
- B_C: blocked 489, of which breaking a hidden rule 311; allowed but breaking a rule 3; by action {'escalate_to_human': 194, 'issue_refund': 242, 'freeze_card': 53}
- B_D: blocked 611, of which breaking a hidden rule 318; allowed but breaking a rule 0; by action {'escalate_to_human': 224, 'issue_refund': 310, 'freeze_card': 77}
- B_G: blocked 367, of which breaking a hidden rule 333; allowed but breaking a rule 0; by action {'escalate_to_human': 81, 'issue_refund': 232, 'freeze_card': 54}
- B_H: blocked 361, of which breaking a hidden rule 290; allowed but breaking a rule 1; by action {'escalate_to_human': 76, 'issue_refund': 230, 'freeze_card': 55}
