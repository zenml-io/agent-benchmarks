"""Recompute the expert-deciders live numbers from the public rows in results/runs/ (no model calls, no network).

  python scripts/ed_compute_rows.py out/ed_out.json        (run with the swapbench venv: ../swapbench/.venv/bin/python)

Same quantities as the original export's ed_compute.py (which read the raw runs), plus the rule-violation counts and
paired deltas of scripts/ed_online_eval.py, which that export copied from expert_deciders_online.md instead.
"""
import json
import os
import random
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "swapbench"))
from swapbench import stats  # noqa: E402

RUNS = os.path.join(ROOT, "results", "runs")


def mean_ci(eps, key="reward", n_boot=10000, seed=0):
    per = stats.per_scenario(eps, key)
    v = list(per.values())
    rng = random.Random(seed)
    boots = sorted(sum(rng.choice(v) for _ in v) / len(v) for _ in range(n_boot))
    return [sum(v) / len(v), boots[int(0.025 * n_boot)], boots[int(0.975 * n_boot) - 1]]


def main(out_p):
    meta = json.load(open(os.path.join(RUNS, "live_runs.json")))
    E, L = defaultdict(list), defaultdict(list)
    for r in map(json.loads, open(os.path.join(RUNS, "live_conversations.jsonl"))):
        r["bad_handoffs"] = r["unneeded_handoffs"]
        r["viol_any"] = float(r["violations"] > 0)
        E[r["run"]].append(r)
    for x in map(json.loads, open(os.path.join(RUNS, "live_decisions.jsonl"))):
        L[x["run"]].append(x)
    out = {}
    for r, eps in E.items():
        m, dec = meta[r], L.get(r, [])
        n = len(eps)
        resolved = sum(e["reward"] >= 1 for e in eps)
        cost = m["agent_cost_usd"] + m["check_cost_usd"]
        by_tool = {}
        for x in dec:
            d = by_tool.setdefault(x["tool"], {"checked": 0, "blocked_rule": 0, "blocked_valid": 0, "allowed_rule": 0})
            d["checked"] += 1
            if x["blocked"]:
                d["blocked_rule" if x["truth"] else "blocked_valid"] += 1
            elif x["truth"]:
                d["allowed_rule"] += 1
        blk = [x for x in dec if x["blocked"]]
        out[r] = dict(agent_model=m["agent_model"], user_model=m["user_model"], n=n, scenarios=len({e["scenario"] for e in eps}),
                      excluded=m["excluded"], excluded_reasons=m["excluded_reasons"], empty=sum(e["empty"] for e in eps),
                      resolved=resolved, accuracy=resolved / n, handoffs=sum(e["handoffs"] for e in eps),
                      bad_handoffs=sum(e["bad_handoffs"] for e in eps), agent_cost_usd=m["agent_cost_usd"],
                      check_cost_usd=m["check_cost_usd"], cost_src=m["agent_cost_source"], call_log_calls=m["call_log_calls"],
                      cost_per_conv_cents=cost / n * 100, check_cost_per_conv_cents=m["check_cost_usd"] / n * 100,
                      cost_per_resolved_cents=cost / resolved * 100 if resolved else None,
                      mean_tokens_traj=sum(e["input_tokens"] + e["output_tokens"] for e in eps) / n,
                      mean_calls_traj=sum(e["agent_calls"] for e in eps) / n,
                      checks=len(dec), blocked=len(blk), blocked_rule=sum(bool(x["truth"]) for x in blk),
                      allowed_rule=sum(1 for x in dec if not x["blocked"] and x["truth"]), by_tool=by_tool,
                      violations_per_conv=sum(e["violations"] for e in eps) / n,
                      conversations_with_violation=int(sum(e["viol_any"] for e in eps)),
                      resolved_ci=mean_ci(eps), handoffs_ci=mean_ci(eps, "handoffs"))
    ref = E.get("R_gpt5")
    for r, eps in E.items():
        base = E.get(r.split("_")[0] + "_none")
        o = out[r]
        if base and not r.endswith("_none"):
            o["vs_none"] = stats.paired_delta(eps, base)
            o["handoffs_vs_none"] = stats.paired_delta(eps, base, "handoffs")
            o["bad_handoffs_vs_none"] = stats.paired_delta(eps, base, "bad_handoffs")
            o["violations_vs_none"] = stats.paired_delta(eps, base, "violations")
        if ref and r != "R_gpt5":
            o["vs_gpt5"] = stats.paired_delta(eps, ref)
    os.makedirs(os.path.dirname(os.path.abspath(out_p)), exist_ok=True)
    json.dump(out, open(out_p, "w"), indent=1, default=str)
    for r in sorted(out):
        o = out[r]
        v = o.get("violations_vs_none")
        print(r, "n", o["n"], "resolved", o["resolved"], f"viol/conv {o['violations_per_conv']:.3f}", "conv w/ viol",
              o["conversations_with_violation"], "viol delta", v and [round(v[k], 3) for k in ("delta", "lo", "hi")])


if __name__ == "__main__":
    main(sys.argv[1])
