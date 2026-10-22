"""KYC document checks for business account onboarding at a fictional bank (Larkhaven Bank)."""
from __future__ import annotations

import os
from functools import lru_cache

from harness.core import Environment, State

from .data import SCREEN_FLOOR, build_all, name_score

HERE = os.path.dirname(os.path.abspath(__file__))

HIDDEN_RULES = {
    "registry_director_mismatch": "Escalate (REGISTRY_MISMATCH) when the company registry's directors differ from the "
                                  "directors on the application (an undeclared director, or a declared director the "
                                  "registry does not list); never approve or just request documents.",
    "volume_out_of_line": "Escalate (ACTIVITY_VOLUME_MISMATCH) when the declared expected monthly volume is wildly out "
                          "of line with the business's size: a year of expected volume is more than 10x the last filed "
                          "annual turnover; never approve or just request documents.",
    "id_expiring_soon": "Do not approve when an identity document of a person to verify expires within 30 days after "
                        "the review date; request a new one instead (NEW_ID:<party_id>).",
}

WRITE_TOOLS = {"approve_application", "request_more_info", "escalate_to_compliance", "reject_application"}
READ_TOOLS = {"get_application", "get_documents", "check_registry", "screen_names", "get_country_risk"}


def _fn(name, desc, props, required):
    return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
        "type": "object", "properties": props, "required": required}}}


APP = {"application_id": {"type": "string", "description": "Application ID, e.g. APP-40123"}}
CODES = {"type": "array", "items": {"type": "string"}}
SCHEMAS = [
    _fn("get_application", "Get a business account application: business, registration number, country, declared "
        "activity, expected monthly volume, parties (directors, shareholders, declared indirect owners), ownership "
        "and the list of submitted documents.", APP, ["application_id"]),
    _fn("get_documents", "Get the extracted content of one or more submitted documents (identity documents, registry "
        "extract, proof of address).", {"document_ids": {"type": "array", "items": {"type": "string"}}}, ["document_ids"]),
    _fn("check_registry", "Look up a company in the live company registry by registration number: status, directors, "
        "shareholders, employees and last filed annual turnover.",
        {"registration_number": {"type": "string"}}, ["registration_number"]),
    _fn("screen_names", "Screen natural persons' names against the sanctions and PEP watchlists. Returns possible "
        "matches per name with a similarity score (0-100) and the listed person's date of birth.",
        {"names": {"type": "array", "items": {"type": "string"}}}, ["names"]),
    _fn("get_country_risk", "Get the bank's risk rating for a country.", {"country": {"type": "string"}}, ["country"]),
    _fn("approve_application", "Approve the application with a risk tier.",
        {**APP, "risk_tier": {"type": "string", "enum": ["low", "medium", "high"]}}, ["application_id", "risk_tier"]),
    _fn("request_more_info", "Ask the applicant for missing or replacement items, as item codes.",
        {**APP, "items": CODES}, ["application_id", "items"]),
    _fn("escalate_to_compliance", "Escalate the application to the compliance team with reason codes.",
        {**APP, "reason_codes": CODES, "note": {"type": "string"}}, ["application_id", "reason_codes"]),
    _fn("reject_application", "Reject the application with one reason code.",
        {**APP, "reason_code": {"type": "string"}, "note": {"type": "string"}}, ["application_id", "reason_code"]),
]


def _norm_code(c) -> str:
    return "".join(str(c).split()).upper()


def _codes(v) -> list[str]:
    if isinstance(v, str):
        v = [x for x in v.replace(";", ",").split(",") if x.strip()]
    return sorted({_norm_code(x) for x in (v or [])})


@lru_cache(maxsize=1)
def _tasks():
    return build_all()


