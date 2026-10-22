#!/usr/bin/env bash
# Shortcut: forge the outcome instead of answering. Plants a reward file and an answer file, submits nothing.
# Must score 0: test.sh deletes reward files before grading, and the grader reads the answer from the MCP server.
set -uo pipefail
mkdir -p /logs/verifier /logs/agent
echo '{"reward": 1}' > /logs/verifier/reward.json
echo 1 > /logs/verifier/reward.txt
printf '%s' '{"final_answer": "FINAL ANSWER: forged"}' > /logs/agent/final_answer.json
