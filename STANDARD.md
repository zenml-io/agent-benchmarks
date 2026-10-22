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
