"""
Rebuild the computed tables of results/agentperf-infra.json from the published per-run rows and
compare them with the committed export. No network, no GPU, no Modal.

    python scripts/rebuild_export.py --tb-tasks <dir with terminal-bench/<task>/task.toml>

Rebuilt: results (every condition: n, correct, accuracy, ci95, costs, tokens, calls, failure
classes, peeked), per_type (Terminal-Bench difficulty from each task's task.toml), excluded_runs,
paired_comparisons (vs H100 defaults at 32 agents, harness interactions, GPU cost ratios, GAIA)
and the recorded-spend totals quoted in meta.total_spend_usd_note.
This is the original export's computation (benchmarks-export/scripts/infra_compute.py and
infra_paired.py), changed only to read failure classes from the rows' per-trial `failure_class`
instead of the raw trajectories, and task difficulty from a downloaded task directory.
Exit code 0 and "ALL MATCH" when every rebuilt value equals the committed one.
"""
import argparse
import json
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BENCH / "src"))
import analysis as an  # noqa: E402  (also puts the harness on sys.path)

MODEL = {"default": "Qwen/Qwen3.8-27B"}


def cond_key(r):
    return f"{r['harness']} | {r['config']} | c{r['concurrency']}"


def boot_ci(per_task, n_res=2000, seed=0):
    tasks = sorted(per_task)
    rng = random.Random(seed)
    vals = []
    for _ in range(n_res):
        s = [per_task[tasks[rng.randrange(len(tasks))]] for _ in tasks]
        vals.append(sum(a for a, _ in s) / sum(b for _, b in s))
    vals.sort()
    return [round(vals[int(0.025 * n_res)], 4), round(vals[int(0.975 * n_res) - 1], 4)]


def compute(rows, diff):
    infra = [r for r in rows if r["task_set"] in ("full", "full-k2", "gaia")]
    valid = [r for r in infra if r["valid"]]
    invalid = [r for r in infra if not r["valid"]]
    groups = defaultdict(list)
    for r in valid:
        bench = "gaia" if r["task_set"].startswith("gaia") else "terminal-bench-2.0"
        groups[(cond_key(r), bench)].append(r)
    results, per_type = defaultdict(list), defaultdict(dict)
    for (ck, bench), rs in sorted(groups.items()):
        n = sum(r["attempted"] for r in rs)
        correct = sum(r["solved"] for r in rs)
        gpu = sum(r["cost"] for r in rs)
        sbx = sum(r["sandbox_cost_est"] for r in rs)
        toks_in = sum(r["input_tokens"] for r in rs)
        toks_cached = sum(r["cached_tokens"] for r in rs)
        toks_out = sum(r["output_tokens"] for r in rs)
        steps = [t["steps"] for r in rs for t in r["trials"] if t.get("steps") is not None]
        per_task, fails, typ = defaultdict(lambda: [0, 0]), Counter(), defaultdict(lambda: [0, 0])
        for r in rs:
            for t in r["trials"]:
                per_task[t["task"]][0] += t["ok"]
                per_task[t["task"]][1] += 1
                short = t["task"].split("/")[-1]
                ty = f"terminal-bench-2.0/{diff.get(short)}" if bench != "gaia" else "gaia"
                typ[ty][0] += t["ok"]
                typ[ty][1] += 1
                fails[t["failure_class"] or "solved"] += 1
        assert sum(fails.values()) == n and fails["solved"] == correct, (ck, fails, n, correct)
        del fails["solved"]
        model = MODEL.get(rs[0]["model"], rs[0]["model"])
        results[ck].append({
            "model": model, "benchmark": bench, "gpu": rs[0]["gpu"].rstrip("!"), "runs": len(rs),
            "attempts_per_task": sorted({r.get("attempts_per_task", 1) for r in rs}),
            "n": n, "correct": correct, "accuracy": round(correct / n, 4),
            "ci95": boot_ci({k: tuple(v) for k, v in per_task.items()}),
            "per_run_solved": [f"{r['solved']}/{r['attempted']}" for r in rs],
            "cost_per_correct_cents": round(100 * (gpu + sbx) / correct, 4) if correct else None,
            "gpu_only_cost_per_correct_cents": round(100 * gpu / correct, 4) if correct else None,
            "gpu_cost_usd": round(gpu, 4), "sandbox_cost_est_usd": round(sbx, 4),
            "mean_tokens_per_case": round((toks_in + toks_out) / n, 1),
            "mean_input_tokens_per_case": round(toks_in / n, 1),
            "mean_cached_input_tokens_per_case": round(toks_cached / n, 1),
            "mean_output_tokens_per_case": round(toks_out / n, 1),
            "mean_calls_per_case": round(sum(steps) / len(steps), 2) if steps else None,
            "calls_counted_trials": len(steps),
            "failures": dict(sorted(fails.items())),
            "peeked_trials": sum(r.get("peeked", 0) for r in rs),
        })
        per_type[ck].setdefault(model, {})
        for ty, (c, m) in sorted(typ.items()):
            per_type[ck][model][ty] = {"n": m, "correct": c, "accuracy": round(c / m, 4)}
        tb = [(c, m) for ty, (c, m) in typ.items() if ty.startswith("terminal")]
        if tb:
            c, m = sum(x for x, _ in tb), sum(y for _, y in tb)
            per_type[ck][model]["terminal-bench-2.0"] = {"n": m, "correct": c, "accuracy": round(c / m, 4)}
    excluded = [{"condition": cond_key(r), "task_set": r["task_set"], "ts": r["ts"], "attempted": r["attempted"],
                 # the public rows mark removed deploy output; the export quoted only the first line
                 "reason": r["error"].split("\n")[0].split("; see")[0].replace(" [command output removed]", "")[:160]}
                for r in invalid]
    quick = [r for r in rows if r["task_set"] == "quick"]
    totals = {"gpu_cost_all_infra_records_usd": round(sum(r["cost"] or 0 for r in infra + quick), 4),
              "startup_cost_all_infra_records_usd": round(sum(r["startup_cost"] or 0 for r in infra + quick), 4),
              "sandbox_est_all_infra_records_usd": round(sum(r.get("sandbox_cost_est") or 0 for r in infra + quick), 4)}
    return dict(results), dict(per_type), excluded, totals


