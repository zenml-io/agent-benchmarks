"""Offline test of score.py on synthetic rows: uv run --with pytest pytest scripts/test_score.py"""

import json
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from score import metrics, score

CASES = {cid: {"id": cid, "batch": b, "truth": t} for cid, b, t in [
    ("c1", 1, "uphold"), ("c2", 1, "uphold"), ("c3", 1, "overturn"), ("c4", 1, "overturn"),
    ("c5", 2, "overturn"), ("c6", 2, "overturn"), ("c7", 2, "uphold")]}


def row(cid: str, decision: str | None) -> dict:
    return {"case_id": cid, "final": {"decision": decision} if decision else None, "run_error": None if decision else "limit"}


ROWS = [row("c4", "overturn"),  # superseded by the later c4 row
        row("c1", "uphold"), row("c2", "overturn"), row("c3", "overturn"), row("c4", None),
        row("c5", "overturn"), row("c6", "overturn"), row("c7", "uphold"), row("zz", "uphold")]


def test_per_batch_and_cumulative() -> None:
    res = dict(score(ROWS, CASES))
    assert list(res) == ["batch 1", "batches <= 1", "batch 2", "batches <= 2"]
    b1, b2, cum = res["batch 1"], res["batch 2"], res["batches <= 2"]
    assert (b1["n"], b1["decided"], b1["accuracy"], b1["balanced_accuracy"]) == (4, 3, 0.5, 0.5)
    assert (b1["wrongful_denials"], b1["wrongful_approvals"]) == (0, 1)
    assert (b2["n"], b2["accuracy"], b2["balanced_accuracy"]) == (3, 1.0, 1.0)
    # upheld 2 of 3 right, overturned 3 of 4 right (the undecided c4 counts as wrong)
    assert (cum["n"], cum["decided"], cum["accuracy"]) == (7, 6, 5 / 7)
    assert abs(cum["balanced_accuracy"] - (2 / 3 + 3 / 4) / 2) < 1e-12
    lo, hi = cum["ci95"]
    assert 0 <= lo <= cum["balanced_accuracy"] <= hi <= 1


def test_wrongful_denial_and_single_outcome() -> None:
    m = metrics([("uphold", "overturn"), ("overturn", "overturn")])
    assert (m["wrongful_denials"], m["wrongful_approvals"], m["balanced_accuracy"]) == (1, 0, 0.5)
    assert metrics([("overturn", "overturn")])["ci95"] == (1.0, 1.0)


def test_cli(tmp_path: Path) -> None:
    (tmp_path / "cases.jsonl").write_text("".join(json.dumps(c) + "\n" for c in CASES.values()))
    (tmp_path / "rows.jsonl").write_text("".join(json.dumps(r) + "\n" for r in ROWS))
    out = subprocess.run([sys.executable, str(Path(__file__).with_name("score.py")), str(tmp_path / "rows.jsonl"),
                          "--cases", str(tmp_path / "cases.jsonl")], capture_output=True, text=True, check=True).stdout
    assert "| batches <= 2 | 7 | 6 | 71.4% | 70.8% (" in out
    assert "1 appeal(s) in the rows are not in" in out
