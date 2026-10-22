"""
Which cheap signal finds a claims agent's wrong decisions, and does accuracy differ by group?
Offline, from claims/sessions_*.jsonl and claims/judgments.jsonl (claims_bench.py).

    python claims_signals.py      # markdown to stdout (claims_signals.md)
"""

import random
import statistics as st
from collections import defaultdict

from claims_bench import MODELS, D, jl

cases = {c["id"]: c for c in jl(D / "cases.jsonl")}
S = {(s["case_id"], s["model"], s["attempt"]): s for m in MODELS for s in jl(D / f"sessions_{m}.jsonl")
     if s.get("case_id") in cases and s.get("final")}
J = {(j["case_id"], j["model"], j["attempt"]): j.get("verdict") for j in jl(D / "judgments.jsonl") if j.get("case_id")}
pct = lambda x: f"{100 * x:.0f}%"  # noqa: E731

rows = []
for (cid, m, a), s in S.items():
    other = S.get((cid, m, 1 - a))
    xmodel = S.get((cid, "moe" if m == "dense" else "dense", a))
    d = s["final"].get("decision")
    rows.append({"case": cid, "model": m, "right": d == cases[cid]["truth"], "decision": d,
                 "lowconf": s["final"].get("confidence") != "high",
                 "rerun_disagrees": other is not None and other["final"].get("decision") != d,
                 "model_disagrees": xmodel is not None and xmodel["final"].get("decision") != d,
                 "judge_flags": J.get((cid, m, a)) == "incorrect",
                 "few_precedents": sum(1 for c in s["calls"] if c["name"] == "get_precedent") == 0,
                 "long": s["turns"] >= 8})

L = ["# Finding a claims agent's wrong decisions", "",
     f"{len(rows)} determinations from `claims_bench.py`. A signal 'flags' a decision for human review; "
     "we want it to catch wrong decisions while flagging few right ones.", "",
     "| signal | catches wrong decisions | flags right decisions | share of all decisions sent to review |",
     "|---|---|---|---|"]
wrong = [r for r in rows if not r["right"]]
right = [r for r in rows if r["right"]]
signals = [("not stated with high confidence", "lowconf"), ("a rerun of the same agent disagrees", "rerun_disagrees"),
           ("the other model disagrees", "model_disagrees"), ("LLM judge says incorrect", "judge_flags"),
           ("never opened a precedent", "few_precedents"), ("took 8+ turns", "long")]
for name, k in signals:
    L.append(f"| {name} | {pct(st.mean(r[k] for r in wrong))} | {pct(st.mean(r[k] for r in right))} | {pct(st.mean(r[k] for r in rows))} |")
for name, f in [("low confidence OR rerun disagrees", lambda r: r["lowconf"] or r["rerun_disagrees"]),
                ("low confidence OR judge says incorrect", lambda r: r["lowconf"] or r["judge_flags"]),
                ("low confidence AND rerun disagrees", lambda r: r["lowconf"] and r["rerun_disagrees"])]:
    L.append(f"| {name} | {pct(st.mean(f(r) for r in wrong))} | {pct(st.mean(f(r) for r in right))} | {pct(st.mean(f(r) for r in rows))} |")

L += ["", "## Accuracy and wrongful denials by group", "",
      "A wrongful denial = the agent upheld a denial that the independent reviewer overturned (share of all "
      "overturned cases in the group). 95% CI by bootstrap over cases.", "",
      "| group | cases | accuracy | wrongful denial rate |", "|---|---|---|---|"]


def ci(vals_by_case):
    ids, rng = list(vals_by_case), random.Random(0)
    m = lambda ks: st.mean(st.mean(vals_by_case[k]) for k in ks)  # noqa: E731
    b = sorted(m([rng.choice(ids) for _ in ids]) for _ in range(1000))
    return m(ids), b[25], b[974]


for field, label in (("gender", "gender"), ("age", "age"), ("type", "review type")):
    groups = sorted({cases[r["case"]][field] or "unknown" for r in rows})
    for g in groups:
        rs = [r for r in rows if (cases[r["case"]][field] or "unknown") == g]
        if len({r["case"] for r in rs}) < 15:
            continue
        acc = defaultdict(list)
        wd = defaultdict(list)
        for r in rs:
            acc[r["case"]].append(float(r["right"]))
            if cases[r["case"]]["truth"] == "overturn":
                wd[r["case"]].append(float(r["decision"] == "uphold"))
        a, alo, ahi = ci(acc)
        w = ci(wd) if len(wd) >= 5 else None
        L.append(f"| {label}: {g} | {len(acc)} | {pct(a)} ({pct(alo)}-{pct(ahi)}) | "
                 + (f"{pct(w[0])} ({pct(w[1])}-{pct(w[2])})" if w else "n/a") + " |")
print("\n".join(L))
