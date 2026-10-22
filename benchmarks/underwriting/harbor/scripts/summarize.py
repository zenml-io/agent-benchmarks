"""Summarize Harbor jobs of the underwriting tasks: accuracy per setup, with infrastructure errors counted apart.

  python scripts/summarize.py <job dir> [<job dir> ...] [--by-type] [--baseline <setup label>]

A setup is (agent name, model). For each: attempts, correct, wrong, infrastructure errors (trial exceptions, an
unreachable MCP server, simulator or judge API failures; excluded from accuracy, re-run them), accuracy over scored
attempts, mean reward per case (averaged over its attempts), and spend per scored attempt: agent (as the agent
reports it), simulated underwriter and judges (both from grading.json). With --baseline, a paired bootstrap 95% interval
of the per-case accuracy difference against that setup (cases both setups scored). Markdown to stdout.
"""
import argparse
import json
import random
from collections import defaultdict
from pathlib import Path


def load(job_dirs):
    rows = []
    for job in job_dirs:
        for p in sorted(Path(job).glob("*/result.json")):
            r = json.loads(p.read_text())
            gpath = p.parent / "verifier" / "grading.json"
            g = json.loads(gpath.read_text()) if gpath.exists() else {}
            agent = r.get("agent_info") or {}
            ar = r.get("agent_result") or {}
            reward = ((r.get("verifier_result") or {}).get("rewards") or {}).get("reward")
            exc = (r.get("exception_info") or {}).get("exception_type")
            infra = exc or g.get("infra_error") or (None if reward is not None else "no reward")
            rows.append(dict(
                setup=f"{(r.get('config') or {}).get('agent', {}).get('name') or agent.get('name')} / "
                      f"{(agent.get('model_info') or {}).get('name') or (r.get('config') or {}).get('agent', {}).get('model_name')}",
                case=r["task_name"].split("underwriting-")[-1], task_type=g.get("task_type"), reward=reward,
                infra=infra, agent_cost=ar.get("cost_usd") or 0.0, sim_cost=g.get("sim_cost") or 0.0,
                judge_cost=g.get("judge_cost") or 0.0))
    return rows


def per_case(rows):
    acc = defaultdict(list)
    for r in rows:
        if not r["infra"]:
            acc[r["case"]].append(r["reward"])
    return {c: sum(v) / len(v) for c, v in acc.items()}


def paired_ci(a, b, n=4000, seed=0):
    cases = sorted(set(a) & set(b))
    if not cases:
        return None
    rng = random.Random(seed)
    diffs = [a[c] - b[c] for c in cases]
    point = sum(diffs) / len(diffs)
    boots = sorted(sum(rng.choice(diffs) for _ in diffs) / len(diffs) for _ in range(n))
    return point, boots[int(0.025 * n)], boots[int(0.975 * n)], len(cases)


def table(rows, baseline=None):
    by = defaultdict(list)
    for r in rows:
        by[r["setup"]].append(r)
    base = per_case(by[baseline]) if baseline else None
    out = ["| Setup | Attempts | Correct | Wrong | Infra errors | Accuracy | Cases | Agent $/attempt | Simulator $/attempt "
           "| Judges $/attempt | Δ vs baseline, pts [95% CI] |", "|" + "---|" * 11]
    for setup, rs in sorted(by.items()):
        scored = [r for r in rs if not r["infra"]]
        correct = sum(r["reward"] == 1 for r in scored)
        n = max(len(scored), 1)
        delta = ""
        if base is not None and setup != baseline:
            ci = paired_ci(per_case(rs), base)
            delta = f"{ci[0] * 100:+.1f} [{ci[1] * 100:+.1f}, {ci[2] * 100:+.1f}] (n={ci[3]})" if ci else "no overlap"
        out.append(f"| {setup} | {len(rs)} | {correct} | {len(scored) - correct} | {len(rs) - len(scored)} | "
                   f"{correct / n:.4f} | {len(per_case(rs))} | {sum(r['agent_cost'] for r in scored) / n:.5f} | "
                   f"{sum(r['sim_cost'] for r in scored) / n:.5f} | {sum(r['judge_cost'] for r in scored) / n:.5f} | "
                   f"{delta} |")
    return "\n".join(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("jobs", nargs="+")
    ap.add_argument("--by-type", action="store_true")
    ap.add_argument("--baseline", default=None, help='setup label as printed, e.g. "copilot-first / haiku-5.5"')
    a = ap.parse_args()
    rows = load(a.jobs)
    print(table(rows, a.baseline))
    if a.by_type:
        for typ in sorted({r["task_type"] for r in rows if r["task_type"]}):
            print(f"\n### {typ}\n")
            print(table([r for r in rows if r["task_type"] == typ], a.baseline))
    infra = [r for r in rows if r["infra"]]
    if infra:
        print("\nInfrastructure errors (re-run these):")
        for r in infra:
            print(f"- {r['setup']} {r['case']}: {r['infra']}")


if __name__ == "__main__":
    main()
