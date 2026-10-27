# Rerun: claims over time

Each component's README has the full detail; this file gives the order. Commands marked "verified 2026-10-27" were run while building the benchmark. No full round has run, so the full-run steps are untested.

## 1. Prerequisites

- macOS or Linux, Python 3.12, uv 0.13 or later.
- Docker with OrbStack on macOS (Harbor's network control needs it; Docker Desktop rejects `no-network`). Use `DOCKER_CONTEXT=orbstack` on Harbor commands.
- Harbor 0.22.0 (`uv tool install harbor==0.22.0`).
- A Modal account (one H100 for the open model, case-file extraction and the classifier).
- An OpenAI account (the claims agent before the switch, both improvers).
- For the ZenML Pro arm only: a Kitaru workspace on ZenML Pro, a ZenML Pro service-account key, and the ZenML Pro agent bundle (not public; see `harbor/round_task/README.md`).

## 2. Credentials

Names only; values go in `work/.env` (gitignored) or the shell. See `.env.example`.

| variable | for | steps |
|---|---|---|
| `OPENAI_API_KEY` | claims agent on OpenAI models, both improvers | 6, 7 |
| `MODAL_ENVIRONMENT` | the Modal environment to deploy into | 4, 6, 7 |
| `CLAIMS_AGENT_BASE_URL` | the open model's endpoint (`.../v1`), from the switch round on | 6, 7 |
| `KITARU_API_URL`, `KITARU_PRO_API_KEY` | the Kitaru workspace for the ZenML Pro arm | 7 |
| `PRO_AGENT_DIR`, `PRO_BASE_IMAGE` | the ZenML Pro agent bundle and its trial image | 7 |
| `CLAIMS_WORK_DIR` | optional; default `./work` | all |

## 3. Install

```bash
uv sync --all-extras    # verified 2026-10-27: kitaru 0.27.2, kitaru-pydantic-ai 0.3.1, modal 1.6.2
```

## 4. Get the data

```bash
uv run python scripts/build_stream.py                                   # free; verified 2026-10-27
uv run --extra modal python harness/extract/extract.py all              # about $3.20 on Modal; verified (as up/run/down)
uv run python scripts/assign_batches.py                                 # free; verified 2026-10-27
```

Expected: 19,374 precedents (same sha256 as `../decision-agents/data/SHA256SUMS`), 3,155 candidates, 3,131 usable case files, 900 appeals in `data/stream.jsonl` (100 per batch, 160 revealed). `assign_batches.py` writes the same `data/stream.jsonl` as the committed one when the extraction matches; vLLM output at temperature 0 can vary slightly between runs, which can change which appeals are usable.

Source: [California IMR determinations](https://data.chhs.ca.gov/dataset/independent-medical-review-imr-determinations-trend), CalHHS Open Data Portal (terms of use allow free download and use).

## 5. Free checks

```bash
uv run --with pytest pytest -q scripts                                  # 3 passed; verified 2026-10-27
uv run python scripts/score.py work/runs/<tag>.jsonl                    # per-batch and cumulative table
```

## 6. Smoke tests (paid, small)

- **Calibration batch on three models** (about $2.50): run `scripts/run_batch.py --batch 0` with the frozen agent on Qwen (`CLAIMS_AGENT_BASE_URL` set, server from `harness/extract/extract.py up`), and with copies whose `config.toml` uses `openai-responses:gpt-6.1-sol` and `openai-responses:gpt-6-luna`. Expected: Qwen 70 to 76% accuracy, Sol about 88% balanced accuracy. Verified 2026-10-27 (table in `README.md`). GPT-6 models need the Responses API (`openai-responses:`); on chat completions they reject tools with reasoning.
- **HICRIC classifier** (about $1.60): `harness/hicric/README.md`, section Rerun. Verified 2026-10-27.
- **Mini round** (about $0.50): `harbor/round_task/README.md`, section Mini round 3. Verified 2026-10-27.

## 7. Full rerun (not run yet)

```bash
harbor/round_task/build_images.sh                                       # verified 2026-10-27
export DOCKER_CONTEXT=orbstack CLAIMS_AGENT_BASE_URL=... PRO_AGENT_DIR=...
uv run --extra agent python scripts/round.py --frontier-preset gpt-6.1-sol --rounds 1-8
```

`round.py` is resumable: each finished step writes `work/rounds/round-<k>/<step>.json` and is skipped on rerun. The open model's server must be up from round 4. Cost and wall time are not known yet.

## 8. Compare with the published results

`scripts/score.py` rebuilds every table from the rows in `work/runs/`. Read differences against the 95% intervals it prints: one batch of 100 has an interval 10 to 20 points wide.

## 9. Troubleshooting

- **`Function tools with reasoning_effort are not supported ... in /v1/chat/completions`**: use `openai-responses:<model>` in the agent's `config.toml` for GPT-6 models.
- **Harbor rejects `no-network`**: the Docker context is Docker Desktop; set `DOCKER_CONTEXT=orbstack`.
- **Local Kitaru API keys rejected ("under control plane authentication")**: a ZenML Pro hosted workspace accepts only ZenML Pro credentials; use a service-account key.
- **Qwen appeals end undecided with "Model token limit (4096) exceeded"**: the original agent's output limit; the model's reasoning used it up. Expected for a few appeals per batch.
