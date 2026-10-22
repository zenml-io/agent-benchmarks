"""
Rebuild the computed tables of results/ml-training-ops.json from the published rows and compare
them with the committed export. No network, no GPU, no API calls.

    python scripts/rebuild_export.py

Rows: results/runs/attempts.jsonl (self-hosted runs, one row per run with per-trial results),
results/runs/api_attempts.jsonl and api_attempts_anthropic.jsonl (vendor-API runs).
Rebuilt: results (every condition), per_type, excluded_runs, paired_comparisons, and the recorded
spend figures quoted in meta.total_spend_usd_note. Same computation as the original export script
(benchmarks-export/scripts/build_mlops.py); the paired comparisons read per-task solves from the
rows' per-trial `ok` instead of the raw reward.txt files (identical for every run; checked before
publishing). Exit code 0 and "ALL MATCH" when every rebuilt value equals the committed one.
Also prints the sandbox estimate re-priced at the tasks' requested CPU and memory (see README.md,
Trust status: the recorded estimate assumed 1 CPU / 2 GiB for these local tasks).
"""
import json
import os
import random
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
RUNS = BENCH / "results" / "runs"
os.environ.setdefault("ATTEMPTS_FILE", str(RUNS / "attempts.jsonl"))
sys.path.insert(0, str(BENCH / "src"))
import mlops_hard_analysis as mha  # noqa: E402

FAMILY = {
    "ddp-replica-drift": "A. distributed jobs", "uneven-shard-hang": "A. distributed jobs",
    "straggler-diagnosis": "B. diagnosis from telemetry", "corrupt-shard": "B. diagnosis from telemetry",
    "two-stragglers": "B. diagnosis from telemetry",
    "atomic-checkpoint": "C. checkpointing and recovery", "reshard-optimizer": "C. checkpointing and recovery",
    "exact-resume": "C. checkpointing and recovery",
    "k8s-unschedulable": "D. resource limits and scheduling", "memory-leak-oom": "D. resource limits and scheduling",
    "k8s-quota-zone": "D. resource limits and scheduling",
    **{t: "v1 pilot (script-level bugs)" for t in ["nan-loss", "label-shuffle", "resume-checkpoint", "oom-grad-accum", "ddp-sharding", "eval-mode"]},
    **{t: "v3 (designed frontier-hard)" for t in ["regression-bisect", "throughput-sla", "ray-exactly-once", "gang-controller", "elastic-churn"]},
    **{t: "real-system (torchtitan, 2 GPUs)" for t in ["titan-fork-drift", "titan-silent-divergence"]},
}
HARD8 = set(mha.TASKS)
TASKSET_LABEL = {"mlops-k5": "v1 pilot (6 tasks)", "mlops_hard-k3": "hard set (8 tasks)", "mlops_hard2-k6": "v2 set (4 tasks)"}
MODEL_SELF = {"default": "Qwen/Qwen3.8-27B"}
CFG = {"defaults": "vLLM defaults on an H100", "h200": "vLLM defaults on an H200", "no-thinking": "reasoning off, H100",
       "defaults-2x-time": "defaults on an H100, agent time limit doubled (60 min)", "moe-a3b": "MoE model Qwen/Qwen3.6-35B-A3B-FP8 on an H100",
       "max-out-4k": "server caps output at 4,096 tokens per call, H100", "max-out-8k": "server caps output at 8,192 tokens per call, H100",
       "max-out-16k": "server caps output at 16,384 tokens per call, H100"}


def boot_ci(per_task, n=2000, seed=0):
    ids, rng = sorted(per_task), random.Random(seed)
    if len(ids) < 2:
        return None
    vals = sorted(sum(per_task[t][0] for t in s) / sum(per_task[t][1] for t in s)
                  for s in ([ids[rng.randrange(len(ids))] for _ in ids] for _ in range(n)))
    return [round(vals[int(0.025 * n)], 4), round(vals[int(0.975 * n) - 1], 4)]


def classify(t):
    if t["ok"]:
        return None
    exc = t.get("exc")
    if exc == "AgentTimeoutError":
        return "timeout"
    if exc is None:
        return "finished wrong"
    if exc == "NonZeroAgentExitCodeError":
        return "agent exited with error"
    return f"other error ({exc})"


def task_resources():
    """(cpus, GiB) each task requests, from the task sources (for the re-priced sandbox estimate)."""
    out = {}
    for f in list((BENCH / "tasks").glob("mlops_tasks/*/task.toml")) + [BENCH / "tasks/mlops_hard/_task.toml"] \
            + list((BENCH / "tasks").glob("mlops_hard/src/*/task.toml.full")):
        t = f.read_text()
        cpus = float(re.search(r"^cpus\s*=\s*([0-9.]+)", t, re.M).group(1))
        gib = float(re.search(r'^memory\s*=\s*"([0-9.]+)G"', t, re.M).group(1))
        name = f.parent.name if f.name != "_task.toml" else "_hard"
        out[name] = (cpus, gib)
    return out


