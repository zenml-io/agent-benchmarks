"""Task generation and reference solver for the IT access-request environment.

Everything is synthetic and built from a fixed seed. The gold for each task comes from `solve()`, which applies the
written policy plus the hidden prudence rules to the task's data; `solve(..., hidden=False)` applies the written policy
only, and the hidden rules that change the outcome are the task's `triggers`.
"""
from __future__ import annotations

import datetime as dt
import random

SEED = 20261019
LEVELS = {"read": 1, "write": 2, "admin": 3}
H_CONTRACT = "contractor_end_date"
H_SELF = "conflicted_approval"
H_READ = "read_only_need"
H_DEPART = "departing_employee"

# resource_id, name, system, tier, roles [(role, level, replaced_by or None)], home departments
RESOURCES = {
    "RES-201": ("Billing Database (production)", "PostgreSQL", "T3",
                [("billing-prod-ro", "read", None), ("billing-prod-rw", "write", None),
                 ("billing-prod-admin", "admin", None), ("billing-prod-readonly", "read", "billing-prod-ro")],
                ["Finance", "Engineering"]),
    "RES-202": ("Billing Database (staging)", "PostgreSQL", "T2",
                [("billing-stg-ro", "read", None), ("billing-stg-rw", "write", None), ("billing-stg-admin", "admin", None)],
                ["Finance", "Engineering"]),
    "RES-310": ("Finance Shared Drive", "File share", "T2",
                [("fin-drive-viewer", "read", None), ("fin-drive-editor", "write", None),
                 ("fin-drive-owner", "admin", None), ("fin-drive-viewers", "read", "fin-drive-viewer")],
                ["Finance"]),
    "RES-311": ("Finance Shared Drive Archive", "File share", "T1",
                [("fin-archive-viewer", "read", None), ("fin-archive-editor", "write", None)], ["Finance"]),
    "RES-420": ("Pipeline CRM", "CRM", "T2",
                [("crm-read", "read", None), ("crm-sales-rep", "write", None), ("crm-admin", "admin", None)],
                ["Sales", "Marketing"]),
    "RES-421": ("Pipeline CRM Sandbox", "CRM", "T1",
                [("crm-sbx-read", "read", None), ("crm-sbx-write", "write", None), ("crm-sbx-admin", "admin", None)],
                ["Sales"]),
    "RES-530": ("Production Cluster Console", "Container platform", "T3",
                [("prod-cluster-viewer", "read", None), ("prod-cluster-deployer", "write", None),
                 ("prod-cluster-admin", "admin", None)], ["Engineering"]),
    "RES-531": ("Staging Cluster Console", "Container platform", "T1",
                [("stg-cluster-viewer", "read", None), ("stg-cluster-deployer", "write", None),
                 ("stg-cluster-admin", "admin", None)], ["Engineering"]),
    "RES-640": ("People Records System", "HR system", "T3",
                [("people-records-viewer", "read", None), ("people-records-editor", "write", None),
                 ("people-records-admin", "admin", None), ("people-record-viewer", "read", "people-records-viewer")],
                ["People"]),
    "RES-750": ("Analytics Warehouse", "Data warehouse", "T2",
                [("wh-analyst-read", "read", None), ("wh-analyst-write", "write", None), ("wh-admin", "admin", None),
                 ("wh-analyst-ro", "read", "wh-analyst-read")], ["Data", "Finance", "Marketing"]),
    "RES-751": ("Analytics Warehouse Sandbox", "Data warehouse", "T1",
                [("wh-sbx-read", "read", None), ("wh-sbx-write", "write", None), ("wh-sbx-admin", "admin", None)],
                ["Data"]),
    "RES-860": ("Engineering Wiki", "Wiki", "T1",
                [("wiki-reader", "read", None), ("wiki-editor", "write", None), ("wiki-admin", "admin", None)],
                ["Engineering", "Data"]),
    "RES-870": ("Support Ticket Console", "Helpdesk", "T1",
                [("support-viewer", "read", None), ("support-agent", "write", None), ("support-admin", "admin", None)],
                ["Support"]),
    "RES-880": ("Contracts Drive", "File share", "T2",
                [("contracts-viewer", "read", None), ("contracts-editor", "write", None),
                 ("contracts-admin", "admin", None)], ["Legal", "Sales"]),
    "RES-890": ("Identity Admin Console", "Identity provider", "T3",
                [("idp-auditor", "read", None), ("idp-helpdesk", "write", None), ("idp-superadmin", "admin", None)],
                ["Engineering", "Support"]),
    "RES-960": ("Payroll Portal", "Payroll", "T3",
                [("payroll-viewer", "read", None), ("payroll-editor", "write", None), ("payroll-admin", "admin", None)],
                ["People", "Finance"]),
    "RES-970": ("Marketing Assets Drive", "File share", "T1",
                [("mkt-assets-viewer", "read", None), ("mkt-assets-editor", "write", None),
                 ("mkt-assets-admin", "admin", None)], ["Marketing"]),
}
SIBLING = {"RES-201": "RES-202", "RES-202": "RES-201", "RES-310": "RES-311", "RES-311": "RES-310",
           "RES-420": "RES-421", "RES-421": "RES-420", "RES-530": "RES-531", "RES-531": "RES-530",
           "RES-750": "RES-751", "RES-751": "RES-750"}
