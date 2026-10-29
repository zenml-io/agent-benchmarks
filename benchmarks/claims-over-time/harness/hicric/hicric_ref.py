"""
The HICRIC reference classifier as an outside yardstick: inputs, data checks, and scores. All offline.

    uv run --with pyarrow python harness/hicric/hicric_ref.py fetch    # HICRIC benchmark parquet files
    uv run --with pyarrow python harness/hicric/hicric_ref.py checks   # leakage, format drift, overlap
    uv run python harness/hicric/hicric_ref.py inputs                  # classifier input per candidate
    uv run python harness/hicric/hicric_ref.py score                   # predictions.jsonl + scores.json

Training and prediction run on Modal (hicric_modal.py). Everything reads and writes $CLAIMS_WORK_DIR
(default BENCH/work): candidates.jsonl, case_files.jsonl and imr.csv come from the shared data build,
and this script's own files live in work/hicric/.
"""

import argparse
import csv
import json
import os
import re
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
WORK = Path(os.environ.get("CLAIMS_WORK_DIR") or BENCH / "work")
OUT = WORK / "hicric"
HF = OUT / "hf"
DATASET_URL = "https://huggingface.co/datasets/Persius/imr-appeals/resolve/c68b70e0faf74cd2b5731ea02ad7ba7d99a11b8b/"
# LEAK is verbatim from benchmarks/decision-agents/harness/claims_bench.py.
LEAK = re.compile(r"medically necessary|not necessary|is indicated|not indicated|is appropriate|not appropriate|"
                  r"uphold|upheld|overturn|denial should|should be (approved|denied|covered)|"
                  r"is supported|not supported|reviewer (found|determined|concluded)|guideline", re.I)
REVIEWER_MARK = re.compile(r"reviewers? (found|determined|concluded)|Reviewer'?s? Findings|Final Result|Findings:")
LABELS = ("Insufficient", "Upheld", "Overturned")


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in open(path) if x.strip()] if path.exists() else []


def write_jl(path: Path, rows: list[dict]) -> None:
    with path.open("w") as f:
        for r in rows:
            f.write(json.dumps(r) + "\n")


def hicric_split(name: str) -> list[dict]:
    import pyarrow.parquet as pq

    return pq.read_table(HF / f"{name}.parquet").to_pylist()


# ---------------------------------------------------------------- data

def fetch() -> None:
    HF.mkdir(parents=True, exist_ok=True)
    for name in ("train", "test"):
        dest = HF / f"{name}.parquet"
        if not dest.exists():
            urllib.request.urlretrieve(DATASET_URL + f"data/{name}-00000-of-00001.parquet", dest)
        print(name, len(hicric_split(name)))


def sentence(text: str) -> str:
    t = re.sub(r"\s+", " ", text).strip()
    return t if not t or t[-1] in ".!?" else t + "."


def flatten(case_file: dict) -> str:
    """A facts-only case file as plain prose, in the order HICRIC backgrounds use: request, condition, history."""
    parts: list[object] = [case_file.get("request"), case_file.get("condition"),
                           *(case_file.get("history") or []), *(case_file.get("prior_treatments") or [])]
    texts = [p if isinstance(p, str) else json.dumps(p) for p in parts if p]
    return " ".join(sentence(t) for t in texts if t.strip())


def request_sentence(findings: str) -> str:
    # IMR texts often run sentences together ("...services.The reviewer"), so a capital letter after the
    # period ends the sentence even without a space.
    first = re.split(r"(?<=[.!?])\s*(?=[A-Z])", findings.strip(), maxsplit=1)[0]
    return sentence(first[:1].upper() + first[1:])


def inputs() -> None:
    """One classifier input per candidate: the flattened case file, or the request sentence when there is none."""
    cands = jl(WORK / "candidates.jsonl")
    files = {r["id"]: r for r in jl(WORK / "case_files.jsonl")}
    rows = []
    for c in cands:
        f = files.get(c["id"])
        if f and f.get("case_file") and not f.get("leak"):
            rows.append({"id": c["id"], "input": "case_file", "text": flatten(f["case_file"])})
        else:
            rows.append({"id": c["id"], "input": "request_sentence", "text": request_sentence(c["findings"])})
    for r in rows:
        r["leak"] = bool(LEAK.search(r["text"]))
    OUT.mkdir(parents=True, exist_ok=True)
    write_jl(OUT / "inputs.jsonl", rows)
    kinds = Counter(r["input"] for r in rows)
    leaks = Counter(r["input"] for r in rows if r["leak"])
    print(f"candidates: {len(cands)}, case files read: {len(files)}; inputs: {dict(kinds)}; LEAK matches: {dict(leaks)}")
    for r in [r for r in rows if r["leak"]][:5]:
        print("  LEAK", r["id"], LEAK.search(r["text"]).group(0), "|", r["text"][:160])


