"""
Rebuild work/bva/index_sample.jsonl, the 4,000-row slice of the BVA research index that
bva_bench.py samples test cases from and uses as the precedent library.

The original run saved this slice without the script that made it; data/bva_index_ids.txt keeps
its doc_ids in their original order (including the index's duplicate rows), and this script
fills each one from the Hugging Face dataset at the pinned revision. The result is byte-identical
to the original file (checked against data/SHA256SUMS).

    python scripts/fetch_bva_index.py

Source: https://huggingface.co/datasets/williamTLmiller/BVA-AMA-Era-170KStructured
License: CC-BY-NC-4.0 (non-commercial; attribute the dataset). Not redistributed here.
"""

import csv
import json
import os
import sys
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("DECISION_WORK_DIR") or HERE / "work")
OUT = WORK / "bva" / "index_sample.jsonl"
HF = WORK / "bva" / "hf"
REPO = "williamTLmiller/BVA-AMA-Era-170KStructured"
REVISION = "e09f672731f54b9501615dc65887ed5ecd2bb178"
FILES = ["BVA-AMA-Era-2019-2020.csv", "BVA-AMA-Era-t2021.csv", "BVA-AMA-Era-2022-2023.csv"]
FIELDS = ["doc_id", "source_url", "issues", "conditions", "outcomes", "citations", "evidence",
          "reasoning_atoms", "char_length", "regime"]


def main():
    HF.mkdir(parents=True, exist_ok=True)
    csv.field_size_limit(sys.maxsize)
    rows = {}
    for name in FILES:
        path = HF / name
        if not path.exists():
            url = f"https://huggingface.co/datasets/{REPO}/resolve/{REVISION}/{name}"
            print(f"downloading {url}", flush=True)
            urllib.request.urlretrieve(url, path)
        for r in csv.DictReader(open(path, encoding="utf-8", errors="replace")):
            rows.setdefault(r["doc_id"], r)  # the dataset repeats some rows byte for byte
    ids = [x.strip() for x in open(HERE / "data" / "bva_index_ids.txt") if x.strip()]
    missing = [i for i in ids if i not in rows]
    if missing:
        raise SystemExit(f"{len(missing)} doc_ids not in the dataset, e.g. {missing[:5]}")
    with OUT.open("w") as f:
        for i in ids:
            r = rows[i]
            o = {k: (r[k] if r[k] != "" else None) for k in FIELDS}
            o["char_length"] = int(r["char_length"]) if r["char_length"] else None
            f.write(json.dumps(o) + "\n")
    print(f"wrote {OUT} ({len(ids)} rows, {len(set(ids))} unique doc_ids)")


if __name__ == "__main__":
    main()
