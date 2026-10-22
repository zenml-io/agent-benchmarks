"""A local stand-in for the three Kitaru server endpoints the PydanticAI adapter writes to.

The pinned Kitaru (0.27.2+dev at 0217140c) can only record to a server: `KitaruAgent` creates a
`KitaruAPIClient` per run and calls

    POST  /api/v1/sessions               create the session
    POST  /api/v1/sessions/{id}/nodes    ingest node batches (LLM calls, tool calls, the run span)
    PATCH /api/v1/sessions/{id}          finish the session

This sink answers those calls on 127.0.0.1 inside the sandbox and appends every request body, unchanged,
to `requests.jsonl`; at the end `session.json` holds the session as a server would store it (last write
of each node wins, as the server's ingest does). Responses are built and validated with Kitaru's own
response models, so the real client code path runs. Any other call gets a 404, which fails the recording
loudly instead of guessing. `upload_recordings.py` sends the recorded requests to a real server later.
"""

import json
import re
import threading
import uuid
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from kitaru.api_models.v1.session import SessionResponse
from kitaru.api_models.v1.session_node import SessionNodeResponse

PLACEHOLDER_ID = "00000000-0000-0000-0000-000000000000"  # agent and owner ids the sink has no server for
_NODES = re.compile(r"^/api/v1/sessions/([0-9a-f-]{36})/nodes$")
_SESSION = re.compile(r"^/api/v1/sessions/([0-9a-f-]{36})$")


def _now() -> str:
    return datetime.now(UTC).isoformat()


class KitaruSink:
    """Threaded HTTP sink; use as a context manager. `url` is the base URL for KITARU_API_URL."""

    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.out_dir.mkdir(parents=True, exist_ok=True)
        self.requests_path = out_dir / "requests.jsonl"
        self.sessions: dict[str, dict[str, Any]] = {}
        self.nodes: dict[str, dict[str, dict[str, Any]]] = {}
        self.lock = threading.Lock()
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), self._handler())
        self.url = f"http://127.0.0.1:{self.server.server_address[1]}"
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self) -> "KitaruSink":
        self.thread.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.server.shutdown()
        self.server.server_close()
        self.write_sessions()

    def write_sessions(self) -> None:
        with self.lock:
            sessions = [{"session": s, "nodes": list(self.nodes.get(sid, {}).values())}
                        for sid, s in self.sessions.items()]
        (self.out_dir / "session.json").write_text(json.dumps(sessions, indent=2, default=str))

    def _record(self, method: str, path: str, body: Any) -> None:
        line = json.dumps({"received_at": _now(), "method": method, "path": path, "body": body})
        with self.lock, self.requests_path.open("a") as f:
            f.write(line + "\n")

    def _session_response(self, stored: dict[str, Any]) -> dict[str, Any]:
        nodes = self.nodes.get(stored["id"], {}).values()
        response = {
            **stored,
            "agent_id": stored.get("agent_id") or PLACEHOLDER_ID,
            "owner_id": PLACEHOLDER_ID,
            "number": stored["number"],
            "status": stored.get("status") or "in_progress",
            "metadata": stored.get("metadata") or {},
            "llm_call_count": sum(n.get("node_type") == "llm_call" for n in nodes),
            "tool_call_count": sum(n.get("node_type") == "tool_call" for n in nodes),
        }
        return SessionResponse.model_validate(response).model_dump(mode="json")

    def create_session(self, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            sid = str(uuid.uuid4())
            self.sessions[sid] = {**body, "id": sid, "number": len(self.sessions) + 1, "created": _now(),
                                  "updated": _now()}
            self.nodes[sid] = {}
            return self._session_response(self.sessions[sid])

    def ingest(self, sid: str, body: dict[str, Any]) -> list[dict[str, Any]]:
        out = []
        with self.lock:
            for node in body.get("nodes", []):
                stored = {"links": [], "reasoning_selectors": [], "metadata": {}, "attributes": None, **node,
                          "id": str(uuid.uuid4()), "session_id": sid}
                self.nodes[sid][node["external_id"]] = stored
                out.append(SessionNodeResponse.model_validate(stored).model_dump(mode="json"))
        return out

    def update_session(self, sid: str, body: dict[str, Any]) -> dict[str, Any]:
        with self.lock:
            self.sessions[sid] |= body | {"updated": _now()}
            return self._session_response(self.sessions[sid])

    def _handler(self) -> type[BaseHTTPRequestHandler]:
        sink = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def _reply(self, status: int, payload: Any) -> None:
                data = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _handle(self, method: str) -> None:
                raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
                body = json.loads(raw) if raw else None
                path = self.path.split("?", 1)[0]
                sink._record(method, path, body)
                try:
                    if method == "POST" and path == "/api/v1/sessions":
                        return self._reply(201, sink.create_session(body))
                    if method == "POST" and (m := _NODES.match(path)) and m.group(1) in sink.sessions:
                        return self._reply(200, sink.ingest(m.group(1), body))
                    if method == "PATCH" and (m := _SESSION.match(path)) and m.group(1) in sink.sessions:
                        return self._reply(200, sink.update_session(m.group(1), body))
                except Exception as exc:  # noqa: BLE001
                    return self._reply(500, {"detail": f"recording sink: {exc!r}"})
                self._reply(404, {"detail": f"recording sink does not serve {method} {path}"})

            def do_POST(self) -> None:
                self._handle("POST")

            def do_PATCH(self) -> None:
                self._handle("PATCH")

            def do_GET(self) -> None:
                self._handle("GET")

            def log_message(self, *args: object) -> None:
                return

        return Handler
