"""
Is the score a time budget set by the server? Analyses on the per-trial records in
attempts.jsonl (no GPU, no Modal).

    python analysis.py            # prints all analyses as markdown

1. speed: per harness, how much slower or faster each config's agent steps are than the
   reference (c=16 defaults on H100), paired by task: median over tasks of
   (agent seconds / step in config) / (same in reference).
2. counterfactual: from a run with a generous time limit (defaults-4x-time), each task's
   uncapped time to solve. A config with speed factor f is predicted to solve the tasks
   whose uncapped solve time x f fits the task's normal limit. Compared with what the
   config actually solved: if speed alone predicts the score, the score is a time budget.
3. paired: solves in config vs reference on the same tasks, with a paired bootstrap 95% CI
   for the difference in success rate (tasks resampled; repeats/attempts pooled per task).
"""

import json
import random
import statistics
from collections import defaultdict
from pathlib import Path

import _paths  # noqa: E402  (harness on sys.path; published rows by default)

ATTEMPTS = _paths.ATTEMPTS
REF = ("defaults", 16, "H100!")
UNCAPPED = "defaults-4x-time"


def load(task_sets=("full", "full-k2")) -> list[dict]:
    rows = [json.loads(l) for l in ATTEMPTS.read_text().splitlines() if l.strip()]
    return [r for r in rows if r.get("valid") and r.get("trials") and r["task_set"] in task_sets]


def by_cell(rows) -> dict:
    """(harness, config, concurrency, gpu) -> trials pooled over repeats and attempts."""
    cells = defaultdict(list)
    for r in rows:
        cells[(r["harness"], r["config"], r["concurrency"], r["gpu"])].extend(r["trials"])
    return cells


def per_task(trials, f) -> dict:
    out = defaultdict(list)
    for t in trials:
        v = f(t)
        if v is not None:
            out[t["task"]].append(v)
    return out


def step_s(t):
    return t["agent_s"] / t["steps"] if t.get("agent_s") and t.get("steps") else None


def speed_factor(cell_trials, ref_trials) -> tuple[float | None, int]:
    """Median over shared tasks of mean step time in cell / in reference."""
    a, b = per_task(cell_trials, step_s), per_task(ref_trials, step_s)
    ratios = [statistics.mean(a[k]) / statistics.mean(b[k]) for k in a.keys() & b.keys()]
    return (statistics.median(ratios), len(ratios)) if ratios else (None, 0)


def task_limits(rows) -> dict:
    """A task's normal agent time limit = the longest timed-out trial at 1x (if any)."""
    lim = defaultdict(float)
    for r in rows:
        if r["config"] in ("defaults-2x-time", UNCAPPED):
            continue
        for t in r["trials"]:
            if t.get("exc") == "AgentTimeoutError" and t.get("agent_s"):
                lim[t["task"]] = max(lim[t["task"]], t["agent_s"])
    return lim


def success(trials) -> dict:
    """task -> share of its trials solved."""
    out = defaultdict(list)
    for t in trials:
        if t.get("agent_s") is not None or t.get("exc"):  # attempted
            out[t["task"]].append(1.0 if t["ok"] else 0.0)
    return {k: statistics.mean(v) for k, v in out.items()}


def paired_ci(a: dict, b: dict, n=2000, seed=0):
    """Difference in mean success (a - b) over shared tasks, with a bootstrap 95% CI."""
    tasks = sorted(a.keys() & b.keys())
    if not tasks:
        return None
    d = [a[k] - b[k] for k in tasks]
    rng = random.Random(seed)
    boots = sorted(statistics.mean(rng.choice(d) for _ in d) for _ in range(n))
    return statistics.mean(d), boots[int(0.025 * n)], boots[int(0.975 * n)], len(tasks)


def interaction_ci(a1, a0, b1, b0, n=2000, seed=0):
    """Difference-in-differences over tasks shared by all four cells:
    (a1 - a0) - (b1 - b0), e.g. how much more harness A loses than B from the same change."""
    tasks = sorted(a1.keys() & a0.keys() & b1.keys() & b0.keys())
    if not tasks:
        return None
    d = [(a1[k] - a0[k]) - (b1[k] - b0[k]) for k in tasks]
    rng = random.Random(seed)
    boots = sorted(statistics.mean(rng.choice(d) for _ in d) for _ in range(n))
    return statistics.mean(d), boots[int(0.025 * n)], boots[int(0.975 * n)], len(tasks)


