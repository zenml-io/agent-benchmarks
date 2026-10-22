# Rerunning the model-swap calibration

All commands run from `benchmarks/model-swap-on-recorded-traffic/`. Steps 3-5 are free and were run while writing this document. Steps 6-7 call paid model APIs and were **not** re-run.

This benchmark reuses the Haiku Tax harness in [`../haiku-tax`](../haiku-tax) for three things:

- the environments;
- the agent runner that records transcripts;
- the price table and endpoint configuration.

It also uses Haiku Tax's full runs as ground truth. `src/` finds that directory through `HAIKU_TAX_DIR` (default `../haiku-tax`) and its result rows through `HAIKU_TAX_RESULTS` (default `../haiku-tax/results`).

## 1. Prerequisites

- Linux or macOS
- Python 3.11 or newer (verified with 3.13)
- [uv](https://docs.astral.sh/uv/)
- git, because Kitaru is installed from GitHub

Docker, GPUs and a Kitaru server are not needed. The analyzer runs offline on transcripts held in memory.

Paid steps need the same accounts as the Haiku Tax runs (Anthropic, OpenAI, one OpenAI-compatible provider for the open models) plus Jev, which is the judge.

## 2. Credentials

| variable | for | needed by |
|---|---|---|
| `EVAL_ANTHROPIC_API_KEY` | Claude models, including recording Sonnet 5.5 | steps 6-7 |
| `OPENAI_API_KEY` | GPT-6 candidates | steps 6-7 |
| `OPENAI_COMPAT_BASE_URL_PROVIDER_A`, `OPENAI_COMPAT_API_KEY_PROVIDER_A`, optional `OPENAI_COMPAT_AUTH_PREFIX_PROVIDER_A` | open-weight candidates (`...@provider-a`) | steps 6-7 |
| `JEV_API_KEY` | the analyzer's equivalence judge | step 7 |
| `HAIKU_TAX_DIR`, `HAIKU_TAX_RESULTS` | optional; where the Haiku Tax harness and its full-run rows are | `src/` |

They are listed in `.env.example`. Never commit values.

## 3. Install

```bash
uv sync
```

This installs Kitaru and the `kitaru-model-swap` plugin from `zenml-io/kitaru` at commit `0217140c9bd6fc1b0569abefbaea30be20a6fde4`, the head of `feature/model-swap-analyzer` on 2026-10-22. The plugin is not released on PyPI. Verified on 2026-10-22.

To reproduce batches A and B exactly, use `04d52c6fdc5ba8afc3b2f5333969ca0489d6b2c9`, the analyzer they ran on. Change both `rev` values in `pyproject.toml`. Section 8 explains what differs.

## 4. Get the data

There is nothing to download for the three public use cases. Their tasks come from the Haiku Tax generators (`../haiku-tax/envs`). The recorded traffic is made in step 7.1. Bank support uses a private hidden split, is not available and cannot be rerun.

Committed here:

- `results/runs/step_calls.jsonl`: 15,129 rows, 6.1 MB. There is one row per candidate reply to a sampled recorded call, across all four use cases and every batch (A, B, G, the 30-call Responses check R, and the smoke batches). Each row holds the use case, batch, task id, sampled-step index, candidate, attempt, agreement label, judge ruling and probability, the recorded and replied tool names, the failure category, cost and latency. Texts and arguments are left out, and support task ids are replaced with `support-NNN`.
- `results/model-swap-on-recorded-traffic.json`: the export, with full-run fields withheld.

## 5. Free checks

### 5.1 Regenerate every published step-check number from the rows

Verified on 2026-10-22. It needs only the standard library.

```bash
python3 scripts/step_check_tables.py
```

Expected output: the first line is `step-check entries: 52, fields compared: 468, mismatches: 0`. Then comes one table per use case with tool choice, exact and judged agreement, failure rate, the comparable verdict, the rank and the picks; the values match the README tables. The last line is `total values compared: 556, mismatches: 0`, and the exit code is 0.

### 5.2 Check that the calibration scripts load

Verified on 2026-10-22. This needs `uv sync` and `../haiku-tax`.

```bash
.venv/bin/python src/swap_calib.py --help
.venv/bin/python src/analyze.py && rm -rf out
```

Expected: the usage text, then `mean within-use-case spearman: {}`. With no `out/` analyzer outputs, there is nothing to merge.

When `out/` holds analyzer outputs but `HAIKU_TAX_RESULTS` has no full-run rows, `analyze.py` prints the step-level table with empty `full` columns. This was verified on 2026-10-22 against the original outputs.

### 5.3 What cannot be checked here

The aggregate calibration (35 of 44 verdicts matched, the top-three counts, the Spearman correlations) needs the withheld Haiku Tax full runs. It was regenerated privately on 2026-10-22 (README.md, Trust status).

## 6. Smoke test (paid, not re-run)

Record two KYC tasks, then run the analyzer on 3 calls for both batches. Each command runs from the directory shown in its comment.

```bash
# from ../haiku-tax: record Sonnet 5.5 with transcripts
uv run python harness/run.py kyc_checks sonnet-5.5 --n 2 --out ../model-swap-on-recorded-traffic/recordings \
    --record ../model-swap-on-recorded-traffic/traces
# from this directory
.venv/bin/python src/swap_calib.py kyc_checks --smoke --tag A --cap 2 \
    --candidates sonnet-5.5,opus-5.5,haiku-5.5,gpt-6-luna,deepseek-v4.1-flash@provider-a
```

- **Cost:** the original smoke batches cost $0.1657, plus a few cents to record.
- **Success looks like:** `out/kyc_checks_smokeA/report.json` exists, the printout lists each candidate with a tool-choice rate, and failure rates are 0.

## 7. Full rerun (paid, not re-run)

### 7.1 Record the incumbent

This records Sonnet 5.5 on 100 tasks per use case, with transcripts.

- **Cost:** $6.55 for all three.
- **Wall time:** about 1-2 minutes each at 8 workers.

```bash
cd ../haiku-tax
for uc in invoice_extraction claims_triage kyc_checks; do
  uv run python harness/run.py $uc sonnet-5.5 --n 100 --out ../model-swap-on-recorded-traffic/recordings \
      --record ../model-swap-on-recorded-traffic/traces
done
cd ../model-swap-on-recorded-traffic
```

A new recording differs from the original one, which is not public, so step-check numbers will move within their noise.

### 7.2 Analyzer batches A and B

Batch A is Sonnet, Opus, Haiku, Luna, Sol, DeepSeek V4.1 Flash, DeepSeek V4 Pro and GLM 5.3. Batch B is Sonnet, GLM 5.3 Flash, gpt-oss-120b, Qwen3.8-27B and MiniMax-M3. Each run samples 250 calls.

```bash
src/run_all.sh invoice_extraction claims_triage kyc_checks
```

- **Cost per use case:** about $11.5-12.1 for batch A and $4.1-4.3 for batch B, from the analyzer's own `spent_usd`. That is about $49 for three use cases.
- **Spend caps:** $25 per batch.
- **Wall time:** about 1-3 minutes per run at concurrency 32.
- **Outputs:** `out/<use_case>{A,B}/{report.json,insights.json,calls.jsonl}` and `logs/`.

### 7.3 GPT-6 through the Responses API (batch G)

```bash
src/run_gpt6.sh invoice_extraction claims_triage kyc_checks
```

- **Cost:** about $0.40-0.48 per use case.
- **Wall time:** under a minute each.

### 7.4 Merge and calibrate

```bash
.venv/bin/python src/analyze.py      # writes out/calibration.json
```

You need full-run ground truth in `HAIKU_TAX_RESULTS`: the Haiku Tax `none`-arm rows for the 12 models on the same use cases. Produce your own with [`../haiku-tax/RERUN.md`](../haiku-tax/RERUN.md), section 7. For these 12 models on four use cases the original full runs cost $100.65 at list prices (agent tokens; three use cases cost less).

To rebuild the rows file for comparison, extract the same fields from `out/*/calls.jsonl`.

## 8. Compare with the published results

- **Step checks.** Compare your tool-choice, exact and judged agreement rates per candidate with the results file, using each published Wilson 95% interval. For n = 250, that interval is about ±6 points at 0.5 and about ±2-4 points near 0.95.
  - Sonnet's own replay sets the noise floor. Its tool-choice rate against itself was 0.92-1.0, and its exact agreement 0.48-0.71 depending on the use case.
  - A candidate's verdict can flip when it sits within a few points of the "best minus 0.10" line.
- **Picks.** At `0217140` the picks differ from the published ones by design:
  - "Closest to today" excludes Sonnet's own replay.
  - Picks are measured against that replay.
  - A "worth a full replay" shortlist is added.

  Compare verdicts and ranks, not pick names, unless you pin `04d52c6`.
- **Calibration.** Recompute matches between the "comparable" verdict and your own full-run "holds" (success at most 5 points below Sonnet's, point estimate). Compare the match count with 35 of 44 over four use cases; you have three without bank support.

## 9. Troubleshooting

- **GPT-6 through `/chat/completions` fails with tools and reasoning.** Use `--responses` (batch G). Batch A's GPT-6 results are superseded for this reason.
- **The analyzer takes at most 8 candidates per run.** That is why there are two batches with Sonnet in both.
- **The analyzer's time budget is capped at 840 s** inside Kitaru tasks. `swap_calib.py` raises it to 3600 s for this offline run.
- **Rate limits (HTTP 429).** They removed up to 17% of one open model's calls. Failed calls are left out of every agreement rate; check `failure_rate`.
- **Audited tasks.** Sessions from tasks in `../haiku-tax/audit_exclusions.json` are skipped, to match the audited full runs.

## Changes from the original run

1. **Paths.**
   - `src/swap_calib.py` and `src/analyze.py` read the Haiku Tax harness from `HAIKU_TAX_DIR` (default `../haiku-tax`) and full-run rows from `HAIKU_TAX_RESULTS` (default `../haiku-tax/results`).
   - Transcripts come from `traces/`, analyzer outputs go to `out/`, and `analyze.py` writes `out/calibration.json` instead of `calib/calibration.json`.
   - `run_all.sh` and `run_gpt6.sh` use `.venv` (or `KVENV`) and write logs to `logs/`.
2. **Provider labels.** Open-model candidate keys were renamed from `model@<provider>` to `model@provider-a`; endpoints come from the environment (see `../haiku-tax/harness/models.py`).
3. **Missing ground truth.** `analyze.py` runs without full-run rows. Ground-truth fields become `null`, and correlations, confusion and finalists are empty. With the rows present, its output is unchanged, which was verified privately: the output was identical at Kitaru `04d52c6`.
4. **Removed.**
   - The bank support converter (`tau2_to_records.py`) and tool export (`support_env.json`), which need the private split.
   - The blog draft, page builder, charts and HTML page (internal).
   - The Kitaru patch file, which is now commit `e96fa2a` on the Kitaru branch.
   - Raw `out/`, `traces/` and `results/`, replaced by the compact `results/runs/step_calls.jsonl`.
5. **Added.**
   - `scripts/step_check_tables.py`, `pyproject.toml` (Kitaru pinned to `0217140`), `.env.example` and `.gitignore`.
   - The public export `results/model-swap-on-recorded-traffic.json`. It is derived from the internal export, with per-candidate full-run fields removed and provider names neutralized.
