import json
import os
import subprocess
import sys

import pytest
import yaml

APP = os.environ.get("APP_DIR", "/app")
REPO = os.path.join(APP, "repo")
CULPRIT = "4b1b9009b6b71df2eb74eefbb2f43aecd786b5a1"


def test_culprit():
    ans = json.load(open(os.path.join(APP, "answer.json")))
    got = ans["culprit_commit"].strip().lower()
    assert len(got) >= 7 and CULPRIT.startswith(got), f"wrong commit {got}"


def test_constraints_kept():
    cfg = yaml.safe_load(open(os.path.join(REPO, "config.yaml")))
    assert cfg["batch_size"] == 1024 and cfg["epochs"] == 14
    assert cfg["label_smoothing"] == 0.1 and cfg["weight_decay"] == 0.1


@pytest.fixture(scope="module")
def runs(tmp_path_factory):
    out = []
    d = tmp_path_factory.mktemp("runs")
    for seed in (0, 1, 2):
        f = str(d / f"m{seed}.json")
        w = str(d / f"w{seed}.pt")
        r = subprocess.run([sys.executable, "train.py", "--seed", str(seed), "--out", f, "--save", w], cwd=REPO,
                           capture_output=True, text=True, timeout=900)
        assert r.returncode == 0, r.stderr[-2000:]
        m = json.load(open(f))
        assert "macro_f1" in m and os.path.exists(w)
        out.append(m["accuracy"])
    assert os.path.exists(os.path.join(REPO, "metrics.jsonl"))
    return out


def test_accuracy_recovered(runs):
    mean = sum(runs) / len(runs)
    assert mean >= 0.664, f"mean accuracy {mean:.4f} over seeds 0-2 ({[round(a, 4) for a in runs]})"
