"""Kitaru evaluator: tau2-bench task success, read from the episode's graded output.

The tau2_kitaru_agent episode writes tau2's own reward (EvaluationType.ALL, substring
communicate scoring) as the run's final output. A session without a graded outcome
(a crashed or cut-off run) counts as a failed task.
"""

import json
from typing import Any

from kitaru.task.evaluator import EvaluationResult, SessionView


def _outcome(outputs: Any) -> dict[str, Any] | None:
    if isinstance(outputs, str):
        try:
            outputs = json.loads(outputs)
        except ValueError:
            return None
    return outputs if isinstance(outputs, dict) and isinstance(outputs.get("tau2"), dict) else None


def evaluate(session: SessionView) -> EvaluationResult:
    """Score 1.0 when tau2 graded the episode as solved, else 0.0."""
    outcome = _outcome(session.session.outputs)
    reward = outcome["tau2"].get("reward") if outcome else None
    if reward is None:
        return EvaluationResult(name="tau2_task_success", score=0.0, passed=False, min_score=0.0, max_score=1.0,
                                explanation="No graded tau2 outcome on this session; counted as a failed task.")
    return EvaluationResult(name="tau2_task_success", score=float(reward), passed=reward >= 1.0,
                            min_score=0.0, max_score=1.0,
                            explanation=f"tau2 reward {reward} ({outcome['tau2'].get('termination_reason')})")
