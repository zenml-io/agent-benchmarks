#!/bin/bash
# Run one arm of a SwapBench task with a coding agent on Modal through Harbor.
#   run_arm.sh <harbor_task> <agent: codex|claude-code> <model> <attempts> [concurrency]
# Modal workspace/environment come from your modal config or MODAL_ENVIRONMENT.
# Keys come from the environment (OPENAI_API_KEY, EVAL_ANTHROPIC_API_KEY); Harbor resolves the
# task's ${VAR} templates at runtime and persists only the templates.
set -u
TASK=$1; AGENT=$2; MODEL=$3; K=$4; N=${5:-2}
ROOT=$(cd "$(dirname "$0")/.." && pwd)
JOBS=${JOBS_DIR:-$ROOT/jobs}; mkdir -p "$JOBS"
NAME="swapbench-${TASK}__${AGENT}__${MODEL##*/}__$(date -u +%Y%m%d-%H%M%S)"
if [ "$AGENT" = claude-code ]; then
  export ANTHROPIC_API_KEY="$EVAL_ANTHROPIC_API_KEY"; unset ANTHROPIC_BASE_URL
fi
cd "$ROOT/harbor" && harbor run -y -p . -i "$TASK" -a "$AGENT" -m "$MODEL" -e modal \
  --ae 'OPENAI_API_KEY=${OPENAI_API_KEY}' --ae 'ANTHROPIC_API_KEY=${EVAL_ANTHROPIC_API_KEY}' \
  -k "$K" -n "$N" --jobs-dir "$JOBS" --job-name "$NAME" --ek sandbox_timeout_secs=10800 \
  --artifact /app/submission > "$JOBS/$NAME.log" 2>&1
echo "$NAME rc=$?"
