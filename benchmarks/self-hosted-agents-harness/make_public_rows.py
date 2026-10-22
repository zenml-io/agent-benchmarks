"""
Write the publishable per-run rows for one benchmark from a private attempts.jsonl.

    BENCH_DIR=<dir with the private attempts.jsonl and jobs/> \
      python make_public_rows.py --task-sets full full-k2 gaia quick --classify > attempts.jsonl

Each output row is the input row with two changes:
  - `error` keeps only its first line, with deploy output, URLs, local paths and Modal image ids
    removed (they named the Modal workspace, environment and the runner's home directory);
  - with --classify, every trial gets `failure_class` (trajectories.classify from the
    agentperf-infra analysis: None if solved) and, for timed-out trials, `loop_share`
    ([full text, first 40 chars, first 20 chars]), computed from the raw trajectories in jobs/.
    That lets the failure tables be rebuilt without publishing trajectories.
Nothing measured changes. Run where the raw jobs/ directory exists (the private archive).
"""

import argparse
import json
import re
import sys
from pathlib import Path

import experiment as ex

SCRUB = [
    (re.compile(r"https?://\S+"), "<url>"),
    (re.compile(r"(/Users|/home|/root|/tmp)/\S*"), "<path>"),
    (re.compile(r"\bim-[A-Za-z0-9]{10,}\b"), "<image>"),
]


def clean_error(err: str) -> str:
    if not err:
        return err
    first = err.split("\n")[0]
    first = first.split("; see ")[0]
    if first.rstrip().endswith(":"):
        first = first.rstrip() + " [command output removed]"
    for rx, sub in SCRUB:
        first = rx.sub(sub, first)
    return first


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--task-sets", nargs="+", required=True)
    ap.add_argument("--classify", action="store_true",
                    help="add failure_class / loop_share per trial from jobs/ (agentperf-infra classifier)")
    ap.add_argument("--infra-src", default=str(Path(__file__).resolve().parent.parent / "agentperf-infra" / "src"),
                    help="where trajectories.py lives")
    a = ap.parse_args()
    tj = None
    if a.classify:
        sys.path.insert(0, a.infra_src)
        import trajectories as tj  # noqa: F811
    for line in ex.ATTEMPTS.read_text().splitlines():
        if not line.strip():
            continue
        r = json.loads(line)
        if r["task_set"] not in a.task_sets:
            continue
        r["error"] = clean_error(r.get("error", ""))
        job = ex.JOBS_DIR / r["job_name"]
        if tj and job.exists():
            dirs = sorted(p.parent for p in job.glob("*/result.json"))
            assert len(dirs) == len(r["trials"]), r["job_name"]
            for d, t in zip(dirs, r["trials"]):
                cls = tj.classify(d)
                t["failure_class"] = cls
                if cls and cls.startswith("out of time"):
                    acts = tj.actions(d / "agent" / "trajectory.json")
                    t["loop_share"] = [tj.loop_share([x[:p] for x in acts] if p else acts) for p in (None, 40, 20)]
        print(json.dumps(r))


if __name__ == "__main__":
    main()
