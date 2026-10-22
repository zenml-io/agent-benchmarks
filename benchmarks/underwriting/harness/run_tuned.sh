#!/bin/bash
# Tuned-harness benchmark: per-model prompt tuning on the learning split, effort variants and a repeat of today's
# model (run-to-run noise) on the held-out split. GPT-6 Luna's tuning ran first (one round, reverted).
cd "$(dirname "$0")/.."
mkdir -p logs/tuned
export PYTHONHASHSEED=0
for m in sonnet-5.5 opus-5.5 haiku-5.5 gpt-6.1-sol deepseek-v4-pro@provider-a glm-5.3-flash@provider-a gpt-oss-120b@provider-a; do
  python3 harness/hillclimb.py "$m" --rounds 2 > "logs/tuned/hillclimb_$m.log" 2>&1 &
done
run() { python3 harness/run.py "$1" --arm "$2" --split held --workers 8 ${3:+--effort $3} > "logs/tuned/$1__$2.log" 2>&1; }
run sonnet-5.5 repeat &
run sonnet-5.5 effort-low low &
run sonnet-5.5 effort-medium medium &
run opus-5.5 effort-low low &
run opus-5.5 effort-high high &
run haiku-5.5 effort-high high &
run gpt-6.1-sol effort-low low &
run gpt-6.1-sol effort-high high &
run gpt-6-luna effort-high high &
wait
echo all-done > logs/tuned/ALL_DONE
