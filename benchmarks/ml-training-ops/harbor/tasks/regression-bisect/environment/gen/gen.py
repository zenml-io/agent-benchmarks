"""Builds /app/repo: a git history of a small training project in which test accuracy regressed
after tag v1.0. Deterministic (fixed author, dates), so commit SHAs are reproducible."""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import files as F  # noqa: E402

REPO = os.path.abspath("repo")
os.makedirs(REPO, exist_ok=True)
T0 = 1757000000
n = 0


def git(*args, env=None):
    subprocess.run(["git", *args], cwd=REPO, check=True, env=env, stdout=subprocess.DEVNULL)


def commit(msg, author="Priya Raman <priya@example.com>"):
    global n
    n += 1
    name, email = author[:-1].split(" <")
    env = {**os.environ, "GIT_AUTHOR_NAME": name, "GIT_AUTHOR_EMAIL": email, "GIT_COMMITTER_NAME": name,
           "GIT_COMMITTER_EMAIL": email, "GIT_AUTHOR_DATE": f"@{T0 + n * 86400 + 3600 * (n % 5)} +0000",
           "GIT_COMMITTER_DATE": f"@{T0 + n * 86400 + 3600 * (n % 5)} +0000"}
    git("add", "-A")
    git("commit", "-q", "-m", msg, env=env)


def w(path, text):
    p = os.path.join(REPO, path)
    os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
    open(p, "w").write(text)


def r(path):
    return open(os.path.join(REPO, path)).read()


def sub(path, old, new):
    s = r(path)
    assert old in s, (path, old[:60])
    w(path, s.replace(old, new))


git("init", "-q", "-b", "main")
git("config", "commit.gpgsign", "false")
w("data.py", F.DATA)
w("model.py", F.MODEL)
w("train.py", F.TRAIN_V1)
w("README.md", "# churn-risk classifier\n\nTabular classifier trained nightly.\n")
commit("Initial training pipeline")
sub("README.md", "trained nightly.\n", "trained nightly.\n\n## Usage\n\n    python train.py --seed 0 --out metrics.json\n")
commit("README: usage")
sub("train.py", "            sched.step()\n", "            sched.step()\n        print(f\"epoch {epoch} loss {loss.item():.4f}\", flush=True)\n")
commit("Print epoch progress", "Tom Becker <tom@example.com>")
git("tag", "v1.0")

sub("train.py", '''def param_groups(m):
    decay = [p for p in m.parameters() if p.ndim > 1]
    no_decay = [p for p in m.parameters() if p.ndim <= 1]
    return [{"params": decay, "weight_decay": WEIGHT_DECAY}, {"params": no_decay, "weight_decay": 0.0}]''',
    '''def param_groups(m):
    # one group is enough; AdamW decoupled decay is mild
    return [{"params": list(m.parameters()), "weight_decay": WEIGHT_DECAY}]''')
commit("Simplify optimizer setup: single param group", "Tom Becker <tom@example.com>")

sub("train.py", "    for epoch in range(EPOCHS):\n", "    log = open(\"metrics.jsonl\", \"w\")\n    for epoch in range(EPOCHS):\n")
sub("train.py", "        print(f\"epoch {epoch} loss {loss.item():.4f}\", flush=True)\n",
    "        print(f\"epoch {epoch} loss {loss.item():.4f}\", flush=True)\n        log.write(json.dumps({\"epoch\": epoch, \"loss\": loss.item()}) + \"\\n\")\n")
commit("Write per-epoch metrics to metrics.jsonl")

sub("train.py", "            loss = F.cross_entropy(m((xtr[idx] - mu) / sd), ytr[idx], label_smoothing=LABEL_SMOOTHING)",
    "            xb = xtr[idx]\n            xb = (xb - xb.mean(0)) / (xb.std(0) + 1e-6)  # per-batch: works for streaming input\n"
    "            loss = F.cross_entropy(m(xb), ytr[idx], label_smoothing=LABEL_SMOOTHING)")
commit("Normalize each batch independently (prepares for streaming input)", "Ana Silva <ana@example.com>")

