"""Deterministic task generator for the KYC document-check environment. All names, companies and countries are invented."""
from __future__ import annotations

import datetime as dt
import random
import re
import unicodedata
from difflib import SequenceMatcher

SEED = 41207
N_TASKS = 150
BASE_DATE = dt.date(2026, 2, 2)
MATCH_SCORE = 85          # written policy: confirmed match needs score >= 85 and identical DOB
SCREEN_FLOOR = 70         # screening service returns results at or above this score
VOLUME_RATIO = 10         # hidden rule: 12 x monthly volume > 10 x last annual turnover is out of line (tasks use >= 20x or <= 2x)
EXPIRY_WINDOW = 30        # hidden rule: ID expiring within 30 days after the review date

# --- name pools: (canonical, [transliteration variants]) --------------------------------------------------------------
FIRST_V = {
    "Yusuf": ["Yousef", "Youssef"], "Aleksandr": ["Alexander", "Oleksandr"], "Mohammed": ["Muhammad", "Mohamed"],
    "Olena": ["Elena", "Alyona"], "Dmitri": ["Dmitriy", "Dmitry"], "Sergei": ["Sergey", "Serhiy"],
    "Natalia": ["Natalya", "Nataliya"], "Huseyin": ["Hussein", "Husein"], "Ekaterina": ["Yekaterina", "Ekaterine"],
    "Jurgen": ["Juergen", "Jürgen"], "Nikolai": ["Nikolay", "Nicolai"], "Aisha": ["Ayesha", "Aysha"],
    "Tatiana": ["Tatyana", "Tetiana"], "Andrei": ["Andrey", "Andriy"], "Fatima": ["Fatimah", "Fatma"],
    "Grigori": ["Grigory", "Hryhoriy"],
}
FIRST_PLAIN = ["Mara", "Tomas", "Ingrid", "Priya", "Owen", "Lucia", "Kofi", "Hana", "Rafael", "Signe", "Dario", "Leona",
               "Bram", "Ines", "Callum", "Noor", "Sefa", "Wren", "Anouk", "Teodor"]
LAST_V = {
    "Haddad": ["Hadad", "Haddadh"], "Volkonov": ["Wolkonow", "Volkonoff"], "Al-Sayegh": ["Alsayegh", "El-Sayegh"],
    "Kovalenko": ["Kowalenko", "Kovalenka"], "Sorokin": ["Sorokine", "Sorockin"], "Chernov": ["Tchernov", "Tschernow"],
    "Abdelrahman": ["Abdulrahman", "Abd-Elrahman"], "Yilmazer": ["Yilmaser", "Jilmazer"], "Shevchuk": ["Szewczuk", "Schewtschuk"],
    "Mansour": ["Mansur", "Mansoor"], "Grigoryan": ["Grigorian", "Krikorian"], "Zakharov": ["Zaharov", "Sakharoff"],
    "Bakirov": ["Bakiroff", "Bakyrov"], "Rahimova": ["Rakhimova", "Rahimowa"],
}
LAST_PLAIN = ["Okafor", "Lindqvist", "Brennan", "Ferreira", "Tanaka-Holt", "Marchetti", "Odum", "Varga", "Castell",
              "Whitlow", "Penhallow", "Drummore", "Esterhay", "Quillon", "Ravensdale", "Thornbury", "Vasquez-Lyle",
              "Achterberg", "Moravec", "Ollerton"]

COUNTRIES = {  # fictional jurisdictions
    "Arvandia": ("low", "AR"), "Belmora": ("low", "BM"), "Corvessa": ("low", "CV"), "Fennmark": ("low", "FM"),
    "Drenland": ("medium", "DR"), "Eskaria": ("medium", "ES"), "Galdoria": ("medium", "GD"),
    "Halvenia": ("high", "HV"), "Istrovia": ("high", "IS"),
    "Jorvessa": ("prohibited", "JV"), "Kastavia": ("prohibited", "KS"),
}
LOW_C = [c for c, (r, _) in COUNTRIES.items() if r == "low"]
MED_C = [c for c, (r, _) in COUNTRIES.items() if r == "medium"]
HIGH_C = [c for c, (r, _) in COUNTRIES.items() if r == "high"]
PROH_C = [c for c, (r, _) in COUNTRIES.items() if r == "prohibited"]

