"""Offline tests of the held-out approval appeals drawn for each batch."""

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("round_script", Path(__file__).with_name("round.py"))
assert _spec is not None and _spec.loader is not None
round_script = importlib.util.module_from_spec(_spec)
sys.modules["round_script"] = round_script
_spec.loader.exec_module(round_script)


def settings(mini: bool, approval_on: str = "held-out") -> object:
    return round_script.Settings(frontier_preset="gpt-6.1-sol", open_preset="open", switch_round=4,
                                 improver_model="gpt-6-luna", rerun_budget=3, minutes=45, pro_agent="claims-agent",
                                 mini=mini, pro_arm=True, approval_on=approval_on)


def cases(k: int, n: int) -> list[dict]:
    return [{"id": f"B{k}-{i}", "truth": "uphold" if i % 4 == 0 else "overturn"} for i in range(n)]


def test_held_out_is_stable_and_sized() -> None:
    pool = cases(3, 80)
    first = round_script.held_out(settings(False), 3, pool)
    assert first == round_script.held_out(settings(False), 3, list(pool))
    assert len(first) == 20 and set(first) <= {c["id"] for c in pool}
    assert first != round_script.held_out(settings(False), 4, cases(3, 80))
    # 20 of 80 are upheld in the pool, so 5 of the 20 drawn.
    assert sum(int(i.split("-")[1]) % 4 == 0 for i in first) == 5


def test_mini_held_out_has_both_outcomes() -> None:
    pool = cases(1, 6)
    picked = {c["id"]: c["truth"] for c in pool if c["id"] in round_script.held_out(settings(True), 1, pool)}
    assert len(picked) == 4 and set(picked.values()) == {"uphold", "overturn"}


def test_approval_ids_never_revealed() -> None:
    plan = {1: {"ids": [], "revealed": ["a", "b"], "approval": ["c", "d"]},
            2: {"ids": [], "revealed": ["e"], "approval": ["f"]}}
    assert round_script.approval_ids(settings(False), plan, 2) == ["c", "d", "f"]
    assert round_script.approval_ids(settings(False, "revealed"), plan, 2) == ["a", "b", "e"]
