import json
import os

import pytest

APP = os.environ.get("APP_DIR", "/app")
KEY = {"host": "gpu-b09", "physical_gpu": 6, "global_rank": 45, "start_step": 1812,
       "cause": "clock_or_power_throttling", "cordon": ["gpu-b09"]}


@pytest.fixture(scope="module")
def ans():
    return json.load(open(os.path.join(APP, "answer.json")))


def test_host(ans):
    assert ans["host"] == KEY["host"]


def test_gpu_and_rank(ans):
    assert int(ans["physical_gpu"]) == KEY["physical_gpu"]
    assert int(ans["global_rank"]) == KEY["global_rank"]


def test_start_step(ans):
    assert abs(int(ans["start_step"]) - KEY["start_step"]) <= 30


def test_cause(ans):
    assert ans["cause"] == KEY["cause"]


def test_cordon_only_bad_host(ans):
    assert sorted(ans["cordon"]) == KEY["cordon"]
