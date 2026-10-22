# Rerunning the Haiku Tax

All commands run from `benchmarks/haiku-tax/`. Steps 3-5 cost nothing and were run while writing this document; each one says so. Steps 6-7 call paid model APIs and were **not** re-run.

## 1. Prerequisites

- Linux or macOS
- Python 3.11 or newer (verified with 3.13)
- [uv](https://docs.astral.sh/uv/) (verified with 0.11)

The harness, the environments and the analysis use only the Python standard library. Docker, Modal and GPUs are not needed.

Paid runs need these accounts:

- Anthropic, for the Claude models;
- OpenAI, for the GPT-6 models;
- two OpenAI-compatible inference providers, for the open-weight models;
- Jev, for the pre-action check arms only.

## 2. Credentials

Every variable is listed in `.env.example`. Never commit values.

| variable | for | needed by |
|---|---|---|
| `EVAL_ANTHROPIC_API_KEY` | Claude models (Messages API) | steps 6-7 |
| `OPENAI_API_KEY` | GPT-6 models (Responses API) | steps 6-7 |
| `OPENAI_COMPAT_BASE_URL_PROVIDER_A`, `OPENAI_COMPAT_API_KEY_PROVIDER_A` | open models with keys `...@provider-a` (`/chat/completions`) | steps 6-7 |
| `OPENAI_COMPAT_BASE_URL_PROVIDER_B`, `OPENAI_COMPAT_API_KEY_PROVIDER_B` | open models with keys `...@provider-b` | steps 6-7 |
| `OPENAI_COMPAT_AUTH_PREFIX_PROVIDER_A` / `_B` | optional; the text before the key in the `Authorization` header (default `Bearer `; some providers want another scheme) | steps 6-7 |
| `JEV_API_KEY`, optional `JEV_API_URL` | the `jev`, `jev2` and `jev3` arms | step 7 (check arms only) |
| `HT_SPENT_BEFORE` | optional; spend made elsewhere that `harness/grid.py --cap` should count | step 7 |

The base URL ends in `/v1`. The runner appends `/chat/completions`. Any OpenAI-compatible provider that serves the model IDs in `harness/models.py` works. Edit the IDs there if your provider names them differently.

## 3. Install

```bash
uv sync
```

Expected output: `Resolved 1 package` and an empty environment, since there are no dependencies. Verified on 2026-10-22.

## 4. Get the data

There is nothing to download. Every task is generated from a fixed seed in `envs/<name>/`, and all data is synthetic. Ground truth is built by construction.

Generation depends on Python's hash seed for a few tasks. `harness/run.py` re-executes itself with `PYTHONHASHSEED=0`, so always generate with that seed.

The tenth use case, support tickets, needs the private SwapBench hidden split and is not available. Section 7 covers what that changes.

## 5. Free checks

### 5.1 Validate every environment

This runs the oracle, the do-nothing agent and the adversarial checks. Verified on 2026-10-22: every script exits 0.

```bash
for e in invoice_extraction claims_triage kyc_checks contract_review sql_analyst lead_qualification it_access pr_review meeting_to_crm; do
  PYTHONHASHSEED=0 uv run python envs/$e/validate.py || echo "FAILED: $e"
done
```

Expected: each prints `oracle ... 1.0` and `do_nothing ... 0.0`, with these task counts:

| use case | tasks |
|---|---|
| invoice | 150 |
| claims | 150 |
| KYC | 150 |
| contract | 150 |
| SQL | 135 |
| lead | 150 |
| IT access | 168 |
| PR | 160 |
| meeting | 132 |

Each also prints its adversarial checks as passing. No `FAILED:` lines appear. Each environment's `README.md` shows its full validation output.

### 5.2 Rebuild the task sets and the test/kept counts

Verified on 2026-10-22. It takes about 50 s.

```bash
uv run python scripts/check_tasks.py
```

Expected output:

```
use case             generated  test  kept hidden-rule  fingerprint(seed 0)  test tasks differing under other seeds
invoice_extraction         150   100    91          38  88c0f0abcd8bb2e9  0
claims_triage              150   100    74          34  06597e1317f1df54  0
kyc_checks                 150   100    86          38  c2d1b44bb44a77ec  0
contract_review            150   100    72          38  92394100233645ab  0
sql_analyst                135   100    70          40  dc737b5c9dd0e258  0
lead_qualification         150   100    75          36  59f0f137bd5b7545  7 ['lead-025', 'lead-032', 'lead-055', 'lead-074', 'lead-092', 'lead-132'] ...
it_access                  168   100    87          41  b4f9fabfe10ecd01  0
pr_review                  160   100    74          38  7e5273a7cce56929  0
meeting_to_crm             132   100    85          37  468ad28173daa96b  0
nine use cases                   900   714
```

The fingerprints are identical to the tasks built from the original research directory. The seven seed-dependent lead tasks are all in `audit_exclusions.json`. Add the 100 support tasks to 714 and you get the 814 audited tasks of the original analysis.

### 5.3 Regenerate the audit exclusions

Verified on 2026-10-22: the output is byte-identical to the committed file.

```bash
cp audit_exclusions.json /tmp/audit_before.json
PYTHONHASHSEED=0 uv run python harness/audit.py
cmp /tmp/audit_before.json audit_exclusions.json && echo identical
```

Expected output: per-environment counts (`claims_triage 37`, `contract_review 40`, `invoice_extraction 15`, `it_access 18`, `kyc_checks 24`, `lead_qualification 45`, `meeting_to_crm 20`, `pr_review 43`, `sql_analyst 37`) and `identical`. These counts cover the whole generated set, not only the test tasks.

### 5.4 Dry-run the grid scheduler

Verified on 2026-10-22.

```bash
uv run python harness/grid.py --dry
```

Expected: the first line is `grid start: 189 jobs, cap $430, spend so far $0.00`, followed by one `start` line per job. It calls no APIs. Delete the `logs/` directory it creates afterwards.

### 5.5 Regenerate the published tables

Not possible from this repository: the result rows are withheld (see README.md). With your own rows from step 7 in `results/`, the command is:

```bash
uv run python harness/report.py          # audited set: results.csv, tables.md, charts/*.svg
uv run python harness/report.py --full   # every test task: results_full_set.csv, tables_full.md
```

Each takes several minutes because of the bootstrap. On 2026-10-22 the ported `report.py` was run privately on the original rows, relabeled to `provider-a` / `provider-b`, and reproduced every number in the original `results.csv` and `tables.md` (only the order of rows with tied sort keys and the provider-naming sentences differ).

## 6. Smoke test (paid, not re-run)

Before any full run, the original run tested 3-5 KYC tasks per model and API path. This catches tool-call parsing problems, which once broke 95% of runs on a provider.

```bash
uv run python harness/run.py kyc_checks haiku-5.5 --n 5 --out smoke/
uv run python harness/run.py kyc_checks gpt-6-luna --n 5 --out smoke/
uv run python harness/run.py kyc_checks deepseek-v4.1-flash@provider-a --n 5 --out smoke/
uv run python harness/run.py kyc_checks gpt-oss-120b@provider-b --n 5 --out smoke/
uv run python harness/summarize.py smoke/
```

- **Cost:** about $0.06 for all of them (the original smoke tests across five models).
- **Success looks like:** every row has `status` `finished`. Empty replies, `tool_parse_error` and `api_error` should be rare.
- **Known problem:** on one provider, gpt-oss-120b ended many turns with reasoning only, which shows up as `empty_reply`.

## 7. Full rerun (paid, not re-run)

The output is one JSON line per task in `results/<use_case>/<model_key>__<arm>.jsonl`. Reruns skip finished tasks; tasks that ended in an API error are run again.

### 7.1 Main grid (`none` arm)

This covers all nine harness use cases × 3 Claude models, 2 GPT-6 models and 12 open model/provider pairs, plus the `jev` (v1) arm for six models. The cap stops new jobs once recorded spend passes the given amount.

```bash
uv run python harness/grid.py --cap 430
```

Queue parallelism and wall time come from the original `logs/grid.log`. There is one queue per API: Anthropic, OpenAI, provider-a and provider-b. Jobs inside a queue run one at a time, with 8 workers (4 on provider-b). The median job of 100 tasks took:

| queue | median job |
|---|---|
| Anthropic | 3.1 min |
| OpenAI | 4.0 min |
| provider-a | 4.1 min |
| provider-b | 8.4 min |

The whole original grid, including the additions below and the support queue, ran from 19:04 to 07:18 UTC, about 12 hours. The slowest queues (provider-a and provider-b) each took about 7 hours of job time.

### 7.2 Additions run outside `grid.py`

Each of these is one `run.py` call per use case:

```bash
UCS="invoice_extraction claims_triage kyc_checks contract_review sql_analyst lead_qualification it_access pr_review meeting_to_crm"
for uc in $UCS; do uv run python harness/run.py $uc gpt-6-astra --n 100; done
for m in minimax-m3@provider-a kimi-k3@provider-b deepseek-v4.1-flash-1017@provider-b muse-spark-open@provider-b beam-1.0@provider-b; do
  for uc in $UCS; do uv run python harness/run.py $uc $m --n 100 --workers 4; done
done
# final pre-action check (v3), on the five use cases that pair in the data
for m in haiku-5.5 gpt-6-luna deepseek-v4.1-flash@provider-b glm-5.3-flash@provider-b; do
  for uc in invoice_extraction kyc_checks lead_qualification it_access pr_review; do uv run python harness/run.py $uc $m --arm jev3 --n 100; done
done
# reasoning pass-back check: development sample (tasks ranked 101-120) of eight use cases (claims triage was not
# included), with and without passing reasoning back; 160 tasks per arm
for uc in invoice_extraction kyc_checks contract_review sql_analyst lead_qualification it_access pr_review meeting_to_crm; do
  for arm in none nonerz; do uv run python harness/run.py $uc deepseek-v4.1-flash@provider-b --arm $arm --offset 100 --n 20 --out dev/rz; done
done
```

### 7.3 Cost

Recorded token cost at list prices in the original run, summed from the rows:

| block | rows | cost |
|---|---|---|
| nine harness use cases, closed models, no check | 5,400 | $130.90 |
| nine harness use cases, open models, no check | 14,064 | $230.35 |
| check arms (`jev`, `jev3`), closed models | 2,000 | $3.79 |
| check arms (`jev`, `jev3`), open models | 3,000 | $38.70 |
| support (not reproducible here) | 1,900 | $69.02 |

- The study total, including superseded runs and development, was $521.42.
- A nine-use-case rerun of the same grid should cost roughly $400.
- GPT-6 Astra and Opus 5.5 are the most expensive rows. Drop them to save most of the closed-model cost.
- Jev checks bill input tokens at the price in `harness/models.py` (`JEV_PRICE_IN`).

### 7.4 Tables

Run `harness/audit.py` (if you changed generators), then `harness/report.py` and `harness/report.py --full`.

## 8. Compare with the published results

The original numbers are withheld (README.md), so there is nothing public to compare against yet. Once they are published as `results/haiku-tax.json`, compare as follows:

- Use `harness/report.py` for the pooled and per-use-case tables, and `harness/compare.py results all <model_a> <model_b>` for any paired difference with a bootstrap interval.
- **Noise floor.** With one run per task, a per-model success rate on the 714 audited harness tasks has a 95% interval of about ±3 points. A paired difference pooled over use cases has about ±2-3 points; per use case (n = 70-100) it has about ±6-8 points. A re-run with one setting changed flipped 18 of 159 tasks.
- A difference whose interval includes zero is "not enough evidence".
- Pooled numbers over nine use cases are not comparable with the original ten-use-case pools, because support is missing.

## 9. Troubleshooting

- **Tasks differ between processes.** Some generators iterate sets of strings. Always use `PYTHONHASHSEED=0`; `run.py` sets it itself. The tasks that still vary are listed in `harness/audit.py` `UNSTABLE` and excluded.
- **Empty replies from gpt-oss-120b on one provider.** The turn ends with reasoning only (`finish_reason` `stop`). It counts as unresolved by design. Passing reasoning back (always on for gpt-oss and Beam) reduced it only slightly.
- **`account_blocked` (HTTP 402/412).** The runner stops the job. Check billing with the provider; nothing is retried.
- **GPT-6 with tools.** It needs the Responses API, which the runner uses automatically for `api.openai.com` endpoints. `/chat/completions` rejects function tools with reasoning on.
- **Rate limits (429).** The runner retries up to 6 times with backoff. Use `--workers 4` on providers that throttle.
- **Anthropic cache writes** are billed at 1.25× input. The runner counts them as input plus a quarter.

## Changes from the original run

Every change from the code that produced the original results:

1. **Provider endpoints and keys.** `harness/models.py` no longer hard-codes two providers' URLs and key variables. Endpoints come from `OPENAI_COMPAT_BASE_URL_PROVIDER_A/B`, `OPENAI_COMPAT_API_KEY_PROVIDER_A/B` and the optional `OPENAI_COMPAT_AUTH_PREFIX_PROVIDER_A/B`. Model keys were renamed from `model@<provider>` to `model@provider-a` / `model@provider-b` in `models.py`, `grid.py` and `report.py` (table headings included). Prices, model IDs and request bodies are unchanged.
2. **Tie-break in `report.py`'s price-matched table.** The original picked the best open model with `max(..., key=success)`, so ties went to the first model key in sorted order. With the new labels that order flipped for one tie (DeepSeek V4 Pro on both providers, equal success). Ties are now broken by lower cost per success, which gives the same choice as the original on the original data.
3. **`report.py` use cases.** It pools over the use cases that have result files (`UCS`). With all ten present this is the original list. Without support it pools nine.
4. **`grid.py`.**
   - The spend already made before the grid (`SPENT_BEFORE`, originally 48.66) now comes from `HT_SPENT_BEFORE`, default 0.
   - The support queue is scheduled only if `harness/support_tau2.py` exists; it is not in this repository.
   - `logs/` is created if missing.
5. **`run.py`.** The Jev endpoint can be overridden with `JEV_API_URL`; the default is unchanged.
6. **Removed.**
   - `harness/support_tau2.py` (needs the private SwapBench split and local paths).
   - The root `models.py` and `ping.py` (account checks that listed every provider).
   - All results, sanity runs, logs, charts, `results*.csv` and `tables*.md` (withheld).
   - `REPORT.md`, `PLAN.md`, `PILOT.md` and `costs.md` (internal draft, budgets and account notes).
7. **Moved.** `ENV_SPEC.md` moved to `docs/ENV_SPEC.md`. `audit_exclusions.json` stays at the benchmark root, where the code expects it.
8. **Added.** `scripts/check_tasks.py`, `pyproject.toml`, `.env.example` and `.gitignore`.

The environments under `envs/` are unchanged, apart from deleting `__pycache__`.
