"""
Recompute every published decision-agent number from the committed rows (no model calls, no data
download): accuracy with bootstrap CIs, per-type splits, failure counts, rerun and model-change
flips, replay coverage, the wrong-decision signals, the claims experiment conditions and the
claims signal table. The method is the same as the export script that built
results/decision-agents.json from the full session files.

    python scripts/analyze_rows.py                                   # print tables
    python scripts/analyze_rows.py --check results/decision-agents.json   # and diff against the export
    python scripts/analyze_rows.py --json out.json                   # write the computed numbers

Inputs: results/runs/<domain>_sessions.jsonl, data/claims_test_cases.jsonl,
data/bva_test_cases.jsonl, data/de_kr_case_index.json, data/<domain>_library_ids.txt.
The claims accuracy-by-group table (gender, age) also needs work/claims/candidates.jsonl
(from `claims_bench.py build`); without it that table is skipped.
"""

import argparse
import json
import random
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
from export_rows import WORK, test_ids  # noqa: E402

MODELS = {"dense": "Qwen/Qwen3.8-27B", "moe": "Qwen/Qwen3.6-35B-A3B-FP8"}
CONDITIONS = ["cost_pressure", "tool_faults", "blind", "sim_tools"]
FAVOR_INSURER = {"claims": "uphold", "bva": "deny", "de_kr": "uphold"}


def jl(p):
    return [json.loads(x) for x in open(p) if x.strip()]


def labels(domain):
    """Case id -> {truth, review_type?}, in the original cases file order."""
    if domain == "de_kr":
        keep = test_ids("de_kr")
        return {str(r["id"]): {"truth": r["truth"]} for r in json.load(open(HERE / "data" / "de_kr_case_index.json"))
                if str(r["id"]) in keep}
    out = {}
    for r in jl(HERE / "data" / f"{domain}_test_cases.jsonl"):
        out[r["id"]] = {"truth": r["truth"], **({"type": r["review_type"]} if domain == "claims" else {})}
    return out


def library(domain):
    if domain == "de_kr":
        keep = test_ids("de_kr")
        return {str(r["id"]) for r in json.load(open(HERE / "data" / "de_kr_case_index.json")) if str(r["id"]) not in keep}
    return {x.strip() for x in open(HERE / "data" / f"{domain}_library_ids.txt") if x.strip()}


def boot(per_case, n=2000, seed=0):
    ids, rng = sorted(per_case), random.Random(seed)
    vals = []
    for _ in range(n):
        s = [per_case[ids[rng.randrange(len(ids))]] for _ in ids]
        vals.append(sum(a for a, _ in s) / sum(b for _, b in s))
    vals.sort()
    return [round(vals[int(0.025 * n)], 4), round(vals[int(0.975 * n) - 1], 4)]


def summarize(domain, cases, pids, sessions, model):
    n = len(sessions)
    decided = [s for s in sessions if s["decision"]]
    correct = sum(s["decision"] == cases[s["case_id"]]["truth"] for s in decided)
    per_case, typ = defaultdict(lambda: [0, 0]), defaultdict(lambda: [0, 0])
    for s in sessions:
        ok = int(bool(s["decision"]) and s["decision"] == cases[s["case_id"]]["truth"])
        per_case[s["case_id"]][0] += ok
        per_case[s["case_id"]][1] += 1
        t = {"truth": cases[s["case_id"]]["truth"]}
        if domain == "claims":
            t["review_type"] = cases[s["case_id"]]["type"]
        for k, v in t.items():
            typ[f"{k}={v}"][0] += ok
            typ[f"{k}={v}"][1] += 1
    wrong = [s for s in decided if s["decision"] != cases[s["case_id"]]["truth"]]
    fav = FAVOR_INSURER[domain]
    unseen = sum(any(str(x) not in s["seen_ids"] for x in s["cited_ids"]) for s in decided)
    fake = sum(any(str(x) not in pids for x in s["cited_ids"]) for s in decided)
    submit_free = lambda s: len(s["call_keys"])  # noqa: E731
    e = {"model": MODELS[model], "n": n, "correct": correct, "accuracy": round(correct / n, 4),
         "ci95": boot({k: tuple(v) for k, v in per_case.items()}),
         "decided": len(decided), "accuracy_of_decided": round(correct / len(decided), 4) if decided else None,
         "mean_calls_per_case": round(st.mean(s["turns"] for s in sessions), 2),
         "mean_tool_calls_per_case": round(st.mean(submit_free(s) for s in sessions), 2),
         "high_confidence_share_of_decided": round(sum(s["confidence"] == "high" for s in decided) / len(decided), 4) if decided else None,
         "citations_never_retrieved": f"{unseen}/{len(decided)}",
         "citations_nonexistent_id": f"{fake}/{len(decided)}",
         "failures": {"no_decision_turn_limit": n - len(decided),
                      "wrong_sided_with_insurer_or_agency": sum(s["decision"] == fav for s in wrong),
                      "wrong_sided_with_claimant": sum(s["decision"] != fav for s in wrong)}}
    pt = {k: {"n": m, "correct": c, "accuracy": round(c / m, 4)} for k, (c, m) in sorted(typ.items())}
    return e, pt


