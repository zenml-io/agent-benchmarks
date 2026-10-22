"""Does the model-swap analyzer's step-level screen pick the models that hold underwriting accuracy?

  <kitaru venv>/bin/python replay/analyze.py [--grade]     # writes replay/comparison.json and prints a summary

Ground truth: each candidate's full-run accuracy on the 252 tasks, paired against Sonnet 5.5 (today's model) with a
bootstrap 95% interval, from results/runs. Step-level numbers: the analyzer's report (replay/out/underwriting{A,B}),
merged (batch B's Sonnet run is a second reference, i.e. the noise floor), plus two views recomputed from calls.jsonl:
agreement on the steps where Sonnet queried the database (read_query), and, with --grade, whether a candidate's reply
at a step where Sonnet gave its FINAL ANSWER is itself a correct answer (graded against the task reference by the
benchmark's own judges: the outcome measured at the decision step, from Sonnet's context).
"""
import argparse
import json
import os
import random
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor

from kitaru_model_swap import report as R

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, "harness"))
INCUMBENT = "sonnet-5.5"
NONINFERIOR = 0.05  # "holds quality": full-run accuracy at most 5 points below today's model
AGREE = {"same_tool_same_args", "same_text"}
FINAL = "FINAL ANSWER"


def full_runs():
    out = {}
    d = os.path.join(ROOT, "results", "runs")
    for f in os.listdir(d):
        rows = {}
        for line in open(os.path.join(d, f)):
            r = json.loads(line)
            if r["status"] != "harness_error":
                rows[r["task"]] = r
        out[f[:-6]] = rows
    return out


def paired(cand, inc, rng):
    tasks = sorted(set(cand) & set(inc))
    diffs = [int(cand[t]["success"]) - int(inc[t]["success"]) for t in tasks]
    n = len(diffs)
    boots = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(2000))
    k = sum(cand[t]["success"] for t in tasks)
    return dict(n=n, delta=sum(diffs) / n, lo=boots[50], hi=boots[1949], success=k / n,
                cost_per_success=sum(cand[t]["cost"] for t in tasks) / max(1, k))


def spearman(xs, ys):
    def ranks(v):
        order = sorted(range(len(v)), key=lambda i: v[i])
        r = [0.0] * len(v)
        i = 0
        while i < len(v):
            j = i
            while j + 1 < len(v) and v[order[j + 1]] == v[order[i]]:
                j += 1
            for k in range(i, j + 1):
                r[order[k]] = (i + j) / 2
            i = j + 1
        return r
    rx, ry = ranks(xs), ranks(ys)
    mx, my = sum(rx) / len(rx), sum(ry) / len(ry)
    num = sum((a - mx) * (b - my) for a, b in zip(rx, ry))
    den = (sum((a - mx) ** 2 for a in rx) * sum((b - my) ** 2 for b in ry)) ** 0.5
    return num / den if den else None


def calls():
    for tag in "AB":
        p = os.path.join(ROOT, "replay", "out", "underwriting" + tag, "calls.jsonl")
        if os.path.exists(p):
            for line in open(p):
                r = json.loads(line)
                if not r["attempt"] and not r["not_run"]:
                    r["name"] = r["candidate"] + (" (rerun B)" if r["candidate"] == INCUMBENT and tag == "B" else "")
                    yield r


