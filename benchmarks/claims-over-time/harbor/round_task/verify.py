"""The round task's verifier: check that the candidate is a loadable claims agent and copy it out of the trial.

    /opt/claims-venv/bin/python /claims/bin/verify.py --out /logs/verifier

It does not score accuracy: the coordinator's approval rule does that on the host. It writes, into `--out`:
`candidate.tgz` (the agent directory as the improver left it, CHANGE.md included, caches left out), `CHANGE.md`,
`reruns.jsonl` (a copy of `/claims/reruns/log.jsonl`, when the trial has one), `check.json` (what was checked and why it failed) and `reward.txt`:
1 when the package loads and builds an agent for a revealed appeal and CHANGE.md exists, else 0.
Loading runs with placeholder model credentials, so no model is called; the verifier has no network.
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

CLAIMS = Path("/claims")
LOAD_CHECK = """
import json, sys
from claims_agent import agent, episode
config = agent.load_config()
for key in ("model", "request_limit", "tool_result_chars", "nudge"):
    assert key in config, f"config.toml has no {key}"
env = agent.Env(agent.work_dir())
agent.build_agent(env, sys.argv[1], set(), config)
print(json.dumps({"model": config["model"], "base_url_env": config.get("base_url_env"),
                  "version": episode.version_hash()}))
"""


def check(agent_dir: Path, data: Path) -> dict:
    result: dict = {"agent_dir": str(agent_dir), "exists": agent_dir.is_dir(),
                    "change_md": (agent_dir / "CHANGE.md").is_file()}
    if not result["exists"]:
        return result | {"loadable": False, "error": "agent directory is missing"}
    revealed = [c["id"] for c in map(json.loads, (data / "cases.jsonl").read_text().splitlines()) if c.get("truth")]
    env = {**{k: v for k, v in os.environ.items() if not k.endswith("_API_KEY")}, "CLAIMS_WORK_DIR": str(data),
           "OPENAI_API_KEY": "placeholder-for-load-check", "CLAIMS_AGENT_BASE_URL": "http://127.0.0.1:9/v1",
           "PYTHONDONTWRITEBYTECODE": "1"}
    proc = subprocess.run([sys.executable, "-c", LOAD_CHECK, revealed[0]], cwd=agent_dir.parent, env=env,
                          capture_output=True, text=True, timeout=300, check=False)
    if proc.returncode != 0:
        return result | {"loadable": False, "error": proc.stderr[-3000:]}
    return result | {"loadable": True, "loaded": json.loads(proc.stdout.strip().splitlines()[-1])}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent-dir", type=Path, default=CLAIMS / "agent" / "claims_agent")
    ap.add_argument("--data", type=Path, default=CLAIMS / "data")
    ap.add_argument("--reruns", type=Path, default=CLAIMS / "reruns")
    ap.add_argument("--out", type=Path, required=True)
    a = ap.parse_args()
    a.out.mkdir(parents=True, exist_ok=True)
    try:
        result = check(a.agent_dir, a.data)
    except Exception as exc:  # noqa: BLE001
        result = {"loadable": False, "error": repr(exc)[:3000]}
    if a.agent_dir.is_dir():
        with tarfile.open(a.out / "candidate.tgz", "w:gz") as tar:
            tar.add(a.agent_dir, arcname="claims_agent",
                    filter=lambda t: None if "__pycache__" in t.name or t.name.endswith(".pyc") else t)
        if (a.agent_dir / "CHANGE.md").is_file():
            shutil.copy(a.agent_dir / "CHANGE.md", a.out / "CHANGE.md")
    if (a.reruns / "log.jsonl").is_file():
        shutil.copy(a.reruns / "log.jsonl", a.out / "reruns.jsonl")
    reward = int(bool(result.get("loadable") and result.get("change_md")))
    (a.out / "check.json").write_text(json.dumps(result | {"reward": reward}, indent=2))
    (a.out / "reward.txt").write_text(f"{reward}\n")
    print(json.dumps(result | {"reward": reward})[:2000])


if __name__ == "__main__":
    main()
