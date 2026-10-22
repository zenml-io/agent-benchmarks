#!/usr/bin/env bash
# Step 3, revised with the user: load + serving sweep on a lean harness (terminus-2) and a
# token-heavy one (mini-swe-agent), all 36 tasks, 1 rep, vLLM /metrics scraped every run.
# terminus-2's c=16 defaults run came from the earlier matrix. Each line is resumable: completed
# runs in attempts.jsonl are skipped. Run detached:
#   setsid nohup ./run_infra.sh > infra.log 2>&1 < /dev/null &
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."   # benchmark dir: attempts.jsonl, jobs/, data/
run() { SPENT_BEFORE=${SPENT_BEFORE:-0} python3 -u ../self-hosted-agents-harness/experiment.py --run-reserve 15 --harnesses terminus-2 mini-swe-agent -- matrix --reps 1 "$@"; }
run --concurrency 16 --configs defaults          # load sweep: 16 (terminus-2 already done)
run --concurrency 32 --configs defaults          #             -> 32
run --concurrency 32 --configs no-prefix-cache   # serving changes at the higher load
run --concurrency 32 --configs spec-mtp
run --concurrency 32 --configs kv-fp8
run --concurrency 32 --configs weights-fp8
run --concurrency 8 --configs defaults           # load sweep: 8 (slowest, so last)
echo "INFRA DONE"
