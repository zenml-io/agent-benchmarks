"""Paths for the analysis scripts: the shared harness on sys.path, the published rows as input.

Input rows: $ATTEMPTS_FILE, default results/runs/attempts.jsonl (the published rows).
Raw Harbor job directories: $BENCH_DIR/jobs (default <benchmark>/jobs). They are not published;
scripts that need them say so, and the failure-class tables fall back to the per-trial
`failure_class` stored in the published rows.
"""
import os
import sys
from pathlib import Path

BENCH = Path(__file__).resolve().parents[1]
HARNESS = BENCH.parent / "self-hosted-agents-harness"
sys.path.insert(0, str(HARNESS))
os.environ.setdefault("BENCH_DIR", str(BENCH))
os.environ.setdefault("ATTEMPTS_FILE", str(BENCH / "results" / "runs" / "attempts.jsonl"))
ATTEMPTS = Path(os.environ["ATTEMPTS_FILE"])
