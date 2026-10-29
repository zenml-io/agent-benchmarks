"""Give the in-trial rerun tool (`claims-rerun`) the claims agent's model credentials.

The Codex arm's agent calls this from its `install`: it writes `/claims/secrets/rerun.env`, one `NAME=value` line
per variable that is set on the host, readable only by the agent's user. (The pro arm has no `claims-rerun`; its
in-trial Kitaru worker gets the same variables in its own environment, see `pro_round_agent.py`.) The values travel in the environment of one `docker exec`, never through a file on the host, so they do not
land in the trial's log folder. Coding agents usually hide variables named like keys from the commands they run,
which is why the tool reads a file instead of its environment.
"""

import os
import re
import shlex

from harbor.agents.installed.base import BaseInstalledAgent
from harbor.environments.base import BaseEnvironment

RERUN_ENV_FILE = "/claims/secrets/rerun.env"
DEFAULT_NAMES = "OPENAI_API_KEY,CLAIMS_AGENT_BASE_URL,CLAIMS_AGENT_API_KEY"


def parse_names(value: str) -> list[str]:
    names = [n.strip() for n in value.split(",") if n.strip()]
    bad = [n for n in names if not re.fullmatch(r"[A-Z_][A-Z0-9_]*", n)]
    if bad:
        raise ValueError(f"not environment variable names: {bad}")
    return names


async def upload_rerun_env(agent: BaseInstalledAgent, environment: BaseEnvironment, user: str, names: list[str]) -> list[str]:
    """Write the host's values of `names` into the trial's rerun env file; return the names that were set."""
    values = {n: os.environ[n] for n in names if os.environ.get(n)}
    pattern = "|".join(values) or "^$"
    owner = shlex.quote(user)
    await agent.exec_as_root(
        environment,
        f"mkdir -p /claims/secrets && umask 077 && env | grep -E '^({pattern})=' > {RERUN_ENV_FILE}; "
        f"chown -R {owner}: /claims/secrets && chmod 700 /claims/secrets && chmod 600 {RERUN_ENV_FILE}",
        env=values,
    )
    return sorted(values)
