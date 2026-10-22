# Rerunning SwapBench

Every command below runs from `benchmarks/swapbench/`. Sections 3-5 were run on 2026-10-22 from a fresh copy of this directory (no `.venv`, no `third_party/`) and are marked "verified on 2026-10-22". Sections 6-7 cost money and were **not re-run**; their costs come from the result rows (agent tokens) and the original notes, and their wall times from the raw run timestamps.

## 1. Prerequisites

- Linux or macOS, `git`, [uv](https://docs.astral.sh/uv/) (tested with 0.11), Python 3.12 (uv installs it; tau2-bench needs `>=3.12,<3.14`, the runs used 3.12.3).
- About 1 GB of disk for the tau2-bench checkout (its `data/` is 734 MB).
- For paid steps only: OpenAI and Anthropic API accounts; accounts on OpenAI-compatible inference providers for the hosted open-model runs; Jev (TypeSafe) access for the Jev-gate experiments; a [Modal](https://modal.com) account and the separate vLLM server code for the self-hosted Qwen runs and LoRA training; [Harbor](https://www.harborframework.com) (`harbor[modal]`) for the coding-agent arms; Chrome/Chromium for the Swap Report PDF.

## 2. Credentials

Names only; `.env.example` lists them all. None is needed for sections 3-5.

| variable | used for | steps |
|---|---|---|
| `OPENAI_API_KEY` | OpenAI agents and next-step runs; Codex in the arms | 6, 7 |
| `EVAL_ANTHROPIC_API_KEY` (or `ANTHROPIC_API_KEY`) | Claude Haiku 5.5: the simulated customer in every run, and the retail incumbent | 6, 7 |
| `OPENAI_COMPAT_BASE_URL_PROVIDER_A` ... `_D`, `OPENAI_COMPAT_API_KEY_PROVIDER_A` ... `_D` | hosted open models, one pair per provider label | 7 (providers) |
| `PROVIDERS_CONFIG` | path to `providers.json` (label → model ID per model key; template `providers.example.json`) | 7 (providers) |
| `SWAPBENCH_PROVIDER_PRICES` | JSON of provider prices for cost accounting (optional) | 7 |
| `JEV_API_KEY` (or `TYPESAFE_API_KEY`) | Jev gate / decider gate | 7 (Jev experiments) |
| `MODAL_ENVIRONMENT`, `SWAPBENCH_SERVING_DIR` | self-hosted vLLM on Modal | 7 (self-hosted) |
| `SWAPBENCH_HF_CACHE_VOLUME`, `SWAPBENCH_RFT_VOLUME`, `SWAPBENCH_RFT_APP` | LoRA training on Modal | 7 (RFT) |

## 3. Install

```bash
./scripts/fetch_tau2.sh     # tau2-bench at dd8757d4c8791dad7b3cdaf02a105a3d5f9d86bd -> third_party/tau2-bench
uv sync                     # Python 3.12 venv in .venv, tau2 installed editable from third_party/
```

Verified on 2026-10-22: the environment matches the one every published run used (`uv pip freeze` differs from it only by pytest and its two dependencies). `pyproject.toml` pins the direct dependencies and the transitive versions that differed; `uv.lock` pins the rest.

## 4. Get the data

- **tau2-bench** (MIT, Sierra Research, https://github.com/sierra-research/tau2-bench): fetched by `scripts/fetch_tau2.sh` above; the retail store comes from `third_party/tau2-bench/data/tau2/domains/retail/`.
- **Public scenario sets** (ours, committed, 500 fintech + 500 retail, seed 31415): `data/public/`. Unzip the bank before use: `gunzip -k data/public/fintech/db.json.gz`. The retail `db.json.gz` is tau2's unmodified store (SHA-256 `413a6516...`).
- **Result rows** (ours, committed): `results/runs/<domain>/<run>.jsonl`, one row per conversation (no text), and `<run>.nextstep.jsonl` (one row per replayed step).
- **Not public:** the hidden v1 sets behind the published numbers and the v2 leaderboard sets (see README, Limitations), transcripts, raw run folders.

Regenerate the public sets yourself (verified on 2026-10-22: byte-identical to `data/public/`, 15 s and 35 s):

```bash
.venv/bin/python -m swapbench.fintech.gen out/fin --n 500 --seed 31415 --splits public:500 --prefix pf
.venv/bin/python -m swapbench.gen_retail third_party/tau2-bench out/ret --n 500 --seed 31415 --splits public:500 --prefix pg
```

## 5. Free checks

All verified on 2026-10-22, on one CPU core.

```bash
# offline tests: both public sets regenerate byte for byte, all 500 fintech gold action lists execute,
# the fintech domain registers with tau2, statistics and pricing sanity (about 3.5 min)
.venv/bin/python -m pytest -q tests
# expected: 6 passed

# headline table, verdict tally and threshold sweep from results/runs/ (about 2.5 min)
.venv/bin/python scripts/headline.py > out/headline.md
diff <(tail -n +2 experiments/headline.md) <(tail -n +2 out/headline.md) && echo SAME
# expected: SAME

# the four charts of the write-up (about 35 s)
.venv/bin/python scripts/charts.py --out out/img
for f in docs/img/*.svg; do cmp "$f" "out/img/$(basename "$f")"; done
# expected: no output (identical)

# rebuild results/swapbench.json from the rows (about 6 min)
.venv/bin/python scripts/export/sb_compute.py out/sb_out.json
.venv/bin/python scripts/export/build_export.py out/sb_out.json out/swapbench.json scripts/export/sb_part2.py
.venv/bin/python -c "import json; print(json.load(open('results/swapbench.json')) == json.load(open('out/swapbench.json')))"
# expected: "ok 11946 89.2142", "written", True

# the tau2 CLI with the fintech domain registered
TAU2X_PYTHON=.venv/bin/python scripts/tau2x run --help | grep fintech
```

## 6. Smoke test (paid, not re-run)

GPT-5 mini as the agent on the first 20 public fintech scenarios, one trial, Claude Haiku 5.5 as the customer:

```bash
gunzip -k data/public/fintech/db.json.gz
DOMAIN=fintech SWAPBENCH_FINTECH_DIR=$PWD/data/public/fintech NUM_TASKS=20 \
  scripts/gt_one.sh $PWD/third_party/tau2-bench $PWD/.venv $PWD/out/smoke gpt-5-mini-2025-08-07 "public:1"
```

- Cost: about $0.30 (GPT-5 mini averaged 1.30¢ per bank conversation in the hidden runs, the simulator about 0.1¢).
- Wall time: a few minutes (480 hidden conversations took 0.65 h at 12 concurrent).
- Success looks like: `out/smoke/gpt-5-mini-2025-08-07/public/results.json` with 20 simulations, an "Average Reward" in `public.log` around 0.9 (GPT-5 mini resolved 94% of hidden bank conversations), and `public.done`. Turn it into rows with `scripts/export_results.py` (manifest format in its docstring).

## 7. Full rerun (paid, not re-run)

**You need the hidden v1 sets** (request them; see README Provenance) to reproduce the published numbers. With the public sets you get a comparable but different benchmark: replace the split names below with `public` (500 scenarios, one split), or re-split the public set yourself.

Layout of every candidate and incumbent: visible × 1, hidden × 2, pool × 1 (`"train:1 test:2 pool:1"`), 740 conversations. Agent costs below are the sums of `cost_usd` over the committed rows; the simulator adds about $0.75 per 740 conversations; wall times are from the raw runs at 12 concurrent conversations.

| step | command | agent cost | wall time |
|---|---|---|---|
| fintech incumbent GPT-5 | `DOMAIN=fintech SWAPBENCH_FINTECH_DIR=<v1 fintech> scripts/gt_one.sh <tau2> .venv <out> gpt-5-2025-08-07 "train:1 test:2 pool:1"` | $53.61 | 1.4 h |
| fintech API candidates | same with `gpt-5-mini-2025-08-07`, `openai/responses/gpt-6-luna`, `gpt-5.4-nano` | $9.50, $0.73, $3.28 | 0.6-1.0 h each |
| retail incumbent Haiku 5.5 (+ re-run) | `TAU2_DATA_DIR=<v1 retail> scripts/gt_one.sh <tau2> .venv <out> anthropic/claude-haiku-5-5 "train:1 test:2 pool:1"` (re-run: `test:1 ...`) | $13.23 (+ $8.86) | about 0.6 h |
| self-hosted Qwen configs (both domains) | `SWAPBENCH_SERVING_DIR=... python scripts/open_model.py <qwen27b \| qwen27b-fp8 \| moe-a3b \| qwen27b-hermes \| qwen27b-nothink \| qwen27b-rft> --domain <fintech\|retail> --tau2 <tau2> --tau2-env .venv --out <out> --splits "train:1 test:2 pool:1" [--nextstep <incumbent train results.json>]` | GPU only: about 0.5-1¢ per conversation on one H100 at $3.95/h (e.g. Qwen3.8-27B BF16 0.79¢ on fintech), plus about 4 min of startup per config | 0.5-2.5 h per config |
| fix loop (fintech) | as above with `SWAPBENCH_GUARDS=1`, then also `SWAPBENCH_POLICY_ADDENDUM=swapbench/fintech/policy_addendum.md` | GPU only | about 1 h each |
| next-step replay | `python -m swapbench.nextstep <incumbent visible results.json> --model <candidate> --out <out> --domain <domain>` | small (one call per recorded step, 475-540 steps) | minutes |
| hosted providers | `DOMAIN=<fintech\|retail> PROVIDERS_CONFIG=providers.json scripts/provider_runs.sh <tau2> .venv <data> <out> deepseek-v4.1-flash gpt-oss-120b qwen3.8-2.4t qwen3.8-27b` | depends on your providers' prices; the original 22 runs (withheld) cost $323.71 in agent tokens in all | 0.3-4.5 h per hidden run; rate limits dominate |
| coding-agent arms | `python scripts/build_harbor_task.py retail-refunds --visible <incumbent train results.json>`, then `scripts/run_arm.sh retail-refunds-arm1 <codex\|claude-code> <model> <attempts>`; grade with `python -m swapbench.grade <harbor_job_dir> --task retail-refunds --gt <ground-truth dir> --tau2 <tau2> --tau2-env .venv` | not in the rows (originally about $5 of candidate inference per run plus the coding agent) | about 2 h per attempt (sandbox cap) |

Then export the raw runs to rows (`scripts/export_results.py <manifest>`; name provider runs `<model>@<label>` and keep them out of `results/runs/manifest.json`, or `headline.py` will tabulate them; `scripts/providers.py` compares them) and continue with section 8.

## 8. Compare with the published results

```bash
.venv/bin/python scripts/headline.py > out/headline.md        # tables, verdicts, threshold sweep
.venv/bin/python scripts/providers.py > out/providers.md       # only if you ran your own providers
.venv/bin/python scripts/export/sb_compute.py out/sb_out.json && \
  .venv/bin/python scripts/export/build_export.py out/sb_out.json out/swapbench.json scripts/export/sb_part2.py
```

How to read differences:

- The only measured noise floor is the retail incumbent against itself: −2.08 points [−5.42, +1.25] on 240 scenarios; two GPT-5 runs gave the same outcome on 91.7% of conversations, two Haiku runs on 92.5%. Expect per-run success to move by 1-3 points.
- A rerun matches when each candidate's truth label holds and its paired Δ falls inside the published 95% interval. Labels near the margin (GPT-6 Luna, Qwen MoE, thinking-off Qwen) can flip; strong regressions (GPT-5.4 nano, hermes parser) should not.
- Verdict tallies (false safes out of 8) have very wide uncertainty; compare verdict by verdict, not the tally.
- Model snapshots change (GPT-5's `gpt-5-2025-08-07` is scheduled for removal on 2026-12-11), and hosted providers change their serving; differences there are a finding, not a failure to reproduce.

## 9. Troubleshooting

- **tau2 grading skips some tools:** tau2 replays only tools with `mutates_state=True`; `transfer_to_human_agents` is skipped. Any offline re-grader must do the same (`scripts/mock_fidelity.py`).
- **litellm's provider-specific adapters can mangle tool calls** (in one case they came back as text); `scripts/provider_runs.sh` uses the OpenAI-compatible route for every provider. Before blaming a model for a gap on a hosted endpoint, check a raw request (e.g. for reasoning text leaking into `content`).
- **Rate limits and credit balance** drop whole splits: lower `CONC` (3 with retries worked), and treat `infra_error` rows as not run, not as failures.
- **vLLM tool parser:** serving Qwen3.8 with the generic `hermes` parser silently breaks every tool call (1 of 240 resolved, no errors raised). Use `qwen3_coder` and the `qwen3` reasoning parser.
- **Modal:** `modal app stop` returns before the container is gone, and a crash-looping server keeps billing; check `modal app list` after any failure. Killing Harbor locally does not stop its Modal sandboxes.
- **Long jobs** launched from a session that may be interrupted: use `nohup setsid ...`.
- **`gt_one.sh` paths:** it `cd`s into the tau2 directory, so pass absolute paths for the output and data directories.

## Changes from the original run

Behaviour of the benchmark code is unchanged except where noted.

- **Layout:** result rows moved from `results/<domain>/` to `results/runs/<domain>/` (path constants in `headline.py`, `providers.py`, `swap_report.py`, `export_results.py`); `SPEC.md`, `PRIOR_ART.md`, `RISK_EXPERIMENT.md`, `RESULTS.md` moved to `docs/`; the expert-deciders write-ups moved to `../expert-deciders/docs/`. The Python package stays at `swapbench/` (not `src/`) so every script's relative paths keep working.
- **Manifest:** `results/runs/manifest.json` is the Oct 14 version (main runs) that reproduces `headline.md` (see README, inconsistency 1).
- **Per-provider results withheld** (owner decision, pending provider review): the 22 hosted-provider row files, their manifest, the `*_hidden_hosted_providers` blocks, hosted-model entries and the decomposition/Jev-gate note in `results/swapbench.json` (rebuilt with the builder), `experiments/providers.md`, `providers_setup.md`, `jev_gate.md`, `decomposition.md`, `outcome_decider.md` and the per-provider notes. `scripts/providers.py` no longer prints our runs' account-limit notes. `swapbench/pricing.py` no longer holds provider names or prices; they load from `SWAPBENCH_PROVIDER_PRICES`. `scripts/provider_runs.sh` was rewritten to read neutral labels from a config and env vars and to call every provider through litellm's OpenAI-compatible route (the original used litellm's provider-specific adapters for most endpoints), so a rerun can behave differently from the original. `gt_one.sh` no longer maps provider key names. `ed_build_steps.py` and `ed_costs.py` use neutral run-directory names (provider-a ... provider-d, opaque labels).
- **Infrastructure names:** `open_model.py` reads the serving code location from `SWAPBENCH_SERVING_DIR` and the Modal environment from `MODAL_ENVIRONMENT` (it used a fixed environment and `../serve_vllm.py`); `run_arm.sh` uses `JOBS_DIR` and your Modal config; `rft/train_lora.py` takes volume and app names from env vars (same defaults); `swap_report.py` takes `CHROME` from the environment.
- **Docs edited for publication:** budget lines, the private-storage location of the hidden sets, outreach notes were removed; `experiments/methods_v2_plan.md` (an unrun plan with budget figures) and the 21 sample-report conversation pages were left out.
- **Added:** `pyproject.toml`/`uv.lock` (pinned to the original environment), `scripts/fetch_tau2.sh`, `tests/test_offline.py`, `providers.example.json`, `.env.example`, and `scripts/export/` (the original export builders, with relative paths and a `publish.py` step that sets the public-safety and licence fields; the builder leaves hosted-provider runs out).
