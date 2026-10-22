"""
Print the experiment.py command that reproduces every valid run in a rows file, with what that
run cost and how long it took when it was recorded. Prints only; runs nothing.

    python plan_rerun.py ../agentperf-infra/results/runs/attempts.jsonl [--task-sets full full-k2]

Each command is `matrix` restricted to one harness, config, concurrency, repeat and attempt count,
so it re-creates exactly that run (and, run twice, skips it the second time). Run them from the
benchmark directory. Costs: GPU = run seconds x $/GPU-hour (startup excluded, as recorded);
sandboxes = experiment.py's estimate (under-counts the bill); wall = server up-time (deploy to stop).
"""
import argparse
import json
from collections import defaultdict

TASKS_FILE = {"full": "tasks.json", "gaia": "tasks_gaia.json", "mlops": "tasks_mlops.json",
              "mlops_hard": "tasks_mlops_hard.json", "mlops_hard2": "tasks_mlops_hard2.json"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("rows")
    ap.add_argument("--task-sets", nargs="*")
    a = ap.parse_args()
    rows = [json.loads(l) for l in open(a.rows) if l.strip()]
    rows = [r for r in rows if r.get("valid") and (not a.task_sets or r["task_set"] in a.task_sets)]
    by_set = defaultdict(list)
    for r in rows:
        by_set[r["task_set"]].append(r)
    total = defaultdict(float)
    for ts, rs in by_set.items():
        print(f"\n## task set `{ts}` ({len(rs)} runs)\n")
        print("| command | trials | GPU $ | sandbox est. $ | wall min |\n|---|---|---|---|---|")
        for r in sorted(rs, key=lambda r: (r["ts"])):
            k = r.get("attempts_per_task", 1)
            if ts == "quick":  # one quickcheck command runs both of its configs
                cmd = f"experiment.py --harnesses {r['harness']} -- quickcheck"
            else:
                base = ts.rsplit("-k", 1)[0] if k > 1 else ts
                tf = TASKS_FILE[base]
                cmd = (f"experiment.py --tasks-file {tf} --harnesses {r['harness']} -- matrix --configs {r['config']} "
                       f"--concurrency {r['concurrency']} --rep-from {r['rep']} --reps {r['rep'] + 1}"
                       + (f" --attempts {k}" if k > 1 else ""))
            gpu, sbx, up = r.get("cost") or 0, r.get("sandbox_cost_est") or 0, (r.get("up_s") or 0) / 60
            for key, v in (("gpu", gpu), ("sbx", sbx), ("startup", r.get("startup_cost") or 0), ("wall_min", up)):
                total[key] += v
            note = f" (its {r['config']} run)" if ts == "quick" else ""
            print(f"| `{cmd}`{note} | {r['attempted']} | {gpu:.2f} | {sbx:.2f} | {up:.0f} |")
    print(f"\nTotal over {len(rows)} runs: GPU ${total['gpu']:.2f} + startup ${total['startup']:.2f} + "
          f"sandbox estimate ${total['sbx']:.2f}; {total['wall_min'] / 60:.1f} server-hours if run one after another.")


if __name__ == "__main__":
    main()