# near-identical role names that do NOT exist on the resource (for ROLE_NOT_FOUND tasks)
FAKE_ROLES = {"RES-201": "billing-prod-read", "RES-202": "billing-stg-read", "RES-310": "fin-drive-view",
              "RES-311": "fin-archive-viewers", "RES-420": "crm-reader", "RES-421": "crm-sbx-reader",
              "RES-530": "prod-cluster-view", "RES-531": "stg-cluster-view", "RES-640": "people-records-view",
              "RES-750": "wh-analyst-reader", "RES-751": "wh-sbx-reader", "RES-860": "wiki-readers",
              "RES-870": "support-viewers", "RES-880": "contract-viewer", "RES-890": "idp-audit",
              "RES-960": "payroll-view", "RES-970": "mkt-asset-viewer"}

DEPTS = {
    "Finance": (["Financial Analyst", "Senior Financial Analyst", "Accounts Payable Specialist"], "Finance Manager"),
    "Engineering": (["Software Engineer", "Senior Software Engineer", "Site Reliability Engineer"], "Engineering Manager"),
    "Data": (["Data Analyst", "Senior Data Analyst", "Data Engineer"], "Analytics Manager"),
    "Sales": (["Account Executive", "Senior Account Executive", "Sales Operations Specialist"], "Sales Manager"),
    "Support": (["Support Specialist", "Senior Support Specialist", "Support Operations Analyst"], "Support Team Lead"),
    "People": (["HR Generalist", "Payroll Specialist", "People Operations Analyst"], "People Partner Lead"),
    "Legal": (["Paralegal", "Contracts Specialist", "Senior Paralegal"], "Contracts Manager"),
    "Marketing": (["Content Marketer", "Marketing Designer", "Marketing Analyst"], "Marketing Manager"),
}
FIRST = ["Mara", "Tobias", "Ines", "Kwame", "Lucia", "Dmitri", "Anouk", "Rafael", "Sunniva", "Idris", "Hollis", "Priya",
         "Matteo", "Yara", "Bastian", "Noor", "Callum", "Esme", "Joaquin", "Leilani", "Oskar", "Thandiwe", "Wren",
         "Ravi", "Delphine", "Emeka", "Signe", "Tomasz", "Ayla", "Corin", "Zainab", "Florian", "Beatriz", "Hamish",
         "Mirela", "Odell", "Saskia", "Tarek", "Vivienne", "Dana"]
LAST = ["Okafor", "Whitfield", "Lindqvist", "Marchetti", "Asante", "Brandvold", "Castellanos", "Duvall", "Esterhuizen",
        "Fairbairn", "Gallardo", "Halloran", "Ilunga", "Jaramillo", "Kowalczyk", "Lachance", "Mbeki", "Nakashima",
        "Ostrowski", "Pemberton", "Quintero", "Rasmussen", "Saltonstall", "Thibodeaux", "Umeadi", "Vasquez-Holt",
        "Wexley", "Yilmazer", "Zubiri", "Abernathy", "Brightwell", "Corrigan", "Delacroix", "Engstrom", "Ferreira",
        "Grimsby", "Haverford", "Iversen", "Janssen", "Kellerman"]
LOCATIONS = ["Portland office", "Raleigh office", "Denver office", "Remote (US)", "Toronto office"]
NEED_VERBS = {
    "read": ["view records in", "look up data in", "run read-only reports against", "read documents in",
             "check figures in", "review entries in"],
    "write": ["update records in", "upload and edit files in", "make changes in", "edit entries in"],
    "admin": ["manage user permissions on", "change the configuration of"],
}
REASONS = ["for the quarter-end close", "for an audit sample", "for a customer escalation", "for the migration project",
           "for onboarding", "for the vendor review", "for a reporting request from my director",
           "for the incident follow-up", "for the budget refresh", "for the data quality review"]


def d(s: str) -> dt.date:
    return dt.date.fromisoformat(s)


def iso(x: dt.date) -> str:
    return x.isoformat()


def role_map(res: dict) -> dict:
    return {r["role"]: r for r in res["roles"]}


def lowest_role(res: dict, need: str) -> dict | None:
    cands = [r for r in res["roles"] if not r["deprecated"] and LEVELS[r["access_level"]] >= LEVELS[need]]
    return min(cands, key=lambda r: LEVELS[r["access_level"]]) if cands else None


def required_approvals(res: dict, level: str) -> list[str]:
    req = []
    if res["tier"] in ("T2", "T3"):
        req.append("manager")
    if res["tier"] == "T3" or level == "admin":
        req.append("resource_owner")
    return req


def owner_conflicted(data: dict, approver_id: str, requester_id: str, beneficiary_id: str) -> bool:
    """Hidden rule: an owner approval may not come from the requester, the beneficiary, or a direct report of either."""
    if approver_id in (requester_id, beneficiary_id):
        return True
    a = data["employees"].get(approver_id)
    return bool(a and a.get("manager_id") in (requester_id, beneficiary_id))


