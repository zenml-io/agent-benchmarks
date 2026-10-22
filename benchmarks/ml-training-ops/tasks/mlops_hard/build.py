"""
Assemble the hard ML-training-operations tasks (Harbor format) from src/ into tasks/.

    python build.py                  # write tasks/<task>/...
    python build.py --check [task]   # locally: the original code must FAIL its tests, the reference fix must PASS

src/<task>/ holds instruction.md, app/ (the code the agent sees), fixed/ (files that overwrite app/
for the reference solution), tests/ (hidden from the agent: test_outputs.py plus answer keys and
independent reference code) and optionally gen/gen.sh, run in /app at image build time to create
large generated inputs (telemetry, data shards, checkpoints) and then deleted.
"""
import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
SRC, OUT = HERE / "src", HERE / "tasks"


def write(task):
    s, d = SRC / task, OUT / task
    shutil.rmtree(d, ignore_errors=True)
    (d / "environment").mkdir(parents=True)
    shutil.copy(s / "instruction.md", d / "instruction.md")
    toml = (HERE / "_task.toml").read_text()
    if (s / "task.toml.full").exists():  # tasks with their own resources (e.g. GPUs)
        toml = (s / "task.toml.full").read_text()
    if (s / "task.toml.extra").exists():
        toml += (s / "task.toml.extra").read_text()
    (d / "task.toml").write_text(toml)
    docker = (HERE / "_Dockerfile").read_text()
    if (s / "Dockerfile.extra").exists():  # extra system packages, before the app is copied
        docker = docker.replace("WORKDIR /app\n", (s / "Dockerfile.extra").read_text() + "WORKDIR /app\n")
    shutil.copytree(s / "app", d / "environment" / "app")
    if (s / "gen").exists():
        shutil.copytree(s / "gen", d / "environment" / "gen")
        docker += "COPY gen/ /tmp/gen/\nRUN cd /app && bash /tmp/gen/gen.sh && rm -rf /tmp/gen\n"
    if (s / "Dockerfile.full").exists():
        docker = (s / "Dockerfile.full").read_text()
    (d / "environment" / "Dockerfile").write_text(docker)
    shutil.copytree(s / "tests", d / "tests")
    shutil.copy(HERE / "_test.sh", d / "tests" / "test.sh")
    (d / "solution").mkdir()
    shutil.copytree(s / "fixed", d / "solution" / "files")
    shutil.copy(s / "solve.sh" if (s / "solve.sh").exists() else HERE / "_solve.sh", d / "solution" / "solve.sh")
    for f in (d / "tests" / "test.sh", d / "solution" / "solve.sh"):
        os.chmod(f, 0o755)


def check(task, python):
    s = SRC / task
    res = {}
    for variant in ("buggy", "fixed"):
        tmp = Path(tempfile.mkdtemp(prefix=f"{task}-"))
        app = tmp / "app"
        shutil.copytree(s / "app", app)
        env = {**os.environ, "APP_DIR": str(app), "PATH": str(Path(python).parent) + ":" + os.environ["PATH"]}
        if (s / "gen").exists():
            subprocess.run(["bash", str(s / "gen" / "gen.sh")], cwd=app, env={**env, "GEN_DIR": str(s / "gen")}, check=True)
        if variant == "fixed":
            shutil.copytree(s / "fixed", app, dirs_exist_ok=True)
        shutil.copytree(s / "tests", tmp / "tests")
        t0 = time.time()
        r = subprocess.run([python, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(tmp / "tests" / "test_outputs.py")],
                           cwd=app, env=env, capture_output=True, text=True, timeout=3600)
        res[variant] = r.returncode == 0
        print(f"  {variant}: {'pass' if res[variant] else 'fail'} in {time.time() - t0:.0f}s", flush=True)
        if (variant == "buggy") == res[variant] or os.environ.get("VERBOSE"):
            print(r.stdout[-3000:])
    ok = (not res["buggy"]) and res["fixed"]
    print(f"{task:24s} -> {'OK' if ok else 'PROBLEM'}", flush=True)
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("tasks", nargs="*")
    a = ap.parse_args()
    names = a.tasks or sorted(p.name for p in SRC.iterdir() if p.is_dir())
    for t in names:
        write(t)
    if a.check:
        sys.exit(0 if all([check(t, a.python) for t in names]) else 1)
    print("wrote", ", ".join(names))
