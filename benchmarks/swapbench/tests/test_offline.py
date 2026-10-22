"""Offline checks (no model calls, no network): generators, domain, gold actions, statistics, provider config."""
import copy
import gzip
import json
import os
import subprocess
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
PUBLIC = os.path.join(ROOT, "data", "public")
TAU2 = os.path.join(ROOT, "third_party", "tau2-bench")


def _same_set(gen_dir, public_dir):
    for f in ("tasks.json", "split_tasks.json", "policy.md"):
        assert open(os.path.join(gen_dir, f), "rb").read() == open(os.path.join(public_dir, f), "rb").read(), f
    assert open(os.path.join(gen_dir, "db.json"), "rb").read() == gzip.open(os.path.join(public_dir, "db.json.gz")).read()


def test_public_fintech_set_regenerates(tmp_path):
    subprocess.run([sys.executable, "-m", "swapbench.fintech.gen", str(tmp_path), "--n", "500", "--seed", "31415",
                    "--splits", "public:500", "--prefix", "pf"], cwd=ROOT, check=True, capture_output=True)
    _same_set(tmp_path, os.path.join(PUBLIC, "fintech"))


@pytest.mark.skipif(not os.path.isdir(TAU2), reason="run scripts/fetch_tau2.sh first")
def test_public_retail_set_regenerates(tmp_path):
    subprocess.run([sys.executable, "-m", "swapbench.gen_retail", TAU2, str(tmp_path), "--n", "500", "--seed", "31415",
                    "--splits", "public:500", "--prefix", "pg"], cwd=ROOT, check=True, capture_output=True)
    _same_set(tmp_path / "tau2" / "domains" / "retail", os.path.join(PUBLIC, "retail"))


def test_fintech_gold_actions_execute():
    """Every public fintech scenario's gold tool calls run cleanly on a fresh copy of the bank (the oracle)."""
    from swapbench.fintech.domain import FintechDB, FintechTools
    db = json.load(gzip.open(os.path.join(PUBLIC, "fintech", "db.json.gz")))
    tasks = json.load(open(os.path.join(PUBLIC, "fintech", "tasks.json")))
    assert len(tasks) == 500
    for t in tasks:
        tools = FintechTools(FintechDB.model_validate(copy.deepcopy(db)))
        for a in t["evaluation_criteria"]["actions"]:
            getattr(tools, a["name"])(**a["arguments"])


def test_fintech_domain_registers_with_tau2():
    from swapbench.fintech.domain import register
    from tau2.registry import registry
    register()
    assert "fintech" in registry.get_domains()


def test_paired_delta_and_truth_label():
    from swapbench import stats
    inc = [dict(scenario=f"s{i}", trial=0, reward=1.0) for i in range(100)]
    same = stats.paired_delta(inc, inc)
    assert same["delta"] == 0 and same["lo"] == 0 and same["hi"] == 0 and same["n"] == 100
    worse = [dict(scenario=f"s{i}", trial=0, reward=float(i >= 20)) for i in range(100)]
    d = stats.paired_delta(worse, inc)
    assert d["delta"] == pytest.approx(-0.2)
    h = stats.paired_delta(inc, inc, "reward")
    assert stats.truth_label(d, dict(h, delta=0.0, lo=0.0, hi=0.0), 0.05) == "REGRESSED"


def test_pricing_has_no_provider_prices_by_default(monkeypatch):
    from swapbench import pricing
    assert pricing.cost("gpt-5-2025-08-07", 1_000_000, 0, 0) == pytest.approx(1.25)
    assert pricing.cost("openai/some-hosted-open-model", 1_000_000, 0, 0) == 0.0
