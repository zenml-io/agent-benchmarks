"""Kitaru evaluator: is the session's final underwriting answer correct against the task's reference?

Uses the benchmark's own grading (harness/judge.py): GPT-6 Luna and Claude Haiku 5.5, GPT-6.1 Sol breaks ties.
"""
import os
import sys

# The script is uploaded to the server and run from a copy, so find the harness through the worker environment.
# UW_HARNESS: absolute path of this benchmark's harness/ directory on the worker machine.
sys.path.insert(0, os.environ["UW_HARNESS"])
from judge import grade  # noqa: E402
from kitaru.task.evaluator import EvaluationResult, SessionView  # noqa: E402


def evaluate(session: SessionView, **params) -> EvaluationResult:
    meta = session.session.metadata or {}
    final = (session.session.outputs or {}).get("final_answer")
    if not final:
        status = (session.session.outputs or {}).get("status", session.session.status)
        return EvaluationResult(name="correct_decision", score=False, passed=False,
                                explanation=f"no final answer ({status})")
    votes = [grade(j, meta["task_type"], meta["expected"], final) for j in ("gpt-6-luna", "haiku-5.5")]
    if votes[0][0] != votes[1][0] or votes[0][0] is None:
        votes.append(grade("gpt-6.1-sol", meta["task_type"], meta["expected"], final))
    ok = bool(votes[-1][0])
    return EvaluationResult(name="correct_decision", score=ok, passed=ok, explanation=votes[-1][1][:500])
