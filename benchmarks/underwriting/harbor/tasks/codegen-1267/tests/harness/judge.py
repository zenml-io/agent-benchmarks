"""Grade an agent's final answer against the reference answer with an LLM judge.

Snorkel graded with an LLM judge comparing the final answer to a programmatically generated reference (GPT-4.1,
94.5% agreement with human annotators). This judge is validated the same way against Snorkel's own labels
(harness/validate_judge.py) before it grades any run.
"""
import json
import re

from llm import complete

SYSTEM = """You grade an AI underwriting assistant's final answer against the correct reference answer.

Rules:
- The answer is correct only if its conclusion matches the reference: same yes/no decision, same NAICS code, same
  dollar amounts, same set of lines of business (order and wording do not matter).
- For product recommendations, the assistant must name exactly the lines of business in the reference, no more and
  no fewer, using the insurer's line names (workers compensation, property, general liability, auto, cyber, bop).
  Generic industry advice that does not commit to that set is incorrect.
- If the reference says the business is out of appetite (so limits or deductibles are irrelevant), the assistant
  must say so; recommending limits or a deductible anyway is incorrect.
- Extra explanation is fine. Hedging between several conclusions is incorrect.

Reply with JSON only: {"correct": true or false, "reason": "<one short sentence>"}"""


def grade(judge_key, task_type, reference, final_answer):
    """Returns (correct: bool | None, reason, cost USD)."""
    if not (final_answer or "").strip():
        return False, "no final answer", 0.0
    user = (f"Task type: {task_type}\n\nReference answer (correct):\n{reference}\n\n"
            f"Assistant's final answer:\n{final_answer[:6000]}")
    text, _, cost = complete(judge_key, SYSTEM, [{"role": "user", "content": user}], max_tokens=400)
    m = re.search(r"\{.*\}", text, re.S)
    try:
        v = json.loads(m[0]) if m else {}
        return bool(v["correct"]), str(v.get("reason", "")), cost
    except (ValueError, KeyError, TypeError):
        return None, "unparseable judge reply: " + text[:120], cost
