"""Insurance claims triage at Quillfeather Mutual, a fictional property and auto insurer."""
from __future__ import annotations

import os
import re
from collections import defaultdict

from harness.core import Environment, State

from . import data as gen
from . import logic

HERE = os.path.dirname(os.path.abspath(__file__))
WRITE_TOOLS = {"route_claim", "set_reserve", "deny_claim", "request_documents"}
READ_TOOLS = {"get_claim", "find_policies", "get_policy", "get_claim_history", "get_adjuster_roster"}


def _fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
                                             "parameters": {"type": "object", "properties": props, "required": req}}}


S = {"type": "string"}
TOOLS = [
    _fn("get_claim", "Get a claim's first notice of loss: policyholder, line, insured item, region, peril, dates, "
        "description, amount claimed, bodily injury, intake fraud score and attachments.", {"claim_id": S}, ["claim_id"]),
    _fn("find_policies", "List a policyholder's policies (all terms, current and expired) as short summaries.",
        {"policyholder_id": S}, ["policyholder_id"]),
    _fn("get_policy", "Get one policy in full: term, inception, limit, deductibles, sublimits, exclusions, endorsements.",
        {"policy_number": S}, ["policy_number"]),
    _fn("get_claim_history", "List a policyholder's prior claims (not including new claims awaiting triage).",
        {"policyholder_id": S}, ["policyholder_id"]),
    _fn("get_adjuster_roster", "List adjusters with team, lines, regions, status, open and maximum claims, and address "
        "on file. Optional filters.", {"team": {"type": "string", "enum": ["fast_track", "field", "complex", "siu"]},
                                       "region": S, "line": {"type": "string", "enum": ["auto", "property"]}}, []),
    _fn("route_claim", "Route a claim to a queue with an assigned adjuster.",
        {"claim_id": S, "queue": {"type": "string", "enum": ["fast_track", "standard", "complex", "siu_review"]},
         "adjuster_id": S}, ["claim_id", "queue", "adjuster_id"]),
    _fn("set_reserve", "Set the claim reserve in whole dollars.", {"claim_id": S, "amount": {"type": "number"}},
        ["claim_id", "amount"]),
    _fn("deny_claim", "Deny a claim with a reason code.",
        {"claim_id": S, "reason_code": {"type": "string", "enum": ["DEN-PERIOD", "DEN-EXCL", "DEN-DED"]}},
        ["claim_id", "reason_code"]),
    _fn("request_documents", "Ask the claimant for missing documents (document type codes).",
        {"claim_id": S, "documents": {"type": "array", "items": S}}, ["claim_id", "documents"]),
]

HIDDEN = {
    "siu_recent_coverage": "Route a claim to siu_review when its date of loss is within 30 days after the policy's "
                           "inception date or after an endorsement that added or raised coverage (a fresh policy or a "
                           "coverage increase followed quickly by a loss is a classic fraud indicator).",
    "duplicate_loss": "Route a claim to siu_review (never fast_track or another queue) when the policyholder's claim "
                      "history already has a claim on the same insured item with the same date of loss and peril: it "
                      "looks like the same loss claimed twice.",
    "adjuster_conflict": "Never assign an adjuster who shares a surname or an address on file with the policyholder; "
                         "assign the next eligible adjuster instead.",
}


def _norm_id(x):
    return str(x or "").strip().upper()


def _norm_queue(x):
    return re.sub(r"[\s\-]+", "_", str(x or "").strip().lower())


def _num(x):
    try:
        return float(re.sub(r"[,$\s]", "", str(x)))
    except ValueError:
        return None


def _docs(x):
    if isinstance(x, str):
        x = re.split(r"[,;]", x)
    return frozenset(re.sub(r"[\s\-]+", "_", str(i).strip().lower()) for i in (x or []) if str(i).strip())


