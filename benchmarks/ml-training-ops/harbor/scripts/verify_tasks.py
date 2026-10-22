"""
The four Harbor checks for the built tasks, run on Modal with Harbor's free agents (no model calls):

1. oracle: solution/solve.sh scores 1 on every attempt (-k 5 by default);
2. nop: doing nothing scores 0;
3. every tests/shortcuts/*.sh, installed as the solution, scores 0;
4. every solution/alternatives/*.sh, installed as the solution, scores 1.

    HARBOR_TELEMETRY=off python harbor/scripts/verify_tasks.py --jobs-dir ~/mlops-harbor-jobs nan-loss eval-mode
    HARBOR_TELEMETRY=off python harbor/scripts/verify_tasks.py --jobs-dir ~/mlops-harbor-jobs --cpu-tasks
    python harbor/scripts/verify_tasks.py --jobs-dir ~/mlops-harbor-jobs --summarize <job> [<job> ...]

Checks 3 and 4 copy each task to a temporary directory with the script as solution/solve.sh (the
reference stays at /solution/files) and run Harbor's oracle agent on all copies in one job. Every
job uses its own Modal app (--app-name) so its sandbox cost can be read from `modal billing report`.
--titan-static runs the torchtitan tasks on CPU sandboxes with only their GPU-free tests (see
harbor/README.md). Prints a table and exits 1 if any check fails.
"""
import argparse
import json
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
SEP = "--"


def cpu_tasks():
    return sorted(p.name for p in TASKS.iterdir() if p.is_dir() and p.name not in GPU_TASKS)


def variant_copy(task, script, label, root, static=False):
    """Copy of the task, with `script` as solution/solve.sh and a distinct name when label is set."""
    d = root / (f"{task}{SEP}{label}" if label else task)
    shutil.copytree(TASKS / task, d)
    if script is not None:
        shutil.copy(script, d / "solution" / "solve.sh")
    toml = (d / "task.toml").read_text()
    if label:
        toml = re.sub(r'^name = "zenml/mlops-([^"]+)"', rf'name = "zenml/mlops-\1{SEP}{label}"', toml, flags=re.M)
    if static:  # GPU-free grading of the torchtitan tasks
        toml = re.sub(r"^gpus = .*\n|^gpu_types = .*\n", "", toml, flags=re.M)
        toml = re.sub(r"^cpus = .*", "cpus = 4", toml, flags=re.M)
        toml = re.sub(r"^memory_mb = .*", "memory_mb = 16384", toml, flags=re.M)
        t = (d / "tests" / "test.sh").read_text()
        t2 = t.replace('--junitxml="$JUNIT"', '--junitxml="$JUNIT" -k "not matches_golden"')
        assert t2 != t
        (d / "tests" / "test.sh").write_text(t2)
    (d / "task.toml").write_text(toml)
    return d


def harbor_job(paths_root, agent, attempts, jobs_dir, name, n, app):
    cmd = ["harbor", "run", "-y", "-p", str(paths_root), "-a", agent, "-k", str(attempts), "-n", str(n), "-e", "modal",
           "--ek", f"app_name={app}", "--ek", "sandbox_timeout_secs=5400", "-o", str(jobs_dir), "--job-name", name]
    print(" ".join(cmd), flush=True)
    t0 = time.time()
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(f"  harbor exit {r.returncode} after {time.time() - t0:.0f}s", flush=True)
    if r.returncode != 0:
        print(r.stdout[-3000:], r.stderr[-3000:], file=sys.stderr)


def read_job(job_dir):
    """{(task dir name, agent): [reward or None (no reward: infrastructure or harness error)]}."""
    out = {}
    for p in sorted(Path(job_dir).glob("*/result.json")):
        r = json.loads(p.read_text())
        name = Path((r.get("task_id") or {}).get("path", "")).name
        agent = (r.get("agent_info") or {}).get("name", "?")
        rew = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        out.setdefault((name, agent), []).append(None if rew is None else float(rew))
    return out


