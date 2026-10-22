"""Offline tests for the Harbor port: MCP server, grader (judges mocked), copilot runner, task generator.

  uv run --with "mcp==1.26.0" --with pytest pytest -q harbor/tests     (from benchmarks/underwriting)

Needs the rebuilt environment (scripts/fetch_data.sh). No model or judge calls.
"""
import ast
import json
import os
import socket
import subprocess
import sys
import threading
import time
from pathlib import Path

import pytest

HARBOR = Path(__file__).resolve().parents[1]
BENCH = HARBOR.parent
os.environ["UW_ROOT"] = str(BENCH)
for p in (BENCH / "harness", HARBOR / "runtime", HARBOR / "grader", HARBOR / "underwriting_agent", HARBOR):
    sys.path.insert(0, str(p))

import copilot  # noqa: E402
import generate_tasks as gen  # noqa: E402
import grade as G  # noqa: E402
import run as uw  # noqa: E402
import server as S  # noqa: E402
from mcp_client import MCPClient  # noqa: E402

TASKS = {t["id"]: t for t in json.load(open(BENCH / "env" / "tasks.json"))}
CASE = TASKS["codegen-1007"]


def sidecar_case(t):
    return {"id": t["id"], "task": t["task"], "company": t["company"]}


def fake_reply(case, transcript):
    return f"reply {len(transcript)}", 0.001


# ---------- MCP server ----------

@pytest.fixture()
def server():
    import uvicorn

    case = S.Case(sidecar_case(CASE), reply_fn=fake_reply)
    app = S.build_server(case, host="127.0.0.1").streamable_http_app()
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        port = s.getsockname()[1]
    srv = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    th = threading.Thread(target=srv.run, daemon=True)
    th.start()
    for _ in range(100):
        if srv.started:
            break
        time.sleep(0.05)
    yield case, f"http://127.0.0.1:{port}"
    srv.should_exit = True
    th.join(5)


def test_server_tools_match_original(server):
    case, base = server
    c = MCPClient(base + "/mcp")
    c.initialize()
    tools = {t["name"]: t for t in c.list_tools()}
    orig = {t["function"]["name"]: t["function"] for t in uw.TOOLS}
    assert set(tools) == set(orig) | {"ask_underwriter", "submit_final_answer"}
    for name, f in orig.items():
        assert tools[name]["description"] == f["description"]
        assert set(tools[name]["inputSchema"].get("properties", {})) == set(f["parameters"]["properties"])
    env = uw.Env()
    q = "SELECT * FROM lobs"
    assert c.call("read_query", {"query": q}) == env.run("read_query", {"query": q})
    assert c.call("get_underwriting_guidelines") == env.run("get_underwriting_guidelines", {})
    assert "Only SELECT" in c.call("read_query", {"query": "DELETE FROM lobs"})
    assert case.tool_calls == 3


def test_server_episode_and_one_shot_submit(server):
    case, base = server
    c = MCPClient(base + "/mcp")
    c.initialize()
    assert c.call("ask_underwriter", {"message": "What state?"}) == "reply 2"
    assert c.call("submit_final_answer", {"answer": "No, out of appetite."}).startswith("Final answer recorded")
    assert "already submitted" in c.call("submit_final_answer", {"answer": "Yes, in appetite."})
    assert "already submitted" in c.call("ask_underwriter", {"message": "hello?"})
    state = json.load(__import__("urllib.request").request.urlopen(base + "/state"))
    assert state["final_answer"] == "FINAL ANSWER: No, out of appetite."
    assert state["status"] == "finished" and state["underwriter_turns"] == 1
    assert state["transcript"][0] == ["underwriter", uw.SEEDS[CASE["task"]]]
    assert "reference" not in json.dumps(state) and CASE["reference"] not in json.dumps(state)


def test_turn_limit_matches_original():
    case = S.Case(sidecar_case(CASE), reply_fn=fake_reply)
    for i in range(uw.MAX_TURNS):
        assert case.ask(f"q{i}").startswith("reply")
    assert "turn limit" in case.ask("one more")
    assert case.status == "turn_limit"
    assert "turn limit" in case.submit("FINAL ANSWER: yes")
    assert case.final_answer is None


def test_submit_keeps_text_from_final_answer_marker():
    case = S.Case(sidecar_case(CASE), reply_fn=fake_reply)
    case.submit("Thinking done.\nFINAL ANSWER: No.")
    assert case.final_answer == "FINAL ANSWER: No."


def test_simulator_failure_is_infra():
    def boom(case, transcript):
        raise RuntimeError("haiku-5.5: 529 overloaded")

    case = S.Case(sidecar_case(CASE), reply_fn=boom)
    assert "unavailable" in case.ask("hi")
    out = G.grade_case(CASE, case.state(), None, uw.JUDGES, uw.TIEBREAK)
    assert out["infra_error"].startswith("simulator_error") and out["success"] is False


def test_underwriter_prompt_holds_application_not_answer():
    seen = {}

    def spy(case, transcript):
        seen["case"] = case
        return "ok", 0.0

    case = S.Case(sidecar_case(CASE), reply_fn=spy)
    case.ask("hi")
    assert set(seen["case"]) == {"id", "task", "company"}


