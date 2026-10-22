"""Summarize Harbor jobs of the tau2 Telecom benchmark: one row per arm, compared with the baseline task by task.

    python harbor/scripts/summarize.py <jobs-dir>/<job> [<jobs-dir>/<job2> ...] [--baseline baseline] [--json out.json]

Standard library only. Arms come from each trial's agent kwargs (`arm`). Per arm: graded attempts, mean
reward with a Wilson 95% interval, infrastructure errors (a trial with an exception and no reward;
counted apart, not as failures), agent timeouts that were still graded, agent cost (Kitaru's estimate
from the recording; empty for models its pricing catalog lacks), and the paired difference against the
baseline arm: mean over shared tasks of (arm's per-task mean reward - baseline's), with a 95% bootstrap
interval over tasks (scripts/stats.py, the helper the published tables use). With several attempts per
task it also prints pass^k (tau-bench's reliability metric) for k = 1..attempts.
"""

import argparse
import json
import math
import sys
from collections import defaultdict
from math import comb
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))
from stats import paired_delta


def wilson(k: int, n: int) -> tuple[float, float]:
    if n == 0:
        return (math.nan, math.nan)
    z, p = 1.959964, k / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return (centre - half, centre + half)


def load(jobs: list[Path]) -> dict[str, list[dict]]:
    arms: dict[str, list[dict]] = defaultdict(list)
    for job in jobs:
        for result_path in sorted(job.glob("*/result.json")):
            trial = result_path.parent
            config = json.loads((trial / "config.json").read_text())
            result = json.loads(result_path.read_text())
            agent = config.get("agent") or {}
            reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
            exception = (result.get("exception_info") or {}).get("exception_type")
            context = result.get("agent_result") or {}
            arms[(agent.get("kwargs") or {}).get("arm") or agent.get("name") or "?"].append({
                "scenario": Path(config["task"]["path"]).name, "reward": reward, "exception": exception,
                "model": agent.get("model_name"), "cost": context.get("cost_usd"), "job": job.name,
                "user_cost": user_cost(trial / "agent" / "tau3_runtime_state.json")})
    return arms


def user_cost(state_path: Path) -> float | None:
    """Simulated-user spend: the cost tau2 stamps on each user message the sidecar logged."""
    if not state_path.exists():
        return None
    costs = [m.get("cost") for m in json.loads(state_path.read_text()).get("messages", []) if m.get("role") == "user"]
    return sum(c for c in costs if c) if costs else None


def pass_hat_k(per_task: dict[str, list[float]], k: int) -> float:
    vals = [comb(int(sum(r)), k) / comb(len(r), k) for r in per_task.values() if len(r) >= k]
    return sum(vals) / len(vals) if vals else math.nan


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", nargs="+", type=Path)
    ap.add_argument("--baseline", default="baseline")
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    arms = load(a.jobs)
    base = [t for t in arms.get(a.baseline, []) if t["reward"] is not None]
    rows = []
    print("| arm | model | tasks | graded attempts | solved | mean reward | 95% CI | infra errors | graded timeouts "
          "| paired vs baseline (points) | 95% CI | gained / lost | agent cost (USD) | user simulator cost (USD) |")
    print("|---|---|---|---|---|---|---|---|---|---|---|---|---|---|")
    for arm, trials in sorted(arms.items(), key=lambda kv: (kv[0] != a.baseline, kv[0])):
        graded = [t for t in trials if t["reward"] is not None]
        solved = sum(t["reward"] == 1.0 for t in graded)
        lo, hi = wilson(solved, len(graded))
        errors = sum(t["reward"] is None for t in trials)
        timeouts = sum(t["reward"] is not None and t["exception"] is not None for t in trials)
        costs = [t["cost"] for t in trials if t["cost"] is not None]
        paired = paired_delta(graded, base) if arm != a.baseline and base else None
        row = {"arm": arm, "model": trials[0]["model"], "tasks": len({t["scenario"] for t in trials}),
               "graded": len(graded), "solved": solved, "mean_reward": solved / len(graded) if graded else None,
               "wilson95": [lo, hi], "infra_errors": errors, "graded_timeouts": timeouts,
               "paired_vs_baseline": paired, "agent_cost_usd": sum(costs) if costs else None,
               "cost_known_for": len(costs),
               "user_simulator_cost_usd": sum(t["user_cost"] or 0.0 for t in trials)}
        per_task: dict[str, list[float]] = defaultdict(list)
        for t in graded:
            per_task[t["scenario"]].append(float(t["reward"]))
        row["pass_hat_k"] = {k: pass_hat_k(per_task, k) for k in range(1, max(map(len, per_task.values()), default=0) + 1)}
        rows.append(row)
        p = (f"{100 * paired['delta']:+.1f} | {100 * paired['lo']:+.1f} to {100 * paired['hi']:+.1f} | "
             f"{paired['flips_up']} / {paired['flips_down']}") if paired and paired["n"] else " | | "
        mean = f"{row['mean_reward']:.4f}" if graded else ""
        cost = f"{row['agent_cost_usd']:.4f} ({len(costs)} priced)" if costs else ""
        print(f"| {arm} | {row['model']} | {row['tasks']} | {len(graded)} | {solved} | {mean} | {lo:.4f}-{hi:.4f} | "
              f"{errors} | {timeouts} | {p} | {cost} | {row['user_simulator_cost_usd']:.4f} |")
    if any(len(r["pass_hat_k"]) > 1 for r in rows):
        print("\npass^k: " + "; ".join(f"{r['arm']}: " + ", ".join(f"k={k} {v:.4f}" for k, v in r["pass_hat_k"].items())
                                       for r in rows))
    if a.json:
        a.json.write_text(json.dumps({"jobs": [str(j) for j in a.jobs], "baseline": a.baseline, "arms": rows}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
