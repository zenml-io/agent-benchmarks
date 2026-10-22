# Engine defaults (section 10 of the original FINDINGS.md)

*Copied unchanged from the original private repository (commit 0d1500e2). Where it disagrees with results/sglang-vs-vllm.json, the JSON wins; see README.md, Trust status.*

### 10. Engine defaults: stock SGLang ran at half of vLLM's throughput on this model

We replayed real mini-swe-agent traffic (124 recorded sessions, same prompts and generation
lengths, 32 at once, 12 minutes) on one H100 against vLLM 0.31.0 and SGLang 0.5.20
(`replay_bench.py`, `bench.jsonl`; no agents, so this measures serving, not solves):

| | stock vLLM | stock SGLang | SGLang, lazy radix + bf16 states | SGLang, radix cache off |
|---|---|---|---|---|
| requests completed | 504 | 277 | 417 | 435 |
| generated tokens/s | 392 | 206 | 302 | 329 |
| median request time | 28 s | 88 s | 54 s | 46 s |
| peak concurrent requests | 31 | 5 | 27 | 31 |

For this hybrid model, SGLang's prefix cache keeps 5 linear-attention state slots of 154 MB per
request, so its default memory split admits only 5 requests at a time; nothing errors, requests
just queue. Following its cookbook recovers most of the gap, and its best setting here was
turning its prefix cache off, still 14% behind stock vLLM. The claim we started from (SGLang
about 50% faster than vLLM, measured on 3090s with a different model) does not carry over to this
model, GPU and workload. One run per setting; we tried two of SGLang's settings, not an
exhaustive tuning.
