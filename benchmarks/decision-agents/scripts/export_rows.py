"""
Turn session and judgment files into the per-session result rows in results/runs/.

A session file holds the full transcript, which quotes the case file (facts of a real medical,
veterans' or court case) and the agent's reasoning. The rows keep only what the analysis needs:
IDs, the decision and stated confidence, counts, the names of the tools called, a hash of each
tool call (name + normalized arguments, so replay coverage can be recomputed without the
arguments' text), the precedent IDs the agent saw and cited, and the judge's verdict.

    python scripts/export_rows.py                 # reads work/<domain>/, writes results/runs/
    python scripts/export_rows.py --src DIR --out DIR

Row fields: domain, cond ("base" or a claims condition), case_id, model ("dense"/"moe"), attempt,
decision (claims: uphold/overturn, bva: grant/deny, de_kr: uphold = dismiss / overturn = allow;
null = no decision), confidence (low/medium/high; de_kr's niedrig/mittel/hoch mapped), turns
(model turns, max 12), seconds (claims only), tool_names (every call in order, including the
submit call), call_keys (sha1[:16] of each non-submit call's canonical form, in order), seen_ids,
cited_ids, precedent_calls_all_failed (claims only: every precedent call returned an error; null
when there were none), judge (base sessions with a decision: correct / incorrect / null).
"""

import argparse
import hashlib
import json
import os
import random
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "harness"))
from claims_bench import canon, jl  # noqa: E402

WORK = Path(os.environ.get("DECISION_WORK_DIR") or HERE / "work")
SPEC = {
    "claims": dict(submit="submit_determination", seen="seen_precedents", cite="cited_precedents",
                   files=["sessions_dense.jsonl", "sessions_moe.jsonl", "sessions_conditions.jsonl"]),
    "bva": dict(submit="submit_decision", seen="seen", cite="cited_decisions",
                files=["sessions_dense.jsonl", "sessions_moe.jsonl"]),
    "de_kr": dict(submit="submit_entscheidung", seen="seen", cite="zitierte_entscheidungen",
                  files=["sessions_dense.jsonl", "sessions_moe.jsonl"]),
}
DE_CONF = {"hoch": "high", "mittel": "medium", "niedrig": "low"}


def test_ids(domain):
    if domain != "de_kr":
        return {json.loads(x)["id"] for x in open(HERE / "data" / f"{domain}_test_cases.jsonl") if x.strip()}
    # Same seeded split as de_kr_bench.split_cases, which only uses each case's label and file order.
    raw = json.load(open(HERE / "data" / "de_kr_case_index.json"))
    rng = random.Random(0)
    by = {lab: [r for r in raw if r["truth"] == lab] for lab in ("uphold", "overturn")}
    k = min(75, *(len(v) for v in by.values()))
    return {str(r["id"]) for lab in by for r in rng.sample(by[lab], k)}


def key(c):
    return hashlib.sha1(canon(c).encode()).hexdigest()[:16]


def all_failed(s, submit):
    res = [m for m in s.get("transcript", []) if m["role"] == "tool"]
    prec = [m for m, c in zip(res, [c for c in s["calls"] if c["name"] != submit])
            if c["name"] in ("search_precedents", "get_precedent")]
    return (all('"error"' in m["content"][:40] for m in prec)) if prec else None


def rows_for(domain, src):
    sp, ids = SPEC[domain], test_ids(domain)
    J = {(j["case_id"], j["model"], j["attempt"]): j.get("verdict") for j in jl(src / domain / "judgments.jsonl") if j.get("case_id")}
    out = []
    for name in sp["files"]:
        for s in jl(src / domain / name):
            if s.get("case_id") not in ids:
                continue
            final = s.get("final") or {}
            if domain == "de_kr":
                dec, conf = s.get("decision"), DE_CONF.get(final.get("sicherheit"))
            else:
                dec, conf = final.get("decision"), final.get("confidence")
            cond = s.get("cond", "base")
            r = {"domain": domain, "cond": cond, "case_id": s["case_id"], "model": s["model"], "attempt": s["attempt"],
                 "decision": dec, "confidence": conf, "turns": s["turns"]}
            if domain == "claims":
                r["seconds"] = round(s["seconds"], 1)
            r["tool_names"] = [c["name"] for c in s["calls"]]
            r["call_keys"] = [key(c) for c in s["calls"] if c["name"] != sp["submit"]]
            r["seen_ids"] = list(s.get(sp["seen"]) or [])
            r["cited_ids"] = list(final.get(sp["cite"]) or [])
            if domain == "claims":
                r["precedent_calls_all_failed"] = all_failed(s, sp["submit"])
            if cond == "base":
                r["judge"] = J.get((s["case_id"], s["model"], s["attempt"])) if dec else None
            out.append(r)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", type=Path, default=WORK)
    ap.add_argument("--out", type=Path, default=HERE / "results" / "runs")
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    for domain in SPEC:
        rows = rows_for(domain, a.src)
        with (a.out / f"{domain}_sessions.jsonl").open("w") as f:
            for r in rows:
                f.write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"{domain}: {len(rows)} rows")


if __name__ == "__main__":
    main()
