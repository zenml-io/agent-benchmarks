"""Run the claims-over-time experiment round by round: three lines of the claims agent, two improvers, one approval rule.

    uv run --extra agent python scripts/round.py --frontier-preset gpt-6.1-sol --rounds 1-8
    uv run --extra agent python scripts/round.py --frontier-preset gpt-6.1-sol --rounds 3 --stop-after improve
    uv run --extra agent python scripts/round.py --mini --frontier-preset smoke-gpt-5-mini

Lines: `left_alone` (the starting agent, only ever switched to the open model), `codex` and `pro` (each improved
once per round by its improver, in a Harbor trial: Codex, and the ZenML Pro agent). Each line's versions are copies of the package directory under
`<rounds>/<line>/versions/<n>/claims_agent/`; `<rounds>/<line>/current.json` names the current one.

Round k, in order (each step writes `<rounds>/round-<k>/<step>.json` when it finishes, and a rerun skips it):
  switch   (only in round --switch-round) every line's current version gets the open model preset as a new version
  run      each line's current version decides every appeal of batch k: left_alone and codex locally, pro through
           the Kitaru workspace (one session run per appeal, each executed by its own worker on this machine, scoped
           to that agent version and that job); rows in <runs>/<line>/
  score    score.py per line on batch k and on batches 1..k, against the real rulings, on this machine only
  reveal   the revealed appeals of batches 1..k get their ruling in the round's view of the appeals
  cohort   a new version of the Kitaru cohort of the pro line's revealed sessions (batches 1..k)
  improve  one Harbor round task per improver arm (harbor/round_task/), both trials at once; no worker runs on this
           machine meanwhile: the pro trial runs its own, so versions the Pro agent registers run only in its sandbox
  approve  the candidate each trial left is run with the current version on every revealed appeal so far (locally,
           cached by version hash and appeal); it ships only if its balanced accuracy is at least as high. Reruns are
           counted per arm (Codex: `claims-rerun` calls; pro: Kitaru experiment runs), and the improver's own command
           log is scanned for runs of the claims agent outside that path, which count as over budget
  audit    checks the Kitaru workspace: no evaluation of an unrevealed appeal, no task of a version the Pro agent
           registered claimed by a worker on this machine

Fairness rules this script enforces: every agent version runs with a view of the appeals that has no ruling at all
(<rounds>/views/agent/); a trial and the Kitaru worker see rulings for revealed appeals only (<rounds>/views/round-<k>/);
nothing about unrevealed appeals is scored anywhere but here.

Environment: OPENAI_API_KEY; CLAIMS_AGENT_BASE_URL (from the switch round on). The pro line needs the ZenML Pro agent
bundle, which is not public: PRO_AGENT_DIR (its directory, put on Harbor's import path; this script runs its
`prepare` before each round's trials), PRO_ROUND_IMAGE (default claims-over-time-round-pro:latest, built by
harbor/round_task/build_images.sh), KITARU_API_URL and KITARU_PRO_API_KEY (read from work/.env when not set). Without
PRO_AGENT_DIR only the left_alone and codex lines run. Docker must reach OrbStack (DOCKER_CONTEXT defaults to orbstack).
"""

import argparse
import concurrent.futures
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import string
import subprocess
import sys
import tarfile
import time
import tomllib
import uuid
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

BENCH = Path(__file__).resolve().parent.parent
WORK = Path(os.environ.get("CLAIMS_WORK_DIR") or BENCH / "work")
FROZEN_AGENT = BENCH / "harness" / "claims_agent"
INSTRUCTIONS = BENCH / "harness" / "improver_instructions.md"
TASK_TEMPLATE = BENCH / "harbor" / "round_task" / "template"
TRIAL_TOOLS = [BENCH / "harbor" / "round_task" / "rerun.py", BENCH / "harbor" / "round_task" / "verify.py",
               BENCH / "scripts" / "run_batch.py", BENCH / "scripts" / "score.py"]
KITARU = Path(sys.executable).parent / "kitaru"

STEPS = ("switch", "run", "score", "reveal", "cohort", "improve", "approve", "audit")
TOTAL_ROUNDS = 8
CODEX_IMAGE = "claims-over-time-round-codex:latest"
HARBOR_AGENTS = {"codex": "codex.agent:CodexRoundAgent", "pro": "round_task.pro_round_agent:ProRoundAgent"}
TRIAL_AGENT_DIR = "/claims/agent/claims_agent"
TRIAL_CASES = "/claims/data/cases.jsonl"
# The Pro agent's only rerun path is Kitaru experiments, so its trial gets neither `claims-rerun` nor run_batch.py.
TRIAL_TOOLS_BY_ARM = {"codex": TRIAL_TOOLS, "pro": [BENCH / "harbor" / "round_task" / "verify.py"]}
# Commands that run the claims agent outside an arm's counted rerun path (`claims-rerun`, Kitaru experiments).
OUTSIDE_RUNS = re.compile(r"-m\s+claims_agent\.episode|(^|[\s;&|(])(import\s+claims_agent\b|from\s+claims_agent(\.\w+)?\s+import\b)"
                          r"|python[\d.]*\s+\S*run_batch\.py|\bkitaru\b.*\breplay\s+create\b|session_runs\.create")
# The command a Kitaru agent version is registered with names the episode module without running it.
REGISTERED_COMMAND = re.compile(r"--command[\s=]+(\"[^\"]*\"|'[^']*'|\S+)")
# A candidate whose Python adds any of these is not shipped: they are how an agent could read rulings or reach out.
INTEGRITY = re.compile(r"truth|cases\.jsonl|imr\.csv|\.\./|/Users/|os\.environ|subprocess|socket|urllib|requests|httpx")

# Model presets: the claims agent's `model`, `base_url_env` and `[model_settings]`, always set together.
PRESETS: dict[str, dict[str, Any]] = {
    # GPT-6 models need the Responses API for function tools with reasoning; reasoning tokens count toward max_tokens.
    "gpt-6.1-sol": {"model": "openai-responses:gpt-6.1-sol", "base_url_env": "", "model_settings": {"max_tokens": 16000}},
    # The self-hosted open model, as the frozen package ships it.
    "open": {"model": "agent-model", "base_url_env": "CLAIMS_AGENT_BASE_URL",
             "model_settings": {"temperature": 0.6, "max_tokens": 4096}},
    # Cheap smoke tests only.
    "smoke-gpt-5-mini": {"model": "openai-chat:gpt-5-mini", "base_url_env": "",
                         "model_settings": {"temperature": 0.6, "max_tokens": 4096}},
}


@dataclass(frozen=True)
class Settings:
    frontier_preset: str
    open_preset: str
    switch_round: int
    improver_model: str
    rerun_budget: int
    minutes: int
    pro_agent: str
    mini: bool
    pro_arm: bool

    @property
    def lines(self) -> tuple[str, ...]:
        return ("left_alone", "codex", "pro") if self.pro_arm else ("left_alone", "codex")

    @property
    def arms(self) -> tuple[str, ...]:
        return ("codex", "pro") if self.pro_arm else ("codex",)

    @property
    def batch_size(self) -> int:
        return 10 if self.mini else 100

    @property
    def revealed_per_batch(self) -> int:
        return 4 if self.mini else 20

    def preset_for(self, k: int) -> str:
        return self.open_preset if k >= self.switch_round else self.frontier_preset


