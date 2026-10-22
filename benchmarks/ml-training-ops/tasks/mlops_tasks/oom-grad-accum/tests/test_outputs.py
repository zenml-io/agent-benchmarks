import os, sys, torch
APP = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP)
from data import make_data  # noqa: E402


def accuracy(model, n=4000, seed=999):
    X, y = make_data(n, seed)
    model.eval()
    with torch.no_grad():
        return (model(X).argmax(1) == y).float().mean().item()

import re, subprocess
import torch.nn as nn


def reference():
    """The original job's math, computed in micro-batches (the test's own implementation)."""
    import train
    torch.manual_seed(0)
    X, y = make_data(32768 * 4, seed=1)
    model = train.build_model()
    opt = torch.optim.SGD(model.parameters(), lr=0.05)
    for step in range(4):
        xb, yb = X[step * 32768:(step + 1) * 32768], y[step * 32768:(step + 1) * 32768]
        opt.zero_grad()
        for i in range(0, 32768, 1024):
            loss = nn.functional.cross_entropy(model(xb[i:i + 1024]), yb[i:i + 1024], reduction="sum") / 32768
            loss.backward()
        opt.step()
    return model.state_dict()


def test_fits_memory_and_matches():
    src = open(os.path.join(APP, "train.py")).read()
    assert "nn.Linear(2048, 2048)" in src and "lr=0.05" in src
    import resource
    before = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss
    out = subprocess.run([sys.executable, os.path.join(APP, "train.py")], cwd=APP,
                         capture_output=True, text=True, timeout=900)
    assert out.returncode == 0, out.stderr[-2000:]
    peak_kb = resource.getrusage(resource.RUSAGE_CHILDREN).ru_maxrss  # largest child so far (kB on Linux)
    assert peak_kb > before or before < 1.2 * 1024 * 1024
    assert peak_kb < 1.2 * 1024 * 1024, f"peak RSS {peak_kb / 1024:.0f} MB"
    got = torch.load(os.path.join(APP, "model.pt"))
    ref = reference()
    for k in ref:
        assert torch.allclose(got[k], ref[k], atol=1e-4, rtol=1e-3), k
