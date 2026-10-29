"""
Split the usable cases into the calibration batch and batches 1-8, and pick the revealed cases.

    uv run python scripts/assign_batches.py

Usable cases are candidates whose case file extracted and passed the leak check. In filing order,
they are cut into 9 consecutive windows of (nearly) equal size: window 0 feeds the calibration batch,
windows 1-8 feed batches 1-8. Each batch is 100 cases drawn from its window with
random.Random(f"batch-{k}"); in batches 1-8, 20 of them are revealed, drawn with
random.Random(f"reveal-{k}"). The outcome mix is left as it comes. String seeds make the draw the
same on every machine and Python run.

Writes $CLAIMS_WORK_DIR/cases.jsonl (with the true outcome; stays out of the repo) and
data/stream.jsonl (id, batch, order, revealed only; committed). Free and offline.
"""

import json
import os
import random
import re
from pathlib import Path

BENCH = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("CLAIMS_WORK_DIR") or BENCH / "work")
WINDOWS, BATCH_SIZE, REVEALED = 9, 100, 20
GLP1 = re.compile(r"semaglutide|tirzepatide|wegovy|ozempic|mounjaro|zepbound", re.I)


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in open(path) if x.strip()]


def assign(usable: list[dict]) -> list[dict]:
    """Return the drawn cases in filing order, each with `batch` and `revealed` added."""
    n, out = len(usable), []
    for k in range(WINDOWS):
        window = usable[k * n // WINDOWS:(k + 1) * n // WINDOWS]
        batch = sorted(random.Random(f"batch-{k}").sample(window, BATCH_SIZE), key=lambda c: c["order"])
        shown = {c["id"] for c in random.Random(f"reveal-{k}").sample(batch, REVEALED)} if k else set()
        out += [c | {"batch": k, "revealed": c["id"] in shown} for c in batch]
    return out


def describe(k: int, cases: list[dict], window: tuple[int, int]) -> str:
    n = len(cases)
    years = sorted({c["year"] for c in cases})
    over = sum(c["truth"] == "overturn" for c in cases) / n
    glp1 = sum(bool(GLP1.search(c["findings"])) for c in cases) / n
    return (f"| {k} | {n} | {sum(c['revealed'] for c in cases)} | {years[0]}-{years[-1]} | "
            f"{cases[0]['id']} .. {cases[-1]['id']} | {window[1] - window[0]} | {over:.0%} | {glp1:.0%} |")


def main() -> None:
    cands = sorted(jl(WORK / "candidates.jsonl"), key=lambda c: c["order"])
    files = {r["id"]: r for r in jl(WORK / "case_files.jsonl")}
    missing = sum(c["id"] not in files for c in cands)
    usable = [c for c in cands if c["id"] in files and files[c["id"]]["case_file"] and not files[c["id"]]["leak"]]
    print(f"candidates: {len(cands)}, not extracted: {missing}, usable: {len(usable)}")
    cases = assign(usable)
    with (WORK / "cases.jsonl").open("w") as f:
        for c in cases:
            f.write(json.dumps({k: v for k, v in c.items() if k != "findings"} | {"case_file": files[c["id"]]["case_file"]}) + "\n")
    with (BENCH / "data" / "stream.jsonl").open("w") as f:
        for c in cases:
            f.write(json.dumps({"id": c["id"], "batch": c["batch"], "order": c["order"], "revealed": c["revealed"]}) + "\n")
    n = len(usable)
    print("| batch | cases | revealed | years | IDs | window size | overturn | GLP-1 |")
    print("|---|---|---|---|---|---|---|---|")
    for k in range(WINDOWS):
        print(describe(k, [c for c in cases if c["batch"] == k], (k * n // WINDOWS, (k + 1) * n // WINDOWS)))


if __name__ == "__main__":
    main()