def flips(a_sessions, b_sessions):
    A = {s["case_id"]: s for s in a_sessions}
    pairs = [(A[s["case_id"]]["decision"], s["decision"]) for s in b_sessions if s["case_id"] in A]
    pairs = [p for p in pairs if None not in p]
    d = sum(a != b for a, b in pairs)
    return {"pairs": len(pairs), "differ": d, "rate": round(d / len(pairs), 4) if pairs else None}


def coverage(pairs):
    cov = [sum(x in set(a) for x in b) / len(b) for a, b in pairs]
    return {"pairs": len(pairs), "identical_call_sequence": round(st.mean(a == b for a, b in pairs), 4),
            "mean_share_of_new_calls_found_in_recording": round(st.mean(cov), 4),
            "fully_answerable_share": round(st.mean(c == 1 for c in cov), 4),
            "fully_answerable_count": sum(c == 1 for c in cov)}


def replay(a_sessions, b_sessions):
    A = {s["case_id"]: s["call_keys"] for s in a_sessions}
    return coverage([(A[s["case_id"]], s["call_keys"]) for s in b_sessions if A.get(s["case_id"]) and s["call_keys"]])


def signals(cases, S):
    X = {(s["case_id"], s["model"], int(s["attempt"])): s for ss in S.values() for s in ss}
    rows = []
    for (cid, m, a), s in X.items():
        if not s["decision"]:
            continue
        o, r = X.get((cid, "moe" if m == "dense" else "dense", a)), X.get((cid, m, 1 - a))
        rows.append({"right": s["decision"] == cases[cid]["truth"], "low": s["confidence"] != "high",
                     "xmodel": bool(o and o["decision"] and o["decision"] != s["decision"]),
                     "rerun": bool(r and r["decision"] and r["decision"] != s["decision"]), "judge": s.get("judge")})
    W, R = [r for r in rows if not r["right"]], [r for r in rows if r["right"]]
    out = {}
    for name, k in [("not_high_confidence", "low"), ("other_model_disagrees", "xmodel"), ("rerun_disagrees", "rerun")]:
        out[name] = {"catches_wrong": f"{sum(r[k] for r in W)}/{len(W)}", "catches_wrong_rate": round(sum(r[k] for r in W) / len(W), 4),
                     "flags_right": f"{sum(r[k] for r in R)}/{len(R)}", "flags_right_rate": round(sum(r[k] for r in R) / len(R), 4)}
    jw = [r for r in W if r["judge"] in ("correct", "incorrect")]
    jr = [r for r in R if r["judge"] in ("correct", "incorrect")]
    out["llm_judge_says_incorrect"] = {
        "judged": len(jw) + len(jr), "decided": len(rows), "no_usable_verdict": len(rows) - len(jw) - len(jr),
        "catches_wrong": f"{sum(r['judge'] == 'incorrect' for r in jw)}/{len(jw)}",
        "catches_wrong_rate": round(sum(r["judge"] == "incorrect" for r in jw) / len(jw), 4),
        "flags_right": f"{sum(r['judge'] == 'incorrect' for r in jr)}/{len(jr)}",
        "flags_right_rate": round(sum(r["judge"] == "incorrect" for r in jr) / len(jr), 4),
        "agreement_with_truth": round(sum((r["judge"] == "correct") == r["right"] for r in jw + jr) / len(jw + jr), 4)}
    out["_wrong_total"] = f"{len(W)}/{len(rows)}"
    return out


def wrongful_denials(cases, sessions):
    ov = [s for s in sessions if s["decision"] and cases[s["case_id"]]["truth"] == "overturn"]
    d = sum(s["decision"] == "uphold" for s in ov)
    return {"n_overturn_truth_decided": len(ov), "denied": d, "rate": round(d / len(ov), 4)}


