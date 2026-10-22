"""
Generate the ML-training-operations pilot tasks (Harbor task format) into this directory.

    python make_tasks.py              # writes <task>/{instruction.md,task.toml,environment,tests,solution}
    python make_tasks.py --check      # locally: buggy code must FAIL its tests, the solution must PASS

Each task is a small PyTorch training job (CPU, seconds to a few minutes) with one injected
fault from real training operations. The tests do not trust the agent's own reports: they
retrain or re-evaluate from the agent's code and compare against values the test computes
itself. The injected fault is known, so the right fix is known.
"""

import argparse
import os
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

HERE = Path(__file__).resolve().parent

DATA = '''
import torch


def make_data(n, seed, d=32, k=4):
    """Synthetic classification data from a fixed random teacher (the same for every seed)."""
    teacher = torch.Generator().manual_seed(1234)
    W = torch.randn(d, k, generator=teacher)
    g = torch.Generator().manual_seed(seed)
    X = torch.randn(n, d, generator=g)
    y = (X @ W + 0.5 * torch.tanh(X[:, :k])).argmax(1)
    return X, y
'''

EVAL_HELPER = '''
import os, sys, torch
APP = os.environ.get("APP_DIR", "/app")
sys.path.insert(0, APP)
from data import make_data  # noqa: E402


def accuracy(model, n=4000, seed=999):
    X, y = make_data(n, seed)
    model.eval()
    with torch.no_grad():
        return (model(X).argmax(1) == y).float().mean().item()
'''

TASKS = {}

# ------------------------------------------------------------------ 1. NaN loss
TASKS["nan-loss"] = dict(
    instruction="""\
The training job in /app (`python /app/train.py`) produces NaN losses after the first few steps
and the saved model is useless. Find and fix the cause so that training is numerically stable
and the model learns.

Constraints: keep the model architecture, its initialization, the optimizer, the learning rate,
the batch size and the number of steps exactly as they are. The job must still save the trained
weights to /app/model.pt.
""",
    app={"data.py": DATA, "train.py": '''
import json
import torch
import torch.nn as nn
from data import make_data


def loss_fn(logits, y):
    """Softmax cross-entropy."""
    p = torch.exp(logits) / torch.exp(logits).sum(1, keepdim=True)
    return -torch.log(p[torch.arange(len(y)), y]).mean()


def build_model():
    model = nn.Sequential(nn.Linear(32, 128), nn.ReLU(), nn.Linear(128, 4))
    with torch.no_grad():
        model[2].weight.mul_(100.0)  # wide output init used by the original recipe
    return model


def main():
    torch.manual_seed(0)
    X, y = make_data(8192, seed=1)
    model = build_model()
    opt = torch.optim.SGD(model.parameters(), lr=0.02)
    for step in range(600):
        idx = torch.randint(0, len(X), (256,))
        loss = loss_fn(model(X[idx]), y[idx])
        opt.zero_grad()
        loss.backward()
        opt.step()
        if step % 100 == 0:
            print(f"step {step} loss {loss.item():.4f}")
    torch.save(model.state_dict(), "/app/model.pt")
    json.dump({"final_loss": loss.item()}, open("/app/metrics.json", "w"))


if __name__ == "__main__":
    main()
'''},
    test=EVAL_HELPER + '''
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
''',
    solution={"train.py": "PATCH:loss_fn"},
)

