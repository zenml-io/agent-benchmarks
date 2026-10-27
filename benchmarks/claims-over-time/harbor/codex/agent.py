"""The Codex improver arm's Harbor agent: Harbor's built-in `codex` agent, plus the rerun tool's model credentials.

    harbor run ... -a codex.agent:CodexRoundAgent -m openai/gpt-6-luna   (PYTHONPATH=harbor)

The trial image (`build_image.sh`) already has the Codex CLI, so Harbor's install step finds it and downloads nothing;
the trial has no network while it is set up. Everything about the Codex run is Harbor's; this class only adds
`/claims/secrets/rerun.env` after the install, the model credentials `claims-rerun` reads (see `round_task/rerun_env.py`).
Extra job kwarg: `rerun_env`, comma-separated names of the host variables to pass (default
`OPENAI_API_KEY,CLAIMS_AGENT_BASE_URL,CLAIMS_AGENT_API_KEY`).
"""

from typing import Any

from harbor.agents.installed.codex import Codex
from harbor.environments.base import BaseEnvironment
from round_task.rerun_env import DEFAULT_NAMES, parse_names, upload_rerun_env


class CodexRoundAgent(Codex):
    """One `codex exec` run on a round task, with the rerun tool's credentials in the trial."""

    def __init__(self, *args: Any, rerun_env: str = DEFAULT_NAMES, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self._rerun_env_names = parse_names(rerun_env)

    async def install(self, environment: BaseEnvironment) -> None:
        await super().install(environment)
        await upload_rerun_env(self, environment, "root", self._rerun_env_names)
