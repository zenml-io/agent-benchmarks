"""Grader tests for the 40 generated tasks, run offline with tau2's own evaluator (no model calls).

    TAU2_BENCH_ROOT=/path/to/tau2-bench uv run --extra harbor-dev pytest harbor/tests/test_tasks.py

For every task: the reference state scores 1, the alternative path (rechecks) scores 1, every shortcut
scores 0, and a run that never started (nop: no state file, or the sidecar's untouched state) scores 0.
The grader runs in-process for speed (the same functions test.sh reaches); three tasks also go through
the evaluate.py command line, and test.sh is checked for the reward-file rules. TAU2_BENCH_ROOT must be a
tau2-bench checkout at the commit in task.toml (RERUN.md section 3 has a sparse checkout command).
"""

import importlib.util
import json
import os
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import pytest

sys.dont_write_bytecode = True  # the tests import task files; keep __pycache__ out of the task folders

HARBOR = Path(__file__).resolve().parents[1]
TASK_DIRS = sorted(p for p in (HARBOR / "tasks").iterdir() if (p / "task.toml").exists())
TAU2_ROOT = os.environ.get("TAU2_BENCH_ROOT")
pytestmark = pytest.mark.skipif(not TAU2_ROOT, reason="set TAU2_BENCH_ROOT to a tau2-bench checkout")


def load(path: Path, name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def modules() -> tuple[ModuleType, ModuleType]:
    evaluate = load(TASK_DIRS[0] / "tests" / "evaluate.py", "task_evaluate")
    build_state = load(HARBOR / "task_files" / "build_state.py", "task_build_state")
    return evaluate, build_state


def grade(evaluate: ModuleType, task: Path, state: dict) -> dict:
    config = json.loads((task / "tests" / "config.json").read_text())
    return evaluate._run_evaluation(config=config, runtime_state=state, skip_nl_assertion=False)


def test_tasks_share_grader_and_state_builder() -> None:
    assert len(TASK_DIRS) == 40
    for name in ("tests/evaluate.py", "tests/test.sh", "solution/build_state.py",
                 "environment/runtime-server/server.py"):
        assert len({(t / name).read_text() for t in TASK_DIRS}) == 1, name
    assert (TASK_DIRS[0] / "solution/build_state.py").read_text() == (HARBOR / "task_files/build_state.py").read_text()


@pytest.mark.parametrize("task", TASK_DIRS, ids=lambda p: p.name)
def test_reference_alternative_and_shortcuts(task: Path, tmp_path: Path, modules) -> None:
    evaluate, build_state = modules
    oracle = json.loads((task / "solution" / "oracle.json").read_text())
    shortcuts = sorted(p.stem for p in (task / "tests" / "shortcuts").glob("*.sh"))
    for mode, expected in [("reference", 1.0), ("rechecks", 1.0)] + [(s, 0.0) for s in shortcuts]:
        build_state.STATE_PATH = tmp_path / f"{mode}.json"
        build_state.build(mode, oracle)
        result = grade(evaluate, task, json.loads(build_state.STATE_PATH.read_text()))
        assert result["used_tau2_evaluator"], f"{task.name} {mode}: {result}"
        assert result["reward"] == expected, f"{task.name} {mode}: {result['status']} {result['reward_info']}"


@pytest.mark.parametrize("task", TASK_DIRS, ids=lambda p: p.name)
def test_run_that_never_started_scores_0(task: Path, modules) -> None:
    evaluate, _ = modules
    untouched = {"domain": "telecom", "termination_reason": None, "messages": []}  # sidecar state at start-up
    result = grade(evaluate, task, untouched)
    assert result["reward"] == 0.0 and result["reward_info"]["info"]["tau2_evaluation"] is False


@pytest.mark.parametrize("task", TASK_DIRS[:3], ids=lambda p: p.name)
def test_command_line_grader(task: Path, tmp_path: Path) -> None:
    env = dict(os.environ, TAU3_RUNTIME_STATE_PATH=str(tmp_path / "state.json"))
    subprocess.run([sys.executable, str(task / "solution" / "build_state.py"), "reference"], env=env, check=True,
                   capture_output=True)
    for state, expected, status in ((tmp_path / "state.json", 1.0, "passed"),
                                    (tmp_path / "missing.json", 0.0, "missing_runtime_log")):
        subprocess.run([sys.executable, str(task / "tests" / "evaluate.py"), "--config", str(task / "tests/config.json"),
                        "--runtime-log", str(state), "--reward", str(tmp_path / "reward.txt"),
                        "--result", str(tmp_path / "result.json")], check=True, capture_output=True)
        assert float((tmp_path / "reward.txt").read_text()) == expected
        assert json.loads((tmp_path / "result.json").read_text())["status"] == status


def test_test_sh_removes_planted_reward_and_always_writes_one(tmp_path: Path) -> None:
    task = TASK_DIRS[0]
    logs, tests = tmp_path / "logs", tmp_path / "tests"
    (logs / "verifier").mkdir(parents=True)
    (logs / "agent").mkdir()
    tests.mkdir()
    script = (task / "tests" / "test.sh").read_text().replace("/logs/", f"{logs}/").replace("/tests/", f"{tests}/")
    (tests / "test.sh").write_text(script)
    (tests / "evaluate.py").write_text("raise SystemExit(3)\n")  # a grader that crashes before writing
    (tests / "config.json").write_text("{}")
    (logs / "verifier" / "reward.json").write_text('{"reward": 1}')  # planted by an agent
    (logs / "verifier" / "reward.txt").write_text("1")
    env = dict(os.environ, TAU2_BENCH_ROOT=str(tmp_path))
    subprocess.run(["bash", str(tests / "test.sh")], env=env, check=True, capture_output=True)
    assert not (logs / "verifier" / "reward.json").exists()
    assert (logs / "verifier" / "reward.txt").read_text().strip() == "0"
