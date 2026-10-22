"""Harbor agent that runs the benchmark's own copilot loop (harness/run.py) against a task's MCP server.

  import_path: underwriting_agent.agent:UnderwritingCopilot   (run Harbor from benchmarks/underwriting/harbor with
                                                               PYTHONPATH=. so the package imports)
  model_name:  a model key from src/models_client/models.py, e.g. haiku-5.5, gpt-6-luna, glm-5.3-flash@provider-a
  kwargs:      prompt_file (system prompt; default: the first prompt, run.SYSTEM), effort (low|medium|high)

It uploads harness/run.py, llm.py, judge.py (imported by run.py), src/models_client and the runner into the main
container and runs it there; the runner calls the model APIs directly with keys from the host environment
(EVAL_ANTHROPIC_API_KEY, OPENAI_API_KEY, OPENAI_COMPAT_BASE_URL_*/OPENAI_COMPAT_API_KEY_*).
"""
import json
import re
import shlex
import shutil
import tempfile
from pathlib import Path

from pydantic import Field

from harbor.agents.capabilities import AgentCapabilities
from harbor.agents.installed.base import BaseInstalledAgent
from harbor.agents.options import InstalledAgentOptions

HERE = Path(__file__).resolve().parent
BENCH = HERE.parents[1]  # benchmarks/underwriting
REMOTE = "/installed-agent/uw"
SUMMARY = "uw-copilot.json"
KEY_VARS = ("EVAL_ANTHROPIC_API_KEY", "OPENAI_API_KEY")
REQUEST_RE = re.compile(r"<request>\s*(.*?)\s*</request>", re.S)


class UnderwritingCopilotOptions(InstalledAgentOptions):
    prompt_file: str | None = Field(
        default=None, description="System prompt file (host path). Default: the first prompt (harness/run.py SYSTEM).")
    effort: str | None = Field(default=None, description="Effort / reasoning effort for the agent's calls.")


def extract_request(instruction):
    """The underwriter's opening message, which the instruction carries between <request> tags."""
    m = REQUEST_RE.search(instruction)
    if not m:
        raise ValueError("instruction has no <request> block")
    return m.group(1)


def stage_files(dest):
    """Copy the files the runner needs into dest, in the repository's layout."""
    (dest / "harness").mkdir(parents=True)
    for f in ("run.py", "llm.py", "judge.py"):
        shutil.copy(BENCH / "harness" / f, dest / "harness" / f)
    shutil.copytree(BENCH / "src" / "models_client", dest / "src" / "models_client",
                    ignore=shutil.ignore_patterns("__pycache__"))
    for f in ("copilot.py", "mcp_client.py"):
        shutil.copy(HERE / f, dest / f)


class UnderwritingCopilot(BaseInstalledAgent):
    options_model = UnderwritingCopilotOptions
    capabilities = AgentCapabilities(mcp_servers=True)

    @staticmethod
    def name():
        return "underwriting-copilot"

    def version(self):
        return "0.1.0"

    def get_version_command(self):
        return None

    async def install(self, environment):
        with tempfile.TemporaryDirectory() as tmp:
            stage = Path(tmp) / "uw"
            stage_files(stage)
            await environment.upload_dir(stage, REMOTE)

    def _server_url(self):
        servers = [s for s in self.mcp_servers if s.name == "underwriting"]
        if len(servers) != 1 or not servers[0].url:
            raise ValueError("the task must declare one MCP server named 'underwriting' with a URL")
        return servers[0].url

    async def run(self, instruction, environment, context):
        if not self.model_name:
            raise ValueError("set -m <model key>")
        opts = self.options
        files = {"request.txt": extract_request(instruction)}
        if opts.prompt_file:
            files["system.txt"] = Path(opts.prompt_file).read_text()
        for name, text in files.items():
            local = self.logs_dir / f"uw-{name}"
            local.write_text(text)
            await environment.upload_file(local, f"{REMOTE}/{name}")
        cmd = ["python3", f"{REMOTE}/copilot.py", "--model", self.model_name, "--url", self._server_url(),
               "--request-file", f"{REMOTE}/request.txt", "--out", f"{self.environment_logs_dir}/{SUMMARY}"]
        if opts.prompt_file:
            cmd += ["--prompt-file", f"{REMOTE}/system.txt"]
        if opts.effort:
            cmd += ["--effort", opts.effort]
        env = {k: v for k in KEY_VARS if (v := self._get_env(k))}
        env.update(self._get_env_prefixed_full("OPENAI_COMPAT_"))
        await self.exec_as_agent(environment, command=" ".join(shlex.quote(c) for c in cmd), env=env)

    def _get_env_prefixed_full(self, prefix):
        return {prefix + k: v for k, v in self._get_env_prefixed(prefix).items()}

    def populate_context_post_run(self, context):
        path = self.logs_dir / SUMMARY
        if not path.exists():
            return
        row = json.loads(path.read_text())
        context.n_input_tokens = row.get("input")
        context.n_cache_tokens = row.get("cached")
        context.n_output_tokens = row.get("output")
        context.cost_usd = row.get("cost")
        context.metadata = {k: row.get(k) for k in ("status", "failures", "calls", "tool_calls",
                                                     "underwriter_turns", "reasoning", "errors")}
