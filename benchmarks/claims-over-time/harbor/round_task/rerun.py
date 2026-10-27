"""`claims-rerun`: run a version of the claims agent on the revealed appeals and compare its decisions with the rulings.

    claims-rerun                                   # the agent in /claims/agent/claims_agent, every revealed appeal
    claims-rerun --agent-dir /tmp/try/claims_agent # another copy (the directory must be named claims_agent)
    claims-rerun --ids MN25-1,MN25-2               # only these revealed appeals

Runs inside a round task's trial, the same way for both improver arms. Each call is one rerun of the round's budget,
whatever the number of appeals; a call over budget still runs and is reported to the coordinator. Rows, with the
full transcripts, go to /claims/reruns/<n>/rows.jsonl. Every call appends a `start` line to /claims/reruns/log.jsonl
before it runs anything (so the count holds even if the call is interrupted) and a `finish` line with its scores.
"""

import argparse
import fcntl
import hashlib
import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

CLAIMS = Path("/claims")
BIN = CLAIMS / "bin"
DATA = CLAIMS / "data"
RERUNS = CLAIMS / "reruns"
SECRETS = CLAIMS / "secrets" / "rerun.env"

sys.path.insert(0, str(BIN))
from score import balanced, decision_of, metrics


def jl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open() if line.strip()] if path.exists() else []


def read_env_file(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    pairs = (line.split("=", 1) for line in path.read_text().splitlines() if "=" in line)
    return {k: v for k, v in pairs}


def tree_hash(agent_dir: Path) -> str:
    """The claims agent's own version hash (episode.version_hash), computed without importing the package."""
    digest = hashlib.sha256()
    for path in sorted(agent_dir.iterdir()):
        if path.is_file() and path.suffix in (".py", ".md", ".json", ".toml"):
            digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:12]


def main() -> None:
    ap = argparse.ArgumentParser(prog="claims-rerun", description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--agent-dir", type=Path, default=CLAIMS / "agent" / "claims_agent")
    ap.add_argument("--ids", help="comma-separated revealed appeal ids (default: every revealed appeal)")
    ap.add_argument("--concurrency", type=int, default=6)
    a = ap.parse_args()

    agent_dir = a.agent_dir.resolve()
    if agent_dir.name != "claims_agent" or not (agent_dir / "episode.py").exists():
        sys.exit(f"{agent_dir} is not a claims_agent package directory (it must be named claims_agent)")
    truth = {c["id"]: c["truth"] for c in jl(DATA / "cases.jsonl") if c.get("truth")}
    ids = a.ids.split(",") if a.ids else sorted(truth)
    unknown = [i for i in ids if i not in truth]
    if unknown:
        sys.exit(f"not revealed appeals (reruns are for revealed appeals only): {unknown}")

    budget = json.loads((CLAIMS / "round.json").read_text())["rerun_budget"]
    RERUNS.mkdir(parents=True, exist_ok=True)
    log = RERUNS / "log.jsonl"
    with log.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        n = sum(1 for e in jl(log) if e.get("event") == "start") + 1
        entry = {"event": "start", "n": n, "at": datetime.now(UTC).isoformat(), "agent_dir": str(agent_dir),
                 "agent_version": tree_hash(agent_dir), "ids": ids, "budget": budget, "over_budget": n > budget}
        f.write(json.dumps(entry) + "\n")
    if n > budget:
        print(f"WARNING: this is rerun {n}; the budget is {budget}. It runs, and the coordinator reports it as over budget.",
              flush=True)
    out = RERUNS / str(n) / "rows.jsonl"
    out.parent.mkdir(parents=True, exist_ok=True)

    env = {**os.environ, **read_env_file(SECRETS), "CLAIMS_WORK_DIR": str(DATA)}
    subprocess.run([sys.executable, str(BIN / "run_batch.py"), "--agent-dir", str(agent_dir), "--tag", f"rerun-{n}",
                    "--ids", ",".join(ids), "--out", str(out), "--concurrency", str(a.concurrency)],
                   env=env, check=True, stdout=subprocess.DEVNULL)

    rows = {r["case_id"]: r for r in jl(out)}
    pairs = []
    print(f"\nrerun {n} of {budget}: agent {entry['agent_version']} ({agent_dir}), {len(ids)} revealed appeals")
    print(f"{'appeal':<14} {'ruling':<9} {'decision':<9} right  turns  error")
    for cid in ids:
        row = rows.get(cid, {})
        d = decision_of(row)
        pairs.append((d, truth[cid]))
        print(f"{cid:<14} {truth[cid]:<9} {d or '-':<9} {'yes' if d == truth[cid] else 'no ':<5}  "
              f"{row.get('turns', '-'):<5}  {(row.get('run_error') or '')[:60]}")
    m = metrics(pairs)
    print(f"\naccuracy {m['accuracy']:.3f}, balanced accuracy {balanced(pairs):.3f} "
          f"(decided {m['decided']} of {m['n']}; wrongful denials {m['wrongful_denials']}, "
          f"wrongful approvals {m['wrongful_approvals']})")
    print(f"rows with transcripts: {out}")
    finish = {"event": "finish", "n": n, "at": datetime.now(UTC).isoformat(), "accuracy": m["accuracy"],
              "balanced_accuracy": balanced(pairs), "errors": sum(1 for r in rows.values() if r.get("run_error")),
              "cost_usd": sum(r.get("cost_usd") or 0 for r in rows.values())}
    with log.open("a") as f:
        fcntl.flock(f, fcntl.LOCK_EX)
        f.write(json.dumps(finish) + "\n")

if __name__ == "__main__":
    main()
