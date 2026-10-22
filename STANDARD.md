# The benchmark standard

Every benchmark in this repo has the same layout, so anyone (or any coding agent) can rerun, check, or port it without asking the person who built it.

## Layout

```
benchmarks/<slug>/
  README.md        what it asks, the published results, how much to trust them, Harbor status
  RERUN.md         every step from a clean machine to the published tables, with cost and time
  pyproject.toml   pinned dependencies for this benchmark only (uv)
  .env.example     names of every environment variable it reads; no values
  src/ or harness/ the code that runs it
  data/            only data we created and may redistribute; third-party data is fetched by a script
  scripts/         fetch_data, smoke test, analysis/report scripts
  results/
    <slug>.json    the export (schema below)
    runs/          per-case result rows (JSONL), when the data license allows; no transcripts
```

## README.md sections (in this order)

1. **Question**: one line.
2. **Status**: complete / in progress / stopped (why); run dates; total spend.
3. **Results**: the main table(s), each number with its n, copied from `results/<slug>.json`.
4. **Trust status**: what was checked (and how), what wasn't, known inconsistencies between earlier write-ups and the data, and the concrete steps that would vet it further. Never claim more certainty than the checks support.
5. **Harbor status**: `native` (already runs as a Harbor job), `portable` (what porting would take: task packaging, verifier, simulated user, etc.), or `not applicable` (why).
6. **Limitations**.
7. **Provenance**: where it came from (original repo path and commit), who ran it.

## RERUN.md sections (in this order)

1. **Prerequisites**: OS, Python version, uv, Docker/Modal/GPU if needed, accounts.
2. **Credentials**: every env var by name, what it is for, and which steps need it. Never values.
3. **Install**: exact commands.
4. **Get the data**: exact commands; source URLs and licenses.
5. **Free checks**: commands that cost nothing (offline tests, rebuilding environments, regenerating every published table from `results/runs/`). Each with the expected output.
6. **Smoke test**: the smallest paid run, its cost, and what success looks like.
7. **Full rerun**: commands per condition, in order, with expected cost and wall time per step, and where outputs land.
8. **Compare with the published results**: the command that rebuilds the tables and how to read differences (noise floor, CIs).
9. **Troubleshooting**: failures we hit and their fixes.

Every command in sections 3-5 must have been run while writing the doc, and it says so. Commands in 6-7 cost money and were not re-run; it says that too.

## Rules for a public repo

- No secrets, API keys, hidden test sets or their seeds.
- No inference-provider names tied to results that providers have not seen. Open-weight endpoints are configured by env vars (`OPENAI_COMPAT_BASE_URL_<LABEL>`, `OPENAI_COMPAT_API_KEY_<LABEL>`) with neutral labels (`provider-a`, `provider-b`).
- No internal infrastructure names (cloud workspaces, volumes, internal URLs) and no business notes (prospects, budgets).
- Third-party data is fetched, not vendored, unless its license clearly allows redistribution and it is small.
- Results that are not cleared for publication stay out (say so in the README).

## `results/<slug>.json`

The export schema (`meta`, `dataset`, `models`, `setup`, `grading`, `noise`, `results`, `per_type`, `failures`, `replays_and_step_checks`, `headline_findings`, `limitations`, `public_safety`, `inconsistencies`) is defined in [EXPORT_SCHEMA.md](EXPORT_SCHEMA.md).

## Harbor-native target (the second pass)

The first pass documents each benchmark as it was run. The goal is for every benchmark that has agents and tasks to run as a Harbor job, following the conventions of [zenml-bench](https://github.com/zenml-io/zenml-bench):

- **Task format.** One directory per task: `instruction.md`, `task.toml`, `environment/` (Dockerfile or compose file, built on a shared base image), `solution/solve.sh` (reference solution), and hidden `tests/` that write a reward. Graders score facts the environment recorded, never the agent's prose.
- **Four checks before a task counts.** The reference solution passes 5 of 5 times (`-a oracle`), doing nothing scores 0 (`-a nop`), every listed shortcut scores 0, and at least one different valid solution passes. Grader unit tests cover the reference, the empty answer, each trap and messy real answers.
- **Setups as config.** Agent, model, MCP servers, skills and prompts live in job config files; conditions differ only in their setup file. Custom agents use `import_path: package.module:Class` and declare their options in an options model.
- **Simulated users and tools** run as MCP servers next to the agent (the way Harbor's τ-bench adapter does), so multi-turn benchmarks fit the task format.
- **Publishing.** `dataset.toml` and `registry.json` so the whole set runs from the repo: `harbor run --repo zenml-io/agent-benchmarks@<tag> -d <dataset>@<version> -a <agent> -m <model>`.
- **Reading results.** Attempts per task and setup (5 or more for anything but large gaps), the baseline in the same batch, infrastructure errors counted apart from wrong answers, and the summary table committed with the command and the commit it ran from; raw job folders stay outside the checkout.