def grade_finals(rows):
    """Grade candidate replies at Sonnet's final-answer steps against the task reference (cached)."""
    from judge import grade
    tasks = {t["id"]: t for t in json.load(open(os.path.join(ROOT, "env", "tasks.json")))}
    path = os.path.join(ROOT, "replay", "final_grades.json")
    cache = json.load(open(path)) if os.path.exists(path) else {}
    def one(r):
        text = (r["reply"] or {}).get("text") or ""
        if FINAL not in text:
            return dict(correct=False, reason="no final answer at this step", cost=0)
        t = tasks[r["task"]]
        answer = text[text.index(FINAL):]
        for attempt in range(4):
            try:
                votes = [grade(j, t["task"], t["reference"], answer) for j in ("gpt-6-luna", "haiku-5.5")]
                if votes[0][0] != votes[1][0]:
                    votes.append(grade("gpt-6.1-sol", t["task"], t["reference"], answer))
                return dict(correct=bool(votes[-1][0]), reason=votes[-1][1][:200], cost=sum(v[2] for v in votes))
            except (OSError, RuntimeError):
                time.sleep(2 ** attempt)
        return None

    todo = [r for r in rows if f"{r['name']}|{r['node']}" not in cache]
    cost = 0.0
    with ThreadPoolExecutor(16) as ex:
        for i, (r, g) in enumerate(zip(todo, ex.map(one, todo))):
            if g is not None:
                cache[f"{r['name']}|{r['node']}"] = g
                cost += g["cost"]
            if i % 50 == 49:
                json.dump(cache, open(path, "w"), indent=1)
    json.dump(cache, open(path, "w"), indent=1)
    print(f"final-step grading spend ${cost:.2f}")
    return cache


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--grade", action="store_true")
    a = ap.parse_args()
    rng = random.Random(0)
    reports = {}
    for tag in "AB":
        p = os.path.join(ROOT, "replay", "out", "underwriting" + tag, "report.json")
        if os.path.exists(p):
            reports[tag] = json.load(open(p))
    runs = full_runs()
    inc = runs[INCUMBENT]
    stats = defaultdict(lambda: defaultdict(int))
    final_rows = []
    for r in calls():
        s = stats[r["name"]]
        s["calls"] += 1
        if r["agreement"] is None:
            s["failed"] += 1
            continue
        s["answered"] += 1
        s["agree_or_equiv"] += r["agreement"] in AGREE or r["judge_equivalent"] is True
        if any(t[0] == "read_query" for t in r["recorded"]):
            s["query_steps"] += 1
            s["query_tool"] += r["agreement"] in ("same_tool_same_args", "same_tool_different_args")
            s["query_exact"] += r["agreement"] == "same_tool_same_args"
        if FINAL in (r["recorded_text"] or ""):
            s["final_steps"] += 1
            s["final_equiv"] += r["agreement"] == "same_text" or r["judge_equivalent"] is True
            final_rows.append(r)
    grades = grade_finals(final_rows) if a.grade else {}
    for r in final_rows:
        g = grades.get(f"{r['name']}|{r['node']}")
        if g:
            stats[r["name"]]["final_graded"] += 1
            stats[r["name"]]["final_correct"] += g["correct"]
    merged = [c for tag, rep in reports.items() for c in rep["candidates"] if not (tag == "B" and c["reference"])]
    picks = R._best_for(merged)
    rows = []
    for c in merged:
        name = c["name"]
        s = stats[name]
        ratio = lambda k, n: s[k] / s[n] if s[n] else None  # noqa: E731
        rows.append(dict(
            name=name, reference=c["reference"], open_weights=c["open_weights"], tool_choice=c["tool_choice_rate"],
            exact=c["agreement_rate"], failure=c["failure_rate"], answered=s["answered"],
            judge_adjusted=ratio("agree_or_equiv", "answered"), query_tool=ratio("query_tool", "query_steps"),
            query_exact=ratio("query_exact", "query_steps"), final_equiv=ratio("final_equiv", "final_steps"),
            final_correct=ratio("final_correct", "final_graded"), final_steps=s["final_steps"],
            step_cost_per_call=c["cost"]["per_call_usd"],
            full=paired(runs[name], inc, rng) if name != INCUMBENT else None))
    ref_b = stats.get(INCUMBENT + " (rerun B)")
    noise = dict(tool_choice_A=next((r["tool_choice"] for r in rows if r["reference"]), None),
                 final_correct_B=(ref_b["final_correct"] / ref_b["final_graded"]) if ref_b and ref_b["final_graded"]
                 else None)
    cands = [r for r in rows if r["full"]]
    corr = {}
    for metric in ("tool_choice", "exact", "judge_adjusted", "query_tool", "query_exact", "final_equiv",
                   "final_correct"):
        for target in ("success", "cost_per_success"):
            xs = [(r[metric], r["full"][target]) for r in cands if r[metric] is not None]
            corr[f"{metric}~{target}"] = spearman(*zip(*xs)) if len(xs) > 2 else None
    usable = [r for r in cands if (r["failure"] or 0) <= 0.2 and r["tool_choice"] is not None]
    holders = [r for r in cands if r["full"]["delta"] >= -NONINFERIOR]
    cheapest_holder = min(holders, key=lambda r: r["full"]["cost_per_success"], default=None)
    finalists = {}
    for metric in ("tool_choice", "final_correct"):
        ranked = sorted([r for r in usable if r[metric] is not None], key=lambda r: -r[metric])
        finalists[metric] = dict(
            top3=[r["name"] for r in ranked[:3]],
            holders_in_top3=[r["name"] for r in ranked[:3] if r["full"]["delta"] >= -NONINFERIOR],
            cheapest_holder_rank=next((i + 1 for i, r in enumerate(ranked)
                                       if cheapest_holder and r["name"] == cheapest_holder["name"]), None))
    pick_rows = [dict(goal=p["goal"], candidate=p["candidate"], why=p["why"],
                      full=[dict(name=n, **(next((r["full"] for r in rows if r["name"] == n and r["full"]), None)
                                            or {})) for n in p["candidate"].split(" + ")]) for p in picks]
    out = dict(rows=rows, picks=pick_rows, spearman=corr, noise=noise, finalists=finalists,
               holders=[r["name"] for r in holders], cheapest_holder=cheapest_holder and cheapest_holder["name"],
               best_mix={t: rep.get("best_mix") for t, rep in reports.items()},
               spent={t: rep.get("spent_usd") for t, rep in reports.items()},
               incumbent=dict(success=sum(r["success"] for r in inc.values()) / len(inc), n=len(inc)))
    json.dump(out, open(os.path.join(ROOT, "replay", "comparison.json"), "w"), indent=1, default=str)
    print(f"today's model {INCUMBENT}: {out['incumbent']['success']:.1%} on {out['incumbent']['n']}; noise {noise}")
    for r in sorted(rows, key=lambda r: -(r["tool_choice"] or 0)):
        f = r["full"]
        fmt = lambda x: "  -  " if x is None else f"{x:.2f}"  # noqa: E731
        print(f"  {r['name']:28} tool {fmt(r['tool_choice'])} exact {fmt(r['exact'])} judge {fmt(r['judge_adjusted'])}"
              f" query {fmt(r['query_tool'])} final≡ {fmt(r['final_equiv'])} final✓ {fmt(r['final_correct'])}"
              f" (n={r['final_steps']}) fail {fmt(r['failure'])} | "
              + ("reference" if not f else f"full {f['success']:.1%} d {f['delta']:+.1%} [{f['lo']:+.2f},{f['hi']:+.2f}]"
                 f" {f['cost_per_success'] * 100:.2f}c"))
    for p in pick_rows:
        print("  PICK", p["goal"], p["candidate"], [(x.get("name"), x.get("delta")) for x in p["full"]])
    print("  holders", out["holders"], "cheapest", out["cheapest_holder"])
    print("  finalists", finalists)
    print("  spearman", {k: v and round(v, 2) for k, v in corr.items()})
    print("  spent", out["spent"])


if __name__ == "__main__":
    main()
