"""
Can an eval tool that only sees agent traces (what Langfuse-style tracing records: per-call
timing and token usage) tell when a run was served under bad conditions, and how much of a
score change that explains? Ground truth comes from the server's own metrics, which such a
tool would not have.

    python trace_signals.py        # markdown to stdout (trace_signals.md)

Trace-only features per run, from each trial's ATIF trajectory:
  step_s      median seconds between agent steps (includes tool time, so noisier than the
              per-call latency a tracer records)
  gen_rate    completion tokens per second of agent time (median over trials)
  cache       cached / prompt tokens over all calls (mini-swe-agent only; terminus-2's
              client does not record cached tokens)
Server truth: KV-cache peak >= 0.99 ("saturated"), preemptions.

Only runs that keep the agent, model and time budget fixed (infrastructure changes only)
on Terminal-Bench are used, so a score change between two runs is the infrastructure's.
"""

import json
import math
import statistics as st
from datetime import datetime
from itertools import combinations

import _paths  # noqa: F401  (harness on sys.path)
import analysis as an
import confirmatory as cf
import experiment as ex

INFRA_ONLY = {"defaults", "h200", "b200", "kv-fp8", "weights-fp8", "no-prefix-cache", "spec-mtp", "h200-spec-mtp"}
HARNESSES = ("terminus-2", "mini-swe-agent")


