"""Rebuild the published step-check numbers from the per-call rows and check them against the results file.

  python3 scripts/step_check_tables.py            # prints the tables; exits non-zero on any mismatch

Reads results/runs/step_calls.jsonl (one row per candidate reply to one sampled recorded call) and recomputes, per use
case and model: calls sampled / answered / failed, tool-choice agreement, same arguments given the same tool, exact
agreement, judged agreement (exact or ruled equivalent by the judge), and agreement on state-changing steps, each with
a Wilson 95% interval. Then the analyzer's verdicts: comparable = failure rate <= 0.2 and tool-choice rate within 0.10
of the best rate in the use case (Sonnet's own replay included), and the rank by tool choice among candidates with a
failure rate <= 0.2 (ties keep the candidate order of the results file). Every recomputed value is compared with
results/model-swap-on-recorded-traffic.json. Batch selection is the one the analysis used: batches A, B and G; GPT-6
models from batch G only (batch A ran them through /chat/completions and is superseded); Sonnet's batch-B replay is a
second noise-floor reference. Standard library only; no network.
"""
import json
import os
import sys
from collections import Counter, defaultdict

BENCH = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ROWS = os.path.join(BENCH, "results", "runs", "step_calls.jsonl")
RESULTS = os.path.join(BENCH, "results", "model-swap-on-recorded-traffic.json")
UCS = ["support", "invoice_extraction", "claims_triage", "kyc_checks"]
INC = "sonnet-5.5"
AGREE = {"same_tool_same_args", "same_text"}
SAME_TOOL = {"same_tool_same_args", "same_tool_different_args"}
WRITES = {"support": {"issue_refund", "open_dispute", "freeze_card", "escalate_to_human"},
          "invoice_extraction": {"submit_invoice", "hold_invoice", "reject_invoice"},
          "claims_triage": {"request_documents", "deny_claim", "route_claim", "set_reserve"},
          "kyc_checks": {"approve_application", "escalate_to_compliance", "request_more_info", "reject_application"}}


def r4(x):
    return None if x is None else round(x, 4)


def wilson(k, n, z=1.96):
    if not n:
        return None
    p = k / n
    c = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / (1 + z * z / n)
    m = (p + z * z / (2 * n)) / (1 + z * z / n)
    return [round(m - c, 4), round(m + c, 4)]


def counts():
    stats = defaultdict(Counter)
    for line in open(ROWS):
        r = json.loads(line)
        if r["batch"] not in ("A", "B", "G") or r["attempt"] or r["not_run"]:
            continue
        if r["batch"] == "A" and r["candidate"].startswith("gpt-6"):
            continue
        key = (r["use_case"], r["candidate"], "B" if r["candidate"] == INC and r["batch"] == "B" else "main")
        s = stats[key]
        s["sampled"] += 1
        if r["agreement"] is None:
            s["failed"] += 1
            continue
        a = r["agreement"]
        s["answered"] += 1
        s[a] += 1
        s["agree"] += a in AGREE
        if r["recorded_tools"]:
            s["tool_steps"] += 1
            s["same_tool"] += a in SAME_TOOL
        else:
            s["text_steps"] += 1
        if a not in AGREE:
            s["disagreements"] += 1
            s["judge_equivalent"] += r["judge_equivalent"] is True
            s["judge_different"] += r["judge_equivalent"] is False
            s["judge_unsure_or_none"] += r["judge_equivalent"] is None
        s["agree_or_equiv"] += a in AGREE or r["judge_equivalent"] is True
        if set(r["recorded_tools"]) & WRITES[r["use_case"]]:
            s["write_steps"] += 1
            s["write_same_tool"] += a in SAME_TOOL
            s["write_same_tool_same_args"] += a == "same_tool_same_args"
    return stats


