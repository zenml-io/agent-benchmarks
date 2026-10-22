"""Local OpenAI-compatible router for the replay arms.

  OPENAI_API_KEY=... OPENAI_COMPAT_BASE_URL_PROVIDER_A=... OPENAI_COMPAT_API_KEY_PROVIDER_A=... \
      python model_router.py --port 8766

The agent's OpenAI client points here (OPENAI_BASE_URL=http://127.0.0.1:8766/v1). Requests for
OpenAI models (gpt-*) go to api.openai.com unchanged; every other model goes to provider-a's
OpenAI-compatible API (base URL from OPENAI_COMPAT_BASE_URL_PROVIDER_A, ending in /v1). The provider
used for the published run adds `metadata.weight_versions` (a list) to chat completions, which the
OpenAI response schema PydanticAI validates against rejects, so the `metadata` key is removed from
every successful provider-a response. Keys and the base URL come from this process's environment only.
"""
import argparse
import json
import os
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

OPENAI = ("https://api.openai.com/v1", "OPENAI_API_KEY")
PROVIDER_A = (os.environ.get("OPENAI_COMPAT_BASE_URL_PROVIDER_A", "").rstrip("/"), "OPENAI_COMPAT_API_KEY_PROVIDER_A")


class Router(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def do_POST(self):  # noqa: N802
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        model = str(json.loads(body or b"{}").get("model", ""))
        base, key_env = OPENAI if model.startswith("gpt-") else PROVIDER_A
        path = self.path.removeprefix("/v1")
        request = urllib.request.Request(base + path, data=body, method="POST", headers={
            "Content-Type": "application/json", "Authorization": f"Bearer {os.environ[key_env]}"})
        try:
            with urllib.request.urlopen(request, timeout=600) as response:
                status, payload = response.status, response.read()
        except urllib.error.HTTPError as error:
            status, payload = error.code, error.read()
        if base == PROVIDER_A[0] and status == 200:
            data = json.loads(payload)
            data.pop("metadata", None)
            payload = json.dumps(data).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, fmt, *args):
        return


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8766)
    a = ap.parse_args()
    ThreadingHTTPServer(("127.0.0.1", a.port), Router).serve_forever()
