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


COUNT_STEPS = """
import runpy, sys, torch
calls = [0]
orig = torch.optim.Adam.step
def step(self, *a, **k):
    calls[0] += 1
    return orig(self, *a, **k)
torch.optim.Adam.step = step
sys.argv = [sys.argv[1]] + sys.argv[2:]
sys.path.insert(0, __import__("os").path.dirname(sys.argv[0]))
runpy.run_path(sys.argv[0], run_name="__main__")
print("OPTIMIZER_STEPS", calls[0])
"""


def test_resume_continues_instead_of_retraining():
    """Added for the Harbor-native version: retraining from step 0 on --resume also ends with the
    uninterrupted weights, so count the optimizer steps a resume from step 150 to 300 takes."""
    d = tempfile.mkdtemp()
    part = os.path.join(d, "part.pt")
    run("--steps", "150", "--ckpt", part)
    r = subprocess.run([sys.executable, "-c", COUNT_STEPS, os.path.join(APP, "train.py"), "--steps", "300", "--ckpt",
                        part, "--resume"], cwd=APP, capture_output=True, text=True, timeout=600)
    assert r.returncode == 0, r.stderr[-2000:]
    n = int(r.stdout.split("OPTIMIZER_STEPS")[-1].split()[0])
    assert n <= 150, f"resuming from step 150 to 300 took {n} optimizer steps: it retrained instead of resuming"
