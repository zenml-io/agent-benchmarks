# How agents fail, by harness and server

Share of all trials per class (pooled over repeats). Looping = at least 50% of the last 8 actions repeat an earlier action.

| benchmark | harness | c | config | gpu | trials | solved | never started | looked up answer | finished wrong | out of time, working | out of time, looping | other error |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| terminal-bench | mini-swe-agent | 8 | defaults | H100! | 36 | 50% | 6% | 0% | 8% | 36% | 0% | 0% |
| terminal-bench | mini-swe-agent | 16 | defaults | H100! | 108 | 44% | 6% | 0% | 3% | 47% | 0% | 1% |
| terminal-bench | mini-swe-agent | 16 | defaults-4x-time | H100! | 36 | 47% | 6% | 0% | 11% | 28% | 0% | 8% |
| terminal-bench | mini-swe-agent | 16 | moe-a3b | H100! | 108 | 49% | 6% | 0% | 23% | 9% | 0% | 13% |
| terminal-bench | mini-swe-agent | 16 | spec-mtp | H100! | 36 | 47% | 6% | 3% | 0% | 44% | 0% | 0% |
| terminal-bench | mini-swe-agent | 32 | defaults | H100! | 144 | 30% | 6% | 0% | 1% | 64% | 0% | 0% |
| terminal-bench | mini-swe-agent | 32 | b200 | B200 | 108 | 49% | 6% | 1% | 8% | 28% | 0% | 8% |
| terminal-bench | mini-swe-agent | 32 | defaults-2x-time | H100! | 108 | 39% | 6% | 1% | 3% | 48% | 0% | 4% |
| terminal-bench | mini-swe-agent | 32 | defaults-4x-time | H100! | 36 | 39% | 6% | 0% | 11% | 42% | 0% | 3% |
| terminal-bench | mini-swe-agent | 32 | h200 | H200 | 108 | 45% | 6% | 0% | 5% | 41% | 0% | 4% |
| terminal-bench | mini-swe-agent | 32 | h200-spec-mtp | H200 | 36 | 50% | 6% | 0% | 11% | 25% | 0% | 8% |
| terminal-bench | mini-swe-agent | 32 | kv-fp8 | H100! | 72 | 38% | 6% | 1% | 4% | 50% | 0% | 1% |
| terminal-bench | mini-swe-agent | 32 | moe-a3b | H100! | 108 | 49% | 6% | 0% | 20% | 15% | 0% | 10% |
| terminal-bench | mini-swe-agent | 32 | no-prefix-cache | H100! | 72 | 35% | 6% | 0% | 1% | 58% | 0% | 0% |
| terminal-bench | mini-swe-agent | 32 | no-thinking | H100! | 108 | 40% | 6% | 0% | 11% | 42% | 1% | 1% |
| terminal-bench | mini-swe-agent | 32 | spec-mtp | H100! | 144 | 36% | 6% | 1% | 1% | 55% | 0% | 1% |
| terminal-bench | mini-swe-agent | 32 | weights-fp8 | H100! | 72 | 40% | 6% | 0% | 3% | 50% | 0% | 1% |
| terminal-bench | mini-swe-agent | 48 | defaults | H100! | 72 | 35% | 6% | 0% | 0% | 60% | 0% | 0% |
| terminal-bench | mini-swe-agent | 64 | defaults | H100! | 72 | 26% | 6% | 0% | 1% | 67% | 0% | 0% |
| terminal-bench | opencode | 16 | defaults | H100! | 36 | 50% | 6% | 0% | 14% | 31% | 0% | 0% |
| terminal-bench | opencode | 32 | defaults | H100! | 36 | 44% | 6% | 0% | 8% | 42% | 0% | 0% |
| terminal-bench | pi | 16 | defaults | H100! | 36 | 42% | 6% | 3% | 11% | 36% | 0% | 3% |
| terminal-bench | pi | 32 | defaults | H100! | 36 | 39% | 6% | 0% | 17% | 36% | 0% | 3% |
| terminal-bench | terminus-2 | 8 | defaults | H100! | 36 | 53% | 0% | 0% | 8% | 39% | 0% | 0% |
| terminal-bench | terminus-2 | 16 | defaults | H100! | 108 | 44% | 0% | 0% | 5% | 50% | 1% | 0% |
| terminal-bench | terminus-2 | 16 | defaults-4x-time | H100! | 36 | 61% | 0% | 0% | 19% | 17% | 3% | 0% |
| terminal-bench | terminus-2 | 16 | moe-a3b | H100! | 108 | 47% | 0% | 0% | 27% | 21% | 4% | 1% |
| terminal-bench | terminus-2 | 16 | spec-mtp | H100! | 36 | 53% | 0% | 0% | 17% | 31% | 0% | 0% |
| terminal-bench | terminus-2 | 32 | defaults | H100! | 216 | 41% | 0% | 0% | 4% | 54% | 0% | 0% |
| terminal-bench | terminus-2 | 32 | b200 | B200 | 108 | 56% | 0% | 0% | 9% | 35% | 0% | 0% |
| terminal-bench | terminus-2 | 32 | defaults-2x-time | H100! | 108 | 46% | 0% | 0% | 8% | 44% | 1% | 0% |
| terminal-bench | terminus-2 | 32 | defaults-4x-time | H100! | 36 | 47% | 0% | 0% | 19% | 33% | 0% | 0% |
| terminal-bench | terminus-2 | 32 | h200 | H200 | 108 | 44% | 0% | 0% | 6% | 48% | 1% | 0% |
| terminal-bench | terminus-2 | 32 | h200-spec-mtp | H200 | 36 | 58% | 0% | 0% | 6% | 36% | 0% | 0% |
| terminal-bench | terminus-2 | 32 | kv-fp8 | H100! | 72 | 50% | 0% | 0% | 4% | 46% | 0% | 0% |
| terminal-bench | terminus-2 | 32 | moe-a3b | H100! | 108 | 43% | 0% | 1% | 20% | 26% | 7% | 3% |
| terminal-bench | terminus-2 | 32 | no-prefix-cache | H100! | 72 | 43% | 0% | 0% | 1% | 56% | 0% | 0% |
| terminal-bench | terminus-2 | 32 | no-thinking | H100! | 108 | 45% | 0% | 0% | 9% | 40% | 6% | 0% |
| terminal-bench | terminus-2 | 32 | spec-mtp | H100! | 144 | 44% | 0% | 0% | 4% | 51% | 1% | 0% |
| terminal-bench | terminus-2 | 32 | weights-fp8 | H100! | 72 | 42% | 0% | 0% | 6% | 53% | 0% | 0% |
| terminal-bench | terminus-2 | 48 | defaults | H100! | 72 | 33% | 0% | 0% | 1% | 64% | 1% | 0% |
| terminal-bench | terminus-2 | 64 | defaults | H100! | 72 | 22% | 0% | 0% | 1% | 75% | 1% | 0% |
| gaia | mini-swe-agent | 16 | defaults | H100! | 60 | 30% | 0% | 7% | 10% | 53% | 0% | 0% |
| gaia | mini-swe-agent | 32 | defaults | H100! | 60 | 22% | 0% | 7% | 7% | 65% | 0% | 0% |
| gaia | mini-swe-agent | 32 | h200 | H200 | 60 | 35% | 0% | 12% | 10% | 43% | 0% | 0% |
| gaia | terminus-2 | 16 | defaults | H100! | 60 | 23% | 0% | 0% | 18% | 58% | 0% | 0% |
| gaia | terminus-2 | 32 | defaults | H100! | 60 | 20% | 0% | 0% | 17% | 63% | 0% | 0% |
| gaia | terminus-2 | 32 | h200 | H200 | 60 | 33% | 0% | 0% | 15% | 50% | 2% | 0% |

Sensitivity: share of timed-out trials classed as looping when actions only need to match on their first N characters (looser = more loops).

| match on | timed-out trials | looping | still working |
|---|---|---|---|
| full text | 1710 | 2% | 98% |
| first 40 chars | 1710 | 14% | 86% |
| first 20 chars | 1710 | 30% | 70% |