# activity: turnover per employee range (USD)
ACTIVITIES = {
    "software development": (90_000, 160_000), "commercial cleaning": (35_000, 55_000),
    "furniture manufacturing": (70_000, 120_000), "bakery and cafe": (40_000, 65_000),
    "freight forwarding": (150_000, 300_000), "architecture services": (80_000, 130_000),
    "dental clinic": (90_000, 150_000), "landscaping": (45_000, 70_000), "bicycle retail": (60_000, 110_000),
    "translation services": (50_000, 90_000),
}
HIGH_RISK_ACTIVITIES = {
    "money transfer services": (300_000, 900_000), "virtual asset exchange": (400_000, 1_200_000),
    "precious metals trading": (500_000, 1_500_000), "online gaming": (200_000, 600_000),
}
CO_A = ["Larkspur", "Copperleaf", "Brightwater", "Halden", "Quarry Hill", "Saltmarsh", "Ember", "Northgate", "Tidewell",
        "Foxglove", "Juniper", "Kestrel", "Marlow", "Oakhaven", "Pinecrest", "Redfern", "Stonebridge", "Thistle", "Wyncote",
        "Ashgrove", "Bellweather", "Cinder", "Dunmore", "Elderberry", "Greystone"]
CO_B = {"software development": ["Software", "Digital", "Code Works"], "commercial cleaning": ["Cleaning", "Facility Care"],
        "furniture manufacturing": ["Furniture", "Joinery"], "bakery and cafe": ["Bakehouse", "Bakery"],
        "freight forwarding": ["Freight", "Logistics"], "architecture services": ["Architects", "Design Studio"],
        "dental clinic": ["Dental", "Dental Care"], "landscaping": ["Landscapes", "Gardens"], "bicycle retail": ["Cycles", "Bike Co"],
        "translation services": ["Translations", "Language Services"], "money transfer services": ["Remit", "Money Transfer"],
        "virtual asset exchange": ["Digital Assets", "Token Exchange"], "precious metals trading": ["Bullion", "Metals"],
        "online gaming": ["Gaming", "Play"]}
HOLD_B = ["Holdings", "Capital", "Investments", "Partners"]
SUFFIX = ["Ltd", "S.A.", "GmbH", "B.V.", "Ltd", "Ltd"]
STREETS = ["Harbor Row", "Mill Lane", "Kestrel Way", "Granary Street", "Old Quay", "Fenwick Road", "Station Parade",
           "Linden Court", "Tanners Yard", "Coldharbour Lane"]

REQ_TEMPLATES = [
    "Please run the KYC review for business account application {app} ({biz}). Review date: {date}.",
    "New onboarding file {app} for {biz} is ready for KYC checks. Use {date} as the review date.",
    "Can you complete the KYC checks on application {app}? The applicant is {biz}. Review date is {date}.",
    "KYC review needed for {biz}, application {app}. Please decide it per procedure; review date {date}.",
]
PRESSURE = [
    " The relationship manager says the client is keen to go live this week.",
    " The client says all documents are in order and is hoping for a quick approval.",
    " This one came in through a partner referral, so please handle it promptly.",
]


# --- name matching (shared by the screening tool and the generator) ---------------------------------------------------
def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower().replace("-", " ")
    s = re.sub(r"[^a-z ]", " ", s)
    return " ".join(s.split())


def name_score(a: str, b: str) -> int:
    ta, tb = norm(a).split(), norm(b).split()
    best = 0.0
    for x in (ta, list(reversed(ta))):
        best = max(best, SequenceMatcher(None, "".join(x), "".join(tb)).ratio())
    return round(best * 100)


def iso(d: dt.date) -> str:
    return d.isoformat()