@dataclass(frozen=True)
class Paths:
    rounds: Path
    runs: Path

    def round(self, k: int) -> Path:
        return self.rounds / f"round-{k}"

    def line(self, line: str) -> Path:
        return self.rounds / line

    @property
    def agent_view(self) -> Path:
        return self.rounds / "views" / "agent"

    def revealed_view(self, k: int) -> Path:
        return self.agent_view if k == 0 else self.rounds / "views" / f"round-{k}"


# ---------------------------------------------------------------- small helpers

def jl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open() if line.strip()] if path.exists() else []


def write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, default=str))
    tmp.replace(path)


def now() -> str:
    return datetime.now(UTC).isoformat()


def log(message: str) -> None:
    print(f"[round {datetime.now(UTC).strftime('%H:%M:%S')}] {message}", flush=True)


def load_module(path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(path.stem, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


score_mod = load_module(BENCH / "scripts" / "score.py")


def tree_hash(agent_dir: Path) -> str:
    """The same hash as the package's own `episode.version_hash` (files ending .py .md .json .toml, by name)."""
    digest = hashlib.sha256()
    for path in sorted(agent_dir.iterdir()):
        if path.is_file() and path.suffix in (".py", ".md", ".json", ".toml"):
            digest.update(path.name.encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()[:12]


def load_dotenv(path: Path) -> None:
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


# ---------------------------------------------------------------- appeals, plan and views

def all_cases() -> list[dict[str, Any]]:
    return jl(WORK / "cases.jsonl")


def make_plan(s: Settings) -> dict[int, dict[str, list[str]]]:
    """Per batch: the appeal ids the lines decide and the ids revealed after it."""
    cases = sorted(all_cases(), key=lambda c: c["order"])
    plan = {}
    for k in range(1, TOTAL_ROUNDS + 1):
        batch = [c for c in cases if c["batch"] == k]
        revealed = [c for c in batch if c["revealed"]]
        if s.mini:
            # Two of each outcome among the revealed (when the batch has them), so balanced accuracy means something.
            shown = ([c for c in revealed if c["truth"] == "uphold"][:2] + [c for c in revealed if c["truth"] == "overturn"][:2])
            shown += [c for c in revealed if c not in shown][:4 - len(shown)]
            hidden = [c for c in batch if not c["revealed"]][:s.batch_size - len(shown)]
            batch, revealed = sorted(shown + hidden, key=lambda c: c["order"]), shown
        plan[k] = {"ids": [c["id"] for c in batch], "revealed": sorted(c["id"] for c in revealed)}
    return plan


def revealed_through(plan: dict[int, dict[str, list[str]]], k: int) -> list[str]:
    return sorted(i for j in range(1, k + 1) for i in plan[j]["revealed"])


def write_view(directory: Path, truth_ids: set[str]) -> None:
    """All appeals, with `truth` kept only for `truth_ids` and `revealed` saying which those are."""
    directory.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in all_cases():
        row = {k: v for k, v in c.items() if k != "truth"} | {"revealed": c["id"] in truth_ids}
        if c["id"] in truth_ids:
            row["truth"] = c["truth"]
        rows.append(row)
    leaked = [r["id"] for r in rows if "truth" in r and r["id"] not in truth_ids]
    assert not leaked, leaked
    (directory / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    link = directory / "precedents.jsonl"
    if not link.exists():
        link.symlink_to(WORK / "precedents.jsonl")


# ---------------------------------------------------------------- agent versions

def toml_value(value: Any) -> str:
    return json.dumps(value) if isinstance(value, str) else repr(value).lower() if isinstance(value, bool) else repr(value)


def apply_preset(agent_dir: Path, name: str) -> None:
    """Set `model`, `base_url_env` and the whole `[model_settings]` table of config.toml to a preset."""
    preset, path = PRESETS[name], agent_dir / "config.toml"
    text = path.read_text()
    for key in ("model", "base_url_env"):
        text, n = re.subn(rf"(?m)^{key}\s*=.*$", f"{key} = {toml_value(preset[key])}", text)
        if n != 1:
            raise RuntimeError(f"{path}: expected one top-level `{key} =` line, found {n}")
    table = "[model_settings]\n" + "".join(f"{k} = {toml_value(v)}\n" for k, v in preset["model_settings"].items())
    text, n = re.subn(r"(?ms)^\[model_settings\]\n.*?(?=^\[|\Z)", table, text)
    if n != 1:
        raise RuntimeError(f"{path}: expected one [model_settings] table, found {n}")
    path.write_text(text)
    config = tomllib.loads(text)
    got = {"model": config["model"], "base_url_env": config.get("base_url_env", ""), "model_settings": config.get("model_settings")}
    if got != preset:
        raise RuntimeError(f"{path}: preset {name} did not apply cleanly: {got}")


def read_model(agent_dir: Path) -> tuple[str, str]:
    config = tomllib.loads((agent_dir / "config.toml").read_text())
    return config.get("model", ""), config.get("base_url_env", "")


def current(p: Paths, line: str) -> dict[str, Any]:
    return json.loads((p.line(line) / "current.json").read_text())


def version_dir(p: Paths, line: str, n: int) -> Path:
    return p.line(line) / "versions" / str(n) / "claims_agent"


def add_version(p: Paths, line: str, source: Path, k: int, reason: str, change_md: str | None = None) -> dict[str, Any]:
    versions = p.line(line) / "versions"
    n = max((int(d.name) for d in versions.iterdir() if d.name.isdigit()), default=-1) + 1 if versions.exists() else 0
    dest = version_dir(p, line, n)
    shutil.copytree(source, dest, ignore=shutil.ignore_patterns("__pycache__", "*.pyc", "CHANGE.md"))
    if change_md is not None:
        (dest.parent / "CHANGE.md").write_text(change_md)
    meta = {"version": n, "hash": tree_hash(dest), "round": k, "reason": reason, "created": now(),
            "model": read_model(dest)}
    write_json(dest.parent / "meta.json", meta)
    write_json(p.line(line) / "current.json", meta)
    with (p.line(line) / "history.jsonl").open("a") as f:
        f.write(json.dumps(meta) + "\n")
    log(f"{line}: version {n} ({meta['hash']}) is now current: {reason}")
    return meta


def init_lines(s: Settings, p: Paths) -> None:
    settings_file = p.rounds / "settings.json"
    record = asdict(s) | {"frozen_agent_hash": tree_hash(FROZEN_AGENT),
                          "presets": {s.frontier_preset: PRESETS[s.frontier_preset], s.open_preset: PRESETS[s.open_preset]}}
    if settings_file.exists():
        old = json.loads(settings_file.read_text())
        changed = {k: (old.get(k), v) for k, v in record.items() if old.get(k) != v}
        if changed:
            raise SystemExit(f"{settings_file} was written with other settings: {changed}. Use the same settings, or "
                             f"another rounds directory.")
    else:
        write_json(settings_file, record | {"created": now()})
    for line in s.lines:
        if (p.line(line) / "current.json").exists():
            continue
        stage = p.rounds / "staging" / line / "claims_agent"
        shutil.rmtree(stage.parent, ignore_errors=True)
        shutil.copytree(FROZEN_AGENT, stage, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
        apply_preset(stage, s.preset_for(1))
        add_version(p, line, stage, 1, f"starting version: the frozen package ({record['frozen_agent_hash']}) with "
                                       f"model preset {s.preset_for(1)}")
        shutil.rmtree(stage.parent)
    write_view(p.agent_view, set())


# ---------------------------------------------------------------- running the agent

def run_batch(rows_file: Path, ids: list[str], work_view: Path, agent_dir: Path, concurrency: int = 8) -> list[dict[str, Any]]:
    """run_batch.py (local mode) on `ids`, then once more on the appeals whose row has a run_error; returns the rows."""
    rows_file.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, str(BENCH / "scripts" / "run_batch.py"), "--tag", rows_file.stem, "--out", str(rows_file),
           "--ids", ",".join(ids), "--concurrency", str(concurrency), "--agent-dir", str(agent_dir)]
    full_env = {**os.environ, "CLAIMS_WORK_DIR": str(work_view)}
    with (rows_file.parent / f"{rows_file.stem}.log").open("a") as out:
        subprocess.run(cmd, env=full_env, check=True, stdout=out, stderr=subprocess.STDOUT)
        if any(r.get("run_error") for r in jl(rows_file) if r["case_id"] in ids):
            subprocess.run([*cmd, "--retry-errors"], env=full_env, check=True, stdout=out, stderr=subprocess.STDOUT)
    rows = {r["case_id"]: r for r in jl(rows_file)}
    missing = [i for i in ids if i not in rows]
    if missing:
        raise RuntimeError(f"{rows_file}: no row for {missing}")
    return [rows[i] for i in ids]


def done(p: Paths, k: int, step: str) -> dict[str, Any]:
    """The result a finished step recorded."""
    return json.loads((p.round(k) / f"{step}.json").read_text())["result"]


def row_cost(row: dict[str, Any]) -> float:
    value = row.get("cost_usd")
    if value is None:
        value = row.get("kitaru_cost_usd")
    return float(value or 0.0)


# ---------------------------------------------------------------- Kitaru

def kitaru_env(p: Paths) -> dict[str, str]:
    url, key = os.environ.get("KITARU_API_URL"), os.environ.get("KITARU_PRO_API_KEY")
    if not (url and key):
        raise SystemExit("set KITARU_API_URL and KITARU_PRO_API_KEY (work/.env)")
    return {"KITARU_API_URL": url, "KITARU_API_KEY": key, "KITARU_CONFIG_DIR": str(p.rounds / ".kitaru-config"),
            "KITARU_NON_INTERACTIVE": "1", "KITARU_DISABLE_CLIENT_ANALYTICS": "1"}


def kitaru(p: Paths, *args: str) -> dict[str, Any]:
    proc = subprocess.run([str(KITARU), *args, "-o", "json"], env={**os.environ, **kitaru_env(p)},
                          capture_output=True, text=True, timeout=300, check=False)
    try:
        out = json.loads(proc.stdout)
    except ValueError:
        out = {"ok": False}
    if proc.returncode != 0 or not out.get("ok", True):
        raise RuntimeError(f"kitaru {' '.join(args)} failed ({proc.returncode}): {proc.stdout[-1500:]} {proc.stderr[-1500:]}")
    return out


def kitaru_list(p: Paths, *args: str) -> list[dict[str, Any]]:
    items, cursor = [], None
    while True:
        out = kitaru(p, *args, "--size", "1000", *(["--cursor", cursor] if cursor else []))
        items += out.get("items", [])
        cursor = (out.get("page") or {}).get("next_cursor")
        if not cursor:
            return items


def repeat(flag: str, values: list[str]) -> list[str]:
    """`--flag a --flag b`: the CLI takes one value per occurrence of a repeatable flag."""
    return [x for value in values for x in (flag, value)]


def kitaru_find(p: Paths, *args: str) -> dict[str, Any] | None:
    """The item of a `kitaru ... get`, or None when the workspace has no such object."""
    try:
        return kitaru(p, *args)["item"]
    except RuntimeError as exc:
        if "not_found" in str(exc):
            return None
        raise


def version_of(out: dict[str, Any]) -> dict[str, Any]:
    """The version object in a register/create answer (a parent create nests it under `version`)."""
    item = out["item"]
    return item["version"] if isinstance(item.get("version"), dict) else item


def kitaru_registry(p: Paths) -> dict[str, Any]:
    path = p.line("pro") / "kitaru.json"
    return json.loads(path.read_text()) if path.exists() else {"versions": {}}


def register_pro_version(s: Settings, p: Paths) -> dict[str, Any]:
    """The Kitaru agent version that runs the pro line's current version (registered on first use).

    The command finds Python on PATH, so the same registered version runs in a host worker (PATH starts with the
    benchmark's .venv) and in the pro trial's worker (PATH starts with /opt/claims-venv, and the trial image holds
    a read-only copy of the version at the same working directory)."""
    reg, cur = kitaru_registry(p), current(p, "pro")
    if cur["hash"] in reg["versions"]:
        return reg["versions"][cur["hash"]]
    workdir = str(version_dir(p, "pro", cur["version"]).parent)
    flags = ["--command", "python -m claims_agent.episode", "--working-dir", workdir,
             "--description", f"pro line version {cur['version']} ({cur['hash']})"]
    if "agent_id" not in reg:
        existing = kitaru_find(p, "agent", "get", s.pro_agent)
        if existing is None:
            out = kitaru(p, "agent", "register", s.pro_agent, *flags)
            reg |= {"agent": s.pro_agent, "agent_id": out["item"]["agent"]["id"]}
        else:
            reg |= {"agent": s.pro_agent, "agent_id": existing["id"], "adopted_existing_agent": True}
            out = kitaru(p, "agent", "version", "register", s.pro_agent, *flags)
    else:
        out = kitaru(p, "agent", "version", "register", s.pro_agent, *flags)
    version = version_of(out)
    entry = {"id": str(version["id"]), "number": version["version"], "line_version": cur["version"],
             "workdir": workdir, "created": now()}
    reg["versions"][cur["hash"]] = entry
    write_json(p.line("pro") / "kitaru.json", reg)
    log(f"kitaru: registered {s.pro_agent} version {entry['number']} ({entry['id']}) for line version {cur['version']}")
    return entry


def register_evaluator(s: Settings, p: Paths) -> dict[str, Any]:
    """The evaluator that scores the pro line's sessions: a new version of it whenever round.py registers it."""
    reg = kitaru_registry(p)
    if "evaluator" not in reg:
        name, script = f"{s.pro_agent}-decision-correct", str(BENCH / "harness" / "evaluator.py")
        if kitaru_find(p, "evaluator", "get", name) is None:
            out = kitaru(p, "evaluator", "register", name, "--script", script, "--entrypoint", "evaluate",
                         "--agent-id", str(reg["agent_id"]))
        else:
            out = kitaru(p, "evaluator", "version", "register", name, "--script", script, "--entrypoint", "evaluate")
        reg["evaluator"] = {"name": name, "version": version_of(out)["version"],
                            "sha256": hashlib.sha256(Path(script).read_bytes()).hexdigest()}
        write_json(p.line("pro") / "kitaru.json", reg)
    return reg["evaluator"]


def host_worker_command(agent_version_id: str, job_id: str) -> list[str]:
    """A worker on this machine scoped to one agent version and one job: it never claims a job the round runner did
    not create (an experiment of the Pro agent, a version it registered), and it ends when its job settles."""
    return [str(KITARU), "worker", "start", "--claim", f"agent={agent_version_id}", "--job-id", job_id,
            "--concurrency", "1", "--name", f"claims-host-{job_id[-12:]}"]


async def run_kitaru_appeal(p: Paths, client: Any, case_id: str, tag: str, version_id: str, work_view: Path,
                            log_file: Path) -> dict[str, Any]:
    """One session run of `case_id`, executed by its own job-scoped host worker; returns the result row."""
    import asyncio

    from kitaru.api_models.v1.filter import FilterCondition, FilterOp
    from kitaru.api_models.v1.session import SessionListParams
    from kitaru.api_models.v1.session_run import SessionRunCreateRequest

    job = await client.session_runs.create(SessionRunCreateRequest(
        agent_version_id=uuid.UUID(version_id), inputs=f"Review appeal {case_id}.", name=f"claims {tag} {case_id}"))
    env = {**os.environ, **kitaru_env(p), "CLAIMS_WORK_DIR": str(work_view),
           "PATH": f"{Path(sys.executable).parent}{os.pathsep}{os.environ.get('PATH', '')}"}
    command = host_worker_command(version_id, str(job.id))
    with log_file.open("a") as out:
        proc = await asyncio.create_subprocess_exec(*command, env=env, stdout=out, stderr=subprocess.STDOUT)
        try:
            await asyncio.wait_for(proc.wait(), timeout=3600)
        except TimeoutError:
            proc.send_signal(signal.SIGTERM)
            await proc.wait()
    job = await client.jobs.get(job.id)
    tasks = (await client.jobs.list_tasks(job.id)).items
    task = tasks[-1] if tasks else None
    result = task.result if task is not None else None
    row: dict[str, Any] = result if isinstance(result, dict) and result.get("case_id") else \
        {"case_id": case_id, "final": None, "run_error": f"job {job.status.value}: {job.error or (task.error if task else '')}"[:500]}
    row |= {"kitaru_job_id": str(job.id), "host_worker": command[-1], "tag": tag, "kitaru_agent_version": version_id}
    if task is not None:
        sessions = (await client.sessions.list(SessionListParams(
            filter=FilterCondition(field="task_id", op=FilterOp.EQ, value=str(task.id))))).items
        if sessions:
            row |= {"session_id": str(sessions[0].id), "session_status": sessions[0].status.value,
                    "kitaru_cost_usd": float(sessions[0].cost) if sessions[0].cost is not None else None}
    return row


def run_kitaru_batch(p: Paths, rows_file: Path, ids: list[str], version_id: str, work_view: Path, tag: str,
                     concurrency: int) -> list[dict[str, Any]]:
    """Like run_batch() in Kitaru mode, but each appeal's job gets its own job-scoped host worker; a rerun skips
    appeals that have a row and retries, once, those whose row has a run_error."""
    import asyncio

    from kitaru.client import KitaruAPIClient

    async def run(todo: list[str]) -> None:
        sem = asyncio.Semaphore(concurrency)
        async with KitaruAPIClient(base_url=kitaru_env(p)["KITARU_API_URL"], api_key=kitaru_env(p)["KITARU_API_KEY"]) as client:
            async def one(case_id: str) -> None:
                async with sem:
                    row = await run_kitaru_appeal(p, client, case_id, tag, version_id, work_view,
                                                  rows_file.with_suffix(".workers.log"))
                with rows_file.open("a") as f:
                    f.write(json.dumps(row) + "\n")
            await asyncio.gather(*(one(i) for i in todo))

    rows_file.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(2):
        rows = {r["case_id"]: r for r in jl(rows_file)}
        todo = [i for i in ids if i not in rows or (attempt and rows[i].get("run_error"))]
        if attempt and todo:
            rows_file.write_text("".join(json.dumps(r) + "\n" for r in rows.values() if r["case_id"] not in todo))
        if todo:
            asyncio.run(run(todo))
    rows = {r["case_id"]: r for r in jl(rows_file)}
    missing = [i for i in ids if i not in rows]
    if missing:
        raise RuntimeError(f"{rows_file}: no row for {missing}")
    return [rows[i] for i in ids]


# ---------------------------------------------------------------- steps

def step_switch(s: Settings, p: Paths, k: int, plan: dict) -> dict[str, Any]:
    out = {}
    for line in s.lines:
        cur = current(p, line)
        stage = p.rounds / "staging" / line / "claims_agent"
        shutil.rmtree(stage.parent, ignore_errors=True)
        shutil.copytree(version_dir(p, line, cur["version"]), stage)
        apply_preset(stage, s.open_preset)
        out[line] = add_version(p, line, stage, k, f"model switch to preset {s.open_preset} before batch {k}")
        shutil.rmtree(stage.parent)
    return out


def step_run(s: Settings, p: Paths, k: int, plan: dict, concurrency: int) -> dict[str, Any]:
    ids = plan[k]["ids"]

    def run_line(line: str) -> dict[str, Any]:
        cur, rows_file = current(p, line), p.runs / line / f"batch-{k}.jsonl"
        if line == "pro":
            version = register_pro_version(s, p)
            register_evaluator(s, p)
            rows = run_kitaru_batch(p, rows_file, ids, version["id"], p.agent_view, f"pro-b{k}", concurrency)
        else:
            rows = run_batch(rows_file, ids, p.agent_view, agent_dir=version_dir(p, line, cur["version"]),
                             concurrency=concurrency)
        return {"version": cur["version"], "hash": cur["hash"], "rows": str(rows_file), "n": len(rows),
                "errors": sum(1 for r in rows if r.get("run_error")),
                "undecided": sum(1 for r in rows if score_mod.decision_of(r) is None),
                "cost_usd": round(sum(row_cost(r) for r in rows), 4)}

    with concurrent.futures.ThreadPoolExecutor(len(s.lines)) as pool:
        futures = {line: pool.submit(run_line, line) for line in s.lines}
        result = {line: f.result() for line, f in futures.items()}
    for line, r in result.items():
        log(f"run: {line} version {r['version']} on batch {k}: {r['n']} appeals, {r['errors']} errors, ${r['cost_usd']}")
    return result


def step_score(s: Settings, p: Paths, k: int, plan: dict) -> dict[str, Any]:
    truth = {c["id"]: c for c in all_cases()}
    cases = {i: truth[i] for j in range(1, k + 1) for i in plan[j]["ids"]}
    out = {}
    for line in s.lines:
        rows = [r for j in range(1, k + 1) for r in jl(p.runs / line / f"batch-{j}.jsonl")]
        results = score_mod.score(rows, cases)
        out[line] = dict(results)
        print(f"\n{line}\n{score_mod.table(results)}")
    return out


def step_reveal(s: Settings, p: Paths, k: int, plan: dict) -> dict[str, Any]:
    revealed = revealed_through(plan, k)
    write_view(p.revealed_view(k), set(revealed))
    return {"revealed": revealed, "new": plan[k]["revealed"], "view": str(p.revealed_view(k)), "at": now()}


def step_cohort(s: Settings, p: Paths, k: int, plan: dict) -> dict[str, Any]:
    if not s.pro_arm:
        return {"skipped": "no pro line in this run"}
    revealed = set(revealed_through(plan, k))
    sessions = {r["case_id"]: r.get("session_id") for j in range(1, k + 1)
                for r in jl(p.runs / "pro" / f"batch-{j}.jsonl") if r["case_id"] in revealed}
    missing = sorted(i for i in revealed if not sessions.get(i))
    if missing:
        raise RuntimeError(f"pro rows without a Kitaru session for revealed appeals {missing}")
    session_ids = sorted({str(v) for v in sessions.values() if v})
    reg, name = kitaru_registry(p), f"{s.pro_agent}-revealed"
    previous = reg.get("cohort_versions", [])
    existing = None if previous else kitaru_find(p, "cohort", "get", name)
    if existing is not None:
        # Another run (an earlier smoke test) made this cohort: replace its members with this run's sessions.
        latest = kitaru_list(p, "cohort", "version", "list", name)[-1] if existing.get("latest_version") else None
        old = [str(x["id"]) for x in kitaru_list(p, "session", "list", "--cohort", f"{name}@{latest['version']}")] if latest else []
        args = ["--baseline", str(latest["id"])] if latest else []
        args += repeat("--remove-session", old) + repeat("--add-session", session_ids)
        out = kitaru(p, "cohort", "version", "create", name, *args, "--display-version", f"round-{k}")
    elif not previous:
        sessions_file = p.round(k) / "cohort-sessions.txt"
        sessions_file.write_text("".join(f"{i}\n" for i in session_ids))
        out = kitaru(p, "cohort", "create", name, "--agent", s.pro_agent, "--sessions-file", str(sessions_file),
                     "--display-version", f"round-{k}", "--description",
                     "Sessions of revealed appeals (the true ruling is known), batches 1 to the current round")
    else:
        new = sorted(set(session_ids) - set(previous[-1]["sessions"]))
        out = kitaru(p, "cohort", "version", "create", name, "--baseline", previous[-1]["id"],
                     "--display-version", f"round-{k}", *repeat("--add-session", new))
    entry = {"round": k, "id": str(version_of(out)["id"]), "sessions": session_ids, "raw": out}
    reg["cohort"] = name
    reg["cohort_versions"] = [*previous, entry]
    write_json(p.line("pro") / "kitaru.json", reg)
    return {"cohort": name, "version_id": entry["id"], "sessions": len(entry["sessions"])}


def arm_access(s: Settings, p: Paths, arm: str, k: int) -> str:
    """The instruction's ARM-SPECIFIC line: what this arm can read and how its reruns run and are counted."""
    if arm == "codex":
        return ("The recorded runs are JSONL files in `/claims/runs/`, `batch-<k>.jsonl`, one row per appeal: the "
                "decision (`final`), the tool calls, the cost, and the full conversation (`transcript`, as PydanticAI "
                "messages). `claims-rerun` runs a copy of the agent on the revealed appeals and prints its decisions "
                "next to the rulings, with its balanced accuracy and the path of the new transcripts. "
                "`claims-rerun --help` shows the options; `--agent-dir` takes any copy of the package (the directory "
                "must be named `claims_agent`). Each `claims-rerun` call counts as one rerun.")
    reg = kitaru_registry(p)
    version = reg["versions"][current(p, "pro")["hash"]]
    evaluator = reg["evaluator"]
    return (f"The agent is registered in the Kitaru workspace you can reach as `{s.pro_agent}`, and its recorded runs "
            f"are sessions of that agent, one per appeal (the session input is `Review appeal <id>.`). The sessions of "
            f"the revealed appeals are in the cohort `{reg['cohort']}` (its latest version). The version in "
            f"`{TRIAL_AGENT_DIR}` as you received it is registered as `{s.pro_agent}@{version['number']}`, whose working "
            f"directory `{version['workdir']}` exists in this sandbox as a read-only copy of it. The evaluator "
            f"`{evaluator['name']}@{evaluator['version']}` is registered for the agent and scores a session 1 or 0 "
            f"against its revealed ruling. A Kitaru worker named `{trial_worker_name(s, k)}` is running in this sandbox: "
            f"it claims agent tasks of any agent version and evaluator tasks, and runs them with "
            f"`/opt/claims-venv/bin` (the agent's Python environment) first on PATH, `CLAIMS_WORK_DIR=/claims/data` "
            f"and the agent's model credentials. No other worker claims tasks of agent versions registered during "
            f"this round. Reruns on the revealed appeals are Kitaru experiment runs; each experiment run counts as one "
            f"rerun.")


def trial_worker_name(s: Settings, k: int) -> str:
    return f"claims-trial-{'mini-' if s.mini else ''}round-{k}"


def pro_round_image() -> str:
    return os.environ.get("PRO_ROUND_IMAGE") or "claims-over-time-round-pro:latest"


def image_user(image: str) -> str:
    """The user an image runs as (its USER), which is the trial's agent user."""
    out = subprocess.run(["docker", "image", "inspect", "-f", "{{.Config.User}}", image], capture_output=True, text=True,
                         env={**os.environ, "DOCKER_CONTEXT": os.environ.get("DOCKER_CONTEXT", "orbstack")}, check=False)
    if out.returncode != 0:
        raise SystemExit(f"cannot inspect the trial image {image}: {out.stderr.strip()} (build it with "
                         f"harbor/round_task/build_images.sh)")
    return out.stdout.strip() or "root"


def trial_image_and_user(arm: str) -> tuple[str, str]:
    return (CODEX_IMAGE, "root") if arm == "codex" else (pro_round_image(), image_user(pro_round_image()))


def build_task(s: Settings, p: Paths, k: int, arm: str, plan: dict) -> Path:
    task = p.round(k) / arm / "task"
    shutil.rmtree(task, ignore_errors=True)
    shutil.copytree(TASK_TEMPLATE, task)
    cur = current(p, arm)
    # The pro trial holds a read-only copy of the registered current version at its registered working directory,
    # so the worker in the trial can run it for the Pro agent's experiments.
    mirror = kitaru_registry(p)["versions"][cur["hash"]]["workdir"] if arm == "pro" else ""
    image, user = trial_image_and_user(arm)
    values = {"round": k, "arm": arm, "user": user, "base_image": image, "mirror_dir": mirror,
              "agent_timeout_sec": float(s.minutes * 60 + (300 if arm == "pro" else 0))}
    for name in ("task.toml", "environment/Dockerfile"):
        path = task / name
        path.write_text(string.Template(path.read_text()).substitute(values))
    ctx = task / "environment" / "claims"
    shutil.copytree(version_dir(p, arm, cur["version"]), ctx / "agent" / "claims_agent")
    if mirror:
        shutil.copytree(version_dir(p, arm, cur["version"]), ctx / "registered" / "claims_agent")
    (ctx / "data").mkdir(parents=True)
    # Only the appeals already decided: the improver sees no case file of a later batch.
    decided = {i for j in range(1, k + 1) for i in plan[j]["ids"]}
    rows = [r for r in jl(p.revealed_view(k) / "cases.jsonl") if r["id"] in decided]
    (ctx / "data" / "cases.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    revealed = set(revealed_through(plan, k))
    shown = {r["id"] for r in jl(ctx / "data" / "cases.jsonl") if "truth" in r}
    if shown != revealed:
        raise RuntimeError(f"the trial's cases.jsonl shows rulings for {sorted(shown ^ revealed)} by mistake")
    (ctx / "bin").mkdir()
    for tool in TRIAL_TOOLS_BY_ARM[arm]:
        shutil.copy(tool, ctx / "bin" / tool.name)
    if arm == "codex":
        (ctx / "runs").mkdir()
        for j in range(1, k + 1):
            rows = [{key: v for key, v in r.items() if key != "agent_dir"} for r in jl(p.runs / "codex" / f"batch-{j}.jsonl")]
            (ctx / "runs" / f"batch-{j}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))
    write_json(ctx / "round.json", {"round": k, "arm": arm, "rerun_budget": s.rerun_budget, "minutes": s.minutes,
                                    "current_version": cur["version"], "revealed": len(revealed)})
    text = INSTRUCTIONS.read_text().split("\n---\n", 1)[1].strip() + "\n"
    (task / "instruction.md").write_text(text.format(
        round=k, total_rounds=TOTAL_ROUNDS, batch_size=s.batch_size, current_version=cur["version"],
        agent_dir=TRIAL_AGENT_DIR, runs_total=sum(len(plan[j]["ids"]) for j in range(1, k + 1)),
        revealed_count=s.revealed_per_batch, revealed_total=len(revealed), cases_file=TRIAL_CASES,
        arm_access=arm_access(s, p, arm, k), rerun_budget=s.rerun_budget, minutes=s.minutes))
    return task


def trial_hosts(s: Settings, k: int, arm: str, extra: list[str]) -> list[str]:
    urls = [os.environ["KITARU_API_URL"]] if arm == "pro" else []
    preset = PRESETS[s.preset_for(k)]
    if preset["base_url_env"]:
        url = os.environ.get(preset["base_url_env"])
        if not url:
            raise SystemExit(f"set {preset['base_url_env']}: the claims agent's model endpoint for round {k}")
        urls.append(url)
    hosts = list(extra)
    for url in urls:
        host = urlparse(url).hostname
        if not host:
            raise SystemExit(f"no host name in {url!r}")
        hosts.append(host)
    return sorted(set(hosts))


def pro_agent_dir() -> Path | None:
    value = os.environ.get("PRO_AGENT_DIR")
    return Path(value).resolve() if value else None


def prepare_pro() -> Any:
    """Run the Pro agent bundle's `prepare` (it re-renders what the agent starts with, such as today's date); return
    its last output line, parsed as JSON when it is."""
    directory = pro_agent_dir()
    assert directory is not None
    out = subprocess.run([str(directory / "prepare")], capture_output=True, text=True, check=False)
    if out.returncode != 0:
        raise SystemExit(f"{directory / 'prepare'} failed ({out.returncode}): {out.stderr[-2000:]}")
    last = (out.stdout.strip().splitlines() or [""])[-1]
    try:
        return json.loads(last)
    except ValueError:
        return last


def step_improve(s: Settings, p: Paths, k: int, plan: dict, extra_hosts: list[str], concurrency: int) -> dict[str, Any]:
    prepared = prepare_pro() if s.pro_arm else None
    if s.preset_for(k) != s.preset_for(k + 1) and k + 1 <= TOTAL_ROUNDS:
        log(f"note: round {k}'s candidates are judged on preset {s.preset_for(k)}; batch {k + 1} runs on {s.preset_for(k + 1)}")
    import_path = [str(BENCH / "harbor"), *([str(pro_agent_dir())] if s.pro_arm else [])]
    env = {**os.environ, "PYTHONPATH": os.pathsep.join(import_path), "HARBOR_TELEMETRY": "off",
           "DOCKER_CONTEXT": os.environ.get("DOCKER_CONTEXT", "orbstack")}
    procs, info = {}, {}
    for arm in s.arms:
        task = build_task(s, p, k, arm, plan)
        jobs, job = p.round(k) / arm / "jobs", f"{'mini-' if s.mini else ''}round-{k}-{arm}"
        if (jobs / job).exists():
            (jobs / job).rename(jobs / f"{job}-abandoned-{int(time.time())}")
        cmd = ["harbor", "run", "-y", "-p", str(task), "-a", HARBOR_AGENTS[arm], "-m", f"openai/{s.improver_model}",
               "-e", "docker", "-o", str(jobs), "--job-name", job]
        for host in trial_hosts(s, k, arm, extra_hosts):
            cmd += ["--allow-agent-host", host]
        image, user = trial_image_and_user(arm)
        if arm == "pro":
            cmd += ["--ak", f"run_timeout_sec={s.minutes * 60}", "--ak", f"worker_name={trial_worker_name(s, k)}",
                    "--ak", f"trial_user={user}"]
        info[arm] = {"task": str(task), "job_dir": str(jobs / job), "hosts": trial_hosts(s, k, arm, extra_hosts),
                     "command": cmd, "image": image, "prepared": prepared if arm == "pro" else None}
    # No worker runs on this machine during the trials: the pro trial starts its own (pro_round_agent.py).
    started = now()
    for arm in s.arms:
        log(f"improve: starting the {arm} trial: {' '.join(info[arm]['command'][:12])} ...")
        out = (p.round(k) / arm / "harbor.log").open("w")
        procs[arm] = (subprocess.Popen(info[arm]["command"], env=env, stdout=out, stderr=subprocess.STDOUT), out)
    for arm, (proc, out) in procs.items():
        info[arm]["exit_code"] = proc.wait()
        out.close()
    finished = now()
    for arm in s.arms:
        trials = [d for d in Path(info[arm]["job_dir"]).iterdir() if (d / "verifier").is_dir()] \
            if Path(info[arm]["job_dir"]).exists() else []
        info[arm] |= {"started": started, "finished": finished, "trial_dir": str(trials[0]) if trials else None}
        log(f"improve: {arm} trial finished (harbor exit {info[arm]['exit_code']}): {info[arm]['trial_dir']}")
    return info


def changed_python_lines(old: Path, new: Path) -> list[str]:
    lines = []
    for path in sorted(new.rglob("*.py")):
        before = (old / path.relative_to(new)).read_text().splitlines() if (old / path.relative_to(new)).exists() else []
        lines += [f"{path.relative_to(new)}: {line.strip()}" for line in path.read_text().splitlines() if line not in before]
    return lines


def improver_usage(trial: Path, arm: str) -> dict[str, Any]:
    result = json.loads((trial / "result.json").read_text()) if (trial / "result.json").exists() else {}
    agent = result.get("agent_result") or {}
    usage = {"cost_usd": agent.get("cost_usd"), "input_tokens": agent.get("n_input_tokens"),
             "cache_tokens": agent.get("n_cache_tokens"), "output_tokens": agent.get("n_output_tokens"),
             "exception": (result.get("exception_info") or {}).get("exception_type")}
    if arm == "pro" and (trial / "agent" / "pro" / "summary.json").exists():
        summary = json.loads((trial / "agent" / "pro" / "summary.json").read_text())
        usage |= {"pro_usage": summary.get("usage"), "end": summary.get("end")}
    return usage


def improver_commands(trial: Path, arm: str) -> list[str]:
    """The commands the improver ran, from its own log: Codex's trajectory (every tool call's arguments), or the Pro
    agent's `commands.jsonl` (one shell command per line, written by its Harbor class)."""
    if arm == "codex":
        path = trial / "agent" / "trajectory.json"
        steps = json.loads(path.read_text()).get("steps", []) if path.exists() else []

        def strings(value: Any) -> list[str]:
            if isinstance(value, str):
                return [value]
            if isinstance(value, dict):
                return [x for v in value.values() for x in strings(v)]
            if isinstance(value, list):
                return [x for v in value for x in strings(v)]
            return []
        return ["\n".join(strings(call.get("arguments"))) for step in steps for call in step.get("tool_calls") or []]
    return [str(row.get("command", "")) for row in jl(trial / "agent" / "pro" / "commands.jsonl")]


def outside_runs(trial: Path, arm: str) -> dict[str, Any]:
    """Commands in the improver's log that run the claims agent outside the arm's counted rerun path."""
    commands = improver_commands(trial, arm)
    # Codex writes shell commands inside JavaScript string literals, so escaped newlines and tabs are unescaped first.
    hits = [c for c in commands
            if OUTSIDE_RUNS.search(REGISTERED_COMMAND.sub(" ", c.replace("\\n", "\n").replace("\\t", "\t")))]
    return {"commands_scanned": len(commands), "count": len(hits), "commands": [c[:400] for c in hits]}


def experiment_runs_in(p: Paths, started: str, finished: str) -> list[dict[str, Any]]:
    runs = kitaru_list(p, "experiment", "run", "list")
    return [r for r in runs if started <= str(r.get("created", "")) <= finished]


def step_approve(s: Settings, p: Paths, k: int, plan: dict, concurrency: int) -> dict[str, Any]:
    improve = done(p, k, "improve")
    revealed = revealed_through(plan, k)
    truth = {c["id"]: c["truth"] for c in all_cases()}
    out = {}
    for arm in s.arms:
        info, cur = improve[arm], current(p, arm)
        cur_dir = version_dir(p, arm, cur["version"])
        decision: dict[str, Any] = {"round": k, "arm": arm, "current_version": cur["version"], "current_hash": cur["hash"],
                                    "trial_dir": info.get("trial_dir"), "revealed_n": len(revealed), "shipped": False}
        trial = Path(info["trial_dir"]) if info.get("trial_dir") else None
        verifier = trial / "verifier" if trial else None
        check = json.loads((verifier / "check.json").read_text()) if verifier and (verifier / "check.json").exists() else {}
        decision["verifier"] = {k2: check.get(k2) for k2 in ("loadable", "change_md", "reward", "error")}
        if trial:
            decision["improver_usage"] = improver_usage(trial, arm)
        counted: dict[str, Any]
        if arm == "codex":
            reruns = [e for e in jl(verifier / "reruns.jsonl")] if verifier else []
            counted = {
                "claims_rerun": sum(1 for e in reruns if e.get("event") == "start"),
                "claims_rerun_cost_usd": round(sum(e.get("cost_usd") or 0 for e in reruns if e.get("event") == "finish"), 4)}
            counted["counted"] = counted["claims_rerun"]
        else:
            runs = experiment_runs_in(p, info["started"], info["finished"])
            counted = {"kitaru_experiment_runs": len(runs), "kitaru_experiment_run_ids": [str(r.get("id")) for r in runs],
                       "counted": len(runs)}
        # A run of the claims agent outside the counted path is a rerun the budget did not allow: all of it is over.
        outside: dict[str, Any] = outside_runs(trial, arm) if trial else {"count": 0, "commands": []}
        counted["outside_counted_path"] = outside
        counted["total"] = counted["counted"] + outside["count"]
        counted["over_budget"] = max(0, counted["counted"] - s.rerun_budget) + outside["count"]
        decision["reruns"] = counted
        candidate = p.line(arm) / "candidates" / f"round-{k}"
        shutil.rmtree(candidate, ignore_errors=True)
        tgz = verifier / "candidate.tgz" if verifier else None
        if not tgz or not tgz.exists():
            out[arm] = finish_decision(p, k, arm, decision, "no candidate came out of the trial")
            continue
        candidate.mkdir(parents=True)
        with tarfile.open(tgz) as tar:
            tar.extractall(candidate, filter="data")
        cand_dir = candidate / "claims_agent"
        change = cand_dir / "CHANGE.md"
        change_md = change.read_text() if change.exists() else None
        if change.exists():
            shutil.move(change, candidate / "CHANGE.md")
        for cache in cand_dir.rglob("__pycache__"):
            shutil.rmtree(cache)
        decision |= {"candidate_dir": str(cand_dir), "candidate_hash": tree_hash(cand_dir),
                     "change_md_head": (change_md or "")[:600]}
        flags = [line for line in changed_python_lines(cur_dir, cand_dir) if INTEGRITY.search(line)]
        decision["integrity_flags"] = flags
        if check.get("reward") != 1:
            out[arm] = finish_decision(p, k, arm, decision, "the verifier did not pass it (not loadable, or no CHANGE.md)")
        elif decision["candidate_hash"] == cur["hash"]:
            out[arm] = finish_decision(p, k, arm, decision, "no change to the agent")
        elif read_model(cand_dir) != read_model(cur_dir):
            out[arm] = finish_decision(p, k, arm, decision, f"it changes the model: {read_model(cand_dir)}")
        elif flags:
            out[arm] = finish_decision(p, k, arm, decision, "integrity flags in its Python changes; review them")
        else:
            scores: dict[str, dict[str, Any]] = {}
            balanced: dict[str, float] = {}
            for label, directory, h in (("current", cur_dir, cur["hash"]), ("candidate", cand_dir, decision["candidate_hash"])):
                cache = p.runs / "approval" / f"{h}.jsonl"
                before = {r["case_id"] for r in jl(cache)}
                rows = run_batch(cache, revealed, p.agent_view, agent_dir=directory, concurrency=concurrency)
                pairs = [(score_mod.decision_of(r), truth[r["case_id"]]) for r in rows]
                balanced[label] = float(score_mod.balanced(pairs))
                scores[label] = {"hash": h, "balanced_accuracy": score_mod.balanced(pairs),
                                 "accuracy": sum(d == t for d, t in pairs) / len(pairs),
                                 "undecided": sum(d is None for d, _ in pairs), "rows": str(cache),
                                 "new_runs": len(set(revealed) - before),
                                 "new_cost_usd": round(sum(row_cost(r) for r in rows if r["case_id"] not in before), 4)}
            decision["approval"] = scores
            ship = balanced["candidate"] >= balanced["current"]
            reason = (f"balanced accuracy on {len(revealed)} revealed appeals: candidate "
                      f"{scores['candidate']['balanced_accuracy']:.3f} vs current {scores['current']['balanced_accuracy']:.3f}")
            if ship:
                decision["shipped"] = True
                decision["new_version"] = add_version(p, arm, cand_dir, k, f"round {k} candidate, approved: {reason}",
                                                      change_md)["version"]
            out[arm] = finish_decision(p, k, arm, decision, ("shipped: " if ship else "not shipped: ") + reason)
    return out


def finish_decision(p: Paths, k: int, arm: str, decision: dict[str, Any], reason: str) -> dict[str, Any]:
    decision["reason"] = reason
    write_json(p.round(k) / f"decision-{arm}.json", decision)
    log(f"approve: {arm}: {reason}" + (f"; reruns over budget by {decision['reruns']['over_budget']}"
                                        if decision.get("reruns", {}).get("over_budget") else ""))
    return {key: decision.get(key) for key in ("shipped", "reason", "candidate_hash", "new_version", "reruns")}


async def workers_by_version(p: Paths, version_ids: list[str], since: str) -> dict[str, dict[str, int]]:
    """For each agent version, how many of its tasks created since `since` each worker (by name) claimed."""
    from kitaru.api_models.v1.task import TaskListParams
    from kitaru.client import KitaruAPIClient

    env, names = kitaru_env(p), {}
    out: dict[str, dict[str, int]] = {v: {} for v in version_ids}
    async with KitaruAPIClient(base_url=env["KITARU_API_URL"], api_key=env["KITARU_API_KEY"]) as client:
        cursor = None
        while True:
            page = await client.tasks.list(TaskListParams(size=1000, cursor=cursor, sort="created:desc"))
            for task in page.items:
                if task.created is not None and task.created.isoformat() < since:
                    return out
                version = str(task.agent_version_id)
                if version not in out:
                    continue
                if task.worker_id is None:
                    name = "(not claimed)"
                else:
                    if task.worker_id not in names:
                        names[task.worker_id] = (await client.workers.get(task.worker_id)).name
                    name = names[task.worker_id]
                out[version][name] = out[version].get(name, 0) + 1
            cursor = page.next_cursor
            if not cursor:
                return out


def step_audit(s: Settings, p: Paths, k: int, plan: dict) -> dict[str, Any]:
    """Check the workspace, for everything created since this run started: no evaluation of an appeal before it was
    revealed, no task of a version the round runner did not register claimed by a host worker, and what was
    registered by anyone else."""
    import asyncio

    if not s.pro_arm:
        return {"skipped": "no pro line in this run, so nothing ran in the Kitaru workspace"}
    since = json.loads((p.rounds / "settings.json").read_text())["created"]
    reveal_at: dict[str, str] = {}
    for j in range(1, k + 1):
        marker = done(p, j, "reveal")
        reveal_at |= {cid: marker["at"] for cid in marker["new"]}
    sessions = [x for x in kitaru_list(p, "session", "list", "--agent", s.pro_agent, "--include-payloads")
                if str(x.get("created")) >= since]
    appeal_of = {}
    for session in sessions:
        m = re.search(r"Review appeal (\S+?)\.?(?:\"|$)", json.dumps(session.get("inputs")))
        if m:
            appeal_of[str(session["id"])] = m.group(1)
    evaluations = [e for e in kitaru_list(p, "evaluation", "list") if str(e.get("created")) >= since]
    violations, outside = [], []
    for e in evaluations:
        sid = str(e.get("session_id"))
        if sid not in appeal_of:
            outside.append({"evaluation": str(e.get("id")), "session_id": sid})
            continue
        cid, created = appeal_of[sid], str(e.get("created"))
        if cid not in reveal_at or created < reveal_at[cid]:
            violations.append({"evaluation": str(e.get("id")), "appeal": cid, "created": created,
                               "score": e.get("score"), "revealed_at": reveal_at.get(cid)})
    reg = kitaru_registry(p)
    ours = {v["id"] for v in reg["versions"].values()}
    versions = [v for v in kitaru_list(p, "agent", "version", "list", s.pro_agent) if str(v.get("created")) >= since]
    foreign = [str(v["id"]) for v in versions if str(v["id"]) not in ours]
    evaluators = [x.get("name") for x in kitaru_list(p, "evaluator", "list") if str(x.get("created")) >= since
                  and not str(x.get("name", "")).startswith("kitaru/") and x.get("name") != reg.get("evaluator", {}).get("name")]
    workers = asyncio.run(workers_by_version(p, [str(v["id"]) for v in versions], since))
    host_ran_foreign = {v: w for v, w in workers.items() if v in foreign and any(n.startswith("claims-host-") for n in w)}
    replays = [x for x in sessions if x.get("origin") != "recorded"]
    report = {"since": since, "sessions": len(sessions), "evaluations": len(evaluations),
              "evaluations_with_score": sum(1 for e in evaluations if e.get("score") is not None),
              "non_recorded_sessions": len(replays),
              "non_recorded_sessions_cost_usd": round(sum(float(x.get("cost") or 0) for x in replays), 4),
              "violations": violations, "evaluations_outside_the_agent": outside,
              "agent_versions_registered_by_round_py": sorted(ours & {str(v["id"]) for v in versions}),
              "agent_versions_registered_by_others": foreign, "evaluators_registered_by_others": evaluators,
              "workers_by_agent_version": workers, "host_workers_on_other_versions": host_ran_foreign}
    if violations or host_ran_foreign:
        log(f"AUDIT FAILED: {len(violations)} evaluation(s) of unrevealed appeals, {len(host_ran_foreign)} version(s) "
            f"not registered by round.py ran on a host worker; see audit.json")
    else:
        log(f"audit: {len(evaluations)} evaluations since the run started, all of revealed appeals; "
            f"{len(foreign)} agent versions registered by others, none run by a host worker")
    return report


# ---------------------------------------------------------------- main

def parse_rounds(value: str) -> list[int]:
    lo, _, hi = value.partition("-")
    return list(range(int(lo), int(hi or lo) + 1))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--frontier-preset", required=True, choices=sorted(PRESETS), help="the model before the switch")
    ap.add_argument("--open-preset", default="open", choices=sorted(PRESETS), help="the model from --switch-round on")
    ap.add_argument("--switch-round", type=int, default=4, help="the first batch every line runs on the open model")
    ap.add_argument("--improver-model", default="gpt-6-luna", help="OpenAI model for both improvers")
    ap.add_argument("--rerun-budget", type=int, default=3)
    ap.add_argument("--minutes", type=int, default=45, help="each improver's time limit")
    ap.add_argument("--pro-agent", help="Kitaru agent name of the pro line (default claims-agent, or claims-agent-smoke "
                                        "with --mini)")
    ap.add_argument("--rounds", default="1-8", help="rounds to run, for example 1-8 or 3")
    ap.add_argument("--stop-after", choices=STEPS, help="stop each round after this step (it resumes on the next call)")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--allow-host", action="append", default=[], help="another host both trials may reach")
    ap.add_argument("--mini", action="store_true", help="smoke test: round 1 only, 10 appeals of batch 1, 4 revealed; "
                                                         "state in work/rounds/mini and work/runs/mini")
    a = ap.parse_args()

    load_dotenv(WORK / ".env")
    pro_dir = pro_agent_dir()
    if pro_dir is None:
        log("PRO_AGENT_DIR is not set: this run has the left_alone and codex lines only. The pro line needs the ZenML "
            "Pro agent bundle, which is not public (see harbor/round_task/README.md).")
    elif not (pro_dir / "pro_agent" / "agent.py").exists() or not os.access(pro_dir / "prepare", os.X_OK):
        raise SystemExit(f"PRO_AGENT_DIR={pro_dir} has no pro_agent/agent.py or no executable prepare")
    s = Settings(frontier_preset=a.frontier_preset, open_preset=a.open_preset, switch_round=a.switch_round,
                 improver_model=a.improver_model, rerun_budget=a.rerun_budget, minutes=a.minutes, mini=a.mini,
                 pro_agent=a.pro_agent or ("claims-agent-smoke" if a.mini else "claims-agent"),
                 pro_arm=pro_dir is not None)
    p = Paths(rounds=WORK / "rounds" / ("mini" if a.mini else ""), runs=WORK / "runs" / ("mini" if a.mini else ""))
    p = Paths(rounds=p.rounds.resolve(), runs=p.runs.resolve())
    rounds = [1] if a.mini else parse_rounds(a.rounds)
    plan = make_plan(s)
    init_lines(s, p)

    steps: dict[str, Callable[[int], dict[str, Any]]] = {
        "switch": lambda k: step_switch(s, p, k, plan),
        "run": lambda k: step_run(s, p, k, plan, a.concurrency),
        "score": lambda k: step_score(s, p, k, plan),
        "reveal": lambda k: step_reveal(s, p, k, plan),
        "cohort": lambda k: step_cohort(s, p, k, plan),
        "improve": lambda k: step_improve(s, p, k, plan, a.allow_host, a.concurrency),
        "approve": lambda k: step_approve(s, p, k, plan, a.concurrency),
        "audit": lambda k: step_audit(s, p, k, plan),
    }
    for k in rounds:
        if k > 1 and not (p.round(k - 1) / "audit.json").exists():
            raise SystemExit(f"round {k - 1} is not finished; run it first")
        for step in STEPS:
            marker = p.round(k) / f"{step}.json"
            if step == "switch" and k != s.switch_round:
                continue
            if marker.exists():
                log(f"round {k}: {step} already done")
            else:
                log(f"round {k}: {step}")
                started = now()
                write_json(marker, {"step": step, "round": k, "started": started, "finished": None,
                                    "result": steps[step](k)} | {"finished": now()})
            if step == a.stop_after:
                break
        else:
            continue
        break


if __name__ == "__main__":
    main()
