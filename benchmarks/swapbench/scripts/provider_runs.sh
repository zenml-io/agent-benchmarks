#!/bin/bash
# Same open model on several hosted providers, the full benchmark split layout of results/runs/ (visible x1, hidden x2, pool x1).
#   [DOMAIN=fintech|retail] [SPLITS=...] provider_runs.sh <tau2-dir> <tau2-env> <data-dir> <out-dir> <model-key>...
# <data-dir>: the fintech data dir, or for retail a TAU2_DATA_DIR holding tau2/domains/retail.
# Model keys: deepseek-v4.1-flash, gpt-oss-120b, qwen3.8-27b, qwen3.8-2.4t (any key present in the provider config).
#
# Providers are configured, not named: PROVIDERS_CONFIG (default ./providers.json, see providers.example.json) maps a
# neutral label (provider-a, provider-b, ...) to the model ID each provider serves for each key. Each label's endpoint
# comes from OPENAI_COMPAT_BASE_URL_<LABEL> and OPENAI_COMPAT_API_KEY_<LABEL> (label upper-cased, '-' -> '_', e.g.
# OPENAI_COMPAT_BASE_URL_PROVIDER_A). Every provider is called through litellm's OpenAI-compatible route
# (openai/<model id>, endpoint and key from OPENAI_API_BASE / OPENAI_API_KEY for that job only, so the key never lands in
# the saved results). Outputs: <out-dir>/<label>/<model tag>/<split>/results.json.
set -u
TAU2=$1; ENV=$2; DATA=$3; OUT=$4; shift 4
HERE=$(cd "$(dirname "$0")" && pwd)
CONFIG=${PROVIDERS_CONFIG:-$HERE/../providers.json}
DOMAIN=${DOMAIN:-fintech}; SPLITS=${SPLITS:-"test:2 train:1 pool:1"}
for key in "$@"; do
  while IFS=$'\t' read -r label model_id; do
    var=$(echo "$label" | tr 'a-z-' 'A-Z_')
    base_var="OPENAI_COMPAT_BASE_URL_$var"; key_var="OPENAI_COMPAT_API_KEY_$var"
    if [ -z "${!base_var:-}" ] || [ -z "${!key_var:-}" ]; then echo "skip $label: $base_var / $key_var not set" >&2; continue; fi
    if [ "$DOMAIN" = retail ]; then export TAU2_DATA_DIR="$DATA"; else export SWAPBENCH_FINTECH_DIR="$DATA"; fi
    mkdir -p "$OUT/$label"
    OPENAI_API_BASE="${!base_var}" OPENAI_API_KEY="${!key_var}" DOMAIN=$DOMAIN CONC=${CONC:-8} \
      "$HERE/gt_one.sh" "$TAU2" "$ENV" "$OUT/$label" "openai/$model_id" "$SPLITS" &
  done < <(python3 -c 'import json,sys; c=json.load(open(sys.argv[1])); [print(f"{l}\t{m[sys.argv[2]]}") for l, m in c.items() if sys.argv[2] in m]' "$CONFIG" "$key")
done
wait
