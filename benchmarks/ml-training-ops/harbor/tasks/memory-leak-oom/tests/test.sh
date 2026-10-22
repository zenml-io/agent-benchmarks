#!/bin/bash
# Grader entrypoint: Harbor copies tests/ to /tests and runs this after the agent finishes.
# It always writes a reward, and the reward is 1 only if every hidden test ran and passed.
# CPU tasks grade in a fresh container (task.toml: verifier environment_mode = "separate") that holds
# the image's own Python and the agent's /app copied back, so nothing the agent changed outside /app
# (site-packages, /tests, /logs) takes part in grading.
set -u
V=/logs/verifier
mkdir -p "$V"
rm -f "$V/reward.txt" "$V/reward.json"  # a reward file the agent left behind must never count
echo 0 > "$V/reward.txt"
JUNIT="$(mktemp -d)/junit-$RANDOM$RANDOM.xml"
cd "${APP_DIR:-/app}" || exit 0
unset PYTEST_ADDOPTS PYTHONPATH PYTHONSTARTUP PYTHONHOME
export PYTEST_DISABLE_PLUGIN_AUTOLOAD=1
# -P: /app is not put on sys.path, so a pytest.py or conftest-style module there cannot replace the
# test runner; graders that import the agent's code add /app themselves.
python -P -m pytest /tests/test_outputs.py -rA -p no:cacheprovider --noconftest \
  -c /tests/pytest.ini --rootdir /tests --junitxml="$JUNIT"
status=$?
cp "$JUNIT" "$V/junit.xml" 2>/dev/null
if [ "$status" -eq 0 ] && python -I /tests/junit_ok.py "$JUNIT"; then
  echo 1 > "$V/reward.txt"
fi
exit 0
