"""Hidden grader: the agent's /app/controller.py against the pristine simulator, on seeds and cluster
shapes it has not seen. Every run must satisfy all invariants (see /app/README.md)."""
import importlib
import os
import sys

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, os.path.join(HERE, "pristine"))  # pristine kube/ and run.py take precedence
sys.path.append(APP)
import run  # noqa: E402

CASES = [(s, {}) for s in range(1000, 1150)] + [(s, {"n_nodes": 12, "n_jobs": 40}) for s in range(2000, 2060)]


@pytest.fixture(scope="module")
def results():
    spec = importlib.util.spec_from_file_location("agent_controller", os.path.join(APP, "controller.py"))
    mod = importlib.util.module_from_spec(spec)
    sys.modules["agent_controller"] = mod
    spec.loader.exec_module(mod)
    out = []
    for seed, kw in CASES:
        try:
            err, _ = run.check(seed, "agent_controller", **kw)
        except Exception as e:  # noqa: BLE001 - a crash in the controller is a failure
            err = f"crashed: {type(e).__name__}: {e}"
        out.append((seed, kw, err))
    return out


def test_all_hidden_scenarios(results):
    bad = [(s, kw, e) for s, kw, e in results if e]
    assert not bad, f"{len(bad)}/{len(results)} scenarios failed, e.g. {bad[:3]}"