def control_inputs() -> None:
    """HICRIC's own test split cut to its first background span, the part that rarely carries reviewer text."""
    rows = [{"id": f"test-{i}", "input": "hicric_first_span", "text": r["text"].split("\n")[0].strip()}
            for i, r in enumerate(hicric_split("test"))]
    write_jl(OUT / "control_inputs.jsonl", rows)
    print(f"control inputs: {len(rows)}")


# ---------------------------------------------------------------- checks

def checks() -> None:
    """Leakage inside HICRIC's own inputs, the drift of the IMR text format, and train/case overlap."""
    report: dict = {}
    hicric = [r | {"split": s} for s in ("train", "test") for r in hicric_split(s)]

    # 1. Does HICRIC's `text` (its classifier input) contain spans written after the reviewer started concluding?
    marked = later = 0
    by_split: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in hicric:
        m = REVIEWER_MARK.search(r["full_text"])
        if not m:
            continue
        spans = [s.strip() for s in r["text"].split("\n") if len(s.strip()) > 20]
        hit = any(r["full_text"].find(s[:60]) > m.start() for s in spans)
        marked += 1
        later += hit
        by_split[r["split"]][0] += 1
        by_split[r["split"]][1] += hit
    report["hicric_text_leak"] = {
        "rows": len(hicric), "rows_with_reviewer_marker": marked,
        "share_with_span_after_marker": round(later / marked, 3),
        "by_split": {k: round(v[1] / v[0], 3) for k, v in by_split.items()},
        "share_matching_LEAK_regex": round(sum(bool(LEAK.search(r["text"])) for r in hicric) / len(hicric), 3)}

    # 2. How often does an IMR Findings text start with a case summary before the reviewer's own words?
    with open(WORK / "imr.csv", encoding="utf-8", errors="replace") as f:
        rows = list(csv.DictReader(f))
    fmt: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for r in rows:
        f = r["Findings"]
        i_sum, i_rev = f.find("Nature of Statutory"), f.find("reviewer found")
        fmt[r["ReportYear"]][0] += 1
        fmt[r["ReportYear"]][1] += i_sum >= 0 and (i_rev < 0 or i_sum < i_rev)
    report["summary_before_reviewer_by_year"] = {y: round(v[1] / v[0], 3) for y, v in sorted(fmt.items()) if y >= "2014"}

    # 3. Is any 2025-2026 candidate already in HICRIC's data? Word 8-gram containment against every full_text,
    # on the case-specific part of each Findings text and ignoring 8-grams found in 5 or more HICRIC texts,
    # because the reviewers' stock sentences (drug approvals, credentials, the final result) repeat across cases.
    def grams(t: str) -> set[int]:
        w = re.findall(r"[a-z0-9]+", t.lower())
        return {hash(tuple(w[i:i + 8])) for i in range(len(w) - 7)}

    raw = {r["ReferenceID"]: re.split(r"Final Result:|Credentials/Qualifications:", r["Findings"])[0] for r in rows}
    cand_grams = {c["id"]: grams(raw[c["id"]]) for c in jl(WORK / "candidates.jsonl")}
    wanted = set().union(*cand_grams.values())
    doc_grams = [grams(r["full_text"]) & wanted for r in hicric]
    df = Counter(g for gs in doc_grams for g in gs)
    specific = {cid: {g for g in gs if df[g] < 5} for cid, gs in cand_grams.items()}
    index: dict[int, list[str]] = defaultdict(list)
    for cid, gs in specific.items():
        for g in gs:
            index[g].append(cid)
    best: dict[str, float] = defaultdict(float)
    for gs in doc_grams:
        counts = Counter(cid for g in gs for cid in index.get(g, ()))
        for cid, n in counts.items():
            best[cid] = max(best[cid], n / len(specific[cid]))
    report["candidate_overlap"] = {
        "candidates": len(cand_grams), "candidates_with_any_shared_8gram": len(best),
        "max_share_of_case_specific_8grams_in_one_hicric_text": round(max(best.values(), default=0), 3),
        "candidates_over_50pct": sorted(c for c, v in best.items() if v > 0.5)}
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "checks.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report, indent=1))


# ---------------------------------------------------------------- scores

def binary(probs: dict) -> tuple[str, float]:
    """Our label from HICRIC's three classes: drop 'Insufficient' and compare Upheld with Overturned."""
    p_over = probs["Overturned"] / (probs["Overturned"] + probs["Upheld"])
    return ("overturn" if p_over >= 0.5 else "uphold"), p_over