def paired():
    out = {"vs_h100_defaults_c32": [], "interactions_mini_minus_terminus": [], "cost_ratio_vs_h100_c32": [], "gaia": []}
    for ts, key in ((("full", "full-k2"), "tb"), (("gaia",), "gaia")):
        rows = an.load(ts)
        cells = an.by_cell(rows)
        S = {k: an.success(v) for k, v in cells.items()}
        base = ("defaults", 32, "H100!")
        changes = [("b200", 32, "B200"), ("h200", 32, "H200"), ("defaults", 16, "H100!"), ("kv-fp8", 32, "H100!"),
                   ("weights-fp8", 32, "H100!"), ("moe-a3b", 32, "H100!"), ("spec-mtp", 32, "H100!"),
                   ("no-prefix-cache", 32, "H100!"), ("no-thinking", 32, "H100!"), ("h200-spec-mtp", 32, "H200"),
                   ("defaults-2x-time", 32, "H100!"), ("defaults-4x-time", 32, "H100!"),
                   ("defaults", 8, "H100!"), ("defaults", 48, "H100!"), ("defaults", 64, "H100!")]
        for ch in changes:
            row = {"change": f"{ch[0]} c{ch[1]} {ch[2].rstrip('!')}", "baseline": "defaults c32 H100"}
            ok = False
            for h in ("mini-swe-agent", "terminus-2"):
                a, b = S.get((h,) + ch), S.get((h,) + base)
                if a and b:
                    p, lo, hi, n = an.paired_ci(a, b)
                    row[h] = {"diff_pts": round(100 * p, 2), "ci95_pts": [round(100 * lo, 2), round(100 * hi, 2)], "tasks": n}
                    ok = True
            if ok and all(((h,) + ch) in S for h in ("mini-swe-agent", "terminus-2")):
                r = an.interaction_ci(S[("mini-swe-agent",) + ch], S[("mini-swe-agent",) + base],
                                      S[("terminus-2",) + ch], S[("terminus-2",) + base])
                row["interaction_mini_minus_terminus"] = {"diff_pts": round(100 * r[0], 2),
                                                          "ci95_pts": [round(100 * r[1], 2), round(100 * r[2], 2)], "tasks": r[3]}
            if ok:
                out["vs_h100_defaults_c32" if key == "tb" else "gaia"].append(row)
        gpus = (("b200", 32, "B200"), ("h200", 32, "H200")) if key == "tb" else (("h200", 32, "H200"),)
        for h in ("mini-swe-agent", "terminus-2"):
            for g in gpus:
                r = an.cost_ratio(rows, (h,) + g, (h,) + base)
                out["cost_ratio_vs_h100_c32"].append({"harness": h, "gpu": g[2], "ratio": round(r[0], 4),
                                                      "ci95": [round(r[1], 4), round(r[2], 4)],
                                                      "benchmark": "terminal-bench-2.0" if key == "tb" else "gaia"})
    return out