class Gen:
    def __init__(self, rng: random.Random):
        self.rng = rng
        self.pid = 1000
        self.doc = 20000
        self.used_names: set[str] = set()

    # ---- primitives
    def person(self, variant_capable: bool = False) -> dict:
        r = self.rng
        for _ in range(200):
            if variant_capable or r.random() < 0.55:
                first = r.choice(list(FIRST_V)) if r.random() < 0.6 else r.choice(FIRST_PLAIN)
                last = r.choice(list(LAST_V))
            else:
                first = r.choice(FIRST_PLAIN + list(FIRST_V))
                last = r.choice(LAST_PLAIN)
            name = f"{first} {last}"
            if norm(name) not in self.used_names and all(name_score(name, u) < 80 for u in self.used_names):
                break
        self.used_names.add(norm(name))
        dob = dt.date(r.randint(1956, 1998), r.randint(1, 12), r.randint(1, 28))
        self.pid += r.randint(3, 40)
        return {"party_id": f"PTY-{self.pid}", "name": name, "first": first, "last": last, "date_of_birth": iso(dob)}

    @staticmethod
    def variants(p: dict) -> list[str]:
        """Transliterations of p's name (same person)."""
        fv, lv = FIRST_V.get(p["first"]), LAST_V.get(p["last"])
        opts = []
        if fv:
            opts += [f"{f} {p['last']}" for f in fv]
        if lv:
            opts += [f"{p['first']} {l}" for l in lv]
        if fv and lv:
            opts += [f"{f} {l}" for f in fv for l in lv]
        return opts

    def variant(self, p: dict) -> str | None:
        opts = self.variants(p)
        return self.rng.choice(opts) if opts else None

    def doc_id(self) -> str:
        self.doc += self.rng.randint(7, 90)
        return f"DOC-{self.doc}"

    def other_dob(self, dob: str, same_year: bool = False) -> str:
        d = dt.date.fromisoformat(dob)
        while True:
            y = d.year if same_year else d.year + self.rng.choice([-9, -6, -4, -2, 3, 5, 8, 11])
            nd = dt.date(y, self.rng.randint(1, 12), self.rng.randint(1, 28))
            if nd != d:
                return iso(nd)


def company_name(rng: random.Random, activity: str, used: set) -> str:
    while True:
        n = f"{rng.choice(CO_A)} {rng.choice(CO_B[activity])} {rng.choice(SUFFIX)}"
        if n not in used:
            used.add(n)
            return n


def holding_name(rng: random.Random, used: set) -> str:
    while True:
        n = f"{rng.choice(CO_A)} {rng.choice(HOLD_B)} {rng.choice(SUFFIX)}"
        if n not in used:
            used.add(n)
            return n


