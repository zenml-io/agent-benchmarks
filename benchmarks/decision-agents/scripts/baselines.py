"""
The no-AI baselines from claims.md, bva.md and de_kr.md, recomputed from the fetched public data
(no model calls), plus the claims agent-vs-baseline paired difference from the committed rows.

    python scripts/baselines.py

Needs work/claims/{candidates,precedents}.jsonl (`claims_bench.py build`),
work/bva/{candidates,precedents}.jsonl (`fetch_bva_index.py` + `pin_bva_candidates.py`) and
work/de_kr/cases_raw.jsonl (`de_kr_fetch.py --ids ...`). The code mirrors each bench's
`analyze` function. The de_kr keyword baseline orders candidate words with a set sorted by length
only, so its value depends on Python's hash seed; run with several PYTHONHASHSEED values to see
the spread.
"""

import json
import random
import re
import statistics as st
import sys
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "scripts"))
sys.path.insert(0, str(HERE / "harness"))
from analyze_rows import labels  # noqa: E402
from export_rows import WORK  # noqa: E402


def jl(p):
    return [json.loads(x) for x in open(p) if x.strip()]


def claims():
    lab = labels("claims")
    meta = {c["id"]: c for c in jl(WORK / "claims" / "candidates.all.jsonl" if (WORK / "claims" / "candidates.all.jsonl").exists()
                                   else WORK / "claims" / "candidates.jsonl")}
    cases = {c: {**lab[c], "treatment": meta[c]["treatment"]} for c in lab}
    maj = defaultdict(Counter)
    for p in jl(WORK / "claims" / "precedents.jsonl"):
        maj[p["treatment"].lower()][p["decision"]] += 1
    guess = lambda c: (maj[c["treatment"].lower()].most_common(1)[0][0] if maj[c["treatment"].lower()] else "overturn")  # noqa: E731
    right = [guess(c) == c["truth"] for c in cases.values()]
    print(f"claims: majority of past decisions for the same treatment: {sum(right)}/{len(right)} = {sum(right) / len(right):.4f}")
    print(f"claims: always overturn: {sum(c['truth'] == 'overturn' for c in cases.values())}/{len(cases)}")
    rows = [r for r in jl(HERE / "results" / "runs" / "claims_sessions.jsonl") if r["cond"] == "base"]
    for m in ("dense", "moe"):
        per = defaultdict(list)
        for s in rows:
            if s["model"] == m:
                per[s["case_id"]].append(1.0 if s["decision"] and s["decision"] == cases[s["case_id"]]["truth"] else 0.0)
        bl = {c: float(guess(cases[c]) == cases[c]["truth"]) for c in per}
        ids, rng = sorted(per), random.Random(0)
        diff = lambda ks: st.mean(st.mean(per[k]) - bl[k] for k in ks)  # noqa: E731,B023
        boots = sorted(diff([rng.choice(ids) for _ in ids]) for _ in range(2000))
        print(f"claims: agent ({m}) vs baseline, all sessions: {100 * diff(ids):+.0f} pts "
              f"(CI {100 * boots[50]:+.0f} to {100 * boots[1949]:+.0f})")


def bva():
    lab = labels("bva")
    meta = {c["id"]: c for c in jl(WORK / "bva" / "candidates.all.jsonl" if (WORK / "bva" / "candidates.all.jsonl").exists()
                                   else WORK / "bva" / "candidates.jsonl")}
    cases = {c: {**lab[c], "issue": meta[c]["issue"]} for c in lab}
    prec = jl(WORK / "bva" / "precedents.jsonl")
    grant_rate = st.mean(p["decision"] == "grant" for p in prec)

    def kw_baseline(c):  # bva_bench.analyze
        words = [w for w in re.findall(r"[a-z]{5,}", str(c["issue"]).lower())
                 if w not in ("entitlement", "service", "connection", "rating", "disability", "excess", "percent", "increased")]
        for w in words:
            hits = Counter(p["decision"] for p in prec if w in str(p["issue"]).lower())
            if sum(hits.values()) >= 5:
                return hits.most_common(1)[0][0]
        return "grant" if grant_rate >= 0.5 else "deny"

    right = [kw_baseline(c) == c["truth"] for c in cases.values()]
    print(f"bva: majority of past decisions on the same condition word: {sum(right)}/{len(right)} = {sum(right) / len(right):.4f}")
    print(f"bva: always grant: {sum(c['truth'] == 'grant' for c in cases.values())}/{len(cases)} "
          f"(library: {len(prec)} rows, {len({p['id'] for p in prec})} unique IDs)")


def de_kr():
    import de_kr_bench as dk
    env = dk.Env()
    cases, prec = env.cases, list(env.prec.values())
    base_rate = Counter(p["truth"] for p in prec).most_common(1)[0][0]

    def kw_baseline(c):  # de_kr_bench.analyze
        words = sorted(set(re.findall(r"[a-zäöüß]{9,}", dk.first_para(c["facts"]).lower())), key=len, reverse=True)
        for w in words:
            hits = Counter(p["truth"] for p in prec if w in p["facts"].lower())
            if 5 <= sum(hits.values()) <= 200:
                return hits.most_common(1)[0][0]
        return base_rate

    right = [kw_baseline(c) == c["truth"] for c in cases.values()]
    print(f"de_kr: majority of library cases sharing a distinctive word: {sum(right)}/{len(right)} = {sum(right) / len(right):.4f} "
          f"(depends on PYTHONHASHSEED)")
    print(f"de_kr: always dismiss: {sum(c['truth'] == 'uphold' for c in cases.values())}/{len(cases)}; "
          f"library {len(prec)} cases, {st.mean(p['truth'] == 'uphold' for p in prec):.4f} dismissed")


if __name__ == "__main__":
    for f in (claims, bva, de_kr):
        try:
            f()
        except FileNotFoundError as e:
            print(f"{f.__name__}: skipped, missing {e.filename}")
