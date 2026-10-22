"""Fast grader and packaging tests (no containers, no torch, seconds):

    uv run --with pytest --with pyyaml --with 'harbor==0.24.0' pytest -q harbor/tests

- the shared test.sh: always writes a reward, removes a reward file the agent left, and gives 0 when
  pytest exits 0 without a passing JUnit report (a shadowed or short-circuited test run);
- junit_ok.py on passing, failing, skipped and empty reports;
- every built task: Harbor's own TaskConfig loads it; the verifier runs in a separate container that gets
  /app back; it has the shared grader files, the grade-forgery shortcut, at least one task-specific
  shortcut; built tasks match a fresh build;
- the answer-file graders (diagnosis and Kubernetes tasks), run on the reference, the empty answer, each
  shortcut and each alternative, which needs only pytest and pyyaml.

The code-fixing graders need the task images' packages; scripts/check_local.py runs them.
"""
import filecmp
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

import pytest

HARBOR = Path(__file__).resolve().parent.parent
TASKS = HARBOR / "tasks"
SHARED = HARBOR / "shared"
ALL = sorted(p.name for p in TASKS.iterdir() if p.is_dir())
ANSWER_TASKS = ["corrupt-shard", "straggler-diagnosis", "two-stragglers", "k8s-unschedulable", "k8s-quota-zone"]


def run_test_sh(tmp, test_outputs, app_files=None, stale_reward=None):
    """Run a copy of shared/test.sh with /tests, /logs/verifier and /app pointed into tmp."""
    tests, logs, app = tmp / "tests", tmp / "logs" / "verifier", tmp / "app"
    for d in (tests, logs, app):
        d.mkdir(parents=True, exist_ok=True)
    for f in ("junit_ok.py", "pytest.ini"):
        shutil.copy(SHARED / f, tests / f)
    (tests / "test_outputs.py").write_text(test_outputs)
    for name, text in (app_files or {}).items():
        (app / name).write_text(text)
    if stale_reward is not None:
        (logs / "reward.json").write_text(stale_reward)
    script = re.sub(r"/tests\b", str(tests), (SHARED / "test.sh").read_text().replace("/logs/verifier", str(logs)))
    (tmp / "test.sh").write_text(script)
    env = {**os.environ, "APP_DIR": str(app), "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"}
    r = subprocess.run(["bash", str(tmp / "test.sh")], env=env, capture_output=True, text=True, timeout=120)
    assert r.returncode == 0
    return (logs / "reward.txt").read_text().strip(), logs


def test_test_sh_passing_tests_score_1(tmp_path):
    reward, logs = run_test_sh(tmp_path, "def test_ok():\n    assert True\n")
    assert reward == "1" and not (logs / "reward.json").exists()


def test_test_sh_failing_tests_score_0_and_stale_reward_json_is_removed(tmp_path):
    reward, logs = run_test_sh(tmp_path, "def test_bad():\n    assert False\n", stale_reward='{"reward": 1.0}')
    assert reward == "0" and not (logs / "reward.json").exists()


def test_test_sh_ignores_a_pytest_shadow_in_app(tmp_path):
    """An agent's /app/pytest.py that exits 0 must not replace the test run (python -P)."""
    reward, _ = run_test_sh(tmp_path, "def test_bad():\n    assert False\n",
                            app_files={"pytest.py": "import sys\nsys.exit(0)\n"})
    assert reward == "0"


def test_test_sh_ignores_a_conftest_in_app(tmp_path):
    hook = "def pytest_sessionfinish(session, exitstatus):\n    session.exitstatus = 0\n"
    reward, _ = run_test_sh(tmp_path, "def test_bad():\n    assert False\n", app_files={"conftest.py": hook})
    assert reward == "0"


def test_test_sh_scores_0_when_the_test_process_exits_0_early(tmp_path):
    """Agent code imported by a grader that calls os._exit(0) ends pytest with status 0 and no report."""
    reward, _ = run_test_sh(tmp_path, "import os\nos._exit(0)\n\ndef test_never_runs():\n    pass\n")
    assert reward == "0"


def test_test_sh_scores_0_when_a_test_is_skipped(tmp_path):
    reward, _ = run_test_sh(tmp_path, "import pytest\n\ndef test_skipped():\n    pytest.skip('agent code skipped me')\n")
    assert reward == "0"


@pytest.mark.parametrize("xml,ok", [
    ('<testsuites><testsuite><testcase name="a"/><testcase name="b"/></testsuite></testsuites>', True),
    ('<testsuites><testsuite><testcase name="a"><failure/></testcase></testsuite></testsuites>', False),
    ('<testsuites><testsuite><testcase name="a"><error/></testcase></testsuite></testsuites>', False),
    ('<testsuites><testsuite><testcase name="a"><skipped/></testcase></testsuite></testsuites>', False),
    ('<testsuites><testsuite></testsuite></testsuites>', False),
    ("not xml", False),
])
def test_junit_ok(tmp_path, xml, ok):
    p = tmp_path / "j.xml"
    p.write_text(xml)
    assert (subprocess.run([sys.executable, "-I", str(SHARED / "junit_ok.py"), str(p)]).returncode == 0) == ok


