"""
Turn each candidate's Findings text into a facts-only case file, with the model, prompt and sampling
settings that decision-agents used.

    uv run --extra modal python harness/extract/extract.py all [--limit N]   # deploy, extract, stop
    uv run --extra modal python harness/extract/extract.py up                # deploy; prints the URL
    uv run python harness/extract/extract.py run --url URL [--limit N]       # extract on a running server
    uv run --extra modal python harness/extract/extract.py down              # stop the server

Reads $CLAIMS_WORK_DIR/candidates.jsonl (scripts/build_stream.py) and appends one row per candidate
to $CLAIMS_WORK_DIR/case_files.jsonl: {id, case_file, leak, error}. A rerun skips every ID already in
that file, so an interrupted run resumes where it stopped; --retry-failed redoes the rows with an
error. Deploying needs MODAL_ENVIRONMENT and a logged-in Modal CLI. The server scales to zero: the GPU
bills from the first request (the readiness check in `up` sends it) until 20 minutes after the last
one, or until `down`; `all` always stops the server, even on failure or Ctrl-C.
"""

import argparse
import json
import os
import re
import subprocess
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
BENCH = HERE.parent.parent
WORK = Path(os.environ.get("CLAIMS_WORK_DIR") or BENCH / "work")
OUT = WORK / "case_files.jsonl"
APP_NAME = f"{os.environ.get('MODAL_APP_PREFIX', 'agent')}-claims-extract"
H100_PER_HOUR = 3.95  # Modal list price, Oct 2026

# EXTRACT and LEAK are verbatim from benchmarks/decision-agents/harness/claims_bench.py at commit
# 2542d57148afd627dc123827b4dbb924f470d8e5 of zenml-io/agent-benchmarks.
EXTRACT = """You turn an insurance medical-review decision into a neutral case file for a new reviewer.
Keep ONLY facts: what treatment or service was requested, the patient's diagnosis and condition,
relevant history, test results, symptoms, and treatments already tried and how they went.
Leave out everything the original reviewer concluded or argued: no opinions, no guidelines or
studies, no statements about necessity, appropriateness, evidence or outcome. Do not hint at the
decision. Write JSON only: {"request": "...", "condition": "...", "history": ["fact", ...],
"prior_treatments": ["fact", ...]}. Use plain clinical language."""
LEAK = re.compile(r"medically necessary|not necessary|is indicated|not indicated|is appropriate|not appropriate|"
                  r"uphold|upheld|overturn|denial should|should be (approved|denied|covered)|"
                  r"is supported|not supported|reviewer (found|determined|concluded)|guideline", re.I)


def jl(path: Path) -> list[dict]:
    return [json.loads(x) for x in open(path) if x.strip()] if path.exists() else []


def chat(url: str, messages: list[dict], max_tokens: int, temperature: float) -> dict:
    """One chat completion, with the original harness's three tries and 15-minute timeout."""
    body = {"model": "agent-model", "messages": messages, "max_tokens": max_tokens, "temperature": temperature}
    req = urllib.request.Request(url + "/v1/chat/completions", json.dumps(body).encode(),
                                 {"Content-Type": "application/json"})
    for attempt in range(3):
        try:
            return json.loads(urllib.request.urlopen(req, timeout=900).read())
        except Exception:
            if attempt == 2:
                raise
            time.sleep(5)
    raise AssertionError("unreachable")


def extract_one(url: str, cand: dict) -> tuple[dict, dict]:
    """Return the case-file row and the call's token usage. Parsing and the leak check match the original."""
    try:
        r = chat(url, [{"role": "system", "content": EXTRACT}, {"role": "user", "content": cand["findings"]}],
                 max_tokens=6000, temperature=0.0)
        text = r["choices"][0]["message"]["content"] or ""
        m = re.search(r"\{.*\}", text, re.S)
        cf = json.loads(m.group(0)) if m else None
    except Exception as e:  # noqa: BLE001
        return {"id": cand["id"], "case_file": None, "leak": None, "error": repr(e)[:300]}, {}
    row = {"id": cand["id"], "case_file": cf, "leak": bool(LEAK.search(json.dumps(cf))) if cf else None,
           "error": None if cf else f"no JSON object in the reply (finish_reason={r['choices'][0].get('finish_reason')})"}
    return row, r.get("usage") or {}


def summarize(rows: list[dict]) -> str:
    failed = sum(1 for r in rows if not r["case_file"])
    leaked = sum(1 for r in rows if r["leak"])
    return (f"{len(rows)} rows in {OUT.name}: {failed} failed, {leaked} dropped for leaking words, "
            f"{len(rows) - failed - leaked} usable")


