#!/usr/bin/env bash
# Reference solution: submit Snorkel's reference answer.
set -euo pipefail
python3 - <<'PY'
"""A minimal MCP client over streamable HTTP, standard library only.

It runs inside the task's main container (python:3.12-slim, nothing installed), for the copilot runner and the
reference and shortcut solutions. It handles plain JSON and server-sent-event replies.
"""
import json
import urllib.request


class MCPClient:
    def __init__(self, url, timeout=300):
        self.url, self.timeout, self.session, self.n = url, timeout, None, 0

    def _post(self, payload):
        headers = {"Content-Type": "application/json", "Accept": "application/json, text/event-stream"}
        if self.session:
            headers["mcp-session-id"] = self.session
        req = urllib.request.Request(self.url, data=json.dumps(payload).encode(), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as r:
            self.session = r.headers.get("mcp-session-id") or self.session
            body = r.read().decode()
            ctype = r.headers.get("content-type", "")
        if "id" not in payload or not body.strip():
            return None
        if ctype.startswith("text/event-stream"):
            msgs = [json.loads(line[5:]) for line in body.splitlines() if line.startswith("data:") and line[5:].strip()]
            msg = next(m for m in msgs if m.get("id") == payload["id"])
        else:
            msg = json.loads(body)
        if "error" in msg:
            raise RuntimeError(f"MCP error: {msg['error']}")
        return msg["result"]

    def request(self, method, params=None):
        self.n += 1
        return self._post({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})

    def initialize(self):
        res = self.request("initialize", {"protocolVersion": "2025-06-18", "capabilities": {},
                                          "clientInfo": {"name": "underwriting-client", "version": "0.1"}})
        self._post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        return res

    def list_tools(self):
        return self.request("tools/list")["tools"]

    def call(self, name, arguments=None):
        res = self.request("tools/call", {"name": name, "arguments": arguments or {}})
        text = "".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        return ("Error: " + text) if res.get("isError") and not text.startswith("Error") else text
c = MCPClient("http://uw-runtime:8000/mcp")
c.initialize()
print(c.call("submit_final_answer", {"answer": "You should offer a $500.0 deductible."}))
PY
