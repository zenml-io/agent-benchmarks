| run | episodes | tool calls agreeing | episodes with every call agreeing | hand-written grade = recorded | generated grade = hand-written | calls on guessed paths | success hand-written → generated |
|---|---|---|---|---|---|---|---|
| haiku-5.5 | 480 | 100.0% | 100.0% | 100.0% | 100.0% | 7.1% | 95.4% → 95.4% |
| qwen27b-fp8 | 480 | 99.9% | 99.4% | 100.0% | 100.0% | 10.0% | 85.6% → 85.6% |
| qwen-moe-a3b | 480 | 99.9% | 99.6% | 100.0% | 100.0% | 8.1% | 94.8% → 94.8% |
| qwen27b-nothink | 480 | 99.7% | 99.2% | 100.0% | 100.0% | 8.6% | 92.9% → 92.9% |
| candidate | Δ vs incumbent, hand-written | truth | Δ vs incumbent, generated | truth | same? |
|---|---|---|---|---|---|
| qwen27b-fp8 | -9.8 [-13.8, -6.0] | REGRESSED | -9.8 [-13.8, -6.0] | REGRESSED | yes |
| qwen-moe-a3b | -0.6 [-3.3, +2.1] | NON-INFERIOR | -0.6 [-3.3, +2.1] | NON-INFERIOR | yes |
| qwen27b-nothink | -2.5 [-5.4, +0.2] | AMBIGUOUS | -2.5 [-5.4, +0.2] | AMBIGUOUS | yes |
