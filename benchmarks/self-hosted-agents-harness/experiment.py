"""
Agentic serving experiment: what decides what a coding agent costs to run on your
own GPU, the agent harness or how you serve the model?

For each harness x serving config x concurrency x repeat, this deploys the model on
Modal (serve_vllm.py), runs the harness through Harbor on the tasks in tasks.json,
stops the server, and appends one record to attempts.jsonl: tasks solved, GPU
time, cost and startup time. report.md is built only from attempts.jsonl.

Serving configs (each is one change vs. defaults, except the placeholder):
  defaults         vLLM 0.31 defaults (prefix caching and chunked prefill already on)
  no-prefix-cache  prefix caching off: what is KV reuse across agent turns worth?
  kv-fp8           KV cache stored in fp8: more resident sessions vs. quality
  weights-fp8      Qwen's official FP8 checkpoint instead of BF16
  recommended      PLACEHOLDER for a vLLM expert; skipped until filled in

Every run starts a fresh server, so no run inherits a warm prefix cache from the
previous one. Startup time is recorded separately from the cost of the run.

Commands
  python experiment.py quickcheck              # defaults vs no-prefix-cache, c=16, first 8 tasks, every harness
  python experiment.py run --harness terminus-2 --config kv-fp8 --concurrency 16 --rep 0
  python experiment.py matrix                  # harness x config x concurrency x repeat, resumable
  python experiment.py report
Global options go before the subcommand: --dry-run prints the commands without
running them; --harnesses picks harnesses for quickcheck/matrix.
"""

import argparse
import json
import os
import re
import signal
import statistics
import subprocess
import sys
import time
import urllib.request
from datetime import datetime
from pathlib import Path

import vllm_metrics

HERE = Path(__file__).resolve().parent
# The benchmark directory (task lists, attempts.jsonl, jobs/, report.md) is separate from
# this shared harness: BENCH_DIR, or the current directory.
BENCH = Path(os.environ.get("BENCH_DIR") or Path.cwd()).resolve()
ATTEMPTS = Path(os.environ.get("ATTEMPTS_FILE") or BENCH / "attempts.jsonl")
TASKS = BENCH / "tasks.json"
JOBS_DIR = BENCH / "jobs"
REPORT = BENCH / "report.md"
PAUSE = BENCH / "PAUSE"
# Modal app names are <prefix>-<config>[-s<slot>]; serve_vllm.py / serve_sglang.py read the same variable.
APP_PREFIX = os.environ.get("MODAL_APP_PREFIX", "agent")

MAX_MODEL_LEN = 65536  # must match --max-model-len in serve_vllm.py

# A config is extra vLLM flags (None = omit / bare switch = True) and optionally a
# different model checkpoint. Model and flags held constant across configs live
# in serve_vllm.py (MODEL, COMMON).
CONFIGS = {
    "defaults": {"args": {}},
    "no-prefix-cache": {"args": {"--no-enable-prefix-caching": True}},
    "kv-fp8": {"args": {"--kv-cache-dtype": "fp8"}},
    # Qwen publishes an official FP8 checkpoint of the same model; that's what a
    # team would actually deploy, so it's used instead of on-the-fly quantization.
    "weights-fp8": {"args": {}, "model": "Qwen/Qwen3.8-27B-FP8"},
    # Speculative decoding with the checkpoint's own multi-token-prediction layer
    # (Qwen3.8 ships one, trained for multiple steps; vLLM 0.31 method "mtp").
    "spec-mtp": {"args": {"--speculative-config": json.dumps({"method": "mtp", "num_speculative_tokens": 2})}},
    # Reasoning off by default (requests can still turn it on). The model spends most
    # of its decode time thinking, so this is the biggest decode-volume lever.
    "no-thinking": {"args": {"--default-chat-template-kwargs": json.dumps({"enable_thinking": False})}},
    # The three decode-side levers together: FP8 weights + FP8 KV cache + MTP.
    "stacked": {"args": {"--kv-cache-dtype": "fp8",
                         "--speculative-config": json.dumps({"method": "mtp", "num_speculative_tokens": 2})},
                "model": "Qwen/Qwen3.8-27B-FP8"},
    # Same server as defaults on an H200 (141 GB, ~1.4x the memory bandwidth).
    "h200": {"args": {}, "gpu": "H200"},  # no "!" form exists for H200
    # Blackwell: same bandwidth as B300 (~8 TB/s) at a lower price; a 27B model at 32
    # agents doesn't need B300's extra memory. Plain "B200" (no "+") so Modal can't
    # substitute a B300.
    "b200": {"args": {}, "gpu": "B200"},
    # spec-mtp where there's KV headroom (on H100 at c=32 the KV cache is full and spec
    # decoding made preemptions 5x worse): does the same knob flip from hurting to helping?
    "h200-spec-mtp": {"args": {"--speculative-config": json.dumps({"method": "mtp", "num_speculative_tokens": 2})},
                      "gpu": "H200"},
    # A second model with the opposite profile: MoE, 36B total / 3B active per token (fast
    # decode) and a tiny KV cache (2 KV heads, full attention in 1 of 4 layers). FP8 checkpoint
    # (~36 GB) on the same H100. Does the harness x infra coupling change with the model?
    "moe-a3b": {"args": {}, "model": "Qwen/Qwen3.6-35B-A3B-FP8"},
    # Agent-side, not serving: defaults server, agents get 2x the task's time limit.
    # Shows how much the wall-clock limit caps success on this hardware.
    "defaults-2x-time": {"args": {}, "agent_timeout_multiplier": 2.0},
    # "Practically unlimited" (60-80 min per task): real deployments rarely cut an agent off
    # at 15 min, so this shows the uncapped solve rate, time per solve and cost per solve.
    # Harbor's sandbox cap (2 h) still covers it.
    "defaults-4x-time": {"args": {}, "agent_timeout_multiplier": 4.0},
    # Server-side cap on generated tokens per call (vLLM uses it as the default max_tokens
    # when a request sets none). On the hard ML-ops tasks some calls never returned within
    # the agent's time limit: does a cap turn runaway generations into usable turns?
    "max-out-8k": {"args": {"--override-generation-config": json.dumps({"max_new_tokens": 8192})}},
    # Dose curve for the output cap (hard ML-ops tasks): where does capping stop helping?
    "max-out-4k": {"args": {"--override-generation-config": json.dumps({"max_new_tokens": 4096})}},
    "max-out-16k": {"args": {"--override-generation-config": json.dumps({"max_new_tokens": 16384})}},
    # PLACEHOLDER: a vLLM practitioner should fill this in for this model + GPU.
    # While args is None, matrix skips it and `run --config recommended` refuses.
    "recommended": {"args": None},
}

