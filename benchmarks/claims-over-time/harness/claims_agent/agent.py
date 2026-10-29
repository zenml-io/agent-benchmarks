"""The claims-review agent: a PydanticAI port of decision-agents' claims agent (base condition).

Everything an improver is likely to change lives in plain files next to this one: prompt.md (system
prompt), tools.json (tool names, descriptions and argument schemas, and the final answer schema),
config.toml (model, model settings, request limit). Case data comes from $CLAIMS_WORK_DIR, never from
this directory, so every copy of the package reads the same cases and precedents.
"""

import json
import os
import tomllib
from collections import defaultdict
from pathlib import Path
from typing import Any

from pydantic_ai import Agent, ModelRetry, StructuredDict, TextOutput, Tool, ToolOutput
from pydantic_ai.models import Model
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

HERE = Path(__file__).resolve().parent
FINAL_TOOL = "submit_determination"


def load_config() -> dict[str, Any]:
    return tomllib.loads((HERE / "config.toml").read_text())


def work_dir() -> Path:
    value = os.environ.get("CLAIMS_WORK_DIR")
    if not value:
        raise SystemExit("set CLAIMS_WORK_DIR to the directory holding cases.jsonl and precedents.jsonl")
    return Path(value)


def jl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.open() if line.strip()]


class Env:
    """The case database and precedent library behind the read tools (decision-agents' Env, base condition)."""

    def __init__(self, work: Path) -> None:
        self.cases = {c["id"]: c for c in jl(work / "cases.jsonl")}
        self.prec = {p["id"]: p for p in jl(work / "precedents.jsonl")}
        self.by_t: dict[str, list[dict[str, Any]]] = defaultdict(list)
        for p in sorted(self.prec.values(), key=lambda p: (p["year"], p["id"]), reverse=True):
            self.by_t[p["treatment"].lower()].append(p)

    def call(self, case_id: str, name: str, a: dict[str, Any]) -> dict[str, Any]:
        # The case tools ignore the case_id argument and always answer for the appeal under review, as the original did.
        c = self.cases[case_id]
        if name == "get_case":
            return {"case_id": case_id, "request": c["case_file"].get("request"), "review_type": c["type"],
                    "diagnosis_category": c["diagnosis_category"], "diagnosis": c["diagnosis"],
                    "treatment_category": c["treatment_category"], "treatment": c["treatment"],
                    "age_range": c["age"], "gender": c["gender"]}
        if name == "get_medical_records":
            cf = c["case_file"]
            return {"condition": cf.get("condition"), "history": cf.get("history"), "prior_treatments": cf.get("prior_treatments")}
        if name == "search_precedents":
            t = str(a.get("treatment", "")).lower().strip()
            hits = self.by_t.get(t) or [p for k, v in self.by_t.items() if t and (t in k or k in t) for p in v]
            if a.get("diagnosis"):
                dd = str(a["diagnosis"]).lower()
                narrowed = [p for p in hits if dd in p["diagnosis"].lower() or p["diagnosis"].lower() in dd]
                hits = narrowed or hits
            if a.get("decision") in ("uphold", "overturn"):
                hits = [p for p in hits if p["decision"] == a["decision"]]
            res = [{"precedent_id": p["id"], "year": p["year"], "decision": p["decision"], "diagnosis": p["diagnosis"],
                    "summary": p["text"][:350]} for p in hits[:5]]
            return {"total_matches": len(hits), "results": res}
        if name == "get_precedent":
            p = self.prec.get(str(a.get("precedent_id")))
            if not p:
                return {"error": "not found"}
            return {k: p[k] for k in ("id", "year", "decision", "type", "diagnosis", "treatment", "text")}
        return {"error": f"unknown tool {name}"}


def build_model(config: dict[str, Any]) -> Model | str:
    env_name = config.get("base_url_env")
    if not env_name:
        return config["model"]
    url = os.environ.get(env_name, "").rstrip("/")
    if not url:
        raise SystemExit(f"set {env_name} to the base URL of the OpenAI-compatible server serving {config['model']!r}")
    provider = OpenAIProvider(base_url=url if url.endswith("/v1") else url + "/v1",
                              api_key=os.environ.get("CLAIMS_AGENT_API_KEY", "EMPTY"))
    # Match the original request: `max_tokens` (not `max_completion_tokens`), and only each reply's content
    # sent back, never the server's separate reasoning text.
    return OpenAIChatModel(config["model"], provider=provider,
                           profile=lambda p: {**p, "openai_chat_send_back_thinking_parts": False,
                                              "openai_chat_supports_max_completion_tokens": False})


def build_agent(env: Env, case_id: str, seen: set[str], config: dict[str, Any]) -> Agent[None, dict[str, Any]]:
    """One appeal's agent: the read tools answer for `case_id` and add every precedent id they return to `seen`."""
    specs = {t["function"]["name"]: t["function"] for t in json.loads((HERE / "tools.json").read_text())}
    final = specs.pop(FINAL_TOOL)
    limit = config["tool_result_chars"]

    def read_tool(name: str, spec: dict[str, Any]) -> Tool[None]:
        def call(**args: Any) -> str:
            out = env.call(case_id, name, args)
            seen.update(str(x["precedent_id"]) for x in out.get("results", []) if isinstance(x, dict) and x.get("precedent_id"))
            if name == "get_precedent" and out.get("id"):
                seen.add(out["id"])
            return json.dumps(out)[:limit]

        tool = Tool.from_schema(call, name=name, description=spec["description"], json_schema=spec["parameters"])
        tool.strict = False
        return tool

    def nudge(text: str) -> dict[str, Any]:
        raise ModelRetry(config["nudge"])

    # Allowing text output keeps tool_choice at "auto" as in the original; a text answer is sent back with the nudge.
    # strict=False everywhere sends the schemas from tools.json unchanged (PydanticAI would otherwise add
    # OpenAI strict mode to the schemas that allow it, which the original never asked for).
    output = [ToolOutput(StructuredDict(final["parameters"]), name=FINAL_TOOL, description=final["description"], strict=False),
              TextOutput(nudge)]
    return Agent(build_model(config), system_prompt=(HERE / "prompt.md").read_text().strip(),
                 tools=[read_tool(n, s) for n, s in specs.items()], output_type=output,
                 model_settings=config.get("model_settings"), retries=config["request_limit"])
