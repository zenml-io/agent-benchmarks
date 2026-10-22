#!/usr/bin/env bash
# Verifier entrypoint. Always writes /logs/verifier/reward.json; clears any reward file left before grading.
set -uo pipefail
mkdir -p /logs/verifier
rm -f /logs/verifier/reward.json /logs/verifier/reward.txt /logs/verifier/grading.json
python3 -I /tests/grade.py --case /tests/case.json --out-dir /logs/verifier 2>&1 | tee /logs/verifier/grade.log
[ -s /logs/verifier/reward.json ] || echo '{"reward": 0}' > /logs/verifier/reward.json
exit 0
