"""
The confirmatory tests fixed in PREREGISTRATION.md, on runs recorded after its commit.

    python confirmatory.py        # markdown to stdout

C1-C3: one-sided paired bootstrap over tasks (2000 resamples, seed 0) of a difference-in-
differences, Holm-corrected at alpha 0.05. C4: Spearman rho between a cell's median seconds per
agent step and its share of "out of time, still working" trials (and, as the contrast, its
"finished wrong" share), one-sided permutation p-value, over cells with >= 36 trials.
"""

import json
import random
import statistics
from collections import Counter, defaultdict

import _paths  # noqa: F401  (harness on sys.path)
import analysis as an
import experiment as ex
import trajectories as tj

PREREG_COMMIT_TIME = "2026-10-09T07:12:08"  # git log -1 --format=%cI on PREREGISTRATION.md
N_BOOT, SEED, ALPHA = 2000, 0, 0.05

# (claim, direction, (cell for mini after, mini before, terminus after, terminus before))
CLAIMS = [
    ("C1 GPU x harness: H200 vs H100 at c=32", +1,
     (("h200", 32, "H200"), ("defaults", 32, "H100!"))),
    ("C2 load x harness: c=32 vs c=16 on H100", -1,
     (("defaults", 32, "H100!"), ("defaults", 16, "H100!"))),
    ("C3 reasoning x harness: no-thinking vs defaults at c=32", +1,
     (("no-thinking", 32, "H100!"), ("defaults", 32, "H100!"))),
]


def new_rows():
    rows = [json.loads(l) for l in ex.ATTEMPTS.read_text().splitlines() if l.strip()]
    return [r for r in rows if r.get("valid") and r.get("trials") and r["ts"] > PREREG_COMMIT_TIME
            and r["task_set"] in ("full", "full-k2")]


def did_test(cells, after, before, direction):
    keys = [("mini-swe-agent", *after), ("mini-swe-agent", *before),
            ("terminus-2", *after), ("terminus-2", *before)]
    missing = [k for k in keys if k not in cells]
    if missing:
        return None, missing
    s = [an.success(cells[k]) for k in keys]
    tasks = sorted(set.intersection(*(set(x) for x in s)))
    d = [(s[0][k] - s[1][k]) - (s[2][k] - s[3][k]) for k in tasks]
    rng = random.Random(SEED)
    boots = [statistics.mean(rng.choice(d) for _ in d) for _ in range(N_BOOT)]
    p = sum(1 for b in boots if direction * b <= 0) / N_BOOT  # one-sided
    return (statistics.mean(d), sorted(boots)[int(0.025 * N_BOOT)], sorted(boots)[int(0.975 * N_BOOT)],
            p, len(tasks)), []


def holm(ps):
    order = sorted(range(len(ps)), key=lambda i: ps[i])
    adj, running = [None] * len(ps), 0.0
    for rank, i in enumerate(order):
        running = max(running, min(1.0, (len(ps) - rank) * ps[i]))
        adj[i] = running
    return adj


def spearman(x, y):
    def ranks(v):
        idx = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[idx[j + 1]] == v[idx[i]]:
                j += 1
            for k in range(i, j + 1):
                r[idx[k]] = (i + j) / 2
            i = j + 1
        return r
    return statistics.correlation(ranks(x), ranks(y))


def c4(rows):
    groups = defaultdict(lambda: {"step": [], "cls": Counter()})
    for r in rows:
        job = ex.JOBS_DIR / r["job_name"]
        key = (r["harness"], r["config"], r["concurrency"], r["gpu"])
        groups[key]["step"] += [t["agent_s"] / t["steps"] for t in r["trials"] if t.get("agent_s") and t.get("steps")]
        if not job.exists():  # published rows: classes precomputed from the trajectories
            for t in r["trials"]:
                groups[key]["cls"][t["failure_class"] or "solved"] += 1
        for d in job.glob("*/result.json"):
            groups[key]["cls"][tj.classify(d.parent) or "solved"] += 1
    cells = [(statistics.median(g["step"]), g["cls"]) for g in groups.values()
             if sum(g["cls"].values()) >= 36 and g["step"]]
    if len(cells) < 4:
        return None, len(cells)
    x = [c[0] for c in cells]
    out = {}
    for cls in ("out of time, working", "finished wrong"):
        y = [c[1][cls] / sum(c[1].values()) for c in cells]
        rho = spearman(x, y)
        rng = random.Random(SEED)
        perm = [spearman(x, rng.sample(y, len(y))) for _ in range(N_BOOT)]
        out[cls] = (rho, sum(1 for p in perm if p >= rho) / N_BOOT)
    return out, len(cells)


def main():
    rows = new_rows()
    cells = an.by_cell(rows)
    lines = ["# Confirmatory tests (PREREGISTRATION.md)", "",
             f"Runs recorded after {PREREG_COMMIT_TIME} UTC only: {len(rows)} runs.", "",
             "| claim | effect, pts (95% CI) | one-sided p | Holm-adjusted p | verdict |", "|---|---|---|---|---|"]
    results = []
    for name, direction, (after, before) in CLAIMS:
        res, missing = did_test(cells, after, before, direction)
        results.append((name, res, missing))
    ps = [r[1][3] for r in results if r[1]]
    adj = iter(holm(ps)) if ps else iter([])
    for name, res, missing in results:
        if not res:
            lines.append(f"| {name} | not yet tested (missing new runs: "
                         f"{', '.join(f'{h} {c} c={n} {g}' for h, c, n, g in missing)}) | | | |")
            continue
        a = next(adj)
        verdict = "confirmed" if a < ALPHA else "not confirmed"
        lines.append(f"| {name} | {100 * res[0]:+.0f} ({100 * res[1]:+.0f} to {100 * res[2]:+.0f}), "
                     f"{res[4]} tasks | {res[3]:.3f} | {a:.3f} | {verdict} |")
    out, n = c4(rows)
    lines += ["", "**C4** (failure mix follows server speed), over cells with >= 36 new trials: "
              + (f"not yet tested ({n} cells)." if out is None else
                 f"{n} cells. Spearman rho with median s/step: 'out of time, working' "
                 f"{out['out of time, working'][0]:+.2f} (p = {out['out of time, working'][1]:.3f}); "
                 f"'finished wrong' {out['finished wrong'][0]:+.2f} (p = {out['finished wrong'][1]:.3f}). "
                 + ("Confirmed." if out['out of time, working'][1] < ALPHA else "Not confirmed.")), ""]
    print("\n".join(lines))


if __name__ == "__main__":
    main()
