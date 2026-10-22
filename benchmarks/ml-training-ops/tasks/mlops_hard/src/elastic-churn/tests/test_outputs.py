"""Elastic churn: run the job as successive torchrun launches with changing world sizes, SIGKILL each
launch at a random moment (including mid-checkpoint), then let a final launch finish. The final
weights must match the single-process specification (pristine reference.py)."""
import importlib.util
import os
import random
import shutil
import signal
import subprocess
import sys
import time

import pytest
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.environ.get("APP_DIR", "/app")
spec_mod = importlib.util.spec_from_file_location("reference_pristine", os.path.join(HERE, "reference_pristine.py"))
REF = importlib.util.module_from_spec(spec_mod)
spec_mod.loader.exec_module(REF)
WANT = None


def want():
    global WANT
    if WANT is None:
        WANT = REF.train(REF.TOTAL_STEPS)
    return WANT


def launch(world, ckpt):
    return subprocess.Popen([sys.executable, "-m", "torch.distributed.run", "--standalone",
                             f"--nproc_per_node={world}", "train.py", "--ckpt-dir", ckpt], cwd=APP,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True)


def churn(seed, tmp):
    rng = random.Random(seed)
    ckpt = os.path.join(tmp, f"ckpt-{seed}")
    shutil.rmtree(ckpt, ignore_errors=True)
    history = []
    for _ in range(rng.randint(3, 6)):
        w = rng.choice([2, 3, 4, 5])
        p = launch(w, ckpt)
        delay = rng.uniform(4.0, 12.0)
        try:
            p.wait(timeout=delay)
            history.append((w, "finished"))
            if os.path.exists(os.path.join(ckpt, "final.pt")):
                break
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            history.append((w, f"killed at {delay:.1f}s"))
    if not os.path.exists(os.path.join(ckpt, "final.pt")):
        w = rng.choice([2, 3, 4, 5])
        p = launch(w, ckpt)
        try:
            out, _ = p.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            pytest.fail(f"seed {seed}: final launch (world {w}) hung; history {history}")
        assert p.returncode == 0, f"seed {seed}: final launch (world {w}) failed; history {history}\n{out[-2500:]}"
        history.append((w, "finished"))
    got = torch.load(os.path.join(ckpt, "final.pt"), map_location="cpu", weights_only=False)
    ref = want()
    diff = max((got[k].float() - ref[k].float()).abs().max().item() for k in ref)
    assert diff < 1e-4, f"seed {seed}: final weights differ from the spec by {diff:.3g}; launches {history}"


def test_single_launch_matches_spec(tmp_path):
    ckpt = str(tmp_path / "plain")
    p = launch(3, ckpt)
    out, _ = p.communicate(timeout=600)
    assert p.returncode == 0, out[-2500:]
    got = torch.load(os.path.join(ckpt, "final.pt"), map_location="cpu", weights_only=False)
    diff = max((got[k].float() - want()[k].float()).abs().max().item() for k in want())
    assert diff < 1e-4, f"world 3, no failures: differs from the spec by {diff:.3g}"


@pytest.mark.parametrize("seed", [101, 202, 303])
def test_churn(seed, tmp_path):
    churn(seed, str(tmp_path))
