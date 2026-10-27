"""
Serve Qwen/Qwen3.8-27B on one Modal H100 with vLLM, as the model name "agent-model".

A fixed copy of ../../../self-hosted-agents-harness/serve_vllm.py with its default ("defaults") config:
the same image, vLLM version and flags that decision-agents used for case-file extraction. Deploy and
stop it with `extract.py up` / `extract.py down` (or `extract.py all`), which run

    modal deploy --env $MODAL_ENVIRONMENT --strategy recreate harness/extract/serve.py
    modal app stop --env $MODAL_ENVIRONMENT -y $MODAL_APP_PREFIX-claims-extract

Volume and app names come from MODAL_HF_CACHE_VOLUME, MODAL_VLLM_CACHE_VOLUME,
MODAL_FLASHINFER_CACHE_VOLUME and MODAL_APP_PREFIX (defaults below).
"""

import os
import subprocess

import modal

VLLM_VERSION = "0.31.0"
MODEL = "Qwen/Qwen3.8-27B"
PORT = 8000
APP_NAME = f"{os.environ.get('MODAL_APP_PREFIX', 'agent')}-claims-extract"

FLAGS = [
    "--host", "0.0.0.0",
    "--port", str(PORT),
    "--served-model-name", "agent-model",
    "--max-model-len", "65536",
    "--reasoning-parser", "qwen3",
    "--enable-auto-tool-choice",
    "--tool-call-parser", "qwen3_coder",
    # vLLM's H100 default (1024) exceeds the Mamba state blocks this hybrid model fits next to its
    # weights, and start-up fails.
    "--max-num-seqs", "128",
    "--enable-prompt-tokens-details",
    "--language-model-only",
]

image = (
    # A CUDA devel image: on H100 vLLM JIT-compiles a FlashInfer kernel for this model's
    # linear-attention layers at start-up, and that needs nvcc.
    modal.Image.from_registry("nvidia/cuda:13.0.3-devel-ubuntu24.04", add_python="3.12")
    .uv_pip_install(f"vllm=={VLLM_VERSION}", "transformers>=5.8.0", "huggingface_hub[hf_transfer]")
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1"})
)

hf_cache = modal.Volume.from_name(os.environ.get("MODAL_HF_CACHE_VOLUME", "hf-cache"), create_if_missing=True)
vllm_cache = modal.Volume.from_name(os.environ.get("MODAL_VLLM_CACHE_VOLUME", "vllm-cache"), create_if_missing=True)
flashinfer_cache = modal.Volume.from_name(os.environ.get("MODAL_FLASHINFER_CACHE_VOLUME", "flashinfer-cache"),
                                          create_if_missing=True)

app = modal.App(APP_NAME)


@app.server(
    image=image,
    # "!" stops Modal from silently upgrading the request to an H200.
    gpu="H100!",
    port=PORT,
    # One GPU from deploy until `modal app stop`: a second container would double the cost.
    min_containers=1,
    max_containers=1,
    startup_timeout=30 * 60,
    scaledown_window=5 * 60,
    # The extraction client sends no auth headers; the URL is only live while extraction runs.
    unauthenticated=True,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
        "/root/.cache/flashinfer": flashinfer_cache,
    },
)
class Server:
    @modal.enter()
    def start(self) -> None:
        cmd = ["vllm", "serve", MODEL, *FLAGS]
        print("Starting:", " ".join(cmd))
        self.proc = subprocess.Popen(cmd)

    @modal.exit()
    def stop(self) -> None:
        self.proc.terminate()
