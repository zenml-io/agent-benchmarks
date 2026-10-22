import os, sys, torch
APP = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP)
from data import make_data  # noqa: E402


def accuracy(model, n=4000, seed=999):
    X, y = make_data(n, seed)
    model.eval()
    with torch.no_grad():
        return (model(X).argmax(1) == y).float().mean().item()

import subprocess


def test_learns_with_shuffling():
    subprocess.run([sys.executable, os.path.join(APP, "train.py")], cwd=APP, check=True, timeout=600)
    import train  # noqa: E402
    model = train.build_model()
    model.load_state_dict(torch.load(os.path.join(APP, "model.pt")))
    assert accuracy(model) >= 0.9
    # shuffling must still happen (pairs kept together, order changes between epochs)
    X, y = make_data(512, seed=5)
    ds = train.ShuffledDataset(X, y, seed=3)
    a, b = ds.epoch(), ds.epoch()
    assert not torch.equal(a[0], X) and not torch.equal(a[0], b[0])
    lut = {tuple(x.tolist()): int(t) for x, t in zip(X, y)}
    assert all(lut[tuple(x.tolist())] == int(t) for x, t in zip(*a))