# ------------------------------------------------------------------ 2. data/label misalignment
TASKS["label-shuffle"] = dict(
    instruction="""\
A colleague added shuffling to the data pipeline in /app (`python /app/train.py`). Since then the
model's accuracy is stuck around chance level even though the loss goes down a little. Find and
fix the bug in the data pipeline so the model learns properly again. Do not change the model,
optimizer or hyperparameters. The job must still save its weights to /app/model.pt.
""",
    app={"data.py": DATA, "train.py": '''
import torch
import torch.nn as nn
from data import make_data


class ShuffledDataset:
    """Shuffles the training set once per epoch."""

    def __init__(self, X, y, seed=0):
        self.X, self.y, self.g = X, y, torch.Generator().manual_seed(seed)

    def epoch(self):
        xi = torch.randperm(len(self.X), generator=self.g)
        yi = torch.randperm(len(self.y), generator=self.g)
        return self.X[xi], self.y[yi]


def build_model():
    return nn.Sequential(nn.Linear(32, 128), nn.ReLU(), nn.Linear(128, 4))


def main():
    torch.manual_seed(0)
    X, y = make_data(8192, seed=1)
    ds = ShuffledDataset(X, y)
    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    for epoch in range(8):
        Xe, ye = ds.epoch()
        for i in range(0, len(Xe), 256):
            loss = nn.functional.cross_entropy(model(Xe[i:i + 256]), ye[i:i + 256])
            opt.zero_grad()
            loss.backward()
            opt.step()
        print(f"epoch {epoch} loss {loss.item():.4f}")
    torch.save(model.state_dict(), "/app/model.pt")


if __name__ == "__main__":
    main()
'''},
    test=EVAL_HELPER + '''
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
''',
    solution={"train.py": "PATCH:shuffle"},
)

# ------------------------------------------------------------------ 3. checkpoint resume
TASKS["resume-checkpoint"] = dict(
    instruction="""\
Our training job (/app/train.py) can be interrupted and resumed: `python /app/train.py --steps N
--ckpt PATH` trains up to step N and saves a checkpoint, and `--resume` continues from it. After a
resume, the loss jumps and the final model differs from an uninterrupted run. Fix checkpointing
and resuming so that training for 300 steps in one go and training 150 steps, then resuming to 300,
produce the same final weights (up to floating-point noise). Keep the model, optimizer (Adam),
learning-rate schedule and data order as they are.
""",
    app={"data.py": DATA, "train.py": '''
import argparse
import torch
import torch.nn as nn
from data import make_data


def build_model():
    return nn.Sequential(nn.Linear(32, 128), nn.ReLU(), nn.Linear(128, 4))


def batch(step, X, y, bs=128):
    g = torch.Generator().manual_seed(10_000 + step)  # data order is a function of the step
    idx = torch.randint(0, len(X), (bs,), generator=g)
    return X[idx], y[idx]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--steps", type=int, default=300)
    ap.add_argument("--ckpt", default="/app/ckpt.pt")
    ap.add_argument("--resume", action="store_true")
    a = ap.parse_args()
    torch.manual_seed(0)
    X, y = make_data(8192, seed=1)
    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=2e-3)
    sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=300)
    start = 0
    if a.resume:
        state = torch.load(a.ckpt)
        model.load_state_dict(state["model"])
    for step in range(start, a.steps):
        xb, yb = batch(step, X, y)
        loss = nn.functional.cross_entropy(model(xb), yb)
        opt.zero_grad()
        loss.backward()
        opt.step()
        sched.step()
    torch.save({"model": model.state_dict()}, a.ckpt)
    print(f"done at step {a.steps}, loss {loss.item():.4f}")


if __name__ == "__main__":
    main()
'''},
    test=EVAL_HELPER + '''
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
''',
    solution={"train.py": "PATCH:resume"},
)

