"""Reference triage logic: the written policy plus the hidden prudence rules. Used to build gold and to grade."""
from __future__ import annotations

import copy
from datetime import date
from decimal import ROUND_HALF_UP, Decimal

LAE = {"fast_track": Decimal("0.05"), "standard": Decimal("0.10"), "complex": Decimal("0.15"),
       "siu_review": Decimal("0.15")}
TEAM_FOR_QUEUE = {"fast_track": "fast_track", "standard": "field", "complex": "complex", "siu_review": "siu"}
INCREASE_CODES = {"LIM-UP", "WB-1", "EQ-3", "RS-2"}   # endorsements that add or raise coverage

# Exclusion library: key -> (text shown to the agent, peril or vehicle_use it excludes, lifting endorsement or None)
EXCLUSIONS = {
    "flood": ("Flood: surface water, rising rivers or lakes, storm surge, or overflow of any body of water (peril code "
              "flood). Water that escapes from a burst pipe inside the dwelling is not flood.", ("peril", "flood"), None),
    "earthquake": ("Earth movement, including earthquake and landslide (peril code earthquake), unless endorsement "
                   "EQ-3 is attached.", ("peril", "earthquake"), "EQ-3"),
    "wear": ("Wear and tear, rust, gradual deterioration or long-term seepage (peril code wear_and_tear).",
             ("peril", "wear_and_tear"), None),
    "sewer": ("Water that backs up through sewers or drains (peril code sewer_backup), unless endorsement WB-1 is "
              "attached.", ("peril", "sewer_backup"), "WB-1"),
    "mold": ("Mold or fungus of any kind (peril code mold).", ("peril", "mold"), None),
    "mechanical": ("Mechanical or electrical breakdown (peril code mechanical).", ("peril", "mechanical"), None),
    "commercial": ("Any loss while the vehicle is used to carry passengers or goods for a fee, such as ride-hail or "
                   "delivery (vehicle_use rideshare or delivery), unless endorsement RS-2 is attached.",
                   ("use", ("rideshare", "delivery")), "RS-2"),
}
PROPERTY_EXCLUSIONS = ["flood", "earthquake", "wear", "sewer", "mold"]
AUTO_EXCLUSIONS = ["mechanical", "commercial"]


def d(s: str) -> date:
    return date.fromisoformat(s)


def surname(name: str) -> str:
    return name.strip().split()[-1].lower()


def find_policy(data, claim):
    loss = d(claim["date_of_loss"])
    for p in data["policies"].values():
        if (p["policyholder_id"] == claim["policyholder_id"] and p["line"] == claim["line"]
                and p["insured_item"] == claim["insured_item"] and d(p["term_start"]) <= loss < d(p["term_end"])):
            return p
    return None


def endorsement_on(p, code, loss):
    return any(e["code"] == code and d(e["effective_date"]) <= loss for e in p["endorsements"])


def is_excluded(p, claim):
    loss = d(claim["date_of_loss"])
    for key in p["exclusions"]:
        _, (kind, val), unless = EXCLUSIONS[key]
        hit = claim["peril"] == val if kind == "peril" else claim.get("vehicle_use") in val
        if hit and not (unless and endorsement_on(p, unless, loss)):
            return True
    return False


def deductible(p, claim):
    if p["line"] == "property" and p.get("wind_hail_deductible_pct") and claim["peril"] in ("wind", "hail"):
        return p["limit"] * p["wind_hail_deductible_pct"] // 100
    return p["deductible"]


def applicable_limit(p, claim):
    return p.get("sublimits", {}).get(claim["peril"], p["limit"])


def required_docs(claim):
    req = {"photos"}
    if claim["peril"] in ("theft", "vandalism") or claim["bodily_injury"]:
        req.add("police_report")
    if claim["line"] == "auto" and claim["peril"] != "theft":
        req.add("repair_estimate")
    if claim["line"] == "property" and claim["amount_claimed"] > 10000:
        req.add("contractor_estimate")
    if claim["peril"] == "fire":
        req.add("fire_report")
    if claim["bodily_injury"]:
        req.add("medical_records")
    return req


