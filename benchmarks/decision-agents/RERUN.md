# Rerunning the decision-agent benchmark

All commands run from `benchmarks/decision-agents/` unless they start with `cd harness`. Steps 3-5 were run while writing this file (on 2026-10-22, Linux, Python 3.13, uv 0.11) and say so; steps 6-7 cost GPU time and were **not re-run**.

## 1. Prerequisites

- Linux or macOS, Python 3.11+ and [uv](https://docs.astral.sh/uv/). The harness and every script use only the standard library.
- `curl` (the California CSV must be downloaded with curl, see Troubleshooting).
- For the paid steps only: two GPU servers running vLLM 0.31.0, one NVIDIA H100 80 GB each (one for the dense model, one for the MoE), reachable over HTTP from the machine running the harness. The original run used one cloud H100 per model; `../self-hosted-agents-harness/serve_vllm.py` is the deployment script it used (Modal), configured by environment variables there.
- About 400 MB of disk for the fetched data.

## 2. Credentials

| variable | what for | steps |
|---|---|---|
| `AGENT_BASE_URL_DENSE` | base URL of the vLLM server for `Qwen/Qwen3.8-27B` (served as `agent-model`); also used for case-file extraction, the LLM judge and the simulated tools | 6, 7 |
| `AGENT_BASE_URL_MOE` | base URL of the vLLM server for `Qwen/Qwen3.6-35B-A3B-FP8` (served as `agent-model`) | 6, 7 |
| `DECISION_WORK_DIR` | optional; where fetched data and run outputs go (default `./work`, gitignored) | all |

No API keys: the harness sends no `Authorization` header, so keep the servers private (a VPN, an SSH tunnel, or a URL that is only live during the run). Deploying with the sibling serving script needs that script's own cloud credentials (see its RERUN.md). Copy `.env.example` to `.env` and `set -a; . ./.env; set +a` to load them.

## 3. Install

```bash
uv venv .venv && uv sync
```

Verified on 2026-10-22: creates `.venv` with no third-party packages (`dependencies = []`).

## 4. Get the data

Nothing is vendored except IDs and labels (`data/`). Sources and licenses:

| domain | source | license | fetched to |
|---|---|---|---|
| claims | California DMHC Independent Medical Review determinations, CalHHS Open Data Portal: https://data.chhs.ca.gov/dataset/independent-medical-review-imr-determinations-trend | no open license declared; CalHHS Open Data Portal Terms of Use | `work/claims/imr.csv` |
| bva | research index `williamTLmiller/BVA-AMA-Era-170KStructured` (Hugging Face, revision `e09f672731f54b9501615dc65887ed5ecd2bb178`) for case IDs and library labels; decision text from va.gov | index CC-BY-NC-4.0; va.gov text is a US government work | `work/bva/` |
| de_kr | Open Legal Data API, https://de.openlegaldata.io/api/cases/ | no content license declared; German court decisions are official works without copyright (§ 5 UrhG) | `work/de_kr/cases_raw.jsonl` |

```bash
# claims: CSV (85 MB), then the deterministic candidate set and precedent library
mkdir -p work/claims
curl -sSL -o work/claims/imr.csv "https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/3340c5d7-4054-4d03-90e0-5f44290ed095/download/independent-medical-review-imr-determinations-trends.csv"
(cd harness && ../.venv/bin/python claims_bench.py build)
# -> precedents: 19374, candidates: 300                       (verified 2026-10-22, 5 s)

# bva: the 4,000-row index slice (three CSVs, 284 MB), then the original 285 candidates from va.gov
.venv/bin/python scripts/fetch_bva_index.py
# -> wrote .../work/bva/index_sample.jsonl (4000 rows, 3901 unique doc_ids)   (verified 2026-10-22, 18 s)
.venv/bin/python scripts/pin_bva_candidates.py
# -> candidates: 285 rows (0 IDs failed to fetch or label: [])               (verified 2026-10-22, 50 s)

# de_kr: the published 684 judgments, re-fetched by ID (about 1 s per case)
(cd harness && ../.venv/bin/python de_kr_fetch.py --ids ../data/de_kr_case_index.json)
# -> wrote 684 of 684 cases; 0 differ or failed                            (verified 2026-10-22, 16 min)

sha256sum -c data/SHA256SUMS
```

Verified on 2026-10-22: all ten lines print `OK`, so every fetched and derived file is byte-identical to the original run's.

Do not use `bva_bench.py build` to reproduce the published set: it samples grant candidates from decisions fetched on 4 threads in completion order, so every run picks a slightly different set (a rebuild on 2026-10-22 kept 274 of the 281 original candidate IDs). `pin_bva_candidates.py` does the same work with the original candidate list fixed. Likewise, `de_kr_fetch.py` without `--ids` walks the API newest first and stops at 700 cases, so its result depends on the day it runs.

## 5. Free checks

```bash
# every published number from the committed rows, diffed against the export (about 5 s)
.venv/bin/python scripts/analyze_rows.py --check results/decision-agents.json
```

Verified on 2026-10-22. Expected: the accuracy table, the flip and replay numbers, the claims condition table (`base (attempt 0) | 147/150 | 77% | 59% | 32% | 54%`, ..., `sim_tools | 148/150 | 70% | 65% | 45% | 34% | 22%`), `+11 pts (CI +3 to +20, 74 cases)`, the suite-power lines (24%, 37%, 80%), the claims signal and group tables, and then

```
results: MATCH
per_type: MATCH
flips: MATCH
replay: MATCH
signals: MATCH
noise.size: MATCH
```

The claims group table (gender, age) needs `work/claims/candidates.jsonl` from step 4; everything else needs only `results/runs/` and `data/`.

```bash
# the no-AI baselines from the fetched data, plus claims agent-vs-baseline from the rows
.venv/bin/python scripts/baselines.py
for s in 0 1 2 3 4 5; do PYTHONHASHSEED=$s .venv/bin/python scripts/baselines.py | grep "de_kr: majority"; done
```

Verified on 2026-10-22. Expected:

```
claims: majority of past decisions for the same treatment: 103/150 = 0.6867
claims: always overturn: 75/150
claims: agent (dense) vs baseline, all sessions: +7 pts (CI -3 to +17)
claims: agent (moe) vs baseline, all sessions: +1 pts (CI -7 to +11)
bva: majority of past decisions on the same condition word: 77/124 = 0.6210
bva: always grant: 70/124 (library: 705 rows, 693 unique IDs)
de_kr: majority of library cases sharing a distinctive word: 82/150 = 0.5467 (depends on PYTHONHASHSEED)   # one draw; seeds 0-5 give 82, 78, 83, 80, 83, 80
de_kr: always dismiss: 75/150; library 534 cases, 0.4981 dismissed
```

```bash
# rebuild the rows from session files (only possible after a rerun, or with the private originals)
.venv/bin/python scripts/export_rows.py --src work
```

Verified on 2026-10-22 against the original (private) session files: it writes `claims_sessions.jsonl` (1,200 rows), `bva_sessions.jsonl` (496), `de_kr_sessions.jsonl` (600) identical to the committed ones. With those private files in a work directory, the original `analyze` commands of the three benches (`claims_bench.py analyze`, `claims_bench.py expanalyze`, `claims_signals.py`, `bva_bench.py analyze`, `de_kr_bench.py analyze`) run unchanged from `harness/` and print `claims.md`, `claims_conditions.md`, `claims_signals.md` and `bva.md` byte for byte (`de_kr.md` differs only in the hash-seed-dependent baseline line). That check needs the private files and cannot be repeated from this repo.

## 6. Smoke test (paid, not re-run)

The smallest meaningful run is de_kr (no extraction step): 10 cases, both models, one attempt, on running servers.

```bash
set -a; . ./.env; set +a
cd harness && ../.venv/bin/python - <<'EOF'
import json, de_kr_bench as dk
from claims_bench import MODELS, deploy
env = dk.Env()
ids = list(env.cases)[:10]
for m in MODELS:
    url, _ = deploy(f"dekr-{m}", MODELS[m])
    for cid in ids:
        s = dk.session(url, env, cid, m, 0)
        print(m, cid, s["decision"], env.cases[cid]["truth"], s["turns"])
EOF
```

Success: every line prints a decision (`uphold`/`overturn`, occasionally `None` when the dense model runs out of turns) and the published rows for the same `case_id`, `model` and attempt 0 mostly agree (expect 1-2 of 10 to differ: the rerun flip rate is 10-20%). Cost: GPU time only, about 3 minutes of server start-up plus a few minutes of generation per server (cost was not recorded for the original runs; multiply by your H100 hourly price).

## 7. Full rerun (paid, not re-run)

Start the two servers first. With the sibling script (Modal; see `../self-hosted-agents-harness/RERUN.md` for its credentials and naming variables):

```bash
RUN_NAME=decision-dense MODEL=Qwen/Qwen3.8-27B GPU='H100!' VLLM_ARGS='{}' \
  modal deploy --env "$MODAL_ENVIRONMENT" --strategy recreate ../self-hosted-agents-harness/serve_vllm.py
RUN_NAME=decision-moe MODEL=Qwen/Qwen3.6-35B-A3B-FP8 GPU='H100!' VLLM_ARGS='{}' \
  modal deploy --env "$MODAL_ENVIRONMENT" --strategy recreate ../self-hosted-agents-harness/serve_vllm.py
```

or on your own GPU machines (the same flags):

```bash
pip install "vllm==0.31.0" "transformers>=5.8.0"
vllm serve Qwen/Qwen3.8-27B --served-model-name agent-model --max-model-len 65536 \
  --reasoning-parser qwen3 --enable-auto-tool-choice --tool-call-parser qwen3_coder \
  --max-num-seqs 128 --enable-prompt-tokens-details --language-model-only --port 8000
# second machine: the same with Qwen/Qwen3.6-35B-A3B-FP8
```

`--max-num-seqs 128` is required on H100 for the hybrid dense model (vLLM's default exceeds its Mamba cache blocks and start-up fails). Set `AGENT_BASE_URL_DENSE` and `AGENT_BASE_URL_MOE` to the two URLs. Each bench waits until `/v1/models` lists `agent-model`; stop the servers yourself afterwards (`modal app stop ...` for the sibling script). Every bench runs 32 sessions at a time per server; 12 model turns, 4096 max tokens and temperature 0.6 per call; extraction, judge and simulator calls use temperature 0.

Wall times below are from the original run's file timestamps and logs (each includes about 3 minutes of server start-up). GPU cost was not recorded.

| step | command (from `harness/`) | what it does | original wall time | outputs in `work/` |
|---|---|---|---|---|
| claims 1 | `../.venv/bin/python ../scripts/pin_test_set.py claims` | keep the 150 published cases (free) | - | `claims/candidates.jsonl` |
| claims 2 | `../.venv/bin/python claims_bench.py all` | extract case files with the dense model, run both agents (2 attempts), judge (4096 max tokens) | 54 min (17:27-18:21) | `claims/cases.jsonl`, `sessions_{dense,moe}.jsonl`, `judgments.jsonl` |
| claims 3 | `../.venv/bin/python claims_bench.py rejudge` | re-judge sessions with no verdict, 16,000 max tokens | finished 19:00 (start not logged) | `claims/judgments.jsonl` |
| claims 4 | `../.venv/bin/python claims_bench.py exp` | dense agent under the 4 conditions, 1 attempt | finished 21:08 (start not logged) | `claims/sessions_conditions.jsonl` |
| bva 1 | `../.venv/bin/python ../scripts/pin_test_set.py bva` | keep the 124 published cases (free) | - | `bva/candidates.jsonl` |
| bva 2 | `../.venv/bin/python bva_bench.py all` | extract, run both agents, judge | 75 min (20:02-21:17) plus judge | `bva/cases.jsonl`, sessions, judgments |
| bva 3 | `../.venv/bin/python bva_bench.py judge` | judge sessions with no verdict (the original needed restarts; finished 01:37 Oct 10) | not logged | `bva/judgments.jsonl` |
| de_kr 1 | `../.venv/bin/python de_kr_bench.py all` | run both agents, judge | 88 min (21:32-23:00) | `de_kr/sessions_{dense,moe}.jsonl`, judgments |
| de_kr 2 | `../.venv/bin/python de_kr_bench.py resume` | rerun sessions that failed on server errors (74 in the original), then judge | finished 02:04 Oct 10 | the same files |

Extraction samples from the extractions that succeed and pass the leak check, so if some published cases fail to extract the rerun tests fewer cases (the step prints how many it kept). The original claims extraction kept 150 of 300 (1 failed); bva kept 126 rows of 281 (151 failed, 6 leaked).

Then rebuild the rows and the tables:

```bash
cd .. && .venv/bin/python scripts/export_rows.py --src work --out work/runs
```

## 8. Compare with the published results

`scripts/analyze_rows.py` reads `results/runs/`; to analyze a rerun, point it at the new rows by copying them over a scratch checkout's `results/runs/` (or back up the committed rows first), then:

```bash
.venv/bin/python scripts/analyze_rows.py --check results/decision-agents.json
```

Every value will differ; read the differences against the noise floor. An unchanged rerun of the same model flipped 9-20% of decisions, so per-case agreement of 80-90% with the published rows is what "the same" looks like. Accuracy CIs are about ±6-7 points per model and domain (bootstrap over cases): a new accuracy inside the published CI is consistent with it. For paired comparisons (condition vs normal run, agent vs baseline) use the paired bootstrap the scripts print. The judge's no-verdict counts depend on server stability and are not comparable run to run.

## 9. Troubleshooting

- **`claims_bench.py build` fails with HTTP 403 on the CSV.** The portal redirects to a signed S3 URL with an explicit `:443` port, which Python's `urllib` (used by `build`) fails on in some network setups; `curl` works. Download with the `curl` command above first; `build` skips the download when the file exists.
- **va.gov drops the odd request.** `pin_bva_candidates.py` retries each decision 4 times; if it still reports failed IDs, run it again.
- **The dense model on H100 fails to start** with an error about Mamba cache blocks: pass `--max-num-seqs 128`. On H100 vLLM JIT-compiles a FlashInfer kernel for the model's linear-attention layers and needs `nvcc` (a CUDA devel image).
- **Sessions crash with server errors (HTTP 503, disconnects).** The original de_kr dense run lost 115 sessions this way; `de_kr_bench.py resume` reruns only the failed ones. `claims` and `bva` have no resume command; failed sessions are written as `{"error": ...}` rows and analysis skips them, so check the "N sessions, M with a decision" line.
- **The judge returns no verdict** for many sessions (server disconnects, or the judge's reasoning used all its tokens). `claims_bench.py rejudge` and `bva_bench.py judge` redo only the missing ones; the bva and de_kr judges save each verdict as it arrives (`judgments.partial.jsonl`), so a restart loses nothing.
- **A crash-looping or forgotten server keeps billing.** Stop the servers when a bench prints its `done` line.

## Changes from the original run

- `harness/claims_bench.py`: `deploy()` / `stop()` no longer deploy and stop cloud GPU apps by name. `deploy()` reads the server URL from `AGENT_BASE_URL_DENSE` / `AGENT_BASE_URL_MOE` and waits for `/v1/models` exactly as before; `stop()` only prints. The `import experiment` and `subprocess` uses went with them. Data paths moved from `<script dir>/<domain>/` to `work/<domain>/` (override with `DECISION_WORK_DIR`), exported as `WORK` for the other benches; `build` creates parent directories. Docstring updated. Prompts, tools, sampling, agent loop, judge and analysis are unchanged.
- `harness/bva_bench.py`, `harness/de_kr_bench.py`: import `WORK` from `claims_bench` for their data directories; unused `Path` import removed; docstrings updated. The va.gov User-Agent string now names this repo instead of the private one.
- `harness/de_kr_fetch.py`: output path under `work/de_kr/`; neutral User-Agent; new `--ids` mode that re-fetches a fixed list of cases by ID and checks each label (the original month walk is unchanged and still the default).
- `harness/claims_signals.py`: unchanged (it reads `claims_bench.D`).
- New scripts: `scripts/fetch_bva_index.py` (the original had no script for `bva/index_sample.jsonl`), `scripts/pin_bva_candidates.py`, `scripts/pin_test_set.py`, `scripts/export_rows.py`, `scripts/analyze_rows.py` (a rows-based port of the export's `decision_compute.py`), `scripts/baselines.py`.
- `results/decision-agents.json`: the export with its `public_safety` items rewritten without internal infrastructure names, the dataset licenses filled in, a public code location and a `port_notes` list added. No number changed.
