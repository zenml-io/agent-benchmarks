import json
import os
import re
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TITAN = "/app/titan"
GOLDEN = json.load(open(os.path.join(HERE, "golden.json")))["losses"]


def src(rel):
    return open(os.path.join(TITAN, rel)).read()


def test_intentional_changes_kept():
    assert re.search(r"max_norm: float \| int = 0\.5", src("torchtitan/config/job_config.py"))
    assert "cosine_floor" in src("torchtitan/components/lr_scheduler.py")
    assert "shuffle(seed=1234)" in src("torchtitan/hf_datasets/text_datasets.py")
    assert "contiguous=True" in src("torchtitan/hf_datasets/text_datasets.py")
    m = src("torchtitan/models/llama3/model/model.py")
    assert "0.5 * self.model_args.dim**-0.5" in m and "TITAN_ROPE_THETA" in m and "self.attn_scale" in m
    assert "CE_CHUNK" in src("torchtitan/components/loss.py")
    assert "TITAN_RUN_TAG" in src("torchtitan/train.py")


@pytest.fixture(scope="module")
def curve():
    out = "/tmp/grader_losses.json"
    r = subprocess.run(["bash", os.path.join(HERE, "run_debug.sh"), out], capture_output=True, text=True, timeout=1500)
    assert os.path.exists(out), r.stdout[-2000:] + r.stderr[-2000:]
    c = json.load(open(out))
    assert None not in c, "the reference run did not complete 200 steps:\n" + r.stdout[-2000:]
    return c


def test_matches_golden(curve):
    d = [abs(a - b) for a, b in zip(curve, GOLDEN)]
    late = sum(d[150:]) / 50
    assert late < 0.001 and max(d) < 0.005, f"mean |d| steps 151-200 = {late:.4f}, max |d| = {max(d):.4f}"
