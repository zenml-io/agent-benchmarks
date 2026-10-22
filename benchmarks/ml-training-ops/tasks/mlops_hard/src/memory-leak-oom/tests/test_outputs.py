import json
import os
import resource
import subprocess
import sys

import torch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ref  # noqa: E402

APP = os.environ.get("APP_DIR", "/app")


def run(steps, out):
    code = ("import resource, subprocess, sys\n"
            f"r = subprocess.run([sys.executable, {os.path.join(APP, 'train.py')!r}, '--steps', '{steps}', '--out', {out!r}],"
            f" cwd={APP!r}, capture_output=True, text=True, timeout=900)\n"
            "print(r.returncode, resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss)\n"
            "sys.stderr.write(r.stderr[-3000:])\n")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True, timeout=1000)
    rc, peak_kb = r.stdout.split()
    assert rc == "0", f"training failed:\n{r.stderr}"
    return int(peak_kb) / 1024


def test_same_training_semantics(tmp_path):
    out = str(tmp_path / "o600")
    run(600, out)
    want, losses = ref.train(600)
    got = torch.load(os.path.join(out, "model.pt"))
    d = max((got[k] - want[k]).abs().max().item() for k in want)
    assert d < 1e-4, f"training changed: weights differ from the intended semantics by {d:.3g}"
    m = json.load(open(os.path.join(out, "metrics.json")))
    assert len(m["loss_history"]) == 600 and len(m["grad_norm_history"]) == 600
    assert abs(m["loss_history"][-1] - losses[-1]) < 1e-3


def test_memory_does_not_grow(tmp_path):
    short = run(600, str(tmp_path / "a"))
    long = run(1800, str(tmp_path / "b"))
    assert long - short < 100, f"peak RSS grows with training length: {short:.0f} MB at 600 steps, {long:.0f} MB at 1800"
    assert long < 1200, f"peak RSS {long:.0f} MB"
