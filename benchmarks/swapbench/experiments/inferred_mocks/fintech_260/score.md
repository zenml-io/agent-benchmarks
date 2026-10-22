| run | episodes | tool calls agreeing | episodes with every call agreeing | hand-written grade = recorded | generated grade = hand-written | calls on guessed paths | success hand-written → generated |
|---|---|---|---|---|---|---|---|
| gpt-5 | 480 | 100.0% | 100.0% | 100.0% | 96.2% | 12.2% | 94.2% → 92.9% |
| qwen27b-bf16 | 480 | 100.0% | 100.0% | 100.0% | 96.9% | 12.4% | 88.5% → 87.1% |
| gpt-6-luna | 480 | 100.0% | 99.8% | 100.0% | 97.1% | 12.5% | 91.7% → 89.6% |
| gpt-5.4-nano | 480 | 99.6% | 98.5% | 100.0% | 98.3% | 15.0% | 56.7% → 56.2% |
| gpt-5-mini | 480 | 99.9% | 99.8% | 100.0% | 97.3% | 12.4% | 94.4% → 92.1% |
| qwen27b-fp8 | 445 | 100.0% | 100.0% | 100.0% | 97.1% | 13.0% | 88.8% → 87.2% |
| candidate | Δ vs incumbent, hand-written | truth | Δ vs incumbent, generated | truth | same? |
|---|---|---|---|---|---|
| qwen27b-bf16 | -5.6 [-8.8, -2.5] | REGRESSED | -5.8 [-9.0, -2.7] | REGRESSED | yes |
| gpt-6-luna | -2.5 [-5.4, +0.4] | REGRESSED | -3.3 [-6.2, -0.4] | REGRESSED | yes |
| gpt-5.4-nano | -37.5 [-42.9, -32.1] | REGRESSED | -36.7 [-42.1, -31.2] | REGRESSED | yes |
| gpt-5-mini | +0.2 [-2.5, +2.9] | NON-INFERIOR | -0.8 [-3.1, +1.5] | NON-INFERIOR | yes |
| qwen27b-fp8 | -6.0 [-9.4, -2.9] | REGRESSED | -6.2 [-9.8, -2.9] | REGRESSED | yes |
