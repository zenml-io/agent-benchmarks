"""Does the model-swap analyzer's step-level screen pick models that hold task success? (finance and insurance)

  .venv/bin/python src/analyze.py      # writes out/calibration.json and prints a summary (from this benchmark's dir)

Ground truth: each candidate's full-run success on the same audited tasks as the incumbent (Sonnet 5.5), from the
Haiku Tax grid (HAIKU_TAX_RESULTS, default ../haiku-tax/results), as a paired difference with a bootstrap 95% interval.
Those full-run rows are not in the public repo (the Haiku Tax results are withheld); without them every `full` field is
null and the ground-truth sections (correlations, confusion, finalists, incumbent) are skipped. Step-level numbers: the
analyzer's own report (out/<use_case>{A,B,G}/report.json, merged: batch B's Sonnet run is a second reference), plus
agreement on the steps where Sonnet called a state-changing tool, recomputed from calls.jsonl with the analyzer's own
`compare`.
"""
import json
import os
import random
import sys
from collections import defaultdict
from decimal import Decimal

from kitaru_model_swap import report as R

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HT = os.environ.get("HAIKU_TAX_DIR", os.path.join(os.path.dirname(BENCH), "haiku-tax"))
HT_RESULTS = os.environ.get("HAIKU_TAX_RESULTS", os.path.join(HT, "results"))
sys.path.insert(0, HT)
from harness import models as M  # noqa: E402

USE_CASES = ["support", "invoice_extraction", "claims_triage", "kyc_checks"]
LABEL = {"support": "Bank support tickets", "invoice_extraction": "Invoice extraction",
         "claims_triage": "Insurance claims triage", "kyc_checks": "KYC document checks"}
WRITES = {"support": {"issue_refund", "open_dispute", "freeze_card", "escalate_to_human"},
          "invoice_extraction": {"submit_invoice", "hold_invoice", "reject_invoice"},
          "claims_triage": {"request_documents", "deny_claim", "route_claim", "set_reserve"},
          "kyc_checks": {"approve_application", "escalate_to_compliance", "request_more_info", "reject_application"}}
INCUMBENT = "sonnet-5.5"
NONINFERIOR = 0.05  # "holds quality": full-run success at most 5 points below the incumbent's
AGREE = {"same_tool_same_args", "same_text"}


def full_runs(uc):
    excluded = json.load(open(os.path.join(HT, "audit_exclusions.json"))).get(uc, {})
    out = {}
    d = os.path.join(HT_RESULTS, uc)
    if not os.path.isdir(d):
        return out
    for f in os.listdir(d):
        if not f.endswith("__none.jsonl"):
            continue
        rows = {}
        for line in open(os.path.join(d, f)):
            r = json.loads(line)
            if r["task"] not in excluded and r.get("status") not in ("api_error", "account_blocked"):
                rows[r["task"]] = r
        out[f.split("__")[0]] = rows
    return out


def paired(cand, inc, rng):
    tasks = sorted(set(cand) & set(inc))
    diffs = [int(cand[t]["success"]) - int(inc[t]["success"]) for t in tasks]
    n = len(diffs)
    boots = sorted(sum(rng.choice(diffs) for _ in range(n)) / n for _ in range(2000))
    return dict(n=n, delta=sum(diffs) / n, lo=boots[50], hi=boots[1949],
                success=sum(cand[t]["success"] for t in tasks) / n,
                cost_per_success=(sum(cand[t]["cost"] for t in tasks) / max(1, sum(cand[t]["success"] for t in tasks))))


def wilson(k, n, z=1.96):
    if n == 0:
        return None, None
    p = k / n
    c = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    m = (p + z * z / (2 * n)) / (1 + z * z / n)
    return m - c, m + c


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


