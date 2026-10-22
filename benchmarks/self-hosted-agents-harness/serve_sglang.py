"""
Serve one open model on Modal with SGLang, as the counterpart of serve_vllm.py.

    RUN_NAME=<name>  SGLANG_ARGS='{"--mamba-full-memory-ratio": "0.5"}'  [MODEL=...]  [GPU=...]
    modal deploy --env $MODAL_ENVIRONMENT --strategy recreate serve_sglang.py

Same served model name ("agent-model"), port, context length, reasoning and tool-call
parsers and request cap as serve_vllm.py, so only the engine (and SGLANG_ARGS) differs.
"""

import json
import os
import subprocess
import threading

import modal

# Pinned; v0.5.20 (Sept 18 2026) is the newest release more than two weeks old.
SGLANG_IMAGE = "lmsysorg/sglang:v0.5.20"

MODEL = os.environ.get("MODEL", "Qwen/Qwen3.8-27B")
GPU = os.environ.get("GPU", "H100!")
RUN_NAME = os.environ.get("RUN_NAME", "sglang")
SGLANG_ARGS = json.loads(os.environ.get("SGLANG_ARGS", "{}"))
PORT = 8000

# The equivalents of serve_vllm.COMMON. Everything else stays at SGLang's defaults
# (stock vs stock): RadixAttention prefix cache on, default memory split.
COMMON = {
    "--host": "0.0.0.0",
    "--port": str(PORT),
    "--served-model-name": "agent-model",
    "--context-length": "65536",
    "--reasoning-parser": "qwen3",
    "--tool-call-parser": "qwen3_coder",
    "--max-running-requests": "128",
    # Report cached prompt tokens in usage (vLLM: --enable-prompt-tokens-details).
    "--enable-cache-report": True,
    # Prometheus /metrics (vLLM serves it by default).
    "--enable-metrics": True,
}


def to_cli(args: dict) -> list[str]:
    out = []
    for flag, value in args.items():
        if value is None or value is False:
            continue
        out.append(flag)
        if value is not True:
            out.append(json.dumps(value) if isinstance(value, (dict, list)) else str(value))
    return out


image = (
    modal.Image.from_registry(SGLANG_IMAGE)
    .entrypoint([])
    .env({"MODEL": MODEL, "RUN_NAME": RUN_NAME, "SGLANG_ARGS": json.dumps(SGLANG_ARGS),
          "HF_HUB_ENABLE_HF_TRANSFER": "1",
          # The SGLang image ships files in /root/.cache/huggingface, and Modal can't mount a
          # volume on a non-empty path (the container crash-loops), so mount elsewhere.
          "HF_HOME": "/hf-cache"})
)

# Same weights volume as serve_vllm.py, so the model isn't downloaded again.
hf_cache = modal.Volume.from_name(os.environ.get("MODAL_HF_CACHE_VOLUME", "hf-cache"), create_if_missing=True)

app = modal.App(f"{os.environ.get('MODAL_APP_PREFIX', 'agent')}-{RUN_NAME}")


@app.server(
    image=image,
    gpu=GPU,
    port=PORT,
    min_containers=1,
    max_containers=1,
    startup_timeout=30 * 60,
    scaledown_window=5 * 60,
    unauthenticated=True,
    volumes={"/hf-cache": hf_cache},
)
class Server:
    @modal.enter()
    def start(self):
        cmd = ["python3", "-m", "sglang.launch_server", "--model-path", MODEL, *to_cli(COMMON), *to_cli(SGLANG_ARGS)]
        print("Starting:", " ".join(cmd))
        self.proc = subprocess.Popen(cmd)

        # If the server dies (e.g. a startup error), end the container instead of idling on
        # a GPU until the startup timeout: Modal keeps billing a container whose port is dead.
        def exit_with_server():
            code = self.proc.wait()
            print(f"sglang exited with code {code}; stopping the container")
            os._exit(1)

        threading.Thread(target=exit_with_server, daemon=True).start()

    @modal.exit()
    def stop(self):
        self.proc.terminate()
