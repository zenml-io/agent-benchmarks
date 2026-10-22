"""Replay a SwapBench task with an open model served by vLLM on Modal (the 'endpoint' axis).

  python scripts/open_model.py <config> --tau2 <dir> --tau2-env <venv> --out <dir> [--split test --trials 3]

Same weights, different serving configs: a regression can come from the endpoint, not the model.
Deploys serve_vllm.py from SWAPBENCH_SERVING_DIR (the vLLM-on-Modal server of the infra study, together with its
experiment.py helpers; not part of this benchmark) as app agent-swap-<config> on one GPU in the Modal environment
named by MODAL_ENVIRONMENT, waits until it is fresh, runs tau2
against it (agent = the served model, user simulator as in the task), stops the app, and records GPU
time so $/episode = GPU $/h x wall time / episodes at the run's concurrency.
"""
import argparse
import json
import os
import subprocess
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.environ.get("SWAPBENCH_SERVING_DIR") or sys.exit("set SWAPBENCH_SERVING_DIR to the dir with serve_vllm.py and experiment.py")
MODAL_ENV = ["--env", os.environ["MODAL_ENVIRONMENT"]] if os.environ.get("MODAL_ENVIRONMENT") else []
sys.path.insert(0, REPO)
from experiment import GPU_PRICES, endpoint_from_deploy, wait_gone, wait_ready  # noqa: E402

