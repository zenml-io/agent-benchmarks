"""Offline tests of the scan for claims-agent runs outside an arm's counted rerun path."""

import importlib.util
import sys
from pathlib import Path

_spec = importlib.util.spec_from_file_location("round_script", Path(__file__).with_name("round.py"))
assert _spec is not None and _spec.loader is not None
round_script = importlib.util.module_from_spec(_spec)
sys.modules["round_script"] = round_script
_spec.loader.exec_module(round_script)


def runs_agent(command: str) -> bool:
    return round_script.runs_claims_agent(command)


RUNS = [
    "python -m claims_agent.episode MN25-1 --local",
    "cd /claims && /opt/claims-venv/bin/python -m claims_agent.episode MN25-1 --local",
    "python - <<'EOF'\nfrom claims_agent.episode import run_episode\nimport asyncio\nasyncio.run(run_episode('MN25-1', False))\nEOF",
    "python -c 'from claims_agent.agent import build_agent, Env; a = build_agent(Env(w), c, set(), cfg)'",
    "python /claims/bin/run_batch.py --ids MN25-1",
    "kitaru --server x replay create --session s",
    "grep -c MN25 /claims/ids.txt && python -m claims_agent.episode MN25-1 --local",
]


def test_counts_commands_that_run_the_agent() -> None:
    assert [c for c in RUNS if not runs_agent(c)] == []


NOT_RUNS = [
    "python - <<'EOF'\nfrom claims_agent.agent import Env\nprint(Env(w).call('MN25-1', 'search_precedents', {'treatment': 'MRI'}))\nEOF",
    "cat /claims/agent/claims_agent/episode.py",
    "kitaru agent version register claims-agent --command \"python -m claims_agent.episode\" --working-dir /claims/try",
    "kitaru experiment run start exp --agent claims-agent@5 --wait",
    "claims-rerun --agent-dir /claims/try/claims_agent",
    "cd /claims/agent && CLAIMS_WORK_DIR=/claims/data /opt/claims-venv/bin/python -m claims_agent.episode --help",
    "wc -l /claims/reruns/3/rows.jsonl; ps -eo etime,stat,cmd | rg 'claims_agent.episode' | cut -c1-180 | tail -n 8",
    "ps -eo pid,etime,cmd | rg 'rerun.py|run_batch.py|claims_agent.episode' | cut -c1-200",
    "wc -l /claims/reruns/1/rows.jsonl; ps -eo etime,stat,cmd | rg 'claims_agent.episode' | sed -E 's/.*python -m claims_agent.episode ([^ ]+).*/\\\\1/' | head -15",
]


def test_ignores_commands_that_do_not_run_the_agent() -> None:
    assert [c for c in NOT_RUNS if runs_agent(c)] == []