def policy_expiry(data: dict, item: dict, emp: dict, res: dict) -> dt.date:
    opened = d(data["ticket"]["opened_on"])
    contractor = emp["employment_type"] == "contractor"
    default = 30 if contractor else 90
    mx = {"T1": 365, "T2": 180, "T3": 30}[res["tier"]]
    if contractor:
        mx = min(mx, 90)
    dur = item.get("duration")
    if not dur:
        want = opened + dt.timedelta(days=default)
    elif dur[0] == "days":
        want = opened + dt.timedelta(days=dur[1])
    elif dur[0] == "weeks":
        want = opened + dt.timedelta(days=7 * dur[1])
    else:
        want = d(dur[1])
    return min(want, opened + dt.timedelta(days=mx))


def solve_item(data: dict, item: dict, hidden: bool = True) -> dict:
    """Outcome for one (beneficiary, resource) item: grant / deny / pending / noop. Records hidden rules applied."""
    applied: set[str] = set()
    emp = data["employees"][item["employee_id"]]
    res = data["resources"][item["resource_id"]]
    tk = data["ticket"]
    req_id = tk["requester_id"]
    out = {"employee_id": emp["employee_id"], "resource_id": res["resource_id"]}
    if emp["status"] != "active":
        return {**out, "kind": "deny", "reason": "INACTIVE_ACCOUNT", "applied": applied}
    if req_id != emp["employee_id"] and req_id != emp["manager_id"]:
        return {**out, "kind": "deny", "reason": "NOT_AUTHORIZED", "applied": applied}
    roles = role_map(res)
    need = item["need"]
    if item.get("named_role"):
        if item["named_role"] not in roles:
            return {**out, "kind": "deny", "reason": "ROLE_NOT_FOUND", "applied": applied}
        role = roles[item["named_role"]]
        if role["deprecated"]:
            role = roles[role["replaced_by"]]
    else:
        cat = [c for c in data["role_catalog"].get(emp["department"], [])
               if c["title"] == emp["title"] and c["resource_id"] == res["resource_id"]]
        if cat and LEVELS[roles[cat[0]["default_role"]]["access_level"]] >= LEVELS[need]:
            role = roles[cat[0]["default_role"]]
        else:
            role = lowest_role(res, need)
    if hidden and LEVELS[role["access_level"]] > LEVELS[need]:
        role = lowest_role(res, need)
        applied.add(H_READ)
    level = role["access_level"]
    if emp["employment_type"] == "contractor" and level == "admin":
        return {**out, "kind": "deny", "reason": "CONTRACTOR_ADMIN", "applied": applied}
    expiry = policy_expiry(data, item, emp, res)
    if hidden and emp.get("end_date") and d(emp["end_date"]) < expiry:
        expiry = d(emp["end_date"])
        applied.add(H_CONTRACT if emp["employment_type"] == "contractor" else H_DEPART)
    for a in data["current_access"].get(emp["employee_id"], []):
        if a["resource_id"] == res["resource_id"] and a["role"] == role["role"] and d(a["expiry_date"]) >= expiry:
            return {**out, "kind": "noop", "role": role["role"], "applied": applied}
    apps = [a for a in data["approvals"] if a["resource_id"] == res["resource_id"]]
    missing, rejected = [], False
    for kind in required_approvals(res, level):
        if kind == "manager":
            valid = [a for a in apps if a["approval_type"] == "manager" and a["approver_id"] == emp["manager_id"]]
        else:
            allowed = {res["owner_id"], *res["owner_delegates"]}
            valid = [a for a in apps if a["approval_type"] == "resource_owner" and a["approver_id"] in allowed]
            if hidden:
                kept = [a for a in valid if not owner_conflicted(data, a["approver_id"], req_id, emp["employee_id"])]
                if any(a["decision"] == "approved" for a in valid) and not any(a["decision"] == "approved" for a in kept):
                    applied.add(H_SELF)
                valid = kept
        if any(a["decision"] == "rejected" for a in valid):
            rejected = True
        elif not any(a["decision"] == "approved" for a in valid):
            missing.append(emp["manager_id"] if kind == "manager" else res["owner_id"])
    if rejected:
        return {**out, "kind": "deny", "reason": "APPROVAL_REJECTED", "applied": applied}
    if missing:
        return {**out, "kind": "pending", "role": role["role"], "approvers": missing, "applied": applied}
    return {**out, "kind": "grant", "role": role["role"], "expiry_date": iso(expiry), "applied": applied}


def solve(data: dict, items: list[dict], hidden: bool = True) -> dict:
    outs = [solve_item(data, it, hidden) for it in items]
    tid = data["ticket"]["ticket_id"]
    gold = {"grants": [], "denials": [], "approval_requests": [], "resolution": None, "applied": set()}
    for o in outs:
        gold["applied"] |= o["applied"]
        if o["kind"] == "grant":
            gold["grants"].append({"employee_id": o["employee_id"], "resource_id": o["resource_id"], "role": o["role"],
                                   "expiry_date": o["expiry_date"]})
        elif o["kind"] == "deny":
            gold["denials"].append({"ticket_id": tid, "employee_id": o["employee_id"], "resource_id": o["resource_id"],
                                    "reason_code": o["reason"]})
        elif o["kind"] == "pending":
            for ap in o["approvers"]:
                gold["approval_requests"].append({"ticket_id": tid, "approver_id": ap, "resource_id": o["resource_id"]})
    kinds = {o["kind"] for o in outs}
    gold["resolution"] = ("PENDING_APPROVAL" if "pending" in kinds else "GRANTED" if "grant" in kinds
                          else "DENIED" if "deny" in kinds else "NO_ACTION_NEEDED")
    gold["outcomes"] = [o["kind"] for o in outs]
    return gold


