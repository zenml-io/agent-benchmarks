"""
Grader tests without containers: run each built task's hidden tests locally against the untouched code
(nop, must score 0), the reference solution (must score 1), every shortcut in tests/shortcuts/ (0)
and every alternative in solution/alternatives/ (1).

    python harbor/scripts/check_local.py nan-loss eval-mode          # some tasks
    python harbor/scripts/check_local.py --all                       # every CPU task (about 2 hours on 4 CPUs)
    python harbor/scripts/check_local.py corrupt-shard --only shortcuts/   # variants whose name contains this

Needs the task images' packages in the running Python (`uv sync --group taskcheck` in the benchmark
folder). Paths: scripts and app files written for /app and /solution are pointed at temporary copies.
forge_grade.sh is skipped here (it writes into the running Python's site-packages); it runs on Modal
with the other Harbor checks (scripts/verify_tasks.py). The torchtitan tasks need GPUs and are skipped.
Exit code 1 if any variant scores other than expected.
"""
import argparse
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HARBOR = Path(__file__).resolve().parent.parent
TASKS = HARBOR / "tasks"
GPU_TASKS = {"titan-fork-drift", "titan-silent-divergence"}
LOCAL_SKIP = {"forge_grade.sh"}


def point_at(text, app, sol, tests):
    text = text.replace("/solution/", f"{sol}/")
    text = text.replace("/tests/", f"{tests}/")
    return re.sub(r"/app\b", str(app), text)


def variants(task):
    d = TASKS / task
    out = [("nop", None, 0), ("oracle", d / "solution" / "solve.sh", 1)]
    out += [(f"shortcuts/{p.name}", p, 0) for p in sorted((d / "tests" / "shortcuts").glob("*.sh")) if p.name not in LOCAL_SKIP]
    out += [(f"alternatives/{p.name}", p, 1) for p in sorted((d / "solution" / "alternatives").glob("*.sh"))]
    return out


def original_test(task):
    """The hidden test the original runs were graded with."""
    v1 = HARBOR.parent / "tasks" / "mlops_tasks" / task / "tests" / "test_outputs.py"
    return v1 if v1.exists() else HARBOR.parent / "tasks" / "mlops_hard" / "src" / task / "tests" / "test_outputs.py"


def grade(task, script, python, verbose, original=False):
    d = TASKS / task
    tmp = Path(tempfile.mkdtemp(prefix=f"{task}-"))
    app, sol, tests = tmp / "app", tmp / "solution", tmp / "tests"
    shutil.copytree(d / "environment" / "app", app)
    shutil.copytree(d / "solution", sol)
    shutil.copytree(d / "tests", tests)
    if original:
        shutil.copy(original_test(task), tests / "test_outputs.py")
    env = {**os.environ, "APP_DIR": str(app), "PATH": str(Path(python).parent) + ":" + os.environ["PATH"]}
    for f in app.rglob("*"):  # the app's code writes to /app paths (v1 tasks)
        if f.is_file() and f.suffix in (".py", ".sh", ".md", ".yaml", ".txt"):
            try:
                f.write_text(point_at(f.read_text(), app, sol, tests))
            except UnicodeDecodeError:
                pass
    for f in tests.rglob("*.py"):
        f.write_text(point_at(f.read_text(), app, sol, tests))
    gen = d / "environment" / "gen" / "gen.sh"
    if gen.exists():
        subprocess.run(["bash", str(gen)], cwd=app, env={**env, "GEN_DIR": str(gen.parent)}, check=True,
                       capture_output=True)
    if script is not None:
        s = tmp / "run.sh"
        s.write_text(point_at(script.read_text(), app, sol, tests))
        r = subprocess.run(["bash", str(s)], cwd=app, env=env, capture_output=True, text=True, timeout=3600)
        if r.returncode != 0:
            return 0.0, tmp, f"script failed (exit {r.returncode}): {r.stderr[-1500:]}"
    junit = tmp / "junit.xml"
    cmd = [python, "-P", "-m", "pytest", str(tests / "test_outputs.py"), "-q", "-p", "no:cacheprovider", "--noconftest",
           "-c", str(tests / "pytest.ini"), "--rootdir", str(tests), f"--junitxml={junit}"]
    r = subprocess.run(cmd, cwd=app, env={**env, "PYTEST_DISABLE_PLUGIN_AUTOLOAD": "1"}, capture_output=True,
                       text=True, timeout=7200)
    ok = r.returncode == 0 and subprocess.run([python, "-I", str(tests / "junit_ok.py"), str(junit)],
                                              capture_output=True).returncode == 0
    tail = [line for line in r.stdout.splitlines() if line.startswith(("FAILED", "ERROR", "E "))][:12]
    return (1.0 if ok else 0.0), tmp, "\n".join(tail)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--all", action="store_true")
    ap.add_argument("--only", default="", help="run only variants whose label contains this text")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("-v", "--verbose", action="store_true")
    ap.add_argument("--original", action="store_true",
                    help="grade with the original hidden test instead of the Harbor-native one (to show which "
                         "shortcuts the original grader let through)")
    a = ap.parse_args()
    names = sorted(p.name for p in TASKS.iterdir() if p.is_dir()) if a.all else a.tasks
    rows, ok = [], True
    for t in names:
        if t in GPU_TASKS:
            print(f"{t}: skipped (needs 2 GPUs)")
            continue
        for label, script, want in variants(t):
            if a.only not in label:
                continue
            t0 = time.time()
            got, tmp, why = grade(t, script, a.python, a.verbose, a.original)
            good = got == want
            ok &= good
            rows.append((t, label, want, got, good))
            print(f"{t:22s} {label:42s} want {want} got {got:.0f}  {'ok' if good else 'MISMATCH'}  ({time.time() - t0:.0f}s)", flush=True)
            if why and (a.verbose or not good or want == 0):
                print("    " + why.replace("\n", "\n    ")[:1500], flush=True)
            shutil.rmtree(tmp, ignore_errors=True)
    print(f"\n{sum(r[4] for r in rows)}/{len(rows)} variants as expected")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
