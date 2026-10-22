"""Serve a generated (trace-inferred) tool mock behind the hand-written domain's exact tool interface.

The agent sees the same tool names, signatures and docstrings as with the hand-written tools; only the
backend changes. Grading hashes the mock's own `state()` (a conversation passes if its final state equals the
state after the scenario's gold actions, both on the generated mock).

  SWAPBENCH_GENMOCK=<mock.py> SWAPBENCH_GENMOCK_DOMAIN=fintech|retail  scripts/tau2x run -d fintech_gen ...

A generated mock is a file defining `class Mock(data: dict)`, one method per tool, and `state() -> dict`.
`data` is the domain's data snapshot (db.json without internal state).
"""
import functools
import importlib.util
import json
import os

from tau2.environment.toolkit import TOOL_ATTR
from tau2.utils import get_dict_hash


def load_mock_class(path):
    spec = importlib.util.spec_from_file_location("swapbench_genmock_impl", path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.Mock


def snapshot(domain):
    """The data handed to the generated mock: the scenario world's db.json without internal state."""
    if domain == "fintech":
        from swapbench.fintech.domain import data_dir
        data = json.load(open(os.path.join(data_dir(), "db.json")))
        data.pop("events", None)
        data.pop("session", None)
        return data
    from tau2.domains.retail.utils import RETAIL_DB_PATH
    return json.load(open(RETAIL_DB_PATH))


def _base(domain):
    if domain == "fintech":
        from swapbench.fintech import domain as d
        return d.FintechTools, d
    from tau2.domains.retail import environment as d
    from tau2.domains.retail.tools import RetailTools
    return RetailTools, d


def make_toolkit_class(domain, mock_path):
    Base, _ = _base(domain)
    Mock = load_mock_class(mock_path)
    attrs = {}
    for name, fn in Base.__dict__.items():
        if not getattr(fn, TOOL_ATTR, False):
            continue

        def make(name, fn):
            @functools.wraps(fn)
            def tool(self, *args, **kwargs):
                return getattr(self._mock, name)(*args, **kwargs)
            return tool
        attrs[name] = make(name, fn)

    def __init__(self, db=None):
        Base.__init__(self, db)
        self._mock = Mock(snapshot(domain))

    def get_db_hash(self):
        return get_dict_hash(json.loads(json.dumps(self._mock.state(), default=str)))

    attrs.update(__init__=__init__, get_db_hash=get_db_hash)
    return type(f"Generated{Base.__name__}", (Base,), attrs)


def register(domain, mock_path):
    from tau2.environment.environment import Environment
    from tau2.registry import registry
    _, mod = _base(domain)
    Tools = make_toolkit_class(domain, mock_path)

    def get_environment(db=None, solo_mode=False):
        env = mod.get_environment()  # same policy, same (unused) db as the hand-written domain
        return Environment(domain_name=f"{domain}_gen", policy=env.policy, tools=Tools(env.tools.db))

    get_tasks, get_split = mod.get_tasks, mod.get_tasks_split
    if f"{domain}_gen" not in registry.get_domains():
        registry.register_domain(get_environment, f"{domain}_gen")
        registry.register_tasks(get_tasks, f"{domain}_gen", get_task_splits=get_split)