def self_hosted(rows):
    ml = [r for r in rows if r["task_set"].startswith("mlops")]
    excluded = [{"task_set": r["task_set"], "harness": r["harness"], "config": r["config"], "concurrency": r["concurrency"],
                 "ts": r["ts"], "attempted": r["attempted"], "reason": r["error"].split("; see")[0][:160]}
                for r in ml if not r["valid"]]
    groups = defaultdict(list)
    for r in ml:
        if r["valid"]:
            groups[(r["task_set"], r["harness"], r["config"], r["concurrency"])].append(r)
    results, per_type, gpu_tot, sbx_tot = {}, {}, 0.0, 0.0
    for (ts, h, cfg, c), rs in sorted(groups.items()):
        name = f"self-hosted | {TASKSET_LABEL[ts]} | {h} | {cfg} | c{c}"
        n = sum(r["attempted"] for r in rs)
        corr = sum(r["solved"] for r in rs)
        gpu = sum(r["cost"] for r in rs)
        sbx = sum(r["sandbox_cost_est"] for r in rs)
        gpu_tot += gpu
        sbx_tot += sbx
        pt, typ, fails, steps = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), Counter(), []
        for r in rs:
            for t in r["trials"]:
                pt[t["task"]][0] += t["ok"]; pt[t["task"]][1] += 1
                typ[FAMILY[t["task"]]][0] += t["ok"]; typ[FAMILY[t["task"]]][1] += 1
                f = classify(t)
                if f:
                    fails[f] += 1
                if t.get("steps") is not None:
                    steps.append(t["steps"])
        model = MODEL_SELF.get(rs[0]["model"], rs[0]["model"])
        results[name] = [{
            "model": model, "gpu": rs[0]["gpu"].rstrip("!"), "runs": len(rs), "n": n, "correct": corr, "accuracy": round(corr / n, 4),
            "ci95": boot_ci({k: tuple(v) for k, v in pt.items()}),
            "per_run_solved": [f"{r['solved']}/{r['attempted']}" for r in rs],
            "cost_per_correct_cents": round(100 * (gpu + sbx) / corr, 4) if corr else None,
            "gpu_only_cost_per_correct_cents": round(100 * gpu / corr, 4) if corr else None,
            "gpu_cost_usd": round(gpu, 4), "sandbox_cost_est_usd": round(sbx, 4),
            "mean_tokens_per_case": round(sum(r["input_tokens"] + r["output_tokens"] for r in rs) / n, 1),
            "mean_calls_per_case": round(sum(steps) / len(steps), 2) if steps else None, "calls_counted_trials": len(steps),
            "kv_cache_mean_per_run": [round((r.get("vllm") or {}).get("kv_usage_mean") or 0, 4) for r in rs],
            "failures": dict(sorted(fails.items())),
            "per_task": {k: f"{v[0]}/{v[1]}" for k, v in sorted(pt.items())},
        }]
        per_type[name] = {model: {k: {"n": m, "correct": cc, "accuracy": round(cc / m, 4)} for k, (cc, m) in sorted(typ.items())}}
    return ml, results, per_type, excluded, gpu_tot, sbx_tot


def api_round(r):
    tasks = {t["task"] for t in r["trials"]}
    if tasks <= {"titan-fork-drift", "titan-silent-divergence"}:
        return "real-system tasks (2 torchtitan tasks)"
    if tasks <= set(k for k, v in FAMILY.items() if v.startswith("v3")):
        return "v3 set (5 tasks)"
    if tasks == HARD8:
        return "hard set (8 tasks)"
    if len(tasks) == 11:
        return "hard + v2 sets (11 tasks)"
    return f"partial ({len(tasks)} tasks: {', '.join(sorted(tasks))})"


def vendor_api():
    api = [json.loads(l) for f in ("api_attempts.jsonl", "api_attempts_anthropic.jsonl") for l in open(RUNS / f)]
    ag = defaultdict(list)
    for r in api:
        ag[(api_round(r), r["harness"], r["model"])].append(r)
    results, per_type = {}, {}
    for (rnd, h, m), rs in sorted(ag.items()):
        bare = m.split("/")[-1]
        name = f"vendor API | {rnd} | {h} | {bare}"
        n = sum(r["attempted"] for r in rs)
        corr = sum(int(sum(t["reward"] >= 1 for t in r["trials"])) for r in rs)
        cost = sum(r["api_cost"] for r in rs)
        pt, typ, fails = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0]), Counter()
        for r in rs:
            for t in r["trials"]:
                ok = t["reward"] >= 1
                t["ok"] = ok
                pt[t["task"]][0] += ok; pt[t["task"]][1] += 1
                typ[FAMILY[t["task"]]][0] += ok; typ[FAMILY[t["task"]]][1] += 1
                f = classify(t)
                if f:
                    fails[f] += 1
        results[name] = [{
            "model": bare, "runs": len(rs), "n": n, "correct": corr, "accuracy": round(corr / n, 4) if n else None,
            "ci95": boot_ci({k: tuple(v) for k, v in pt.items()}),
            "per_run_solved": [f"{r['solved']}/{r['attempted']}" for r in rs],
            "api_cost_usd": round(cost, 4),
            "cost_per_correct_cents": round(100 * cost / corr, 4) if corr else None,
            "mean_tokens_per_case": round(sum(t["n_input"] + t["n_output"] for r in rs for t in r["trials"]) / n, 1) if n else None,
            "mean_input_tokens_per_case": round(sum(t["n_input"] for r in rs for t in r["trials"]) / n, 1) if n else None,
            "mean_output_tokens_per_case": round(sum(t["n_output"] for r in rs for t in r["trials"]) / n, 1) if n else None,
            "mean_calls_per_case": None,
            "failures": dict(sorted(fails.items())),
            "harbor_exit_codes": sorted({r.get("harbor_rc") for r in rs}),
            "per_task": {k: f"{v[0]}/{v[1]}" for k, v in sorted(pt.items())},
        }]
        per_type[name] = {bare: {k: {"n": mm, "correct": cc, "accuracy": round(cc / mm, 4)} for k, (cc, mm) in sorted(typ.items())}}
    totals = {"api_total": round(sum(r["api_cost"] for r in api), 4),
              **{p: round(sum(r["api_cost"] for r in api if r["provider"] == p), 4) for p in ("openai", "anthropic")}}
    return results, per_type, totals