def run(url: str, limit: int | None, concurrency: int, retry_failed: bool) -> None:
    url = url.rstrip("/").removesuffix("/v1")
    done = {r["id"]: r for r in jl(OUT)}
    if retry_failed:
        done = {i: r for i, r in done.items() if not r["error"]}
        with OUT.open("w") as f:  # drop the failed rows so each ID keeps one row
            f.writelines(json.dumps(r) + "\n" for r in done.values())
    todo = [c for c in jl(WORK / "candidates.jsonl") if c["id"] not in done][:limit]
    print(f"{len(done)} already extracted; extracting {len(todo)} at concurrency {concurrency}", flush=True)
    lock, tokens, t0 = threading.Lock(), {"prompt": 0, "completion": 0}, time.time()
    with OUT.open("a") as f, ThreadPoolExecutor(concurrency) as pool:
        futures = [pool.submit(extract_one, url, c) for c in todo]
        for n, fut in enumerate(as_completed(futures), 1):
            row, usage = fut.result()
            with lock:
                f.write(json.dumps(row) + "\n")
                f.flush()
                tokens["prompt"] += usage.get("prompt_tokens", 0)
                tokens["completion"] += usage.get("completion_tokens", 0)
            if n % 50 == 0 or n == len(todo):
                el = time.time() - t0
                print(f"  {n}/{len(todo)} in {el:.0f}s ({tokens['completion'] / max(el, 1):.0f} completion tok/s)",
                      flush=True)
    el = time.time() - t0
    print(f"extraction took {el:.0f}s; tokens: {tokens['prompt']} prompt, {tokens['completion']} completion; "
          f"{summarize(jl(OUT))}", flush=True)


def modal_env() -> str:
    env = os.environ.get("MODAL_ENVIRONMENT")
    if not env:
        raise SystemExit("set MODAL_ENVIRONMENT to the Modal environment to deploy into")
    return env


def endpoint_from_deploy(output: str) -> str:
    """Read the endpoint URL from `modal deploy` output (its host depends on the workspace)."""
    output = re.sub(r"\x1b\[[0-9;]*m", "", output)
    output = re.sub(r"\n[ \t]+", "", output)  # Rich wraps long URLs onto indented lines
    urls = re.findall(r"https://[a-z0-9.-]+\.modal\.(?:run|direct)", output)
    match = [u for u in urls if APP_NAME in u] or urls
    if not match:
        raise RuntimeError(f"no endpoint URL in `modal deploy` output:\n{output[-2000:]}")
    return match[-1]


def up() -> str:
    t0 = time.time()
    print(f"deploying {APP_NAME} at {time.strftime('%H:%M:%S')} (the GPU bills from the first request until 20 min after the last)", flush=True)
    dep = subprocess.run(["modal", "deploy", "--env", modal_env(), "--strategy", "recreate", str(HERE / "serve.py")],
                         env={**os.environ, "COLUMNS": "400"}, text=True, capture_output=True, cwd=BENCH,
                         check=False)
    if dep.returncode != 0:
        raise RuntimeError(f"modal deploy failed:\n{dep.stdout[-1500:]}{dep.stderr[-1500:]}")
    url = endpoint_from_deploy(dep.stdout + dep.stderr)
    while time.time() - t0 < 40 * 60:
        try:
            if b"agent-model" in urllib.request.urlopen(url + "/v1/models", timeout=20).read():
                print(f"ready after {time.time() - t0:.0f}s: {url}", flush=True)
                return url
        except Exception:  # noqa: BLE001
            pass
        time.sleep(15)
    raise TimeoutError(f"{url} not ready after 40 min")


def down() -> None:
    subprocess.run(["modal", "app", "stop", "--env", modal_env(), "-y", APP_NAME], cwd=BENCH, check=False)
    print(f"stopped {APP_NAME} at {time.strftime('%H:%M:%S')}", flush=True)


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("cmd", choices=["all", "up", "run", "down"])
    p.add_argument("--url", default=os.environ.get("EXTRACT_BASE_URL"), help="base URL of a running server (run)")
    p.add_argument("--limit", type=int, help="extract at most this many new candidates, in filing order")
    p.add_argument("--concurrency", type=int, default=32, help="requests in flight (the original used 32)")
    p.add_argument("--retry-failed", action="store_true", help="redo rows that have an error")
    a = p.parse_args()
    if a.cmd == "up":
        up()
    elif a.cmd == "down":
        down()
    elif a.cmd == "run":
        if not a.url:
            raise SystemExit("run needs --url or EXTRACT_BASE_URL")
        run(a.url, a.limit, a.concurrency, a.retry_failed)
    else:
        t0 = time.time()
        try:
            run(up(), a.limit, a.concurrency, a.retry_failed)
        finally:
            down()
            hours = (time.time() - t0) / 3600
            print(f"server up for {hours * 60:.1f} min, about ${hours * H100_PER_HOUR:.2f} of H100 time "
                  f"at ${H100_PER_HOUR}/hour", flush=True)


if __name__ == "__main__":
    main()
