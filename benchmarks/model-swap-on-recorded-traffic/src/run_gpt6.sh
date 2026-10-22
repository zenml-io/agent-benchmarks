#!/bin/bash
# GPT-6 Luna and GPT-6.1 Sol through the Responses API (reasoning on, as in their full runs), same 250 sampled calls.
# Run from this benchmark's directory: src/run_gpt6.sh invoice_extraction claims_triage kyc_checks
PY=${KVENV:-.venv}/bin/python
mkdir -p logs
for uc in "$@"; do
  $PY src/swap_calib.py $uc --responses --candidates gpt-6-luna,gpt-6.1-sol --tag G --cap 10 > logs/swap_${uc}_G.log 2>&1
done
