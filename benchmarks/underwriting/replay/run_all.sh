#!/bin/bash
# SUFFIX (optional) tags a rerun, e.g. SUFFIX=2 writes replay/out/underwritingA2.
# Two candidate batches (the analyzer takes at most 8 candidates); Sonnet 5.5 is the reference in both.
# KVENV: a virtualenv with kitaru and the kitaru-model-swap plugin installed (see RERUN.md, step-level screen).
cd "$(dirname "$0")/.."
mkdir -p replay/logs
PY=${KVENV:?set KVENV to the Kitaru virtualenv}/bin/python
A="sonnet-5.5,opus-5.5,haiku-5.5,gpt-6-luna,gpt-6.1-sol,deepseek-v4.1-flash@provider-a,deepseek-v4-pro@provider-a,glm-5.3@provider-a"
B="sonnet-5.5,glm-5.3-flash@provider-a,gpt-oss-120b@provider-a,qwen3.8-27b@provider-a,minimax-m3@provider-a"
$PY replay/swap_underwriting.py underwriting --responses --candidates $A --tag A${SUFFIX} --cap 25 > replay/logs/swap_A${SUFFIX}.log 2>&1
$PY replay/swap_underwriting.py underwriting --responses --candidates $B --tag B${SUFFIX} --cap 25 > replay/logs/swap_B${SUFFIX}.log 2>&1
echo done >> replay/logs/swap_B${SUFFIX}.log