# Agent harnesses, all built into Harbor 0.24 and all pointed at our server as an
# OpenAI-compatible endpoint with model "openai/agent-model". Every harness also
# gets OPENAI_BASE_URL / OPENAI_API_KEY in its environment; "kwargs" are extra
# Harbor --ak options ({BASE} is replaced with the server URL). Installed agents
# run inside the task sandbox and are pinned so a new release can't change results.
_MODEL_INFO = {"max_input_tokens": MAX_MODEL_LEN, "max_output_tokens": 16384,
               "input_cost_per_token": 0, "output_cost_per_token": 0}
HARNESSES = {
    # Harbor's own agent; runs on this machine (not in the sandbox), drives tmux.
    # Versioned with Harbor itself.
    "terminus-2": {"version": "harbor-0.24.0",
                   "kwargs": {"api_base": "{BASE}/v1", "model_info": _MODEL_INFO}},
    # Minimal bash-only agent from the SWE-bench team; actions parsed from text.
    "mini-swe-agent": {"version": "2.4.6",
                       "kwargs": {"litellm_model_registry": {"openai/agent-model": _MODEL_INFO}}},
    # Qwen's own coding CLI (native tool calls), i.e. the model vendor's harness.
    "qwen-coder": {"version": "0.25.0", "kwargs": {"base_url": "{BASE}/v1", "api_key": "not-used"}},
    # OpenHands; native tool calls, heavier install inside each sandbox.
    "openhands": {"version": "1.11.0",
                  "kwargs": {"api_base": "{BASE}/v1", "model_info": _MODEL_INFO}},
    # OpenCode (sst/anomalyco), native tool calls. Harbor only sets a base URL for its
    # built-in openai provider, which talks the Responses API; this overlay registers
    # our server as a plain OpenAI-compatible (chat completions) provider instead.
    "opencode": {"version": "1.18.35", "model": "vllm/agent-model",
                 "kwargs": {"opencode_config": {"provider": {"vllm": {
                     "npm": "@ai-sdk/openai-compatible", "name": "vLLM",
                     "options": {"baseURL": "{BASE}/v1", "apiKey": "not-used"},
                     "models": {"agent-model": {"limit": {"context": MAX_MODEL_LEN, "output": 16384}}}}}}}},
    # Pi (pi-coding-agent), minimal tool-calling agent. Harbor writes a custom
    # provider for our endpoint; model_api picks the chat-completions API.
    "pi": {"version": "1.1.0", "kwargs": {"model_api": "openai-completions"}},
}
DEFAULT_HARNESSES = ["terminus-2", "mini-swe-agent"]

# A config whose mean success rate is more than this many points below the same
# harness's defaults (same concurrency) "fails quality gate" and is not ranked.
QUALITY_GATE_PTS = 5.0

# A tool call matching this reached for the benchmark itself (its repos or site),
# e.g. to read a task's expected answer. The model knows Terminal-Bench and the
# sandboxes have internet access. Note: the task salt "0000TBENCH-SALT" must not match.
BENCHMARK_LOOKUP = re.compile(r"terminal[-_ ]?bench|laude-institute|harbor-framework|\bt-bench\b|tbench\.ai"
                              r"|gaia[-_ ]?benchmark|datasets/gaia|gaia[-_ ]validation|gaia.{0,20}answers", re.I)

SANDBOX_TIMEOUT_S = 2 * 60 * 60

# $/GPU-hour, `modal billing rates` (Oct 2026). A config may pin its own GPU.
GPU_PRICES = {"H100!": 3.95, "H100": 3.95, "H200!": 4.54, "H200": 4.54, "B200": 6.25}

QUICKCHECK = {"configs": ["defaults", "no-prefix-cache"], "concurrency": 16, "n_tasks": 8}


# ---------------------------------------------------------------- helpers

def load_tasks() -> dict:
    if not TASKS.exists():
        sys.exit(f"Missing {TASKS.name}.")
    return json.loads(TASKS.read_text())


def task_set_name(base: str = "full") -> str:
    """tasks.json -> base ("full"/"quick"); tasks_<name>.json -> <name> (e.g. "gaia")."""
    return base if TASKS.name == "tasks.json" else TASKS.stem.removeprefix("tasks_")


def read_attempts() -> list[dict]:
    if not ATTEMPTS.exists():
        return []
    rows = [json.loads(l) for l in ATTEMPTS.read_text().splitlines() if l.strip()]
    for r in rows:
        r.setdefault("harness", "terminus-2")  # records from before the harness axis
    return rows


def run_key(harness: str, config: str, concurrency: int, rep: int, task_set: str) -> tuple:
    return (harness, config, concurrency, rep, task_set)


def completed_keys() -> set:
    """Runs that finished cleanly. Failed runs are not here, so matrix retries them."""
    return {run_key(r["harness"], r["config"], r["concurrency"], r["rep"], r["task_set"])
            for r in read_attempts() if r.get("valid")}


def spent_usd(attempts: list[dict]) -> float:
    """Everything billed so far: whole server uptime (startup + run + stop) per run."""
    return sum((r.get("up_s") or 0) / 3600 * r.get("gpu_price_per_h", 0) for r in attempts)


