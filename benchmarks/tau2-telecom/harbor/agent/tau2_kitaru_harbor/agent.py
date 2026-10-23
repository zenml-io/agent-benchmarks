"""Harbor agent that runs the tau2 Telecom PydanticAI agent (wrapped in Kitaru) inside the trial.

Job config:

    agents:
      - import_path: tau2_kitaru_harbor.agent:Tau2KitaruAgent
        model_name: openai:gpt-5.2-2025-12-11
        kwargs: {arm: baseline}

Harbor must be able to import this module: run Harbor with `PYTHONPATH=harbor/agent` from the benchmark
folder. Only this file runs on the host; `runner.py`, `kitaru_sink.py`, `harness/replay/model_router.py`
and `harness/replay/prompt_addendum.txt` are uploaded into the trial's main container and run there in
their own virtualenv (PydanticAI, Kitaru and the PydanticAI adapter at the original run's versions).

Outputs per trial, under `<trial>/agent/`: `tau2-kitaru-agent.json` (summary: arm, model, tokens, agent
cost, termination, tools called), `tau2-kitaru-agent.txt` (runner output) and `kitaru/` (the Kitaru
recording: `requests.jsonl`, `session.json`). The sidecar's conversation log `tau3_runtime_state.json`
(what the verifier grades) lands in the same folder.
"""

import json
import re
import shlex
import tempfile
import tomllib
from pathlib import Path
from typing import Any

from harbor.agents.capabilities import AgentCapabilities
from harbor.agents.installed.base import BaseInstalledAgent
from harbor.agents.options import InstalledAgentOptions
from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from pydantic import Field

HERE = Path(__file__).resolve().parent
BENCHMARK = HERE.parents[2]  # benchmarks/tau2-telecom
KITARU_GIT = "git+https://github.com/zenml-io/kitaru@0217140c9bd6fc1b0569abefbaea30be20a6fde4"
REQUIREMENTS = [
    "pydantic-ai-slim[openai,mcp]==2.51.0",
    f"kitaru @ {KITARU_GIT}",
    f"kitaru-pydantic-ai @ {KITARU_GIT}#subdirectory=plugins/packages/pydantic-ai",
]
# The MCP client stack is new relative to the original run (which needed no MCP); pinned to the versions tested.
EXTRA_CONSTRAINTS = ["fastmcp-slim==4.1.3", "mcp==2.3.0", "mcp-types==2.3.0"]
VENV = "/opt/tau2-kitaru-agent"
SRC = "/opt/tau2-kitaru-agent-src"
PASSTHROUGH_ENV = ("OPENAI_API_KEY", "OPENAI_COMPAT_BASE_URL_PROVIDER_A", "OPENAI_COMPAT_API_KEY_PROVIDER_A")


class Tau2KitaruAgentOptions(InstalledAgentOptions):
    """Options for one arm. Arms differ only in model_name and these fields."""

    arm: str = Field(default="", description="Condition label, recorded in the summary and the Kitaru session name.")
    prompt_rule: bool = Field(default=False, description="Append harness/replay/prompt_addendum.txt to the instructions.")
    dry_run: bool = Field(
        default=False,
        description="Install, connect and record without a model or the simulated user (scores 0; free).",
    )


class Tau2KitaruAgent(BaseInstalledAgent):
    """The original run's PydanticAI agent, served tau2's tools and user by the task's MCP sidecar."""

    options_model = Tau2KitaruAgentOptions
    capabilities = AgentCapabilities(mcp_servers=True)

    @staticmethod
    def name() -> str:
        return "tau2-kitaru-agent"

    def version(self) -> str | None:
        return "1.0"

    @property
    def _options(self) -> Tau2KitaruAgentOptions:
        assert isinstance(self.options, Tau2KitaruAgentOptions)
        return self.options

    async def install(self, environment: BaseEnvironment) -> None:
        pyproject = tomllib.loads((BENCHMARK / "pyproject.toml").read_text())
        constraints = [*pyproject["tool"]["uv"]["constraint-dependencies"], *EXTRA_CONSTRAINTS]
        await self.exec_as_root(environment, f"mkdir -p {SRC}")
        with tempfile.TemporaryDirectory() as tmp_s:
            tmp = Path(tmp_s)
            (tmp / "constraints.txt").write_text("\n".join(constraints) + "\n")
            files = {
                "constraints.txt": tmp / "constraints.txt",
                "runner.py": HERE / "runner.py",
                "kitaru_sink.py": HERE / "kitaru_sink.py",
                "model_router.py": BENCHMARK / "harness" / "replay" / "model_router.py",
                "prompt_addendum.txt": BENCHMARK / "harness" / "replay" / "prompt_addendum.txt",
            }
            for name, source in files.items():
                await environment.upload_file(source, f"{SRC}/{name}")
        requirements = " ".join(shlex.quote(r) for r in REQUIREMENTS)
        await self.exec_as_root(
            environment,
            f"python3 -m venv {VENV} && {VENV}/bin/pip install --no-cache-dir -q "
            f"-c {SRC}/constraints.txt {requirements} && chmod -R a+rX {VENV} {SRC}",
            timeout_sec=900,
        )

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        if not self.model_name and not self._options.dry_run:
            raise ValueError("tau2-kitaru-agent needs a model (-m / model_name), or dry_run: true")
        servers = [s for s in self.mcp_servers if s.name == "tau3-runtime" and s.url]
        if len(servers) != 1:
            raise ValueError("the task must declare the tau3-runtime MCP server (streamable-http)")

        local_instruction = self.logs_dir / "instruction.md"
        local_instruction.write_text(instruction)
        await environment.upload_file(local_instruction, f"{SRC}/instruction.md")

        logs = str(self.environment_logs_dir)
        args = [
            f"{VENV}/bin/python", f"{SRC}/runner.py",
            "--mcp-url", servers[0].url,
            "--model", self.model_name or "dry-run",
            "--instruction-file", f"{SRC}/instruction.md",
            "--case", self._case(),
            "--arm", self._options.arm,
            "--record-dir", f"{logs}/kitaru",
            "--summary", f"{logs}/tau2-kitaru-agent.json",
        ]
        if self._options.prompt_rule:
            args += ["--addendum-file", f"{SRC}/prompt_addendum.txt"]
        if self._options.dry_run:
            args.append("--dry-run")
        env = {key: value for key in PASSTHROUGH_ENV if (value := self._get_env(key))}
        command = " ".join(shlex.quote(a) for a in args)
        await self.exec_as_agent(environment, f"cd {SRC} && {command} 2>&1 | tee {logs}/tau2-kitaru-agent.txt",
                                 env=env)

    def _case(self) -> str:
        """The original run's case number, from the trial name (tasks are named telecom-test-NN)."""
        match = re.search(r"telecom-test-(\d+)", self.session_id or "")
        return str(int(match.group(1))) if match else ""

    def populate_context_post_run(self, context: AgentContext) -> None:
        path = self.logs_dir / "tau2-kitaru-agent.json"
        if not path.exists():
            return
        summary: dict[str, Any] = json.loads(path.read_text())
        context.n_input_tokens = summary.get("input_tokens")
        context.n_output_tokens = summary.get("output_tokens")
        context.n_cache_tokens = summary.get("cache_read_tokens")
        context.cost_usd = summary.get("agent_cost_usd")
        context.metadata = {k: summary.get(k) for k in ("arm", "model", "case", "run_error", "runtime", "dry_run")}
