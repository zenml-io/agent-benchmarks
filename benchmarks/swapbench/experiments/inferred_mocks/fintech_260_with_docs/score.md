| run | episodes | tool calls agreeing | episodes with every call agreeing | hand-written grade = recorded | generated grade = hand-written | calls on guessed paths | success hand-written → generated |
|---|---|---|---|---|---|---|---|
| gpt-5 | 480 | 100.0% | 100.0% | 100.0% | 98.8% | 0.0% | 94.2% → 95.4% |
| qwen27b-bf16 | 480 | 100.0% | 100.0% | 100.0% | 99.2% | 0.0% | 88.5% → 89.4% |
| gpt-6-luna | 480 | 100.0% | 100.0% | 100.0% | 99.6% | 0.0% | 91.7% → 92.1% |
| gpt-5.4-nano | 480 | 99.8% | 99.0% | 100.0% | 99.8% | 0.0% | 56.7% → 56.9% |
| gpt-5-mini | 480 | 100.0% | 100.0% | 100.0% | 100.0% | 0.0% | 94.4% → 94.4% |
| qwen27b-fp8 | 445 | 100.0% | 100.0% | 100.0% | 99.3% | 0.0% | 88.8% → 89.4% |
| candidate | Δ vs incumbent, hand-written | truth | Δ vs incumbent, generated | truth | same? |
|---|---|---|---|---|---|
| qwen27b-bf16 | -5.6 [-8.8, -2.5] | REGRESSED | -6.0 [-9.2, -2.9] | REGRESSED | yes |
| gpt-6-luna | -2.5 [-5.4, +0.4] | REGRESSED | -3.3 [-6.2, -0.4] | REGRESSED | yes |
| gpt-5.4-nano | -37.5 [-42.9, -32.1] | REGRESSED | -38.5 [-44.0, -33.1] | REGRESSED | yes |
| gpt-5-mini | +0.2 [-2.5, +2.9] | NON-INFERIOR | -1.0 [-3.3, +1.2] | NON-INFERIOR | yes |
| qwen27b-fp8 | -6.0 [-9.4, -2.9] | REGRESSED | -6.5 [-10.0, -3.3] | REGRESSED | yes |
