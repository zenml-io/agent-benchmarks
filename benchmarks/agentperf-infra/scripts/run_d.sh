#!/usr/bin/env bash
# Stream D (after the prior-work search and the first infra results): two parallel streams.
#   setsid nohup ./run_d.sh > stream_d.log 2>&1 < /dev/null &
# D1: the headline comparisons with 2 attempts per task (72 trials per run, about half the
#     noise of a 36-task run): does the score depend on the time budget the server gives?
# D2: does the harness set serving capacity (pi, opencode), and where is the load cliff?
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."   # benchmark dir: attempts.jsonl, jobs/, data/
run() { slot=$1; shift; SPENT_BEFORE=${SPENT_BEFORE:-0} python3 -u ../self-hosted-agents-harness/experiment.py --slot "$slot" --run-reserve 15 "$@"; }
MAIN="terminus-2 mini-swe-agent"

( run 5 --harnesses $MAIN -- matrix --reps 1 --attempts 2 --concurrency 32 --configs defaults defaults-2x-time spec-mtp
  run 5 --harnesses $MAIN -- matrix --reps 1 --attempts 2 --concurrency 16 --configs defaults
  echo "STREAM D1 DONE" ) > stream_d1.log 2>&1 &

( run 6 --harnesses pi opencode -- matrix --reps 1 --concurrency 16 32 --configs defaults
  run 6 --harnesses $MAIN -- matrix --reps 1 --attempts 2 --concurrency 48 64 --configs defaults
  echo "STREAM D2 DONE" ) > stream_d2.log 2>&1 &
wait
