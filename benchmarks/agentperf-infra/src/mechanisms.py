"""
Mechanism checks behind the headline effects, from attempts.jsonl (Terminal-Bench runs).

    python mechanisms.py        # markdown to stdout (mechanisms.md)

1. KV saturation: per cell, KV-cache peak, prefix-cache hit rate, preemptions and solve rate.
2. Deadline fragility: how close to the task's time limit solved trials finish.
3. Where request time goes: prompt vs generated tokens, prefill vs decode seconds.
4. Early-kill policy: capping trials at a fraction of their limit, effect on cost per solve.
5. Timed out but solved: trials that hit the limit after the tests already passed.
"""

import statistics as st
from collections import defaultdict

import analysis as an

HARNESSES = ("terminus-2", "mini-swe-agent")
SAT_CELLS = [("defaults", 8, "H100!"), ("defaults", 16, "H100!"), ("defaults", 32, "H100!"),
             ("defaults", 48, "H100!"), ("defaults", 64, "H100!"), ("weights-fp8", 32, "H100!"),
             ("kv-fp8", 32, "H100!"), ("h200", 32, "H200"), ("b200", 32, "B200"), ("moe-a3b", 32, "H100!")]
DEADLINE_CELLS = [("defaults", 16, "H100!"), ("defaults", 32, "H100!"), ("h200", 32, "H200"),
                  ("b200", 32, "B200"), ("moe-a3b", 32, "H100!")]


def key(r):
    return (r["harness"], r["config"], r["concurrency"], r["gpu"])


def saturation(rows, cells):
    vl = defaultdict(list)
    for r in rows:
        if r.get("vllm") and r["vllm"].get("prefix_hit_rate") is not None:
            vl[key(r)].append(r["vllm"])
    out = []
    for h in HARNESSES:
        for c in SAT_CELLS:
            k = (h, *c)
            if k not in cells or not vl[k]:
                continue
            m = lambda f: st.mean(v.get(f) or 0 for v in vl[k])  # noqa: E731
            out.append({"harness": h, "config": c[0], "c": c[1], "gpu": c[2].rstrip("!"), "trials": len(cells[k]),
                        "kv_max": m("kv_usage_max"), "prefix_hit": m("prefix_hit_rate"),
                        "preemptions": m("preemptions"), "solved": st.mean(an.success(cells[k]).values())})
    return out


def deadline(cells, lim):
    out = []
    for h in HARNESSES:
        for c in DEADLINE_CELLS:
            fr = [t["agent_s"] / lim[t["task"]] for t in cells.get((h, *c), [])
                  if t["ok"] and t.get("agent_s") and lim.get(t["task"])]
            if fr:
                out.append({"harness": h, "config": c[0], "c": c[1], "gpu": c[2].rstrip("!"), "solves": len(fr),
                            "last_quarter": sum(f > 0.75 for f in fr) / len(fr), "median": st.median(fr)})
    return out


def disagreement(rows):
    """Share of tasks where the two attempts of a k2 run disagree, per cell."""
    agg = defaultdict(lambda: [0, 0])
    for r in rows:
        if r["task_set"] != "full-k2":
            continue
        by = defaultdict(list)
        for t in r["trials"]:
            by[t["task"]].append(t["ok"])
        for v in by.values():
            if len(v) == 2:
                agg[key(r)][0] += v[0] != v[1]
                agg[key(r)][1] += 1
    return agg


def phases(rows):
    agg = defaultdict(lambda: {"p": 0, "g": 0, "pf": [], "dc": []})
    for r in rows:
        v = r.get("vllm") or {}
        if v.get("prompt_tokens") and v.get("generation_tokens") and v.get("decode_mean_s"):
            a = agg[(r["harness"], r["config"])]
            a["p"] += v["prompt_tokens"]
            a["g"] += v["generation_tokens"]
            a["pf"].append(v.get("prefill_mean_s") or 0)
            a["dc"].append(v["decode_mean_s"])
    out = []
    for (h, cfg), a in sorted(agg.items()):
        if h in HARNESSES and cfg in ("defaults", "no-thinking", "moe-a3b"):
            pf, dc = st.mean(a["pf"]), st.mean(a["dc"])
            out.append({"harness": h, "config": cfg, "prompt_per_gen": a["p"] / a["g"],
                        "prefill_s": pf, "decode_s": dc, "decode_share": dc / (pf + dc)})
    return out


