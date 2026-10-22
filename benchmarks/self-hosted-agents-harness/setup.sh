#!/usr/bin/env bash
# One-time setup for a fresh machine or cloud session. Credentials come from the
# environment (MODAL_TOKEN_ID / MODAL_TOKEN_SECRET), never from this repo.
set -euo pipefail
command -v uv >/dev/null || curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH="$HOME/.local/bin:$PATH"
uv tool install 'modal[api-proxy-support]==1.6.1'   # extra needed behind an HTTP proxy (cloud sessions)
uv tool install 'harbor[modal]==0.24.0' --with 'modal[api-proxy-support]'   # [modal] is required for `-e modal` sandboxes
if [[ -z "${MODAL_TOKEN_ID:-}" || -z "${MODAL_TOKEN_SECRET:-}" ]]; then
  echo "Set MODAL_TOKEN_ID and MODAL_TOKEN_SECRET (your Modal workspace) before running." >&2
  exit 1
fi
ENV_NAME="${MODAL_ENVIRONMENT:-main}"
modal environment list | grep -q "$ENV_NAME" && echo "Modal OK: environment $ENV_NAME found."
cd "$(dirname "$0")" && python3 test_experiment.py
