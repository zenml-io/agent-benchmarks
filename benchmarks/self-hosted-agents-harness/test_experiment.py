"""Offline tests for parsing and reporting. No Modal, no Harbor, no GPU.

    python test_experiment.py
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

# experiment.py reads its task list and attempts.jsonl from a benchmark directory (BENCH_DIR).
# The tests use a throwaway one with a 36-task list, so no real runs are ever skipped or read.
_BENCH = tempfile.mkdtemp(prefix="harness-test-bench-")
(Path(_BENCH) / "tasks.json").write_text(json.dumps(
    {"dataset": "terminal-bench@2.0", "tasks": [f"task-{i:02d}" for i in range(36)]}))
TEST_ENV = {**os.environ, "BENCH_DIR": _BENCH, "MODAL_ENVIRONMENT": "test-env"}
TEST_ENV.pop("ATTEMPTS_FILE", None)
os.environ.update({"BENCH_DIR": _BENCH, "MODAL_ENVIRONMENT": "test-env"})
os.environ.pop("ATTEMPTS_FILE", None)

import experiment as ex  # noqa: E402
import vllm_metrics as vm  # noqa: E402


def write_trial(job: Path, name: str, reward=None, crashed=False, tokens=(1000, 600, 50),
                setup_failed=False, commands=()):
    d = job / name
    d.mkdir(parents=True)
    data = {
        "task_name": name, "trial_name": name,
        "verifier_result": None if reward is None else {"rewards": {"reward": reward}},
        "exception_info": ({"exception_type": "NonZeroAgentExitCodeError"} if setup_failed else
                           {"exception_type": "AgentTimeoutError"} if crashed else None),
        "agent_execution": None if setup_failed else {"started_at": "2026-10-09T01:00:00Z",
                                                      "finished_at": "2026-10-09T01:01:00Z"},
        "agent_result": {"n_input_tokens": tokens[0], "n_cache_tokens": tokens[1],
                         "n_output_tokens": tokens[2]},
    }
    (d / "result.json").write_text(json.dumps(data))
    if commands:
        (d / "agent").mkdir()
        (d / "agent" / "trajectory.json").write_text(json.dumps(
            {"steps": [{"tool_calls": [{"arguments": {"command": c}}]} for c in commands]}))


def test_parse_job():
    with tempfile.TemporaryDirectory() as tmp:
        job = Path(tmp) / "job"
        write_trial(job, "a__1", reward=1.0)
        write_trial(job, "b__1", reward=0.0)
        write_trial(job, "c__1", reward=None, crashed=True)  # crashed before verifying
        write_trial(job, "d__1", reward=1)
        write_trial(job, "f__1", setup_failed=True, tokens=(0, 0, 0))  # harness install failed
        # passed by copying the answer from the benchmark repo: not solved
        write_trial(job, "g__1", reward=1.0, tokens=(0, 0, 0), commands=[
            "git clone https://github.com/laude-institute/terminal-bench.git /tmp/tb"])
        # the code-from-image task's salt is not a benchmark lookup
        write_trial(job, "h__1", reward=1.0, tokens=(0, 0, 0), commands=["echo 0000TBENCH-SALT | sha256sum"])
        # Job-level summary that embeds trial results must not be counted.
        (job / "result.json").write_text(json.dumps(
            {"trial_results": [{"verifier_result": {"rewards": {"reward": 1.0}}}]}))
        (job / "e__1").mkdir()
        (job / "e__1" / "result.json").write_text("{not json")  # half-written file: skipped
        got = ex.parse_job(job)
        assert got["attempted"] == 7, got
        assert got["solved"] == 3, got
        assert got["peeked"] == 1 and got["peeked_solved"] == 1, got
        trials = {t["task"]: t for t in got["trials"]}
        assert len(trials) == 7 and trials["a__1"]["ok"] and not trials["g__1"]["ok"], trials  # peeked
        assert trials["c__1"]["exc"] == "AgentTimeoutError" and trials["f__1"]["agent_s"] is None, trials
        assert trials["a__1"]["agent_s"] == 60.0 and trials["h__1"]["steps"] == 1, trials
        assert got["errors"] == 2 and got["setup_failed"] == 1, got
        assert got["input_tokens"] == 4000 and got["cached_tokens"] == 2400, got
        assert ex.parse_job(Path(tmp) / "missing")["attempted"] == 0


def test_vllm_metrics():
    text = ("# HELP x\n"
            'vllm:num_requests_running{engine="0",model_name="agent-model"} 3.0\n'
            'vllm:kv_cache_usage_perc{engine="0"} 0.5\n'
            'vllm:prefix_cache_queries_total{engine="0"} 1000.0\n'
            'vllm:prefix_cache_hits_total{engine="0"} 800.0\n'
            'vllm:generation_tokens_total{engine="0"} 600.0\n'
            'vllm:inter_token_latency_seconds_sum{engine="0"} 12.0\n'
            'vllm:inter_token_latency_seconds_count{engine="0"} 600.0\n'
            'vllm:inter_token_latency_seconds_bucket{le="0.01"} 5.0\n'
            'vllm:time_to_first_token_seconds_sum{engine="0"} NaN\n')
    got = vm.parse(text)
    assert got["num_requests_running"] == 3 and "inter_token_latency_seconds_bucket" not in got, got
    assert "time_to_first_token_seconds_sum" not in got  # NaN skipped
    idle = {"t": 100.0, "num_requests_running": 0.0, "kv_cache_usage_perc": 0.0}
    busy = {"t": 160.0, **got}
    s = vm.summarize([idle, busy], t0=100.0)
    assert s["busy_frac"] == 0.5 and s["running_max"] == 3 and s["kv_usage_mean"] == 0.25, s
    assert s["prefix_hit_rate"] == 0.8 and s["gen_tok_per_s"] == 10.0 and s["itl_mean_ms"] == 20.0, s
    assert s["ttft_mean_s"] is None and s["spec_accept_rate"] is None, s
    assert vm.summarize([idle]) is None


def test_wait_ready_rejects_previous_runs_server():
    """Right after a deploy, the old container can still answer at the same URL."""
    import http.server
    import threading

    state = {"tokens": 5000.0}

    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            body = (f'vllm:prompt_tokens_total{{engine="0"}} {state["tokens"]}\n'
                    if self.path == "/metrics" else '{"data": []}').encode()
            self.send_response(200)
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *a):
            pass

    srv = http.server.HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_port}"
    try:
        try:
            ex.wait_ready(base, timeout_s=0.5, poll_s=0.1)  # old server: has served tokens
            raise AssertionError("accepted a server that already served tokens")
        except TimeoutError:
            pass
        state["tokens"] = 0.0  # the fresh server
        assert ex.wait_ready(base, timeout_s=5, poll_s=0.1) < 5
    finally:
        srv.shutdown()


def test_slots_attempts_and_gpu_pinning():
    here = Path(__file__).resolve().parent
    p = subprocess.run([sys.executable, "experiment.py", "--dry-run", "--slot", "3", "--harnesses",
                        "terminus-2", "--", "matrix", "--concurrency", "64", "--attempts", "2",
                        "--reps", "2", "--rep-from", "1", "--configs", "h200", "defaults-2x-time"],
                       cwd=here, capture_output=True, text=True, env=TEST_ENV)
    assert p.returncode == 0, p.stderr
    out = p.stdout
    assert "2 runs in matrix" in out, out          # only repeat 1, two configs
    assert "RUN_NAME='h200-s3'" in out and "GPU='H200'" in out, out
    assert "-y agent-h200-s3" in out and "-y agent-defaults-2x-time-s3" in out, out
    assert " -k 2 " in out and "(full-k2)" in out and "__r1__" in out and "__r0__" not in out, out
    assert out.count("--agent-timeout-multiplier 2.0") == 1, out
    assert ex.GPU_PRICES["H200"] > ex.GPU_PRICES["H100!"]


def test_nested_flag_values_survive_the_image_env():
    """serve_vllm.py puts VLLM_ARGS in a Dockerfile ENV line, which eats backslashes. A JSON
    flag value (spec-mtp, no-thinking) must reach the container intact (it crash-looped)."""
    src = (Path(__file__).resolve().parent / "serve_vllm.py").read_text()
    ns: dict = {}
    exec(src.split("image = (")[0].replace("import modal", ""), ns)  # helpers only, no Modal
    for name, spec in ex.CONFIGS.items():
        if spec["args"] is None:
            continue
        image_env = json.dumps(ns["_unnest"](json.loads(json.dumps(spec["args"]))))
        assert "\\" not in image_env, (name, image_env)
        cli = ns["to_cli"](ns["_unnest"](json.loads(image_env)))
        for flag, value in spec["args"].items():
            if isinstance(value, str) and value.startswith("{"):
                assert json.loads(cli[cli.index(flag) + 1]) == json.loads(value), (name, cli)


def test_sandbox_cost_estimate():
    # an unknown task defaults to 1 CPU + 2 GiB; one hour of sandbox
    est = ex.sandbox_cost([{"task": "no-such-task-xyz", "wall_s": 3600.0}, {"task": "x", "wall_s": None}])
    assert abs(est - (ex.SANDBOX_CPU_PER_H + 2 * ex.SANDBOX_GIB_PER_H)) < 1e-3, est


def test_endpoint_parsing():
    out = ("✓ Created objects.\n├── 🔨 Created server Server =>\n"
           "\x1b[1mhttps://myworkspace-myenv--agent-kv-fp8-server.us-east.modal.direct\x1b[0m (unauthenticated)\n")
    assert ex.endpoint_from_deploy(out, "agent-kv-fp8") == \
        "https://myworkspace-myenv--agent-kv-fp8-server.us-east.modal.direct"
    wrapped = ("└── ✓ Created Server Server\n    └── https://myworkspace-myenv--agent-no-prefix-cache-server.us-east.modal.d\n"
               "        irect (unauthenticated)\n✓ App deployed in 2.094s!\n\nView Deployment: \nhttps://modal.com/apps/myworkspace/myenv/deployed/x")
    assert ex.endpoint_from_deploy(wrapped, "agent-no-prefix-cache") == \
        "https://myworkspace-myenv--agent-no-prefix-cache-server.us-east.modal.direct"
    old = "https://myworkspace-myenv--agent-smoke-serve.modal.run 🔑"
    assert ex.endpoint_from_deploy(old, "agent-smoke") == "https://myworkspace-myenv--agent-smoke-serve.modal.run"
    try:
        ex.endpoint_from_deploy("no url here", "agent-x")
        raise AssertionError("expected RuntimeError")
    except RuntimeError:
        pass


def rec(config, conc, rep, solved, run_s, task_set="full", tasks=36, valid=True, cached=0,
        harness="terminus-2"):
    cost = run_s / 3600 * 3.95
    return {"harness": harness, "config": config, "concurrency": conc, "rep": rep, "task_set": task_set,
            "gpu": "H100!", "gpu_price_per_h": 3.95, "tasks": tasks, "solved": solved,
            "attempted": tasks, "success_rate": solved / tasks, "run_s": run_s,
            "cost": cost, "cost_per_solved": cost / solved if solved else None,
            "sec_per_task": run_s / tasks, "startup_s": 300, "valid": valid,
            "input_tokens": 1000, "cached_tokens": cached}


def test_report_quality_gate_and_headline():
    attempts = [
        # concurrency 16: defaults 50%, kv-fp8 ~45.8% (-4.2 pts, passes, cheaper),
        # weights-fp8 38.9% (-11 pts, fails gate even though it's cheapest)
        rec("defaults", 16, 0, 18, 3600, cached=700), rec("defaults", 16, 1, 18, 3800, cached=700),
        rec("kv-fp8", 16, 0, 17, 2700), rec("kv-fp8", 16, 1, 16, 2900),
        rec("weights-fp8", 16, 0, 14, 1500), rec("weights-fp8", 16, 1, 14, 1500),
        rec("no-prefix-cache", 16, 0, 18, 5000, cached=0),
        # invalid run must be ignored
        rec("no-prefix-cache", 16, 1, 0, 10, valid=False),
        # concurrency 4: nothing beats defaults
        rec("defaults", 4, 0, 18, 3600), rec("no-prefix-cache", 4, 0, 18, 4000),
        # quickcheck kept separate
        rec("defaults", 16, 0, 4, 900, task_set="quick", tasks=8),
    ]
    text = ex.build_report(attempts)
    full = text.split("## Full matrix")[1]
    c16 = full.split("**Concurrency 16.**")[1].split("**Concurrency")[0]
    assert "Best config that passes the quality gate: kv-fp8" in c16, c16
    row = lambda name: next(l for l in c16.splitlines() if l.startswith(f"| {name} |"))
    assert "fails quality gate" in row("weights-fp8")
    assert "passes" in row("kv-fp8")
    assert "| 1 |" in row("no-prefix-cache"), "invalid rep must not count"
    assert "(44%–47%)" in row("kv-fp8"), row("kv-fp8")  # mean with min–max spread
    assert "70%" in row("defaults") and "| 0% |" in row("no-prefix-cache")
    c4 = full.split("**Concurrency 4.**")[1].split("**Concurrency")[0]
    assert "No config that passes the quality gate is cheaper" in c4, c4
    assert "## Quickcheck (first 8 tasks)" in text
    assert "## Limitations" in text and "compounds" in text
    # Cost per solved never appears without success rate and time in the same row.
    assert "success rate | GPU cost / solved task | incl. sandboxes | sec / task" in text
    assert ex.build_report([]).endswith("No completed runs yet.")


def test_completed_keys_skip_logic():
    with tempfile.TemporaryDirectory() as tmp:
        ex.ATTEMPTS = Path(tmp) / "attempts.jsonl"
        ex.ATTEMPTS.write_text("\n".join(json.dumps(r) for r in [
            {k: v for k, v in rec("defaults", 4, 0, 18, 3600).items() if k != "harness"},
            rec("kv-fp8", 4, 0, 0, 10, valid=False),  # failed -> should be retried
        ]))
        keys = ex.completed_keys()
        # records written before the harness axis existed count as terminus-2
        assert ("terminus-2", "defaults", 4, 0, "full") in keys
        assert ("terminus-2", "kv-fp8", 4, 0, "full") not in keys


def test_dry_run_prints_commands_and_spends_nothing():
    here = Path(__file__).resolve().parent
    # quickcheck on a harness with no real runs in attempts.jsonl, so nothing is skipped
    for args in (["--dry-run", "--harnesses", "openhands", "--", "quickcheck"], ["--dry-run", "matrix", "--reps", "1", "--concurrency", "4"]):
        p = subprocess.run([sys.executable, "experiment.py", *args], cwd=here,
                           capture_output=True, text=True, env=TEST_ENV)
        assert p.returncode == 0, p.stderr
        out = p.stdout
        assert "modal deploy --env test-env --strategy recreate" in out
        assert "modal app stop --env test-env -y agent-" in out
        assert " -i " in out and " -t " not in out
        assert "api_base={BASE}/v1" in out
        assert "--ek sandbox_timeout_secs=7200" in out
    assert "Skipping 'recommended'" in out
    # 2 default harnesses x every runnable config x 1 concurrency x 1 rep
    runnable = [c for c, spec in ex.CONFIGS.items() if spec["args"] is not None]
    assert out.count("modal deploy") == 2 * len(runnable), out
    assert "RUN_NAME='spec-mtp'" in out
    # spec-mtp's flag value is itself JSON; it must come back intact from VLLM_ARGS
    args = json.loads(json.dumps(ex.CONFIGS["spec-mtp"]["args"]))
    assert json.loads(args["--speculative-config"]) == {"method": "mtp", "num_speculative_tokens": 2}
    assert "-a terminus-2" in out and "-a mini-swe-agent" in out
    assert "'version=2.4.6'" in out or "version=2.4.6" in out


def test_cross_harness_report():
    attempts = [
        rec("defaults", 16, 0, 18, 3600), rec("kv-fp8", 16, 0, 17, 2700),
        rec("defaults", 16, 0, 12, 1800, harness="mini-swe-agent"),
        rec("kv-fp8", 16, 0, 8, 1700, harness="mini-swe-agent"),   # 22% vs 33%: fails its own gate
    ]
    text = ex.build_report(attempts)
    assert "### Across harnesses" in text
    assert "### Harness: mini-swe-agent" in text and "### Harness: terminus-2" in text
    across = text.split("### Across harnesses")[1].split("### Harness:")[0]
    kv = next(l for l in across.splitlines() if l.startswith("| 16 | kv-fp8 |"))
    cells = [c.strip() for c in kv.strip("|").split("|")]
    assert cells[2] == "✗" or cells[2].endswith("✗"), kv      # mini-swe-agent column (sorted first)
    assert cells[3].startswith("-") and "✗" not in cells[3], kv  # terminus-2: cheaper, passes
    mini = text.split("### Harness: mini-swe-agent")[1].split("### Harness:")[0]
    assert "fails quality gate" in mini


if __name__ == "__main__":
    for name, fn in list(globals().items()):
        if name.startswith("test_"):
            with contextlib.redirect_stdout(io.StringIO()):
                fn()
            print("ok", name)
