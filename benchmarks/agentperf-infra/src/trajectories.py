"""
How agents fail, and whether the mix shifts with the server. Reads the raw trajectories in
jobs/ (Harbor ATIF) for every valid run in attempts.jsonl; no GPU, no Modal.

    python trajectories.py        # markdown to stdout

Each unsolved trial gets one class:
  never started     the harness never ran (e.g. its install failed in the sandbox)
  looked up answer  it reached for the benchmark itself (see experiment.BENCHMARK_LOOKUP)
  finished wrong    the agent stopped on its own and the tests failed
  out of time, working   hit the time limit while its recent actions were still new
  out of time, looping   hit the time limit while mostly repeating earlier actions
  other error       anything else (crashes, API errors)
"Recent" = the last WINDOW actions; "looping" = at least LOOP_SHARE of them repeat an earlier
action of the same trial (exact text after whitespace normalization; empty keystrokes, i.e.
waiting, are ignored). The hypothesis: a slow or overloaded server adds "out of time,
working" failures, which look like agent failures on a leaderboard but are infra failures.
"""

import json
import re
from collections import Counter, defaultdict
from pathlib import Path

import _paths  # noqa: F401  (harness on sys.path)
import experiment as ex

WINDOW = 8
LOOP_SHARE = 0.5
CLASSES = ["never started", "looked up answer", "finished wrong",
           "out of time, working", "out of time, looping", "other error"]


def actions(trajectory: Path) -> list[str]:
    """Normalized text of every tool call, in order (waits dropped)."""
    try:
        steps = json.loads(trajectory.read_text()).get("steps") or []
    except (OSError, json.JSONDecodeError):
        return []
    out = []
    for st in steps:
        for tc in st.get("tool_calls") or []:
            args = tc.get("arguments") or {}
            text = (args.get("command") or args.get("keystrokes") or args.get("cmd")
                    if isinstance(args, dict) else None)
            if text is None:
                text = f"{tc.get('function_name')} {json.dumps(args, sort_keys=True)}"
            text = re.sub(r"\s+", " ", str(text)).strip().lower()
            if text:
                out.append(text)
    return out


def loop_share(acts: list[str]) -> float | None:
    """Share of the last WINDOW actions that repeat an earlier action of the trial."""
    if len(acts) < 3:
        return None
    start = max(0, len(acts) - WINDOW)
    seen = set(acts[:start])
    repeats = 0
    for a in acts[start:]:
        repeats += a in seen
        seen.add(a)
    return repeats / (len(acts) - start)


def classify(trial_dir: Path) -> str | None:
    """None if solved; otherwise one of CLASSES."""
    try:
        data = json.loads((trial_dir / "result.json").read_text())
    except (OSError, json.JSONDecodeError):
        return "other error"
    traj = trial_dir / "agent" / "trajectory.json"
    reward = ((data.get("verifier_result") or {}).get("rewards") or {}).get("reward")
    passed = reward is not None and float(reward) >= 1.0
    if ex.looked_up_benchmark(traj):
        return "looked up answer"
    if passed:
        return None
    exc = (data.get("exception_info") or {}).get("exception_type")
    if data.get("agent_execution") is None:
        return "never started"
    if exc == "AgentTimeoutError":
        share = loop_share(actions(traj))
        return "out of time, looping" if share is not None and share >= LOOP_SHARE else "out of time, working"
    if exc is None:
        return "finished wrong"
    return "other error"


def main():
    rows = [json.loads(l) for l in ex.ATTEMPTS.read_text().splitlines() if l.strip()]
    groups: dict = defaultdict(Counter)
    timed_out: list[list[str]] = []  # actions of every unsolved timed-out trial
    for r in rows:
        if not r.get("valid") or r["task_set"] == "quick":
            continue
        job = ex.JOBS_DIR / r["job_name"]
        bench = "gaia" if r["task_set"].startswith("gaia") else "terminal-bench"
        key = (bench, r["harness"], r["concurrency"], r["config"], r["gpu"])
        if not job.exists():
            # Published rows: the class and loop shares were computed from the same
            # trajectories by make_public_rows.py (raw jobs/ is not published).
            for t in r["trials"]:
                cls = t["failure_class"] or "solved"
                groups[key][cls] += 1
                if cls.startswith("out of time"):
                    timed_out.append(t["loop_share"])
            continue
        for d in sorted(p.parent for p in job.glob("*/result.json")):
            cls = classify(d) or "solved"
            groups[key][cls] += 1
            if cls.startswith("out of time"):
                acts = actions(d / "agent" / "trajectory.json")
                timed_out.append([loop_share([a[:p] for a in acts] if p else acts) for p in (None, 40, 20)])
    hdr = ["benchmark", "harness", "c", "config", "gpu", "trials", "solved", *CLASSES]
    lines = ["# How agents fail, by harness and server", "",
             f"Share of all trials per class (pooled over repeats). Looping = at least "
             f"{LOOP_SHARE:.0%} of the last {WINDOW} actions repeat an earlier action.", "",
             "| " + " | ".join(hdr) + " |", "|" + "---|" * len(hdr)]
    for (b, h, n, c, g), cnt in sorted(groups.items(), key=lambda kv: (kv[0][0] != "terminal-bench", kv[0][1], kv[0][2], kv[0][3] != "defaults", kv[0][3])):
        tot = sum(cnt.values())
        lines.append("| " + " | ".join([b, h, str(n), c, g, str(tot), f"{100 * cnt['solved'] / tot:.0f}%",
                                         *[f"{100 * cnt[k] / tot:.0f}%" for k in CLASSES]]) + " |")
    # How much the "looping" verdict depends on what counts as the same action.
    lines += ["", "Sensitivity: share of timed-out trials classed as looping when actions only need to "
              "match on their first N characters (looser = more loops).", "",
              "| match on | timed-out trials | looping | still working |", "|---|---|---|---|"]
    for i, prefix in enumerate((None, 40, 20)):
        cnt = Counter()
        for shares in timed_out:
            share = shares[i]
            cnt["loop" if share is not None and share >= LOOP_SHARE else "working"] += 1
        tot = sum(cnt.values()) or 1
        lines.append(f"| {'full text' if prefix is None else f'first {prefix} chars'} | {tot} | "
                     f"{100 * cnt['loop'] / tot:.0f}% | {100 * cnt['working'] / tot:.0f}% |")
    print("\n".join(lines + [""]))


if __name__ == "__main__":
    main()