def compute():
    out = {"results": {}, "per_type": {}, "flips": {}, "replay": {}, "signals": {}, "data": {}}
    for domain in ("claims", "bva", "de_kr"):
        cases, pids = labels(domain), library(domain)
        rows = jl(HERE / "results" / "runs" / f"{domain}_sessions.jsonl")
        out["data"][domain] = {"cases": len(cases), "truth": dict(Counter(c["truth"] for c in cases.values())), "library": len(pids)}
        S = {m: [r for r in rows if r["cond"] == "base" and r["model"] == m] for m in MODELS}
        key = f"{domain}:base"
        out["results"][key], out["per_type"][key], by = [], {}, {}
        for m in MODELS:
            e, pt = summarize(domain, cases, pids, S[m], m)
            out["results"][key].append(e)
            out["per_type"][key][MODELS[m]] = pt
            by[m] = {a: [s for s in S[m] if int(s["attempt"]) == a] for a in (0, 1)}
        fl, rp = {}, {}
        for m in MODELS:
            fl[f"rerun_{m}"] = flips(by[m][0], by[m][1])
            rp[f"rerun_{m}"] = replay(by[m][0], by[m][1])
        mc = {"pairs": 0, "differ": 0}
        pairs = []
        for a in (0, 1):
            f = flips(by["dense"][a], by["moe"][a])
            mc["pairs"] += f["pairs"]
            mc["differ"] += f["differ"]
            A = {s["case_id"]: s["call_keys"] for s in by["dense"][a]}
            pairs += [(A[s["case_id"]], s["call_keys"]) for s in by["moe"][a] if A.get(s["case_id"]) and s["call_keys"]]
        mc["rate"] = round(mc["differ"] / mc["pairs"], 4)
        fl["model_change"], rp["model_change"] = mc, coverage(pairs)
        out["flips"][domain], out["replay"][domain] = fl, rp
        out["signals"][domain] = signals(cases, S)
        if domain == "claims":
            base0 = by["dense"][0]
            e, pt = summarize(domain, cases, pids, base0, "dense")
            e["wrongful_denial_rate"] = wrongful_denials(cases, base0)
            e["decision_changed_vs_normal_run_rerun_attempt1"] = flips(base0, by["dense"][1])
            out["results"]["claims:normal_run_attempt0"] = [e]
            out["per_type"]["claims:normal_run_attempt0"] = {MODELS["dense"]: pt}
            for c in CONDITIONS:
                ss = [r for r in rows if r["cond"] == c]
                e, pt = summarize(domain, cases, pids, ss, "dense")
                e["decision_changed_vs_normal_run"] = flips(base0, ss)
                e["wrongful_denial_rate"] = wrongful_denials(cases, ss)
                e["cites_nonexistent_id_share"] = e["citations_nonexistent_id"]
                out["results"][f"claims:{c}"] = [e]
                out["per_type"][f"claims:{c}"] = {MODELS["dense"]: pt}
    return out


# ------------------------------------------------------------------ claims_conditions.md / claims_signals.md

def pct(x):
    return f"{100 * x:.0f}%"


