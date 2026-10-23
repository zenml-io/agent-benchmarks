"""Send the Kitaru recordings Harbor collected to a Kitaru server, one session per trial.

    KITARU_API_URL=http://localhost:8000 uv run --extra replay python harbor/scripts/upload_recordings.py \
        <jobs-dir>/<job-name> --agent-id <uuid> [--agent-version-id <uuid>] [--dry-run]

Each trial folder holds `agent/kitaru/requests.jsonl`: the exact request bodies the PydanticAI adapter
sent to the in-sandbox sink, in order (create session, node batches, finish). This script resends them
with Kitaru's own client, mapping the sink's session ids to the server's and setting the agent (the sink
recorded none, because the trial had no server to register an agent on). Trials already uploaded are
listed in `<job>/kitaru-uploaded.json` and skipped. Checked against the in-sandbox sink only; not yet run
against a real Kitaru server.

Harbor grades a trial in its verifier after the agent has finished, so the recording itself holds no
grade. The upload adds it: the session's final outputs get a `tau2` object (the verifier's reward, the
tau2 task id, the termination reason) in the shape the original episode wrote, so the
`tau2-task-success` evaluator in `harness/replay/tau2_reward_evaluator.py` scores uploaded sessions the
same way as sessions recorded by the original harness. A trial without a verifier reward (an
infrastructure error) is uploaded without one and that evaluator counts it as failed.
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

from kitaru.client import KitaruAPIClient

TASK_INDEX = Path(__file__).resolve().parents[1] / "tasks" / "index.json"
SESSION_PATH = re.compile(r"^/api/v1/sessions/([0-9a-f-]{36})(/nodes)?$")


def harbor_grade(trial: Path, task_ids: dict[str, str]) -> dict | None:
    """The verifier's grade of one trial as the original episode's `tau2` output, or None if it has none."""
    result = json.loads((trial / "result.json").read_text()) if (trial / "result.json").exists() else {}
    reward = ((result.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    if reward is None:
        return None
    task = Path(json.loads((trial / "config.json").read_text())["task"]["path"]).name
    summary_path = trial / "agent" / "tau2-kitaru-agent.json"
    summary = json.loads(summary_path.read_text()) if summary_path.exists() else {}
    return {"task_id": task_ids.get(task), "harbor_task": task, "split": "test", "reward": float(reward),
            "termination_reason": (summary.get("runtime") or {}).get("termination_reason"),
            "graded_by": "harbor verifier"}


def with_grade(outputs: object, grade: dict) -> object:
    """Recorded session outputs (`{"answer": ...}`, as a JSON string or object) with the grade added."""
    parsed = outputs
    if isinstance(outputs, str):
        try:
            parsed = json.loads(outputs)
        except ValueError:
            parsed = {"answer": outputs}
    merged = (parsed if isinstance(parsed, dict) else {"answer": parsed}) | {"tau2": grade}
    return json.dumps(merged) if isinstance(outputs, str) else merged


async def upload_trial(client: KitaruAPIClient, requests: list[dict], agent_id: str, version_id: str | None,
                       grade: dict | None = None) -> list[str]:
    ids: dict[str, str] = {}  # sink session id -> server session id
    created: str | None = None  # server id of the session created last and not yet mapped
    for request in requests:
        method, path, body = request["method"], request["path"], request["body"]
        if method == "POST" and path == "/api/v1/sessions":
            body = body | {"agent_id": agent_id, "agent_version_id": version_id or body.get("agent_version_id")}
            created = (await client.request("POST", path, json=body)).json()["id"]
            continue
        match = SESSION_PATH.match(path)
        if not match:
            raise SystemExit(f"unexpected recorded request {method} {path}")
        local = match.group(1)
        if local not in ids:
            if created is None:
                raise SystemExit(f"request for unknown session {local}")
            ids[local], created = created, None
        if grade is not None and method == "PATCH" and not match.group(2) and "outputs" in body:
            body = body | {"outputs": with_grade(body["outputs"], grade)}
        await client.request(method, path.replace(local, ids[local]), json=body)
    return list(ids.values())


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("job", type=Path)
    ap.add_argument("--agent-id", required=True)
    ap.add_argument("--agent-version-id")
    ap.add_argument("--dry-run", action="store_true", help="list what would be sent")
    a = ap.parse_args()
    done_path = a.job / "kitaru-uploaded.json"
    done = json.loads(done_path.read_text()) if done_path.exists() else {}
    trials = sorted(p.parents[2] for p in a.job.glob("*/agent/kitaru/requests.jsonl"))
    task_ids = {t["task"]: t["tau2_task_id"] for t in json.loads(TASK_INDEX.read_text())["tasks"]}
    client = KitaruAPIClient() if not a.dry_run else None
    try:
        for trial in trials:
            if trial.name in done:
                continue
            requests = [json.loads(line) for line in (trial / "agent/kitaru/requests.jsonl").read_text().splitlines()]
            grade = harbor_grade(trial, task_ids)
            reward = "no verifier reward" if grade is None else f"reward {grade['reward']}"
            if a.dry_run:
                print(trial.name, len(requests), "requests,", reward)
                continue
            done[trial.name] = await upload_trial(client, requests, a.agent_id, a.agent_version_id, grade)
            done_path.write_text(json.dumps(done, indent=2))
            print(trial.name, "->", done[trial.name], reward)
    finally:
        if client is not None:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