def step_stats(uc):
    """Per candidate (and per batch for the reference): rates from calls.jsonl, attempt 0."""
    stats = defaultdict(lambda: defaultdict(int))
    responses = os.path.exists(os.path.join(BENCH, "out", uc + "G", "calls.jsonl"))
    for tag in "ABG":
        p = os.path.join(BENCH, "out", uc + tag, "calls.jsonl")
        if not os.path.exists(p):
            continue
        for line in open(p):
            r = json.loads(line)
            if r["attempt"] or r["not_run"]:
                continue
            if responses and tag == "A" and r["candidate"].startswith("gpt-6"):
                continue  # superseded by the Responses API run (G)
            name = r["candidate"] + (" (rerun B)" if r["candidate"] == INCUMBENT and tag == "B" else "")
            s = stats[name]
            s["calls"] += 1
            if r["agreement"] is None:
                s["failed"] += 1
                continue
            s["answered"] += 1
            s["agree"] += r["agreement"] in AGREE
            # Jev's "equivalent" ruling standing in for a reviewer's "both acceptable"
            s["agree_or_equiv"] += r["agreement"] in AGREE or r["judge_equivalent"] is True
            rec_tools = {t[0] for t in r["recorded"]}
            if rec_tools & WRITES[uc]:
                s["write_steps"] += 1
                s["write_agree"] += r["agreement"] == "same_tool_same_args"
                s["write_tool"] += r["agreement"] in ("same_tool_same_args", "same_tool_different_args")
    return stats