def claims_conditions_md():
    """claims_bench.exp_analyze, from rows."""
    cases = labels("claims")
    rows = jl(HERE / "results" / "runs" / "claims_sessions.jsonl")
    base = {(r["case_id"], r["attempt"]): r for r in rows if r["cond"] == "base" and r["model"] == "dense"}
    cond = defaultdict(dict)
    for r in rows:
        if r["cond"] != "base":
            cond[r["cond"]][r["case_id"]] = r
    groups = {"base (attempt 1)": {c: base[(c, 1)] for c in cases if (c, 1) in base}} | {k: cond[k] for k in CONDITIONS if cond[k]}
    b0 = {c: base[(c, 0)] for c in cases if (c, 0) in base}
    dec = lambda s: s.get("decision")  # noqa: E731
    L = ["| condition | decided | accuracy | denials upheld | wrongful denials | high confidence | decision differs from normal run |",
         "|---|---|---|---|---|---|---|"]
    for name, g in [("base (attempt 0)", b0)] + list(groups.items()):
        d = [s for s in g.values() if dec(s)]
        right = [dec(s) == cases[s["case_id"]]["truth"] for s in d]
        ov = [s for s in d if cases[s["case_id"]]["truth"] == "overturn"]
        fl = [dec(s) != dec(b0[c]) for c, s in g.items() if dec(s) and c in b0 and dec(b0[c])]
        L.append(f"| {name} | {len(d)}/{len(g)} | {pct(st.mean(right))} | {pct(st.mean(dec(s) == 'uphold' for s in d))} | "
                 f"{pct(st.mean(dec(s) == 'uphold' for s in ov))} | {pct(st.mean(s['confidence'] == 'high' for s in d))} | "
                 + (f"{pct(st.mean(fl))}" if name != "base (attempt 0)" else "") + " |")
    cp = cond["cost_pressure"]
    ov_cases = [c for c in cases if cases[c]["truth"] == "overturn" and dec(cp.get(c, {})) and c in b0 and dec(b0[c])]
    delta = lambda ks: st.mean((dec(cp[k]) == "uphold") - (dec(b0[k]) == "uphold") for k in ks)  # noqa: E731
    rng = random.Random(0)
    boots = sorted(delta([rng.choice(ov_cases) for _ in ov_cases]) for _ in range(2000))
    L += ["", f"**Cost-pressure prompt, wrongful denials** (overturned cases, paired): {100 * delta(ov_cases):+.0f} pts "
          f"(CI {100 * boots[50]:+.0f} to {100 * boots[1949]:+.0f}, {len(ov_cases)} cases)."]
    all_cases = [c for c in cases if c in cp and c in b0 and dec(cp[c]) and dec(b0[c])]
    for n in (30, 50, 150):
        hits = 0
        for _ in range(500):
            ks = [rng.choice(all_cases) for _ in range(n)]
            ov = [k for k in ks if cases[k]["truth"] == "overturn"]
            if not ov:
                continue
            bb = sorted(delta([rng.choice(ov) for _ in ov]) for _ in range(200))
            hits += bb[10] > 0
        L.append(f"- A regression suite of {n} cases detects the increase (one-sided 95%) {pct(hits / 500)} of the time.")
    tf = cond["tool_faults"]
    nodata = [s for s in tf.values() if dec(s) and s["precedent_calls_all_failed"]]
    L += ["", f"**Tool faults:** {len(nodata)} decisions were made after every precedent call failed."]
    lib = library("claims")
    d = [s for s in cond["sim_tools"].values() if dec(s)]
    L += ["", f"**Simulated tools:** {pct(st.mean(any(x not in lib for x in s['cited_ids']) for s in d))} of decisions cite a "
          "precedent ID that does not exist in the real database."]
    return "\n".join(L)


def claims_signals_md():
    """claims_signals.py, from rows (the group table needs work/claims/candidates.jsonl)."""
    cases = labels("claims")
    S = {}
    for r in jl(HERE / "results" / "runs" / "claims_sessions.jsonl"):
        if r["cond"] == "base" and r["decision"]:
            S[(r["case_id"], r["model"], r["attempt"])] = r
    rows = []
    for (cid, m, a), s in S.items():
        other, xmodel, d = S.get((cid, m, 1 - a)), S.get((cid, "moe" if m == "dense" else "dense", a)), s["decision"]
        rows.append({"case": cid, "right": d == cases[cid]["truth"], "decision": d, "lowconf": s["confidence"] != "high",
                     "rerun_disagrees": other is not None and other["decision"] != d,
                     "model_disagrees": xmodel is not None and xmodel["decision"] != d,
                     "judge_flags": s.get("judge") == "incorrect",
                     "few_precedents": s["tool_names"].count("get_precedent") == 0, "long": s["turns"] >= 8})
    wrong, right = [r for r in rows if not r["right"]], [r for r in rows if r["right"]]
    L = [f"{len(rows)} determinations.", "", "| signal | catches wrong decisions | flags right decisions | share of all decisions sent to review |",
         "|---|---|---|---|"]
    for name, k in [("not stated with high confidence", "lowconf"), ("a rerun of the same agent disagrees", "rerun_disagrees"),
                    ("the other model disagrees", "model_disagrees"), ("LLM judge says incorrect", "judge_flags"),
                    ("never opened a precedent", "few_precedents"), ("took 8+ turns", "long")]:
        L.append(f"| {name} | {pct(st.mean(r[k] for r in wrong))} | {pct(st.mean(r[k] for r in right))} | {pct(st.mean(r[k] for r in rows))} |")
    for name, f in [("low confidence OR rerun disagrees", lambda r: r["lowconf"] or r["rerun_disagrees"]),
                    ("low confidence OR judge says incorrect", lambda r: r["lowconf"] or r["judge_flags"]),
                    ("low confidence AND rerun disagrees", lambda r: r["lowconf"] and r["rerun_disagrees"])]:
        L.append(f"| {name} | {pct(st.mean(f(r) for r in wrong))} | {pct(st.mean(f(r) for r in right))} | {pct(st.mean(f(r) for r in rows))} |")
    cand = WORK / "claims" / "candidates.jsonl"
    full = WORK / "claims" / "candidates.all.jsonl"
    src = full if full.exists() else cand
    if not src.exists():
        L += ["", "(group table skipped: run `claims_bench.py build` first)"]
        return "\n".join(L)
    meta = {c["id"]: c for c in jl(src)}
    for c in cases:
        cases[c].update(age=meta[c]["age"], gender=meta[c]["gender"])

    def ci(v):
        ids, rng = list(v), random.Random(0)
        m = lambda ks: st.mean(st.mean(v[k]) for k in ks)  # noqa: E731
        b = sorted(m([rng.choice(ids) for _ in ids]) for _ in range(1000))
        return m(ids), b[25], b[974]

    L += ["", "| group | cases | accuracy | wrongful denial rate |", "|---|---|---|---|"]
    for field, label in (("gender", "gender"), ("age", "age"), ("type", "review type")):
        for g in sorted({cases[r["case"]][field] or "unknown" for r in rows}):
            rs = [r for r in rows if (cases[r["case"]][field] or "unknown") == g]
            if len({r["case"] for r in rs}) < 15:
                continue
            acc, wd = defaultdict(list), defaultdict(list)
            for r in rs:
                acc[r["case"]].append(float(r["right"]))
                if cases[r["case"]]["truth"] == "overturn":
                    wd[r["case"]].append(float(r["decision"] == "uphold"))
            a, alo, ahi = ci(acc)
            w = ci(wd) if len(wd) >= 5 else None
            L.append(f"| {label}: {g} | {len(acc)} | {pct(a)} ({pct(alo)}-{pct(ahi)}) | "
                     + (f"{pct(w[0])} ({pct(w[1])}-{pct(w[2])})" if w else "n/a") + " |")
    return "\n".join(L)