# the regression: hyperparameters move to config.yaml, and the batch size silently changes
w("config.yaml", "# training hyperparameters (moved out of train.py)\nbatch_size: 1024\nlr: 0.002\nepochs: 12\n"
  "weight_decay: 0.1\nlabel_smoothing: 0.05\n")
sub("train.py", '''BATCH = 256
LR = 2e-3
EPOCHS = 12
WEIGHT_DECAY = 0.1
LABEL_SMOOTHING = 0.05
''', '''import yaml

CFG = yaml.safe_load(open(__import__("os").path.join(__import__("os").path.dirname(__file__), "config.yaml")))
BATCH = CFG["batch_size"]
LR = CFG["lr"]
EPOCHS = CFG["epochs"]
WEIGHT_DECAY = CFG["weight_decay"]
LABEL_SMOOTHING = CFG["label_smoothing"]
''')
commit("Move hyperparameters to config.yaml", "Ana Silva <ana@example.com>")

sub("train.py", '''        acc = (m((xte - mu) / sd).argmax(1) == yte).float().mean().item()''',
    '''        pred = m((xte - mu) / sd).argmax(1)
        acc = (pred == yte).float().mean().item()
        f1s = []
        for c in range(10):
            tp = ((pred == c) & (yte == c)).sum().item()
            prec = tp / max((pred == c).sum().item(), 1)
            rec = tp / max((yte == c).sum().item(), 1)
            f1s.append(0.0 if tp == 0 else 2 * prec * rec / (prec + rec))
        macro_f1 = sum(f1s) / len(f1s)''')
sub("train.py", 'print(f"seed {a.seed} test accuracy {acc:.4f}")', 'print(f"seed {a.seed} test accuracy {acc:.4f} macro-F1 {macro_f1:.4f}")')
sub("train.py", '{"accuracy": acc, "seed": a.seed}', '{"accuracy": acc, "macro_f1": macro_f1, "seed": a.seed}')
commit("Report macro-F1 alongside accuracy", "Tom Becker <tom@example.com>")

sub("config.yaml", "label_smoothing: 0.05", "label_smoothing: 0.1")
commit("Label smoothing 0.05 -> 0.1 (calibration request from risk team)", "Ana Silva <ana@example.com>")

sub("train.py", 'ap.add_argument("--seed", type=int, default=0)', 'ap.add_argument("--seed", type=int, default=1234)')
commit("Default seed 1234 for the reproducibility audit")

sub("train.py", '    ap.add_argument("--out", default=None)\n',
    '    ap.add_argument("--out", default=None)\n    ap.add_argument("--save", default=None, help="write the trained weights here")\n')
sub("train.py", '    if a.out:\n', '    if a.save:\n        torch.save(m.state_dict(), a.save)\n    if a.out:\n')
commit("Add --save for the deployment pipeline", "Tom Becker <tom@example.com>")

sub("train.py", "    mu, sd = xtr.mean(0), xtr.std(0)\n",
    "    keep = torch.unique(xtr, dim=0, return_inverse=True)[1].unique()  # drop exact duplicate rows\n"
    "    xtr, ytr = xtr[keep], ytr[keep]\n    mu, sd = xtr.mean(0), xtr.std(0)\n")
commit("Deduplicate training rows", "Ana Silva <ana@example.com>")

sub("config.yaml", "epochs: 12", "epochs: 14")
commit("Train 14 epochs", "Tom Becker <tom@example.com>")

w("smoke_test.sh", "#!/bin/bash\nset -e\npython train.py --seed 0 --out /tmp/m.json\npython -c \"import json; assert json.load(open('/tmp/m.json'))['accuracy'] > 0.5\"\n")
commit("CI smoke test")

sub("README.md", "    python train.py --seed 0 --out metrics.json\n",
    "    python train.py --seed 0 --out metrics.json\n\nHyperparameters live in config.yaml. Accuracy is reported on the fixed test split.\n")
commit("README: config")
print(subprocess.run(["git", "log", "--oneline"], cwd=REPO, capture_output=True, text=True).stdout)
