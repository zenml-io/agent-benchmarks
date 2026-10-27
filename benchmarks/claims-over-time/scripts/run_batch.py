"""Run one agent version on the appeals of one batch (or a list of ids) and append one row per appeal.

    uv run --extra agent python scripts/run_batch.py --agent-dir harness/claims_agent --tag v1-b1 --batch 1
    uv run --extra agent python scripts/run_batch.py --agent-dir DIR --tag t --ids MN25-1,MN25-2
    uv run --extra agent python scripts/run_batch.py --tag v1-b1 --batch 1 --kitaru-agent-version <AGENT_VERSION_ID>

Local mode (the default) runs `python -m <package>.episode <id> --local` in the agent directory's
parent, one process per appeal, with no Kitaru server. Kitaru mode asks the server for one session
run per appeal ("Review appeal <id>."); a worker runs the registered agent version's command, and the
row is read back from the task result. Rows go to $CLAIMS_WORK_DIR/runs/<tag>.jsonl, or to --out. An appeal that
already has a row there is skipped, so a rerun resumes; --retry-errors reruns appeals whose row has a
run_error.
"""

import argparse
import asyncio
import json
import os
import sys
import uuid
from pathlib import Path
from typing import Any

BENCH = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("CLAIMS_WORK_DIR") or BENCH / "work")
TERMINAL = {"completed", "failed", "canceled"}


def jl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open() if line.strip()] if path.exists() else []


def append(path: Path, row: dict[str, Any]) -> None:
    with path.open("a") as f:
        f.write(json.dumps(row) + "\n")
    final = row.get("final") or {}
    print(row["case_id"], final.get("decision"), row.get("turns"), (row.get("run_error") or "")[:120], flush=True)


async def run_local(case_id: str, agent_dir: Path, sem: asyncio.Semaphore) -> dict[str, Any]:
    async with sem:
        proc = await asyncio.create_subprocess_exec(
            sys.executable, "-m", f"{agent_dir.name}.episode", case_id, "--local", cwd=agent_dir.parent,
            env=dict(os.environ, CLAIMS_WORK_DIR=str(WORK)), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
        stdout, stderr = await proc.communicate()
    lines = [line for line in stdout.decode().splitlines() if line.startswith("{")]
    if lines:
        return json.loads(lines[-1])
    return {"case_id": case_id, "final": None, "run_error": f"exit {proc.returncode}, no row: {stderr.decode()[-400:]}"}


async def run_kitaru(case_id: str, tag: str, version_id: uuid.UUID, client: Any) -> dict[str, Any]:
    from kitaru.api_models.v1.filter import FilterCondition, FilterOp
    from kitaru.api_models.v1.session import SessionListParams
    from kitaru.api_models.v1.session_run import SessionRunCreateRequest

    job = await client.session_runs.create(SessionRunCreateRequest(
        agent_version_id=version_id, inputs=f"Review appeal {case_id}.", name=f"claims {tag} {case_id}"))
    while job.status.value not in TERMINAL:
        await asyncio.sleep(5)
        job = await client.jobs.get(job.id)
    tasks = (await client.jobs.list_tasks(job.id)).items
    task = tasks[-1] if tasks else None
    row: dict[str, Any] = task.result if task is not None and isinstance(task.result, dict) and task.result.get("case_id") else \
        {"case_id": case_id, "final": None, "run_error": f"job {job.status.value}: {job.error or (task.error if task else '')}"[:500]}
    row["kitaru_job_id"] = str(job.id)
    if task is not None:
        sessions = (await client.sessions.list(SessionListParams(
            filter=FilterCondition(field="task_id", op=FilterOp.EQ, value=str(task.id))))).items
        if sessions:
            s = sessions[0]
            row |= {"session_id": str(s.id), "session_status": s.status.value,
                    "kitaru_cost_usd": float(s.cost) if s.cost is not None else None}
    return row


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--tag", required=True, help="output file name: runs/<tag>.jsonl")
    ap.add_argument("--out", type=Path, help="write rows to this file instead of $CLAIMS_WORK_DIR/runs/<tag>.jsonl")
    ap.add_argument("--agent-dir", type=Path, default=BENCH / "harness" / "claims_agent", help="the agent package directory (local mode)")
    pick = ap.add_mutually_exclusive_group(required=True)
    pick.add_argument("--batch", type=int, help="every appeal of this batch in cases.jsonl")
    pick.add_argument("--ids", help="comma-separated appeal ids")
    ap.add_argument("--revealed-only", action="store_true", help="with --batch: only the revealed appeals")
    ap.add_argument("--kitaru-agent-version", type=uuid.UUID, help="run through Kitaru as this registered agent version")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--retry-errors", action="store_true")
    a = ap.parse_args()

    cases = jl(WORK / "cases.jsonl")
    if a.ids:
        ids = a.ids.split(",")
    else:
        ids = [c["id"] for c in sorted(cases, key=lambda c: c["order"])
               if c["batch"] == a.batch and (c["revealed"] or not a.revealed_only)]
    out = a.out or WORK / "runs" / f"{a.tag}.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)
    rows = jl(out)
    if a.retry_errors:
        rows = [r for r in rows if not r.get("run_error")]
        out.write_text("".join(json.dumps(r) + "\n" for r in rows))
    done = {r["case_id"] for r in rows}
    todo = [i for i in ids if i not in done]
    print(f"{len(ids)} appeals, {len(ids) - len(todo)} already in {out}, running {len(todo)}", flush=True)
    meta = {"tag": a.tag, "kitaru_agent_version": str(a.kitaru_agent_version) if a.kitaru_agent_version else None}

    async def one(case_id: str, fn: Any) -> None:
        append(out, await fn(case_id) | meta)

    if a.kitaru_agent_version:
        from kitaru.client import KitaruAPIClient

        async with KitaruAPIClient() as client:
            sem = asyncio.Semaphore(a.concurrency)

            async def via_kitaru(case_id: str) -> dict[str, Any]:
                async with sem:
                    return await run_kitaru(case_id, a.tag, a.kitaru_agent_version, client)

            await asyncio.gather(*(one(i, via_kitaru) for i in todo))
    else:
        sem = asyncio.Semaphore(a.concurrency)
        agent_dir = a.agent_dir.resolve()
        await asyncio.gather(*(one(i, lambda c: run_local(c, agent_dir, sem)) for i in todo))


if __name__ == "__main__":
    asyncio.run(main())