def paired(ml):
    tasks = {}
    for r in mha.records():
        res, _ = mha.per_task(r["job_name"], r["trials"])
        merged = tasks.setdefault((r["harness"], r["config"], r["concurrency"]), defaultdict(list))
        for t, v in res.items():
            merged[t] += v
    out = []
    for h in ("terminus-2", "mini-swe-agent"):
        base = tasks[(h, "defaults", 24)]
        for (hh, cfg, c), d in sorted(tasks.items()):
            if hh != h or (cfg, c) == ("defaults", 24) or not all(t in d for t in mha.TASKS):
                continue
            p, lo, hi = mha.boot(base, d)
            out.append({"harness": h, "change": f"{cfg} c{c}", "baseline": "defaults c24 H100 (both runs pooled)",
                        "diff_pts": round(100 * p, 2), "ci95_pts": [round(100 * lo, 2), round(100 * hi, 2)], "tasks": 8})
    v2 = {}
    for r in ml:
        if r["valid"] and r["task_set"] == "mlops_hard2-k6":
            res, _ = mha.per_task(r["job_name"], r["trials"])
            v2[(r["harness"], r["config"])] = res
    mha.TASKS = sorted(next(iter(v2.values())))
    for h in ("terminus-2", "mini-swe-agent"):
        p, lo, hi = mha.boot(v2[(h, "defaults")], v2[(h, "h200")])
        out.append({"harness": h, "change": "h200 c24 (v2 set)", "baseline": "defaults c24 H100 (v2 set, one run)",
                    "diff_pts": round(100 * p, 2), "ci95_pts": [round(100 * lo, 2), round(100 * hi, 2)], "tasks": 4})
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
    rows = [json.loads(l) for l in open(RUNS / "attempts.jsonl") if l.strip()]
    ml, results, per_type, excluded, gpu_tot, sbx_tot = self_hosted(rows)
    api_results, api_per_type, api_tot = vendor_api()
    results.update(api_results)
    per_type.update(api_per_type)
    pc = paired(ml)
    exp = json.load(open(BENCH / "results" / "ml-training-ops.json"))
    problems = []
    diff_values(results, exp["results"], "results", problems)
    diff_values(per_type, exp["per_type"], "per_type", problems)
    diff_values(excluded, exp["excluded_runs"], "excluded_runs", problems)
    diff_values(pc, exp["paired_comparisons"]["comparisons"], "paired_comparisons.comparisons", problems)
    note = exp["meta"]["total_spend_usd_note"]
    for want in (f"vendor API cost ${api_tot['api_total']:.4f}", f"OpenAI ${api_tot['openai']:.4f}",
                 f"Anthropic ${api_tot['anthropic']:.4f}", f"GPU run time ${gpu_tot:.4f}", f"estimated sandboxes ${sbx_tot:.4f}"):
        if want not in note:
            problems.append(f"meta.total_spend_usd_note: '{want}' not found")
    # Re-price the recorded sandbox lifetimes at each task's requested resources.
    res, repriced = task_resources(), 0.0
    for r in ml:
        if r["valid"]:
            for t in r["trials"]:
                cpus, gib = res.get(t["task"]) or res["_hard"]
                repriced += (t.get("wall_s") or 0) / 3600 * (cpus * 0.1419 + gib * 0.024)
    print(f"conditions rebuilt: {len(results)} ({len(api_results)} vendor-API); paired comparisons: {len(pc)}; "
          f"API ${api_tot}; self-hosted GPU ${gpu_tot:.4f}, recorded sandbox estimate ${sbx_tot:.4f}, "
          f"re-priced at requested CPU/memory ${repriced:.4f}")
    if problems:
        print(f"{len(problems)} MISMATCHES:\n" + "\n".join(problems[:200]))
        sys.exit(1)
    print("ALL MATCH")


if __name__ == "__main__":
    main()
