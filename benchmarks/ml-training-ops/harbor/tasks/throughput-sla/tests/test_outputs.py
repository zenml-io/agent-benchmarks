"""Speed is measured against the original code in the same sandbox: total time at 400 steps, and the
marginal cost of 800 extra steps (so moving work before an internal timer doesn't help)."""
import json
import math
import os
import subprocess
import sys
import time

import pytest
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
APP = os.environ.get("APP_DIR", "/app")


def timed(cwd, steps, tmp):
    out = os.path.join(tmp, f"m-{os.path.basename(cwd)}-{steps}.json")
    t = time.time()
    r = subprocess.run([sys.executable, "train.py", "--steps", str(steps), "--out", out], cwd=cwd,
                       capture_output=True, text=True, timeout=900)
    dt = time.time() - t
    assert r.returncode == 0, r.stderr[-2000:]
    return dt, json.load(open(out))


@pytest.fixture(scope="module")
def timings(tmp_path_factory):
    tmp = str(tmp_path_factory.mktemp("t"))
    base = os.path.join(HERE, "baseline")
    b400, _ = timed(base, 400, tmp)
    b1200, _ = timed(base, 1200, tmp)
    a400, m = timed(APP, 400, tmp)
    a1200, _ = timed(APP, 1200, tmp)
    lines = open(os.path.join(APP, "train_log.jsonl")).read().strip().splitlines()
    return {"b400": b400, "b1200": b1200, "a400": a400, "a1200": a1200, "metrics": m, "log_lines": len(lines)}


def test_same_data_semantics():
    sys.path.insert(0, APP)
    from trainer.data import Events  # noqa: E402
    e = Events(300, seed=5)
    g = torch.Generator().manual_seed(5)
    raw = torch.rand(300, 64, generator=g, dtype=torch.float64)
    w = torch.randn(64, generator=torch.Generator().manual_seed(99), dtype=torch.float64)
    for i in range(0, 300, 7):
        f = [max(-3.0, min(3.0, math.log1p(v * 20.0) - 1.5)) for v in raw[i].tolist()]
        score = sum(a * b for a, b in zip(f, w.tolist())) + math.sin(3.0 * f[0]) + f[1] * f[2]
        x, y = e[i]
        assert torch.allclose(torch.as_tensor(x, dtype=torch.float64), torch.tensor(f, dtype=torch.float64), atol=1e-5)
        assert int(y) == (1 if score > 0 else 0)


def test_same_model_and_optimizer():
    sys.path.insert(0, APP)
    from trainer.model import Scorer  # noqa: E402
    shapes = sorted(tuple(p.shape) for p in Scorer().parameters())
    assert shapes == sorted([(512, 64), (512,), (512, 512), (512,), (2, 512), (2,)])
    src = open(os.path.join(APP, "train.py")).read()
    assert "AdamW" in src and "lr=1e-3" in src and "BATCH = 256" in src


def test_still_learns_and_logs(timings):
    assert timings["metrics"]["accuracy"] >= 0.94
    assert timings["log_lines"] == 1200, "train_log.jsonl must have one line per step"


def test_total_time(timings):
    s = timings["b400"] / timings["a400"]
    assert s >= 10, f"400-step job only {s:.1f}x faster than before ({timings['a400']:.1f}s vs {timings['b400']:.1f}s)"


def test_per_step_cost(timings):
    b = timings["b1200"] - timings["b400"]
    a = max(timings["a1200"] - timings["a400"], 1e-3)
    assert b / a >= 3, f"training steps only {b / a:.1f}x faster ({a:.1f}s vs {b:.1f}s per 800 steps)"
