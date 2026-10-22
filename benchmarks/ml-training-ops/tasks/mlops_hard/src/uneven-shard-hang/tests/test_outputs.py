import json
import os
import shutil
import subprocess
import sys

import pytest
import torch

APP = os.environ.get("APP_DIR", "/app")


def run(world, n_train, out):
    shutil.rmtree(out, ignore_errors=True)
    env = {**os.environ, "GLOO_TIMEOUT_S": "60"}
    cmd = [sys.executable, "-m", "torch.distributed.run", "--standalone", f"--nproc_per_node={world}",
           os.path.join(APP, "train.py"), "--n-train", str(n_train), "--epochs", "3", "--out", out]
    try:
        r = subprocess.run(cmd, cwd=APP, env=env, capture_output=True, text=True, timeout=420)
    except subprocess.TimeoutExpired:
        pytest.fail(f"world={world} n_train={n_train}: job did not finish within 7 minutes")
    assert r.returncode == 0, f"world={world} n_train={n_train} failed:\n" + r.stdout[-1500:] + r.stderr[-2500:]


# sizes chosen so that a naive split gives one rank fewer batches than the others,
# plus sizes that divide evenly
CASES = [(3, 19970), (4, 19969), (5, 19841), (2, 19970), (3, 18000)]


@pytest.mark.parametrize("world,n_train", CASES)
def test_finishes_and_ranks_agree(world, n_train, tmp_path):
    out = str(tmp_path / "out")
    run(world, n_train, out)
    ranks = [torch.load(os.path.join(out, f"rank{r}.pt")) for r in range(world)]
    for r, sd in enumerate(ranks[1:], 1):
        for k in sd:
            assert torch.allclose(sd[k], ranks[0][k], atol=1e-6), f"rank {r} weights differ from rank 0 ({k})"
    m = json.load(open(os.path.join(out, "metrics.json")))
    assert m["val_accuracy"] >= 0.66, m
