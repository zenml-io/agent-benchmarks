import os, sys, torch
APP = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP)
from data import make_data  # noqa: E402


def accuracy(model, n=4000, seed=999):
    X, y = make_data(n, seed)
    model.eval()
    with torch.no_grad():
        return (model(X).argmax(1) == y).float().mean().item()

import copy, json, subprocess


def test_eval_is_correct_and_side_effect_free():
    src = open(os.path.join(APP, "train.py")).read()
    assert "nn.Dropout(0.5)" in src and "BatchNorm1d(128)" in src
    subprocess.run([sys.executable, os.path.join(APP, "train.py")], cwd=APP, check=True, timeout=600)
    import train  # noqa: E402
    model = train.build_model()
    model.load_state_dict(torch.load(os.path.join(APP, "model.pt")))
    Xv, yv = make_data(2000, seed=2)
    reported = json.load(open(os.path.join(APP, "metrics.json")))["val_acc"][-1]
    model.eval()
    with torch.no_grad():
        true = (model(Xv).argmax(1) == yv).float().mean().item()
    assert abs(reported - true) < 0.005, (reported, true)
    m2 = train.build_model()
    m2.load_state_dict(torch.load(os.path.join(APP, "model.pt")))
    m2.train()
    before = copy.deepcopy(m2.state_dict())
    a1 = train.evaluate(m2, Xv, yv)
    a2 = train.evaluate(m2, Xv, yv)
    assert a1 == a2
    for k, v in m2.state_dict().items():
        assert torch.equal(v, before[k]), f"evaluation changed {k}"
