"""
Replay real agent traffic against a serving engine, without agents or sandboxes.

    python replay_bench.py --engine vllm   --name rb-vllm
    python replay_bench.py --engine sglang --name rb-sglang [--args '{"--flag": "v"}']

Workload: mini-swe-agent trajectories from our own Terminal-Bench runs (jobs/). Each
session replays one trajectory turn by turn: request i sends the conversation exactly as
the agent sent it before its i-th reply and asks for exactly as many tokens as that reply
used (ignore_eos), so both engines get the same prompts, the same prefix sharing and the
same generation lengths. --concurrency sessions run at once (finished sessions are
replaced by the next one), with --gap seconds between turns for tool execution, for
--duration seconds. Deploys the server, runs, stops it, and appends a record to bench.jsonl.
"""

import argparse
import glob
import json
import queue
import statistics as st
import subprocess
import threading
import time
import urllib.request
from pathlib import Path

import os
import sys

BENCH = Path(__file__).resolve().parents[1]
HARNESS = BENCH.parent / "self-hosted-agents-harness"
sys.path.insert(0, str(HARNESS))
import experiment as ex  # noqa: E402

HERE = BENCH
# New runs land next to the benchmark, not in the published results/runs/.
OUT = BENCH / "bench.jsonl"
MODAL_ENV = os.environ.get("MODAL_ENVIRONMENT", "main")
APP_PREFIX = os.environ.get("MODAL_APP_PREFIX", "agent")
BASH_TOOL = [{"type": "function", "function": {
    "name": "bash", "description": "Execute a bash command",
    "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}}]
METRIC_KEYS = ("vllm:kv_cache_usage_perc", "vllm:num_requests_running", "vllm:num_requests_waiting",
               "vllm:num_preemptions_total", "sglang:token_usage", "sglang:num_running_reqs",
               "sglang:num_queue_reqs", "sglang:cache_hit_rate", "sglang:num_retracted_reqs")


def clean(m):
    """A message as the agent sent it back to the server (no reasoning or bookkeeping)."""
    out = {"role": m["role"], "content": m.get("content") or ""}
    if m.get("tool_calls"):
        out["tool_calls"] = [{"id": c["id"], "type": "function", "function": c["function"]} for c in m["tool_calls"]]
    if m["role"] == "tool":
        out["tool_call_id"] = m.get("tool_call_id")
    return out


def sessions(pattern, max_prompt=60000):
    """[(trial, [(messages, completion_tokens, recorded_prompt_tokens), ...]), ...] in a fixed order."""
    out = []
    for f in sorted(glob.glob(str(HERE / pattern))):
        msgs = json.load(open(f))["messages"]
        turns = []
        for i, m in enumerate(msgs):
            u = (((m.get("extra") or {}).get("response") or {}).get("usage") or {})
            if m["role"] == "assistant" and u.get("completion_tokens"):
                if u.get("prompt_tokens", 0) > max_prompt:
                    break
                turns.append(([clean(x) for x in msgs[:i]], u["completion_tokens"], u.get("prompt_tokens")))
        if turns:
            out.append((Path(f).parts[-3], turns))
    return out


def request(url, messages, n):
    body = {"model": "agent-model", "messages": messages, "tools": BASH_TOOL, "max_tokens": n,
            "ignore_eos": True, "temperature": 0.6, "stream": True, "stream_options": {"include_usage": True}}
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    t0, ttft, usage = time.time(), None, None
    with urllib.request.urlopen(req, timeout=1800) as r:
        for line in r:
            line = line.strip()
            if not line.startswith(b"data:") or line == b"data: [DONE]":
                continue
            d = json.loads(line[5:])
            if ttft is None and d.get("choices"):
                ttft = time.time() - t0
            if d.get("usage"):
                usage = d["usage"]
    return {"t0": t0, "ttft": ttft, "latency": time.time() - t0, "usage": usage}


def scrape(url, out, stop):
    while not stop.is_set():
        try:
            text = urllib.request.urlopen(url + "/metrics", timeout=10).read().decode()
            vals = {}
            for line in text.splitlines():
                name = line.split("{")[0].split(" ")[0]
                if name in METRIC_KEYS:
                    vals[name] = vals.get(name, 0.0) + float(line.rsplit(" ", 1)[1])
            out.append({"t": time.time(), **vals})
        except Exception:  # noqa: BLE001 - a missed sample is fine
            pass
        stop.wait(10)


def run(url, work, concurrency, duration, gap):
    q = queue.Queue()
    for s in work:
        q.put(s)
    results, lock, deadline = [], threading.Lock(), time.time() + duration

    def worker():
        while time.time() < deadline:
            try:
                trial, turns = q.get_nowait()
            except queue.Empty:
                return
            for msgs, n, rec_prompt in turns:
                if time.time() >= deadline:
                    return
                try:
                    r = request(url, msgs, n)
                    r.update(trial=trial, want=n, recorded_prompt=rec_prompt, error=None)
                except Exception as e:  # noqa: BLE001 - record and move on
                    r = {"trial": trial, "want": n, "error": repr(e)[:200], "t0": time.time()}
                with lock:
                    results.append(r)
                time.sleep(gap)

    threads = [threading.Thread(target=worker) for _ in range(concurrency)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    return results


def summarize(results, samples, duration):
    ok = [r for r in results if not r["error"] and r.get("usage")]
    gen = sum(r["usage"]["completion_tokens"] for r in ok)
    prompt = sum(r["usage"]["prompt_tokens"] for r in ok)
    cached = sum(((r["usage"].get("prompt_tokens_details") or {}).get("cached_tokens") or 0) for r in ok)
    tpot = [(r["latency"] - r["ttft"]) / max(1, r["usage"]["completion_tokens"] - 1) for r in ok if r["ttft"]]
    pk = lambda k: max((s.get(k, 0) for s in samples), default=None)  # noqa: E731
    return {
        "requests_ok": len(ok), "errors": len(results) - len(ok), "gen_tok_per_s": gen / duration,
        "latency_p50_s": st.median(r["latency"] for r in ok) if ok else None,
        "latency_p90_s": st.quantiles([r["latency"] for r in ok], n=10)[-1] if len(ok) > 10 else None,
        "ttft_p50_s": st.median(r["ttft"] for r in ok if r["ttft"]) if ok else None,
        "tpot_p50_ms": 1000 * st.median(tpot) if tpot else None,
        "client_cache_hit": cached / prompt if prompt else None,
        "prompt_vs_recorded": (st.median(r["usage"]["prompt_tokens"] / r["recorded_prompt"] for r in ok
                                         if r.get("recorded_prompt")) if ok else None),
        "kv_peak": pk("vllm:kv_cache_usage_perc") or pk("sglang:token_usage"),
        "running_peak": pk("vllm:num_requests_running") or pk("sglang:num_running_reqs"),
        "waiting_peak": pk("vllm:num_requests_waiting") or pk("sglang:num_queue_reqs"),
        "sglang_cache_hit_last": samples[-1].get("sglang:cache_hit_rate") if samples else None,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--engine", choices=["vllm", "sglang"], required=True)
    ap.add_argument("--name", required=True, help="Modal app suffix ($MODAL_APP_PREFIX-<name>) and record name")
    ap.add_argument("--args", default="{}", help="extra engine flags as JSON")
    ap.add_argument("--gpu", default="H100!")
    ap.add_argument("--concurrency", type=int, default=32)
    ap.add_argument("--duration", type=int, default=720)
    ap.add_argument("--gap", type=float, default=3.0)
    # Recorded traffic: mini-swe-agent trajectories from agentperf-infra's c=32 defaults runs (not published).
    ap.add_argument("--traj", default=os.environ.get(
        "REPLAY_TRAJ_GLOB", "../agentperf-infra/jobs/full*__mini-swe-agent__defaults__c32__*/*/agent/mini-swe-agent.trajectory.json"))
    a = ap.parse_args()

    work = sessions(a.traj)
    print(f"{len(work)} sessions, {sum(len(t) for _, t in work)} turns")
    env = {"RUN_NAME": a.name, "GPU": a.gpu, ("VLLM_ARGS" if a.engine == "vllm" else "SGLANG_ARGS"): a.args}
    app = f"{APP_PREFIX}-{a.name}"
    server = HARNESS / ("serve_vllm.py" if a.engine == "vllm" else "serve_sglang.py")
    t_deploy = time.time()
    dep = subprocess.run(["modal", "deploy", "--env", MODAL_ENV, "--strategy", "recreate", str(server)],
                         env={**__import__("os").environ, **env}, capture_output=True, text=True)
    if dep.returncode:
        raise SystemExit(f"deploy failed:\n{dep.stdout[-2000:]}{dep.stderr[-2000:]}")
    url = ex.endpoint_from_deploy(dep.stdout, app)
    samples, stop = [], threading.Event()
    try:
        while True:  # ready = the OpenAI endpoint lists the model
            try:
                if b"agent-model" in urllib.request.urlopen(url + "/v1/models", timeout=20).read():
                    break
            except Exception:  # noqa: BLE001
                pass
            if time.time() - t_deploy > 15 * 60:
                raise SystemExit("server not ready after 15 min")
            time.sleep(15)
        startup = time.time() - t_deploy
        print(f"ready after {startup:.0f}s: {url}")
        threading.Thread(target=scrape, args=(url, samples, stop), daemon=True).start()
        t0 = time.time()
        results = run(url, work, a.concurrency, a.duration, a.gap)
        dur = time.time() - t0
    finally:
        stop.set()
        subprocess.run(["modal", "app", "stop", "--env", MODAL_ENV, "-y", app], capture_output=True)
    up = time.time() - t_deploy
    price = {"H100!": 3.95, "H200": 4.54, "B200": 6.25}[a.gpu]
    rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime()), "engine": a.engine, "name": a.name,
           "args": json.loads(a.args), "gpu": a.gpu, "concurrency": a.concurrency, "duration_s": dur, "gap_s": a.gap,
           "startup_s": startup, "up_s": up, "cost": up / 3600 * price, **summarize(results, samples, dur)}
    with OUT.open("a") as f:
        f.write(json.dumps(rec) + "\n")
    (HERE / "jobs").mkdir(exist_ok=True)
    Path(HERE / "jobs" / f"bench-{a.name}.json").write_text(json.dumps({"results": results, "samples": samples}))
    print(json.dumps(rec, indent=1))


if __name__ == "__main__":
    main()
