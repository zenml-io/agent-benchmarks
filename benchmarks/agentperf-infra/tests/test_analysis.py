"""Offline tests for the analysis helpers (moved from the harness's test_experiment.py).

    python tests/test_analysis.py
"""
import contextlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


def test_analysis_paired_and_interaction():
    import analysis as an
    trials = lambda pattern: [{"task": f"t{i}", "ok": ok, "agent_s": 100.0, "steps": 10}
                              for i, ok in enumerate(pattern)]
    ref = an.success(trials([1, 1, 1, 1, 0, 0, 0, 0] * 4))
    worse = an.success(trials([0, 0, 1, 1, 0, 0, 0, 0] * 4))
    mean, lo, hi, n = an.paired_ci(worse, ref)
    assert n == 32 and abs(mean + 0.25) < 1e-9 and hi < 0, (mean, lo, hi)
    same = an.paired_ci(ref, ref)
    assert same[0] == 0 and same[1] == 0 and same[2] == 0
    # A loses 25 pts from the change, B loses nothing: interaction = -25 pts
    mean, lo, hi, n = an.interaction_ci(worse, ref, ref, ref)
    assert abs(mean + 0.25) < 1e-9 and hi < 0
    slow = [dict(t, agent_s=200.0) for t in trials([1] * 8)]
    assert an.speed_factor(slow, trials([1] * 8)) == (2.0, 8)


def test_confirmatory_helpers():
    import confirmatory as cf
    assert cf.holm([0.01, 0.04, 0.03]) == [0.03, 0.06, 0.06]
    assert abs(cf.spearman([1, 2, 3, 4], [10, 20, 30, 40]) - 1) < 1e-9
    assert abs(cf.spearman([1, 2, 3, 4], [4, 3, 2, 1]) + 1) < 1e-9


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            with contextlib.redirect_stdout(io.StringIO()):
                fn()
            print("ok", name)