# ---------- grader (judges mocked) ----------

def judge_stub(verdicts):
    calls = []

    def fn(judge, task_type, reference, final):
        calls.append(judge)
        return verdicts[judge], "stub", 0.001
    return fn, calls


def original_success(final, verdicts):
    """The expression from harness/run.py run_task, copied by AST so a change there fails this test."""
    src = (BENCH / "harness" / "run.py").read_text()
    expr = next(n for n in ast.walk(ast.parse(src)) if isinstance(n, ast.Assign) and
                getattr(n.targets[0], "id", None) == "success")
    return eval(compile(ast.Expression(expr.value), "run.py", "eval"), {"final": final, "verdicts": verdicts})


@pytest.mark.parametrize("luna,haiku,sol", [(a, b, c) for a in (True, False, None) for b in (True, False, None)
                                            for c in (True, False, None)])
def test_panel_matches_original_rule(luna, haiku, sol):
    fn, calls = judge_stub({"gpt-6-luna": luna, "haiku-5.5": haiku, "gpt-6.1-sol": sol})
    ok, verdicts, cost = G.panel("Appetite Check", "ref", "FINAL ANSWER: x", fn, uw.JUDGES, uw.TIEBREAK)
    assert ok == original_success("FINAL ANSWER: x", verdicts)
    tie = luna != haiku or None in (luna, haiku)
    assert calls == ["gpt-6-luna", "haiku-5.5"] + (["gpt-6.1-sol"] if tie else [])


def state(status="finished", final="FINAL ANSWER: No, the company is not in appetite for that LOB."):
    return {"status": status, "final_answer": final, "underwriter_turns": 2, "tool_calls": 5, "sim_cost": 0.001}


def test_reference_scores_1_and_nop_scores_0_without_judges():
    fn, calls = judge_stub({"gpt-6-luna": True, "haiku-5.5": True, "gpt-6.1-sol": True})
    assert G.grade_case(CASE, state(), fn, uw.JUDGES, uw.TIEBREAK)["success"] is True
    fn, calls = judge_stub({})
    out = G.grade_case(CASE, {"status": "open", "final_answer": None}, fn, uw.JUDGES, uw.TIEBREAK)
    assert out["success"] is False and calls == [] and out["infra_error"] is None


def test_wrong_and_hedged_answers_score_0_when_judges_say_so():
    fn, _ = judge_stub({"gpt-6-luna": False, "haiku-5.5": False, "gpt-6.1-sol": True})
    assert G.grade_case(CASE, state(final="FINAL ANSWER: maybe"), fn, uw.JUDGES, uw.TIEBREAK)["success"] is False


def test_judge_api_failure_is_infra_not_wrong():
    def fn(*a):
        raise RuntimeError("gpt-6-luna: 500 boom")
    out = G.grade_case(CASE, state(), fn, uw.JUDGES, uw.TIEBREAK)
    assert out["success"] is False and out["infra_error"].startswith("judge_error")


def test_judge_sees_original_prompt_and_answer(monkeypatch):
    import judge
    seen = []

    def fake_complete(key, system, messages, max_tokens=2048):
        seen.append((key, system, messages[0]["content"]))
        return '{"correct": true, "reason": "same"}', {}, 0.0002
    monkeypatch.setattr(judge, "complete", fake_complete)
    out = G.grade_case(CASE, state(), judge.grade, uw.JUDGES, uw.TIEBREAK)
    assert out["success"] is True and [s[0] for s in seen] == list(uw.JUDGES)
    assert seen[0][1] == judge.SYSTEM and CASE["reference"] in seen[0][2]


def test_unreachable_state_writes_reward_0(tmp_path):
    case_file = tmp_path / "case.json"
    case_file.write_text(json.dumps({"id": "x", "task": "Appetite Check", "reference": "r"}))
    out = tmp_path / "v"
    r = subprocess.run([sys.executable, str(HARBOR / "grader" / "grade.py"), "--case", str(case_file), "--out-dir",
                        str(out), "--state-url", "http://127.0.0.1:9/state"], capture_output=True, text=True,
                       timeout=120, env={**os.environ, "PYTHONPATH": str(BENCH / "harness")})
    assert r.returncode == 0, r.stderr
    assert json.loads((out / "reward.json").read_text()) == {"reward": 0}
    assert "unreachable" in json.loads((out / "grading.json").read_text())["infra_error"]


def test_test_sh_clears_planted_reward(tmp_path):
    text = (HARBOR / "grader" / "test.sh").read_text()
    assert text.index("rm -f /logs/verifier/reward.json") < text.index("grade.py")
    assert "set -e" not in text.replace("set -euo", "")


# ---------- copilot runner (the original loop against MCP) ----------

class FakeClient:
    def __init__(self):
        self.calls = []

    def call(self, name, args=None):
        self.calls.append((name, args))
        return {"ask_underwriter": "Ohio.", "submit_final_answer": "Final answer recorded."}.get(name, "[]")


