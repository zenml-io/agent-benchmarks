import json
import os

import pytest

APP = os.environ.get("APP_DIR", "/app")
KEY = {("gpu-b09", 6, 45): (1812, "clock_or_power_throttling"),
       ("gpu-a03", 2, 18): (2407, "pcie_link_degraded")}


@pytest.fixture(scope="module")
def ans():
    return json.load(open(os.path.join(APP, "answer.json")))


def test_exactly_the_bad_gpus(ans):
    got = {(i["host"], int(i["physical_gpu"]), int(i["global_rank"])) for i in ans["incidents"]}
    assert got == set(KEY), f"got {sorted(got)}"


def test_start_steps_and_causes(ans):
    for i in ans["incidents"]:
        step, cause = KEY[(i["host"], int(i["physical_gpu"]), int(i["global_rank"]))]
        assert abs(int(i["start_step"]) - step) <= 30, i
        assert i["cause"] == cause, i


def test_cordon(ans):
    assert sorted(ans["cordon"]) == ["gpu-a03", "gpu-b09"]