# ------------------------------------------------------------------ 4. out of memory
TASKS["oom-grad-accum"] = dict(
    instruction="""\
The training job in /app (`python /app/train.py`) is killed by the cluster for exceeding its
memory limit: jobs may use at most 1.2 GB of resident memory, and this one peaks far above that.
Make it fit under 1.2 GB without changing what it computes: the effective batch size per optimizer
step (32768 samples), the model, the optimizer, the learning rate, the number of optimizer steps
and the data must stay the same, and the final weights must match what the original job would
have produced (up to floating-point noise). The job must still save its weights to /app/model.pt.
""",
    app={"data.py": DATA, "train.py": '''
import torch
import torch.nn as nn
from data import make_data

BATCH = 32768


def build_model():
    return nn.Sequential(nn.Linear(32, 2048), nn.ReLU(), nn.Linear(2048, 2048), nn.ReLU(),
                         nn.Linear(2048, 2048), nn.ReLU(), nn.Linear(2048, 4))


def main():
    torch.manual_seed(0)
    X, y = make_data(BATCH * 4, seed=1)
    model = build_model()
    opt = torch.optim.SGD(model.parameters(), lr=0.05)
    for step in range(4):
        xb, yb = X[step * BATCH:(step + 1) * BATCH], y[step * BATCH:(step + 1) * BATCH]
        loss = nn.functional.cross_entropy(model(xb), yb)
        opt.zero_grad()
        loss.backward()
        opt.step()
        print(f"step {step} loss {loss.item():.4f}")
    torch.save(model.state_dict(), "/app/model.pt")


if __name__ == "__main__":
    main()
'''},
    test=EVAL_HELPER + '''
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
''',
    solution={"train.py": "PATCH:accum"},
)

# ------------------------------------------------------------------ 5. distributed sharding
TASKS["ddp-sharding"] = dict(
    instruction="""\
/app/train_ddp.py trains with torch.distributed (2 processes on CPU, gloo backend):
`torchrun --nproc_per_node 2 /app/train_ddp.py`. Each rank writes the sample indices it trained on
to /app/seen_rank{R}.json (one list per epoch). Training is slower than expected and the loss
curve looks like the job only sees half the data. Fix the data sharding so that in every epoch
each training sample is processed by exactly one rank, the two ranks together cover the whole
training set, and the order changes from epoch to epoch. Keep the model, optimizer, number of
epochs and per-rank batch size as they are.
""",
    app={"data.py": DATA, "train_ddp.py": '''
import json
import os
import torch
import torch.distributed as dist
import torch.nn as nn
from torch.utils.data import DataLoader, TensorDataset
from data import make_data


def main():
    dist.init_process_group("gloo")
    rank, world = dist.get_rank(), dist.get_world_size()
    torch.manual_seed(0)
    X, y = make_data(4096, seed=1)
    ds = TensorDataset(torch.arange(len(X)), X, y)
    loader = DataLoader(ds, batch_size=128, shuffle=True)
    model = nn.parallel.DistributedDataParallel(nn.Sequential(nn.Linear(32, 64), nn.ReLU(), nn.Linear(64, 4)))
    opt = torch.optim.SGD(model.parameters(), lr=0.05)
    seen = []
    for epoch in range(3):
        ep = []
        for idx, xb, yb in loader:
            loss = nn.functional.cross_entropy(model(xb), yb)
            opt.zero_grad()
            loss.backward()
            opt.step()
            ep += idx.tolist()
        seen.append(ep)
    json.dump(seen, open(f"/app/seen_rank{rank}.json", "w"))
    dist.destroy_process_group()


if __name__ == "__main__":
    main()
'''},
    test='''
import json, os, shutil, subprocess

APP = os.environ.get("APP_DIR", "/app")


def test_each_sample_once_per_epoch():
    for r in (0, 1):
        p = os.path.join(APP, f"seen_rank{r}.json")
        if os.path.exists(p):
            os.remove(p)
    torchrun = shutil.which("torchrun")
    subprocess.run([torchrun, "--nproc_per_node", "2", os.path.join(APP, "train_ddp.py")], cwd=APP,
                   check=True, timeout=600, env={**os.environ, "OMP_NUM_THREADS": "1"})
    r0 = json.load(open(os.path.join(APP, "seen_rank0.json")))
    r1 = json.load(open(os.path.join(APP, "seen_rank1.json")))
    assert len(r0) == len(r1) == 3
    for e in range(3):
        a, b = r0[e], r1[e]
        assert not set(a) & set(b), "ranks overlap"
        assert sorted(a + b) == list(range(4096)), "not every sample exactly once"
    assert r0[0] != r0[1], "order does not change between epochs"
''',
    solution={"train_ddp.py": "PATCH:ddp"},
)

