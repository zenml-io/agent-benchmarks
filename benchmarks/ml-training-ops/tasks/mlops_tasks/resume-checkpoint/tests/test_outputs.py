import os, sys, torch
APP = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP)
from data import make_data  # noqa: E402


def accuracy(model, n=4000, seed=999):
    X, y = make_data(n, seed)
    model.eval()
    with torch.no_grad():
        return (model(X).argmax(1) == y).float().mean().item()

import subprocess, tempfile


def run(*args):
    subprocess.run([sys.executable, os.path.join(APP, "train.py"), *args], cwd=APP, check=True, timeout=600)


def test_resume_matches_uninterrupted():
    d = tempfile.mkdtemp()
    full, part = os.path.join(d, "full.pt"), os.path.join(d, "part.pt")
    run("--steps", "300", "--ckpt", full)
    run("--steps", "150", "--ckpt", part)
    run("--steps", "300", "--ckpt", part, "--resume")
    a, b = torch.load(full)["model"], torch.load(part)["model"]
    for k in a:
        assert torch.allclose(a[k], b[k], atol=1e-5), k
