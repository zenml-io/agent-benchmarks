#!/usr/bin/env bash
# Streams B and C of the extended plan (original run), in parallel with run_infra.sh
# (stream A, slot 0). Each stream has its own slot, so its servers are agent-<config>-s<N>
# and never collide with another stream's. Resumable: completed runs are skipped.
#   setsid nohup ./run_streams.sh > streams.log 2>&1 < /dev/null &
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."   # benchmark dir: attempts.jsonl, jobs/, data/
H="terminus-2 mini-swe-agent"
# 3 streams can each start a run before the others' spend is recorded: keep more headroom.
run() { slot=$1; shift; SPENT_BEFORE=${SPENT_BEFORE:-0} python3 -u ../self-hosted-agents-harness/experiment.py --slot "$slot" --run-reserve 15 \
          --harnesses $H -- matrix "$@"; }

# B: new levers at 32 agents. Reasoning off, a bigger GPU, and a longer agent time limit.
( run 1 --reps 1 --concurrency 32 --configs no-thinking h200 defaults-2x-time
  echo "STREAM B DONE" ) > stream_b.log 2>&1 &

# C: second repeat of stream A's 32-agent configs (is a difference bigger than run-to-run noise?).
( run 2 --reps 2 --rep-from 1 --concurrency 32 --configs defaults spec-mtp kv-fp8 weights-fp8 no-prefix-cache
  echo "STREAM C DONE" ) > stream_c.log 2>&1 &
wait
