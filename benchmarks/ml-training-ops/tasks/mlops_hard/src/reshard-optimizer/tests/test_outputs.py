import os
import shutil
import subprocess
import sys

import pytest
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import ref  # noqa: E402

APP = os.environ.get("APP_DIR", "/app")


def run(world, steps, resume, save):
    cmd = [sys.executable, "-m", "torch.distributed.run", "--standalone", f"--nproc_per_node={world}",
           os.path.join(APP, "train.py"), "--steps", str(steps), "--resume", resume, "--save", save]
    r = subprocess.run(cmd, cwd=APP, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, f"world={world} resume={resume} failed:\n" + r.stdout[-1500:] + r.stderr[-2500:]


def compare(save, steps):
    got = torch.load(os.path.join(save, "model.pt"))
    assert got["step"] == steps
    want = ref.train(steps)
    d = max((got["model"][k] - want[k]).abs().max().item() for k in want)
    assert d < 1e-5, f"after resuming, weights at step {steps} differ from uninterrupted training by {d:.3g}"


@pytest.mark.parametrize("chain", [[3, 2], [2, 5], [5, 4]])
def test_resume_at_other_world_sizes(chain, tmp_path):
    src = str(tmp_path / "step-60")
    shutil.copytree(os.path.join(HERE, "pristine", "step-60"), src)  # the checkpoint written by 4 workers
    w1, w2 = chain
    a, b = str(tmp_path / "step-100"), str(tmp_path / "step-130")
    run(w1, 100, src, a)
    compare(a, 100)
    run(w2, 130, a, b)
    compare(b, 130)