def summarize(job_dirs, static=False):
    rows, ok = [], True
    for jd in job_dirs:
        for (name, agent), rewards in sorted(read_job(jd).items()):
            task, label = name.split(SEP, 1) if SEP in name else (name, agent)
            want = 1.0 if (label == "oracle" or label.startswith("alternatives_")) else 0.0
            if static and (label in ("oracle", "nop", "shortcuts_forge_grade") or label.startswith("shortcuts_gpu_")):
                # GPU-free tests only: the untouched fork keeps its intentional changes (so nop and the grade
                # forgery, which changes no code, pass them), and shortcuts named gpu_* are caught only by the
                # GPU training run
                want = 1.0
            good = bool(rewards) and all(r == want for r in rewards)
            ok &= good
            rows.append((task, label, want, rewards, good, Path(jd).name))
    print(f"\n{'task':24s} {'check':44s} want  rewards                        status")
    for task, label, want, rewards, good, job in rows:
        print(f"{task:24s} {label:44s} {want:<5} {str(rewards):30s} {'PASS' if good else 'FAIL'}")
    print("\nALL CHECKS PASS" if ok else "\nSOME CHECKS FAILED (None = no reward: infrastructure or harness error)")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", nargs="*")
    ap.add_argument("--cpu-tasks", action="store_true", help="all 22 CPU tasks")
    ap.add_argument("--titan-static", action="store_true", help="the torchtitan tasks' GPU-free tests on CPU sandboxes")
    ap.add_argument("--jobs-dir", type=Path, required=True, help="outside the checkout")
    ap.add_argument("--prefix", default=time.strftime("verify-%Y%m%d-%H%M%S"))
    ap.add_argument("--oracle-attempts", type=int, default=5)
    ap.add_argument("-n", type=int, default=8, help="trials at once")
    ap.add_argument("--app-name", default="mlops-harbor-checks")
    ap.add_argument("--skip", nargs="*", default=[], choices=["oracle", "nop", "variants"])
    ap.add_argument("--summarize", nargs="*", help="only print the table for these job directories")
    a = ap.parse_args()
    if a.summarize is not None:
        return 0 if summarize([a.jobs_dir / j for j in a.summarize], static=a.titan_static) else 1
    if a.titan_static:
        names = sorted(GPU_TASKS)
    else:
        names = cpu_tasks() if a.cpu_tasks else a.tasks
    bad = [t for t in names if not (TASKS / t).is_dir() or (t in GPU_TASKS and not a.titan_static)]
    if bad:
        sys.exit(f"not runnable here: {bad} (torchtitan tasks need --titan-static or GPUs)")
    jobs = []
    with tempfile.TemporaryDirectory(prefix="mlops-verify-") as tmp_s:
        tmp = Path(tmp_s)
        base, var = tmp / "base", tmp / "variants"
        base.mkdir()
        var.mkdir()
        for t in names:
            variant_copy(t, None, None, base, static=a.titan_static)
            for kind in ("tests/shortcuts", "solution/alternatives"):
                for s in sorted((TASKS / t / kind).glob("*.sh")):
                    variant_copy(t, s, f"{kind.split('/')[1]}_{s.stem}", var, static=a.titan_static)
        if "oracle" not in a.skip:
            jobs.append(f"{a.prefix}-oracle")
            harbor_job(base, "oracle", 1 if a.titan_static else a.oracle_attempts, a.jobs_dir, jobs[-1], a.n, a.app_name)
        if "nop" not in a.skip:
            jobs.append(f"{a.prefix}-nop")
            harbor_job(base, "nop", 1, a.jobs_dir, jobs[-1], a.n, a.app_name)
        if "variants" not in a.skip:
            jobs.append(f"{a.prefix}-variants")
            harbor_job(var, "oracle", 1, a.jobs_dir, jobs[-1], a.n, a.app_name)
    return 0 if summarize([a.jobs_dir / j for j in jobs], static=a.titan_static) else 1


if __name__ == "__main__":
    sys.exit(main())