def check_budget(a):
    """Refuse to start another run once recorded spend + spend outside attempts.jsonl
    (--spent-before) is within --run-reserve of --budget."""
    spent = spent_usd(read_attempts()) + a.spent_before
    if spent + a.run_reserve > a.budget:
        sys.exit(f"Budget stop: ${spent:.2f} spent of ${a.budget:.2f}; next run could need "
                 f"~${a.run_reserve:.2f}.")
    print(f"Budget: ${spent:.2f} of ${a.budget:.2f} spent.", flush=True)


def endpoint_from_deploy(output: str, app_name: str) -> str:
    """modal deploy prints the endpoint URL; its host depends on the workspace and
    the environment's web suffix, so read it instead of building it."""
    output = re.sub(r"\x1b\[[0-9;]*m", "", output)  # strip Rich colour codes
    output = re.sub(r"\n[ \t]+", "", output)  # Rich wraps long URLs onto indented lines
    urls = re.findall(r"https://[a-z0-9.-]+\.modal\.(?:run|direct)", output)
    match = [u for u in urls if app_name in u] or urls
    if not match:
        raise RuntimeError(f"No endpoint URL in `modal deploy` output:\n{output[-2000:]}")
    return match[-1]


def is_fresh(metrics: dict) -> bool:
    """A server this run just started has served no tokens yet."""
    return not metrics.get("prompt_tokens_total") and not metrics.get("generation_tokens_total")


def wait_ready(base: str, timeout_s: int, poll_s: float = 15) -> float:
    """Poll until a *fresh* vLLM answers. Returns seconds waited.

    `modal app stop` returns before the old container is gone, so right after a deploy
    the URL can still be answered by the previous run's server. That one has already
    served tokens; the new one hasn't. (See also wait_gone.)"""
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            with urllib.request.urlopen(f"{base}/v1/models", timeout=30) as r:
                if r.status == 200 and is_fresh(vllm_metrics.fetch(base)):
                    return time.time() - start
        except Exception:
            pass
        time.sleep(poll_s)
    raise TimeoutError(f"{base} not ready after {timeout_s}s")


def wait_gone(base: str, timeout_s: int = 300):
    """After `modal app stop`, wait until the URL stops answering, so the next run's
    deploy doesn't overlap with this container (it still bills while it drains)."""
    start = time.time()
    while time.time() - start < timeout_s:
        try:
            urllib.request.urlopen(f"{base}/v1/models", timeout=10).close()
        except Exception:
            return
        time.sleep(10)


