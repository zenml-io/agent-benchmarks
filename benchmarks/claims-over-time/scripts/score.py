"""Score claims agent rows against the real rulings, per batch and cumulative.

    uv run python scripts/score.py work/runs/v1-b1.jsonl work/runs/v1-b2.jsonl
    uv run python scripts/score.py work/runs/v1-b1.jsonl --cases work/cases.jsonl --ids MN25-1,MN25-2

Reads rows written by run_batch.py (or the episode) and $CLAIMS_WORK_DIR/cases.jsonl (for `truth`
and `batch`). When an appeal has several rows, the last one counts. A row with no submitted decision
is undecided, and undecided counts as wrong in both accuracies. Balanced accuracy is the mean of the
accuracy on appeals the reviewer upheld and on appeals the reviewer overturned (over the outcomes
present). The 95% interval resamples appeals with replacement (2000 draws, fixed seed).
Wrongful denial: the agent upheld a denial the reviewer overturned. Wrongful approval: the agent
overturned a denial the reviewer upheld. Uses only the standard library.
"""

import argparse
import json
import os
import random
from pathlib import Path
from typing import Any

BENCH = Path(__file__).resolve().parent.parent
OUTCOMES = ("uphold", "overturn")


def jl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open() if line.strip()]


def decision_of(row: dict[str, Any]) -> str | None:
    final = row.get("final")
    d = final.get("decision") if isinstance(final, dict) else None
    return d if d in OUTCOMES else None


def balanced(pairs: list[tuple[str | None, str]]) -> float:
    """Mean over the true outcomes present of the share decided correctly; `pairs` are (decision, truth)."""
    per = [[d == t for d, t in pairs if t == o] for o in OUTCOMES]
    return sum(sum(x) / len(x) for x in per if x) / sum(1 for x in per if x)


def metrics(pairs: list[tuple[str | None, str]], draws: int = 2000, seed: int = 0) -> dict[str, Any]:
    n = len(pairs)
    if not n:
        return {"n": 0}
    rng = random.Random(seed)
    boots = sorted(balanced([rng.choice(pairs) for _ in pairs]) for _ in range(draws))
    return {"n": n, "decided": sum(d is not None for d, _ in pairs),
            "accuracy": sum(d == t for d, t in pairs) / n, "balanced_accuracy": balanced(pairs),
            "ci95": (boots[int(0.025 * draws)], boots[int(0.975 * draws) - 1]),
            "wrongful_denials": sum(d == "uphold" and t == "overturn" for d, t in pairs),
            "wrongful_approvals": sum(d == "overturn" and t == "uphold" for d, t in pairs)}


def score(rows: list[dict[str, Any]], cases: dict[str, dict[str, Any]]) -> list[tuple[str, dict[str, Any]]]:
    """Per-batch then cumulative metrics, in batch order; rows for appeals not in `cases` are ignored."""
    last = {r["case_id"]: r for r in rows if r.get("case_id") in cases}
    by_batch: dict[int, list[tuple[str | None, str]]] = {}
    for cid, r in last.items():
        by_batch.setdefault(cases[cid]["batch"], []).append((decision_of(r), cases[cid]["truth"]))
    out, upto = [], []
    for b in sorted(by_batch):
        upto += by_batch[b]
        out += [(f"batch {b}", metrics(by_batch[b])), (f"batches <= {b}", metrics(list(upto)))]
    return out


def table(results: list[tuple[str, dict[str, Any]]]) -> str:
    lines = ["| scope | n | decided | accuracy | balanced accuracy (95% CI) | wrongful denials | wrongful approvals |",
             "|---|---|---|---|---|---|---|"]
    for label, m in results:
        lo, hi = m["ci95"]
        lines.append(f"| {label} | {m['n']} | {m['decided']} | {100 * m['accuracy']:.1f}% | "
                     f"{100 * m['balanced_accuracy']:.1f}% ({100 * lo:.1f} to {100 * hi:.1f}) | "
                     f"{m['wrongful_denials']} | {m['wrongful_approvals']} |")
    return "\n".join(lines)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("rows", nargs="+", type=Path, help="JSONL files of result rows")
    ap.add_argument("--cases", type=Path, default=Path(os.environ.get("CLAIMS_WORK_DIR") or BENCH / "work") / "cases.jsonl")
    ap.add_argument("--ids", help="comma-separated appeal ids to restrict to (for example the revealed ones)")
    ap.add_argument("--json", action="store_true", help="print JSON instead of a table")
    a = ap.parse_args()
    cases = {c["id"]: c for c in jl(a.cases)}
    if a.ids:
        keep = set(a.ids.split(","))
        cases = {k: v for k, v in cases.items() if k in keep}
    rows = [r for path in a.rows for r in jl(path)]
    results = score(rows, cases)
    skipped = len({r.get("case_id") for r in rows} - set(cases))
    print(json.dumps(dict(results), indent=1) if a.json else table(results))
    if skipped:
        print(f"\n{skipped} appeal(s) in the rows are not in {a.cases}{' or --ids' if a.ids else ''}; ignored.")


if __name__ == "__main__":
    main()
