import os
import shutil
import subprocess
import sys

import pytest
import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref  # noqa: E402

APP = os.environ.get("APP_DIR", "/app")
STEPS = 300
REF = None


def reference():
    global REF
    if REF is None:
        REF = ref.train(STEPS)
    return REF


def run(world, tmp):
    out = os.path.join(tmp, f"out{world}")
    shutil.rmtree(out, ignore_errors=True)
    cmd = [sys.executable, "-m", "torch.distributed.run", "--standalone", f"--nproc_per_node={world}",
           os.path.join(APP, "train.py"), "--steps", str(STEPS), "--out", out]
    r = subprocess.run(cmd, cwd=APP, capture_output=True, text=True, timeout=900)
    assert r.returncode == 0, r.stdout[-2000:] + r.stderr[-3000:]
    return [torch.load(os.path.join(out, f"rank{i}.pt")) for i in range(world)], torch.load(os.path.join(out, "model.pt"))


def maxdiff(a, b):
    return max((a[k].float() - b[k].float()).abs().max().item() for k in b)


@pytest.mark.parametrize("world", [2, 3, 4])
def test_data_parallel_matches_single_process(world, tmp_path):
    ranks, saved = run(world, str(tmp_path))
    for i, sd in enumerate(ranks[1:], 1):
        assert maxdiff(sd, ranks[0]) < 1e-5, f"rank {i} differs from rank 0"
    assert maxdiff(saved, ranks[0]) < 1e-5
    d = maxdiff(saved, reference())
    assert d < 2e-5, f"world={world}: weights differ from single-process training on the global batch by {d:.3g}"