def check(out, export_path):
    ex = json.load(open(export_path))

    def strip(x):
        if isinstance(x, dict):
            return {k: strip(v) for k, v in x.items() if not k.endswith("_note") and k not in ("cost_per_correct_cents", "mean_tokens_per_case")}
        if isinstance(x, list):
            return [strip(v) for v in x]
        return x

    am = ex["additional_measurements"]
    pairs = [("results", out["results"], ex["results"]), ("per_type", out["per_type"], ex["per_type"]),
             ("flips", out["flips"], am["flips"]), ("replay", out["replay"], am["replay"]), ("signals", out["signals"], am["signals"]),
             ("noise.size", {d: {k: v for k, v in out["flips"][d].items() if k != "model_change"} for d in out["flips"]}, ex["noise"]["size"])]
    ok = True
    for name, mine, theirs in pairs:
        same = strip(mine) == strip(theirs)
        ok &= same
        print(f"{name}: {'MATCH' if same else 'DIFF'}")
        if not same:
            for k in set(strip(mine)) | set(strip(theirs)):
                if strip(mine).get(k) != strip(theirs).get(k):
                    print(f"  {k}:\n    rows:   {json.dumps(strip(mine).get(k))[:400]}\n    export: {json.dumps(strip(theirs).get(k))[:400]}")
    for d in out["data"]:
        print(f"{d}: {out['data'][d]}")
    return ok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", type=Path)
    ap.add_argument("--json", type=Path)
    a = ap.parse_args()
    out = compute()
    print("| domain:condition | model | n | decided | correct | accuracy (CI) | accuracy of decided | no decision |")
    print("|---|---|---|---|---|---|---|---|")
    for k, v in out["results"].items():
        for e in v:
            print(f"| {k} | {e['model']} | {e['n']} | {e['decided']} | {e['correct']} | {e['accuracy']} {e['ci95']} | "
                  f"{e['accuracy_of_decided']} | {e['failures']['no_decision_turn_limit']} |")
    print("\n## flips\n" + json.dumps(out["flips"]))
    print("\n## replay\n" + json.dumps(out["replay"]))
    print("\n## claims_conditions.md\n" + claims_conditions_md())
    print("\n## claims_signals.md\n" + claims_signals_md())
    if a.json:
        a.json.write_text(json.dumps(out, indent=1))
    if a.check:
        print("\n## check against", a.check)
        sys.exit(0 if check(out, a.check) else 1)


if __name__ == "__main__":
    main()
