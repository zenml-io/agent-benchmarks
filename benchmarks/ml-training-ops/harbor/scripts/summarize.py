"""
Summarize Harbor job folders: solve rate per setup (agent + model) and task, infrastructure errors apart from
wrong answers, and a paired difference against a baseline setup.

    python harbor/scripts/summarize.py ~/mlops-harbor-jobs/hard-luna ~/mlops-harbor-jobs/hard-sol \
        --baseline "codex / openai/gpt-6-luna" | tee results/harbor-hard-2026-10-30.md

A trial counts as:
- solved: reward 1;
- wrong: reward 0, including agent time-outs (the grader still ran on what the agent left) and agent
  errors (the agent crashed, failed to install, ...), as in the original runs;
- infrastructure error: no reward at all (sandbox, image build or verifier failure). These are listed
  apart and left out of the accuracy; re-run them.

Accuracy is solved / (solved + wrong), pooled over the tasks the setup ran. The paired difference against
the baseline averages per-task solve rates over the tasks both setups ran, with a task-level bootstrap
interval (10,000 resamples, seed 0), the method of the original analysis (src/mlops_hard_analysis.py).
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def trials(job_dirs):
    for jd in job_dirs:
        for p in sorted(Path(jd).glob("*/result.json")):
            r = json.loads(p.read_text())
            agent = (r.get("agent_info") or {}).get("name", "?")
            model = ((r.get("agent_info") or {}).get("model_info") or {})
            model = f"{model.get('provider', '')}/{model.get('name', '')}".strip("/") if model else ""
            setup = f"{agent} / {model}" if model else agent
            task = Path((r.get("task_id") or {}).get("path", r.get("task_name", "?"))).name
            reward = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward")
            exc = (r.get("exception_info") or {}).get("exception_type")
            cost = (r.get("agent_result") or {}).get("cost_usd")
            yield setup, task, reward, exc, cost, Path(jd).name


def bootstrap(diffs, n=10_000, seed=0):
    rng = random.Random(seed)
    means = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return means[int(0.025 * n)], means[int(0.975 * n) - 1]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", nargs="+", type=Path)
    ap.add_argument("--baseline", help='setup label, e.g. "codex / openai/gpt-6-luna" (default: the first setup)')
    ap.add_argument("--infra-as-wrong", action="store_true",
                    help="count no-reward trials as unsolved, as the original analysis did (for comparing with README.md)")
    a = ap.parse_args()
    cells = defaultdict(lambda: {"solved": 0, "wrong": 0, "infra": 0, "exc": defaultdict(int), "cost": 0.0, "jobs": set()})
    for setup, task, reward, exc, cost, job in trials(a.jobs):
        c = cells[(setup, task)]
        c["jobs"].add(job)
        if reward is None and a.infra_as_wrong:
            c["wrong"] += 1
            c["exc"][exc or "no reward"] += 1
        elif reward is None:
            c["infra"] += 1
            c["exc"][exc or "no reward"] += 1
        else:
            c["solved" if reward >= 1 else "wrong"] += 1
            if exc:
                c["exc"][exc] += 1
        c["cost"] += cost or 0.0
    setups = list(dict.fromkeys(s for s, _ in cells))
    tasks = sorted({t for _, t in cells})
    base = a.baseline or setups[0]
    print(f"# ml-training-ops (Harbor): {', '.join(sorted({j for c in cells.values() for j in c['jobs']}))}\n")
    print("| setup | trials | solved | accuracy | infra errors | agent cost (USD, as reported) |")
    print("|---|---|---|---|---|---|")
    for s in setups:
        cs = [c for (ss, _), c in cells.items() if ss == s]
        n = sum(c["solved"] + c["wrong"] for c in cs)
        solved = sum(c["solved"] for c in cs)
        print(f"| {s} | {n} | {solved} | {solved / n if n else float('nan'):.4f} | {sum(c['infra'] for c in cs)} | "
              f"{sum(c['cost'] for c in cs):.4f} |")
    print("\n| task | " + " | ".join(setups) + " |")
    print("|---|" + "---|" * len(setups))
    for t in tasks:
        row = []
        for s in setups:
            c = cells.get((s, t))
            row.append("-" if c is None else f"{c['solved']}/{c['solved'] + c['wrong']}" + (f" (+{c['infra']} infra)" if c["infra"] else ""))
        print(f"| {t} | " + " | ".join(row) + " |")
    print(f"\nPaired differences against `{base}` (percentage points, per-task solve rates, tasks both ran):\n")
    for s in setups:
        if s == base:
            continue
        diffs = []
        for t in tasks:
            b, c = cells.get((base, t)), cells.get((s, t))
            if b and c and (b["solved"] + b["wrong"]) and (c["solved"] + c["wrong"]):
                diffs.append(100 * (c["solved"] / (c["solved"] + c["wrong"]) - b["solved"] / (b["solved"] + b["wrong"])))
        if diffs:
            lo, hi = bootstrap(diffs)
            print(f"- {s}: {sum(diffs) / len(diffs):+.2f} ({lo:+.2f} to {hi:+.2f}) over {len(diffs)} tasks")
    errs = {(s, t): dict(c["exc"]) for (s, t), c in cells.items() if c["exc"]}
    if errs:
        print("\nExceptions (agent time-outs and errors count as wrong; no-reward trials are infrastructure errors):\n")
        for (s, t), e in sorted(errs.items()):
            print(f"- {s} | {t}: {e}")


if __name__ == "__main__":
    main()