# ------------------------------------------------------------------------------------------------------------------
# World building


class World:
    def __init__(self, rng: random.Random, opened: dt.date):
        self.rng = rng
        self.opened = opened
        self.emps: dict[str, dict] = {}
        self.names: set[str] = set()
        self.ids: set[str] = set()
        self.resources: dict[str, dict] = {}
        self.approvals: list[dict] = []
        self.access: dict[str, list] = {}
        self.catalog: dict[str, list] = {}
        self.director = self.emp("Engineering", "Director of Operations", manager=None)

    def new_id(self, prefix: str, digits: int) -> str:
        while True:
            x = f"{prefix}{self.rng.randint(10 ** (digits - 1), 10 ** digits - 1)}"
            if x not in self.ids:
                self.ids.add(x)
                return x

    def new_name(self) -> str:
        while True:
            n = f"{self.rng.choice(FIRST)} {self.rng.choice(LAST)}"
            if n not in self.names:
                self.names.add(n)
                return n

    def emp(self, dept: str, title: str | None = None, manager: str | None = "director", etype: str = "employee",
            name: str | None = None, **kw) -> str:
        eid = self.new_id("E", 5)
        name = name or self.new_name()
        self.names.add(name)
        title = title or self.rng.choice(DEPTS[dept][0])
        if manager == "director":
            manager = self.director
        start = self.opened - dt.timedelta(days=self.rng.randint(40, 1500))
        rec = {"employee_id": eid, "name": name, "email": name.lower().replace(" ", ".") + "@quillmont.example",
               "department": dept, "title": title, "employment_type": etype, "status": "active",
               "start_date": iso(start), "end_date": None, "manager_id": manager,
               "manager_since": iso(start), "previous_manager_id": None,
               "location": self.rng.choice(LOCATIONS)}
        if etype == "contractor":
            rec["start_date"] = iso(self.opened - dt.timedelta(days=self.rng.randint(20, 300)))
            rec["manager_since"] = rec["start_date"]
            rec["end_date"] = iso(self.opened + dt.timedelta(days=self.rng.randint(120, 400)))
            rec["vendor"] = self.rng.choice(["Tallgrass Staffing", "Ferncliff Consulting", "Northbeam Partners"])
        rec.update(kw)
        self.emps[eid] = rec
        return eid

    def manager_of(self, dept: str) -> str:
        return self.emp(dept, DEPTS[dept][1])

    def add_resource(self, rid: str, owner_dept: str | None = None) -> dict:
        if rid in self.resources:
            return self.resources[rid]
        name, system, tier, roles, homes = RESOURCES[rid]
        owner = self.emp(owner_dept or homes[0], DEPTS[owner_dept or homes[0]][1])
        delegates = [self.emp(homes[0], manager=owner) for _ in range(self.rng.randint(0, 1))]
        self.resources[rid] = {
            "resource_id": rid, "name": name, "system": system, "tier": tier, "owner_id": owner,
            "owner_delegates": delegates,
            "roles": [{"role": r, "access_level": lvl, "deprecated": rep is not None, "replaced_by": rep}
                      for r, lvl, rep in roles]}
        return self.resources[rid]

    def approve(self, approver: str, rid: str, kind: str, decision: str = "approved"):
        self.approvals.append({"approval_id": None, "approver_id": approver, "approver_name": self.emps[approver]["name"],
                               "approval_type": kind, "resource_id": rid, "decision": decision,
                               "recorded_on": iso(self.opened + dt.timedelta(days=self.rng.randint(0, 2)))})

    def data(self, ticket: dict) -> dict:
        self.rng.shuffle(self.approvals)
        for i, a in enumerate(self.approvals):
            a["approval_id"] = f"APR-{ticket['ticket_id'][3:]}-{i + 1}"
        return {"ticket": ticket, "employees": self.emps, "resources": self.resources, "approvals": self.approvals,
                "current_access": self.access, "role_catalog": self.catalog}


SCENARIOS = (
    [("plain", 10), ("t2_ok", 10), ("t3_ok", 8), ("missing_mgr", 7), ("prev_mgr", 7), ("wrong_res_approval", 4),
     ("rejected", 5), ("inactive", 4), ("not_authorized", 7), ("role_not_found", 5), ("deprecated", 5),
     ("contractor_admin", 5), ("already", 5), ("duration_cap", 7),
     (H_CONTRACT, 17), (H_SELF, 17), (H_READ, 17), (H_DEPART, 16), ("multi", 12)])


def plan() -> list[str]:
    out = []
    for s, n in SCENARIOS:
        out += [s] * n
    return out