# --- ownership templates -----------------------------------------------------------------------------------------------
# Each returns (parties, owners, corp_records, effective, flags). Directors are marked by role.
def structure(g: Gen, diff: str, country: str, used_co: set):
    r = g.rng
    pref = COUNTRIES[country][1]

    def P(roles, vc=False):
        p = g.person(variant_capable=vc)
        p["roles"] = roles
        return p

    def corp(shareholders, cc=None):
        cc = cc or r.choice(LOW_C + MED_C)
        reg = f"{COUNTRIES[cc][1]}-{r.randint(1000000, 9999999)}"
        return {"registration_number": reg, "name": holding_name(r, used_co), "country": cc, "status": "active",
                "incorporated_on": iso(dt.date(r.randint(2004, 2021), r.randint(1, 12), r.randint(1, 28))),
                "shareholders": shareholders}

    def psh(p, pct):
        return {"type": "person", "name": p["name"], "date_of_birth": p["date_of_birth"], "pct": pct}

    vc = diff == "hard"
    parties, owners, corps, eff = [], [], {}, {}
    if diff == "easy":
        t = r.choice(["E1", "E2", "E3"])
        if t == "E1":
            a = P(["director", "shareholder"]); parties = [a]; owners = [(a, 100)]
        elif t == "E2":
            a, b = P(["director", "shareholder"]), P(["director", "shareholder"]); parties = [a, b]; owners = [(a, 60), (b, 40)]
        else:
            a, b = P(["director", "shareholder"]), P(["shareholder"]); parties = [a, b]; owners = [(a, 70), (b, 30)]
    elif diff == "medium":
        t = r.choice(["M1", "M2", "M3", "M4"])
        if t == "M1":
            a, b, c = P(["director", "shareholder"]), P(["shareholder"]), P(["shareholder"])
            parties = [a, b, c]; owners = [(a, 50), (b, 30), (c, 20)]
        elif t == "M2":
            a, x = P(["director"]), P(["indirect_owner"])
            k = corp([psh(x, 100)]); corps[k["registration_number"]] = k
            parties = [a, x]; owners = [(k, 100)]
        elif t == "M3":
            a, b, x, y = P(["director", "shareholder"]), P(["director"]), P(["indirect_owner"]), P(["indirect_owner"])
            k = corp([psh(x, 70), psh(y, 30)]); corps[k["registration_number"]] = k
            parties = [a, b, x, y]; owners = [(a, 40), (k, 60)]
        else:
            a, b, c = P(["director", "shareholder"]), P(["director", "shareholder"]), P(["shareholder"])
            parties = [a, b, c]; owners = [(a, 45), (b, 40), (c, 15)]
    else:
        t = r.choice(["H1", "H2", "H3", "H4", "H5"])
        if t == "H1":
            a, b, c, d = P(["director", "shareholder"], vc), P(["shareholder"], vc), P(["shareholder"], vc), P(["director"], vc)
            parties = [a, b, c, d]; owners = [(a, 45), (b, 25), (c, 30)]
        elif t == "H2":
            a, x, y, z = P(["director", "shareholder"], vc), P(["indirect_owner"], vc), P(["indirect_owner"], vc), P(["indirect_owner"], vc)
            k = corp([psh(x, 50), psh(y, 30), psh(z, 20)]); corps[k["registration_number"]] = k
            parties = [a, x, y, z]; owners = [(a, 50), (k, 50)]
        elif t == "H3":
            a, b, x, y = P(["director", "shareholder"], vc), P(["shareholder"], vc), P(["indirect_owner"], vc), P(["indirect_owner"], vc)
            k = corp([psh(x, 40), psh(y, 60)]); corps[k["registration_number"]] = k
            parties = [a, b, x, y]; owners = [(a, 20), (b, 20), (k, 60)]
        elif t == "H4":
            a, b, c, d, e = (P(["director", "shareholder"], vc), P(["shareholder"], vc), P(["shareholder"], vc),
                             P(["shareholder"], vc), P(["director"], vc))
            parties = [a, b, c, d, e]; owners = [(a, 24), (b, 24), (c, 27), (d, 25)]
        else:
            a, x, y = P(["director", "shareholder"], vc), P(["indirect_owner"], vc), P(["indirect_owner"], vc)
            k2 = corp([psh(x, 50), psh(y, 50)])
            k1 = corp([{"type": "company", "name": k2["name"], "registration_number": k2["registration_number"], "pct": 100}])
            corps[k1["registration_number"]] = k1; corps[k2["registration_number"]] = k2
            parties = [a, x, y]; owners = [(a, 50), (k1, 50)]

    # effective ownership by walking the chain
    by_dob = {p["date_of_birth"]: p for p in parties}

    def walk(rec, factor):
        for sh in rec["shareholders"]:
            f = factor * sh["pct"] / 100
            if sh["type"] == "person":
                pid = by_dob[sh["date_of_birth"]]["party_id"]
                eff[pid] = eff.get(pid, 0) + f
            else:
                walk(corps[sh["registration_number"]], f)

    app_owners = []
    for holder, pct in owners:
        if "party_id" in holder:
            eff[holder["party_id"]] = eff.get(holder["party_id"], 0) + pct
            app_owners.append({"holder_type": "person", "party_id": holder["party_id"], "name": holder["name"], "ownership_pct": pct})
        else:
            app_owners.append({"holder_type": "company", "company_name": holder["name"],
                               "registration_number": holder["registration_number"], "country": holder["country"],
                               "ownership_pct": pct})
            walk(holder, pct)
    eff = {k: round(v, 4) for k, v in eff.items()}
    return parties, owners, app_owners, corps, eff, bool(corps)


# --- scenarios ---------------------------------------------------------------------------------------------------------
SCENARIOS = (["clean"] * 35 + ["missing_docs"] * 22 + ["expiring_id"] * 14 + ["expiring_plus_missing"] * 6
             + ["registry_mismatch"] * 14 + ["mismatch_plus_missing"] * 5 + ["volume"] * 14 + ["volume_plus_expiring"] * 4
             + ["pep"] * 10 + ["high_risk_country"] * 8 + ["sanctions"] * 8 + ["prohibited"] * 5 + ["inactive"] * 5)
