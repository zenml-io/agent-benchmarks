#!/bin/bash
# Fetch tau2-bench (MIT, Sierra Research) at the commit every SwapBench run used, into third_party/tau2-bench.
# SwapBench installs it editable from there (pyproject.toml), and the retail world (data/tau2/domains/retail)
# is read from that checkout. Idempotent.
set -euo pipefail
COMMIT=dd8757d4c8791dad7b3cdaf02a105a3d5f9d86bd
HERE=$(cd "$(dirname "$0")/.." && pwd)
DEST="$HERE/third_party/tau2-bench"
if [ -d "$DEST/.git" ] && [ "$(git -C "$DEST" rev-parse HEAD)" = "$COMMIT" ]; then
  echo "tau2-bench already at $COMMIT"; exit 0
fi
mkdir -p "$DEST"
git -C "$DEST" init -q
git -C "$DEST" remote add origin https://github.com/sierra-research/tau2-bench 2>/dev/null || true
git -C "$DEST" fetch -q --depth 1 origin "$COMMIT"
git -C "$DEST" checkout -q FETCH_HEAD
echo "tau2-bench at $(git -C "$DEST" rev-parse HEAD)"
