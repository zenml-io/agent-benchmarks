"""
Serve one open model on Modal with a given set of vLLM flags.

You normally don't call this directly: experiment.py deploys it with
    RUN_NAME=<config>  VLLM_ARGS='{"--kv-cache-dtype": "fp8"}'  [MODEL=...]  [GPU=...]
    modal deploy --env $MODAL_ENVIRONMENT --strategy recreate serve_vllm.py
and stops it with `modal app stop --env $MODAL_ENVIRONMENT -y $MODAL_APP_PREFIX-<config>` after each run.
Volume and app names come from MODAL_HF_CACHE_VOLUME, MODAL_VLLM_CACHE_VOLUME,
MODAL_FLASHINFER_CACHE_VOLUME and MODAL_APP_PREFIX (defaults below).

Uses @app.server, the pattern in Modal's current vLLM example (Modal 1.6). The
served model name is always "agent-model". experiment.py reads the endpoint URL
from the deploy output.
"""

import json
import os
import subprocess

import modal

# Pinned so every run uses the same engine and the same defaults.
VLLM_VERSION = "0.31.0"

# Qwen3.8-27B (Aug 2026): dense 27B, public (no HF token needed), hybrid Gated
# DeltaNet + attention. ~51 GiB in BF16 on an H100's 80 GiB, so KV cache is tight.
MODEL = os.environ.get("MODEL", "Qwen/Qwen3.8-27B")
# "!" stops Modal from silently upgrading an H100 request to an H200, which would
# give some runs more KV cache than others.
GPU = os.environ.get("GPU", "H100!")
RUN_NAME = os.environ.get("RUN_NAME", "defaults")
def _unnest(args: dict) -> dict:
    """Flag values that are themselves JSON (e.g. --speculative-config) become objects.
    The image env is written as a Dockerfile ENV line, which eats backslashes, so a
    JSON string inside the JSON (escaped quotes) arrives broken and the container
    crash-loops. Nested objects need no escapes; to_cli turns them back into JSON."""
    out = {}
    for flag, value in args.items():
        if isinstance(value, str) and value.lstrip().startswith(("{", "[")):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                pass
        out[flag] = value
    return out


VLLM_ARGS = _unnest(json.loads(os.environ.get("VLLM_ARGS", "{}")))
PORT = 8000

# Held constant across every config so only VLLM_ARGS (and MODEL) vary.
COMMON = {
    "--host": "0.0.0.0",
    "--port": str(PORT),
    "--served-model-name": "agent-model",
    "--max-model-len": "65536",
    "--reasoning-parser": "qwen3",
    "--enable-auto-tool-choice": True,
    "--tool-call-parser": "qwen3_coder",
    # Required for this hybrid model: vLLM's default (1024 on H100) exceeds the
    # Mamba state blocks that fit next to the weights, and startup fails. 128 is
    # well above the highest concurrency we test (32 agents).
    "--max-num-seqs": "128",
    # Report cached prompt tokens in usage, so the report can show prefix-cache reuse.
    "--enable-prompt-tokens-details": True,
    # The agent is text-only. Skipping the vision encoder frees VRAM for KV cache
    # (recommended in the vLLM Qwen3.8-27B recipe).
    "--language-model-only": True,
}


def to_cli(args: dict) -> list[str]:
    """{"--flag": "v", "--switch": True, "--skip": None} -> ["--flag", "v", "--switch"]"""
    out = []
    for flag, value in args.items():
        if value is None or value is False:
            continue
        out.append(flag)
        if isinstance(value, (dict, list)):
            out.append(json.dumps(value))
        elif value is not True:
            out.append(str(value))
    return out


image = (
    # CUDA *devel* image (has nvcc), matching vLLM 0.31's own build (CUDA 13.0.3,
    # Ubuntu 24.04, Python 3.12). On H100, vLLM's default kernel for this model's
    # linear-attention layers is FlashInfer, which is JIT-compiled at startup and
    # crashes without nvcc. Keeping that default (instead of --gdn-prefill-backend
    # triton) keeps "defaults" honest.
    modal.Image.from_registry("nvidia/cuda:13.0.3-devel-ubuntu24.04", add_python="3.12")
    # transformers>=5.8.0 is a prerequisite in the vLLM Qwen3.8 recipe.
    .uv_pip_install(f"vllm=={VLLM_VERSION}", "transformers>=5.8.0", "huggingface_hub[hf_transfer]")
    .env(
        {
            "HF_HUB_ENABLE_HF_TRANSFER": "1",
            "MODEL": MODEL,
            "RUN_NAME": RUN_NAME,
            "VLLM_ARGS": json.dumps(VLLM_ARGS),
        }
    )
)

# Volumes are per Modal environment: the first start in a new environment
# downloads the weights. The default model is public; for a gated model add
# secrets=[modal.Secret.from_name("huggingface-secret")] below.
hf_cache = modal.Volume.from_name(os.environ.get("MODAL_HF_CACHE_VOLUME", "hf-cache"), create_if_missing=True)
vllm_cache = modal.Volume.from_name(os.environ.get("MODAL_VLLM_CACHE_VOLUME", "vllm-cache"), create_if_missing=True)
# FlashInfer's JIT-compiled kernels, so only the first start pays for compiling.
# Startup is reported separately from run cost, so this doesn't affect cost numbers.
flashinfer_cache = modal.Volume.from_name(os.environ.get("MODAL_FLASHINFER_CACHE_VOLUME", "flashinfer-cache"),
                                          create_if_missing=True)

app = modal.App(f"{os.environ.get('MODAL_APP_PREFIX', 'agent')}-{RUN_NAME}")


@app.server(
    image=image,
    gpu=GPU,
    port=PORT,
    # Exactly one GPU per run, started at deploy time and kept until experiment.py
    # stops the app. A second container would double cost and split the KV cache.
    min_containers=1,
    max_containers=1,
    # target_concurrency / max_concurrency unset: no concurrency-based scale-out and
    # no per-container request cap; vLLM queues and batches requests itself.
    startup_timeout=30 * 60,
    scaledown_window=5 * 60,
    # terminus-2 can't send Modal proxy-auth headers. The URL is only live while a
    # run is going; experiment.py stops the app as soon as Harbor finishes.
    unauthenticated=True,
    volumes={
        "/root/.cache/huggingface": hf_cache,
        "/root/.cache/vllm": vllm_cache,
        "/root/.cache/flashinfer": flashinfer_cache,
    },
)
class Server:
    @modal.enter()
    def start(self):
        cmd = ["vllm", "serve", MODEL, *to_cli(COMMON), *to_cli(VLLM_ARGS)]
        print("Starting:", " ".join(cmd))
        self.proc = subprocess.Popen(cmd)

    @modal.exit()
    def stop(self):
        self.proc.terminate()
