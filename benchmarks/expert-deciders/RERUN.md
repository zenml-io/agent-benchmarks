# Rerunning the expert-deciders benchmark

This benchmark's runtime code lives in [`../swapbench`](../swapbench); set that up first (its `RERUN.md`, sections 1-3). Commands below run from `benchmarks/expert-deciders/` unless they say otherwise. Sections 3-5 were run on 2026-10-22 from a fresh copy of both directories and are marked "verified on 2026-10-22". Sections 6-7 cost money and were **not re-run**.

## 1. Prerequisites

- As for SwapBench: Linux or macOS, git, uv, Python 3.12, about 1 GB of disk for tau2-bench.
- For paid steps: OpenAI and Anthropic API accounts, Jev (TypeSafe) API access, an account on an OpenAI-compatible inference provider serving Qwen3.8-27B and DeepSeek-V4.1-Flash, and the private bank hidden set with hidden-rule gold (request it; see README Provenance).

## 2. Credentials

Names only (`.env.example`); none for sections 3-5.

| variable | used for | steps |
|---|---|---|
| `OPENAI_API_KEY` | GPT-5 reference agent, GPT-5 mini expert, GPT-6.1 Sol rubric and judge, `text-embedding-3-small` | 6, 7 |
| `EVAL_ANTHROPIC_API_KEY` | Claude Haiku 5.5 expert and simulated customer | 6, 7 |
| `JEV_API_KEY` | Jev, arms B, C, G, H | 6, 7 |
| `OPENAI_COMPAT_BASE_URL_PROVIDER_A`, `OPENAI_COMPAT_API_KEY_PROVIDER_A` | agents A and B on your OpenAI-compatible provider | 6, 7 |
| `SWAPBENCH_PROVIDER_PRICES` | provider prices for the cost tallies (`{"<litellm model string>": [in, cached, out]}`; the original provider charged $0.45/$3.00 per 1M for Qwen3.8-27B and $0.30/$1.20 for DeepSeek-V4.1-Flash, cached input at the input price) | 7 (costs) |

## 3. Install

```bash
(cd ../swapbench && ./scripts/fetch_tau2.sh && uv sync)
uv sync      # this directory's venv: same pins, tau2 from ../swapbench/third_party/tau2-bench
```

Verified on 2026-10-22.

## 4. Get the data