CONFIGS = {
    # Qwen3.8-27B as in serve_vllm.py COMMON (qwen3_coder tool parser, qwen3 reasoning parser)
    "qwen27b": {"args": {}},
    # the official FP8 checkpoint, a common provider choice
    "qwen27b-fp8": {"args": {}, "model": "Qwen/Qwen3.8-27B-FP8"},
    # a generic tool parser instead of the model's own, a plausible provider misconfiguration
    "qwen27b-hermes": {"args": {"--tool-call-parser": "hermes"}},
    # reasoning switched off in the chat template (cheaper, fewer tokens)
    "qwen27b-nothink": {"args": {"--default-chat-template-kwargs": {"enable_thinking": False}}},
    # FP8 KV cache, another common serving default
    "qwen27b-kvfp8": {"args": {"--kv-cache-dtype": "fp8"}},
    # small MoE (3B active), the cheapest open option
    "moe-a3b": {"args": {}, "model": "Qwen/Qwen3.6-35B-A3B-FP8"},
    # Qwen3.8-27B after rejection-sampling fine-tuning on its own correct fintech conversations
    # (rft/train_lora.py merge writes it to the hf-cache volume)
    "qwen27b-rft": {"args": {}, "model": "/root/.cache/huggingface/swapbench/qwen27b-rft"},
}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("config", choices=CONFIGS)
    ap.add_argument("--tau2", required=True)
    ap.add_argument("--tau2-env", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--split", default="test")
    ap.add_argument("--trials", type=int, default=3)
    ap.add_argument("--concurrency", type=int, default=12)
    ap.add_argument("--gpu", default="H100!")
    ap.add_argument("--user-llm", default="anthropic/claude-haiku-5-5")
    ap.add_argument("--data-dir", help="TAU2_DATA_DIR override (e.g. generated scenarios)")
    ap.add_argument("--splits", help='several splits in one server session, e.g. "train:1 pool:1 test:1" (overrides --split/--trials)')
    ap.add_argument("--data-dirs", help="comma list of fintech data dirs; each split runs once per dir (chunks keep memory low)")
    ap.add_argument("--app-suffix", default="", help="distinct Modal app name when the same config runs twice")
    ap.add_argument("--domain", default="retail")
    ap.add_argument("--nextstep", help="incumbent results.json: also run the next-step replay verifier against this server")
    a = ap.parse_args()
    spec = CONFIGS[a.config]
    app = f"agent-swap-{a.config}{a.app_suffix}"
    env = {**os.environ, "RUN_NAME": f"swap-{a.config}{a.app_suffix}", "VLLM_ARGS": json.dumps(spec["args"]), "GPU": a.gpu,
           "COLUMNS": "400"}
    if spec.get("model"):
        env["MODEL"] = spec["model"]
    plan = [tuple(x.split(":")) for x in a.splits.split()] if a.splits else [(a.split, str(a.trials))]
    os.makedirs(os.path.join(a.out, a.config), exist_ok=True)
    rec = {"config": a.config, "gpu": a.gpu, "gpu_price_per_h": GPU_PRICES[a.gpu], "split": a.splits or a.split, "trials": a.trials,
           "concurrency": a.concurrency, "vllm_args": spec["args"], "model": spec.get("model", "Qwen/Qwen3.8-27B")}
    t0 = time.time()
    base = None
    try:
        dep = subprocess.run(["modal", "deploy", *MODAL_ENV, "--strategy", "recreate",
                              os.path.join(REPO, "serve_vllm.py")], env=env, text=True, capture_output=True, cwd=REPO)
        if dep.returncode:
            raise RuntimeError(dep.stdout[-1500:] + dep.stderr[-1500:])
        base = endpoint_from_deploy(dep.stdout + dep.stderr, app)
        rec["startup_s"] = wait_ready(base, 2400)
        run_env = {**os.environ, "ANTHROPIC_API_KEY": os.environ.get("EVAL_ANTHROPIC_API_KEY", "")}
        if a.data_dir:
            run_env["TAU2_DATA_DIR"] = a.data_dir
        agent_args = json.dumps({"api_base": f"{base}/v1", "api_key": "not-used"})
        if a.nextstep:
            t_ns = time.time()
            ns = subprocess.run([os.path.join(a.tau2_env, "bin", "python"), "-m", "swapbench.nextstep", a.nextstep,
                                 "--model", "openai/agent-model", "--llm-args", agent_args,
                                 "--out", os.path.join(a.out, a.config, "nextstep.json"), "--domain", a.domain],
                                cwd=os.path.dirname(HERE), env=run_env, capture_output=True, text=True, timeout=3600)
            rec["nextstep"] = (ns.stdout.strip().splitlines() or [ns.stderr[-500:]])[-1]
            rec["nextstep_s"] = time.time() - t_ns
        rec["runs"] = {}
        dirs = a.data_dirs.split(",") if a.data_dirs else [None]
        plan = [(split, trials, d) for d in dirs for split, trials in plan]
        for split, trials, ddir in plan:
            if ddir:
                run_env["SWAPBENCH_FINTECH_DIR"] = ddir
            out = os.path.join(a.out, a.config, split + (f"_{os.path.basename(ddir)}" if ddir else ""))
            t_run = time.time()
            tau2bin = os.path.join(a.tau2_env, "bin", "tau2")
            if a.domain == "fintech" or a.domain.endswith("_gen"):  # our domains, registered by the tau2x wrapper
                tau2bin = os.path.join(HERE, "tau2x")
                run_env["TAU2X_PYTHON"] = os.path.join(a.tau2_env, "bin", "python")
            cmd = [tau2bin, "run", "-d", a.domain, "--agent-llm", "openai/agent-model",
                   "--agent-llm-args", agent_args, "--user-llm", a.user_llm, "--user-llm-args", "{}",
                   "--task-split-name", split, "--num-trials", trials, "--max-concurrency", str(a.concurrency),
                   "--save-to", out, "--log-level", "ERROR"]
            with open(out + ".log", "w") as log:
                rc = subprocess.run(cmd, cwd=a.tau2, env=run_env, stdout=log, stderr=subprocess.STDOUT,
                                    timeout=4 * 3600).returncode
            rec["runs"][os.path.basename(out)] = {"rc": rc, "run_s": time.time() - t_run}
        rec["run_s"] = sum(r["run_s"] for r in rec["runs"].values())
    except BaseException as e:  # noqa: BLE001 - record, then always stop the server
        rec["error"] = f"{type(e).__name__}: {e}"[:2000]
    finally:
        subprocess.run(["modal", "app", "stop", *MODAL_ENV, "-y", app], capture_output=True)
        if base:
            try:
                wait_gone(base)
            except Exception:
                pass
    rec["up_s"] = time.time() - t0
    rec["gpu_cost_usd"] = rec["up_s"] / 3600 * rec["gpu_price_per_h"]
    with open(os.path.join(a.out, "runs.jsonl"), "a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec))


if __name__ == "__main__":
    main()
