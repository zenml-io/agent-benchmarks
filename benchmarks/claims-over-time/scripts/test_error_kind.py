"""Offline tests of the run-error classifier and the infrastructure retries: uv run --with pytest pytest scripts"""

import asyncio
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
os.environ["CLAIMS_INFRA_BACKOFF"] = "0,0"
import run_batch
from score import error_kind, score

# `run_error` is repr(exception)[:500] from the claims agent's episode, or a message written by run_batch.py or round.py.
AGENT = [
    ("UsageLimitExceeded('The next request would exceed the request_limit of 12. Consider raising the limit, or see "
     "the docs on usage limits for budget-aware patterns: https://pydantic.dev/docs/ai/core-concepts/agent/#usage-limits')"),
    ("UnexpectedModelBehavior('Model token limit (4096) exceeded before any response was generated. Increase the "
     "`max_tokens` model setting, or simplify the prompt')"),
    "UnexpectedModelBehavior('Exceeded maximum retries (12) for output validation')",
    "IncompleteToolCall('Model token limit (4096) exceeded while generating a tool call')",
    ("ModelHTTPError('status_code: 400, model_name: agent-model, body: {\\'message\\': \"This model\\'s maximum context "
     "length is 65536 tokens. However, you requested 70000 tokens\"}')"),
    # The same outcomes in a Kitaru session run, where the failed session keeps only the message.
    ("job failed: Result session 01a17e75-c921 is failed, not completed. The next request would exceed the request_limit "
     "of 12. Consider raising the limit"),
    ("job failed: Result session 01a17e75-c921 is failed, not completed. Model token limit (4096) exceeded before any "
     "response was generated."),
    "job failed: Result session 01a17e75-c921 is failed, not completed. Exceeded maximum output retries (12)",
    ("job failed: Result session 01a17e75-c921 is failed, not completed. Tool 'search_precedents' exceeded max retries "
     "count of 12. Consider raising the retry limit"),
]
INFRA = [
    "ModelAPIError('Connection error.')",
    "ModelAPIError('Request timed out.')",
    "ModelHTTPError('status_code: 429, model_name: gpt-5-mini, body: {\\'message\\': \\'Rate limit reached\\'}')",
    "ModelHTTPError('status_code: 503, model_name: agent-model, body: None')",
    "ModelHTTPError('status_code: 502, model_name: agent-model, body: <html>Bad Gateway</html>')",
    "ModelHTTPError('status_code: 404, model_name: agent-model, body: modal-http: app for invoked web endpoint is stopped')",
    "ModelHTTPError('status_code: 401, model_name: gpt-5-mini, body: invalid api key')",
    "ModelHTTPError('status_code: 400, model_name: gpt-5-mini, body: Unsupported parameter: max_tokens')",
    "exit 1, no row: Traceback (most recent call last): ... ConnectionResetError: [Errno 54]",
    "job failed: task abandoned after 3 attempts without a heartbeat",
    "job failed: Result session 01a17e75-c921 is failed, not completed. Connection error.",
    "job failed: Result session 01a17e75-c921 is failed, not completed. status_code: 503, model_name: agent-model",
    "UnexpectedModelBehavior('Invalid response from openai chat completions endpoint, expected JSON data')",
    "job canceled: ",
    "ConnectError('[Errno 61] Connection refused')",
    "SomethingNobodyHasSeenYet('?')",
]


def test_agent_errors() -> None:
    assert [m for m in AGENT if error_kind(m) != "agent"] == []


def test_infra_errors() -> None:
    assert [m for m in INFRA if error_kind(m) != "infra"] == []


def test_no_error() -> None:
    assert error_kind(None) is None and error_kind("") is None


def test_infra_rows_are_not_scored() -> None:
    cases = {"c1": {"batch": 1, "truth": "uphold"}}
    try:
        score([{"case_id": "c1", "final": None, "run_error": INFRA[0], "error_kind": "infra"}], cases)
    except ValueError as exc:
        assert "infrastructure" in str(exc)
    else:
        raise AssertionError("an infra row was scored")


def test_retries_infra_errors_only() -> None:
    calls: list[str] = []

    def runner(errors: list[str | None]):
        async def run(case_id: str) -> dict:
            calls.append(case_id)
            return {"case_id": case_id, "final": None, "run_error": errors[min(len(calls), len(errors)) - 1]}
        return run

    calls.clear()
    row = asyncio.run(run_batch.with_infra_retries("a", runner([INFRA[0], None])))
    assert (len(calls), row["error_kind"]) == (2, None)
    calls.clear()
    row = asyncio.run(run_batch.with_infra_retries("a", runner([AGENT[0]])))
    assert (len(calls), row["error_kind"]) == (1, "agent")
    calls.clear()
    row = asyncio.run(run_batch.with_infra_retries("a", runner([INFRA[0]])))
    assert (len(calls), row["error_kind"]) == (3, "infra")


def test_an_exception_is_an_infra_row() -> None:
    async def run(case_id: str) -> dict:
        raise ConnectionError("network is down")
    row = asyncio.run(run_batch.with_infra_retries("a", run))
    assert row["error_kind"] == "infra" and "network is down" in row["run_error"]
