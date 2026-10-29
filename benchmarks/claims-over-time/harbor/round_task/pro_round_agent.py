"""The pro improver arm's Harbor agent: the ZenML Pro agent's own Harbor class, plus a Kitaru worker in the trial.

    harbor run ... -a round_task.pro_round_agent:ProRoundAgent -m openai/gpt-6-luna   (PYTHONPATH=harbor:$PRO_AGENT_DIR)

The ZenML Pro agent is not public. Its Harbor class, `pro_agent.agent:ProAgent`, comes from the directory in
`PRO_AGENT_DIR`, which `round.py` puts on Harbor's import path. Everything about the agent's turn is that class's.
This class adds, before the turn, a Kitaru worker (`/opt/claims-venv/bin/kitaru worker start --claim agent --claim
evaluator`), running as the trial's agent user with the claims agent's Python environment first on PATH,
`CLAIMS_WORK_DIR=/claims/data` (rulings of revealed appeals only) and the claims agent's model credentials in its
environment, so the agent's experiments, on any version it registers, run here and nowhere else. After the turn it
stops the worker, whose log lands in `<trial>/agent/kitaru-worker/worker.log`.

Extra job kwargs: `trial_user` (the trial's agent user, required), `model_env` (comma-separated names of the host
variables the claims agent needs, default `OPENAI_API_KEY,CLAIMS_AGENT_BASE_URL,CLAIMS_AGENT_API_KEY`), `worker_name`
(default `claims-trial-worker`), `worker_concurrency` (default 4).
"""

import os
import shlex
from typing import Any

from harbor.environments.base import BaseEnvironment
from harbor.models.agent.context import AgentContext
from pro_agent.agent import ProAgent

from round_task.rerun_env import DEFAULT_NAMES, parse_names

WORKER_LOGS = "/logs/agent/kitaru-worker"


class ProRoundAgent(ProAgent):
    """One ZenML Pro agent turn on a round task, with a Kitaru worker in the trial."""

    def __init__(self, *args: Any, trial_user: str = "", model_env: str = DEFAULT_NAMES,
                 worker_name: str = "claims-trial-worker", worker_concurrency: int = 4, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        if not trial_user:
            raise ValueError("ProRoundAgent needs the trial's agent user (--ak trial_user=<name>)")
        self._trial_user = trial_user
        self._model_env_names = parse_names(model_env)
        self._worker_name = worker_name
        self._worker_concurrency = int(worker_concurrency)

    async def _start_worker(self, environment: BaseEnvironment) -> None:
        url, key = self._get_env("KITARU_API_URL"), self._get_env("KITARU_PRO_API_KEY")
        if not (url and key):
            raise ValueError("the trial's Kitaru worker needs KITARU_API_URL and KITARU_PRO_API_KEY on the host")
        user = shlex.quote(self._trial_user)
        await self.exec_as_root(environment, f"mkdir -p {WORKER_LOGS} && chown {user}: {WORKER_LOGS}")
        # The model credentials travel in the environment of this one exec, never through a file in the trial.
        model_env = {n: os.environ[n] for n in self._model_env_names if os.environ.get(n)}
        command = (
            "export PATH=/opt/claims-venv/bin:$PATH CLAIMS_WORK_DIR=/claims/data KITARU_CONFIG_DIR=/tmp/kitaru-worker "
            "KITARU_NON_INTERACTIVE=1 KITARU_DISABLE_CLIENT_ANALYTICS=1 && cd /claims && "
            f"setsid nohup kitaru worker start --claim agent --claim evaluator --concurrency {self._worker_concurrency} "
            f"--name {shlex.quote(self._worker_name)} > {WORKER_LOGS}/worker.log 2>&1 < /dev/null & "
            f"sleep 8; pgrep -f {shlex.quote(f'[k]itaru worker start .*--name {self._worker_name}')} >/dev/null"
        )
        result = await environment.exec(command, user=self._trial_user,
                                        env={**model_env, "KITARU_API_URL": url, "KITARU_API_KEY": key}, timeout_sec=60)
        if result.return_code != 0:
            log = await environment.exec(f"tail -40 {WORKER_LOGS}/worker.log", user=self._trial_user)
            raise RuntimeError(f"the trial's Kitaru worker did not start:\n{log.stdout}")

    async def _stop_worker(self, environment: BaseEnvironment) -> None:
        # SIGTERM makes the worker drain held tasks and deregister (a background process ignores SIGINT); it is found
        # by its unique name.
        pattern = shlex.quote(f"[k]itaru worker start .*--name {self._worker_name}")
        result = await environment.exec(
            f"pkill -TERM -f {pattern} || exit 0; for i in $(seq 60); do pgrep -f {pattern} >/dev/null || exit 0; sleep 1; done; "
            f"pkill -KILL -f {pattern}; exit 0", user=self._trial_user, timeout_sec=90)
        if result.return_code != 0:
            raise RuntimeError(f"could not stop the trial's Kitaru worker: {result.stdout} {result.stderr}")

    async def run(self, instruction: str, environment: BaseEnvironment, context: AgentContext) -> None:
        await self._start_worker(environment)
        try:
            await super().run(instruction, environment, context)
        finally:
            await self._stop_worker(environment)