def metrics(pairs: list[tuple[str, str]], labels: tuple[str, ...]) -> dict:
    """Accuracy, balanced accuracy (mean recall per true label) and macro F1 over (truth, prediction) pairs."""
    n = len(pairs)
    recall, f1 = {}, {}
    for lab in labels:
        tp = sum(t == p == lab for t, p in pairs)
        true_n, pred_n = sum(t == lab for t, _ in pairs), sum(p == lab for _, p in pairs)
        recall[lab] = tp / true_n if true_n else None
        f1[lab] = 2 * tp / (true_n + pred_n) if true_n + pred_n else 0.0
    present = [r for r in recall.values() if r is not None]
    return {"n": n, "accuracy": round(sum(t == p for t, p in pairs) / n, 4) if n else None,
            "balanced_accuracy": round(sum(present) / len(present), 4) if present else None,
            "macro_f1": round(sum(f1.values()) / len(labels), 4), "recall": {k: v and round(v, 4) for k, v in recall.items()},
            "truth_counts": dict(Counter(t for t, _ in pairs)), "pred_counts": dict(Counter(p for _, p in pairs))}


def score_reproduction() -> dict:
    """Rescore HICRIC's test split from the saved probabilities, three-class and forced uphold/overturn."""
    rows = jl(OUT / "test_probabilities.jsonl")
    if not rows:
        return {}
    truth3 = ["Insufficient" if r["sufficiency_id"] == 0 else r["decision"] for r in rows]
    argmax = [max(LABELS, key=r["probabilities"].get) for r in rows]
    threshold = [("Insufficient" if r["probabilities"]["Insufficient"] >= 0.7 else
                  max(LABELS[1:], key=r["probabilities"].get)) for r in rows]
    forced = [binary(r["probabilities"])[0] for r in rows]
    truth2 = ["overturn" if r["decision"] == "Overturned" else "uphold" for r in rows]
    return {"three_class_argmax": metrics(list(zip(truth3, argmax)), LABELS),
            "three_class_threshold_0.7": metrics(list(zip(truth3, threshold)), LABELS),
            "forced_uphold_overturn": metrics(list(zip(truth2, forced)), ("uphold", "overturn"))}


def score() -> None:
    cands = {c["id"]: c for c in jl(WORK / "candidates.jsonl")}
    probs = jl(OUT / "probabilities.jsonl")
    preds = []
    for r in probs:
        label, p_over = binary(r["probabilities"])
        preds.append({"id": r["id"], "prediction": label, "probabilities": r["probabilities"],
                      "p_overturn": round(p_over, 4), "input": r["input"]})
    write_jl(OUT / "predictions.jsonl", preds)

    def block(rows: list[dict]) -> dict:
        pairs = [(cands[r["id"]]["truth"], r["prediction"]) for r in rows]
        m = metrics(pairs, ("uphold", "overturn"))
        m["insufficient_was_top_class"] = sum(max(LABELS, key=r["probabilities"].get) == "Insufficient" for r in rows)
        m["always_overturn_accuracy"] = round(sum(t == "overturn" for t, _ in pairs) / len(pairs), 4) if pairs else None
        return m

    usable = [p for p in preds if p["input"] == "case_file"]
    out = {"all_eligible": block(preds), "with_case_file": block(usable),
           "request_sentence_only": block([p for p in preds if p["input"] == "request_sentence"]),
           "by_year": {y: block([p for p in usable if cands[p["id"]]["year"] == y])
                       for y in sorted({c["year"] for c in cands.values()})}}
    stream = {r["id"]: r for r in jl(BENCH / "data" / "stream.jsonl")}
    if stream:
        by = {p["id"]: p for p in preds}
        out["by_batch"] = {k: block([by[i] for i, s in stream.items() if s["batch"] == k and i in by])
                           for k in sorted({s["batch"] for s in stream.values()})}
    control = jl(OUT / "control_probabilities.jsonl")
    if control:
        test = hicric_split("test")
        pairs = [("overturn" if test[int(r["id"].split("-")[1])]["decision"] == "Overturned" else "uphold",
                  binary(r["probabilities"])[0]) for r in control]
        out["hicric_test_first_span_only"] = metrics(pairs, ("uphold", "overturn"))
    out["hicric_test_reproduction"] = score_reproduction()
    (OUT / "scores.json").write_text(json.dumps(out, indent=1))
    print(json.dumps({k: v for k, v in out.items() if k not in ("by_year", "by_batch")}, indent=1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", choices=["fetch", "checks", "inputs", "control", "score"])
    cmd = ap.parse_args().cmd
    {"fetch": fetch, "checks": checks, "inputs": inputs, "control": control_inputs, "score": score}[cmd]()


if __name__ == "__main__":
    main()