def run_features(r):
    rates, cached, prompt = [], 0, 0
    for d in (ex.JOBS_DIR / r["job_name"]).glob("*/agent/trajectory.json"):
        try:
            t = json.loads(d.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        steps = [s for s in t.get("steps", []) if s.get("source") == "agent" and s.get("metrics")]
        if len(steps) < 2:
            continue
        ts = [datetime.fromisoformat(s["timestamp"]) for s in steps]
        span = (ts[-1] - ts[0]).total_seconds()
        comp = sum(s["metrics"].get("completion_tokens") or 0 for s in steps[1:])
        if span > 0:
            rates.append(comp / span)
        for s in steps:
            m = s["metrics"]
            c = ((m.get("extra") or {}).get("prompt_tokens_details") or {}).get("cached_tokens")
            if c is not None:
                cached += c
                prompt += m.get("prompt_tokens") or 0
    step = [an.step_s(t) for t in r["trials"] if an.step_s(t)]
    return {"step_s": st.median(step) if step else None, "gen_rate": st.median(rates) if rates else None,
            "cache": cached / prompt if prompt else None}


def auc(pos, neg):
    """P(score of a positive > score of a negative); ties count half."""
    if not pos or not neg:
        return None
    return sum((p > n) + 0.5 * (p == n) for p in pos for n in neg) / (len(pos) * len(neg))


def main():
    rows = [r for r in an.load() if r["config"] in INFRA_ONLY and r.get("vllm") and r["harness"] in HARNESSES]
    runs = []
    for r in rows:
        f = run_features(r)
        if f["step_s"] is None:
            continue
        runs.append({**f, "harness": r["harness"], "config": r["config"], "c": r["concurrency"], "gpu": r["gpu"].rstrip("!"),
                     "job": r["job_name"], "solved": st.mean(an.success(r["trials"]).values()),
                     "kv": r["vllm"].get("kv_usage_max") or 0, "hit": r["vllm"].get("prefix_hit_rate"),
                     "preempt": r["vllm"].get("preemptions") or 0, "success": an.success(r["trials"])})
    L = ["# Can traces alone see the infrastructure?", "",
         f"{len(runs)} Terminal-Bench runs that change only the infrastructure (same agent, model and time budget).", ""]

    L += ["## 1. Flag runs served with a saturated KV cache", "",
          "AUC of each trace-only feature for separating saturated runs (server KV peak >= 99%) from the rest, "
          "within each harness (1.0 = perfect, 0.5 = chance).", "",
          "| harness | runs (saturated) | slower steps | lower generation rate | lower cache reuse |", "|---|---|---|---|---|"]
    for h in HARNESSES:
        rs = [x for x in runs if x["harness"] == h]
        sat = [x for x in rs if x["kv"] >= 0.99]
        ok = [x for x in rs if x["kv"] < 0.99]
        a_step = auc([x["step_s"] for x in sat], [x["step_s"] for x in ok])
        a_rate = auc([-x["gen_rate"] for x in sat if x["gen_rate"]], [-x["gen_rate"] for x in ok if x["gen_rate"]])
        a_cache = auc([-x["cache"] for x in sat if x["cache"] is not None], [-x["cache"] for x in ok if x["cache"] is not None])
        f = lambda v: f"{v:.2f}" if v is not None else "n/a"  # noqa: E731
        L.append(f"| {h} | {len(rs)} ({len(sat)}) | {f(a_step)} | {f(a_rate)} | {f(a_cache)} |")
    mini = [x for x in runs if x["harness"] == "mini-swe-agent" and x["cache"] is not None and x["hit"] is not None]
    if len(mini) >= 4:
        L += ["", f"Client-side cache reuse vs the server's prefix-cache hit rate (mini-swe-agent, {len(mini)} runs): "
              f"Spearman {cf.spearman([x['cache'] for x in mini], [x['hit'] for x in mini]):+.2f}."]

    L += ["", "## 2. Explain score changes between two runs of the same agent", "",
          "Every pair of runs of the same harness: does the change in trace-only step time predict the change "
          "in solve rate? Pairs are what an eval tool compares (baseline vs new run).", "",
          "| harness | pairs | Spearman: step-time ratio vs score change | score change when steps got >=1.3x slower | when within 1.3x |",
          "|---|---|---|---|---|"]
    for h in HARNESSES:
        rs = [x for x in runs if x["harness"] == h]
        pairs = []
        for a, b in combinations(rs, 2):
            if b["step_s"] > a["step_s"]:
                a, b = b, a  # a is the slower run
            tasks = a["success"].keys() & b["success"].keys()
            d = st.mean(a["success"][t] - b["success"][t] for t in tasks)
            pairs.append((a["step_s"] / b["step_s"], d))
        slow = [d for ratio, d in pairs if ratio >= 1.3]
        same = [d for ratio, d in pairs if ratio < 1.3]
        rho = cf.spearman([p[0] for p in pairs], [p[1] for p in pairs])
        L.append(f"| {h} | {len(pairs)} | {rho:+.2f} | {100 * st.mean(slow):+.1f} pts (n={len(slow)}) | "
                 f"{100 * st.mean(same):+.1f} pts (n={len(same)}) |")

    L += ["", "## 3. Predict a run's score from its traces", "",
          "Leave-one-run-out: predict each run's solve rate from the other runs of the same harness, by a linear "
          "fit on log step time (trace-only), versus predicting the harness average.", "",
          "| harness | runs | mean abs. error, trace-only | mean abs. error, average | correlation |", "|---|---|---|---|---|"]
    for h in HARNESSES:
        rs = [x for x in runs if x["harness"] == h]
        errs, base, preds = [], [], []
        for i, x in enumerate(rs):
            rest = rs[:i] + rs[i + 1:]
            xs = [math.log(y["step_s"]) for y in rest]
            ys = [y["solved"] for y in rest]
            mx, my = st.mean(xs), st.mean(ys)
            slope = sum((a - mx) * (b - my) for a, b in zip(xs, ys)) / sum((a - mx) ** 2 for a in xs)
            p = my + slope * (math.log(x["step_s"]) - mx)
            preds.append(p)
            errs.append(abs(p - x["solved"]))
            base.append(abs(my - x["solved"]))
        r = st.correlation(preds, [x["solved"] for x in rs])
        L.append(f"| {h} | {len(rs)} | {100 * st.mean(errs):.1f} pts | {100 * st.mean(base):.1f} pts | {r:+.2f} |")

    L += ["", "## Runs", "", "| harness | config | agents | GPU | solved | s/step | gen tok/s | cache reuse | KV peak | prefix hit (server) | preemptions |",
          "|---|---|---|---|---|---|---|---|---|---|---|"]
    pc = lambda v: "" if v is None else f"{100 * v:.0f}%"  # noqa: E731
    for x in sorted(runs, key=lambda x: (x["harness"], x["step_s"])):
        L.append(f"| {x['harness']} | {x['config']} | {x['c']} | {x['gpu']} | {pc(x['solved'])} | {x['step_s']:.0f} | "
                 f"{x['gen_rate']:.1f} | {pc(x['cache'])} | {pc(x['kv'])} | {pc(x['hit'])} | {x['preempt']:.0f} |")
    print("\n".join(L))


if __name__ == "__main__":
    main()
