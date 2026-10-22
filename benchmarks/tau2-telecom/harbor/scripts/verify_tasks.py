"""The four verifier checks for every task, through Harbor (free: no model calls, the user simulator never starts).

    PYTHONPATH= HARBOR_TELEMETRY=off env -u OPENAI_API_KEY \
        python harbor/scripts/verify_tasks.py --jobs-dir /tmp/tau2-jobs -e modal -n 8

1. oracle (solution/solve.sh, the reference) scores 1.0 on every attempt (default 5 attempts per task)
2. Harbor's `nop` agent (does nothing) scores 0
3. every tests/shortcuts/*.sh scores 0
4. every solution/alternatives/*.sh scores 1.0

Shortcuts and alternatives run as Harbor's oracle agent on a copy of the task whose solution/solve.sh is
that script, so every check uses the same containers and grader. Each check is one Harbor job over all
selected tasks. Follows zenml-bench's scripts/verify_task.py (github.com/zenml-io/zenml-bench), batched.
Exit code 1 if any check fails. Writes <jobs-dir>/<prefix>-summary.json.
"""

import argparse
import json
import math
import re
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

TASKS = Path(__file__).resolve().parents[1] / "tasks"


def harbor_job(path: Path, agent: str, attempts: int, a: argparse.Namespace, name: str) -> dict[str, list[float]]:
    """Run one Harbor job over a dataset folder; rewards per task folder name (nan = trial error)."""
    job = a.jobs_dir / name
    shutil.rmtree(job, ignore_errors=True)
    cmd = ["harbor", "run", "-y", "-p", str(path), "-a", agent, "-k", str(attempts), "-e", a.env, "-n", str(a.n),
           "-o", str(a.jobs_dir), "--job-name", name, "-q"]
    if a.env == "modal":
        cmd += ["--ek", "app_name=tau2-telecom-harbor", "--ek", "sandbox_timeout_secs=3600"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stdout[-3000:], proc.stderr[-3000:], file=sys.stderr)
        raise SystemExit(f"harbor run failed for {name}")
    rewards: dict[str, list[float]] = defaultdict(list)
    for result_path in sorted(job.glob("*/result.json")):
        result = json.loads(result_path.read_text())
        task = Path(json.loads((result_path.parent / "config.json").read_text())["task"]["path"]).name
        reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        rewards[task].append(float(reward) if reward is not None else math.nan)
    return rewards


def variant(task: Path, script: Path, out: Path, label: str) -> str:
    """Copy a task with `script` as its solution; returns the copy's folder name."""
    name = f"{task.name}--{label}"
    copy = out / name
    shutil.copytree(task, copy)
    shutil.copy(script, copy / "solution" / "solve.sh")
    toml = copy / "task.toml"
    toml.write_text(re.sub(r'^name = "(.*)"$', rf'name = "\1--{label}"', toml.read_text(), count=1, flags=re.MULTILINE))
    return name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tasks", nargs="*", help="task folder names (default: all)")
    ap.add_argument("--oracle-attempts", type=int, default=5)
    ap.add_argument("--jobs-dir", type=Path, required=True)
    ap.add_argument("-e", "--env", default="modal")
    ap.add_argument("-n", type=int, default=8)
    ap.add_argument("--prefix", default="verify")
    ap.add_argument("--checks", nargs="*", default=["oracle", "nop", "shortcuts", "alternatives"])
    a = ap.parse_args()
    a.jobs_dir = a.jobs_dir.resolve()
    names = a.tasks or sorted(p.name for p in TASKS.iterdir() if (p / "task.toml").exists())

    expected: dict[tuple[str, str], float] = {}
    observed: dict[tuple[str, str], list[float]] = {}
    with tempfile.TemporaryDirectory(prefix="tau2-verify-") as tmp_s:
        tmp = Path(tmp_s)
        base = tmp / "tasks"
        base.mkdir()
        for name in names:
            shutil.copytree(TASKS / name, base / name)
        for check, agent, attempts in (("oracle", "oracle", a.oracle_attempts), ("nop", "nop", 1)):
            if check in a.checks:
                rewards = harbor_job(base, agent, attempts, a, f"{a.prefix}-{check}")
                for name in names:
                    expected[(name, check)] = 1.0 if check == "oracle" else 0.0
                    observed[(name, check)] = rewards.get(name, [])
        for check, folder, want in (("shortcuts", "tests/shortcuts", 0.0),
                                    ("alternatives", "solution/alternatives", 1.0)):
            if check not in a.checks:
                continue
            out = tmp / check
            out.mkdir()
            labels: dict[str, tuple[str, str]] = {}
            for name in names:
                for script in sorted((TASKS / name / folder).glob("*.sh")):
                    labels[variant(TASKS / name, script, out, script.stem)] = (name, f"{check[:-1]}/{script.stem}")
            rewards = harbor_job(out, "oracle", 1, a, f"{a.prefix}-{check}")
            for copy, key in labels.items():
                expected[key] = want
                observed[key] = rewards.get(copy, [])

    failures = [(k, observed[k], expected[k]) for k in expected
                if not observed[k] or any(r != expected[k] for r in observed[k])]
    by_check: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for (task, check), want in expected.items():
        group = check.split("/")[0]
        by_check[group][1] += 1
        by_check[group][0] += (task, check) not in {f[0] for f in failures}
    for group, (ok, total) in by_check.items():
        print(f"{group:<14} {ok}/{total} tasks pass")
    for (task, check), got, want in failures:
        print(f"FAIL {task} {check}: rewards {got}, expected {want}")
    summary = {"tasks": names, "oracle_attempts": a.oracle_attempts, "env": a.env,
               "by_check": {g: {"pass": ok, "total": t} for g, (ok, t) in by_check.items()},
               "results": [{"task": t, "check": c, "expected": expected[(t, c)], "rewards": observed[(t, c)]}
                           for (t, c) in sorted(expected)]}
    (a.jobs_dir / f"{a.prefix}-summary.json").write_text(json.dumps(summary, indent=2))
    print("\nALL FOUR CHECKS PASS" if not failures else "\nSOME CHECKS FAILED")
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
