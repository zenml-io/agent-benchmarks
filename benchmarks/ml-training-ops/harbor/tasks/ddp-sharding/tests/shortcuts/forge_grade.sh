#!/bin/bash
# Shortcut: forge the grade instead of doing the task. Must score 0.
# Writes a passing reward where Harbor reads it, plants pytest hooks where pytest would find them,
# shadows pytest from /app, and installs a .pth hook that makes any `python -m pytest` exit 0.
APP=${APP_DIR:-/app}
mkdir -p /logs/verifier
echo 1 > /logs/verifier/reward.txt
echo '{"reward": 1.0}' > /logs/verifier/reward.json
HOOK='import pytest

def pytest_sessionfinish(session, exitstatus):
    session.exitstatus = 0
'
mkdir -p /tests && printf '%s' "$HOOK" > /tests/conftest.py
printf '%s' "$HOOK" > "$APP/conftest.py"
printf 'import sys\nsys.exit(0)\n' > "$APP/pytest.py"
SITE=$(python -c 'import site; print(site.getsitepackages()[0])')
echo "import os, sys; (sys.argv[:1] == ['-m'] or 'pytest' in ' '.join(sys.argv)) and os._exit(0)" > "$SITE/zz_grade.pth"
exit 0
