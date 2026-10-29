"""
Fetch the California IMR CSV and write the precedent library and the 2025-2026 candidate list.

    uv run python scripts/build_stream.py

Writes, under $CLAIMS_WORK_DIR (default ./work, not committed):

- imr.csv: the DMHC Independent Medical Review determinations (downloaded with curl if missing).
- precedents.jsonl: the 2016-2023 decisions the agent can search. Byte for byte the file that
  decision-agents' `claims_bench.py build` writes from the same CSV.
- candidates.jsonl: every 2025-2026 case that passes decision-agents' test-set filter and is not one
  of its 150 published test cases, in filing order, with a 0-based `order` field.

Free and offline once the CSV is present.
"""

import csv
import json
import os
import re
import subprocess
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("CLAIMS_WORK_DIR") or BENCH / "work")
CSV_URL = ("https://data.chhs.ca.gov/dataset/b79b3447-4c10-4ae6-84e2-1076f83bb24e/resource/"
           "3340c5d7-4054-4d03-90e0-5f44290ed095/download/independent-medical-review-imr-determinations-trends.csv")
PUBLISHED_TEST = BENCH.parent / "decision-agents" / "data" / "claims_test_cases.jsonl"
YEARS = ("2025", "2026")


def clean(text: str) -> str:
    """Strip the boilerplate around a Findings field (copied from decision-agents' claims_bench.py)."""
    t = re.sub(r"\s+", " ", text or "").strip()
    t = re.sub(r"^Findings:\s*", "", t)
    t = re.sub(r"^The physician reviewer found that\s*", "", t)
    t = re.sub(r"^Nature of Statutory Criteria/Case Summary:\s*", "", t)
    return re.split(r"Credentials/Qualifications:", t)[0].strip()


def decision(r: dict) -> str:
    return "overturn" if r["Determination"].startswith("Overturned") else "uphold"


def fetch_csv(dest: Path) -> None:
    # The portal redirects to a signed S3 URL that Python's urllib fails on in some networks; curl works.
    dest.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["curl", "-sSfL", "-o", str(dest), CSV_URL], check=True)


def precedent_rows(rows: list[dict]) -> list[dict]:
    """The precedent library exactly as decision-agents builds it (same filter, fields, order and cut)."""
    return [{"id": r["ReferenceID"], "year": r["ReportYear"], "decision": decision(r), "type": r["Type"],
             "diagnosis": r["DiagnosisSubCategory"], "treatment_category": r["TreatmentCategory"],
             "treatment": r["TreatmentSubCategory"], "text": clean(r["Findings"])[:1500]}
            for r in rows if "2016" <= r["ReportYear"] <= "2023" and len(r["Findings"]) > 300]


def filing_key(r: dict) -> tuple[str, int]:
    return r["ReportYear"], int(r["ReferenceID"].split("-")[-1])


def candidate_rows(rows: list[dict], excluded: set[str]) -> list[dict]:
    """Eligible 2025-2026 cases in filing order, one row per ReferenceID."""
    eligible = [r for r in rows if r["ReportYear"] in YEARS and 600 < len(r["Findings"]) < 4000
                and r["TreatmentSubCategory"] and r["Type"] != "Urgent Care" and r["ReferenceID"] not in excluded]
    # The CSV repeats a few rows verbatim under the same ReferenceID; a case must appear once.
    unique = {r["ReferenceID"]: r for r in eligible}.values()
    return [{"id": r["ReferenceID"], "year": r["ReportYear"], "truth": decision(r), "type": r["Type"],
             "diagnosis_category": r["DiagnosisCategory"], "diagnosis": r["DiagnosisSubCategory"],
             "treatment_category": r["TreatmentCategory"], "treatment": r["TreatmentSubCategory"],
             "age": r["AgeRange"], "gender": r["PatientGender"], "findings": clean(r["Findings"]), "order": i}
            for i, r in enumerate(sorted(unique, key=filing_key))]


def write_jsonl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def main() -> None:
    src = WORK / "imr.csv"
    if not src.exists():
        fetch_csv(src)
    with open(src, encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
    with open(PUBLISHED_TEST) as f:
        excluded = {json.loads(x)["id"] for x in f if x.strip()}
    precedents, candidates = precedent_rows(rows), candidate_rows(rows, excluded)
    write_jsonl(WORK / "precedents.jsonl", precedents)
    write_jsonl(WORK / "candidates.jsonl", candidates)
    overturn = sum(c["truth"] == "overturn" for c in candidates)
    print(f"csv rows: {len(rows)}, precedents: {len(precedents)}, candidates: {len(candidates)} "
          f"({overturn} overturn, {len(candidates) - overturn} uphold; "
          f"{candidates[0]['id']} .. {candidates[-1]['id']})")


if __name__ == "__main__":
    main()