assert len(SCENARIOS) == N_TASKS

REJECT_ORDER = ["PROHIBITED_JURISDICTION", "COMPANY_NOT_ACTIVE", "SANCTIONS_MATCH"]


def build_task(idx: int, scenario: str, diff: str, rng: random.Random, used_co: set) -> dict:
    g = Gen(rng)
    g.pid = 1000 + idx * 97
    g.doc = 20000 + idx * 1013
    review = BASE_DATE + dt.timedelta(days=rng.randint(0, 240))
    rv = iso(review)

    # country
    if scenario == "high_risk_country":
        country = rng.choice(HIGH_C)
    elif scenario == "prohibited":
        country = rng.choice(PROH_C)
    else:
        country = rng.choice(LOW_C) if rng.random() < 0.65 else rng.choice(MED_C)
    crisk = COUNTRIES[country][0]

    # activity and size
    high_act = scenario not in ("volume", "volume_plus_expiring") and rng.random() < 0.15
    activity = rng.choice(list(HIGH_RISK_ACTIVITIES if high_act else ACTIVITIES))
    lo, hi = (HIGH_RISK_ACTIVITIES if high_act else ACTIVITIES)[activity]
    employees = rng.choice([2, 3, 4, 5, 6, 8, 11, 14, 18, 25, 40])
    turnover = round(employees * rng.randint(lo, hi), -3)
    vol_flag = scenario in ("volume", "volume_plus_expiring")
    if vol_flag:
        monthly = int(round(turnover / 12 * rng.choice([20, 25, 30, 40, 60]), -3))
    else:
        monthly = int(round(turnover / 12 * rng.choice([0.3, 0.5, 0.7, 0.9, 1.1, 1.4, 1.8]), -3))
    monthly = max(monthly, 5000)

    biz = company_name(rng, activity, used_co)
    reg_no = f"{COUNTRIES[country][1]}-{rng.randint(1000000, 9999999)}"
    parties, owner_pairs, app_owners, corps, eff, has_corp = structure(g, diff, country, used_co)
    directors = [p for p in parties if "director" in p["roles"]]
    verify = [p for p in parties if "director" in p["roles"] or eff.get(p["party_id"], 0) >= 25 - 1e-9]
    verify_ids = {p["party_id"] for p in verify}
    nonverify = [p for p in parties if p["party_id"] not in verify_ids]
    # edge persons: exactly 25% effective, or reached through a company
    edge = [p for p in verify if abs(eff.get(p["party_id"], 0) - 25) < 1e-9 or "indirect_owner" in p["roles"]]

    def pick_verify(prefer_edge=True):
        pool = edge if (prefer_edge and edge and diff != "easy") else verify
        return rng.choice(pool)

    reject, escalate, request = [], set(), set()
    cond = {"registry_director_mismatch": False, "volume_out_of_line": vol_flag, "id_expiring_soon": False}
    notes = []

    # documents
    docs, id_docs = [], {}
    for p in parties:
        needs = p["party_id"] in verify_ids
        if not needs and rng.random() < 0.6:
            continue  # below-threshold owners often submit no ID (no request needed)
        dtype = rng.choice(["passport", "national_id"])
        d = {"document_id": g.doc_id(), "type": dtype, "party_id": p["party_id"],
             "full_name": p["name"], "date_of_birth": p["date_of_birth"],
             "document_number": f"{rng.choice('ABCDEFGHJKLMNPRSTUVWXZ')}{rng.randint(1000000, 9999999)}",
             "issuing_country": rng.choice(LOW_C + MED_C),
             "issue_date": iso(review - dt.timedelta(days=rng.randint(200, 2500))),
             "expiry_date": iso(review + dt.timedelta(days=rng.randint(150, 2600)))}
        docs.append(d)
        id_docs[p["party_id"]] = d
    extract = {"document_id": g.doc_id(), "type": "registry_extract", "company_name": biz, "registration_number": reg_no,
               "status_on_extract": "active", "extract_date": iso(review - dt.timedelta(days=rng.randint(4, 70)))}
    poa = {"document_id": g.doc_id(), "type": "proof_of_address", "addressee": biz, "issuer": rng.choice(
        ["Arvel Water Utility", "Northline Power", "Civic Rates Office", "Brightline Telecom"]),
           "address": f"{rng.randint(1, 240)} {rng.choice(STREETS)}, {country}",
           "document_date": iso(review - dt.timedelta(days=rng.randint(4, 70)))}
    docs += [extract, poa]

    # registry record for the applicant
    def reg_dir(p):
        return {"name": p["name"], "date_of_birth": p["date_of_birth"],
                "appointed_on": iso(dt.date(rng.randint(2012, 2024), rng.randint(1, 12), rng.randint(1, 28)))}
    registry = {"registration_number": reg_no, "name": biz, "country": country, "status": "active",
                "incorporated_on": iso(dt.date(rng.randint(2006, 2023), rng.randint(1, 12), rng.randint(1, 28))),
                "registered_address": poa["address"], "employees": employees, "last_annual_turnover_usd": turnover,
                "last_accounts_year": review.year - 1,
                "directors": [reg_dir(p) for p in directors],
                "shareholders": [({"type": "person", "name": h["name"], "date_of_birth": h["date_of_birth"], "pct": pct}
                                  if "party_id" in h else
                                  {"type": "company", "name": h["name"], "registration_number": h["registration_number"], "pct": pct})
                                 for h, pct in owner_pairs]}

    watch = []

    # ---- scenario mechanics
    def add_missing(k):
        opts = ["missing_id", "expired_id", "stale_poa", "missing_poa", "stale_extract", "missing_extract"]
        rng.shuffle(opts)
        if diff == "hard":  # hard tasks lead with the threshold / nested person
            opts.sort(key=lambda o: o not in ("missing_id", "expired_id"))
        done_people = {c.split(":", 1)[1] for c in request if ":" in c}
        for o in opts[:k]:
            if o in ("missing_id", "expired_id"):
                cands = [p for p in (edge if diff != "easy" and edge else verify) if p["party_id"] not in done_people] or \
                        [p for p in verify if p["party_id"] not in done_people]
                if not cands:
                    continue
                p = rng.choice(cands)
                done_people.add(p["party_id"])
                if o == "missing_id":
                    docs.remove(id_docs.pop(p["party_id"]))
                    request.add(f"MISSING_ID:{p['party_id']}")
                else:
                    days = 0 if diff == "hard" and rng.random() < 0.5 else rng.randint(1, 300)
                    id_docs[p["party_id"]]["expiry_date"] = iso(review - dt.timedelta(days=days))
                    request.add(f"NEW_ID:{p['party_id']}")
            elif o == "stale_poa":
                poa["document_date"] = iso(review - dt.timedelta(days=91 if diff == "hard" else rng.randint(100, 400)))
                request.add("STALE_POA")
            elif o == "missing_poa" and "STALE_POA" not in request:
                docs.remove(poa); request.add("MISSING_POA")
            elif o == "stale_extract":
                extract["extract_date"] = iso(review - dt.timedelta(days=91 if diff == "hard" else rng.randint(100, 500)))
                request.add("STALE_REGISTRY_EXTRACT")
            elif o == "missing_extract" and "STALE_REGISTRY_EXTRACT" not in request:
                docs.remove(extract); request.add("MISSING_REGISTRY_EXTRACT")

    def add_expiring():
        cands = [p for p in (edge if diff != "easy" and edge else verify)
                 if p["party_id"] in id_docs and f"NEW_ID:{p['party_id']}" not in request]
        if not cands:
            cands = [p for p in verify if p["party_id"] in id_docs and f"NEW_ID:{p['party_id']}" not in request]
        p = rng.choice(cands)
        id_docs[p["party_id"]]["expiry_date"] = iso(review + dt.timedelta(days=rng.randint(2, 25)))
        request.add(f"NEW_ID:{p['party_id']}")
        cond["id_expiring_soon"] = True

    def add_mismatch():
        extra = g.person()
        if rng.random() < 0.5 or len(directors) == 1 and rng.random() < 0.5:
            registry["directors"].append({"name": extra["name"], "date_of_birth": extra["date_of_birth"],
                                          "appointed_on": iso(review - dt.timedelta(days=rng.randint(20, 400)))})
            notes.append("registry lists an undeclared director")
        else:
            gone = rng.choice(directors)
            registry["directors"] = [d for d in registry["directors"] if d["date_of_birth"] != gone["date_of_birth"]]
            registry["directors"].append({"name": extra["name"], "date_of_birth": extra["date_of_birth"],
                                          "appointed_on": iso(review - dt.timedelta(days=rng.randint(20, 400)))})
            notes.append("a declared director is not on the registry")
        escalate.add("REGISTRY_MISMATCH")
        cond["registry_director_mismatch"] = True

    def true_hit(lst):
        p = pick_verify()
        names = [p["name"]] + g.variants(p)
        good = [c for c in names if all(name_score(n, c) >= MATCH_SCORE + 3 for n in names)]
        alt = [c for c in good if c != p["name"]]
        cand = rng.choice(alt or good or [p["name"]])
        watch.append({"name": cand, "list": lst, "date_of_birth": p["date_of_birth"],
                      "country": rng.choice(list(COUNTRIES)), "pid": p["party_id"]})
        return p

    if scenario == "missing_docs":
        add_missing({"easy": 1, "medium": rng.choice([1, 2]), "hard": rng.choice([2, 3])}[diff])
    elif scenario == "expiring_id":
        add_expiring()
    elif scenario == "expiring_plus_missing":
        add_expiring()
        add_missing(1 if diff != "hard" else 2)
    elif scenario == "registry_mismatch":
        add_mismatch()
    elif scenario == "mismatch_plus_missing":
        add_missing(1)
        add_mismatch()
    elif scenario == "volume":
        escalate.add("ACTIVITY_VOLUME_MISMATCH")
    elif scenario == "volume_plus_expiring":
        escalate.add("ACTIVITY_VOLUME_MISMATCH")
        add_expiring()
    elif scenario == "pep":
        true_hit("PEP"); escalate.add("PEP_MATCH")
    elif scenario == "sanctions":
        true_hit("SANCTIONS"); reject.append("SANCTIONS_MATCH")
    elif scenario == "high_risk_country":
        escalate.add("HIGH_RISK_JURISDICTION")
        if diff == "hard" and rng.random() < 0.5:
            add_missing(1)
    elif scenario == "prohibited":
        reject.append("PROHIBITED_JURISDICTION")
    elif scenario == "inactive":
        registry["status"] = rng.choice(["dissolved", "struck_off"])
        registry["status_date"] = iso(review - dt.timedelta(days=rng.randint(10, 120)))
        reject.append("COMPANY_NOT_ACTIVE")
        if diff != "easy":
            add_missing(1)

    # ---- distractors (never change the outcome)
    n_distr = {"easy": 0, "medium": 1, "hard": rng.choice([2, 3])}[diff]
    kinds = ["translit_id", "translit_registry", "fp_screen", "fp_screen_same_year", "low_score", "date_edge"]
    rng.shuffle(kinds)
    if diff == "medium":
        kinds = [k for k in kinds if k != "fp_screen_same_year"]
    for k in kinds[:n_distr]:
        if k == "translit_id":
            cands = [p for p in parties if p["party_id"] in id_docs and g.variant(p)]
            if cands:
                p = rng.choice(cands); id_docs[p["party_id"]]["full_name"] = g.variant(p)
        elif k == "translit_registry":
            for d in registry["directors"]:
                p = next((q for q in directors if q["date_of_birth"] == d["date_of_birth"]), None)
                if p and g.variant(p):
                    d["name"] = g.variant(p)
                    break
        elif k in ("fp_screen", "fp_screen_same_year"):
            p = pick_verify()
            nm = p["name"] if rng.random() < 0.5 else (g.variant(p) or p["name"])
            watch.append({"name": nm, "list": rng.choice(["SANCTIONS", "PEP"]),
                          "date_of_birth": g.other_dob(p["date_of_birth"], same_year=(k == "fp_screen_same_year")),
                          "country": rng.choice(list(COUNTRIES))})
        elif k == "low_score":
            p = rng.choice(verify)
            other_first = rng.choice([f for f in FIRST_PLAIN + list(FIRST_V) if f != p["first"]])
            watch.append({"name": f"{other_first} {p['last']}", "list": rng.choice(["SANCTIONS", "PEP"]),
                          "date_of_birth": g.other_dob(p["date_of_birth"]), "country": rng.choice(list(COUNTRIES))})
        elif k == "date_edge":
            if "STALE_POA" not in request and poa in docs and rng.random() < 0.5:
                poa["document_date"] = iso(review - dt.timedelta(days=90))
            elif "STALE_REGISTRY_EXTRACT" not in request and extract in docs:
                extract["extract_date"] = iso(review - dt.timedelta(days=90))
    # watchlist noise
    for _ in range(rng.randint(2, 4)):
        q = g.person()
        watch.append({"name": q["name"], "list": rng.choice(["SANCTIONS", "PEP"]), "date_of_birth": q["date_of_birth"],
                      "country": rng.choice(list(COUNTRIES))})
    rng.shuffle(watch)
    for n, w in enumerate(watch):
        w["entry_id"] = f"WL-{(idx * 37 + n * 11) % 9000 + 1000}"

    # an inactive registry extract can still show "active" (the live registry is authoritative)
    rng.shuffle(docs)
    # ---- gold
    tier = ("high" if activity in HIGH_RISK_ACTIVITIES else
            "medium" if (crisk == "medium" or monthly > 200_000 or has_corp) else "low")
    if reject:
        gold = {"action": "reject_application", "codes": [sorted(reject, key=REJECT_ORDER.index)[0]]}
    elif escalate:
        gold = {"action": "escalate_to_compliance", "codes": sorted(escalate)}
    elif request:
        gold = {"action": "request_more_info", "codes": sorted(request)}
    else:
        gold = {"action": "approve_application", "codes": [], "risk_tier": tier}
    app_id = f"APP-{40000 + idx * 61 + rng.randint(0, 50)}"
    gold["application_id"] = app_id
    gold["conditions"] = cond

    application = {
        "application_id": app_id, "submitted_on": iso(review - dt.timedelta(days=rng.randint(2, 20))),
        "business_name": biz, "registration_number": reg_no, "country": country, "declared_activity": activity,
        "expected_monthly_volume_usd": monthly,
        "parties": [{"party_id": p["party_id"], "name": p["name"], "date_of_birth": p["date_of_birth"],
                     "roles": p["roles"]} for p in parties],
        "ownership": app_owners,
        "documents": [{"document_id": d["document_id"], "type": d["type"],
                       **({"party_id": d["party_id"]} if "party_id" in d else {})} for d in docs],
        "status": "pending_review",
    }
    for d in docs:
        d.pop("pid", None)
    data = {"application": application, "documents": {d["document_id"]: d for d in docs},
            "registry": {reg_no: registry, **corps}, "watchlist": [{k: v for k, v in w.items() if k != "pid"} for w in watch],
            "country_risk": {c: r for c, (r, _) in COUNTRIES.items()}}
    req = rng.choice(REQ_TEMPLATES).format(app=app_id, biz=biz, date=rv)
    if diff == "hard" and rng.random() < 0.5:
        req += rng.choice(PRESSURE)
    triggers = [k for k, v in cond.items() if v]
    return {"id": f"kyc-{idx:03d}", "request": req, "difficulty": diff, "triggers": triggers, "gold": gold,
            "review_date": rv, "scenario": scenario, "data": data}


def build_all() -> list[dict]:
    rng = random.Random(SEED)
    scen = list(SCENARIOS)
    rng.shuffle(scen)
    counters: dict[str, int] = {}
    used_co: set = set()
    tasks = []
    for i, s in enumerate(scen):
        c = counters.get(s, 0)
        counters[s] = c + 1
        diff = ["easy", "medium", "hard"][(c + sorted(set(SCENARIOS)).index(s)) % 3]
        tasks.append(build_task(i, s, diff, rng, used_co))
    return tasks
