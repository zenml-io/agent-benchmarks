"""
How long do two runs of the same agent on the same task stay on the same path?

    python divergence.py        # markdown to stdout (divergence.md)

Replay-based evaluation (re-run an agent with the tool answers recorded in an earlier run)
is only faithful until the new run asks for something the recorded run never did. This
measures, over our Terminal-Bench trajectories, the step at which two runs first take a
different action, for pairs that differ by:

  rerun          nothing (same harness, model, settings): sampling alone
  infra change   GPU / load / serving settings only, same model
  thinking off   the model's reasoning switched off (a settings change on the agent side)
  model change   Qwen3.8-27B (dense) vs Qwen3.6-35B-A3B (MoE), same harness and load

An action is the list of shell commands an agent step issued. Two steps match "exactly" if
the commands are identical after whitespace normalization, and "nearly" if their text is at
least 80% similar (difflib), which forgives a different file name or flag.

Lookup coverage is the fairer test for a replay tool that answers each tool call from a table
of recorded answers regardless of order: the share of the new run's commands (individually)
that appear anywhere in the recorded run, and how many of its first commands are all covered.
"""

import json
import random
import re
import statistics as st
from collections import defaultdict
from difflib import SequenceMatcher
from itertools import combinations

import _paths  # noqa: F401  (harness on sys.path)
import analysis as an
import experiment as ex

INFRA_ONLY = {"defaults", "h200", "b200", "kv-fp8", "weights-fp8", "no-prefix-cache", "spec-mtp", "h200-spec-mtp"}
MAX_PAIRS = 1500
random.seed(0)


def actions(traj_path):
    try:
        d = json.loads(traj_path.read_text())
    except (OSError, json.JSONDecodeError):
        return None
    out = []
    for s in d.get("steps", []):
        if s.get("source") != "agent":
            continue
        cmds = []
        for c in s.get("tool_calls") or []:
            a = c.get("arguments") or {}
            cmd = a.get("keystrokes") or a.get("command") or ""
            cmds.append(re.sub(r"\s+", " ", str(cmd)).strip())
        cmds = [c for c in cmds if c]
        if cmds:
            out.append(" ; ".join(cmds))
    return out or None


def diverge(a, b, near):
    """Index (1-based) of the first step that differs; len+1 if one is a prefix of the other."""
    for i, (x, y) in enumerate(zip(a, b)):
        same = x == y if not near else (x == y or SequenceMatcher(None, x, y).ratio() >= 0.8)
        if not same:
            return i + 1
    return min(len(a), len(b)) + 1


def coverage(rec, new):
    """(share of new's commands found in rec, number of leading commands of new all found in rec)."""
    have = {c for step in rec for c in step.split(" ; ")}
    cmds = [c for step in new for c in step.split(" ; ")]
    hits = [c in have for c in cmds]
    lead = next((i for i, h in enumerate(hits) if not h), len(hits))
    return (sum(hits) / len(hits) if hits else 0.0), lead


def load_trials():
    """(harness, config, c, gpu, task) -> [(actions, ok)]"""
    out = defaultdict(list)
    for r in an.load():
        for d in (ex.JOBS_DIR / r["job_name"]).glob("*/agent/trajectory.json"):
            res = d.parent.parent / "result.json"
            try:
                data = json.loads(res.read_text())
            except (OSError, json.JSONDecodeError):
                continue
            task = data.get("task_name") or d.parent.parent.name.rsplit("__", 1)[0]
            reward = ((data.get("verifier_result") or {}).get("rewards") or {}).get("reward")
            ok = reward is not None and float(reward) >= 1.0  # same rule as experiment.parse_job
            acts = actions(d)
            if acts:
                out[(r["harness"], r["config"], r["concurrency"], r["gpu"], task)].append((acts, ok))
    return out


def pairs_for(trials, kind):
    ps = []
    keys = list(trials)
    if kind == "rerun":
        for k in keys:
            ps += list(combinations(trials[k], 2))
    else:
        by_task = defaultdict(list)
        for k in keys:
            by_task[(k[0], k[4])].append(k)
        for (_, _), ks in by_task.items():
            for k1, k2 in combinations(ks, 2):
                c1, c2 = k1[1], k2[1]
                if kind == "infra change":
                    ok = c1 in INFRA_ONLY and c2 in INFRA_ONLY and k1[1:4] != k2[1:4]
                elif kind == "thinking off":
                    ok = {c1, c2} == {"defaults", "no-thinking"} and k1[2:4] == k2[2:4]
                elif kind == "model change":
                    ok = {c1, c2} == {"defaults", "moe-a3b"} and k1[2:4] == k2[2:4]
                else:
                    ok = False
                if ok:
                    ps += [(a, b) for a in trials[k1] for b in trials[k2]]
    if len(ps) > MAX_PAIRS:
        ps = random.sample(ps, MAX_PAIRS)
    return ps


def main():
    trials = load_trials()
    n = sum(len(v) for v in trials.values())
    L = ["# How soon do two runs of the same task diverge?", "",
         f"{n} Terminal-Bench trajectories with recorded actions. Up to {MAX_PAIRS} sampled pairs per row.", ""]
    for near in (False, True):
        L += [f"## {'Near' if near else 'Exact'} match ({'>= 80% similar text' if near else 'identical commands'})", "",
              "| harness | pair differs by | pairs | median first differing step | differ at step 1 | by step 3 | "
              "share of the shorter run replayable | outcomes differ: diverged by step 3 | after step 3 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for h in ("terminus-2", "mini-swe-agent"):
            sub = {k: v for k, v in trials.items() if k[0] == h}
            for kind in ("rerun", "infra change", "thinking off", "model change"):
                ps = pairs_for(sub, kind)
                if not ps:
                    continue
                dv = [diverge(a[0], b[0], near) for a, b in ps]
                frac = [min(1.0, (d - 1) / min(len(a[0]), len(b[0]))) for d, (a, b) in zip(dv, ps)]
                early = [a[1] != b[1] for d, (a, b) in zip(dv, ps) if d <= 3]
                late = [a[1] != b[1] for d, (a, b) in zip(dv, ps) if d > 3]
                pct = lambda xs: f"{100 * st.mean(xs):.0f}% (n={len(xs)})" if xs else "n/a"  # noqa: E731
                L.append(f"| {h} | {kind} | {len(ps)} | {st.median(dv):.0f} | {100 * st.mean(d == 1 for d in dv):.0f}% | "
                         f"{100 * st.mean(d <= 3 for d in dv):.0f}% | {100 * st.mean(frac):.0f}% | {pct(early)} | {pct(late)} |")
        L.append("")
    L += ["## Lookup coverage (order-free, exact command text)", "",
          "| harness | pair differs by | pairs | new run's commands found in the recorded run | "
          "leading commands answerable before the first miss (median) | runs with any recorded answer missing |",
          "|---|---|---|---|---|---|"]
    for h in ("terminus-2", "mini-swe-agent"):
        sub = {k: v for k, v in trials.items() if k[0] == h}
        for kind in ("rerun", "infra change", "thinking off", "model change"):
            ps = pairs_for(sub, kind)
            if not ps:
                continue
            cov = [coverage(a[0], b[0]) for a, b in ps]
            L.append(f"| {h} | {kind} | {len(ps)} | {100 * st.mean(c[0] for c in cov):.0f}% | "
                     f"{st.median(c[1] for c in cov):.0f} | {100 * st.mean(c[0] < 1 for c in cov):.0f}% |")
    print("\n".join(L))


if __name__ == "__main__":
    main()