def main():
    rng = random.Random(0)
    out = {"use_cases": {}, "pooled": {}}
    pooled = defaultdict(list)
    for uc in USE_CASES:
        reports = {}
        for tag in "ABG":
            p = os.path.join(BENCH, "out", uc + tag, "report.json")
            if os.path.exists(p):
                reports[tag] = json.load(open(p))
        if not reports:
            continue
        runs = full_runs(uc)
        inc = runs.get(INCUMBENT, {})
        steps = step_stats(uc)
        merged = []
        for tag, rep in reports.items():
            for c in rep["candidates"]:
                if tag == "B" and c["reference"]:
                    continue
                if tag == "A" and "G" in reports and c["name"].startswith("gpt-6"):
                    continue  # GPT-6 ran again through the Responses API, reasoning on as in its full runs
                merged.append(c)
        picks = R._best_for(merged)
        rows = []
        for c in merged:
            name = c["name"]
            gt = paired(runs[name], inc, rng) if name in runs and name != INCUMBENT else None
            s = steps.get(name, {})
            ws = s.get("write_steps", 0)
            row = dict(name=name, reference=c["reference"], open_weights=c["open_weights"],
                       tool_choice=c["tool_choice_rate"], exact=c["agreement_rate"], failure=c["failure_rate"],
                       answered=s.get("answered", 0), tool_choice_ci=wilson(round((c["tool_choice_rate"] or 0) *
                                                                                   s.get("answered", 0)),
                                                                             s.get("answered", 0)),
                       write_steps=ws, write_exact=(s.get("write_agree", 0) / ws) if ws else None,
                       write_tool=(s.get("write_tool", 0) / ws) if ws else None,
                       judge_adjusted=(s["agree_or_equiv"] / s["answered"]) if s.get("answered") else None,
                       step_cost_per_call=c["cost"]["per_call_usd"], full=gt,
                       config_mismatch=name.startswith("gpt-6") and "G" not in reports)
            rows.append(row)
        ref_b = steps.get(INCUMBENT + " (rerun B)")
        noise = dict(A=next((r["tool_choice"] for r in rows if r["reference"]), None),
                     B_exact=(ref_b["agree"] / ref_b["answered"]) if ref_b and ref_b["answered"] else None)
        cands = [r for r in rows if r["full"] and not r["reference"]]
        corr = {}
        for metric in ("tool_choice", "exact", "judge_adjusted", "write_exact", "write_tool"):
            for variant, keep in (("", lambda r: True), ("_no_gpt6", lambda r: not r["config_mismatch"])):
                xs = [(r[metric], r["full"]["success"]) for r in cands if r[metric] is not None and keep(r)]
                corr[metric + variant] = spearman([x for x, _ in xs], [y for _, y in xs]) if len(xs) > 2 else None
                pooled[metric + variant] += [(uc, r[metric], r["full"]["delta"]) for r in cands
                                             if r[metric] is not None and keep(r)]
        # The analyzer's "comparable" set (within 10 points of the closest) vs truly non-inferior in full runs
        usable = [r for r in cands if (r["failure"] or 0) <= 0.2 and r["tool_choice"] is not None]
        best = max((r["tool_choice"] for r in rows if (r["failure"] or 0) <= 0.2 and r["tool_choice"] is not None),
                   default=0)
        confusion = defaultdict(list)
        for r in usable:
            said = r["tool_choice"] >= best - 0.1
            true = r["full"]["delta"] >= -NONINFERIOR
            confusion[f"{'comparable' if said else 'not comparable'} / {'holds' if true else 'loses'}"].append(
                r["name"])
        pick_rows = []
        for p in picks:
            names = p["candidate"].split(" + ")
            pick_rows.append(dict(goal=p["goal"], candidate=p["candidate"], why=p["why"],
                                  full=[dict(name=n, **(next((r["full"] for r in rows if r["name"] == n and r["full"]),
                                                             None) or {})) for n in names]))
        mix = {t: rep.get("best_mix") for t, rep in reports.items()}
        # Finalists: the top 3 by tool choice go to a full replay. Do they contain a model that holds quality, and the
        # cheapest one that does?
        ranked = sorted(usable, key=lambda r: -r["tool_choice"])
        holders = [r for r in cands if r["full"]["delta"] >= -NONINFERIOR]
        if not inc:  # no full-run ground truth available: step-level numbers only
            ranked = []
        cheapest_holder = min(holders, key=lambda r: r["full"]["cost_per_success"], default=None)
        finalists = dict(top3=[r["name"] for r in ranked[:3]],
                         holders_in_top3=[r["name"] for r in ranked[:3] if r["full"]["delta"] >= -NONINFERIOR],
                         cheapest_holder=cheapest_holder and cheapest_holder["name"],
                         cheapest_holder_rank=next((i + 1 for i, r in enumerate(ranked)
                                                    if cheapest_holder and r["name"] == cheapest_holder["name"]), None))
        out["use_cases"][uc] = dict(label=LABEL[uc], rows=rows, picks=pick_rows, spearman=corr, noise=noise,
                                    confusion=dict(confusion), best_mix=mix, finalists=finalists,
                                    incumbent=None if not inc else dict(success=sum(r["success"] for r in inc.values()) / len(inc),
                                                   n=len(inc), cost_per_success=sum(r["cost"] for r in inc.values()) /
                                                   max(1, sum(r["success"] for r in inc.values()))),
                                    spent={t: rep.get("spent_usd") for t, rep in reports.items()},
                                    coverage={t: rep.get("coverage") for t, rep in reports.items()})
    for metric in pooled:
        # The analyzer is read one agent at a time, so average the within-use-case correlations (rates are not
        # comparable across use cases)
        vals = [u["spearman"][metric] for u in out["use_cases"].values() if u["spearman"].get(metric) is not None]
        out["pooled"][metric] = sum(vals) / len(vals) if vals else None
    os.makedirs(os.path.join(BENCH, "out"), exist_ok=True)
    json.dump(out, open(os.path.join(BENCH, "out", "calibration.json"), "w"), indent=1, default=str)
    for uc, u in out["use_cases"].items():
        inc_txt = f"{u['incumbent']['success']:.0%} (n={u['incumbent']['n']})" if u["incumbent"] else "n/a (no full runs)"
        print(f"\n== {u['label']}  incumbent {inc_txt}  "
              f"noise {u['noise']}  spearman {({k: round(v, 2) if v is not None else None for k, v in u['spearman'].items()})}")
        for r in sorted(u["rows"], key=lambda r: -(r["tool_choice"] or 0)):
            f = r["full"]
            print(f"  {r['name']:28} tool {r['tool_choice']!s:7} exact {r['exact']!s:7} write {r['write_exact'] and round(r['write_exact'], 2)!s:5}"
                  f" fail {r['failure']!s:5} | full {'' if not f else f'{f[chr(115)+chr(117)+chr(99)+chr(99)+chr(101)+chr(115)+chr(115)]:.0%} d {f[chr(100)+chr(101)+chr(108)+chr(116)+chr(97)]:+.1%} [{f[chr(108)+chr(111)]:+.2f},{f[chr(104)+chr(105)]:+.2f}]'}")
        for p in u["picks"]:
            print("  PICK", p["goal"], p["candidate"], [(x.get("name"), x.get("delta")) for x in p["full"]])
        print("  confusion", u["confusion"])
        print("  finalists", u["finalists"])
        print("  judge_adjusted", {r["name"]: r["judge_adjusted"] and round(r["judge_adjusted"], 3) for r in u["rows"]})
    print("\nmean within-use-case spearman:", {k: round(v, 2) for k, v in out["pooled"].items()})


if __name__ == "__main__":
    main()
