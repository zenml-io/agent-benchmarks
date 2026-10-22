# sglang-vs-vllm: SGLang vs vLLM on replayed agent traffic

## Question

At equal hardware and identical agent traffic, does the serving engine (stock vLLM vs SGLang) change throughput and latency for this hybrid-attention model?

## Status

Complete. Four runs on 2026-10-09 between 15:17 and 16:21 UTC. Total spend $4.5206: the sum of the four runs' server up-time (startup + replay) at $3.95 per H100-hour, computed by `src/replay_bench.py`, not taken from the Modal bill. No sandboxes, no model API.

Setup: Qwen3.8-27B (BF16) on one Modal H100 (`H100!`, no substitution). vLLM 0.31.0 with the agentperf-infra server flags, against SGLang 0.5.20 (`lmsysorg/sglang:v0.5.20`) with the equivalent flags (`../self-hosted-agents-harness/serve_sglang.py`). Workload: 124 recorded mini-swe-agent sessions (1,465 model turns) from agentperf-infra's Terminal-Bench runs at 32 agents with vLLM defaults; each request re-sends the conversation as the agent sent it and asks for exactly the recorded number of tokens (`ignore_eos`, temperature 0.6, streaming), 32 sessions at once, 3 s gap between turns, 720 s replay window.

## Results

From `results/sglang-vs-vllm.json` (rebuilt from `results/runs/` by `scripts/rebuild_export.py`, identical). n = requests sent. One run per setting.

| setting | n | completed | errored | sessions reached | generated tok/s | vs vLLM | median request s | p90 s | median TTFT s | median ms/token | peak running | peak waiting | measured window s |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| stock vLLM | 504 | 504 | 0 | 55 | 391.94 | 1.0000 | 27.92 | 107.44 | 8.66 | 53.94 | 31 | 11 | 832.8 |
| stock SGLang | 277 | 277 | 0 | 39 | 205.79 | 0.5251 | 88.09 | 142.25 | 76.29 | 22.51 | 5 | 27 | 815.2 |
| SGLang, lazy radix + bf16 states | 417 | 417 | 0 | 47 | 301.97 | 0.7704 | 54.04 | 115.88 | 36.49 | 31.34 | 27 | 26 | 903.2 |
| SGLang, radix cache off | 446 | 435 | 11 | 47 | 328.68 | 0.8386 | 45.97 | 95.75 | 29.39 | 38.52 | 31 | 24 | 855.4 |

Completed requests relative to stock vLLM: stock SGLang 0.5496, lazy radix 0.8274, radix cache off 0.8631. Settings: lazy radix = `--mem-fraction-static 0.85 --mamba-radix-cache-strategy extra_buffer_lazy --mamba-ssm-dtype bfloat16 --max-mamba-cache-size 128`; radix cache off = `--mem-fraction-static 0.85 --disable-radix-cache --max-mamba-cache-size 48`. The 11 errors were `ConnectionResetError`. Stock SGLang admitted at most 5 requests at once: for this hybrid model its prefix cache keeps 5 linear-attention state slots of 154 MB per request, so its default memory split admits only 5 requests at a time and the rest queue (the original write-up, `docs/FINDINGS-section10.md`).

## Trust status

**Reproduced from the published rows (2026-10-22):** every value in `results` and `meta.total_spend_usd` of the export, from `results/runs/bench.jsonl` (one summary per run, as `replay_bench.py` wrote it) and `results/runs/bench-<name>.json` (every request's timing, token usage and error; no prompts). The rebuild also checks that the per-request rows give the same completed/errored counts and generated tokens per second as the run summaries. `scripts/rebuild_export.py` prints `ALL MATCH`.

**Not reproduced:** no replay was re-run. The replay workload (the 124 recorded mini-swe-agent conversations) is not published: it contains Terminal-Bench task content and agent transcripts. A rerun needs either those trajectories from the private archive or a fresh recording (agentperf-infra's mini-swe-agent defaults runs at 32 agents), which would be different traffic. One run per setting, so there is no noise estimate; in the agent study identical runs varied about 20% in time.

**Known inconsistencies (from the export):**

- The original write-up says each replay ran 12 minutes; the measured windows are 815.2-903.2 s, because in-flight requests finish after the 720 s deadline. Throughput is divided by the measured window.
- It says SGLang with the radix cache off was "14% behind stock vLLM"; that matches completed requests (435 vs 504, 0.8631); by generated tokens per second it is 0.8386 (16% behind).
- It does not mention the 11 errored requests in the radix-cache-off run.
- It says the claim tested against was "SGLang about 50% faster than vLLM, measured on 3090s with a different model"; no source for that claim is recorded.

**Steps that would vet it further:**

1. Repeat the stock vLLM and stock SGLang replays twice each on the same recorded workload (about $1.08-1.10 and 16.5 minutes per run, recorded) to get a noise floor for the 0.5251 ratio.
2. Check stock SGLang's 5-request cap directly: start the server and read its startup log for the computed max running requests (one short paid start, no replay).
3. Rerun with a newer SGLang release, since the hybrid-model memory handling is what limits it here.
4. Re-record a fresh workload (one agentperf-infra mini-swe-agent c=32 defaults run) and replay both stock engines on it, to see whether the ratio holds on different traffic.

## Harbor status

`not applicable`. No agents and no tasks: this replays recorded model requests directly against an engine's OpenAI-compatible endpoint and measures serving only. The traffic itself was recorded from Harbor jobs in agentperf-infra.

## Limitations

- One run per setting; no CIs.
- One model (hybrid Gated DeltaNet + attention, where SGLang's per-request linear-attention state is the bottleneck), one GPU type, one workload (mini-swe-agent traffic at 32 sessions).
- Only two non-default SGLang settings tried, following its cookbook; not an exhaustive tuning of either engine.
- Measures serving throughput and latency, not agent outcomes; a real agent would react to slower responses.
- Runs reached different numbers of sessions (39-55 of 124) within the window, so later sessions with longer prompts weigh differently across engines.
- Replayed prompts were a median 0.8769-0.9256 of the recorded prompt tokens (reasoning text is not re-sent).
- Cost is GPU up-time at list price, not the bill.

## Provenance

Original: `replay_bench.py` and `bench.jsonl` at the root of the private research repo (commit 0d1500e22533e7f546bc6d8cfe5abe8d976c9868; `replay_bench.py`/`serve_sglang.py` last changed in e7262e4ea7f0b435fb5721706ce342ba052c4cba; `bench.jsonl` in ec9420707285f3e778bbe9bd60a5b02cd1dc4464). Per-request files came from the original `jobs/bench-<name>.json`. Run by Hamza Tahir (ZenML) with Claude Code agents. Ported 2026-10-22. The servers are in `../self-hosted-agents-harness/`.