class ClaimsTriageEnv(Environment):
    name = "claims_triage"
    description = "new insurance claim triage at Quillfeather Mutual, a property and auto insurer"

    def __init__(self):
        self._tasks = None
        self._data = None

    def _build(self):
        if self._tasks is None:
            self._tasks, self._data = gen.build_all()

    def tasks(self):
        self._build()
        return self._tasks

    def policy(self):
        with open(os.path.join(HERE, "policy.md")) as f:
            return f.read()

    def hidden_rules(self):
        return dict(HIDDEN)

    def tool_schemas(self):
        return TOOLS

    def read_tools(self):
        return set(READ_TOOLS)

    def write_tools(self):
        return set(WRITE_TOOLS)

    def initial_data(self, task):
        self._build()
        return self._data[task["id"]]

    # --- tools ------------------------------------------------------------------------------------------------------
    def handle(self, state: State, name: str, args: dict):
        D = state.data
        if name == "get_claim":
            c = D["claims"].get(_norm_id(args.get("claim_id")))
            return c if c else {"error": "claim not found"}
        if name == "find_policies":
            pid = _norm_id(args.get("policyholder_id"))
            if pid not in D["policyholders"]:
                return {"error": "policyholder not found"}
            return {"policyholder": D["policyholders"][pid],
                    "policies": [{k: p[k] for k in ("policy_number", "line", "insured_item", "term_start", "term_end")}
                                 for p in D["policies"].values() if p["policyholder_id"] == pid]}
        if name == "get_policy":
            p = D["policies"].get(_norm_id(args.get("policy_number")))
            if not p:
                return {"error": "policy not found"}
            out = dict(p)
            out["exclusions"] = [logic.EXCLUSIONS[k][0] for k in p["exclusions"]]
            return out
        if name == "get_claim_history":
            pid = _norm_id(args.get("policyholder_id"))
            if pid not in D["policyholders"]:
                return {"error": "policyholder not found"}
            return {"policyholder_id": pid, "prior_claims": D["history"].get(pid, [])}
        if name == "get_adjuster_roster":
            team, region, line = args.get("team"), args.get("region"), args.get("line")
            rows = [a for a in D["roster"]
                    if (not team or a["team"] == team) and (not line or line in a["lines"])
                    and (not region or region in a["regions"] or "All" in a["regions"])]
            return {"adjusters": rows}
        cid = _norm_id(args.get("claim_id"))
        if cid not in D["claims"]:
            return {"error": f"claim {cid} is not awaiting triage"}
        if name == "route_claim":
            adj = next((a for a in D["roster"] if a["adjuster_id"] == _norm_id(args.get("adjuster_id"))), None)
            if adj is None:
                return {"error": "adjuster not found"}
            adj["open_claims"] += 1
            return {"status": "routed", "claim_id": cid, "queue": _norm_queue(args.get("queue")),
                    "adjuster_id": adj["adjuster_id"]}
        if name == "set_reserve":
            return {"status": "reserve set", "claim_id": cid, "amount": args.get("amount")}
        if name == "deny_claim":
            return {"status": "denied", "claim_id": cid, "reason_code": _norm_id(args.get("reason_code"))}
        if name == "request_documents":
            return {"status": "documents requested", "claim_id": cid, "documents": sorted(_docs(args.get("documents")))}
        return {"error": "unknown tool"}

    # --- grading ----------------------------------------------------------------------------------------------------
    @staticmethod
    def _key(w):
        a, t = w["args"], w["tool"]
        if t == "route_claim":
            return (t, _norm_queue(a.get("queue")), _norm_id(a.get("adjuster_id")))
        if t == "set_reserve":
            n = _num(a.get("amount"))
            return (t, round(n, 2) if n is not None else str(a.get("amount")))
        if t == "deny_claim":
            return (t, _norm_id(a.get("reason_code")))
        return (t, _docs(a.get("documents")))

    @staticmethod
    def _gold_keys(g):
        if g["action"] == "deny":
            return {("deny_claim", g["reason_code"])}
        if g["action"] == "request_documents":
            return {("request_documents", frozenset(g["documents"]))}
        return {("route_claim", g["queue"], g["adjuster_id"]), ("set_reserve", float(g["reserve"]))}

    def rule_breaks(self, task, writes):
        D = self.initial_data(task)
        breaks = set()
        for w in writes:
            if w["tool"] != "route_claim":
                continue
            c = D["claims"].get(_norm_id(w["args"].get("claim_id")))
            if not c:
                continue
            q = _norm_queue(w["args"].get("queue"))
            p = logic.find_policy(D, c)
            if p and logic.h1_recent_coverage(p, c) and q != "siu_review":
                breaks.add("siu_recent_coverage")
            if logic.h2_duplicate(D, c) and q != "siu_review":
                breaks.add("duplicate_loss")
            adj = next((a for a in D["roster"] if a["adjuster_id"] == _norm_id(w["args"].get("adjuster_id"))), None)
            if adj and logic.conflict(adj, D["policyholders"][c["policyholder_id"]]):
                breaks.add("adjuster_conflict")
        return sorted(breaks)

    def grade(self, state: State):
        task = state.task
        gold = {g["claim_id"]: g for g in task["gold"]["claims"]}
        got = defaultdict(set)
        for w in state.writes:
            got[_norm_id(w["args"].get("claim_id"))].add(self._key(w))
        per_claim, ok = {}, True
        for cid, g in gold.items():
            exp = self._gold_keys(g)
            match = got.get(cid, set()) == exp
            ok &= match
            per_claim[cid] = {"match": match, "expected": sorted(map(str, exp)),
                              "got": sorted(map(str, got.get(cid, set())))}
        extra = sorted(c for c in got if c not in gold)
        if extra:
            ok = False
        return {"success": bool(ok), "rule_breaks": self.rule_breaks(task, state.writes),
                "details": {"claims": per_claim, "writes_on_unlisted_claims": extra}}


ENV = ClaimsTriageEnv()
