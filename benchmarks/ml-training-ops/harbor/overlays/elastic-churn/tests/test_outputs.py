"""Elastic churn: run the job as successive torchrun launches with changing world sizes, SIGKILL each
launch at a random moment (including mid-checkpoint), then let a final launch finish. The final
weights must match the single-process specification (pristine reference.py)."""
import importlib.util
import os
import random
import shutil
import signal
import subprocess
import sys
import time

import pytest
import torch

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from stepcount import stepcount  # noqa: E402
APP = os.environ.get("APP_DIR", "/app")
spec_mod = importlib.util.spec_from_file_location("reference_pristine", os.path.join(HERE, "reference_pristine.py"))
REF = importlib.util.module_from_spec(spec_mod)
spec_mod.loader.exec_module(REF)
WANT = None


def want():
    global WANT
    if WANT is None:
        WANT = REF.train(REF.TOTAL_STEPS)
    return WANT


def launch(world, ckpt, count_file=None):
    return subprocess.Popen([sys.executable, "-m", "torch.distributed.run", "--standalone",
                             f"--nproc_per_node={world}", "train.py", "--ckpt-dir", ckpt], cwd=APP,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, start_new_session=True,
                            env=stepcount.env(count_file) if count_file else None)


def has_checkpoint(ckpt):
    return os.path.isdir(ckpt) and any(f.startswith("ckpt-") and f.endswith(".pt") for f in os.listdir(ckpt))


def check_resumed(count_file, had_checkpoint, what):
    """Added for the Harbor-native version: a job that ignores its checkpoints and retrains from step 0
    also ends with the spec's weights, so a launch that starts with checkpoints present and runs to the
    end must not redo every step."""
    n = stepcount.counts(count_file)[("0", "step")]
    assert not had_checkpoint or n < REF.TOTAL_STEPS, \
        f"{what}: rank 0 ran {n} optimizer steps with checkpoints present: it retrained instead of resuming"


def churn(seed, tmp):
    rng = random.Random(seed)
    ckpt = os.path.join(tmp, f"ckpt-{seed}")
    shutil.rmtree(ckpt, ignore_errors=True)
    history = []
    for i in range(rng.randint(3, 6)):
        w = rng.choice([2, 3, 4, 5])
        had, count_file = has_checkpoint(ckpt), os.path.join(tmp, f"launch-{seed}-{i}.steps")
        final_before = os.path.exists(os.path.join(ckpt, "final.pt"))
        p = launch(w, ckpt, count_file)
        delay = rng.uniform(4.0, 12.0)
        try:
            p.wait(timeout=delay)
            history.append((w, "finished"))
            done = True
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            p.wait()
            history.append((w, f"killed at {delay:.1f}s"))
            done = False
        if not final_before and os.path.exists(os.path.join(ckpt, "final.pt")):  # this launch completed the run
            check_resumed(count_file, had, f"seed {seed}, launch {i} (world {w})")
        if done and os.path.exists(os.path.join(ckpt, "final.pt")):
            break
    if not os.path.exists(os.path.join(ckpt, "final.pt")):
        w = rng.choice([2, 3, 4, 5])
        had, count_file = has_checkpoint(ckpt), os.path.join(tmp, f"launch-{seed}-final.steps")
        p = launch(w, ckpt, count_file)
        try:
            out, _ = p.communicate(timeout=600)
        except subprocess.TimeoutExpired:
            os.killpg(p.pid, signal.SIGKILL)
            pytest.fail(f"seed {seed}: final launch (world {w}) hung; history {history}")
        assert p.returncode == 0, f"seed {seed}: final launch (world {w}) failed; history {history}\n{out[-2500:]}"
        history.append((w, "finished"))
        check_resumed(count_file, had, f"seed {seed}, final launch (world {w})")
    got = torch.load(os.path.join(ckpt, "final.pt"), map_location="cpu", weights_only=False)
    ref = want()
    diff = max((got[k].float() - ref[k].float()).abs().max().item() for k in ref)
    assert diff < 1e-4, f"seed {seed}: final weights differ from the spec by {diff:.3g}; launches {history}"


def test_single_launch_matches_spec(tmp_path):
    ckpt = str(tmp_path / "plain")
    count_file = str(tmp_path / "plain.steps")
    p = launch(3, ckpt, count_file)
    out, _ = p.communicate(timeout=600)
    assert p.returncode == 0, out[-2500:]
    # Added for the Harbor-native version: data-parallel training means every rank computes its share of
    # every step (rank 0 alone running the single-process spec also produces the spec's weights).
    c = stepcount.counts(count_file)
    lazy = {r: c[(str(r), "backward")] for r in range(3) if c[(str(r), "backward")] < REF.TOTAL_STEPS}
    assert not lazy, f"ranks with fewer backward passes than training steps ({REF.TOTAL_STEPS}): {lazy}"
    got = torch.load(os.path.join(ckpt, "final.pt"), map_location="cpu", weights_only=False)
    diff = max((got[k].float() - want()[k].float()).abs().max().item() for k in want())
    assert diff < 1e-4, f"world 3, no failures: differs from the spec by {diff:.3g}"


def test_relaunch_resumes_from_checkpoint(tmp_path):
    """Added for the Harbor-native version: kill a launch as soon as its first checkpoint appears, relaunch
    with another world size, and require the relaunch to continue (fewer optimizer steps than the whole
    run) and still match the spec. A job that ignores its checkpoints passes the churn tests whenever a
    launch happens to finish the whole run on its own."""
    ckpt = str(tmp_path / "resume")
    p = launch(2, ckpt)
    deadline = time.time() + 300
    while p.poll() is None and time.time() < deadline and not has_checkpoint(ckpt):
        time.sleep(0.01)
    if p.poll() is None:
        os.killpg(p.pid, signal.SIGKILL)
    p.wait()
    assert has_checkpoint(ckpt), "no ckpt-*.pt was written before the first launch ended"
    assert not os.path.exists(os.path.join(ckpt, "final.pt")), "the first launch finished before it could be killed"
    count_file = str(tmp_path / "relaunch.steps")
    p = launch(3, ckpt, count_file)
    out, _ = p.communicate(timeout=600)
    assert p.returncode == 0, out[-2500:]
    check_resumed(count_file, True, "relaunch after a kill at the first checkpoint (world 2 -> 3)")
    got = torch.load(os.path.join(ckpt, "final.pt"), map_location="cpu", weights_only=False)
    diff = max((got[k].float() - want()[k].float()).abs().max().item() for k in want())
    assert diff < 1e-4, f"after the relaunch, final weights differ from the spec by {diff:.3g}"


@pytest.mark.parametrize("seed", [101, 202, 303])
def test_churn(seed, tmp_path):
    churn(seed, str(tmp_path))
