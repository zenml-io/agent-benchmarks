"""Run the fork with different fault subsets on 2 GPUs and compare loss curves.

    modal run --env $MODAL_ENVIRONMENT titan/calibrate_fork.py
"""
import json
import os
import re
import subprocess

import modal

image = (modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11")
         .apt_install("git")
         .pip_install("torch==2.11.0", index_url="https://download.pytorch.org/whl/cu128")
         .run_commands("git clone --depth 1 --branch v0.2.2 https://github.com/pytorch/torchtitan /opt/torchtitan",
                       "cd /opt/torchtitan && pip install -r requirements.txt && pip install -e .")
         .pip_install("torchao")
         .add_local_file(os.path.join(os.path.dirname(os.path.abspath(__file__)), "make_fork.py"), "/opt/make_fork.py"))
app = modal.App("titan-calibrate", image=image)
STEPS = 200
NCCL = "NCCL_P2P_DISABLE=1 NCCL_CUMEM_ENABLE=0 NCCL_NVLS_ENABLE=0"


@app.function(gpu=os.environ.get("TITAN_GPU", "L40S") + ":2", timeout=2400, max_containers=4)
def run_variant(faults: str, steps: int = STEPS):
    import shutil
    import tempfile
    d = os.path.join(tempfile.mkdtemp(), "fork")
    shutil.copytree("/opt/torchtitan", d)
    subprocess.run(["python", "/opt/make_fork.py", d, "--faults", faults], check=True)
    cmd = (f"cd {d} && {NCCL} PYTHONPATH={d} NGPU=2 CONFIG_FILE=./torchtitan/models/llama3/train_configs/debug_model.toml "
           f"./run_train.sh --training.steps {steps} --metrics.disable_color_printing --debug.seed 42 --debug.deterministic "
           f"--lr_scheduler.warmup_steps 10 2>&1")
    r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)
    losses = {int(m.group(1)): float(m.group(2)) for m in re.finditer(r"step:\s*(\d+)\s+loss:\s*([0-9.]+)", r.stdout)}
    return faults, [losses.get(s) for s in range(1, steps + 1)], r.stdout[-1500:] if len(losses) < steps else ""


@app.local_entrypoint()
def main():
    variants = ["", "attn", "loss", "shard", "attn,loss,shard"]
    res = list(run_variant.map(variants))
    base = res[0][1]
    out = {}
    for i, (f, curve, tail) in enumerate(res):
        name = f"{f or 'clean'}#{i}"
        out[name] = curve
        if None in curve:
            print(name, "INCOMPLETE", tail[-800:])
            continue
        d = [abs(a - b) for a, b in zip(curve, base)]
        late = d[150:]
        print(f"{name:20s} final {curve[-1]:.4f}  mean|d| last50 {sum(late) / len(late):.4f}  max|d| {max(d):.4f}")
    json.dump(out, open("titan_calibration.json", "w"))