@pytest.mark.parametrize("task", ALL)
def test_task_loads_in_harbor_and_grades_separately(task):
    from harbor.models.task.config import TaskConfig
    cfg = TaskConfig.model_validate_toml((TASKS / task / "task.toml").read_text())
    assert cfg.task.name == f"zenml/mlops-{task}"
    assert cfg.verifier.environment_mode.value == "separate"
    assert [a if isinstance(a, str) else a.source for a in cfg.artifacts] == ["/app"]
    assert cfg.agent.timeout_sec and cfg.environment.cpus and cfg.environment.memory_mb
    for f in ("test.sh", "junit_ok.py", "pytest.ini"):
        assert filecmp.cmp(TASKS / task / "tests" / f, SHARED / f, shallow=False), f
    shortcuts = sorted(p.name for p in (TASKS / task / "tests" / "shortcuts").glob("*.sh"))
    assert "forge_grade.sh" in shortcuts and len(shortcuts) >= 2, shortcuts
    assert (TASKS / task / "solution" / "solve.sh").exists() and (TASKS / task / "environment" / "Dockerfile").exists()


def test_nothing_the_grader_knows_is_in_the_agent_image():
    """The Docker build context (environment/) holds no grader file, answer key or reference fix."""
    for task in ALL:
        env = TASKS / task / "environment"
        names = {p.name for p in env.rglob("*")}
        assert not names & {"test_outputs.py", "solve.sh", "junit_ok.py", "golden.json", "code_sha.json"}, task
        assert not (env / "solution").exists() and not (env / "tests").exists()


def test_built_tasks_match_a_fresh_build(tmp_path):
    """harbor/tasks/ is what build.py writes (rebuild after changing sources or overlays)."""
    spec = __import__("importlib.util").util.spec_from_file_location("hb", HARBOR / "build.py")
    hb = __import__("importlib.util").util.module_from_spec(spec)
    spec.loader.exec_module(hb)
    hb.OUT = tmp_path
    hard = hb.load_hard_builder()
    for task in ALL:
        hb.write(task, hard)
        cmp = filecmp.dircmp(tmp_path / task, TASKS / task, ignore=["__pycache__"])
        diffs = []

        def walk(c, rel=""):
            diffs.extend(f"{rel}{n}" for n in c.left_only + c.right_only + c.diff_files)
            for name, sub in c.subdirs.items():
                walk(sub, f"{rel}{name}/")
        walk(cmp)
        assert not diffs, f"{task}: harbor/tasks differs from a fresh build in {diffs[:5]}"


def answer_variants(task):
    d = TASKS / task
    out = [("oracle", d / "solution" / "solve.sh", True), ("empty", None, False)]
    out += [(p.name, p, False) for p in sorted((d / "tests" / "shortcuts").glob("*.sh")) if p.name != "forge_grade.sh"]
    out += [(p.name, p, True) for p in sorted((d / "solution" / "alternatives").glob("*.sh"))]
    return out


@pytest.mark.parametrize("task,label,script,want", [(t, *v) for t in ANSWER_TASKS for v in answer_variants(t)],
                         ids=lambda v: v if isinstance(v, str) else None)
def test_answer_graders(task, label, script, want):
    d = TASKS / task
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        app, sol, tests = tmp / "app", tmp / "solution", tmp / "tests"
        shutil.copytree(d / "environment" / "app", app)
        shutil.copytree(d / "solution", sol)
        shutil.copytree(d / "tests", tests)
        gen = d / "environment" / "gen" / "gen.sh"
        if gen.exists():
            pytest.importorskip("numpy")
            subprocess.run(["bash", str(gen)], cwd=app, env={**os.environ, "GEN_DIR": str(gen.parent),
                           "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"}, check=True, capture_output=True)
        if script is not None:
            text = script.read_text().replace("/solution/", f"{sol}/")
            text = re.sub(r"/app\b", str(app), text)
            (tmp / "run.sh").write_text(text)
            subprocess.run(["bash", str(tmp / "run.sh")], cwd=app, check=True, capture_output=True,
                           env={**os.environ, "APP_DIR": str(app), "PATH": f"{Path(sys.executable).parent}:{os.environ['PATH']}"})
        r = subprocess.run([sys.executable, "-P", "-m", "pytest", "-q", str(tests / "test_outputs.py"), "-p", "no:cacheprovider",
                            "--noconftest", "-c", str(tests / "pytest.ini"), "--rootdir", str(tests)],
                           cwd=app, env={**os.environ, "APP_DIR": str(app)}, capture_output=True, text=True)
        assert (r.returncode == 0) == want, r.stdout[-1500:]
