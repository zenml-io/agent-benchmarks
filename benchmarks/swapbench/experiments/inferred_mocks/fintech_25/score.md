| run | episodes | tool calls agreeing | episodes with every call agreeing | hand-written grade = recorded | generated grade = hand-written | calls on guessed paths | success hand-written → generated |
|---|---|---|---|---|---|---|---|
| gpt-5 | 480 | 98.9% | 97.5% | 100.0% | 96.2% | 6.7% | 94.2% → 92.9% |
| qwen27b-bf16 | 480 | 97.5% | 89.6% | 100.0% | 89.8% | 7.8% | 88.5% → 80.0% |
| gpt-6-luna | 480 | 99.0% | 97.5% | 100.0% | 97.1% | 6.5% | 91.7% → 89.6% |
| gpt-5.4-nano | 480 | 98.7% | 95.2% | 100.0% | 98.3% | 10.5% | 56.7% → 55.4% |
| gpt-5-mini | 480 | 98.9% | 97.5% | 100.0% | 97.5% | 6.9% | 94.4% → 91.9% |
| qwen27b-fp8 | 445 | 97.5% | 90.1% | 100.0% | 90.6% | 7.9% | 88.8% → 80.7% |
| candidate | Δ vs incumbent, hand-written | truth | Δ vs incumbent, generated | truth | same? |
|---|---|---|---|---|---|
| qwen27b-bf16 | -5.6 [-8.8, -2.5] | REGRESSED | -12.9 [-16.5, -9.4] | REGRESSED | yes |
| gpt-6-luna | -2.5 [-5.4, +0.4] | REGRESSED | -3.3 [-6.2, -0.4] | REGRESSED | yes |
| gpt-5.4-nano | -37.5 [-42.9, -32.1] | REGRESSED | -37.5 [-42.9, -32.1] | REGRESSED | yes |
| gpt-5-mini | +0.2 [-2.5, +2.9] | NON-INFERIOR | -1.0 [-3.3, +1.2] | NON-INFERIOR | yes |
| qwen27b-fp8 | -6.0 [-9.4, -2.9] | REGRESSED | -12.9 [-16.9, -9.2] | REGRESSED | yes |