def missing_docs(claim):
    got = {a["type"] for a in claim["attachments"] if a["status"] == "received"}
    return sorted(required_docs(claim) - got)


# --- hidden-rule conditions ------------------------------------------------------------------------------------------
def h1_recent_coverage(p, claim):
    """Loss within 30 days after inception or after an endorsement that added or raised coverage."""
    loss = d(claim["date_of_loss"])
    starts = [d(p["inception_date"])] + [d(e["effective_date"]) for e in p["endorsements"] if e["code"] in INCREASE_CODES]
    return any(0 <= (loss - s).days <= 30 for s in starts)


def h2_duplicate(data, claim):
    return any(h["insured_item"] == claim["insured_item"] and h["date_of_loss"] == claim["date_of_loss"]
               and h["peril"] == claim["peril"] for h in data["history"].get(claim["policyholder_id"], []))


def conflict(adj, holder):
    return surname(adj["name"]) == surname(holder["name"]) or adj["address_on_file"] == holder["mailing_address"]


# --- triage ----------------------------------------------------------------------------------------------------------
ALL_RULES = frozenset({"siu_recent_coverage", "duplicate_loss", "adjuster_conflict"})


def _active(hidden):
    """hidden: True (all hidden rules), False (written policy only) or a set of hidden-rule ids to apply."""
    return ALL_RULES if hidden is True else (frozenset() if not hidden else frozenset(hidden))


def outcome(data, cid, hidden=True):
    """Decision for one claim, without the adjuster. Returns a dict with action and, for routes, queue/net/reserve."""
    act = _active(hidden)
    c = data["claims"][cid]
    p = find_policy(data, c)
    if p is None:
        return {"action": "deny", "reason_code": "DEN-PERIOD"}
    if is_excluded(p, c):
        return {"action": "deny", "reason_code": "DEN-EXCL"}
    ded = deductible(p, c)
    if c["amount_claimed"] <= ded:
        return {"action": "deny", "reason_code": "DEN-DED"}
    miss = missing_docs(c)
    if miss:
        return {"action": "request_documents", "documents": miss}
    net = min(c["amount_claimed"], applicable_limit(p, c)) - ded
    flags = {"h1": h1_recent_coverage(p, c), "h2": h2_duplicate(data, c)}
    if (c["fraud_score"] >= 70 or (flags["h1"] and "siu_recent_coverage" in act)
            or (flags["h2"] and "duplicate_loss" in act)):
        q = "siu_review"
    elif net > 25000 or c["bodily_injury"]:
        q = "complex"
    elif net <= 5000 and c["peril"] != "fire":
        q = "fast_track"
    else:
        q = "standard"
    reserve = int((Decimal(net) * (1 + LAE[q])).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {"action": "route", "queue": q, "net": net, "reserve": reserve, "flags": flags}


def eligible(adj, queue, claim):
    if adj["team"] != TEAM_FOR_QUEUE[queue] or adj["status"] != "active" or adj["open_claims"] >= adj["max_open_claims"]:
        return False
    if queue != "siu_review" and claim["line"] not in adj["lines"]:
        return False
    if queue != "fast_track" and claim["region"] not in adj["regions"]:
        return False
    return True


def ranked(roster, queue, claim):
    return sorted((a for a in roster if eligible(a, queue, claim)), key=lambda a: (a["open_claims"], a["adjuster_id"]))


def solve(data, claim_ids, hidden=True):
    """Full expected decisions for the claims in order (adjuster loads update as claims are assigned)."""
    data = copy.deepcopy(data)
    out = []
    for cid in claim_ids:
        o = outcome(data, cid, hidden)
        o["claim_id"] = cid
        if o["action"] == "route":
            c = data["claims"][cid]
            holder = data["policyholders"][c["policyholder_id"]]
            cands = ranked(data["roster"], o["queue"], c)
            o["h3"] = bool(cands) and conflict(cands[0], holder)
            if "adjuster_conflict" in _active(hidden):
                cands = [a for a in cands if not conflict(a, holder)]
            if not cands:
                raise ValueError(f"no eligible adjuster for {cid}")
            o["adjuster_id"] = cands[0]["adjuster_id"]
            cands[0]["open_claims"] += 1
        out.append(o)
    return out