# ------------------------------------------------------------------ 6. eval mode
TASKS["eval-mode"] = dict(
    instruction="""\
/app/train.py trains a model with dropout and batch normalization and reports validation accuracy
after every epoch in /app/metrics.json. The reported validation accuracy is noisy, lower than
expected, and evaluating changes the model. Fix the evaluation so that it reports the model's
true validation accuracy and leaves the model unchanged, without changing the model or the
training loop.
""",
    app={"data.py": DATA, "train.py": '''
import json
import torch
import torch.nn as nn
from data import make_data


def build_model():
    return nn.Sequential(nn.Linear(32, 128), nn.BatchNorm1d(128), nn.ReLU(), nn.Dropout(0.5), nn.Linear(128, 4))


def evaluate(model, X, y):
    correct = 0
    for i in range(0, len(X), 64):
        out = model(X[i:i + 64])
        correct += (out.argmax(1) == y[i:i + 64]).sum().item()
    return correct / len(X)


def main():
    torch.manual_seed(0)
    X, y = make_data(8192, seed=1)
    Xv, yv = make_data(2000, seed=2)
    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=3e-3)
    hist = []
    for epoch in range(6):
        model.train()
        perm = torch.randperm(len(X))
        for i in range(0, len(X), 256):
            idx = perm[i:i + 256]
            loss = nn.functional.cross_entropy(model(X[idx]), y[idx])
            opt.zero_grad()
            loss.backward()
            opt.step()
        hist.append(evaluate(model, Xv, yv))
    torch.save(model.state_dict(), "/app/model.pt")
    json.dump({"val_acc": hist}, open("/app/metrics.json", "w"))


if __name__ == "__main__":
    main()
'''},
    test=EVAL_HELPER + '''
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
''',
    solution={"train.py": "PATCH:evalmode"},
)

# ------------------------------------------------------------------ reference fixes


def patched(task, files):
    """The reference fix for each task, applied to the buggy source."""
    app = TASKS[task]["app"]
    out = {}
    for name, how in files.items():
        s = app[name]
        if how == "PATCH:loss_fn":
            s = s.replace('''    p = torch.exp(logits) / torch.exp(logits).sum(1, keepdim=True)
    return -torch.log(p[torch.arange(len(y)), y]).mean()''', '''    return nn.functional.cross_entropy(logits, y)''')
        elif how == "PATCH:shuffle":
            s = s.replace('''        xi = torch.randperm(len(self.X), generator=self.g)
        yi = torch.randperm(len(self.y), generator=self.g)
        return self.X[xi], self.y[yi]''', '''        perm = torch.randperm(len(self.X), generator=self.g)
        return self.X[perm], self.y[perm]''')
        elif how == "PATCH:resume":
            s = s.replace('''        model.load_state_dict(state["model"])''', '''        model.load_state_dict(state["model"])
        opt.load_state_dict(state["opt"])
        sched.load_state_dict(state["sched"])
        start = state["step"]''').replace(
                '''    torch.save({"model": model.state_dict()}, a.ckpt)''',
                '''    torch.save({"model": model.state_dict(), "opt": opt.state_dict(), "sched": sched.state_dict(),
                "step": a.steps}, a.ckpt)''')
        elif how == "PATCH:accum":
            s = s.replace('''        loss = nn.functional.cross_entropy(model(xb), yb)
        opt.zero_grad()
        loss.backward()
        opt.step()''', '''        opt.zero_grad()
        for i in range(0, BATCH, 1024):
            loss = nn.functional.cross_entropy(model(xb[i:i + 1024]), yb[i:i + 1024], reduction="sum") / BATCH
            loss.backward()
        opt.step()''')
        elif how == "PATCH:ddp":
            s = s.replace('''    loader = DataLoader(ds, batch_size=128, shuffle=True)''', '''    sampler = torch.utils.data.distributed.DistributedSampler(ds, num_replicas=world, rank=rank, shuffle=True)
    loader = DataLoader(ds, batch_size=128, sampler=sampler)''').replace(
                '''        ep = []''', '''        sampler.set_epoch(epoch)
        ep = []''')
        elif how == "PATCH:evalmode":
            s = s.replace('''def evaluate(model, X, y):
    correct = 0
    for i in range(0, len(X), 64):
        out = model(X[i:i + 64])
        correct += (out.argmax(1) == y[i:i + 64]).sum().item()
    return correct / len(X)''', '''def evaluate(model, X, y):
    was_training = model.training
    model.eval()
    correct = 0
    with torch.no_grad():
        for i in range(0, len(X), 64):
            out = model(X[i:i + 64])
            correct += (out.argmax(1) == y[i:i + 64]).sum().item()
    model.train(was_training)
    return correct / len(X)''')
        assert s != app[name], f"patch {how} did not apply"
        out[name] = s
    return out


