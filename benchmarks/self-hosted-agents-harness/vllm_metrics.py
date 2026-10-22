"""
Sample vLLM's Prometheus /metrics during a run and summarize what the server did.

experiment.py starts a Scraper while Harbor runs and stores summarize() in the run's
record under "vllm". Raw samples go to jobs/<job-name>.metrics.jsonl.

To attach to a server that is already running:
    python vllm_metrics.py <base-url> jobs/<job-name>.metrics.jsonl
It stops when the server has been unreachable for 2 minutes (the run ended).
"""

import json
import re
import sys
import threading
import time
import urllib.request
from pathlib import Path

GAUGES = ["num_requests_running", "num_requests_waiting", "kv_cache_usage_perc"]
COUNTERS = [
    "prompt_tokens_total", "generation_tokens_total", "prefix_cache_queries_total",
    "prefix_cache_hits_total", "num_preemptions_total", "request_success_total",
    "spec_decode_num_draft_tokens_total", "spec_decode_num_accepted_tokens_total",
]
# Histograms: mean = delta(sum) / delta(count) over the run.
HISTOGRAMS = ["time_to_first_token_seconds", "inter_token_latency_seconds",
              "request_queue_time_seconds", "e2e_request_latency_seconds",
              "request_prefill_time_seconds", "request_decode_time_seconds"]
WANTED = set(GAUGES + COUNTERS + [f"{h}_{s}" for h in HISTOGRAMS for s in ("sum", "count")])
LINE = re.compile(r"^vllm:([a-z_]+)(?:\{[^}]*\})?\s+([0-9.eE+-]+|NaN)$")


def parse(text: str) -> dict:
    """Prometheus text -> {metric: value}, summed over label sets (one engine here)."""
    out: dict = {}
    for line in text.splitlines():
        m = LINE.match(line)
        if m and m.group(1) in WANTED and m.group(2) != "NaN":
            out[m.group(1)] = out.get(m.group(1), 0.0) + float(m.group(2))
    return out


def fetch(base: str, timeout: float = 10) -> dict:
    with urllib.request.urlopen(f"{base}/metrics", timeout=timeout) as r:
        return parse(r.read().decode())


class Scraper:
    """Background thread: one sample every `interval` seconds, appended to `path`."""

    def __init__(self, base: str, path: Path, interval: float = 10):
        self.base, self.path, self.interval = base, path, interval
        self.samples: list[dict] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def _run(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a") as f:
            while not self._stop.is_set():
                try:
                    s = {"t": time.time(), **fetch(self.base)}
                    self.samples.append(s)
                    f.write(json.dumps(s) + "\n")
                    f.flush()
                except Exception:  # noqa: BLE001 - a missed sample is fine
                    pass
                self._stop.wait(self.interval)

    def start(self):
        self._thread.start()
        return self

    def stop(self, t0: float | None = None) -> dict | None:
        self._stop.set()
        self._thread.join(timeout=30)
        return summarize(self.samples, t0)


def load(path: Path) -> list[dict]:
    if not path.exists():
        return []
    return [json.loads(l) for l in path.read_text().splitlines() if l.strip()]


def summarize(samples: list[dict], t0: float | None = None) -> dict | None:
    """What the server did during the run. Every run starts a fresh server that serves
    nothing before the run, so counters are totals since zero; t0 = run start (defaults
    to the first sample). Gauges are averaged over the samples."""
    if len(samples) < 2:
        return None
    last = samples[-1]
    secs = last["t"] - (t0 if t0 is not None else samples[0]["t"])

    def d(k):
        return last.get(k, 0.0)

    def mean_hist(h):
        n = d(f"{h}_count")
        return d(f"{h}_sum") / n if n > 0 else None

    def gauge(k):
        vals = [s[k] for s in samples if k in s]
        return (sum(vals) / len(vals), max(vals)) if vals else (None, None)

    running_mean, running_max = gauge("num_requests_running")
    waiting_mean, waiting_max = gauge("num_requests_waiting")
    kv_mean, kv_max = gauge("kv_cache_usage_perc")
    busy = [s for s in samples if "num_requests_running" in s]
    pq, draft = d("prefix_cache_queries_total"), d("spec_decode_num_draft_tokens_total")
    r = lambda v, n=3: None if v is None else round(v, n)  # noqa: E731
    return {
        "samples": len(samples), "seconds": round(secs),
        # Share of samples with at least one request on the GPU; the rest is time the
        # GPU sat idle while every agent was running tools, installing or being set up.
        "busy_frac": r(sum(s["num_requests_running"] > 0 for s in busy) / len(busy)) if busy else None,
        "running_mean": r(running_mean, 2), "running_max": running_max,
        "waiting_mean": r(waiting_mean, 2), "waiting_max": waiting_max,
        "kv_usage_mean": r(kv_mean), "kv_usage_max": r(kv_max),
        "preemptions": d("num_preemptions_total"),
        "requests": d("request_success_total"),
        "prompt_tokens": d("prompt_tokens_total"), "generation_tokens": d("generation_tokens_total"),
        "prefix_hit_rate": r(d("prefix_cache_hits_total") / pq) if pq > 0 else None,
        "gen_tok_per_s": r(d("generation_tokens_total") / secs, 1) if secs > 0 else None,
        "ttft_mean_s": r(mean_hist("time_to_first_token_seconds")),
        "itl_mean_ms": r(1000 * mean_hist("inter_token_latency_seconds"), 1)
        if mean_hist("inter_token_latency_seconds") is not None else None,
        "queue_mean_s": r(mean_hist("request_queue_time_seconds")),
        "e2e_mean_s": r(mean_hist("e2e_request_latency_seconds")),
        "prefill_mean_s": r(mean_hist("request_prefill_time_seconds")),
        "decode_mean_s": r(mean_hist("request_decode_time_seconds")),
        "spec_accept_rate": r(d("spec_decode_num_accepted_tokens_total") / draft) if draft > 0 else None,
    }


if __name__ == "__main__":
    base, out = sys.argv[1].rstrip("/"), Path(sys.argv[2])
    out.parent.mkdir(parents=True, exist_ok=True)
    misses = 0
    with out.open("a") as f:
        while misses < 12:
            try:
                f.write(json.dumps({"t": time.time(), **fetch(base)}) + "\n")
                f.flush()
                misses = 0
            except Exception:  # noqa: BLE001
                misses += 1
            time.sleep(10)
    print(json.dumps(summarize(load(out)), indent=2))
