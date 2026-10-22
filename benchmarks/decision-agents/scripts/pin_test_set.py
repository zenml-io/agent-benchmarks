"""
Restrict a domain's candidates to the published test cases before the (paid) extraction step.

`claims_bench.py all` and `bva_bench.py all` turn each candidate into a case file with the dense
model and then sample the test set from the extractions that succeeded and passed the leak check.
Extraction failures differ from run to run, so a fresh run would test a different set of cases.
Running this first keeps only the published test cases (data/<domain>_test_cases.jsonl); extract
then keeps every one that extracts cleanly (it samples at most 75 per label, and the published
set has at most 75 per label). The full candidate file is kept as candidates.all.jsonl.

Not needed for de_kr: its test split is a seeded sample of work/de_kr/cases_raw.jsonl.

    python scripts/pin_test_set.py claims
    python scripts/pin_test_set.py bva
"""

import json
import os
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("DECISION_WORK_DIR") or HERE / "work")


def main(domain):
    keep = {json.loads(x)["id"] for x in open(HERE / "data" / f"{domain}_test_cases.jsonl") if x.strip()}
    src = WORK / domain / "candidates.jsonl"
    full = WORK / domain / "candidates.all.jsonl"
    if not full.exists():
        shutil.copy(src, full)
    rows = [json.loads(x) for x in open(full) if x.strip()]
    kept = [r for r in rows if r["id"] in keep]
    with src.open("w") as f:
        for r in kept:
            f.write(json.dumps(r) + "\n")
    print(f"{domain}: kept {len(kept)} of {len(rows)} candidate rows ({len({r['id'] for r in kept})} of {len(keep)} published IDs)")


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] not in ("claims", "bva"):
        raise SystemExit("usage: pin_test_set.py claims|bva")
    main(sys.argv[1])
