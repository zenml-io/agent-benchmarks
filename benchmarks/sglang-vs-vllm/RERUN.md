# Rerunning sglang-vs-vllm

Commands in sections 3-5 were run while writing this file, from this directory, on 2026-10-22. Sections 6-7 cost money and were **not re-run**; costs and times are the recorded ones in `results/runs/bench.jsonl`.

## 1. Prerequisites

- Linux or macOS, Python 3.11+, [uv](https://docs.astral.sh/uv/).
- Paid replays: a Modal account with H100 access, the Modal CLI (`modal[api-proxy-support]==1.6.1`), and the recorded workload (section 4).

## 2. Credentials

| variable | for | steps |
|---|---|---|
| `MODAL_TOKEN_ID`, `MODAL_TOKEN_SECRET` | deploying the vLLM or SGLang server | 6, 7 |
| `MODAL_ENVIRONMENT`, `MODAL_APP_PREFIX`, `MODAL_HF_CACHE_VOLUME`, `MODAL_VLLM_CACHE_VOLUME`, `MODAL_FLASHINFER_CACHE_VOLUME` | Modal environment, app-name prefix and volumes (defaults `main`, `agent`, `hf-cache`, `vllm-cache`, `flashinfer-cache`) | 6, 7 |
| `REPLAY_TRAJ_GLOB` | where the recorded trajectories are (default `../agentperf-infra/jobs/full*__mini-swe-agent__defaults__c32__*/*/agent/mini-swe-agent.trajectory.json`) | 6, 7 |

No API keys, no Hugging Face token (the model is public).

## 3. Install (verified on 2026-10-22)

```bash
cd benchmarks/sglang-vs-vllm
uv sync                                                # no dependencies
uv run python src/replay_bench.py --help               # prints usage; nothing is deployed
uv tool install 'modal[api-proxy-support]==1.6.1'      # paid steps only; "modal client version: 1.6.1"
```

## 4. Get the data

Free checks need nothing beyond `results/runs/` (committed: `bench.jsonl`, four run summaries; `bench-<name>.json`, every request's timing, token counts and error, about 630 KB, no prompts).

The replay workload is **not published**: 124 mini-swe-agent sessions recorded in agentperf-infra's three Terminal-Bench runs at 32 agents with vLLM defaults (`full__mini-swe-agent__defaults__c32__r0__20261009-052026`, `..._r1__20261009-072204`, `full-k2__mini-swe-agent__defaults__c32__r0__20261009-082522`; turns with recorded prompts over 60,000 tokens are cut). They contain Terminal-Bench task content and agent transcripts and stay in the private archive. Without them, record new traffic first (paid; section 6 of `../agentperf-infra/RERUN.md`):

```bash
cd ../agentperf-infra && python ../self-hosted-agents-harness/experiment.py --harnesses mini-swe-agent -- matrix --configs defaults --concurrency 32 --rep-from 0 --reps 1
```

(recorded: $1.29-4.59 GPU and $0.81-4.56 sandboxes per c=32 run, 21-72 minutes). New traffic is a different workload, so expect different absolute numbers.

## 5. Free checks (verified on 2026-10-22)

```bash
uv run python scripts/rebuild_export.py
```

Expected output:

```
stock vLLM: 504/504 requests, 391.94 gen tok/s (1.0 of vLLM), p50 27.92 s, peak running 31.0, errors 0
stock SGLang: 277/277 requests, 205.79 gen tok/s (0.5251 of vLLM), p50 88.09 s, peak running 5.0, errors 0
SGLang, lazy radix + bf16 states: 417/417 requests, 301.97 gen tok/s (0.7704 of vLLM), p50 54.04 s, peak running 27.0, errors 0
SGLang, radix cache off: 435/446 requests, 328.68 gen tok/s (0.8386 of vLLM), p50 45.97 s, peak running 31.0, errors 11
total spend $4.5206
ALL MATCH
```

## 6. Smoke test (paid, not re-run)

One stock vLLM replay with a shorter window:

```bash
uv run python src/replay_bench.py --engine vllm --name rb-vllm-smoke --duration 120
```

Not run in the original study at this length; the full 720 s run cost $1.0943 with 16.6 minutes of server time (164 s of it startup), so a 120 s window costs roughly $0.45. Success: it prints `124 sessions, 1465 turns` (with the original workload), `ready after ...s`, then a record with `requests_ok` > 0 and `errors` 0, appended to `bench.jsonl` in this directory; `jobs/bench-rb-vllm-smoke.json` holds the per-request rows. The server is stopped in a `finally`.

## 7. Full rerun (paid, not re-run)

Run one after another (each deploys, replays for 720 s, stops):

```bash
uv run python src/replay_bench.py --engine vllm   --name rb-vllm
uv run python src/replay_bench.py --engine sglang --name rb-sglang
uv run python src/replay_bench.py --engine sglang --name rb-sglang-lazy \
  --args '{"--mem-fraction-static": "0.85", "--mamba-radix-cache-strategy": "extra_buffer_lazy", "--mamba-ssm-dtype": "bfloat16", "--max-mamba-cache-size": "128"}'
uv run python src/replay_bench.py --engine sglang --name rb-sglang-noradix \
  --args '{"--mem-fraction-static": "0.85", "--disable-radix-cache": true, "--max-mamba-cache-size": "48"}'
```

Recorded cost and server time: $1.0943 / 16.6 min, $1.0790 / 16.4 min, $1.1762 / 17.9 min, $1.1711 / 17.8 min; $4.5206 in total (GPU up-time at $3.95/h; the bill may differ). Defaults: `--gpu H100! --concurrency 32 --duration 720 --gap 3.0`. Outputs: `bench.jsonl` and `jobs/bench-<name>.json` in this directory.

## 8. Compare with the published results

Copy your `bench.jsonl` and `jobs/bench-*.json` over `results/runs/` in a scratch copy and run `scripts/rebuild_export.py`: it lists every value that differs from the published JSON. One run per setting was published, so there is no noise floor; replay each setting at least twice before reading a difference of less than about 20% in throughput as real. With a re-recorded workload, compare ratios to stock vLLM, not absolute numbers.

## 9. Troubleshooting

- SGLang crash loop "cannot mount volume on non-empty path": the image ships files in `/root/.cache/huggingface`; `serve_sglang.py` mounts the weights volume at `/hf-cache` with `HF_HOME` for that reason.
- SGLang server dies at startup: `serve_sglang.py` ends the container when the server exits, so it stops billing; check `modal app logs`.
- Stock SGLang running only ~5 requests is expected for this model (see README); the tuned settings raise it.
- `0 sessions`: `REPLAY_TRAJ_GLOB` does not match any recorded trajectory.

## Changes from the original run

- `src/replay_bench.py`: the Modal environment and app-name prefix come from `MODAL_ENVIRONMENT` / `MODAL_APP_PREFIX` instead of hard-coded names; the servers and `experiment.py` are imported from `../self-hosted-agents-harness/`; outputs go to this directory (`bench.jsonl`, `jobs/`, created if missing); the default trajectory glob points at `../agentperf-infra/jobs/` and can be set with `REPLAY_TRAJ_GLOB`. Measurement code unchanged.
- Results: `results/runs/bench.jsonl` is the original file unchanged; `results/runs/bench-<name>.json` are the original per-request files unchanged (they hold only timings, token counts, trial names and errors). `results/sglang-vs-vllm.json` is the export with its `public_safety` wording neutralized.
- New: `scripts/rebuild_export.py`.