def build_task(idx: int, scen: str, rng: random.Random) -> dict:
    opened = dt.date(2026, 1, 12) + dt.timedelta(days=rng.randint(0, 300))
    w = World(rng, opened)
    tid = w.new_id("IT-", 5)
    pts = 0  # difficulty points
    multi = scen == "multi"
    subs = [rng.choice(["plain", "t2_ok", "t3_ok", "missing_mgr", "rejected", "not_authorized", "deprecated",
                        "already", "duration_cap", "role_not_found"]) for _ in range(2)] if multi else [scen]
    if multi:
        pts += 2
    # requester / beneficiaries
    on_behalf = rng.random() < 0.45 or scen in ("not_authorized",) or (multi and rng.random() < 0.5)
    multi_people = multi and on_behalf and rng.random() < 0.5
    if scen == H_SELF:
        on_behalf = rng.random() < 0.5
    dept_pool = list(DEPTS)
    items, sentences = [], []
    req_mgr = None
    first_res = None
    requester = None
    for k, sub in enumerate(subs):
        # resource choice
        cand = list(RESOURCES)
        if sub in ("t3_ok", H_SELF):
            cand = [r for r in cand if RESOURCES[r][2] == "T3"] if (sub == "t3_ok" or rng.random() < 0.7) else cand
        elif sub in ("t2_ok", "missing_mgr", "prev_mgr", "wrong_res_approval", "rejected"):
            cand = [r for r in cand if RESOURCES[r][2] in ("T2", "T3")]
        elif sub == "plain":
            cand = [r for r in cand if RESOURCES[r][2] == "T1"]
        elif sub == "deprecated":
            cand = [r for r in cand if any(x[2] for x in RESOURCES[r][3])]
        elif sub == "duration_cap":
            cand = [r for r in cand if RESOURCES[r][2] in ("T2", "T3")]
        if sub == "wrong_res_approval":
            cand = [r for r in RESOURCES if r in SIBLING and RESOURCES[r][2] != "T1"]
        if multi and k == 1 and first_res in cand and len(cand) > 1 and not multi_people:
            cand.remove(first_res)
        rid = rng.choice(cand) if not (multi and multi_people and k == 1 and rng.random() < 0.5) else first_res
        first_res = first_res or rid
        homes = RESOURCES[rid][4]
        dept = rng.choice(homes)
        # need level
        need = rng.choice(["read", "read", "write"])
        if sub == "contractor_admin":
            need = "admin"
            if not any(x[1] == "admin" for x in RESOURCES[rid][3]):
                rid = rng.choice([r for r in RESOURCES if any(x[1] == "admin" for x in RESOURCES[r][3])])
                dept = rng.choice(RESOURCES[rid][4])
        if sub == H_READ:
            need = "read"
        if sub == H_SELF and RESOURCES[rid][2] != "T3":
            need = "admin" if any(x[1] == "admin" for x in RESOURCES[rid][3]) else need
            if need != "admin":
                rid = rng.choice([r for r in RESOURCES if RESOURCES[r][2] == "T3"])
                dept = rng.choice(RESOURCES[rid][4])
        res = w.add_resource(rid)
        if rid in SIBLING and (rng.random() < 0.6 or sub == "wrong_res_approval"):
            w.add_resource(SIBLING[rid])
        # people
        etype = "contractor" if sub in (H_CONTRACT, "contractor_admin") or (
            sub in ("plain", "t2_ok", "duration_cap") and rng.random() < 0.25) else "employee"
        if requester is None:
            if on_behalf:
                req_mgr = w.manager_of(dept)
                requester = req_mgr
            title = None
        if on_behalf:
            if multi and k == 1 and not multi_people:
                bene = items[0]["employee_id"]
            else:
                kw = {}
                if sub == H_SELF and rng.random() < 0.3:
                    kw["title"] = DEPTS[dept][1]
                bdept = w.emps[req_mgr]["department"]
                bene = w.emp(bdept, manager=req_mgr, etype=etype, **kw)
        else:
            if k == 0:
                bene = w.emp(dept, etype=etype, manager=w.manager_of(dept))
                requester = bene
            else:
                bene = requester
        b = w.emps[bene]
        if b["employment_type"] != etype and sub in (H_CONTRACT, "contractor_admin"):
            # the beneficiary was reused from item 0 (multi); keep scenario coherent
            pass
        item = {"employee_id": bene, "resource_id": rid, "named_role": None, "need": need, "duration": None}
        roles = role_map(res)
        live = [r for r in res["roles"] if not r["deprecated"]]
        # duration
        r = rng.random()
        if sub == "duration_cap":
            tier = res["tier"]
            mx = {"T2": 180, "T3": 30}[tier]
            if b["employment_type"] == "contractor":
                mx = min(mx, 90)
            choice = rng.choice(["weeks", "until", "days_edge"])
            if choice == "weeks":
                item["duration"] = ("weeks", mx // 7 + rng.randint(1, 4))
            elif choice == "until":
                item["duration"] = ("until", iso(opened + dt.timedelta(days=mx + rng.randint(5, 60))))
            else:
                item["duration"] = ("days", mx)  # exactly at the limit
            pts += 2
        elif r < 0.2:
            item["duration"] = ("days", rng.choice([7, 14, 21, 45, 60]))
        elif r < 0.35:
            item["duration"] = ("weeks", rng.choice([2, 3, 4, 6, 8]))
            pts += 1
        elif r < 0.45:
            item["duration"] = ("until", iso(opened + dt.timedelta(days=rng.randint(10, 120))))
            pts += 1
        # role naming
        level_role = lowest_role(res, need)
        if sub == "deprecated":
            dep = [x for x in res["roles"] if x["deprecated"]][0]
            item["need"] = need = "read"
            item["named_role"] = dep["role"]
            pts += 2
        elif sub == "role_not_found":
            item["named_role"] = FAKE_ROLES[rid]
            pts += 2
        elif sub == H_READ:
            higher = [x for x in live if LEVELS[x["access_level"]] > 1]
            if b["employment_type"] == "contractor":
                higher = [x for x in higher if x["access_level"] != "admin"]
            pick = rng.choice(higher)
            if rng.random() < 0.6:
                item["named_role"] = pick["role"]
            else:
                w.catalog.setdefault(b["department"], []).append(
                    {"title": b["title"], "resource_id": rid, "default_role": pick["role"]})
                pts += 1
            pts += 1
        elif sub == "contractor_admin":
            item["named_role"] = [x for x in live if x["access_level"] == "admin"][0]["role"] if rng.random() < 0.5 else None
        else:
            r = rng.random()
            if r < 0.35:
                item["named_role"] = level_role["role"]
            elif r < 0.6:
                # catalog default that matches the need
                w.catalog.setdefault(b["department"], []).append(
                    {"title": b["title"], "resource_id": rid, "default_role": level_role["role"]})
            elif r < 0.7 and need == "write":
                # catalog default is read only: does not cover the need, fall back to lowest covering role
                rr = lowest_role(res, "read")
                w.catalog.setdefault(b["department"], []).append(
                    {"title": b["title"], "resource_id": rid, "default_role": rr["role"]})
                pts += 1
        # catalog distractors: other titles in the department
        others = [t for t in DEPTS[b["department"]][0] + [DEPTS[b["department"]][1]] if t != b["title"]]
        for t in rng.sample(others, k=min(len(others), rng.randint(1, 2))):
            w.catalog.setdefault(b["department"], []).append(
                {"title": t, "resource_id": rid, "default_role": rng.choice([x["role"] for x in live
                                                                              if x["access_level"] != "admin"])})
        # hidden-rule people setups
        if sub == H_CONTRACT:
            assert b["employment_type"] == "contractor"
        items.append(item)
        # end dates (after duration known)
        if sub in (H_CONTRACT, H_DEPART):
            if sub == H_DEPART:
                b["end_date_reason"] = "resignation"
            pexp = policy_expiry({"ticket": {"opened_on": iso(opened)}}, item, b, res)
            span = (pexp - opened).days
            b["end_date"] = iso(opened + dt.timedelta(days=rng.randint(max(3, span // 4), span - 1)))
            pts += 1
        elif b["employment_type"] == "contractor" and rng.random() < 0.3 and sub not in ("already",):
            # edge: contract ends exactly on the policy expiry (no cap needed)
            pexp = policy_expiry({"ticket": {"opened_on": iso(opened)}}, item, b, res)
            b["end_date"] = iso(pexp)
            pts += 1
        if sub == "inactive":
            b["status"] = "inactive"
            b["end_date"] = iso(opened - dt.timedelta(days=rng.randint(3, 60)))
            b["end_date_reason"] = "terminated" if b["employment_type"] == "employee" else "contract ended"
        if sub == "not_authorized":
            # requester is the beneficiary's former manager, or a peer manager
            if rng.random() < 0.6:
                newm = w.manager_of(b["department"])
                b["previous_manager_id"] = b["manager_id"]
                b["manager_id"] = newm
                b["manager_since"] = iso(opened - dt.timedelta(days=rng.randint(2, 25)))
                pts += 2
            else:
                b["manager_id"] = w.manager_of(b["department"])
                pts += 1
        if sub == "prev_mgr":
            newm = w.manager_of(b["department"])
            b["previous_manager_id"] = b["manager_id"]
            b["manager_id"] = newm
            b["manager_since"] = iso(opened - dt.timedelta(days=rng.randint(1, 20)))
            if on_behalf:
                # the new manager files on behalf; the old manager had approved earlier
                pass
            pts += 2
        elif rng.random() < 0.15 and sub not in ("not_authorized",) and not on_behalf:
            # distractor: recently changed managers, approval (if any) comes from the new one
            newm = w.manager_of(b["department"])
            b["previous_manager_id"] = b["manager_id"]
            b["manager_id"] = newm
            b["manager_since"] = iso(opened - dt.timedelta(days=rng.randint(1, 20)))
            pts += 1
        item["_sub"] = sub
    # on-behalf requests where a manager changed: requester must be the current manager unless not_authorized
    for it in items:
        b = w.emps[it["employee_id"]]
        if on_behalf and it["_sub"] != "not_authorized" and b["manager_id"] != requester:
            if it["_sub"] == "prev_mgr":
                # current manager files the request
                b["previous_manager_id"], b["manager_id"] = b["manager_id"], requester
                w.emps[b["previous_manager_id"]]  # exists
            else:
                b["manager_id"] = requester
        if on_behalf and it["_sub"] == "not_authorized" and b["manager_id"] == requester:
            b["manager_id"] = w.manager_of(b["department"])
    # approvals: satisfy everything the policy role and the hidden-rule role need, then perturb
    ticket = {"ticket_id": tid, "opened_on": iso(opened), "today": iso(opened + dt.timedelta(days=rng.randint(1, 3))),
              "requester_id": requester, "requester_name": w.emps[requester]["name"], "status": "open"}
    for it in items:
        sub = it["_sub"]
        b = w.emps[it["employee_id"]]
        res = w.resources[it["resource_id"]]
        lv = set()
        for hid in (True, False):
            o = solve_item(w.data(ticket), it, hid)
            if "role" in o:
                lv.add(role_map(res)[o["role"]]["access_level"])
            else:
                for nm in [it.get("named_role")]:
                    if nm and nm in role_map(res):
                        lv.add(role_map(res)[nm]["access_level"])
                lv.add(lowest_role(res, it["need"])["access_level"])
        kinds = set()
        for lvl in lv:
            kinds |= set(required_approvals(res, lvl))
        mgr_ok = b["manager_id"]
        reject_kind = None
        if sub == "rejected":
            reject_kind = "resource_owner" if "resource_owner" in kinds and rng.random() < 0.5 else "manager"
        if "manager" in kinds:
            if sub == "prev_mgr":
                w.approve(b["previous_manager_id"], res["resource_id"], "manager")
            elif sub == "missing_mgr":
                pass
            elif sub == "wrong_res_approval":
                sib = SIBLING.get(res["resource_id"])
                if sib:
                    w.add_resource(sib)
                    w.approve(mgr_ok, sib, "manager")
                else:
                    other = w.manager_of(b["department"])
                    w.approve(other, res["resource_id"], "manager")
            elif reject_kind == "manager":
                w.approve(mgr_ok, res["resource_id"], "manager", "rejected")
            else:
                w.approve(mgr_ok, res["resource_id"], "manager")
        if "resource_owner" in kinds:
            if sub == H_SELF:
                mode = rng.choice(["self", "requester", "report_of_bene", "report_of_req"]) if on_behalf else \
                    rng.choice(["self", "report_of_bene", "report_of_bene_recent"])
                if mode == "self":
                    res["owner_delegates"].append(b["employee_id"])
                    approver = b["employee_id"]
                elif mode == "requester":
                    res["owner_delegates"].append(requester)
                    approver = requester
                elif mode in ("report_of_bene", "report_of_bene_recent"):
                    approver = w.emp(b["department"], manager=b["employee_id"])
                    if mode == "report_of_bene_recent":
                        a = w.emps[approver]
                        a["previous_manager_id"] = res["owner_id"]
                        a["manager_since"] = iso(opened - dt.timedelta(days=rng.randint(3, 25)))
                    res["owner_delegates"].append(approver)
                else:
                    approver = w.emp(w.emps[requester]["department"], manager=requester)
                    a = w.emps[approver]
                    a["previous_manager_id"] = res["owner_id"]
                    a["manager_since"] = iso(opened - dt.timedelta(days=rng.randint(3, 25)))
                    res["owner_delegates"].append(approver)
                w.approve(approver, res["resource_id"], "resource_owner")
                pts += 1
            elif reject_kind == "resource_owner":
                w.approve(res["owner_id"], res["resource_id"], "resource_owner", "rejected")
            else:
                choice = rng.random()
                if res["owner_delegates"] and choice < 0.4:
                    dl = res["owner_delegates"][0]
                    if rng.random() < 0.4:
                        # distractor: delegate used to report to the beneficiary, now reports elsewhere (valid)
                        dd = w.emps[dl]
                        dd["previous_manager_id"] = b["employee_id"]
                        dd["manager_since"] = iso(opened - dt.timedelta(days=rng.randint(5, 40)))
                        pts += 1
                    w.approve(dl, res["resource_id"], "resource_owner")
                else:
                    w.approve(res["owner_id"], res["resource_id"], "resource_owner")
        # distractor approval by someone irrelevant
        if rng.random() < 0.25:
            peer = w.emp(b["department"])
            w.approve(peer, res["resource_id"], "manager")
            pts += 1
        # current access
        acc = w.access.setdefault(b["employee_id"], [])
        if sub == "already":
            o = solve_item(w.data(ticket), it, True)
            role = o.get("role")
            if role is None:
                role = lowest_role(res, it["need"])["role"]
            exp = d(ticket["opened_on"]) + dt.timedelta(days=rng.randint(200, 400))
            acc.append({"resource_id": res["resource_id"], "role": role, "granted_on": iso(opened - dt.timedelta(days=30)),
                        "expiry_date": iso(exp)})
        elif rng.random() < 0.3 and sub not in (H_CONTRACT, H_DEPART, H_READ, H_SELF):
            # existing access that does not satisfy the request (same role expiring sooner, or a sibling resource)
            o = solve_item(w.data(ticket), it, True)
            if o["kind"] == "grant" and rng.random() < 0.5:
                acc.append({"resource_id": res["resource_id"], "role": o["role"],
                            "granted_on": iso(opened - dt.timedelta(days=80)),
                            "expiry_date": iso(d(o["expiry_date"]) - dt.timedelta(days=rng.randint(1, 20)))})
                pts += 1
            else:
                item_res = {x["resource_id"] for x in items}
                pool = [x for x in w.resources.values() if x["resource_id"] not in item_res]
                if not pool:
                    pool = [w.add_resource(rng.choice([r for r in RESOURCES if r not in item_res]))]
                other = rng.choice(pool)
                acc.append({"resource_id": other["resource_id"],
                            "role": [x for x in other["roles"] if not x["deprecated"]][0]["role"],
                            "granted_on": iso(opened - dt.timedelta(days=60)),
                            "expiry_date": iso(opened + dt.timedelta(days=60))})
    # unrelated resources and near-duplicate people
    for extra in rng.sample(list(RESOURCES), 1):
        w.add_resource(extra)
    if rng.random() < 0.35 or (on_behalf and rng.random() < 0.5):
        tgt = w.emps[items[0]["employee_id"]]
        if rng.random() < 0.5:
            dup = tgt["name"]
        else:
            f, l = tgt["name"].split(" ", 1)
            dup = f + " " + (l[:-1] + ("e" if l[-1] != "e" else "a"))
        other_dept = rng.choice([x for x in DEPTS if x != tgt["department"]])
        w.emp(other_dept, name=dup)
        it0 = items[0]
        it0["_dup"] = True
        pts += 1

    data = w.data(ticket)
    # request text
    req = w.emps[requester]
    greet = rng.choice(["Hi IT, ", "Hello, ", "Hi team, ", ""])
    parts = []
    for it in items:
        b = w.emps[it["employee_id"]]
        res = w.resources[it["resource_id"]]
        verb = rng.choice(NEED_VERBS[it["need"]])
        dur = it["duration"]
        dtxt = "" if not dur else (f" for {dur[1]} days" if dur[0] == "days" else f" for {dur[1]} weeks"
                                   if dur[0] == "weeks" else f" until {dur[1]}")
        why = rng.choice(REASONS)
        role_txt = ""
        if it["named_role"]:
            role_txt = rng.choice([f" Please use the role `{it['named_role']}`.", f" The role I need is {it['named_role']}.",
                                   f" (role: {it['named_role']})"])
        if b["employee_id"] == requester:
            parts.append(f"I need access to the {res['name']}{dtxt} {why}: I need to {verb} it.{role_txt}")
        else:
            dept_hint = f" ({b['department']})" if it.get("_dup") or rng.random() < 0.5 else ""
            if it["named_role"]:
                role_txt = role_txt.replace("I need", "they need")
            rel = "who reports to me" if it["_sub"] != "not_authorized" else rng.choice(
                ["who is on my team", "from my group", "who works with me"])
            parts.append(f"Please give {b['name']}{dept_hint}, {rel}, access to the {res['name']}{dtxt} {why}. "
                         f"They need to {verb} it.{role_txt}")
    if len(parts) == 1:
        body = greet + parts[0]
    else:
        body = greet + "Two things on this ticket. (1) " + parts[0] + " (2) " + parts[1]
    body = body[0].upper() + body[1:]
    body = body.replace(", Please", ", please").replace(", Two", ", two")
    ticket["subject"] = "Access request: " + ", ".join(w.resources[it["resource_id"]]["name"] for it in items)
    ticket["body"] = body
    request = f"Ticket {tid} from {req['name']}:\n\n{body}"

    clean_items = [{k: v for k, v in it.items() if not k.startswith("_")} for it in items]
    gold = solve(data, clean_items, True)
    pol = solve(data, clean_items, False)
    triggers = sorted(gold.pop("applied"))
    pol.pop("applied")
    if scen in (H_CONTRACT, H_SELF, H_READ, H_DEPART):
        assert scen in triggers, (idx, scen, triggers)
    pts += len(triggers) + (1 if any(o != "grant" for o in gold["outcomes"]) else 0)
    gold["needs"] = {f"{it['employee_id']}|{it['resource_id']}": it["need"] for it in clean_items}
    gold["items"] = clean_items
    return {"id": f"acc-{idx:03d}", "request": request, "scenario": scen, "points": pts, "triggers": triggers,
            "gold": gold, "policy_only": pol, "_data": data}


def build_tasks() -> list[dict]:
    rng = random.Random(SEED)
    scen = plan()
    rng.shuffle(scen)
    tasks = [build_task(i + 1, s, rng) for i, s in enumerate(scen)]
    # difficulty by rank of points: lower third easy, middle medium, top hard
    order = sorted(range(len(tasks)), key=lambda i: (tasks[i]["points"], i))
    n = len(tasks)
    for rank, i in enumerate(order):
        tasks[i]["difficulty"] = "easy" if rank < n // 3 else "medium" if rank < 2 * n // 3 else "hard"
    return tasks
