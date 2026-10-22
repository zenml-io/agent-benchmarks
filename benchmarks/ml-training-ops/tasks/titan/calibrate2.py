"""Calibrate the slow-divergence task: clean vs data fault vs env fault vs both, on 2 GPUs.

    TITAN_STEPS=50 modal run --env $MODAL_ENVIRONMENT titan/calibrate2.py::probe     # step time
    modal run --env $MODAL_ENVIRONMENT titan/calibrate2.py                           # full calibration
"""
import json
import os
import re
import subprocess
import time

import modal

HERE = os.path.dirname(os.path.abspath(__file__))
image = (modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11")
         .apt_install("git")
         .pip_install("torch==2.11.0", index_url="https://download.pytorch.org/whl/cu128")
         .run_commands("git clone --depth 1 --branch v0.2.2 https://github.com/pytorch/torchtitan /opt/torchtitan",
                       "cd /opt/torchtitan && pip install -r requirements.txt && pip install -e .")
         .pip_install("torchao")
         .add_local_file(os.path.join(HERE, "make_fork.py"), "/opt/make_fork.py")
         .add_local_file(os.path.join(HERE, "make_fork2.py"), "/opt/make_fork2.py")
         .add_local_file(os.path.join(HERE, "make_corpus.py"), "/opt/make_corpus.py"))
app = modal.App("titan-calibrate2", image=image)
NCCL = "NCCL_P2P_DISABLE=1 NCCL_CUMEM_ENABLE=0 NCCL_NVLS_ENABLE=0"
STEPS = int(os.environ.get("TITAN_STEPS", "1000"))


@app.function(gpu="L40S:2", timeout=3600, max_containers=4)
def run(name: str, exclude: bool, theta_leak: bool, steps: int):
    import shutil
    import tempfile
    d = os.path.join(tempfile.mkdtemp(), "fork")
    shutil.copytree("/opt/torchtitan", d)
    subprocess.run(["python", "/opt/make_fork2.py", d], check=True, capture_output=True)
    if not os.path.exists("/data/corpus/part-0000.jsonl"):
        subprocess.run(["python", "/opt/make_corpus.py", f"{d}/tests/assets/c4_test/data.json", "/data/corpus"], check=True)
    env = "TITAN_ROPE_THETA=10000 " if theta_leak else ""
    excl = '--training.exclude_shards part-0016.jsonl' if exclude else ""
    cmd = (f"cd {d} && {NCCL} {env} PYTHONPATH={d} NGPU=2 CONFIG_FILE=./torchtitan/models/llama3/train_configs/internal_200m.toml "
           f"./run_train.sh --training.steps {steps} {excl} 2>&1")
    t = time.time()
    r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)
    losses = {int(m.group(1)): float(m.group(2)) for m in re.finditer(r"step:\s*(\d+)\s+loss:\s*([0-9.]+)", r.stdout)}
    return name, [losses.get(s) for s in range(1, steps + 1)], round(time.time() - t), (r.stdout[-2500:] if len(losses) < steps else "")


@app.local_entrypoint()
def probe():
    name, curve, secs, tail = run.remote("clean", True, False, STEPS)
    print(name, "seconds", secs, "first", curve[:3], "last", curve[-3:])
    if tail:
        print(tail)


@app.local_entrypoint()
def main():
    variants = [("clean", True, False), ("clean", True, False), ("data", False, False), ("theta", True, True), ("both", False, True)]
    res = list(run.starmap([(n, e, t, STEPS) for n, e, t in variants]))
    base = res[0][1]
    out = {}
    for i, (name, curve, secs, tail) in enumerate(res):
        key = f"{name}#{i}"
        out[key] = curve
        if None in curve:
            print(key, "INCOMPLETE", tail[-600:])
            continue
        dd = [abs(a - b) for a, b in zip(curve, base)]
        first = next((s + 1 for s, x in enumerate(dd) if x > 0.005), None)
        print(f"{key:10s} {secs}s final {curve[-1]:.4f} mean|d| last100 {sum(dd[-100:]) / 100:.4f} max|d| {max(dd):.4f} first step >0.005: {first}")
    json.dump(out, open(os.path.join(HERE, "calibration_slow.json"), "w"))
