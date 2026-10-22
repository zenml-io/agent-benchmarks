#!/usr/bin/env bash
# Stream I: new 72-trial runs (2 attempts per task) that test PREREGISTRATION.md claims C1-C3.
# Runs recorded before the pre-registration commit don't count, so terminus-2's c=32 defaults
# run gets a second repeat. (mini-swe-agent's c=16/c=32 defaults k2 runs are in stream D1.)
#   setsid nohup ./run_i.sh > stream_i.log 2>&1 < /dev/null &
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."   # benchmark dir: attempts.jsonl, jobs/, data/
run() { SPENT_BEFORE=${SPENT_BEFORE:-0} python3 -u ../self-hosted-agents-harness/experiment.py --slot 9 --run-reserve 15 "$@"; }
run --harnesses terminus-2 mini-swe-agent -- matrix --reps 1 --attempts 2 --concurrency 32 --configs h200 no-thinking
run --harnesses terminus-2 -- matrix --reps 2 --rep-from 1 --attempts 2 --concurrency 32 --configs defaults
echo "STREAM I DONE"
