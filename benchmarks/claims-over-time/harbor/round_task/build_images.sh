#!/usr/bin/env bash
# Build the images the round tasks start from (they stay in the local Docker daemon):
#   claims-over-time-round-codex:latest   Node + the Codex CLI + uv (harbor/codex/Dockerfile), plus the shared tools
#                                         and `claims-rerun`
#   $PRO_ROUND_IMAGE                      the ZenML Pro agent's trial image ($PRO_BASE_IMAGE), plus the shared tools and GEPA
#                                         (default tag claims-over-time-round-pro:latest); only when PRO_BASE_IMAGE is set
#
#   DOCKER_CONTEXT=orbstack [PRO_BASE_IMAGE=<image>] harbor/round_task/build_images.sh
#
# The shared tools (tools.Dockerfile) are the claims agent's locked Python environment and the precedent library from
# $CLAIMS_WORK_DIR/precedents.jsonl (default work/). The pro round image runs as its base image's user.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH="$(cd "$HERE/../.." && pwd)"
WORK="${CLAIMS_WORK_DIR:-$BENCH/work}"
PRO_ROUND_IMAGE="${PRO_ROUND_IMAGE:-claims-over-time-round-pro:latest}"

CTX="$(mktemp -d)"
trap 'rm -rf "$CTX"' EXIT
uv export --project "$BENCH" --frozen --extra agent --no-hashes --no-emit-project > "$CTX/requirements.txt"
cp "$WORK/precedents.jsonl" "$CTX/precedents.jsonl"
SHA="$(shasum -a 256 "$CTX/precedents.jsonl" | cut -d' ' -f1)"

echo "docker context: ${DOCKER_CONTEXT:-default}; precedents sha256 $SHA"
docker build -t claims-over-time-codex-base:latest "$BENCH/harbor/codex"
docker build -f "$HERE/tools.Dockerfile" --build-arg BASE=claims-over-time-codex-base:latest \
  --build-arg AGENT_USER=root --build-arg RERUN_TOOL=1 --build-arg "PRECEDENTS_SHA256=$SHA" \
  -t claims-over-time-round-codex:latest "$CTX"
echo "built claims-over-time-round-codex:latest"
if [ -z "${PRO_BASE_IMAGE:-}" ]; then
  echo "PRO_BASE_IMAGE is not set: the pro round image was not built (the pro arm needs the ZenML Pro agent bundle)"
  exit 0
fi
PRO_USER="$(docker image inspect -f '{{.Config.User}}' "$PRO_BASE_IMAGE")"
docker build -f "$HERE/tools.Dockerfile" --build-arg "BASE=$PRO_BASE_IMAGE" \
  --build-arg "AGENT_USER=${PRO_USER:-root}" --build-arg RERUN_TOOL=0 --build-arg GEPA_TOOLS=1 \
  --build-arg "PRECEDENTS_SHA256=$SHA" \
  -t "$PRO_ROUND_IMAGE" "$CTX"
echo "built $PRO_ROUND_IMAGE on $PRO_BASE_IMAGE (user ${PRO_USER:-root})"