def scripted(*replies):
    it = iter(replies)

    def call(key, msgs, tools):
        assert tools == uw.TOOLS
        return next(it), dict(input=10, cached=0, output=5), 0.1, 0
    return call


def tc(name, args, i="t1"):
    return {"tool_calls": [{"id": i, "function": {"name": name, "arguments": json.dumps(args)}}], "content": ""}


def test_runner_routes_tools_questions_and_final_answer():
    client = FakeClient()
    row = copilot.run_episode("haiku-5.5", uw.SYSTEM, "Hi", client, call=scripted(
        {**tc("list_tables", {}), "content": "Let me look."},
        {"content": "What state is the company in?"},
        {"content": "Thanks.\nFINAL ANSWER: Yes, in appetite."}))
    assert [c[0] for c in client.calls] == ["list_tables", "ask_underwriter", "submit_final_answer"]
    assert client.calls[1][1]["message"] == "Let me look.\n\nWhat state is the company in?"
    assert client.calls[2][1]["answer"] == "FINAL ANSWER: Yes, in appetite."
    assert row["status"] == "finished" and row["calls"] == 3 and row["underwriter_turns"] == 1


def test_runner_limits_match_original():
    client = FakeClient()
    row = copilot.run_episode("haiku-5.5", uw.SYSTEM, "Hi", client,
                              call=scripted(*[{"content": "", **tc("list_tables", {})}] * uw.MAX_CALLS))
    assert row["status"] == "step_limit" and not any(c[0] == "submit_final_answer" for c in client.calls)
    client = FakeClient()
    row = copilot.run_episode("haiku-5.5", uw.SYSTEM, "Hi", client,
                              call=scripted(*[{"content": "A question?"}] * (uw.MAX_TURNS + 1)))
    assert row["status"] == "turn_limit" and row["underwriter_turns"] == uw.MAX_TURNS + 1
    assert sum(c[0] == "ask_underwriter" for c in client.calls) == uw.MAX_TURNS
    client = FakeClient()
    row = copilot.run_episode("haiku-5.5", uw.SYSTEM, "Hi", client, call=scripted(*[{"content": ""}] * 3))
    assert row["status"] == "empty_reply" and row["calls"] == 3


def test_agent_extracts_request_and_validates_options():
    pytest.importorskip("harbor.agents.installed.base")
    from underwriting_agent.agent import UnderwritingCopilot, extract_request
    ins = gen.INSTRUCTION.format(seed=uw.SEEDS["Deductibles"])
    assert extract_request(ins) == uw.SEEDS["Deductibles"]
    UnderwritingCopilot.preflight({"prompt_file": "x.txt", "effort": "high"})
    with pytest.raises(ValueError):
        UnderwritingCopilot.preflight({"promt_file": "x.txt"})


# ---------- generated tasks ----------

def test_generated_sample_is_current_and_leaks_nothing(tmp_path):
    out = tmp_path / "tasks"
    subprocess.run([sys.executable, str(HARBOR / "generate_tasks.py"), "--out", str(out), "--sample"], check=True,
                   capture_output=True)
    committed = HARBOR / "tasks"
    names = sorted(p.name for p in out.iterdir())
    assert names == sorted(p.name for p in committed.iterdir() if p.is_dir())
    assert len(names) == 12
    for name in names:
        for f in (out / name).rglob("*"):
            if f.is_file():
                rel = f.relative_to(out / name)
                assert (committed / name / rel).read_bytes() == f.read_bytes(), f"{name}/{rel} is stale"
        t = TASKS[name]
        visible = [p for p in (out / name / "environment").rglob("*") if p.is_file() and p.suffix != ".xz"]
        visible.append(out / name / "instruction.md")
        blob = "\n".join(p.read_text() for p in visible)
        assert t["reference"] not in blob, f"{name}: reference visible to the agent"
        assert json.loads((out / name / "environment/runtime/uw/case.json").read_text()).keys() == {"id", "task",
                                                                                                    "company"}


def test_every_case_generates_a_paraphrase_and_hedge():
    import random
    for t in TASKS.values():
        p = gen.paraphrase(t, random.Random(0))
        assert p and p != t["reference"]
        assert gen.hedge(t, BENCH / "env" / "insurance.db")


def test_split_metadata_matches_split_file():
    import tomllib
    split = json.load(open(BENCH / "env" / "split.json"))
    for d in (HARBOR / "tasks").iterdir():
        if d.is_dir():
            meta = tomllib.loads((d / "task.toml").read_text())["metadata"]
            assert d.name in split[meta["split"]]
            assert meta["question_type"] == TASKS[d.name]["task"]


def test_runner_connects_and_rejects_unknown_model(server, tmp_path, monkeypatch, capsys):
    case, base = server
    req = tmp_path / "req.txt"
    req.write_text("Hi")
    monkeypatch.setattr(sys, "argv", ["copilot.py", "--model", "no-such-model", "--url", base + "/mcp",
                                      "--request-file", str(req), "--out", str(tmp_path / "out.json")])
    with pytest.raises(SystemExit, match="unknown model key"):
        copilot.main()
    assert "8 tools" in capsys.readouterr().out
