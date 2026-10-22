#!/usr/bin/env bash
# Stream J: does the agent/infra coupling hold beyond coding? GAIA (tasks_gaia.json, 60 tasks,
# 10-min limit). Same key cells as the coding study: H100 at c=16 and c=32, H200 at c=32, for
# terminus-2 and mini-swe-agent. Two slots so both harnesses run in parallel.
#   setsid nohup ./run_j.sh > stream_j2.log 2>&1 < /dev/null &
export PATH="$HOME/.local/bin:$PATH"
cd "$(dirname "$0")/.."   # benchmark dir: attempts.jsonl, jobs/, data/
run() { slot=$1; h=$2; shift 2; SPENT_BEFORE=${SPENT_BEFORE:-0} python3 -u ../self-hosted-agents-harness/experiment.py --tasks-file tasks_gaia.json \
          --slot "$slot" --run-reserve 15 --harnesses "$h" -- matrix --reps 1 "$@"; }
( run 11 mini-swe-agent --concurrency 16 32 --configs defaults
  run 11 mini-swe-agent --concurrency 32 --configs h200
  echo "STREAM J mini DONE" ) > stream_j_mini.log 2>&1 &
( while pgrep -f "tasks-file tasks_gaia.json --slot 10" >/dev/null; do sleep 30; done   # pilot first
  run 10 terminus-2 --concurrency 16 32 --configs defaults
  run 10 terminus-2 --concurrency 32 --configs h200
  echo "STREAM J terminus DONE" ) > stream_j_terminus.log 2>&1 &
wait
