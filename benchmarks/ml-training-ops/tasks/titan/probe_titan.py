"""Feasibility probe: torchtitan (pinned tag) trains the Llama-3 debug model on 2 GPUs in a Modal container.

    TITAN_TAG=v0.2.2 TITAN_TORCH=2.11.0 TITAN_GPU=L4 modal run --env $MODAL_ENVIRONMENT titan/probe_titan.py
"""
import os
import subprocess

import modal

TAG = os.environ.get("TITAN_TAG", "v0.2.2")
TORCH = os.environ.get("TITAN_TORCH", "2.11.0")
GPU = os.environ.get("TITAN_GPU", "L4")

image = (modal.Image.from_registry("nvidia/cuda:12.8.1-devel-ubuntu22.04", add_python="3.11")
         .apt_install("git")
         .pip_install(f"torch=={TORCH}", index_url="https://download.pytorch.org/whl/cu128")
         .run_commands(f"git clone --depth 1 --branch {TAG} https://github.com/pytorch/torchtitan /opt/torchtitan",
                       "cd /opt/torchtitan && pip install -r requirements.txt && pip install -e .")
         .pip_install("torchao"))
app = modal.App("titan-probe", image=image)


@app.function(gpu=f"{GPU}:2", timeout=1800)
def run():
    cmd = ("cd /opt/torchtitan && nvidia-smi -L && python -c 'import torch; print(torch.__version__)' && "
           "export NCCL_P2P_DISABLE=1 NCCL_CUMEM_ENABLE=0 NCCL_NVLS_ENABLE=0 NCCL_DEBUG=WARN; "
           "NGPU=2 CONFIG_FILE=./torchtitan/models/llama3/train_configs/debug_model.toml "
           "timeout 900 ./run_train.sh --training.steps 30 2>&1 | tail -40")
    r = subprocess.run(["bash", "-lc", cmd], capture_output=True, text=True)
    return r.stdout[-6000:] + r.stderr[-2000:]


@app.local_entrypoint()
def main():
    print(run.remote())