- Committed (ours): `results/runs/live_conversations.jsonl` (5,280 conversations: 11 runs × 480; ids, reward, rule violations, handoffs, tokens), `live_decisions.jsonl` (one row per checked action: tool, p, blocked, hidden rules broken), `live_runs.json` (models, exclusions, agent and check cost per run), `results/runs/offline/` (decision-step ids and truth, expert yes/no labels, every arm's scores; no text), `data/rubric.json` (the interview rubric).
- Private (request access): the bank hidden set with hidden-rule gold, raw tau2 results, decision-step texts and expert explanations, the judge's examples and the two trained models.

## 5. Free checks

All verified on 2026-10-22.

```bash
# live tables from the rows (about 50 s)
.venv/bin/python scripts/ed_compute_rows.py out/ed_out.json
# prints one line per run; expected e.g. "A_C n 480 resolved 263 viol/conv 0.004 conv w/ viol 2 viol delta [-0.388, -0.452, -0.325]"
.venv/bin/python scripts/build_export.py out/ed_out.json out/expert-deciders.json
.venv/bin/python -c "import json; print(json.load(open('results/expert-deciders.json')) == json.load(open('out/expert-deciders.json')))"
# expected: "written 149.1911" (sum of agent costs over the 11 runs, USD), True

# offline table from the stripped offline rows (about 1 min)
.venv/bin/python ../swapbench/scripts/ed_eval.py results/runs/offline/steps.jsonl results/runs/offline/labels.jsonl \
    results/runs/offline/scores 2>/dev/null > out/offline.md
diff docs/expert_deciders_offline.md out/offline.md && echo SAME
# expected: SAME
```

## 6. Smoke test (paid, not re-run)

Arm C on agent A for 20 hidden scenarios, one trial (needs the private hidden set with hidden-rule gold; with the public bank set the hidden rules are not applied to the gold, so resolution numbers would not be comparable):

```bash
cd ../swapbench
SWAPBENCH_HYBRID=1 AGENT=decider_gate SWAPBENCH_ED_ARM=C SWAPBENCH_ED_DIR=$PWD/../expert-deciders/data \
SWAPBENCH_JEV_LOG=$PWD/out/smoke_C.log SWAPBENCH_CALL_LOG=$PWD/out/smoke_C.calls \
DOMAIN=fintech SWAPBENCH_FINTECH_DIR=<bank hidden set with hidden-rule gold> CONC=6 NUM_TASKS=20 \
OPENAI_API_BASE=$OPENAI_COMPAT_BASE_URL_PROVIDER_A OPENAI_API_KEY=$OPENAI_COMPAT_API_KEY_PROVIDER_A \
  scripts/gt_one.sh $PWD/third_party/tau2-bench $PWD/.venv $PWD/out/smoke_C openai/<Qwen3.8-27B model id on the provider> "test:1"
```

Cost about $0.60 (2.6¢ per conversation for agent + check, plus the simulator); a few minutes. Success: 20 simulations in `results.json`, a decision log with one line per handoff/refund/freeze proposal, and roughly half the conversations resolved. Note: in this command `OPENAI_API_KEY` is the provider's key for the agent; Jev reads `JEV_API_KEY`.

## 7. Full rerun (paid, not re-run)

In order (from `../swapbench`; costs from `docs/expert_deciders_costs.md`, wall times from the raw run timestamps):

| step | command | cost | wall time |
|---|---|---|---|
| 1. decision steps from recorded runs | `python scripts/ed_build_steps.py <raw-root> <bank hidden dir> <steps.jsonl>` (needs the recorded agent runs, private) | free | minutes |
| 2. expert interviews | `python scripts/ed_experts.py <steps.jsonl> <labels.jsonl> --which test` and `--which train --agent A` | $4.26 | under 1 h |
| 3. offline arms | `python scripts/ed_arms.py <steps.jsonl> <labels.jsonl> <scores-dir> --arms B,C,D,E,F,G` (C also writes `rubric.json`) | $31.75 (judge D $30.87) | about 1 h |
| 4. offline table | `python scripts/ed_eval.py <steps> <labels> <scores-dir>` | free | 1 min |
| 5. live-check files | `python scripts/ed_online_prep.py <steps> <labels> <scores-dir> --n 200` (judge examples, E-200 and T-400 models) | embeddings only | minutes |
| 6. live runs, 11 × 480 conversations | for each agent (A: Qwen3.8-27B, B: DeepSeek-V4.1-Flash, both via `openai/<model id>` on your provider) and arm in none, C, D, H, G: the smoke command with `NUM_TASKS` unset and `"test:2"` (arm none: plain `gt_one.sh` without `AGENT`); GPT-5 reference: `gt_one.sh ... gpt-5-2025-08-07 "test:2"`. Original concurrency: 6 (4 with `AGENT_ARGS='{"num_retries":8}'` for agent B) | $198.63 incl. set-aside runs; agent + check per run: A $11.2-12.4 (D $29.0), B $6.6-12.1 (D $32.5), GPT-5 $36.5; simulator about $0.5 per run | A 0.5-0.7 h, B checked 2.2-2.6 h, B alone 0.9 h, GPT-5 1.7 h |
| 7. live table and spend | `python scripts/ed_online_eval.py <edon-dir> <bank hidden dir>`, `python scripts/ed_costs.py <ed-dir> <edon-dir>` | free | minutes |
| 8. public rows | `python ../expert-deciders/scripts/extract_rows.py <edon-dir> <bank hidden dir> ../expert-deciders/results/runs` and `python ../expert-deciders/scripts/strip_offline.py <ed-dir> ../expert-deciders/results/runs/offline <private rename.json>` | free | 1 min |

## 8. Compare with the published results

Run section 5 on your new rows. There are no repeats in the original, so the noise floor is unknown; as a guide, SwapBench's incumbent re-run moved by 2 points and the paired 95% intervals here are ±4-7 points. A rerun matches when: every check still cuts violations to about 1% or less; G beats Qwen alone; C on DeepSeek stays clearly above DeepSeek alone; D's check cost stays two orders of magnitude above Jev's. Expert labels, the rubric (written by GPT-6.1 Sol) and Jev can all change with model versions; a new rubric is the most likely source of differences in arms C, D and H.

## 9. Troubleshooting

- **DeepSeek returns empty messages after a block** (5-12 per checked run). tau2 records them as errors without reward info; `ed_online_eval.py` and `extract_rows.py` count them as unresolved, not as infrastructure errors.
- **Rate limits / account limits on a provider** lost 85-95% of the first agent-B runs; those runs were set aside and re-run elsewhere. Check `live_runs.json`-style exclusion counts before reading a table.
- **`decider_gate` imports `scripts.ed_arms`**: run from `../swapbench` (or put it on `PYTHONPATH`), as `scripts/tau2x` does.
- **tau2 grading skips `transfer_to_human_agents`**-style tools without `mutates_state=True`; hidden-rule violations are counted separately from tau2's reward, by `swapbench/hidden_rules.py`.

## Changes from the original run

- Write-ups moved from `swapbench/experiments/expert_deciders*.md` to `docs/`; provider names removed (the agents' provider is not named; the set-aside first runs are "another provider"); the budget line and the "for the product story" section were removed from the write-ups; the account-suspension detail is described as account limits.
- `swapbench/scripts/ed_build_steps.py` and `ed_costs.py` use neutral raw-directory names (`prov_hidden/provider-c_Qwen_Qwen3.8-27B`, `provider-b_partial`, ...; the labels are opaque run-directory names, not provider names); `ed_costs.py` no longer prints the budget line. Decision-step ids in the public rows use the same names. `live_runs.json` records agent models without a provider.
- New: `scripts/extract_rows.py` and `scripts/strip_offline.py` (raw private data → public rows), `scripts/ed_compute_rows.py` (rows → numbers, replacing the original export's `ed_compute.py`, which read raw runs, and computing the rule-violation figures that export copied from the write-up), `scripts/build_export.py` and `publish.py` (the original export builder with relative paths and the provider label), `pyproject.toml`, `.env.example`, `data/rubric.json`.
