| run | episodes | tool calls agreeing | episodes with every call agreeing | hand-written grade = recorded | generated grade = hand-written | calls on guessed paths | success hand-written → generated |
|---|---|---|---|---|---|---|---|
| gpt-5 | 480 | 98.9% | 97.5% | 100.0% | 98.8% | 18.1% | 94.2% → 95.4% |
| qwen27b-bf16 | 480 | 97.5% | 89.6% | 100.0% | 98.8% | 19.5% | 88.5% → 89.8% |
| gpt-6-luna | 480 | 99.0% | 97.5% | 100.0% | 99.4% | 18.4% | 91.7% → 92.3% |
| gpt-5.4-nano | 480 | 98.6% | 95.0% | 100.0% | 99.8% | 21.7% | 56.7% → 56.9% |
| gpt-5-mini | 480 | 98.8% | 97.3% | 100.0% | 99.8% | 18.3% | 94.4% → 94.6% |
| qwen27b-fp8 | 445 | 97.5% | 90.1% | 100.0% | 99.3% | 19.7% | 88.8% → 89.4% |
| candidate | Δ vs incumbent, hand-written | truth | Δ vs incumbent, generated | truth | same? |
|---|---|---|---|---|---|
| qwen27b-bf16 | -5.6 [-8.8, -2.5] | REGRESSED | -5.6 [-8.8, -2.5] | REGRESSED | yes |
| gpt-6-luna | -2.5 [-5.4, +0.4] | REGRESSED | -3.1 [-6.0, -0.2] | REGRESSED | yes |
| gpt-5.4-nano | -37.5 [-42.9, -32.1] | REGRESSED | -38.5 [-44.0, -33.1] | REGRESSED | yes |
| gpt-5-mini | +0.2 [-2.5, +2.9] | NON-INFERIOR | -0.8 [-3.1, +1.5] | NON-INFERIOR | yes |
| qwen27b-fp8 | -6.0 [-9.4, -2.9] | REGRESSED | -6.5 [-10.0, -3.3] | REGRESSED | yes |
