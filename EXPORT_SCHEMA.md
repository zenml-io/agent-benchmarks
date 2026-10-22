# Export spec (shared by every benchmark file)

Goal: a website team builds a public "Benchmarks" page from these files. Read existing results, logs and code only. Run nothing that calls a model or spends money.

Write `benchmarks-export/<slug>.json` with these top-level keys (use `null` plus a sibling `"<key>_note"` explaining why, when something was not measured or doesn't apply; never estimate):

- `meta`: name; question (one line); domain; status ("complete" / "in progress" / "stopped"); run_dates; who_ran ("Hamza Tahir (ZenML), with Claude Code agents"); kitaru_version (null if Kitaru wasn't used); harness_git_commit (`git log -1 --format=%H -- <dir>` in /home/user/agentperf); code_location (repo-relative path in htahir1/agentperf); total_spend_usd (from the costs file, exact).
- `dataset`: source, url, license, total_cases, kept_cases, dropped_reason, split (train/tuning/held-out or null), types: [{type, count}].
- `models`: [{id (exact ID used in the harness), display_name, vendor, weights ("open"/"closed"), inference_provider_type ("vendor API" or "commercial provider"), price_per_mtok_input_usd, price_per_mtok_output_usd, price_date}]. Prices come from the harness's price table; price_date = the date of the run if no other date is recorded (say so).
- `setup`: conditions [{name, description}], prompt_rewriting (method, leakage check) or null, tools, user_simulator, limits.
- `grading`: judges, tie_break, human_agreement [{judge, rate, n}] or null, self_grading_check, metrics [{name, definition}] including the exact cost-per-correct formula.
- `noise`: method, size (with CI), ci_method, resamples, tie_threshold.
- `results`: {condition_name: [{model, n, correct, accuracy, ci95 (if available), cost_per_correct_cents, mean_tokens_per_case, mean_calls_per_case, failures: {category: count}}]}. Keep failed/errored runs in n and say how they were scored (`results_note`).
- `per_type`: {condition_name: {model: {type: {n, correct, accuracy}}}}.
- `failures`: [{category, definition, counts: {model: n}, example (one short anonymized sentence or quote; no customer data, no company names)}].
- `replays_and_step_checks`: every Kitaru replay / step-check result with n, paired differences and CIs (empty list if none).
- `headline_findings`: 3-6 one-sentence findings, each with `numbers` pointing to exact values that appear in the tables above (e.g. "results.first_prompt[model=haiku-5.5].accuracy").
- `limitations`: full list.
- `public_safety`: [{item, why, where_in_file}]: anything that must NOT be published (inference provider names, internal paths, keys, unpublished drafts, provider results not yet shared with the provider). Do not include secrets anywhere. Model IDs with an `@provider` suffix: put the bare ID in `id` and the suffix only in a `provider_private` field that is flagged here.

Rules: exact numbers (no "~"); every number has its n; accuracy as a fraction with 4 decimals plus the raw counts; costs in cents with 4 decimals. Compute from the per-row result files where they exist, not from prose. Validate the JSON with `python3 -m json.tool`. Don't commit or push; the coordinator does.
