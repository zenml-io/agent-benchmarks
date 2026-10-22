import hashlib
import json
import os
import subprocess

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
TITAN = "/app/titan"
GOLDEN = json.load(open(os.path.join(HERE, "golden.json")))["losses"]
CORPUS_SHA = json.load(open(os.path.join(HERE, "corpus_sha.json")))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


def test_corpus_untouched():
    files = sorted(os.listdir("/data/corpus"))
    assert files == sorted(CORPUS_SHA), f"corpus files changed: {files}"
    for f, h in CORPUS_SHA.items():
        assert sha(os.path.join("/data/corpus", f)) == h, f"{f} was modified"


def test_config_unchanged_except_exclude():
    import tomllib
    cfg = tomllib.load(open(os.path.join(TITAN, "torchtitan/models/llama3/train_configs/internal_200m.toml"), "rb"))
    want = json.load(open(os.path.join(HERE, "config_ref.json")))
    cfg["training"].pop("exclude_shards", None)
    want["training"].pop("exclude_shards", None)
    assert cfg == want, "internal_200m.toml changed beyond training.exclude_shards"


def test_code_untouched():
    ref = json.load(open(os.path.join(HERE, "code_sha.json")))
    bad = [p for p, h in ref.items() if sha(os.path.join(TITAN, p)) != h]
    assert not bad, f"training code changed: {bad[:5]}"


@pytest.fixture(scope="module")
def curve():
    out = "/tmp/grader_losses.json"
    r = subprocess.run(["bash", os.path.join(HERE, "run_reference.sh"), out], capture_output=True, text=True, timeout=2400)
    assert os.path.exists(out), r.stdout[-2000:] + r.stderr[-2000:]
    c = json.load(open(out))
    assert None not in c, "the acceptance run did not complete 1000 steps:\n" + r.stdout[-2000:]
    return c


def test_matches_golden(curve):
    d = [abs(a - b) for a, b in zip(curve, GOLDEN)]
    late = sum(d[900:]) / 100
    assert late < 0.002 and max(d) < 0.01, f"mean |d| steps 901-1000 = {late:.4f}, max |d| = {max(d):.4f}"
