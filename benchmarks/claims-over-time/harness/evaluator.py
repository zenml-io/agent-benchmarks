"""Kitaru evaluator: 1 when the claims agent's submitted decision matches the real IMR ruling, else 0.

The appeal id comes from the session input ("Review appeal <id>."), the decision from the session
output (the submit_determination arguments), and the ruling (`truth`) from $CLAIMS_WORK_DIR/cases.jsonl,
which must be set in the environment of the worker that runs this evaluator. A session with no
submitted decision (cut off at the request limit, or crashed) scores 0. An appeal whose row has no
`truth` is not revealed: the evaluator raises instead of scoring it, so no score of an unrevealed
appeal is ever written to the workspace.
"""

import json
import os
import re
from pathlib import Path
from typing import Any

from kitaru.task.evaluator import EvaluationResult, SessionView

NAME = "claims_decision_correct"


def _truth() -> dict[str, str]:
    work = os.environ.get("CLAIMS_WORK_DIR")
    if not work:
        raise RuntimeError("CLAIMS_WORK_DIR is not set in the worker's environment; it must point at the directory with cases.jsonl")
    rows = [json.loads(line) for line in (Path(work) / "cases.jsonl").read_text().splitlines() if line.strip()]
    return {c["id"]: c["truth"] for c in rows if c.get("truth")}


def _decision(outputs: Any) -> str | None:
    if isinstance(outputs, str):
        try:
            outputs = json.loads(outputs)
        except ValueError:
            return None
    return outputs.get("decision") if isinstance(outputs, dict) else None


def evaluate(session: SessionView) -> EvaluationResult:
    """Score the session's submitted decision against the appeal's real outcome."""
    inputs = session.session.inputs
    m = re.search(r"Review appeal (\S+?)\.?(?:\"|$)", inputs if isinstance(inputs, str) else json.dumps(inputs))
    if not m:
        raise RuntimeError(f"no appeal id in the session input {inputs!r}"[:300])
    case_id, truths = m.group(1), _truth()
    if case_id not in truths:
        raise RuntimeError(f"appeal {case_id} has no revealed ruling in cases.jsonl; not scored")
    truth, decision = truths[case_id], _decision(session.session.outputs)
    if decision not in ("uphold", "overturn"):
        return EvaluationResult(name=NAME, score=0.0, passed=False, min_score=0.0, max_score=1.0,
                                explanation=f"{case_id}: no decision submitted (truth: {truth}); counted as wrong")
    right = decision == truth
    return EvaluationResult(name=NAME, score=float(right), passed=right, min_score=0.0, max_score=1.0,
                            explanation=f"{case_id}: decided {decision}, truth {truth}")