def write(task, root):
    t = TASKS[task]
    d = root / task
    if d.exists():
        shutil.rmtree(d)
    (d / "environment" / "app").mkdir(parents=True)
    (d / "tests").mkdir()
    (d / "solution").mkdir()
    (d / "instruction.md").write_text(t["instruction"])
    (d / "task.toml").write_text((HERE / "_task.toml").read_text())
    (d / "environment" / "Dockerfile").write_text((HERE / "_Dockerfile").read_text())
    for name, src in t["app"].items():
        (d / "environment" / "app" / name).write_text(textwrap.dedent(src).lstrip())
    (d / "tests" / "test_outputs.py").write_text(textwrap.dedent(t["test"]).lstrip())
    (d / "tests" / "test.sh").write_text((HERE / "_test.sh").read_text())
    os.chmod(d / "tests" / "test.sh", 0o755)
    sol = patched(task, t["solution"])
    lines = ["#!/bin/bash", "set -e"]
    for name, src in sol.items():
        lines += [f"cat > /app/{name} <<'PYEOF'", textwrap.dedent(src).lstrip().rstrip(), "PYEOF"]
    (d / "solution" / "solve.sh").write_text("\n".join(lines) + "\n")
    os.chmod(d / "solution" / "solve.sh", 0o755)


def check(task, python):
    """Run the task's test locally against the buggy app and against the reference fix."""
    res = {}
    for variant in ("buggy", "fixed"):
        tmp = Path(tempfile.mkdtemp())
        app = tmp / "app"
        shutil.copytree(HERE / task / "environment" / "app", app)
        if variant == "fixed":
            for name, src in patched(task, TASKS[task]["solution"]).items():
                (app / name).write_text(textwrap.dedent(src).lstrip())
        for name in os.listdir(app):  # tests and code use /app paths; point them at the copy
            p = app / name
            p.write_text(p.read_text().replace("/app/", str(app) + "/"))
        test = (HERE / task / "tests" / "test_outputs.py").read_text()
        (tmp / "test_outputs.py").write_text(test)
        env = {**os.environ, "APP_DIR": str(app), "PATH": str(Path(python).parent) + ":" + os.environ["PATH"]}
        r = subprocess.run([python, "-m", "pytest", "-q", "-x", "-p", "no:cacheprovider", str(tmp / "test_outputs.py")],
                           cwd=app, env=env, capture_output=True, text=True, timeout=1800)
        res[variant] = r.returncode == 0
        if (variant == "buggy") == res[variant]:
            print(r.stdout[-1500:])
    ok = (not res["buggy"]) and res["fixed"]
    print(f"{task:20s} buggy {'passes (BAD)' if res['buggy'] else 'fails'} | fix {'passes' if res['fixed'] else 'FAILS (BAD)'} -> {'OK' if ok else 'PROBLEM'}",
          flush=True)
    return ok


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--python", default=sys.executable)
    ap.add_argument("tasks", nargs="*")
    a = ap.parse_args()
    names = a.tasks or list(TASKS)
    for t in names:
        write(t, HERE)
    if a.check:
        sys.exit(0 if all([check(t, a.python) for t in names]) else 1)
    print("wrote", ", ".join(names))
