"""Send the Kitaru recordings Harbor collected to a Kitaru server, one session per trial.

    KITARU_API_URL=http://localhost:8000 uv run --extra replay python harbor/scripts/upload_recordings.py \
        <jobs-dir>/<job-name> --agent-id <uuid> [--agent-version-id <uuid>] [--dry-run]

Each trial folder holds `agent/kitaru/requests.jsonl`: the exact request bodies the PydanticAI adapter
sent to the in-sandbox sink, in order (create session, node batches, finish). This script resends them
with Kitaru's own client, mapping the sink's session ids to the server's and setting the agent (the sink
recorded none, because the trial had no server to register an agent on). Trials already uploaded are
listed in `<job>/kitaru-uploaded.json` and skipped. Checked against the in-sandbox sink only; not yet run
against a real Kitaru server.
"""

import argparse
import asyncio
import json
import re
from pathlib import Path

from kitaru.client import KitaruAPIClient

SESSION_PATH = re.compile(r"^/api/v1/sessions/([0-9a-f-]{36})(/nodes)?$")


async def upload_trial(client: KitaruAPIClient, requests: list[dict], agent_id: str, version_id: str | None) -> list[str]:
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
    client = KitaruAPIClient() if not a.dry_run else None
    try:
        for trial in trials:
            if trial.name in done:
                continue
            requests = [json.loads(line) for line in (trial / "agent/kitaru/requests.jsonl").read_text().splitlines()]
            if a.dry_run:
                print(trial.name, len(requests), "requests")
                continue
            done[trial.name] = await upload_trial(client, requests, a.agent_id, a.agent_version_id)
            done_path.write_text(json.dumps(done, indent=2))
            print(trial.name, "->", done[trial.name])
    finally:
        if client is not None:
            await client.close()


if __name__ == "__main__":
    asyncio.run(main())
