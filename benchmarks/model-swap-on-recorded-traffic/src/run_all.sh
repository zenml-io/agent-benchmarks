#!/bin/bash
# Two candidate batches per use case (the analyzer takes at most 8 candidates); Sonnet 5.5 is the reference in both.
# Run from this benchmark's directory: src/run_all.sh invoice_extraction claims_triage kyc_checks
PY=${KVENV:-.venv}/bin/python
mkdir -p logs
A="sonnet-5.5,opus-5.5,haiku-5.5,gpt-6-luna,gpt-6.1-sol,deepseek-v4.1-flash@provider-a,deepseek-v4-pro@provider-a,glm-5.3@provider-a"
B="sonnet-5.5,glm-5.3-flash@provider-a,gpt-oss-120b@provider-a,qwen3.8-27b@provider-a,minimax-m3@provider-a"
for uc in "$@"; do
  $PY src/swap_calib.py $uc --candidates $A --tag A --cap 25 > logs/swap_${uc}_A.log 2>&1
  $PY src/swap_calib.py $uc --candidates $B --tag B --cap 25 > logs/swap_${uc}_B.log 2>&1
done
