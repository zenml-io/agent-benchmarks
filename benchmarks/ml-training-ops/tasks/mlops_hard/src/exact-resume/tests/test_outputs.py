"""Preempt the job at random moments (SIGKILL) many times, then let it finish: the final weights
must equal an uninterrupted run (bit for bit, up to float noise)."""
import glob
import os
import random
import signal
import subprocess
import sys
import time

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref  # noqa: E402

APP = os.environ.get("APP_DIR", "/app")


def start(d):
    return subprocess.Popen([sys.executable, os.path.join(APP, "train.py"), "--ckpt-dir", d], cwd=APP,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def ckpts(d):
    return set(glob.glob(os.path.join(d, "ckpt-*.pt")))


def run_with_preemptions(d, seed, kills=8):
    """Kill shortly after each new checkpoint appears (so every life makes progress and dies
    mid-interval), at a random delay."""
    rng = random.Random(seed)
    n = 0
    for _ in range(kills):
        before = ckpts(d)
        p = start(d)
        deadline = time.time() + 300
        while p.poll() is None and time.time() < deadline and not (ckpts(d) - before):
            time.sleep(0.01)
        if p.poll() is not None:
            out = p.stdout.read()
            assert p.returncode == 0, f"job failed on restart:\n{out[-3000:]}"
            break
        time.sleep(rng.uniform(0.0, 0.5))
        p.send_signal(signal.SIGKILL)
        p.wait()
        n += 1
    p = start(d)
    out, _ = p.communicate(timeout=900)
    assert p.returncode == 0, f"final restart failed:\n{out[-3000:]}"
    return n


def check(d):
    final = torch.load(os.path.join(d, "final.pt"), map_location="cpu")
    want = ref.train()
    diff = max((final[k] - want[k]).abs().max().item() for k in want)
    assert diff < 1e-6, f"final weights differ from an uninterrupted run by {diff:.3g}"


def test_uninterrupted(tmp_path):
    d = str(tmp_path / "a")
    p = start(d)
    out, _ = p.communicate(timeout=900)
    assert p.returncode == 0, out[-3000:]
    check(d)


def test_preempted_runs_match_uninterrupted(tmp_path):
    for seed in (1, 2):
        d = str(tmp_path / f"p{seed}")
        n = run_with_preemptions(d, seed)
        assert n >= 3, "job finished too fast to be preempted; test is not meaningful"
        check(d)
