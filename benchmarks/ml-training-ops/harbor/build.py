"""
Build the Harbor-native ml-training-ops tasks into harbor/tasks/.

    python harbor/build.py            # (re)write harbor/tasks/<task>/ for all 24 tasks
    python harbor/build.py nan-loss   # only some tasks

Sources stay where the original runs used them: the v1 tasks in tasks/mlops_tasks/ (committed as
built) and the hard / v2 / v3 / torchtitan tasks in tasks/mlops_hard/src/ (assembled by that
folder's build.py). This script takes those, unchanged, and adds what the Harbor-native version
needs, from harbor/shared/ and harbor/overlays/<task>/:

- tests/test.sh (shared): clears stale rewards, always writes one, runs pytest with the grader's
  own configuration and accepts only a JUnit report in which every test passed;
- task.toml: schema 1.4 with a [task] name, the original resources and time limits, the verifier
  in a separate container that receives only /app from the agent's container (artifacts);
- tests/shortcuts/*.sh: plausible wrong fixes plus the shared grade forgery, each must score 0;
- solution/alternatives/*.sh: valid solutions different from the reference, each must score 1;
- overlays/<task>/tests/: grader files that replace the original ones where a shortcut passed the
  original grader (listed in GRADER_CHANGES and in harbor/README.md).

Torchtitan images get pinned package versions (PINNED_TITAN) instead of the original unpinned
installs.
"""
import importlib.util
import json
import os
import re
import shutil
import sys
import tempfile
import tomllib
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent
V1_SRC = BENCH / "tasks" / "mlops_tasks"
HARD_DIR = BENCH / "tasks" / "mlops_hard"
OUT = HERE / "tasks"
SHARED = HERE / "shared"
OVERLAYS = HERE / "overlays"

ROUNDS = {
    "v1": ["nan-loss", "label-shuffle", "resume-checkpoint", "oom-grad-accum", "ddp-sharding", "eval-mode"],
    "hard": ["ddp-replica-drift", "uneven-shard-hang", "straggler-diagnosis", "corrupt-shard", "atomic-checkpoint",
             "reshard-optimizer", "k8s-unschedulable", "memory-leak-oom"],
    "v2": ["exact-resume", "k8s-quota-zone", "two-stragglers"],
    "v3": ["regression-bisect", "throughput-sla", "ray-exactly-once", "gang-controller", "elastic-churn"],
    "torchtitan": ["titan-fork-drift", "titan-silent-divergence"],
}
ROUND_OF = {t: r for r, ts in ROUNDS.items() for t in ts}
GPU_TASKS = set(ROUNDS["torchtitan"])
# Graders that count the job's optimizer steps and backward passes (shared/stepcount/).
STEPCOUNT_TASKS = {"atomic-checkpoint", "exact-resume", "elastic-churn"}

# Tasks whose hidden tests differ from the ones the original runs were graded with (a plausible
# shortcut passed the original grader). Everything else grades exactly as before.
GRADER_CHANGES = {
    "nan-loss": "also checks that build_model() still produces the original initialization",
    "resume-checkpoint": "also checks that --resume continues from the checkpoint instead of retraining from step 0",
    "atomic-checkpoint": "also checks that every restart resumes (no checkpoint older than one already saved appears)",
    "exact-resume": "also checks that every restart resumes (no checkpoint older than one already saved appears)",
    "elastic-churn": "also checks that relaunches resume and that every rank trains",
    "uneven-shard-hang": "also checks that no training example is skipped for a whole epoch",
    "regression-bisect": "scores accuracy by evaluating the saved weights itself instead of reading train.py's report",
    "ray-exactly-once": "also checks that the live totals actor holds the exact totals once the job is done",
}

# The v1 instructions have no title line.
V1_TITLES = {
    "nan-loss": "The training job's loss turns NaN after a few steps",
    "label-shuffle": "Accuracy stuck at chance after shuffling was added to the data pipeline",
    "resume-checkpoint": "Resuming from a checkpoint changes the final weights",
    "oom-grad-accum": "The training job exceeds its memory limit",
    "ddp-sharding": "Distributed training only sees half the data",
    "eval-mode": "Validation accuracy is noisy and evaluation changes the model",
}

# Versions resolved for the torchtitan images on 2026-10-22 (the original runs installed torchao and
# torchtitan's requirements unpinned; what they got is not recorded).
PINNED_TITAN_FILE = HERE / "shared" / "titan-requirements.txt"


