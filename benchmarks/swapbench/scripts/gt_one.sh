#!/bin/bash
# Ground truth for one model on a tau2 retail task:
#   gt_one.sh <tau2-dir> <tau2-env> <out-dir> <model> [splits="train:1 test:3"]
# Optional env: TAU2_DATA_DIR (generated scenarios), USER_LLM (default anthropic/claude-haiku-5-5),
#   CONC (default 12), NUM_TASKS (first N tasks of each split), AGENT_ARGS (default {}), AGENT (tau2 agent name).
set -u
TAU2=$1; ENV=$2; OUT=$3; M=$4; SPLITS=${5:-"train:1 test:3"}
USER_LLM=${USER_LLM:-anthropic/claude-haiku-5-5}
DOMAIN=${DOMAIN:-retail}
CONC=${CONC:-12}; AGENT_ARGS=${AGENT_ARGS:-"{}"}
EXTRA=(); [ -n "${NUM_TASKS:-}" ] && EXTRA=(--num-tasks "$NUM_TASKS"); [ -n "${AGENT:-}" ] && EXTRA+=(--agent "$AGENT")
# Hosted open-model providers: pass M=openai/<model id> with OPENAI_API_BASE / OPENAI_API_KEY set for the provider
# (scripts/provider_runs.sh does this from OPENAI_COMPAT_BASE_URL_<LABEL> / OPENAI_COMPAT_API_KEY_<LABEL>).
TAU2BIN="$ENV/bin/tau2"
case "$DOMAIN" in fintech*|*_gen) USE_X=1;; *) USE_X=;; esac
[ -n "$USE_X" ] && TAU2BIN="$(cd "$(dirname "$0")" && pwd)/tau2x" && export TAU2X_PYTHON="$ENV/bin/python"
export ANTHROPIC_API_KEY="${EVAL_ANTHROPIC_API_KEY:-${ANTHROPIC_API_KEY:-}}"
tag=$(echo "$M" | tr '/' '_'); mkdir -p "$OUT/$tag"
for spec in $SPLITS; do split=${spec%%:*}; k=${spec##*:}
  [ -f "$OUT/$tag/$split.done" ] && continue
  (cd "$TAU2" && yes y | timeout 10800 "$TAU2BIN" run -d "$DOMAIN" --agent-llm "$M" --agent-llm-args "$AGENT_ARGS" \
     --user-llm "$USER_LLM" --user-llm-args '{}' --task-split-name "$split" --num-trials "$k" \
     --max-concurrency "$CONC" "${EXTRA[@]}" --save-to "$OUT/$tag/$split" --log-level ERROR > "$OUT/$tag/$split.log" 2>&1) \
     && touch "$OUT/$tag/$split.done"
  echo "$(date -u +%H:%M) done $M $split" >> "$OUT/progress.log"
done
