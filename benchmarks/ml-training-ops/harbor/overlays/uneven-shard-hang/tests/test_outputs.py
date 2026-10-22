import json
import os
import shutil
import subprocess
import sys

import collections
import glob
import hashlib

import pytest
import torch

APP = os.environ.get("APP_DIR", "/app")
ROWLOG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "rowlog")
EPOCHS = 3


def train_rows(n):
    """The task's training set (trainer/data.py make_split(n, seed=1)), computed by the grader."""
    g = torch.Generator().manual_seed(1)
    return torch.randn(n, 48, generator=g)


def check_every_example_used(n_train, rowdir, world):
    """Added for the Harbor-native version: the instruction forbids skipping any training example for a
    whole epoch, which the original test did not check (dropping the remainder also stops the hang).
    Every example must reach the model at least once per epoch, so at least EPOCHS times in total."""
    used = collections.Counter()
    files = glob.glob(os.path.join(rowdir, "rows-*.json"))
    for f in files:
        used.update(json.load(open(f)))
    assert len(files) >= world, f"expected row logs from {world} training processes, found {len(files)}"
    rows = train_rows(n_train).numpy()
    short = sum(1 for r in rows if used[hashlib.blake2b(r.tobytes(), digest_size=8).hexdigest()] < EPOCHS)
    assert short == 0, f"world={world} n_train={n_train}: {short} training examples were skipped in at least one epoch"


def run(world, n_train, out, rowdir=None):
    shutil.rmtree(out, ignore_errors=True)
    env = {**os.environ, "GLOO_TIMEOUT_S": "60"}
    if rowdir:
        os.makedirs(rowdir, exist_ok=True)
        env.update(PYTHONPATH=ROWLOG, ROWLOG_DIR=rowdir, ROWLOG_DIM="48")
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
    out, rowdir = str(tmp_path / "out"), str(tmp_path / "rows")
    run(world, n_train, out, rowdir)
    ranks = [torch.load(os.path.join(out, f"rank{r}.pt")) for r in range(world)]
    for r, sd in enumerate(ranks[1:], 1):
        for k in sd:
            assert torch.allclose(sd[k], ranks[0][k], atol=1e-6), f"rank {r} weights differ from rank 0 ({k})"
    m = json.load(open(os.path.join(out, "metrics.json")))
    assert m["val_accuracy"] >= 0.66, m
    check_every_example_used(n_train, rowdir, world)
