"""Offline check of the replay and step-check environment (no model calls, no Kitaru server).

  TAU2_DATA_DIR=<tau2-bench checkout>/data uv run --extra replay --extra step-check python scripts/check_harness.py

Imports every harness module, loads tau2's Telecom test split and checks that each committed
per-episode row's task id is the task at that case index, and prints the pinned package versions.
"""
import importlib.metadata
import json
import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path[:0] = [os.path.join(HERE, "harness", "replay"), os.path.join(HERE, "harness", "step_check")]

import collect_replays  # noqa: E402,F401
import model_router  # noqa: E402,F401
import run_baseline  # noqa: E402,F401
import swap_run  # noqa: E402,F401
import tau2_kitaru_agent.episode  # noqa: E402,F401
import tau2_reward_evaluator  # noqa: E402,F401
from tau2.registry import registry  # noqa: E402

tasks = registry.get_tasks_loader("telecom")("test")
tools = sorted(t.name for t in registry.get_env_constructor("telecom")().get_tools())
runs = os.path.join(HERE, "results", "runs", "replay")
rows = [json.loads(line) for line in open(os.path.join(runs, "replays.jsonl"))]
base = [json.loads(line) for line in open(os.path.join(runs, "baseline.jsonl"))]
print("test tasks:", len(tasks), "| agent tools:", len(tools))
print("replay rows:", len(rows), "| task id mismatches:", sum(r["task_id"] != tasks[r["case"]].id for r in rows))
print("baseline log rows:", len(base), "| task id mismatches:", sum(b["tau2"]["task_id"] != tasks[b["case"]].id for b in base))
for dist in ("kitaru", "kitaru-pydantic-ai", "kitaru-model-swap", "tau2", "pydantic-ai-slim", "openai", "genai-prices"):
    print(dist, importlib.metadata.version(dist))
