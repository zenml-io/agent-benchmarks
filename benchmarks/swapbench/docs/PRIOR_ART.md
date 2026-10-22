# Prior art for SwapBench (searched Oct 13, 2026)

**Verdict: the workflow is taken; the benchmark is open.**

The workflow already exists as products:
- An agent turns traces into a cheaper or fine-tuned model, then gets a migrate/don't-migrate verdict: LangSmith smithtune, EvalShift.
- Measuring item-level regressions across model upgrades: arXiv 2608.17719.

No benchmark we found has an agent **perform** the cost-cutting swap, makes it **declare** whether the swap is safe, and scores that declaration against a hidden replay set with **false-safe rate** as the headline. We also found no comparison of the agent alone against the agent with verification tools on that metric.

## Closest matches

| Work | What it does | Why it is not SwapBench |
|---|---|---|
| LangSmith Fine-Tuning / smithtune, Sep 24 2026 ([blog](https://www.langchain.com/blog/langsmith-fine-tuning), [repo](https://github.com/langchain-ai/smithtune)) | Traces become an SFT model trained on hosted fine-tuning services, driven by Claude Code/Codex through a skill. 80/10/10 split, next-step replay judged by an LLM, tools not executed. | A product. No safety verdict, no statistical gate. Its score is agreement with recorded steps, not task success. Nobody measures whether its go/no-go is right. |
| EvalShift ([site](https://www.evalshift.dev/)) | Replays captured traces on the current and candidate models. Gives a pass / conditional / fail migration verdict. | A verifier tool, i.e. arm 2, not a benchmark. Its verdict is never scored against ground truth. |
| Xu & Wu, arXiv [2608.17719](https://arxiv.org/abs/2608.17719), Aug 2026 | Item-level regressions across GPT-5.4 to 5.6. 50 trials per item, FDR control. Upgrades with +7.3 pts aggregate still have up to 8.3% of items reliably regressed. | Measurement only. No agent performs or judges the migration. Strongest prior art for the stats gate: cite it. |
| Sheng & Lu, arXiv [2608.13607](https://arxiv.org/abs/2608.13607) | Predicting per-sample regressions before an update. Finds no universal signal. | Measurement only. |
| MUSCLE, arXiv [2407.09435](https://arxiv.org/abs/2407.09435); RETAIN, arXiv [2409.03928](https://arxiv.org/pdf/2409.03928) | Negative flips under model updates; a human-facing migration regression tool. | No agent, no benchmark. |
| PostTrainBench, arXiv [2603.08640](https://arxiv.org/abs/2603.08640) | Claude Code/Codex post-train small models on 1 H100 in 10 h. Documents reward hacking. | Objective is capability, not cost at equal quality. No safety claim scored. |
| HarnessOpt-Bench, arXiv [2608.06301](https://arxiv.org/abs/2608.06301) | An optimizer agent edits a target agent's harness. Scored on a hidden partition inside a trusted environment. | Structurally closest: agent optimizes agent, with a hidden holdout. But its objective is quality gain, and it has no safety declaration. |
| AdaptFT-Bench, arXiv [2604.09791](https://arxiv.org/abs/2604.09791) | An agent continually fine-tunes small production models under regression constraints. | No false "no regression" metric. |
| OverclaimBench, arXiv [2609.20812](https://arxiv.org/abs/2609.20812) | Coding agents falsely claim completed reviews (80.4% of incomplete runs). | Overclaiming in file review, not safety calls under sampling noise. |
| RewardHackingAgents, arXiv [2603.11337](https://arxiv.org/abs/2603.11337) | An ML agent's reported metric vs a trusted reference. | Scores tampering, not honest-but-wrong verdicts. |
| RouteLLM, FrugalGPT, router benchmarks | Cost/quality routing. | No agent performs a migration. |
| tau-bench / tau2-bench ([repo](https://github.com/sierra-research/tau2-bench)) | Mocked-tool multi-turn agents with pass^k. | An environment we build on. It doesn't frame a model swap as the task. |

## What not to claim

Each of these is already published:
- agents fine-tuning LLMs;
- agents optimizing agents on a hidden holdout;
- trace-to-distilled-model pipelines driven by coding agents;
- migration verdict tools;
- aggregate scores hiding item regressions;
- agents overclaiming or gaming their own metric.

## What is open

1. Scoring an agent's **safety declaration** against a hidden replay set: false-safe rate under sampling noise and distribution detail, not tampering.
2. **Cost cut at equal quality** for multi-turn tool-using agents, where the agent picks between swap, prompt change and distillation.
3. Whether verification tooling (mocked replay, sealed holdout, stats gate, calibrated judges) **actually lowers false-safe rates**. The products above sell this, but nobody has measured it.

## Claims checked from the strategy notes

- **OpenAI Evals shutdown is real.** Announced Jun 3 2026, read-only Oct 31, shut down Nov 30 2026. OpenAI points users to Promptfoo. [deprecations](https://developers.openai.com/api/docs/deprecations)
- **Kimi Vendor Verifier is real** and includes a tool-call F1/schema check, but no multi-turn agentic test. [blog](https://www.kimi.com/en/blog/kimi-vendor-verifier)
- **Artificial Analysis provider variance:** seen only in secondary sources, e.g. gpt-oss-120b at 22% vs 37% on BFCL depending on the endpoint ([DEV post](https://dev.to/mr_manushukla/open-models-cut-the-gap-to-6-points-in-2026-then-lost-half-their-accuracy-at-the-endpoint-5h8b)). Not verified at the source.
- **"90% single-turn to ~59% over 5 turns" (distil labs):** found only in a LinkedIn post, and it equals 0.9^5, i.e. independent turns assumed. **It is arithmetic, not a measurement. Don't cite it as evidence.** SwapBench can measure the real multi-turn compounding.


## Update, Oct 15: second review

A second, adversarial search found closer prior work than the first review. The full list with links is the Related work section of [`docs/WRITEUP.md`](WRITEUP.md#related-work). Most important: The Replay Gap (arXiv 2608.08239) for next-step vs live replay, Certifying Model Upgrades (arXiv 2609.13714) for non-inferiority gating of upgrades, and OpenRouter's per-provider tau2-bench results for provider variance.