def parse_job(job_dir: Path) -> dict:
    """
    Harbor 0.24 writes jobs/<job-name>/<trial-name>/result.json per task (a
    TrialResult). The job-level jobs/<job-name>/result.json embeds every trial, so
    only the per-trial files are read. Solved = verifier_result.rewards.reward >= 1.
    A trial that crashed before verification counts as attempted and unsolved.
    setup_failed counts trials whose agent never started (e.g. an in-sandbox harness
    install failed): still unsolved, but reported so harnesses compare fairly.
    peeked counts trials whose agent looked up the benchmark (see BENCHMARK_LOOKUP);
    a peeked trial is never counted as solved (peeked_solved: the verifier passed it).
    trials: one compact entry per trial (task, ok, agent seconds, steps, tokens, exception),
    so the report can show where agent time goes and compare configs task by task.
    """
    out = {"attempted": 0, "solved": 0, "errors": 0, "setup_failed": 0,
           "peeked": 0, "peeked_solved": 0,
           "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0, "trials": []}
    for f in sorted(job_dir.glob("*/result.json")):
        try:
            data = json.loads(f.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        out["attempted"] += 1
        rewards = (data.get("verifier_result") or {}).get("rewards") or {}
        reward = rewards.get("reward")
        passed = reward is not None and float(reward) >= 1.0
        peeked = looked_up_benchmark(f.parent / "agent" / "trajectory.json")
        if peeked:
            out["peeked"] += 1
            out["peeked_solved"] += passed
        elif passed:
            out["solved"] += 1
        if data.get("exception_info"):
            out["errors"] += 1
            if data.get("agent_execution") is None:
                out["setup_failed"] += 1
        ctx = data.get("agent_result") or {}
        out["input_tokens"] += ctx.get("n_input_tokens") or 0
        out["cached_tokens"] += ctx.get("n_cache_tokens") or 0
        out["output_tokens"] += ctx.get("n_output_tokens") or 0
        out["trials"].append({
            "task": data.get("task_name") or f.parent.name.rsplit("__", 1)[0],
            # Whole trial (sandbox setup to verifier): what the sandbox bills for.
            "wall_s": _seconds({"started_at": data.get("started_at"), "finished_at": data.get("finished_at")}),
            "ok": passed and not peeked,
            "agent_s": _seconds(data.get("agent_execution")),
            "steps": _steps(f.parent / "agent" / "trajectory.json"),
            "tokens": (ctx.get("n_input_tokens") or 0) + (ctx.get("n_output_tokens") or 0),
            "exc": (data.get("exception_info") or {}).get("exception_type"),
        })
    return out


# Modal sandbox rates (`modal billing rates`, Oct 2026): $/core-hour and $/GiB-hour.
SANDBOX_CPU_PER_H, SANDBOX_GIB_PER_H = 0.1419, 0.024
HARBOR_TASK_CACHE = Path.home() / ".cache" / "harbor" / "tasks"


def task_resources(task: str) -> tuple[float, float]:
    """(cpus, memory GiB) a task's sandbox requests, from Harbor's cached task.toml."""
    short = task.split("/")[-1]
    for f in HARBOR_TASK_CACHE.glob(f"*/{short}/task.toml"):
        t = f.read_text()
        cpus = re.search(r"^cpus\s*=\s*([0-9.]+)", t, re.M)
        gib = re.search(r'^memory\s*=\s*"([0-9.]+)G"', t, re.M)
        mib = re.search(r"^memory_mb\s*=\s*([0-9.]+)", t, re.M)
        return (float(cpus.group(1)) if cpus else 1.0,
                float(gib.group(1)) if gib else float(mib.group(1)) / 1024 if mib else 2.0)
    return 1.0, 2.0


def sandbox_cost(trials: list[dict]) -> float:
    """Estimated sandbox bill for a run: each trial's sandbox lifetime x its requested CPU and
    memory x Modal's sandbox rates. Checked against `modal billing report` (Oct 9 to 07:00 UTC):
    $38 estimated vs $48 billed, the gap being in-flight, aborted and orphaned sandboxes."""
    total = 0.0
    for t in trials:
        if t.get("wall_s"):
            cpus, gib = task_resources(t["task"])
            total += t["wall_s"] / 3600 * (cpus * SANDBOX_CPU_PER_H + gib * SANDBOX_GIB_PER_H)
    return round(total, 4)


def _seconds(span: dict | None) -> float | None:
    """Duration of a Harbor {started_at, finished_at} span."""
    if not span or not span.get("started_at") or not span.get("finished_at"):
        return None
    t = [datetime.fromisoformat(span[k].replace("Z", "+00:00")) for k in ("started_at", "finished_at")]
    return round((t[1] - t[0]).total_seconds(), 1)


def _steps(trajectory: Path) -> int | None:
    """Agent steps (model calls) in Harbor's ATIF trajectory."""
    try:
        return sum(1 for st in json.loads(trajectory.read_text()).get("steps") or []
                   if st.get("source", "agent") == "agent")
    except (OSError, json.JSONDecodeError):
        return None


def looked_up_benchmark(trajectory: Path) -> bool:
    """True if any tool call in Harbor's ATIF trajectory references the benchmark."""
    try:
        steps = json.loads(trajectory.read_text()).get("steps") or []
    except (OSError, json.JSONDecodeError):
        return False
    return any(BENCHMARK_LOOKUP.search(json.dumps(tc.get("arguments")))
               for st in steps for tc in (st.get("tool_calls") or []))


def harbor_cmd(harness: str, concurrency: int, tasks: list[str], job_name: str,
               attempts: int = 1, agent_timeout_multiplier: float | None = None) -> list[str]:
    h = HARNESSES[harness]
    spec = load_tasks()
    source = ["-p", str(BENCH / spec["path"])] if spec.get("path") else ["-d", spec["dataset"]]  # local task dir or registry
    cmd = ["harbor", "run", "-y", *source, "-a", harness,
           "-m", h.get("model", "openai/agent-model"), "-e", "modal", "-n", str(concurrency),
           "-o", str(JOBS_DIR), "--job-name", job_name,
           # Harbor's default sandbox lifetime is 24 h. If Harbor dies mid-run, its
           # sandboxes (and in-sandbox agents still calling our URL) outlive it; cap
           # that. A trial needs at most ~20 min of agent time plus setup and tests.
           "--ek", f"sandbox_timeout_secs={SANDBOX_TIMEOUT_S}"]
    if attempts > 1:
        cmd += ["-k", str(attempts)]
    if agent_timeout_multiplier:
        cmd += ["--agent-timeout-multiplier", str(agent_timeout_multiplier)]
    kwargs = dict(h["kwargs"])
    if not h["version"].startswith("harbor-"):
        kwargs["version"] = h["version"]
    for k, v in kwargs.items():
        cmd += ["--ak", f"{k}={v if isinstance(v, str) else json.dumps(v)}"]
    for t in tasks:
        cmd += ["-i", t]
    return cmd


# ---------------------------------------------------------------- one run

def run_one(harness: str, config: str, concurrency: int, rep: int, tasks: list[str],
            task_set: str, a) -> dict | None:
    spec = CONFIGS[config]
    if spec["args"] is None:
        sys.exit(f"Config '{config}' is a placeholder; fill it in experiment.py first.")
    # A slot gives parallel streams their own app (and URL) per config.
    run_name = f"{config}-s{a.slot}" if getattr(a, "slot", 0) else config
    app = f"{APP_PREFIX}-{run_name}"
    gpu = spec.get("gpu", a.gpu)
    gpu_price = GPU_PRICES.get(gpu, a.gpu_price) if spec.get("gpu") else a.gpu_price
    k = getattr(a, "attempts", 1)
    tag = f"[{harness} | {config} c={concurrency} r={rep}{f' k={k}' if k > 1 else ''}]"
    job_name = (f"{task_set}__{harness}__{config}__c{concurrency}__r{rep}__"
                f"{time.strftime('%Y%m%d-%H%M%S')}")
    env = {"RUN_NAME": run_name, "VLLM_ARGS": json.dumps(spec["args"]), "GPU": gpu}
    if spec.get("model"):
        env["MODEL"] = spec["model"]

    # recreate: with max_containers=1 a rolling deploy can't bring up a replacement.
    deploy = ["modal", "deploy", "--env", a.modal_env, "--strategy", "recreate", str(HERE / "serve_vllm.py")]
    stop = ["modal", "app", "stop", "--env", a.modal_env, "-y", app]
    harbor = harbor_cmd(harness, concurrency, tasks, job_name, attempts=k,
                        agent_timeout_multiplier=spec.get("agent_timeout_multiplier"))
    # Harbor resolves OpenAI-compatible endpoints from these for every harness;
    # task sandboxes go to the same Modal environment as the server.
    harbor_env = {"OPENAI_BASE_URL": "{BASE}/v1", "OPENAI_API_BASE": "{BASE}/v1",
                  "OPENAI_API_KEY": "not-used", "MODAL_ENVIRONMENT": a.modal_env}

    if a.dry_run:
        print(f"\n# {harness} | {config}  concurrency={concurrency}  rep={rep}  tasks={len(tasks)} ({task_set})")
        print("  " + " ".join(f"{k}={v!r}" for k, v in env.items()) + " " + " ".join(deploy))
        print("  # wait for <BASE>/v1/models")
        print("  " + " ".join(f"{k}={v}" for k, v in harbor_env.items()) + " "
              + " ".join(f"'{x}'" if " " in x or "{" in x else x for x in harbor))
        print("  " + " ".join(stop))
        return None

    check_budget(a)
    JOBS_DIR.mkdir(exist_ok=True)
    log_path = JOBS_DIR / f"{job_name}.log"
    print(f"{tag} deploying; log: {log_path}", flush=True)
    t_deploy = time.time()
    startup_s = run_s = vllm_stats = base = None
    harbor_exit = None
    error = ""
    try:
        # Wide COLUMNS so Rich doesn't wrap the URL in the deploy output.
        dep = subprocess.run(deploy, env={**os.environ, **env, "COLUMNS": "400"}, text=True,
                             capture_output=True, cwd=BENCH)
        if dep.returncode != 0:
            raise RuntimeError(f"modal deploy failed:\n{dep.stdout[-1500:]}{dep.stderr[-1500:]}")
        base = endpoint_from_deploy(dep.stdout + dep.stderr, app)
        startup_s = wait_ready(base, a.ready_timeout)
        print(f"{tag} ready after {startup_s:.0f}s; running Harbor", flush=True)

        cmd = [x.replace("{BASE}", base) for x in harbor]
        run_env = {k: v.replace("{BASE}", base) for k, v in harbor_env.items()}
        t_run = time.time()
        scraper = vllm_metrics.Scraper(base, JOBS_DIR / f"{job_name}.metrics.jsonl").start()
        try:
            with log_path.open("w") as log:
                harbor_exit = subprocess.run(cmd, env={**os.environ, **run_env}, cwd=BENCH,
                                             stdout=log, stderr=subprocess.STDOUT).returncode
        finally:
            vllm_stats = scraper.stop(t_run)
        run_s = time.time() - t_run
    except BaseException as e:  # noqa: BLE001 - record any failure, then stop the server
        # BaseException too: a SIGTERM (SystemExit) or Ctrl-C still bills, so the run
        # is recorded (invalid) before the exit continues below.
        error = f"{type(e).__name__}: {e}"
        print(f"{tag} FAILED: {error}", flush=True)
        interrupted = e if not isinstance(e, Exception) else None
    else:
        interrupted = None
    finally:
        # Always stop the server: an idle or crash-looping GPU container still bills.
        subprocess.run(stop, cwd=BENCH, capture_output=True)
    if base and not interrupted:
        wait_gone(base)
    up_s = time.time() - t_deploy

    job = parse_job(JOBS_DIR / job_name)
    n_trials = len(tasks) * k
    valid = not error and harbor_exit == 0 and job["attempted"] == n_trials
    if not error and not valid:
        error = (f"harbor exit {harbor_exit}, parsed {job['attempted']}/{n_trials} trials; "
                 f"see {log_path}")
    cost = run_s / 3600 * gpu_price if run_s else None
    rec = {
        "ts": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "harness": harness, "harness_version": HARNESSES[harness]["version"],
        "config": config, "concurrency": concurrency, "rep": rep, "task_set": task_set,
        "model": spec.get("model") or "default", "vllm_args": spec["args"], "gpu": gpu,
        "tasks": len(tasks), **job,
        "success_rate": job["solved"] / n_trials,
        "startup_s": round(startup_s) if startup_s is not None else None,
        "run_s": round(run_s) if run_s is not None else None,
        "up_s": round(up_s),
        "gpu_price_per_h": gpu_price, "attempts_per_task": k,
        # Cost = all GPU time while the agent ran (tool waits and failed tasks
        # included). Startup is reported separately.
        "cost": round(cost, 4) if cost is not None else None,
        "startup_cost": round(startup_s / 3600 * gpu_price, 4) if startup_s else None,
        "cost_per_solved": round(cost / job["solved"], 4) if cost and job["solved"] else None,
        # GPU cost only covers the server; Harbor's task sandboxes bill on top (~40% of spend).
        "sandbox_cost_est": sandbox_cost(job["trials"]),
        "total_cost_per_solved": (round((cost + sandbox_cost(job["trials"])) / job["solved"], 4)
                                  if cost and job["solved"] else None),
        "sec_per_task": round(run_s / n_trials, 1) if run_s else None,
        "valid": valid, "error": error, "job_name": job_name,
        # What the server did during the run, from vLLM's /metrics (see vllm_metrics.py).
        "vllm": vllm_stats,
    }
    with ATTEMPTS.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    print(json.dumps(rec, indent=2), flush=True)
    if interrupted:
        raise interrupted
    return rec


# ---------------------------------------------------------------- commands

def runnable_configs(names):
    out = []
    for n in names:
        if CONFIGS[n]["args"] is None:
            print(f"Skipping '{n}': placeholder config, fill it in experiment.py.")
        else:
            out.append(n)
    return out


def cmd_run(a):
    run_one(a.harness, a.config, a.concurrency, a.rep, load_tasks()["tasks"], task_set_name(), a)


def cmd_quickcheck(a):
    tasks = load_tasks()["tasks"][:QUICKCHECK["n_tasks"]]
    done = completed_keys()
    for h in a.harnesses:
        for c in QUICKCHECK["configs"]:
            if run_key(h, c, QUICKCHECK["concurrency"], 0, "quick") in done:
                print(f"Already done: {h} | {c}")
                continue
            run_one(h, c, QUICKCHECK["concurrency"], 0, tasks, "quick", a)


def cmd_matrix(a):
    tasks = load_tasks()["tasks"]
    configs = runnable_configs(a.configs)
    done = completed_keys()
    # With k attempts per task, runs are a separate task set (more trials, so higher
    # concurrency still has work to do).
    base = task_set_name()
    task_set = base if a.attempts == 1 else f"{base}-k{a.attempts}"
    # Repeat-major order: one full pass over every harness x config x concurrency
    # before any repeats, so an interrupted matrix still has comparable data.
    plan = [(h, c, n, r) for r in range(a.rep_from, a.reps) for h in a.harnesses
            for n in a.concurrency for c in configs]
    todo = [p for p in plan if run_key(*p, task_set) not in done]
    print(f"{len(plan)} runs in matrix, {len(plan) - len(todo)} already done, {len(todo)} to go.")
    for h, c, n, r in todo:
        if PAUSE.exists():  # stop cleanly between runs, e.g. to drop a planned config
            print(f"PAUSE file found; stopping before {h} | {c} c={n} r={r}.", flush=True)
            return
        run_one(h, c, n, r, tasks, task_set, a)


# ---------------------------------------------------------------- report

def spread(values):
    vals = [v for v in values if v is not None]
    if not vals:
        return None, None, None
    return statistics.mean(vals), min(vals), max(vals)


def fmt(mean, lo, hi, kind):
    if mean is None:
        return "-"
    f = {"pct": lambda v: f"{100 * v:.0f}%", "usd": lambda v: f"${v:.3f}", "sec": lambda v: f"{v:.0f}s",
         "num": lambda v: f"{v:g}"}[kind]
    return f"{f(mean)} ({f(lo)}–{f(hi)})" if hi != lo else f(mean)


def table(hdr, rows):
    return (["| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
            + ["| " + " | ".join(r) + " |" for r in rows])


def summarize(rs: list[dict]) -> dict:
    tot_in = sum(r.get("input_tokens", 0) for r in rs)
    return {
        "n": len(rs),
        "sr": spread([r["success_rate"] for r in rs]),
        "cps": spread([r["cost_per_solved"] for r in rs]),
        "tcps": spread([r.get("total_cost_per_solved") for r in rs]),
        "spt": spread([r["sec_per_task"] for r in rs]),
        "startup": spread([r["startup_s"] for r in rs]),
        "cached": (sum(r.get("cached_tokens", 0) for r in rs) / tot_in) if tot_in else None,
        "setup_failed": spread([r.get("setup_failed", 0) for r in rs]),
        "peeked": spread([r.get("peeked", 0) for r in rs]),
    }


def gate(s: dict, base: dict | None, gate_pts: float) -> str:
    if base is None:
        return "no defaults run"
    return "fails quality gate" if 100 * (s["sr"][0] - base["sr"][0]) < -gate_pts else "passes"


def vs_defaults(s: dict, base: dict | None) -> float | None:
    """% change in mean cost per solved task vs the same harness's defaults (negative = cheaper)."""
    if base is None or s["cps"][0] is None or base["cps"][0] is None:
        return None
    return 100 * (s["cps"][0] - base["cps"][0]) / base["cps"][0]


def headline(stats: dict, gate_pts: float) -> str:
    base = stats.get("defaults")
    if base is None:
        return "_No defaults run at this concurrency yet._"
    ranked = [(vs_defaults(s, base), c) for c, s in stats.items()
              if c != "defaults" and gate(s, base, gate_pts) == "passes" and vs_defaults(s, base) is not None]
    if not ranked:
        return "_Nothing that passes the quality gate to compare against defaults yet._"
    delta, best = min(ranked)
    if delta >= 0:
        return (f"**No config that passes the quality gate is cheaper per solved task than defaults** "
                f"(closest: {best}, {delta:.0f}% more expensive).")
    return f"**Best config that passes the quality gate: {best}, {-delta:.0f}% cheaper per solved task than defaults.**"


def _pct(v):
    return f"{100 * v:.0f}%"


SERVER_COLS = [  # (header, keys in record["vllm"] (one, or mean / max), format)
    ("GPU busy", ("busy_frac",), _pct),
    ("running (mean / max)", ("running_mean", "running_max"), lambda v: f"{v:.1f}"),
    ("waiting max", ("waiting_max",), lambda v: f"{v:g}"),
    ("KV cache (mean / max)", ("kv_usage_mean", "kv_usage_max"), _pct),
    ("preemptions", ("preemptions",), lambda v: f"{v:g}"),
    ("prefix hit rate", ("prefix_hit_rate",), _pct),
    ("time to first token", ("ttft_mean_s",), lambda v: f"{v:.2f}s"),
    ("ms / output token", ("itl_mean_ms",), lambda v: f"{v:.1f}"),
    ("output tok/s", ("gen_tok_per_s",), lambda v: f"{v:.0f}"),
    ("spec. accept", ("spec_accept_rate",), _pct),
]


def server_section(runs: list[dict]) -> list[str]:
    """One row per harness x concurrency x config, from vLLM /metrics (mean over repeats)."""
    groups: dict = {}
    for r in runs:
        if r.get("vllm"):
            groups.setdefault((r["harness"], r["concurrency"], r["config"]), []).append(r["vllm"])
    if not groups:
        return []

    def cell(vs, keys, f):
        means = []
        for k in keys:
            vals = [v[k] for v in vs if v.get(k) is not None]
            means.append(statistics.mean(vals) if vals else None)
        return "-" if means[0] is None else " / ".join(f(x) for x in means if x is not None)

    rows = [[h, str(n), c, *[cell(vs, keys, f) for _, keys, f in SERVER_COLS]]
            for (h, n, c), vs in sorted(groups.items(),
                                        key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] != "defaults", kv[0][2]))]
    return (["### What the server did (vLLM /metrics)", "",
             "Sampled every 10 s during the agent run. GPU busy = share of samples with at least one "
             "request on the GPU; the rest is time every agent was running tools or being set up. "
             "Latencies are means over all requests.", ""]
            + table(["harness", "concurrency", "config", *[c[0] for c in SERVER_COLS]], rows) + [""])


def time_section(runs: list[dict]) -> list[str]:
    """Where agent time goes, from each record's per-trial list (pooled over repeats)."""
    groups: dict = {}
    for r in runs:
        if r.get("trials"):
            groups.setdefault((r["harness"], r["concurrency"], r["config"]), []).extend(
                t for t in r["trials"] if t.get("agent_s"))
    if not groups:
        return []
    rows = []
    for (h, n, c), ts in sorted(groups.items(), key=lambda kv: (kv[0][0], kv[0][1], kv[0][2] != "defaults", kv[0][2])):
        total = sum(t["agent_s"] for t in ts)
        solved = [t for t in ts if t["ok"]]
        timeouts = [t for t in ts if t.get("exc") == "AgentTimeoutError" and not t["ok"]]
        steps = [t["steps"] for t in ts if t.get("steps")]
        step_s = [t["agent_s"] / t["steps"] for t in ts if t.get("steps")]
        rows.append([h, str(n), c, str(len(ts)), str(len(solved)), str(len(timeouts)),
                     f"{100 * (total - sum(t['agent_s'] for t in solved)) / total:.0f}%" if total else "-",
                     f"{statistics.mean(steps):.0f}" if steps else "-",
                     f"{statistics.median(step_s):.0f}s" if step_s else "-",
                     f"{total / 60 / len(solved):.0f}" if solved else "-"])
    return (["### Where the agents' time goes", "",
             "Per trial, pooled over repeats. Agent time on failed tasks = share of all agent time "
             "spent on trials that weren't solved (mostly timeouts). Seconds per step = median over "
             "trials of agent time / model calls; it rises when the server is slower. Agent-minutes "
             "per solve = all agent time / solved trials.", ""]
            + table(["harness", "concurrency", "config", "trials", "solved", "timed out",
                     "agent time on failed tasks", "steps / trial", "s / step", "agent-min / solve"], rows)
            + [""])


def build_report(attempts: list[dict], gate_pts: float = QUALITY_GATE_PTS) -> str:
    valid = [r for r in attempts if r.get("valid")]
    for r in valid:
        r.setdefault("harness", "terminus-2")
    lines = ["# Agentic serving experiment", ""]
    if not valid:
        return "\n".join(lines + ["No completed runs yet."])
    first = valid[0]
    lines += [f"GPU: {first['gpu']} at ${first['gpu_price_per_h']}/h. Model: Qwen3.8-27B "
              f"(BF16 unless the config says otherwise). Agent harnesses run through Harbor.", ""]

    titles = {"quick": "Quickcheck (first 8 tasks)", "full": "Full matrix (36 tasks)"}
    sets = ["quick", "full"] + sorted({r["task_set"] for r in valid} - {"quick", "full"})
    for task_set, title in [(t, titles.get(t, f"36 tasks x {t.rsplit('-k', 1)[-1]} attempts"))
                            for t in sets]:
        runs = [r for r in valid if r["task_set"] == task_set]
        if not runs:
            continue
        lines += [f"## {title}", ""]
        # stats[harness][concurrency][config] -> summary
        stats: dict = {}
        for r in runs:
            stats.setdefault(r["harness"], {}).setdefault(r["concurrency"], {}).setdefault(r["config"], []).append(r)
        stats = {h: {n: {c: summarize(rs) for c, rs in byc.items()} for n, byc in byn.items()}
                 for h, byn in stats.items()}
        harnesses = sorted(stats)
        concs = sorted({n for h in stats for n in stats[h]})

        if len(harnesses) > 1:
            lines += ["### Across harnesses", "",
                      "At vLLM defaults: how the harnesses compare on their own.", ""]
            rows = []
            for n in concs:
                for h in harnesses:
                    s = stats[h].get(n, {}).get("defaults")
                    if s:
                        rows.append([str(n), h, str(s["n"]), fmt(*s["sr"], "pct"), fmt(*s["cps"], "usd"),
                                     fmt(*s["spt"], "sec")])
            lines += table(["concurrency", "harness", "reps", "success rate", "cost / solved task",
                            "sec / task"], rows) + [""]
            lines += ["Change in cost per solved task vs. the same harness's defaults "
                      "(negative = cheaper; ✗ = fails that harness's quality gate):", ""]
            configs = sorted({c for h in stats for n in stats[h] for c in stats[h][n]} - {"defaults"})
            rows = []
            for n in concs:
                for c in configs:
                    cells = []
                    for h in harnesses:
                        s, base = stats[h].get(n, {}).get(c), stats[h].get(n, {}).get("defaults")
                        d = vs_defaults(s, base) if s else None
                        cell = "-" if d is None else f"{d:+.0f}%"
                        if s and base and gate(s, base, gate_pts) != "passes":
                            cell += " ✗"
                        cells.append(cell)
                    rows.append([str(n), c, *cells])
            lines += table(["concurrency", "config", *harnesses], rows) + [""]

        for h in harnesses:
            lines += [f"### Harness: {h}", ""]
            for n in sorted(stats[h]):
                st = stats[h][n]
                base = st.get("defaults")
                rows = []
                for c in sorted(st, key=lambda c: (c != "defaults", c)):
                    s = st[c]
                    rows.append([c, str(s["n"]), fmt(*s["sr"], "pct"), fmt(*s["cps"], "usd"), fmt(*s["tcps"], "usd"),
                                 fmt(*s["spt"], "sec"),
                                 "-" if s["cached"] is None else f"{100 * s['cached']:.0f}%",
                                 fmt(*s["startup"], "sec"), fmt(*s["setup_failed"], "num"),
                                 fmt(*s["peeked"], "num"), gate(s, base, gate_pts)])
                lines += [f"**Concurrency {n}.** {headline(st, gate_pts)}", ""]
                lines += table(["config", "reps", "success rate", "GPU cost / solved task",
                                "incl. sandboxes", "sec / task",
                                "cached prompt tokens", "startup", "agent never started",
                                "looked up benchmark", "quality gate"], rows) + [""]

        lines += server_section(runs)
        lines += time_section(runs)

    lines += [
        "## How to read this", "",
        "- Values are the mean across repeats with (min–max) in brackets. If two ranges overlap, "
        "treat the difference as noise.",
        f"- Quality gate (fixed before running), applied within each harness: a config whose mean success "
        f"rate is more than {gate_pts:.0f} points below that harness's defaults at the same concurrency "
        "fails and is not ranked on cost.",
        "- Across harnesses, compare success rate and cost per solved task together: a harness that is "
        "cheaper but solves fewer tasks is not automatically better.",
        "- Cost = GPU time from the start to the end of the agent run × $/GPU-hour, including time the GPU "
        "waits on tool calls and time spent on failed tasks. Model startup is shown separately.",
        "- Cached prompt tokens = share of prompt tokens served from vLLM's prefix cache, as the harness "
        "reports it. '-' or 0% can mean the harness doesn't report it.",
        "- Agent never started = tasks where the harness failed before the agent ran (e.g. its install "
        "inside the task sandbox failed). They count as unsolved in the success rate.",
        "- Looked up benchmark = tasks where the agent's tool calls reached for Terminal-Bench itself "
        "(cloning its repo, searching for it), e.g. to find the expected answer. These never count as "
        "solved, even if the verifier passed them.",
        "",
        "## Limitations", "",
        "- One model, one GPU type, one task set, and only the harnesses shown. Results may not transfer.",
        f"- {len(load_tasks()['tasks'])} tasks per full run (8 for the quickcheck): a few tasks either way "
        "moves the success rate by several points.",
        "- Run time includes Harbor's per-task sandbox setup on Modal, which doesn't depend on the serving "
        "config. Harnesses installed inside the sandbox also spend GPU-idle time installing themselves; "
        "that is counted as part of their cost.",
        "- Task sandboxes have internet access (in-sandbox harnesses need it to reach the model), and the "
        "model knows Terminal-Bench, so agents can look answers up. We detect this from tool calls in the "
        "trajectories; a lookup that never names the benchmark (e.g. a search for a task's dataset) is not caught.",
        "- If a config fails more often on long tasks, that does not show quantization damage compounds over "
        "agent steps: harder tasks take more steps. We report what we measure, not why.",
        "",
    ]
    return "\n".join(lines)


def cmd_report(a):
    text = build_report(read_attempts())
    REPORT.write_text(text)
    print(text)


# ---------------------------------------------------------------- cli

def main():
    # Turn SIGTERM (e.g. pkill, a cloud session shutting down) into SystemExit, so the
    # `finally` in run_one still stops the GPU server instead of leaving it billing.
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(143))
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--dry-run", action="store_true", help="print deploy/harbor/stop commands, run nothing")
    p.add_argument("--harnesses", nargs="+", default=DEFAULT_HARNESSES, choices=list(HARNESSES),
                   help=f"harnesses for quickcheck/matrix (default: {' '.join(DEFAULT_HARNESSES)})")
    p.add_argument("--gpu", default=os.environ.get("GPU", "H100!"),
                   help="Modal GPU string; '!' stops Modal swapping an H100 for an H200 (default H100!)")
    p.add_argument("--gpu-price", type=float, default=3.95, help="$/GPU-hour (Modal H100, Oct 2026)")
    p.add_argument("--modal-env", default=os.environ.get("MODAL_ENVIRONMENT", "main"),
                   help="Modal environment for servers and sandboxes (default: $MODAL_ENVIRONMENT, else 'main')")
    # Normal startups take 2-4 min (more on a first weight download). A server that isn't up
    # by then is usually crash-looping, and still billing.
    p.add_argument("--ready-timeout", type=int, default=15 * 60, help="seconds to wait for vLLM to start")
    # This guard only sees GPU time; Harbor's task sandboxes added ~30-70% on top in the
    # original runs (`modal billing report`), so it stops well below the real-spend limit.
    p.add_argument("--budget", type=float, default=560.0,
                   help="stop starting runs past this much GPU spend (default 560 = ~$950 real at 1.7x)")
    p.add_argument("--spent-before", type=float, default=float(os.environ.get("SPENT_BEFORE", 0)),
                   help="$ already spent outside attempts.jsonl (failed smoke tests etc.)")
    p.add_argument("--tasks-file", default="tasks.json",
                   help="task list (tasks_<name>.json gives task set <name>, e.g. tasks_gaia.json -> gaia)")
    p.add_argument("--slot", type=int, default=0,
                   help="parallel stream id: runs deploy as <prefix>-<config>-s<slot> so streams don't collide")
    p.add_argument("--run-reserve", type=float, default=6.0, help="$ a single run may cost; keep this much headroom")
    sub = p.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="one harness + config at one concurrency on all tasks")
    r.add_argument("--harness", default="terminus-2", choices=list(HARNESSES))
    r.add_argument("--config", required=True, choices=list(CONFIGS))
    r.add_argument("--concurrency", type=int, default=16)
    r.add_argument("--rep", type=int, default=0)
    r.set_defaults(fn=cmd_run, attempts=1)

    q = sub.add_parser("quickcheck", help="defaults vs no-prefix-cache, c=16, first 8 tasks, 1 rep, every harness")
    q.set_defaults(fn=cmd_quickcheck, attempts=1)

    m = sub.add_parser("matrix", help="harness x config x concurrency x repeat; skips completed runs")
    m.add_argument("--configs", nargs="+", default=list(CONFIGS), choices=list(CONFIGS))
    m.add_argument("--concurrency", nargs="+", type=int, default=[4, 16])
    m.add_argument("--reps", type=int, default=2, help="repeats 0..reps-1")
    m.add_argument("--rep-from", type=int, default=0, help="first repeat index (e.g. 1 to only add repeats)")
    m.add_argument("--attempts", type=int, default=1, help="attempts per task (Harbor -k); >1 is its own task set")
    m.set_defaults(fn=cmd_matrix)

    rep = sub.add_parser("report")
    rep.set_defaults(fn=cmd_report)

    a = p.parse_args()
    global TASKS
    TASKS = BENCH / a.tasks_file
    if not TASKS.exists() and (BENCH / "data" / a.tasks_file).exists():  # task lists live in data/
        TASKS = BENCH / "data" / a.tasks_file
    a.fn(a)


if __name__ == "__main__":
    main()
