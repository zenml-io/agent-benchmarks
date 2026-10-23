"""Task telecom-test-NN must be the task the original run recorded as case NN (no tau2 checkout needed).

    uv run --with pytest pytest harbor/tests/test_numbering.py

Results are compared with the original run case by case, and the Harbor agent tells Kitaru "Case NN",
which a Kitaru replay with the original harness resolves by position in tau2's test split. A task under
the wrong number would be compared with, or replayed as, a different task without any error.
"""

import json
import re
from pathlib import Path

HARBOR = Path(__file__).resolve().parents[1]
ORIGINAL_CASES = HARBOR.parent / "results" / "runs" / "replay" / "baseline.jsonl"


def test_task_numbers_are_the_original_case_numbers() -> None:
    recorded = {}
    for line in ORIGINAL_CASES.read_text().splitlines():
        row = json.loads(line)
        recorded[row["case"]] = row["tau2"]["task_id"]
    index = json.loads((HARBOR / "tasks" / "index.json").read_text())["tasks"]

    assert len(recorded) == len(index) == 40
    for entry in index:
        case = entry["case"]
        assert entry["task"] == f"telecom-test-{case:02d}"
        assert entry["tau2_task_id"] == recorded[case], entry["task"]
        toml = (HARBOR / "tasks" / entry["task"] / "task.toml").read_text()
        assert re.search(rf"^case = {case}$", toml, re.MULTILINE), entry["task"]
        assert f"source_task_id = {json.dumps(recorded[case])}" in toml, entry["task"]
        oracle = json.loads((HARBOR / "tasks" / entry["task"] / "solution" / "oracle.json").read_text())
        assert oracle["task_id"] == recorded[case], entry["task"]
