"""The four checks for a set of underwriting tasks, through Harbor, one job per check.

  python scripts/verify_tasks.py tasks --jobs-dir <outside the repo> [-n 4] [--oracle-attempts 5] [--checks ...]

1. oracle: solution/solve.sh (Snorkel's reference answer) scores 1 on every attempt;
2. nop: no answer scores 0 (and no judge is called);
3. each tests/shortcuts/*.sh scores 0 (hedge.sh, ask_question.sh, forge_reward.sh);
4. each solution/alternatives/*.sh scores 1 (paraphrase.sh).

Shortcuts and alternatives run as Harbor's oracle agent on a temporary copy of the task set with that script installed
as solution/solve.sh. Judges are called for every submitted answer (about $0.0001-0.0003 per answer); Modal sandboxes
cost more than the judges. Infrastructure errors (grading.json `infra_error`, trial exceptions) are reported apart.
Writes <jobs-dir>/<prefix>-summary.json. Exit code 1 if a check fails.
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from collections import defaultdict
from pathlib import Path

EXPECT = {"oracle": 1, "nop": 0}


def run_job(path, agent, attempts, jobs_dir, name, n):
    shutil.rmtree(jobs_dir / name, ignore_errors=True)
    cmd = ["harbor", "run", "-y", "-p", str(path), "-a", agent, "-k", str(attempts), "-e", "modal", "-o",
           str(jobs_dir), "--job-name", name, "-n", str(n)]
    print("$", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, capture_output=True, text=True, env={**os.environ, "HARBOR_TELEMETRY": "off"})
    if proc.returncode != 0:
        print(proc.stdout[-3000:], proc.stderr[-3000:], file=sys.stderr)
    rows = []
    for p in sorted((jobs_dir / name).glob("*/result.json")):
        r = json.loads(p.read_text())
        reward = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward")
        grading = p.parent / "verifier" / "grading.json"
        g = json.loads(grading.read_text()) if grading.exists() else {}
        rows.append(dict(task=r.get("task_name") or p.parent.name.split("__")[0], reward=reward,
                         exception=(r.get("exception_info") or {}).get("exception_type"),
                         infra_error=g.get("infra_error"), judge_cost=g.get("judge_cost", 0.0),
                         verdicts=g.get("verdicts")))
    return rows


def with_script(tasks_dir, rel, tmp):
    """Copy of the task set with solution/solve.sh replaced by each task's <rel> script."""
    out = tmp / rel.replace("/", "_")
    for d in sorted(p for p in tasks_dir.iterdir() if (p / "task.toml").exists()):
        shutil.copytree(d, out / d.name)
        shutil.copy(d / rel, out / d.name / "solution" / "solve.sh")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tasks", type=Path)
    ap.add_argument("--jobs-dir", type=Path, required=True)
    ap.add_argument("--job-prefix", default="verify")
    ap.add_argument("--oracle-attempts", type=int, default=5)
    ap.add_argument("-n", type=int, default=4)
    ap.add_argument("--checks", nargs="+", default=["oracle", "nop", "shortcuts", "alternatives"])
    a = ap.parse_args()
    tasks_dir = a.tasks.resolve()
    first = next(p for p in sorted(tasks_dir.iterdir()) if (p / "task.toml").exists())
    results = {}
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        if "oracle" in a.checks:
            results["oracle"] = run_job(tasks_dir, "oracle", a.oracle_attempts, a.jobs_dir, f"{a.job_prefix}-oracle", a.n)
        if "nop" in a.checks:
            results["nop"] = run_job(tasks_dir, "nop", 1, a.jobs_dir, f"{a.job_prefix}-nop", a.n)
        for kind, expected in (("shortcuts", 0), ("alternatives", 1)):
            if kind not in a.checks:
                continue
            sub = "tests/shortcuts" if kind == "shortcuts" else "solution/alternatives"
            for script in sorted((first / sub).glob("*.sh")):
                label = f"{kind}/{script.name}"
                EXPECT[label] = expected
                path = with_script(tasks_dir, f"{sub}/{script.name}", tmp)
                results[label] = run_job(path, "oracle", 1, a.jobs_dir, f"{a.job_prefix}-{script.stem}", a.n)
    ok = True
    table = defaultdict(dict)
    cost = 0.0
    print(f"\n{'check':<30} {'pass':>9}  failures")
    for label, rows in results.items():
        bad = [r for r in rows if r["reward"] != EXPECT[label] or r["exception"] or r["infra_error"]]
        ok &= not bad and bool(rows)
        cost += sum(r["judge_cost"] or 0 for r in rows)
        for r in rows:
            table[r["task"]].setdefault(label, []).append(r["reward"])
        print(f"{label:<30} {len(rows) - len(bad):>4}/{len(rows):<4}  "
              + "; ".join(f"{r['task']}: reward {r['reward']} {r['exception'] or ''} {r['infra_error'] or ''}"
                          for r in bad))
    print(f"\njudge spend: ${cost:.4f}")
    print("ALL CHECKS PASS" if ok else "SOME CHECKS FAILED")
    a.jobs_dir.mkdir(parents=True, exist_ok=True)
    (a.jobs_dir / f"{a.job_prefix}-summary.json").write_text(json.dumps(
        dict(ok=ok, judge_cost=cost, per_task=table, rows=results), indent=1))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
