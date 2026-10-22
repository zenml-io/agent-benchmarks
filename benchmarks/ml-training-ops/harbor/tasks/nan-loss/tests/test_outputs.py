import os, sys, torch
APP = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP)
from data import make_data  # noqa: E402


def accuracy(model, n=4000, seed=999):
    X, y = make_data(n, seed)
    model.eval()
    with torch.no_grad():
        return (model(X).argmax(1) == y).float().mean().item()

import json, math, re, subprocess


def test_trains_stably_and_learns():
    src = open(os.path.join(APP, "train.py")).read()
    assert "lr=0.02" in src and "range(600)" in src and "mul_(100.0)" in src, "hyperparameters were changed"
    subprocess.run([sys.executable, os.path.join(APP, "train.py")], cwd=APP, check=True, timeout=600)
    m = json.load(open(os.path.join(APP, "metrics.json")))
    assert math.isfinite(m["final_loss"])
    import train  # noqa: E402
    model = train.build_model()
    model.load_state_dict(torch.load(os.path.join(APP, "model.pt")))
    assert all(torch.isfinite(p).all() for p in model.parameters())
    assert accuracy(model) >= 0.85


def _pristine_build_model():
    """The task's original build_model(), which the instruction says to keep."""
    import torch.nn as nn
    model = nn.Sequential(nn.Linear(32, 128), nn.ReLU(), nn.Linear(128, 4))
    with torch.no_grad():
        model[2].weight.mul_(100.0)
    return model


def test_initialization_kept():
    """Added for the Harbor-native version: rescaling the init after the wide multiply makes training
    stable while keeping the multiply in the source, which the source check above cannot see."""
    import train  # noqa: E402
    for seed in (0, 1):
        torch.manual_seed(seed)
        got = train.build_model().state_dict()
        torch.manual_seed(seed)
        want = _pristine_build_model().state_dict()
        assert list(got) == list(want), "model architecture changed"
        for k in want:
            assert torch.equal(got[k], want[k]), f"initialization of {k} changed"
