"""upload_recordings.py carries Harbor's verifier grade into the uploaded Kitaru session (no tau2 needed).

    uv run --extra replay --with pytest pytest harbor/tests/test_upload.py

Harbor grades a trial after the agent has finished, so the recording has no grade. The uploader adds it to
the session's final outputs, where the benchmark's Kitaru evaluator (`tau2_reward_evaluator.py`) reads it.
A stand-in client records what would be sent; the evaluator then scores the uploaded outputs.
"""

import asyncio
import json
import sys
from pathlib import Path
from types import SimpleNamespace

HARBOR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(HARBOR / "scripts"))
sys.path.insert(0, str(HARBOR.parent / "harness" / "replay"))

import upload_recordings
from tau2_reward_evaluator import evaluate

LOCAL = "11111111-1111-1111-1111-111111111111"
SERVER = "22222222-2222-2222-2222-222222222222"
RECORDING = [
    {"method": "POST", "path": "/api/v1/sessions", "body": {"name": "tau2 telecom case 7 baseline"}},
    {"method": "POST", "path": f"/api/v1/sessions/{LOCAL}/nodes", "body": {"nodes": []}},
    {"method": "PATCH", "path": f"/api/v1/sessions/{LOCAL}",
     "body": {"status": "completed", "outputs": json.dumps({"answer": "Glad it works now."})}},
]


class RecordingClient:
    def __init__(self) -> None:
        self.sent: list[tuple[str, str, dict]] = []

    async def request(self, method: str, path: str, json: dict) -> SimpleNamespace:
        self.sent.append((method, path, json))
        return SimpleNamespace(json=lambda: {"id": SERVER})


def make_trial(tmp: Path, reward: float | None) -> Path:
    trial = tmp / "telecom-test-07__abc"
    (trial / "agent").mkdir(parents=True)
    (trial / "config.json").write_text(json.dumps({"task": {"path": "harbor/tasks/telecom-test-07"}}))
    rewards = {"rewards": {"reward": reward}} if reward is not None else None
    (trial / "result.json").write_text(json.dumps({"verifier_result": rewards}))
    (trial / "agent" / "tau2-kitaru-agent.json").write_text(json.dumps({"runtime": {"termination_reason": "user_stop"}}))
    return trial


def upload(grade: dict | None) -> RecordingClient:
    client = RecordingClient()
    asyncio.run(upload_recordings.upload_trial(client, RECORDING, "agent", None, grade))
    return client


def score(outputs: object) -> float:
    return evaluate(SimpleNamespace(session=SimpleNamespace(outputs=outputs))).score


def task_ids() -> dict[str, str]:
    index = json.loads(upload_recordings.TASK_INDEX.read_text())["tasks"]
    return {t["task"]: t["tau2_task_id"] for t in index}


def test_verifier_reward_reaches_the_evaluator(tmp_path: Path) -> None:
    for reward in (1.0, 0.0):
        grade = upload_recordings.harbor_grade(make_trial(tmp_path / str(reward), reward), task_ids())
        assert grade["reward"] == reward and grade["task_id"] == task_ids()["telecom-test-07"]
        assert grade["termination_reason"] == "user_stop"

        sent = upload(grade).sent
        method, path, body = sent[-1]
        assert (method, path) == ("PATCH", f"/api/v1/sessions/{SERVER}")
        outputs = json.loads(body["outputs"])
        assert outputs["answer"] == "Glad it works now." and outputs["tau2"] == grade
        assert score(body["outputs"]) == reward
        # Only the final session update changes; the node batch goes out as recorded.
        assert sent[1][2] == RECORDING[1]["body"]


def test_trial_without_a_verifier_reward_is_uploaded_ungraded(tmp_path: Path) -> None:
    assert upload_recordings.harbor_grade(make_trial(tmp_path, None), task_ids()) is None
    body = upload(None).sent[-1][2]
    assert body == RECORDING[-1]["body"]
    assert score(body["outputs"]) == 0.0


def test_unparsable_or_object_outputs_keep_their_form() -> None:
    grade = {"reward": 1.0}
    assert json.loads(upload_recordings.with_grade("plain text", grade)) == {"answer": "plain text", "tau2": grade}
    assert upload_recordings.with_grade({"answer": "x"}, grade) == {"answer": "x", "tau2": grade}