def task_toml(task, orig):
    """The Harbor-native task.toml, keeping the original resources and limits."""
    env, agent, ver = orig.get("environment", {}), orig.get("agent", {}), orig.get("verifier", {})
    meta = orig.get("metadata", {})
    title = V1_TITLES.get(task) or (OUT / task / "instruction.md").read_text().splitlines()[0].lstrip("# ").strip()
    gb = lambda s: int(float(str(s).rstrip("G")) * 1024)  # noqa: E731
    lines = [
        'schema_version = "1.4"',
        "",
        "# The verifier container gets the agent's /app back (and nothing else of the agent's container).",
        'artifacts = [{ source = "/app", exclude = ["__pycache__", "outputs"] }]' if task in GPU_TASKS
        else 'artifacts = ["/app"]',
        "",
        "[task]",
        f'name = "zenml/mlops-{task}"',
        'version = "2.0.0"',
        f"description = {json.dumps(title)}",
        'keywords = ["ml-training", "operations", "pytorch"]',
        "",
        "[metadata]",
        f'round = "{ROUND_OF[task]}"',
        f'difficulty = "{meta.get("difficulty", "hard")}"',
        'category = "ml-training-ops"',
        "tags = [" + ", ".join(f'"{t}"' for t in meta.get("tags", [])) + "]",
        f"grader_changed_from_original = {'true' if task in GRADER_CHANGES else 'false'}",
        f"needs_gpu = {'true' if task in GPU_TASKS else 'false'}",
        "",
        "[verifier]",
        f"timeout_sec = {float(ver.get('timeout_sec', 600.0))}",
        'environment_mode = "separate"',
        "",
        "[agent]",
        f"timeout_sec = {float(agent['timeout_sec'])}",
        "",
        "[environment]",
        f"build_timeout_sec = {float(env.get('build_timeout_sec', 1800.0))}",
        f"cpus = {env['cpus']}",
        f"memory_mb = {gb(env['memory'])}",
        f"storage_mb = {gb(env['storage'])}",
    ]
    if "gpus" in env:
        lines += [f"gpus = {env['gpus']}", "gpu_types = [" + ", ".join(f'"{g}"' for g in env["gpu_types"]) + "]"]
    return "\n".join(lines) + "\n"


def pin_titan(dockerfile):
    """Replace the unpinned torchao / requirements installs with the pinned set."""
    s = dockerfile.replace("pip install --no-cache-dir torchao pytest==8.4.1",
                           "pip install --no-cache-dir pytest==8.4.1")
    s = s.replace("COPY gen/ /tmp/gen/\n", "COPY gen/ /tmp/gen/\nCOPY titan-requirements.txt /tmp/titan-requirements.txt\n")
    assert s != dockerfile
    return s


def load_hard_builder():
    spec = importlib.util.spec_from_file_location("mlops_hard_build", HARD_DIR / "build.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def copy_source(task, tmp, hard):
    """Copy the task as the original runs saw it into tmp/<task>."""
    if ROUND_OF[task] == "v1":
        shutil.copytree(V1_SRC / task, tmp / task, ignore=shutil.ignore_patterns("__pycache__"))
    else:
        hard.OUT = tmp
        hard.write(task)


def write(task, hard):
    with tempfile.TemporaryDirectory() as tmp_s:
        tmp = Path(tmp_s)
        copy_source(task, tmp, hard)
        d = OUT / task
        shutil.rmtree(d, ignore_errors=True)
        shutil.copytree(tmp / task, d)
    orig = tomllib.loads((d / "task.toml").read_text())
    (d / "task.toml").write_text(task_toml(task, orig))
    for f in ("test.sh", "junit_ok.py", "pytest.ini"):
        shutil.copy(SHARED / f, d / "tests" / f)
    (d / "tests" / "shortcuts").mkdir()
    shutil.copy(SHARED / "shortcuts" / "forge_grade.sh", d / "tests" / "shortcuts" / "forge_grade.sh")
    if task in STEPCOUNT_TASKS:
        shutil.copytree(SHARED / "stepcount", d / "tests" / "stepcount", ignore=shutil.ignore_patterns("__pycache__"))
    ov = OVERLAYS / task
    if (ov / "tests").exists():
        shutil.copytree(ov / "tests", d / "tests", dirs_exist_ok=True)
    for kind, dest in (("shortcuts", d / "tests" / "shortcuts"), ("alternatives", d / "solution" / "alternatives")):
        for f in sorted((ov / kind).glob("*")) if (ov / kind).exists() else []:
            dest.mkdir(parents=True, exist_ok=True)
            shutil.copy(f, dest / f.name)
    if task in GPU_TASKS:
        df = d / "environment" / "Dockerfile"
        df.write_text(pin_titan(df.read_text()))
        shutil.copy(PINNED_TITAN_FILE, d / "environment" / "titan-requirements.txt")
        gen = d / "environment" / "gen" / "gen.sh"
        g = gen.read_text()
        g2 = g.replace("pip install --no-cache-dir -r requirements.txt && pip install --no-cache-dir -e .",
                       "pip install --no-cache-dir -r /tmp/titan-requirements.txt && pip install --no-cache-dir --no-deps -e .")
        assert g2 != g
        gen.write_text(g2)
    for f in d.rglob("*.sh"):
        os.chmod(f, 0o755)
    for f in d.rglob("__pycache__"):
        shutil.rmtree(f)


def main(argv):
    names = argv or [t for ts in ROUNDS.values() for t in ts]
    unknown = [t for t in names if t not in ROUND_OF]
    if unknown:
        sys.exit(f"unknown tasks: {unknown}")
    hard = load_hard_builder()
    OUT.mkdir(exist_ok=True)
    for t in names:
        write(t, hard)
    print(f"wrote {len(names)} tasks to {OUT.relative_to(BENCH)}/: {', '.join(names)}")


if __name__ == "__main__":
    main(sys.argv[1:])