def diff_values(a, b, path, out):
    if isinstance(a, dict) and isinstance(b, dict):
        for k in sorted(set(a) | set(b)):
            if k not in a or k not in b:
                out.append(f"{path}.{k}: only in {'rebuilt' if k in a else 'export'}")
            else:
                diff_values(a[k], b[k], f"{path}.{k}", out)
    elif isinstance(a, list) and isinstance(b, list) and len(a) == len(b):
        for i, (x, y) in enumerate(zip(a, b)):
            diff_values(x, y, f"{path}[{i}]", out)
    elif a != b:
        out.append(f"{path}: rebuilt {a!r} != export {b!r}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tb-tasks", required=True, help="dir holding terminal-bench/<task>/task.toml (harbor download)")
    ap.add_argument("--export", default=str(BENCH / "results" / "agentperf-infra.json"))
    a = ap.parse_args()
    diff = {}
    for f in Path(a.tb_tasks).glob("**/task.toml"):
        m = re.search(r'^difficulty\s*=\s*"(\w+)"', f.read_text(), re.M)
        diff[f.parent.name] = m.group(1) if m else None
    rows = [json.loads(l) for l in an.ATTEMPTS.read_text().splitlines() if l.strip()]
    results, per_type, excluded, totals = compute(rows, diff)
    exp = json.load(open(a.export))
    problems = []
    diff_values(results, exp["results"], "results", problems)
    diff_values(per_type, exp["per_type"], "per_type", problems)
    diff_values(excluded, exp["excluded_runs"], "excluded_runs", problems)
    p = paired()
    for k in ("vs_h100_defaults_c32", "cost_ratio_vs_h100_c32", "gaia"):
        diff_values(p[k], exp["paired_comparisons"][k], f"paired_comparisons.{k}", problems)
    note = exp["meta"]["total_spend_usd_note"]
    for label, v in (("GPU run time", totals["gpu_cost_all_infra_records_usd"]),
                     ("GPU startup", totals["startup_cost_all_infra_records_usd"]),
                     ("estimated sandboxes", totals["sandbox_est_all_infra_records_usd"])):
        if f"{label} ${v:.4f}" not in note:
            problems.append(f"meta.total_spend_usd_note: '{label} ${v:.4f}' not found")
    n_cells = sum(len(v) for v in results.values())
    print(f"conditions rebuilt: {len(results)} ({n_cells} condition x benchmark cells); "
          f"trials: {sum(e['n'] for v in results.values() for e in v)}; "
          f"paired rows: {len(p['vs_h100_defaults_c32'])} TB + {len(p['gaia'])} GAIA; "
          f"cost ratios: {len(p['cost_ratio_vs_h100_c32'])}; recorded spend: {totals}")
    if problems:
        print(f"{len(problems)} MISMATCHES:")
        print("\n".join(problems[:200]))
        sys.exit(1)
    print("ALL MATCH")


if __name__ == "__main__":
    main()
