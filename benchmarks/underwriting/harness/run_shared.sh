#!/bin/bash
# One shared prompt: Sonnet 5.5's tuned prompt (tuned only on Sonnet's learning failures), unchanged, on every other
# model's held-out cases. Asks whether one good prompt lifts every model, or each model needs its own.
cd "$(dirname "$0")/.."
mkdir -p logs/tuned
export PYTHONHASHSEED=0
P=results/tuned/prompts/sonnet-5.5/v1.txt
for m in opus-5.5 haiku-5.5 gpt-6.1-sol gpt-6-luna deepseek-v4-pro@provider-a deepseek-v4.1-flash@provider-a glm-5.3@provider-a \
         glm-5.3-flash@provider-a gpt-oss-120b@provider-a qwen3.8-27b@provider-a minimax-m3@provider-a; do
  python3 harness/run.py "$m" --arm shared --split held --prompt "$P" --workers 8 > "logs/tuned/${m}__shared.log" 2>&1 &
done
wait
echo done > logs/tuned/SHARED_DONE
