"""
Rebuild work/bva/candidates.jsonl and work/bva/precedents.jsonl for the published candidate set.

`bva_bench.py build` is not deterministic: it fetches decisions on 4 threads and samples the
grant candidates from the fetched list in completion order, so each run picks a slightly
different set of grants (and therefore a slightly different precedent library). This script
does what `build` does, but with the original run's 285 candidate rows fixed
(data/bva_candidate_ids.txt, in their original order). Run it after scripts/fetch_bva_index.py;
the outputs should match data/SHA256SUMS if va.gov still serves the same decision text.

    python scripts/pin_bva_candidates.py
"""

import json
import sys
import time
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE / "harness"))
import bva_bench as bb  # noqa: E402
from claims_bench import jl, parallel  # noqa: E402

UA = {"User-Agent": "agent-benchmarks decision-agents research (github.com/zenml-io/agent-benchmarks)"}


def main():
    idx = jl(bb.D / "index_sample.jsonl")
    first = {}
    for r in idx:
        first.setdefault(r["doc_id"], r)
    ids = [x.strip() for x in open(HERE / "data" / "bva_candidate_ids.txt") if x.strip()]

    def fetch(doc_id):
        r = first[doc_id]
        for attempt in range(4):  # va.gov drops the odd request
            try:
                text = urllib.request.urlopen(urllib.request.Request(r["source_url"], headers=UA), timeout=30).read().decode("utf-8", "replace")
                break
            except Exception:  # noqa: BLE001
                if attempt == 3:
                    raise
                time.sleep(5)
        lab, body = bb.label_and_body(text)
        return {"id": doc_id, "issue": r["issues"], "conditions": r["conditions"], "truth": lab,
                "index_outcome": r["outcomes"], "body": (body or "")[:14000]}

    got = {g["id"]: g for g in parallel(sorted(set(ids)), fetch, n=4) if g.get("id")}
    bad = [i for i in set(ids) if not (got.get(i, {}).get("truth") and got[i].get("body"))]
    with (bb.D / "candidates.jsonl").open("w") as f:
        for i in ids:
            if i in got and i not in bad:
                f.write(json.dumps(got[i]) + "\n")
    test_ids = set(ids)
    with (bb.D / "precedents.jsonl").open("w") as f:  # same rule as bva_bench.build
        for r in idx:
            if r["doc_id"] not in test_ids and r["outcomes"] in ("granted", "denied") and "|" not in str(r["issues"]):
                f.write(json.dumps({"id": r["doc_id"], "decision": "grant" if r["outcomes"] == "granted" else "deny",
                                    "issue": r["issues"], "conditions": r["conditions"], "evidence": r["evidence"],
                                    "reasoning": r["reasoning_atoms"], "citations": (r["citations"] or "")[:400]}) + "\n")
    print(f"candidates: {len(ids) - sum(ids.count(b) for b in bad)} rows ({len(bad)} IDs failed to fetch or label: {bad[:5]})")


if __name__ == "__main__":
    main()
