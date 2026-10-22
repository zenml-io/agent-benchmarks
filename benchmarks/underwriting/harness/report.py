"""Summarize runs: accuracy, cost per correct decision, latency, failure types, by task type.

  python harness/report.py [--ref sonnet-5.5] [--tasks common|all]

Writes results/summary.json and results/tables.md. With --tasks common (default), every model is scored on the tasks
all models finished, so the comparison is paired; harness errors are excluded and re-run, provider failures and
empty replies count as wrong. Differences against --ref are paired bootstrap 95% intervals.
"""
import argparse
import glob
import json
import math
import os
import random
import statistics
from collections import Counter, defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TYPES = ["Appetite Check", "Product Recommendations", "Small Business Elibility Check", "Policy Limits",
         "Deductibles", "Business Classification"]
SHORT = {"Small Business Elibility Check": "Small business check"}


def wilson(k, n, z=1.96):
    if not n:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (c - h, c + h)


def paired(a, b, rng, reps=4000):
    keys = sorted(set(a) & set(b))
    diffs = [int(a[k]) - int(b[k]) for k in keys]
    n = len(diffs)
    boots = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(reps))
    return sum(diffs) / n, boots[int(reps * 0.025)], boots[int(reps * 0.975)], n


def load():
    runs = {}
    for p in glob.glob(os.path.join(ROOT, "results", "runs", "*.jsonl")):
        rows = {}
        for line in open(p):
            r = json.loads(line)
            if r["status"] != "harness_error":
                rows[r["task"]] = r
        runs[os.path.basename(p)[:-6]] = rows
    return runs


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ref", default=None)
    ap.add_argument("--tasks", default="common", choices=["common", "all"])
    a = ap.parse_args()
    runs = load()
    common = set.intersection(*(set(r) for r in runs.values())) if runs else set()
    rng = random.Random(0)
    summary = {}
    for m, rows in runs.items():
        keys = common if a.tasks == "common" else set(rows)
        rs = [rows[k] for k in sorted(keys)]
        n, k = len(rs), sum(r["success"] for r in rs)
        cost = sum(r["cost"] for r in rs)
        by_type = defaultdict(lambda: [0, 0])
        for r in rs:
            by_type[r["task_type"]][0] += r["success"]
            by_type[r["task_type"]][1] += 1
        lats = [r["latency"] for r in rs if r.get("latency")]
        summary[m] = dict(
            n=n, correct=k, accuracy=k / n if n else None, ci=wilson(k, n),
            cost_per_task=cost / n if n else None, cost_per_correct=cost / k if k else None,
            env_cost=sum(r.get("sim_cost", 0) + r.get("judge_cost", 0) for r in rs),
            latency_p50=statistics.median(lats) if lats else None,
            calls_mean=statistics.mean(r.get("calls", 0) for r in rs) if rs else None,
            tokens_per_task=statistics.mean(r.get("input", 0) + r.get("output", 0) for r in rs) if rs else None,
            statuses=dict(Counter(r["status"] for r in rs)), failures=dict(Counter(f for r in rs for f in r["failures"])),
            by_type={t: dict(correct=v[0], n=v[1], accuracy=v[0] / v[1]) for t, v in by_type.items()})
        if a.ref and a.ref in runs and m != a.ref:
            d, lo, hi, np_ = paired({t: rows[t]["success"] for t in keys},
                                    {t: runs[a.ref][t]["success"] for t in keys if t in runs[a.ref]}, rng)
            summary[m]["vs_ref"] = dict(ref=a.ref, delta=d, lo=lo, hi=hi, n=np_)
    os.makedirs(os.path.join(ROOT, "results"), exist_ok=True)
    json.dump(dict(tasks=a.tasks, n_common=len(common), models=summary),
              open(os.path.join(ROOT, "results", "summary.json"), "w"), indent=1)
    order = sorted(summary, key=lambda m: -(summary[m]["accuracy"] or 0))
    lines = [f"Tasks: {a.tasks} ({len(common)} finished by every model)\n",
             "| model | correct | 95% CI | cost per task | cost per correct decision | median latency | "
             + (f"vs {a.ref} (pts) |" if a.ref else "") + " failures |",
             "|---|---|---|---|---|---|" + ("---|" if a.ref else "") + "---|"]
    for m in order:
        s = summary[m]
        lo, hi = s["ci"]
        vs = ""
        if a.ref:
            v = s.get("vs_ref")
            vs = (f" {v['delta'] * 100:+.1f} [{v['lo'] * 100:+.1f}, {v['hi'] * 100:+.1f}] |" if v else " – |")
        fails = ", ".join(f"{k} {v}" for k, v in s["failures"].items()) or "–"
        lines.append(f"| {m} | {s['accuracy']:.1%} ({s['correct']}/{s['n']}) | {lo:.0%}–{hi:.0%} | "
                     f"{s['cost_per_task'] * 100:.2f}¢ | "
                     f"{(s['cost_per_correct'] or 0) * 100:.2f}¢ | {s['latency_p50']:.0f}s |{vs} {fails} |")
    lines += ["", "Accuracy by task type:", "",
              "| model | " + " | ".join(SHORT.get(t, t) for t in TYPES) + " |", "|---|" + "---|" * len(TYPES)]
    for m in order:
        bt = summary[m]["by_type"]
        lines.append(f"| {m} | " + " | ".join(
            f"{bt[t]['accuracy']:.0%} ({bt[t]['n']})" if t in bt else "–" for t in TYPES) + " |")
    open(os.path.join(ROOT, "results", "tables.md"), "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))


if __name__ == "__main__":
    main()
