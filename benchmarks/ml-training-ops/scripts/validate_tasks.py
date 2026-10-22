"""
Load every task directory with Harbor's own task loader (config schema, required files, tests),
without building images or starting sandboxes. Free and offline.

    uv run --with 'harbor==0.24.0' python scripts/validate_tasks.py

Checks tasks/mlops_tasks/* (v1) and tasks/mlops_hard/tasks/* (run tasks/mlops_hard/build.py first),
and that every task named in data/tasks_mlops*.json exists.
"""
import json
import sys
from pathlib import Path

from harbor.models.task.task import Task

BENCH = Path(__file__).resolve().parents[1]
dirs = sorted(p.parent for p in (BENCH / "tasks").glob("mlops_tasks/*/task.toml")) + \
       sorted(p.parent for p in (BENCH / "tasks").glob("mlops_hard/tasks/*/task.toml"))
bad = 0
for d in dirs:
    try:
        t = Task(d)
        c = t.config
        print(f"ok  {d.relative_to(BENCH)}  agent {c.agent.timeout_sec:.0f}s  cpus {c.environment.cpus}  "
              f"gpus {c.environment.gpus}")
    except Exception as e:  # noqa: BLE001 - report every bad task
        bad += 1
        print(f"BAD {d.relative_to(BENCH)}: {type(e).__name__}: {e}")
for f in sorted((BENCH / "data").glob("tasks_mlops*.json")):
    spec = json.loads(f.read_text())
    missing = [t for t in spec["tasks"] if not (BENCH / spec["path"] / t / "task.toml").exists()]
    bad += bool(missing)
    print(f"{'ok ' if not missing else 'BAD'} {f.name}: {len(spec['tasks'])} tasks" + (f", missing {missing}" if missing else ""))
print(f"{len(dirs)} task dirs, {bad} problems")
sys.exit(1 if bad else 0)