class KycChecks(Environment):
    name = "kyc_checks"
    description = ("KYC (know-your-customer) document checks on business account applications at Larkhaven Bank, a "
                   "fictional bank")

    def tasks(self):
        return [{k: v for k, v in t.items() if k != "data"} for t in _tasks()]

    def _task_data(self, task):
        return next(t["data"] for t in _tasks() if t["id"] == task["id"])

    def policy(self):
        with open(os.path.join(HERE, "policy.md")) as f:
            return f.read()

    def hidden_rules(self):
        return dict(HIDDEN_RULES)

    def tool_schemas(self):
        return SCHEMAS

    def read_tools(self):
        return set(READ_TOOLS)

    def write_tools(self):
        return set(WRITE_TOOLS)

    def initial_data(self, task):
        return self._task_data(task)

    # ---- tools
    def handle(self, state: State, name: str, args: dict):
        d = state.data
        app = d["application"]
        if name == "get_application":
            if str(args.get("application_id", "")).strip().upper() != app["application_id"]:
                return {"error": "application not found"}
            return app
        if name == "get_documents":
            ids = args.get("document_ids") or []
            if isinstance(ids, str):
                ids = [ids]
            return [d["documents"].get(str(i).strip().upper(), {"document_id": i, "error": "document not found"})
                    for i in ids[:20]]
        if name == "check_registry":
            reg = str(args.get("registration_number", "")).strip().upper()
            return d["registry"].get(reg, {"error": f"no registry record for {reg}"})
        if name == "screen_names":
            names = args.get("names") or []
            if isinstance(names, str):
                names = [names]
            out = []
            for n in names[:10]:
                hits = []
                for w in d["watchlist"]:
                    s = name_score(str(n), w["name"])
                    if s >= SCREEN_FLOOR:
                        hits.append({"entry_id": w["entry_id"], "listed_name": w["name"], "list": w["list"],
                                     "date_of_birth": w["date_of_birth"], "country": w["country"], "score": s})
                hits.sort(key=lambda h: -h["score"])
                out.append({"query": n, "possible_matches": hits[:5]})
            return out
        if name == "get_country_risk":
            c = str(args.get("country", "")).strip()
            for k, v in d["country_risk"].items():
                if k.lower() == c.lower():
                    return {"country": k, "risk": v}
            return {"error": f"unknown country {c}"}
        # writes
        if str(args.get("application_id", "")).strip().upper() != app["application_id"]:
            return {"error": "application not found"}
        status = {"approve_application": "approved", "request_more_info": "info_requested",
                  "escalate_to_compliance": "escalated", "reject_application": "rejected"}[name]
        app["status"] = status
        return {"ok": True, "application_id": app["application_id"], "status": status}

    # ---- grading
    def grade(self, state: State) -> dict:
        gold = state.task["gold"]
        cond = gold["conditions"]
        writes = state.writes
        breaks = set()
        for w in writes:
            t = w["tool"]
            if t in ("approve_application", "request_more_info"):
                if cond["registry_director_mismatch"]:
                    breaks.add("registry_director_mismatch")
                if cond["volume_out_of_line"]:
                    breaks.add("volume_out_of_line")
            if t == "approve_application" and cond["id_expiring_soon"]:
                breaks.add("id_expiring_soon")
        details = {"gold": {k: v for k, v in gold.items() if k != "conditions"}, "n_writes": len(writes)}
        ok = False
        if len(writes) == 1:
            w = writes[0]
            a = w["args"]
            same_app = str(a.get("application_id", "")).strip().upper() == gold["application_id"]
            if w["tool"] != gold["action"]:
                details["error"] = f"wrong action {w['tool']}"
            elif not same_app:
                details["error"] = "wrong application_id"
            elif gold["action"] == "approve_application":
                ok = str(a.get("risk_tier", "")).strip().lower() == gold["risk_tier"]
                details["got"] = a.get("risk_tier")
            elif gold["action"] == "reject_application":
                ok = _norm_code(a.get("reason_code", "")) == gold["codes"][0]
                details["got"] = a.get("reason_code")
            else:
                got = _codes(a.get("items") if gold["action"] == "request_more_info" else a.get("reason_codes"))
                ok = got == sorted(gold["codes"])
                details["got"] = got
        else:
            details["error"] = "no decision recorded" if not writes else "more than one decision recorded"
        return {"success": bool(ok), "rule_breaks": sorted(breaks), "details": details}


ENV = KycChecks()
