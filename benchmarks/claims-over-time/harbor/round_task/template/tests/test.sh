#!/bin/bash
# Checks that the candidate is a loadable claims agent package with a CHANGE.md, and copies it out of the trial:
# candidate.tgz, CHANGE.md, reruns.jsonl, check.json and reward.txt land in /logs/verifier (see /claims/bin/verify.py).
# Accuracy is not scored here; the coordinator's approval rule does that on the host.
LOG_DIR="/logs/verifier"
mkdir -p "${LOG_DIR}"
rm -f "${LOG_DIR}"/reward.*
/opt/claims-venv/bin/python /claims/bin/verify.py --out "${LOG_DIR}" || echo 0 > "${LOG_DIR}/reward.txt"
cat "${LOG_DIR}/reward.txt"
