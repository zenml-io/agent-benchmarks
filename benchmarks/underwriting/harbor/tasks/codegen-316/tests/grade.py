"""Grade one underwriting case the way harness/run.py did, from the answer the task's MCP server recorded.

  python3 grade.py --case /tests/case.json --out-dir /logs/verifier [--state-url URL]

- The final answer comes from the sidecar's GET /state (written only by `submit_final_answer`), never from a file the
  agent could write.
- No answer: reward 0, no judge call.
- An answer: the original panel. harness/judge.py's grade() with GPT-6 Luna and Claude Haiku 5.5; GPT-6.1 Sol breaks
  a disagreement or an unparseable verdict; the case passes on the tie-break's verdict if there was one, else on the
  first judge's (run.run_task's rule). Judges and tie-break come from run.JUDGES / run.TIEBREAK.
- An unreachable server, a simulator failure or a judge API failure is an infrastructure error: reward 0, and
  grading.json says `infra_error` so summaries count it apart from wrong answers.

Writes reward.json ({"reward": 0|1}, the only key, so Harbor's averages stay clean), grading.json (verdicts, costs,
counters) and runtime_state.json (the server's transcript and events).
"""
import argparse
import json
import os
import sys
import time
import urllib.request

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "harness"))


def fetch_state(url, tries=5):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(url, timeout=30) as r:
                return json.load(r)
        except Exception as e:  # noqa: BLE001
            last = e
            time.sleep(2 ** i)
    raise RuntimeError(f"state unreachable: {last!r}"[:300])


def panel(task_type, reference, final, grade_fn, judges, tiebreak):
    """Verdicts and success exactly as run.run_task computes them."""
    verdicts, cost = [], 0.0
    if final:
        for j in judges:
            ok, reason, c = grade_fn(j, task_type, reference, final)
            verdicts.append((j, ok, reason))
            cost += c
        if len({v[1] for v in verdicts}) > 1 or None in {v[1] for v in verdicts}:
            ok, reason, c = grade_fn(tiebreak, task_type, reference, final)
            verdicts.append((tiebreak, ok, reason))
            cost += c
    success = bool(final) and bool(verdicts[-1][1] if len(verdicts) == 3 else verdicts[0][1])
    return success, verdicts, cost


def grade_case(case, state, grade_fn, judges, tiebreak):
    out = dict(case_id=case["id"], task_type=case["task"], status=state.get("status"),
               final_answer=state.get("final_answer"), underwriter_turns=state.get("underwriter_turns"),
               tool_calls=state.get("tool_calls"), sim_cost=state.get("sim_cost", 0.0), verdicts=[],
               judge_cost=0.0, infra_error=None, success=False)
    if state.get("status") == "simulator_error":
        out["infra_error"] = "simulator_error: " + "; ".join(state.get("errors") or [])[:300]
        return out
    final = state.get("final_answer") if state.get("status") == "finished" else None
    if not final:
        return out
    try:
        success, verdicts, cost = panel(case["task"], case["reference"], final, grade_fn, judges, tiebreak)
    except RuntimeError as e:
        out["infra_error"] = f"judge_error: {e}"[:300]
        return out
    out.update(success=success, verdicts=verdicts, judge_cost=cost)
    return out


def write(out_dir, result, state=None):
    os.makedirs(out_dir, exist_ok=True)
    json.dump(result, open(os.path.join(out_dir, "grading.json"), "w"), indent=1)
    if state is not None:
        json.dump(state, open(os.path.join(out_dir, "runtime_state.json"), "w"), indent=1)
    # reward.json last: it exists only once the grading record is on disk.
    json.dump({"reward": 1 if result["success"] else 0}, open(os.path.join(out_dir, "reward.json"), "w"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--case", required=True)
    ap.add_argument("--out-dir", required=True)
    ap.add_argument("--state-url", default=os.environ.get("UW_STATE_URL", "http://uw-runtime:8000/state"))
    a = ap.parse_args()
    case = json.load(open(a.case))
    try:
        state = fetch_state(a.state_url)
    except RuntimeError as e:
        write(a.out_dir, dict(case_id=case["id"], success=False, infra_error=str(e), verdicts=[], judge_cost=0.0))
        print("infra error:", e)
        return
    import run as uw  # imported late: only an answered case needs the judges' client
    from judge import grade
    result = grade_case(case, state, grade, uw.JUDGES, uw.TIEBREAK)
    write(a.out_dir, result, state)
    print(json.dumps({k: result[k] for k in ("status", "success", "infra_error", "judge_cost")}))
    for j, ok, reason in result["verdicts"]:
        print(f"  {j}: {ok} ({reason})")


if __name__ == "__main__":
    main()
