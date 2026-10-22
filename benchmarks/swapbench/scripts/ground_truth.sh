#!/bin/bash
# Day-1 ground truth for task retail-refunds: incumbent and candidate models on the visible
# (tau2 train) and hidden (tau2 test) splits. Usage: ground_truth.sh <tau2-dir> <tau2-python-env> <out-dir>
# Reads OPENAI_API_KEY and EVAL_ANTHROPIC_API_KEY from the environment; never writes keys anywhere.
set -u
TAU2=$1; ENV=$2; OUT=$3
USER_LLM=anthropic/claude-haiku-5-5
export ANTHROPIC_API_KEY="${EVAL_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-}}"
run() {  # model split trials
  local tag=$(echo "$1" | tr '/' '_')
  [ -f "$OUT/$tag/$2/results.json" ] && return
  mkdir -p "$OUT/$tag"
  (cd "$TAU2" && timeout 7200 "$ENV/bin/tau2" run -d retail --agent-llm "$1" --agent-llm-args '{}' \
     --user-llm $USER_LLM --user-llm-args '{}' --task-split-name "$2" --num-trials "$3" \
     --max-concurrency 8 --save-to "$OUT/$tag/$2" --log-level ERROR > "$OUT/$tag/$2.log" 2>&1)
  echo "$(date -u +%H:%M) done $1 $2" >> "$OUT/progress.log"
}
model() { run "$1" train 1; run "$1" test 3; }
model gpt-5-2025-08-07 &
model gpt-6-luna &
model anthropic/claude-haiku-5-5 &
wait
model gpt-5-mini-2025-08-07 &
model gpt-5.4-nano &
model gpt-4.1-mini-2025-04-14 &
wait
echo GTDONE >> "$OUT/progress.log"
