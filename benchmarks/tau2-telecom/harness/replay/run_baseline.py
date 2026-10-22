"""Record baseline tau2-bench Telecom episodes into Kitaru (one session per test-split case).

  KITARU_API_URL=... TAU2_DATA_DIR=... TAU2_AGENT_VERSION_ID=... uv run python run_baseline.py --tag baseline

Each case runs in its own process (python -m tau2_kitaru_agent.episode). Rows are appended to
results/<tag>.jsonl; a case already present in that file is skipped, so a rerun resumes.
"""
import argparse
import asyncio
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))


async def run_case(case: int, tag: str, sem: asyncio.Semaphore, out_path: str) -> None:
    async with sem:
        env = dict(os.environ, TAU2_CASE=str(case), TAU2_RUN_TAG=tag)
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", "tau2_kitaru_agent.episode", cwd=HERE, env=env,
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
        stdout, _ = await proc.communicate()
        lines = [line for line in stdout.decode().splitlines() if line.startswith("{")]
        row = json.loads(lines[-1]) if lines else {"case": case, "run_error": f"exit {proc.returncode}, no output"}
        row["tag"] = tag
        with open(out_path, "a") as f:
            f.write(json.dumps(row) + "\n")
        print(case, (row.get("tau2") or {}).get("reward"), row.get("run_error"), flush=True)


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True)
    ap.add_argument("--cases", default="0-39")
    ap.add_argument("--concurrency", type=int, default=8)
    a = ap.parse_args()
    lo, hi = (int(x) for x in a.cases.split("-"))
    out_path = os.path.join(HERE, "results", f"{a.tag}.jsonl")
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    done = set()
    if os.path.exists(out_path):
        done = {json.loads(line)["case"] for line in open(out_path)}
    sem = asyncio.Semaphore(a.concurrency)
    await asyncio.gather(*(run_case(c, a.tag, sem, out_path) for c in range(lo, hi + 1) if c not in done))


if __name__ == "__main__":
    asyncio.run(main())
