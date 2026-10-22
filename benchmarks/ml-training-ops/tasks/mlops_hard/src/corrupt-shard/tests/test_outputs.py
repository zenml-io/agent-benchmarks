import json
import os

import pytest

APP = os.environ.get("APP_DIR", "/app")
BAD = {"shard-0037.npy": [9800, 13454], "shard-0040.npy": [9169], "shard-0042.npy": [18395]}


@pytest.fixture(scope="module")
def ans():
    return json.load(open(os.path.join(APP, "answer.json")))


def test_crash_location(ans):
    assert os.path.basename(ans["crash_shard"]) == "shard-0037.npy"
    assert int(ans["crash_rank"]) == 5
    assert int(ans["crash_step"]) == 173


def test_bad_rows_exact(ans):
    got = {os.path.basename(k): sorted(int(i) for i in v) for k, v in ans["bad_rows"].items() if v}
    missing = {k: sorted(set(v) - set(got.get(k, []))) for k, v in BAD.items() if set(v) - set(got.get(k, []))}
    extra = {k: sorted(set(v) - set(BAD.get(k, []))) for k, v in got.items() if set(v) - set(BAD.get(k, []))}
    assert not missing and not extra, f"missing={missing} extra={extra}"
