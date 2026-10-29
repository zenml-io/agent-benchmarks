# Agent benchmarks

Benchmarks of AI agents on real work, from the [Kitaru](https://github.com/zenml-io/kitaru) team at ZenML. Each one asks a practical question (which model should this agent run on, is a model swap safe, does the serving setup change what gets solved) and counts what each correct answer costs.

Every benchmark follows the same layout ([STANDARD.md](STANDARD.md)): a README with the question, results, how far the results have been checked, and how close it is to running on [Harbor](https://www.harborframework.com); a RERUN.md that takes you from a clean machine to the published tables; the code; and the per-case result rows. Results files share one schema ([EXPORT_SCHEMA.md](EXPORT_SCHEMA.md)).

## The benchmarks

| Benchmark | Question | Status | Harbor |
|---|---|---|---|
| [underwriting](benchmarks/underwriting) | What does a correct decision cost when 12 models run the same insurance underwriting agent, and how much of the gap is the prompt? | complete (Oct 21-22, 2026) | native ([harbor/](benchmarks/underwriting/harbor): four checks pass on a 12-case sample; no model run yet) |
| [claims-over-time](benchmarks/claims-over-time) | When a medical-appeals agent meets new cases in batches, does an improver working through Kitaru's recorded sessions and replays improve it more than Codex working from trace files? | complete (two runs, Oct 27-29, 2026) | native (each improvement round is a Harbor trial) |
| [tau2-telecom](benchmarks/tau2-telecom) | If you swap the model behind a tau2-bench Telecom support agent, or fix its prompt, does it solve more tasks, and does a cheap step screen predict which swaps will? | complete (Oct 22, 2026) | portable (Harbor hosts the tasks) |
| [model-swap-on-recorded-traffic](benchmarks/model-swap-on-recorded-traffic) | Can a step-level replay of an agent's recorded model calls pick replacement models that keep full-run task success? | complete; full-run ground truth withheld | not applicable (step check) |
| [swapbench](benchmarks/swapbench) | Is it safe to swap the model behind a production customer-service agent, and which checks can tell? | complete; hosted-provider results withheld | portable |
| [expert-deciders](benchmarks/expert-deciders) | Can a few hundred expert answers, a rubric and a Jev check beat a frontier judge at keeping a cheap agent to a bank's unwritten rules? | complete | portable (after SwapBench) |
| [decision-agents](benchmarks/decision-agents) | Are tool-using decision agents accurate against real outcomes (health appeals, veterans' appeals, German health-insurance suits), and stable across reruns? | complete | portable |
| [agentperf-infra](benchmarks/agentperf-infra) | Do GPU, load and serving settings change how many Terminal-Bench and GAIA tasks a self-hosted agent solves, and what each solve costs? | complete | native |
| [ml-training-ops](benchmarks/ml-training-ops) | Can agents do ML training operations, and does the serving setup of a self-hosted model change how many they solve? | stopped (frontier agents solve 88-100%) | native |
| [sglang-vs-vllm](benchmarks/sglang-vs-vllm) | At equal hardware and identical agent traffic, does the serving engine change throughput and latency? | complete | not applicable |
| [haiku-tax](benchmarks/haiku-tax) | On enterprise agent tasks, which closed or open-weight model gives the most successful tasks per dollar? | run complete; **results withheld** | portable |

[self-hosted-agents-harness](benchmarks/self-hosted-agents-harness) is the shared runner for the self-hosted benchmarks (vLLM and SGLang servers, Harbor jobs, metrics).

**Harbor column:** `native` means every trial already runs as a Harbor job; `portable` means the README lists what porting would take; `not applicable` means there are no agents or tasks to run.

## How much to trust these results

These benchmarks were built quickly, mostly by coding agents, and have not been independently reviewed. Moving them here meant re-running every free step from a clean checkout: downloading the data, rebuilding environments, running offline tests, and regenerating every published table from the committed per-case rows. Each README's **Trust status** says what that reproduced, what it could not, the places where earlier write-ups disagree with the data, and what would vet the result further. No paid run has been repeated yet.

Common limits across them: one run per case in most conditions (so small differences are noise; several benchmarks measure that noise directly), simulated users and LLM judges, list prices, and environments that are synthetic or rebuilt from published traces.

## What is not here

- **Withheld results.** Results that compare named inference providers (the Haiku Tax grid and SwapBench's hosted-provider runs) stay out until each provider has seen its numbers. The code to run your own comparison is included.
- **Hidden test sets.** SwapBench's hidden sets and their seeds stay private so they remain usable as held-out tests; the public sets and generators are included.
- **Raw traces.** Full transcripts and run folders are not published; per-case result rows are.
- **Third-party data** is downloaded by each benchmark's scripts under its own license rather than copied here.

## Where this is going

The next step is to make every benchmark that has agents and tasks run natively on Harbor, following the target in [STANDARD.md](STANDARD.md#harbor-native-target-the-second-pass): Harbor task format, the four checks (reference solution passes, doing nothing fails, shortcuts fail, a second valid solution passes), setups as config, and a registry so the whole set runs from this repo.

## License

Apache-2.0 ([LICENSE](LICENSE)). Third-party datasets keep their own licenses, listed in each benchmark's RERUN.md.