def entry(s):
    ts, st, sa, ws = s["tool_steps"], s["same_tool"], s["same_tool_same_args"], s["write_steps"]
    return {
        "n_calls_sampled": s["sampled"], "n_calls_answered": s["answered"], "n_calls_failed": s["failed"],
        "tool_choice": dict(n=ts, same_tool=st, rate=r4(st / ts) if ts else None, ci95=wilson(st, ts)),
        "args_given_same_tool": dict(n=st, same_args=sa, rate=r4(sa / st) if st else None, ci95=wilson(sa, st)),
        "text_replies": dict(n=s["text_steps"], same_text=s["same_text"],
                             rate=r4(s["same_text"] / s["text_steps"]) if s["text_steps"] else None),
        "exact_agreement": dict(n=s["answered"], agreeing=s["agree"], rate=r4(s["agree"] / s["answered"]),
                                ci95=wilson(s["agree"], s["answered"])),
        "judged": dict(n_disagreements=s["disagreements"], judged_equivalent=s["judge_equivalent"],
                       judged_different=s["judge_different"], judged_unsure_or_unjudged=s["judge_unsure_or_none"],
                       judged_agreement=dict(n=s["answered"], agreeing_or_equivalent=s["agree_or_equiv"],
                                             rate=r4(s["agree_or_equiv"] / s["answered"]),
                                             ci95=wilson(s["agree_or_equiv"], s["answered"]))),
        "state_changing_steps": dict(n=ws, same_tool=s["write_same_tool"],
                                     same_tool_rate=r4(s["write_same_tool"] / ws) if ws else None,
                                     same_tool_same_args=s["write_same_tool_same_args"],
                                     same_tool_same_args_rate=r4(s["write_same_tool_same_args"] / ws) if ws else None),
    }


def main():
    pub = json.load(open(RESULTS))
    stats = counts()
    published = {}
    for x in pub["replays_and_step_checks"]:
        if x["kind"] == "step_check":
            ref_b = x["model"] == INC and x["analyzer_batch"] == "B"
            published[(x["use_case"], x["model"], "B" if ref_b else "main")] = x
    bad = 0
    checked = 0
    for key, x in sorted(published.items()):
        mine = entry(stats[key])
        for field, val in mine.items():
            checked += 1
            if x[field] != val:
                bad += 1
                print("MISMATCH", key, field, "published", x[field], "recomputed", val)
    print(f"step-check entries: {len(published)}, fields compared: {checked}, mismatches: {bad}\n")
    for uc in UCS:
        rows = pub["results"][uc]
        rates = {}
        for r in rows:
            s = stats[(uc, r["model"], "main")]
            tc = s["same_tool"] / s["tool_steps"] if s["tool_steps"] else None
            fail = s["failed"] / s["sampled"] if s["sampled"] else None
            rates[r["model"]] = (tc, fail)
        best = max(tc for tc, f in rates.values() if f <= 0.2 and tc is not None)
        ranked = [r["model"] for r in rows if r["role"] != "incumbent" and rates[r["model"]][1] <= 0.2]
        ranked.sort(key=lambda m: -rates[m][0])
        print(f"== {uc}: best tool-choice rate {best:.4f}; comparable if >= {best - 0.1:.4f} and failure <= 0.2")
        print(f"   {'model':30s} {'tool choice':>11s} {'exact':>6s} {'judged':>6s} {'fail':>6s}  verdict          rank")
        for r in rows:
            tc, fail = rates[r["model"]]
            e = entry(stats[(uc, r["model"], "main")])
            v = r["analyzer_verdict"]
            line = (f"   {r['model']:30s} {tc:11.4f} {e['exact_agreement']['rate']:6.4f} "
                    f"{e['judged']['judged_agreement']['rate']:6.4f} {fail:6.3f}  ")
            if v is None:
                print(line + "(reference)")
                continue
            comparable = tc >= best - 0.1 and fail <= 0.2
            rank = ranked.index(r["model"]) + 1 if r["model"] in ranked else None
            ok = comparable == v["comparable"] and rank == v["rank_by_tool_choice"]
            checked += 2
            if not ok:
                bad += 1
                print("MISMATCH verdict", uc, r["model"], (comparable, rank), "published", v)
            print(line + f"{'comparable' if comparable else 'not comparable':16s} {rank}"
                  + (f"  picked as: {', '.join(v['picked_as'])}" if v["picked_as"] else ""))
        print()
    print(f"total values compared: {checked}, mismatches: {bad}")
    sys.exit(1 if bad else 0)


if __name__ == "__main__":
    main()
