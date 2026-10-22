"""Preempt the job repeatedly (SIGKILL), including in the middle of checkpoint writes, and check that
(1) every ckpt-*.pt visible in the directory is complete at all times, (2) a preemption never loses
saved progress, (3) the job always restarts, and (4) the final model equals uninterrupted training."""
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
STEPS = 200
KILLS = 12


def snapshot(d):
    out = {}
    for f in os.listdir(d) if os.path.isdir(d) else []:
        try:
            out[f] = os.path.getsize(os.path.join(d, f))
        except FileNotFoundError:
            pass
    return out


def checkpoints(d):
    """Load every visible ckpt-*.pt; return their steps. Fails on any partial or corrupt file."""
    steps = []
    for f in sorted(glob.glob(os.path.join(d, "ckpt-*.pt"))):
        try:
            st = torch.load(f, weights_only=False, map_location="cpu")
        except Exception as e:  # noqa: BLE001
            raise AssertionError(f"{os.path.basename(f)} is not a loadable checkpoint after a preemption: {e!r}")
        assert {"model", "opt", "step"} <= set(st), f"{f} lacks model/opt/step"
        steps.append(int(st["step"]))
    return steps


def start(d):
    return subprocess.Popen([sys.executable, os.path.join(APP, "train.py"), "--ckpt-dir", d, "--steps", str(STEPS)],
                            cwd=APP, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)


def test_survives_preemption(tmp_path):
    rng = random.Random(1234)
    d = str(tmp_path / "ckpt")
    best = -1
    kills = 0
    for i in range(KILLS):
        p = start(d)
        on_write = i % 2 == 0
        deadline = time.time() + (60 if on_write else rng.uniform(2.0, 7.0))
        before = snapshot(d)
        killed = False
        while time.time() < deadline:
            if p.poll() is not None:
                break
            if on_write:
                now = snapshot(d)
                if any(f not in before or now[f] != before.get(f) for f in now):
                    p.send_signal(signal.SIGKILL)
                    killed = True
                    break
                before = now
                time.sleep(0.002)
            else:
                time.sleep(0.02)
        else:
            p.send_signal(signal.SIGKILL)
            killed = True
        p.wait()
        out = p.stdout.read()
        if not killed:
            assert p.returncode == 0, f"job crashed on restart #{i} (exit {p.returncode}):\n{out[-3000:]}"
            break
        kills += 1
        steps = checkpoints(d)
        if best >= 0:
            assert steps and max(steps) >= best, f"preemption #{i} lost saved progress: had step {best}, now {steps}"
        if steps:
            best = max(steps)
    assert kills >= 6, "job finished too fast to be preempted; test is not meaningful"
    p = start(d)
    out, _ = p.communicate(timeout=600)
    assert p.returncode == 0, f"final restart failed:\n{out[-3000:]}"
    final = torch.load(os.path.join(d, "final.pt"), map_location="cpu")
    want = ref.train(STEPS)
    diff = max((final[k] - want[k]).abs().max().item() for k in want)
    assert diff < 1e-5, f"final weights differ from uninterrupted training by {diff:.3g}"