def early_kill(cells, lim, cell=("defaults", 32, "H100!")):
    out = []
    for h in HARNESSES:
        ts = [t for t in cells[(h, *cell)] if t.get("agent_s") and lim.get(t["task"])]
        full_t, full_s = sum(t["agent_s"] for t in ts), sum(t["ok"] for t in ts)
        for f in (0.5, 0.75):
            s = sum(1 for t in ts if t["ok"] and t["agent_s"] <= f * lim[t["task"]])
            used = sum(min(t["agent_s"], f * lim[t["task"]]) for t in ts)
            out.append({"harness": h, "cap": f, "solves_kept": s / full_s, "time_used": used / full_t,
                        "cost_per_solve_x": (used / full_t) / (s / full_s)})
    return out


def timeout_solved(rows):
    out = []
    for h in HARNESSES:
        ts = [t for r in rows if r["harness"] == h for t in r["trials"]]
        to = [t for t in ts if t.get("exc") == "AgentTimeoutError"]
        out.append({"harness": h, "timeouts": len(to), "passed": sum(t["ok"] for t in to),
                    "share_of_solves": sum(t["ok"] for t in to) / max(1, sum(t["ok"] for t in ts))})
    return out


def compute():
    rows = an.load()
    cells = an.by_cell(rows)
    lim = an.task_limits(rows)
    return {"saturation": saturation(rows, cells), "deadline": deadline(cells, lim), "phases": phases(rows),
            "early_kill": early_kill(cells, lim), "timeout_solved": timeout_solved(rows),
            "disagreement": {"|".join(map(str, k)): v for k, v in disagreement(rows).items()}}


def main():
    d = compute()
    p = lambda x: f"{100 * x:.0f}%"  # noqa: E731
    L = ["# Mechanisms", "", "Terminal-Bench runs (`full`, `full-k2`). Exploratory.", "",
         "## 1. KV saturation", "", "| harness | config | agents | GPU | trials | KV peak | prefix hit | preemptions | solved |",
         "|---|---|---|---|---|---|---|---|---|"]
    L += [f"| {r['harness']} | {r['config']} | {r['c']} | {r['gpu']} | {r['trials']} | {p(r['kv_max'])} | {p(r['prefix_hit'])} | "
          f"{r['preemptions']:.0f} | {p(r['solved'])} |" for r in d["saturation"]]
    L += ["", "## 2. Deadline fragility", "", "Solved trials' agent time as a share of the task's limit.", "",
          "| harness | config | agents | GPU | solves | in last quarter of limit | median |", "|---|---|---|---|---|---|---|"]
    L += [f"| {r['harness']} | {r['config']} | {r['c']} | {r['gpu']} | {r['solves']} | {p(r['last_quarter'])} | {r['median']:.2f} |"
          for r in d["deadline"]]
    L += ["", "Two attempts of the same task disagreeing (k2 runs):", ""]
    L += [f"- {k.replace('|', ' ')}: {v[0]}/{v[1]} tasks ({p(v[0] / v[1])})" for k, v in sorted(d["disagreement"].items())]
    L += ["", "## 3. Where request time goes", "", "| harness | config | prompt : generated tokens | prefill s | decode s | decode share |",
          "|---|---|---|---|---|---|"]
    L += [f"| {r['harness']} | {r['config']} | {r['prompt_per_gen']:.0f} : 1 | {r['prefill_s']:.2f} | {r['decode_s']:.1f} | {p(r['decode_share'])} |"
          for r in d["phases"]]
    L += ["", "## 4. Early-kill policy (defaults, 32 agents, H100)", "", "| harness | cap | solves kept | agent time used | cost per solve |",
          "|---|---|---|---|---|"]
    L += [f"| {r['harness']} | {p(r['cap'])} of limit | {p(r['solves_kept'])} | {p(r['time_used'])} | {r['cost_per_solve_x']:.2f}x |"
          for r in d["early_kill"]]
    L += ["", "## 5. Timed out but solved", ""]
    L += [f"- {r['harness']}: {r['passed']} of {r['timeouts']} time-outs passed the tests ({p(r['share_of_solves'])} of all solves)"
          for r in d["timeout_solved"]]
    print("\n".join(L))


if __name__ == "__main__":
    main()
