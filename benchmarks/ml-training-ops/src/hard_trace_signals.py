"""
Trace-only early warning on the hard ML-ops runs: from what a tracing tool records (timestamps and
token counts per model call), can you tell early in a trial that the serving setup is about to make
it time out, and what would an early alarm or kill policy save?

    python hard_trace_signals.py      # writes hard_trace_signals.md

Per trial (ATIF trajectory), from the first K agent steps only:
  gen_rate  completion tokens / seconds between consecutive agent steps (median), i.e. how fast the
            server is generating for this agent, as seen from the trace
  step_s    median seconds between consecutive agent steps
Labels: timed out (AgentTimeoutError), solved (reward 1). Server truth (KV-cache load) is not used.
"""
import glob
import json
import os
import statistics as st
from datetime import datetime

import mlops_hard_analysis as mh

K = 5


def trial_features(trial_dir):
    try:
        t = json.load(open(os.path.join(trial_dir, "agent", "trajectory.json")))
    except (OSError, json.JSONDecodeError):
        return None
    steps = [s for s in t.get("steps", []) if s.get("source") == "agent" and s.get("timestamp")]
    if len(steps) < 3:
        return None
    ts = [datetime.fromisoformat(s["timestamp"]) for s in steps]
    gaps, rates = [], []
    for i in range(1, min(len(steps), K + 1)):
        dt = (ts[i] - ts[i - 1]).total_seconds()
        if dt <= 0:
            continue
        gaps.append(dt)
        ct = ((steps[i].get("metrics") or {}).get("completion_tokens") or 0)
        rates.append(ct / dt)
    if not gaps:
        return None
    return {"step_s": st.median(gaps), "gen_rate": st.median(rates), "n_steps": len(steps)}


def auc(pos, neg):
    if not pos or not neg:
        return float("nan")
    wins = sum((p > n) + 0.5 * (p == n) for p in pos for n in neg)
    return wins / (len(pos) * len(neg))


def main():
    rows = []
    for r in mh.records():
        for rf in glob.glob(os.path.join(mh.HERE, "jobs", r["job_name"], "*", "result.json")):
            d = os.path.dirname(rf)
            f = trial_features(d)
            if f is None:
                continue
            res = json.load(open(rf))
            rw = os.path.join(d, "verifier", "reward.txt")
            f.update(harness=r["harness"], config=r["config"], conc=r["concurrency"],
                     timeout=(res.get("exception_info") or {}).get("exception_type") == "AgentTimeoutError",
                     solved=os.path.exists(rw) and float(open(rw).read().strip()) >= 1,
                     kv=(r.get("vllm") or {}).get("kv_usage_mean", 0))
            rows.append(f)
    if not rows:
        raise SystemExit("No trajectories found: this needs the raw Harbor jobs in jobs/ (not published).")
    out = ["# Trace-only early warning on the hard ML-ops runs", "",
           f"{len(rows)} trials with at least 3 agent steps, all hard-set runs (both harnesses, every setup).",
           f"Features use only the first {K} agent steps of a trial, i.e. the first few minutes.", ""]
    out += ["## Does the early trace predict a timeout or a failure? (AUC; 0.5 = no signal)", "",
            "| harness | trials | timeouts | AUC slow steps -> timeout | AUC low generation rate -> timeout | AUC low generation rate -> unsolved |",
            "|---|---|---|---|---|---|"]
    for h in ("terminus-2", "mini-swe-agent"):
        R = [x for x in rows if x["harness"] == h]
        to = [x for x in R if x["timeout"]]
        nt = [x for x in R if not x["timeout"]]
        a1 = auc([x["step_s"] for x in to], [x["step_s"] for x in nt])
        a2 = auc([-x["gen_rate"] for x in to], [-x["gen_rate"] for x in nt])
        a3 = auc([-x["gen_rate"] for x in R if not x["solved"]], [-x["gen_rate"] for x in R if x["solved"]])
        out.append(f"| {h} | {len(R)} | {len(to)} | {a1:.2f} | {a2:.2f} | {a3:.2f} |")
    out += ["", "## Generation rate seen in the trace vs the server's real load", "",
            "Median early generation rate (tokens/s per agent) by setup. Server KV-cache mean from vLLM metrics (not visible to a tracer).", "",
            "| harness | setup | agents | median gen rate (tok/s) | server KV mean | timeouts / trials | solved / trials |",
            "|---|---|---|---|---|---|---|"]
    groups = {}
    for x in rows:
        groups.setdefault((x["harness"], x["config"], x["conc"]), []).append(x)
    for (h, c, n), R in sorted(groups.items(), key=lambda kv: (kv[0][0], -st.median(x["gen_rate"] for x in kv[1]))):
        out.append(f"| {h} | {mh.LABEL.get(c, c)} | {n} | {st.median(x['gen_rate'] for x in R):.0f} | "
                   f"{st.mean(x['kv'] for x in R):.0%} | {sum(x['timeout'] for x in R)}/{len(R)} | {sum(x['solved'] for x in R)}/{len(R)} |")
    out += ["", "## An alarm rule an eval tool could ship", "",
            "Flag a trial when its early generation rate falls below a threshold. Counts over all trials.", "",
            "| threshold (tok/s) | trials flagged | of which timed out | of all timeouts caught | flagged trials that were solved anyway |",
            "|---|---|---|---|---|"]
    all_to = sum(x["timeout"] for x in rows)
    for thr in (10, 15, 20, 25, 30, 40):
        fl = [x for x in rows if x["gen_rate"] < thr]
        if not fl:
            continue
        out.append(f"| {thr} | {len(fl)} | {sum(x['timeout'] for x in fl)} ({sum(x['timeout'] for x in fl) / len(fl):.0%}) | "
                   f"{sum(x['timeout'] for x in fl) / max(all_to, 1):.0%} | {sum(x['solved'] for x in fl)} |")
    open(os.path.join(mh.HERE, "hard_trace_signals.md"), "w").write("\n".join(out) + "\n")
    print("\n".join(out))


if __name__ == "__main__":
    main()