def cost_ratio(rows, a, b, n=2000, seed=0):
    """(real cost per solve in cell a) / (in cell b), cost per trial fixed, solves bootstrapped by task."""
    def cell(key):
        rs = [r for r in rows if (r["harness"], r["config"], r["concurrency"], r["gpu"]) == key]
        cost = sum((r["cost"] or 0) + (r.get("sandbox_cost_est") or 0) for r in rs)
        return cost / sum(r["attempted"] for r in rs), success([t for r in rs for t in r["trials"]])
    (ca, sa), (cb, sb) = cell(a), cell(b)
    tasks = sorted(sa.keys() & sb.keys())

    def ratio(ts):
        pa, pb = statistics.mean(sa[t] for t in ts), statistics.mean(sb[t] for t in ts)
        return (ca / pa) / (cb / pb) if pa and pb else float("inf")
    rng = random.Random(seed)
    boots = sorted(ratio([rng.choice(tasks) for _ in tasks]) for _ in range(n))
    return ratio(tasks), boots[int(0.025 * n)], boots[int(0.975 * n) - 1]


def fmt_pts(x):
    return f"{100 * x:+.0f}"


def main():
    import sys
    sets = tuple(sys.argv[1:]) or ("full", "full-k2")
    rows = load(sets)
    cells = by_cell(rows)
    limits = task_limits(rows)
    out = ["# Is the score a time budget set by the server?", "", f"Task sets: {', '.join(sets)}.", ""]
    for h in sorted({k[0] for k in cells}):
        ref = cells.get((h, *REF[:2], REF[2]))
        if not ref:
            continue
        unc = [t for (hh, c, n, g), ts in cells.items() if hh == h and c == UNCAPPED and n == 16 for t in ts]
        f_unc = speed_factor(unc, ref)[0] if unc else None
        solve_time = {}  # task -> uncapped time to solve (only tasks solved uncapped)
        for t in unc:
            if t["ok"] and t.get("agent_s"):
                solve_time[t["task"]] = min(solve_time.get(t["task"], 1e9), t["agent_s"])
        out += [f"## {h}", "",
                f"Reference: {REF[0]} at c={REF[1]} on {REF[2]}. Uncapped run: "
                + (f"{len(unc)} trials, {len(solve_time)} tasks solved." if unc else "not yet."), ""]
        hdr = ["config", "c", "gpu", "trials", "speed factor (step time vs ref)",
               "solved (observed)", "predicted from speed", "success vs ref, pts (95% CI)"]
        lines = []
        ref_succ = success(ref)
        for (hh, c, n, g), ts in sorted(cells.items(), key=lambda kv: (kv[0][1] != "defaults", kv[0][2], kv[0][1])):
            if hh != h:
                continue
            f, npairs = speed_factor(ts, ref)
            succ = success(ts)
            observed = sum(succ.values())
            pred = "-"
            if solve_time and f and f_unc and c != UNCAPPED:
                # Uncapped solve times were measured at the uncapped run's own speed (longer runs
                # keep the server busier), so rescale them to this cell's speed.
                mult = 2.0 if c == "defaults-2x-time" else 1.0
                pred_n = sum(1 for k in succ if k in solve_time
                             and solve_time[k] * f / f_unc <= mult * limits.get(k, 1e9))
                pred = f"{pred_n} of {len(succ)}"
            ci = paired_ci(succ, ref_succ) if (c, n, g) != (REF[0], REF[1], REF[2]) else None
            lines.append([c, str(n), g, str(len(ts)), "-" if f is None else f"{f:.2f} ({npairs} tasks)",
                          f"{observed:.1f} of {len(succ)} tasks", pred,
                          "-" if not ci else f"{fmt_pts(ci[0])} ({fmt_pts(ci[1])} to {fmt_pts(ci[2])}), {ci[3]} tasks"])
        out += ["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
        out += ["| " + " | ".join(l) + " |" for l in lines] + [""]
        pairs = [(float(l[5].split()[0]), float(l[6].split()[0])) for l in lines if l[6] != "-"]
        if len(pairs) >= 3:
            obs, pred = zip(*pairs)
            mae = statistics.mean(abs(o - p) for o, p in pairs)
            base = statistics.mean(abs(o - statistics.mean(obs)) for o in obs)
            r = statistics.correlation(obs, pred) if len(set(pred)) > 1 else float("nan")
            out += [f"Speed-only prediction over {len(pairs)} cells: mean error {mae:.1f} tasks "
                    f"(predicting every cell's mean instead: {base:.1f}); correlation r = {r:.2f}.", ""]
        if unc:
            to = [t for t in ref if t.get("exc") == "AgentTimeoutError" and not t["ok"]]
            unc_ok = {t["task"] for t in unc if t["ok"]}
            conv = sum(1 for t in to if t["task"] in unc_ok)
            out += [f"Of {len(to)} reference trials that ran out of time, {conv} were solved in the "
                    f"uncapped run ({UNCAPPED}).", ""]
    # Same infra change, different harnesses: does it hurt one more than the other?
    harnesses = sorted({k[0] for k in cells})
    changes = sorted({(c, n, g) for (h, c, n, g) in cells if c != UNCAPPED})
    # Baselines: the reference, and defaults on H100 at the change's own concurrency (so a
    # GPU or flag change is compared at equal load).
    rows_i = []
    for i, ha in enumerate(harnesses):
        for hb in harnesses[i + 1:]:
            for ch in changes:
                for base in {REF, ("defaults", ch[1], "H100!")}:
                    if ch == base:
                        continue
                    cells_needed = [(ha, *ch), (ha, *base), (hb, *ch), (hb, *base)]
                    if all(k in cells for k in cells_needed):
                        ci = interaction_ci(*(success(cells[k]) for k in cells_needed))
                        if ci:
                            rows_i.append([f"{ch[0]} c={ch[1]} {ch[2]}", f"{base[0]} c={base[1]} {base[2]}",
                                           f"{ha} minus {hb}",
                                           f"{fmt_pts(ci[0])} ({fmt_pts(ci[1])} to {fmt_pts(ci[2])}), {ci[3]} tasks"])
    if rows_i:
        out += ["## Harness x infra interaction", "",
                "Change in success from the same infra change (vs the reference) for one harness "
                "minus the other, paired by task, bootstrap 95% CI. A CI excluding 0 means the infra "
                "change affects the harnesses differently.", "",
                "| infra change | vs baseline | harnesses | difference of changes, pts (95% CI) |",
                "|---|---|---|---|"]
        out += ["| " + " | ".join(r) + " |" for r in rows_i] + [""]
    # Real cost per solved task, other GPUs vs the H100 at the same load: ratio with a task bootstrap.
    rows_g = []
    for (h, c, n, g), ts in sorted(cells.items()):
        if c in ("h200", "b200") and (h, "defaults", n, "H100!") in cells:
            ra = cost_ratio(rows, (h, c, n, g), (h, "defaults", n, "H100!"))
            if ra:
                rows_g.append([h, f"{g} vs H100", str(n), f"{ra[0]:.2f} ({ra[1]:.2f} to {ra[2]:.2f})",
                               "cheaper" if ra[2] < 1 else "dearer" if ra[1] > 1 else "no clear difference"])
    if rows_g:
        out += ["## Real cost per solved task by GPU", "",
                "Ratio of real cost per solve (GPU + sandboxes) on the bigger GPU to the H100 at the same "
                "number of agents; cost per trial fixed, solves resampled by task (2000 resamples, 95% CI).", "",
                "| harness | GPU | agents | ratio (95% CI) | verdict |", "|---|---|---|---|---|"]
        out += ["| " + " | ".join(r) + " |" for r in rows_g] + [""]
    out += ["Solved (observed) counts tasks fractionally when a cell has several trials per task "
            "(repeats or 2 attempts). Predicted from speed needs an uncapped run for the harness.", ""]
    print("\n".join(out))


if __name__ == "__main__":
    main()
