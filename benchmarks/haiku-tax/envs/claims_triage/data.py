"""Deterministic task generator for the claims triage environment (fixed seed, ground truth by construction)."""
from __future__ import annotations

import random
from datetime import date, timedelta

from . import logic

SEED = 20261019
TODAY = date(2026, 10, 19)
N_TASKS = 150

FIRST = ["Mara", "Tobias", "Ines", "Caleb", "Priya", "Rowan", "Delphine", "Marcus", "Yuki", "Odette", "Felix", "Hana",
         "Desmond", "Lucia", "Anders", "Nadia", "Bram", "Sefa", "Imogen", "Teodor", "Wren", "Joaquin", "Aster", "Calla",
         "Emeka", "Greta", "Idris", "Linnea", "Matthias", "Noor", "Oren", "Petra", "Quentin", "Rosalind", "Silas",
         "Talia", "Ulric", "Vesna", "Wade", "Zora"]
SURNAMES = ["Okafor", "Whitcombe", "Lindqvist", "Marchetti", "Halvorsen", "Castellano", "Brannigan", "Thistlewood",
            "Ferrante", "Achterberg", "Quillon", "Dunmore", "Esterhazy", "Fairweather", "Gallowglass", "Hollingrake",
            "Ivanescu", "Jessop", "Kettleby", "Larchmont", "Morrisey", "Nakashima", "Oyelaran", "Pemberton", "Quaresma",
            "Ravensworth", "Szabo", "Tamberlane", "Underhill", "Vasquez-Orr", "Wexley", "Yardley", "Zielinski",
            "Abernethy", "Blackwood", "Coriander", "Drummond", "Eckhart", "Fenwright", "Grisewood", "Hartigan",
            "Inchbald", "Jardine", "Kowalczyk", "Lockhart", "Mallory", "Northcott", "Ollerton", "Pritchard", "Rennick",
            "Sandoval", "Trelawney", "Ulverston", "Vellacott", "Winterbourne", "Ashdown", "Bellweather", "Cartwright",
            "Delacourt", "Edgerton"]
REGIONS = {"North": ["Pell Harbor", "Ashford Ridge"], "South": ["Sorrel Bay", "Tamsin Falls"],
           "East": ["Corwen Point", "Ivybridge Hollow"], "West": ["Marrow Creek", "Delling Mesa"],
           "Central": ["Oakhurst Plains", "Brindle Junction"]}
STREETS = ["Juniper Lane", "Kestrel Way", "Alder Court", "Fenwick Road", "Marigold Street", "Quarry Hill Road",
           "Larch Avenue", "Tolliver Drive", "Wren Hollow", "Pinecrest Terrace", "Baylis Street", "Copperleaf Row"]
VIN_CH = "ABCDEFGHJKLMNPRSTUVWXYZ0123456789"
INTAKE = ["Priya (FNOL intake)", "Desmond from the claims desk", "Lucia, intake team", "Oren (intake lead)",
          "Calla from customer care"]

DESCR = {
    ("property", "fire"): ["Kitchen fire started at the stove and spread to the cabinets; smoke damage through the ground floor.",
                           "Dryer fire in the laundry room; wall charred and smoke through the hallway."],
    ("property", "wind"): ["Strong winds tore shingles off the roof and brought down a section of fence.",
                           "Windstorm ripped siding off the north wall and bent the gutters."],
    ("property", "hail"): ["Hailstorm cracked roof shingles and two skylights and dented the gutters.",
                           "Large hail damaged the roof and broke the greenhouse panels."],
    ("property", "theft"): ["Break-in through the back door; laptop, jewelry and a bicycle were taken.",
                            "Garage was broken into overnight; power tools and a generator were stolen."],
    ("property", "burst_pipe"): ["A pipe burst inside the upstairs bathroom wall overnight and the basement flooded with water from it; drywall and flooring ruined.",
                                 "Supply line to the washing machine split; the laundry room and hallway flooded before we shut the water off."],
    ("property", "vandalism"): ["Someone spray-painted the garage door and smashed two front windows.",
                                "Vandals broke the porch railing and slashed the screen doors."],
    ("property", "sewer_backup"): ["Sewage backed up through the basement floor drain during heavy rain.",
                                   "Drain in the lower level backed up; sewage across the finished basement."],
    ("property", "earthquake"): ["Earthquake cracked the foundation and toppled the chimney.",
                                 "Tremor shifted the house; long cracks in the foundation and plaster."],
    ("property", "flood"): ["The creek behind the house overflowed its banks and surface water came into the ground floor.",
                            "River rose after three days of rain and water came in under the doors."],
    ("property", "wear_and_tear"): ["Roof has been leaking slowly for months; shingles are worn out and the decking is rotted.",
                                    "Old water heater rusted through and the floor under it has been soft for a while."],
    ("property", "mold"): ["Found mold behind the bathroom vanity and along the baseboards.",
                           "Black mold spreading across the basement walls."],
    ("auto", "collision"): ["Rear-ended at a red light; trunk and bumper crushed.",
                            "Slid on wet pavement into a guardrail; front end and headlights damaged."],
    ("auto", "hail"): ["Parked outside during a hailstorm; hood and roof covered in dents.",
                       "Hail cracked the windshield and dented every panel."],
    ("auto", "vandalism"): ["Car keyed along both sides and both side mirrors smashed.",
                            "Tires slashed and rear window broken in the apartment lot."],
    ("auto", "glass"): ["Rock from a gravel truck cracked the windshield.",
                        "Windshield cracked across the driver's side after a stone strike."],
    ("auto", "theft"): ["Vehicle stolen from the driveway overnight; not recovered.",
                        "Car taken from the station parking garage; police report filed."],
    ("auto", "flood"): ["Car was parked in a low lot that took on water from the river; water reached the dashboard.",
                        "Flash flood on the underpass; engine stalled and the cabin filled with water."],
    ("auto", "mechanical"): ["Engine seized on the highway; the mechanic says the timing belt failed.",
                             "Transmission failed while driving; shop says internal gears are worn out."],
}
COVERED = {"property": ["fire", "wind", "hail", "theft", "burst_pipe", "vandalism"],
           "auto": ["collision", "hail", "vandalism", "glass", "theft"]}
EXCLUDED = {"property": ["flood", "wear_and_tear", "mold", "earthquake", "sewer_backup"],
            "auto": ["mechanical", "commercial"]}


def iso(x: date) -> str:
    return x.isoformat()


def years_before(x: date, n: int) -> date:
    try:
        return x.replace(year=x.year - n)
    except ValueError:
        return x.replace(year=x.year - n, day=28)


def plus_year(x: date) -> date:
    try:
        return x.replace(year=x.year + 1)
    except ValueError:
        return x.replace(year=x.year + 1, day=28)


class Builder:
    def __init__(self, rng: random.Random, diff: str):
        self.rng, self.diff = rng, diff
        self.surnames = rng.sample(SURNAMES, len(SURNAMES))
        self.used: set = set()
        self.addresses: set = set()
        self.data = {"claims": {}, "policyholders": {}, "policies": {}, "history": {}, "roster": []}

    # --- ids and names --------------------------------------------------------------------------------------------
    def uid(self, fmt, lo, hi):
        while True:
            v = fmt.format(self.rng.randint(lo, hi))
            if v not in self.used:
                self.used.add(v)
                return v

    def surname(self):
        while True:
            s = self.surnames.pop()
            if s not in self.used:
                self.used.add(s)
                return s

    def address(self, region):
        while True:
            a = f"{self.rng.randint(2, 980)} {self.rng.choice(STREETS)}, {self.rng.choice(REGIONS[region])}"
            if a not in self.addresses:
                self.addresses.add(a)
                return a

    def vin(self):
        return "".join(self.rng.choice(VIN_CH) for _ in range(17))

    def holder(self, region=None):
        region = region or self.rng.choice(list(REGIONS))
        h = {"policyholder_id": self.uid("PH-{:05d}", 10000, 99999),
             "name": f"{self.rng.choice(FIRST)} {self.surname()}", "mailing_address": self.address(region)}
        self.data["policyholders"][h["policyholder_id"]] = h
        self.data["history"].setdefault(h["policyholder_id"], [])
        h["_region"] = region
        return h

    # --- policies ---------------------------------------------------------------------------------------------------
    def policy(self, h, line, item, term_start, inception, endorsements=(), pct=None, sublimits=None, base=None,
               deductible=None, limit=None):
        r = self.rng
        if line == "property":
            limit = limit or r.randrange(250, 610, 10) * 1000
            ded = deductible or r.choice([500, 1000, 2500])
            subl = sublimits if sublimits is not None else ({"theft": r.choice([5000, 7500, 10000])} if r.random() < .6 else {})
            excl = list(logic.PROPERTY_EXCLUSIONS)
        else:
            limit = limit or r.randrange(15, 61) * 1000
            ded = deductible or r.choice([250, 500, 1000])
            subl = sublimits if sublimits is not None else ({"glass": r.choice([1500, 2000])} if r.random() < .4 else {})
            excl = list(logic.AUTO_EXCLUSIONS)
        base = base or self.uid("{:06d}", 100000, 999999)
        num = f"{'HO' if line == 'property' else 'AU'}-{base}-{term_start.year % 100:02d}"
        p = {"policy_number": num, "policyholder_id": h["policyholder_id"], "named_insured": h["name"],
             "mailing_address": h["mailing_address"], "line": line, "insured_item": item,
             "inception_date": iso(inception), "term_start": iso(term_start), "term_end": iso(plus_year(term_start)),
             "limit": limit, "deductible": ded, "sublimits": subl, "exclusions": excl,
             "endorsements": sorted(endorsements, key=lambda e: e["effective_date"]), "_base": base}
        if line == "property" and (pct or (pct is None and r.random() < .3)):
            p["wind_hail_deductible_pct"] = pct or r.choice([1, 2])
        self.data["policies"][num] = p
        return p

    def endorsement(self, code, eff, p_line, limit=None):
        r = self.rng
        if code == "LIM-UP":
            old = limit - (r.randrange(5, 15) * 10000 if p_line == "property" else r.randrange(2, 8) * 1000)
            what = "Dwelling" if p_line == "property" else "Physical damage"
            desc = f"{what} limit increased from ${old:,} to ${limit:,}"
        else:
            desc = {"WB-1": "Water backup coverage added", "EQ-3": "Earthquake coverage added",
                    "RS-2": "Ride-hail and delivery use coverage added", "ADDR": "Mailing address updated",
                    "LIEN": "Lienholder added: Bexley Street Credit Union", "PAY": "Payment plan changed to monthly",
                    "DED-UP": "Deductible raised (customer request)", "DRV-RM": "Driver removed from policy"}[code]
        return {"code": code, "effective_date": iso(eff), "description": desc}

    # --- one claim ------------------------------------------------------------------------------------------------
    def claim(self, h, kind, rules, feats, line=None):
        """kind: route, docs, deny_period, deny_excl, deny_ded. Returns claim id."""
        r = self.rng
        loss = TODAY - timedelta(days=r.randint(2, 28))
        line = line or r.choice(["property", "auto"])
        if {"pct_ded", "sublimit", "contractor_edge"} & feats:
            line = "property"
        region = h["_region"]
        item = h["mailing_address"] if line == "property" else self.vin()
        peril, use, bi = None, "personal", False
        endorsements, lift = [], None
        fraud = r.randint(3, 55)
        if "fraud_siu" in feats:
            fraud = 70 if "edge" in feats else r.randint(71, 94)
        elif "fraud_69" in feats:
            fraud = 69

        # peril
        if kind == "deny_excl":
            excl = r.choice(EXCLUDED[line])
            if line == "auto" and excl == "commercial":
                peril, use = "collision", r.choice(["rideshare", "delivery"])
            else:
                peril = excl
            lift = {"earthquake": "EQ-3", "sewer_backup": "WB-1"}.get(peril) or ("RS-2" if use != "personal" else None)
        else:
            perils = list(COVERED[line])
            if "pct_ded" in feats or (kind == "deny_ded" and "pct_ded" in feats):
                perils = ["wind", "hail"]
            if "sublimit" in feats:
                perils = ["theft"]
            if kind == "deny_ded" and "pct_ded" not in feats:
                perils = ["glass", "vandalism", "hail"] if line == "auto" else ["wind", "hail", "vandalism", "theft"]
            if "tricky" in feats:
                perils = (["burst_pipe", "sewer_backup", "earthquake"] if line == "property" else ["flood", "rideshare"])
            peril = r.choice(perils)
            if peril == "rideshare":
                peril, use, lift = "collision", "rideshare", "RS-2"
            if peril in ("sewer_backup", "earthquake"):
                lift = {"sewer_backup": "WB-1", "earthquake": "EQ-3"}[peril]
            if feats & {"fast"} and peril == "fire":
                peril = "wind" if line == "property" else peril
            if "injury" in feats and line == "auto":
                peril, bi = "collision", True

        # policy term
        inception = None
        if "h1" in rules and kind == "route":
            k = r.randint(0, 25)
            if r.random() < .45 and not lift:
                term_start = inception = loss - timedelta(days=k)
                h1_mode = "new"
            else:
                term_start = loss - timedelta(days=r.randint(90, 330))
                inception = years_before(term_start, r.randint(0, 4))
                h1_mode = "endorse"
                h1_eff = loss - timedelta(days=k)
        else:
            h1_mode = None
            if kind == "deny_period":
                mode = feats_mode = r.choice(["before", "expired", "expired", "wrong_item"])
                if "edge" in feats:
                    mode = r.choice(["before1", "on_end"])
            if kind == "deny_period" and mode in ("before", "before1"):
                term_start = loss + timedelta(days=1 if mode == "before1" else r.randint(2, 9))
                inception = term_start
            elif kind == "deny_period" and mode in ("expired", "on_end"):
                term_end = loss - timedelta(days=0 if mode == "on_end" else r.randint(1, 40))
                term_start = years_before(term_end, 1)
                inception = years_before(term_start, r.randint(0, 3))
            elif "renewal_recent" in feats:
                term_start = loss - timedelta(days=r.randint(0, 25))
                inception = years_before(term_start, r.randint(1, 5))
            else:
                term_start = loss - timedelta(days=r.randint(95, 330))
                inception = years_before(term_start, r.randint(0, 5))

        # endorsements
        lim_val = None
        if line == "property":
            lim_val = r.randrange(250, 610, 10) * 1000
        else:
            lim_val = r.randrange(15, 61) * 1000
        if lift:
            if kind == "deny_excl":
                if "lift_late" in feats:   # endorsement added after the loss: does not count
                    endorsements.append(self.endorsement(lift, loss + timedelta(days=r.randint(1, 6)), line))
            else:
                if h1_mode == "endorse" and r.random() < .6:
                    endorsements.append(self.endorsement(lift, h1_eff, line))
                    h1_mode = "done"
                else:
                    eff = max(inception, loss - timedelta(days=r.randint(120, 600)))
                    endorsements.append(self.endorsement(lift, eff, line))
        if h1_mode == "endorse":
            endorsements.append(self.endorsement("LIM-UP", h1_eff, line, limit=lim_val))
        if "noncov_recent" in feats:
            code = r.choice(["ADDR", "LIEN", "PAY", "DRV-RM"] if line == "auto" else ["ADDR", "PAY", "LIEN"])
            endorsements.append(self.endorsement(code, max(term_start, loss - timedelta(days=r.randint(1, 25))), line))
        if "old_increase" in feats:
            eff = max(inception, loss - timedelta(days=r.randint(120, 400)))
            if (loss - eff).days >= 120:
                endorsements.append(self.endorsement("LIM-UP", eff, line, limit=lim_val))
        # guard: an endorsement must not predate inception
        for e in endorsements:
            if e["effective_date"] < iso(inception):
                e["effective_date"] = iso(inception)

        pct = None
        if line == "property" and "pct_ded" in feats:
            pct = r.choice([1, 2])
        sub = None
        if "sublimit" in feats:
            sub = {"theft": r.choice([5000, 7500])}
        p = self.policy(h, line, item, term_start, inception, endorsements, pct=pct, sublimits=sub, limit=lim_val)
        if not pct and peril in ("wind", "hail") and line == "property" and "pct_ded" not in feats and kind != "deny_ded":
            p.pop("wind_hail_deductible_pct", None) if r.random() < .5 else None

        ded = logic.deductible(p, {"peril": peril, "line": line})
        alim = p["sublimits"].get(peril, p["limit"])

        # amount
        if kind == "deny_ded":
            if "edge" in feats:
                amount = ded
            elif "pct_ded" in feats and ded - p["deductible"] > 200:
                amount = r.randint(p["deductible"] + 50, ded - 50)
            else:
                amount = r.randint(max(50, ded // 3), ded - 10)
        elif "sublimit" in feats:
            amount = alim + r.randint(400, 6000)
        elif "over_limit" in feats and peril not in p["sublimits"]:
            amount = p["limit"] + r.randrange(1000, 20000, 50)
        elif "contractor_edge" in feats:
            amount = 10000
        else:
            q = "fast" if ("fast" in feats or peril == "glass") else r.choice(["fast", "fast", "std", "std", "cpx"] if not bi else ["std"])
            if peril in p["sublimits"]:
                q = "fast"
            if q == "cpx" and (alim - ded) // 10 < 2600:
                q = "std"
            if q == "fast":
                net = 5000 if "edge" in feats else r.randint(30, 500) * 10 + r.choice([0, 0, 5, 7])
                net = min(net, alim - ded)
            elif q == "std":
                net = r.choice([25000, 5001]) if "edge" in feats else r.randint(510, 2500) * 10 + r.choice([0, 5, 3])
            else:
                net = r.randint(2510, min(9000, (alim - ded) // 10)) * 10 + r.choice([0, 5])
            amount = net + ded
            if peril == "glass" and amount > alim:
                amount = alim
        amount = max(amount, 1)

        # attachments
        tmp = {"line": line, "peril": peril, "bodily_injury": bi, "amount_claimed": amount}
        req = sorted(logic.required_docs(tmp))
        cid = self.uid("CLM-{:05d}", 30000, 89999)
        atts = [{"type": t, "filename": f"{cid.lower()}_{t}_{i + 1}.pdf" if t != "photos" else f"{cid.lower()}_photos.zip",
                 "status": "received"} for i, t in enumerate(req)]
        if kind == "docs":
            n_miss = 2 if (self.diff == "hard" and len(req) > 2 and r.random() < .5) else 1
            miss = r.sample(req, n_miss)
            for a in atts:
                if a["type"] in miss:
                    if r.random() < .45 and self.diff != "easy":
                        a["status"] = r.choice(["rejected: unreadable scan", "rejected: belongs to another claim"])
                    else:
                        a["status"] = "drop"
            atts = [a for a in atts if a["status"] != "drop"]
        if kind in ("deny_excl", "deny_period", "deny_ded") and r.random() < .35:
            atts = atts[: max(1, len(atts) - 1)]   # incomplete paperwork does not matter for a denial
        if "rejected_dup" in feats and atts:
            a = r.choice(atts)
            atts.append({"type": a["type"], "filename": a["filename"].replace(".", "_old."), "status": "rejected: unreadable scan"})
        if r.random() < .4:
            atts.append({"type": r.choice(["receipt", "witness_statement", "invoice"]), "filename": f"{cid.lower()}_extra.pdf",
                         "status": "received"})
        r.shuffle(atts)

        claim_item = item
        if kind == "deny_period" and mode == "wrong_item":
            # the claim's vehicle/address is not on any policy; a near-identical one is
            if line == "auto":
                claim_item = item[:13] + "".join(r.choice(VIN_CH) for _ in range(4))
            else:
                num, rest = item.split(" ", 1)
                claim_item = f"{int(num) + r.choice([1, 10, 100])} {rest}"
            p["term_start"] = iso(loss - timedelta(days=r.randint(95, 300)))
            p["term_end"] = iso(plus_year(date.fromisoformat(p["term_start"])))
        if kind == "deny_period" and mode in ("expired", "on_end") and r.random() < .5:
            pass

        descr = r.choice(DESCR[(line, peril)])
        if use != "personal":
            descr = (f"Collision while driving for a {'ride-hail app with a passenger aboard' if use == 'rideshare' else 'food delivery app'}; "
                     + r.choice(DESCR[("auto", "collision")]).lower())
        if bi:
            descr += " The other driver was taken to the hospital with a neck injury."
        reported = loss + timedelta(days=r.randint(0, min(6, (TODAY - loss).days)))
        c = {"claim_id": cid, "policyholder_id": h["policyholder_id"], "claimant_name": h["name"], "line": line,
             "insured_item": claim_item, "region": region, "peril": peril, "date_of_loss": iso(loss),
             "date_reported": iso(reported), "description": descr, "amount_claimed": amount, "bodily_injury": bi,
             "fraud_score": fraud, "attachments": atts}
        if line == "auto":
            c["vehicle_use"] = use
        self.data["claims"][cid] = c

        # distractor policies for the same person
        if "other_line" in feats or self.diff != "easy":
            oline = "auto" if line == "property" else "property"
            oitem = h["mailing_address"] if oline == "property" else self.vin()
            if not (oline == "property" and line == "property"):
                ts = loss - timedelta(days=r.randint(30, 300))
                self.policy(h, oline, oitem, ts, years_before(ts, r.randint(0, 3)))
        if "second_item" in feats:
            if line == "auto":
                oitem = item[:12] + "".join(r.choice(VIN_CH) for _ in range(5))
            else:
                num, rest = item.split(" ", 1)
                oitem = f"{int(num) + r.choice([2, 4, 20])} {rest}"
                if r.random() < .5 or oitem in self.addresses:
                    oitem = self.address(region)
                self.addresses.add(oitem)
            ts = loss - timedelta(days=r.randint(40, 300))
            self.policy(h, line, oitem, ts, years_before(ts, r.randint(0, 3)))
        if "renewal_recent" in feats or "prior_term" in feats or (kind == "deny_period" and mode in ("expired", "on_end")):
            prev_start = years_before(date.fromisoformat(p["term_start"]), 1)
            if date.fromisoformat(p["inception_date"]) <= prev_start:
                q = self.policy(h, line, item, prev_start, date.fromisoformat(p["inception_date"]), base=p["_base"],
                                limit=p["limit"], deductible=p["deductible"])
                q["endorsements"] = [e for e in p["endorsements"] if e["effective_date"] < q["term_end"]]

        # history
        hist = self.data["history"][h["policyholder_id"]]
        for _ in range(r.randint(0, 2)):
            ld = loss - timedelta(days=r.randint(200, 1500))
            pr = r.choice(COVERED[line])
            hist.append(self.hist_row(h, line, item, pr, ld))
        if "h2" in rules:
            hist.append(self.hist_row(h, line, item, peril, loss, status=r.choice(["open", "closed_paid"]),
                                      descr=r.choice(["Reported by phone: ", "Customer called in: ", "Web form: "]) + descr[0].lower() + descr[1:]))
        if "near_dup" in feats:
            # a look-alike prior claim that is clearly a different loss: same peril months earlier, or the same date
            # with an unrelated peril
            if r.random() < .5:
                hist.append(self.hist_row(h, line, item, peril, loss - timedelta(days=r.randint(60, 150))))
            else:
                unrelated = {"theft": ["glass", "hail", "wind"], "glass": ["theft", "vandalism"],
                             "hail": ["theft"], "wind": ["theft"], "collision": ["theft", "glass"],
                             "vandalism": ["glass", "wind"], "fire": ["theft"], "burst_pipe": ["theft", "glass"],
                             "flood": ["theft"], "sewer_backup": ["theft"], "earthquake": ["theft"]}.get(peril, ["theft"])
                unrelated = [x for x in unrelated if x in COVERED[line]] or ["theft"]
                hist.append(self.hist_row(h, line, item, r.choice(unrelated), loss))
        hist.sort(key=lambda x: x["date_of_loss"])
        return cid

    def hist_row(self, h, line, item, peril, ld, status=None, descr=None):
        r = self.rng
        status = status or r.choice(["closed_paid", "closed_paid", "closed_denied"])
        pols = [p for p in self.data["policies"].values() if p["insured_item"] == item]
        return {"claim_id": self.uid("CLM-{:05d}", 10000, 29999), "policy_number": pols[0]["policy_number"] if pols else None,
                "line": line, "insured_item": item, "peril": peril, "date_of_loss": iso(ld),
                "description": descr or r.choice(DESCR[(line, peril)]), "status": status,
                "amount_paid": r.randrange(300, 9000, 10) if status == "closed_paid" else 0}

    # --- roster -----------------------------------------------------------------------------------------------------
    def adjuster(self, team, lines, regions, load, cap=None, status="active", name=None, address=None):
        r = self.rng
        a = {"adjuster_id": self.uid("ADJ-{:03d}", 100, 899), "name": name or f"{r.choice(FIRST)} {self.surname()}",
             "team": team, "lines": lines, "regions": regions, "status": status, "open_claims": load,
             "max_open_claims": cap if cap is not None else r.randint(max(load + 4, 30), 45),
             "address_on_file": address or self.address(r.choice(list(REGIONS)))}
        self.data["roster"].append(a)
        return a

    def roster(self, routed, roster_feats):
        """routed: list of (claim, queue, rules)."""
        r = self.rng
        pools = {}
        keyof = lambda c, q: (logic.TEAM_FOR_QUEUE[q], None if q == "siu_review" else c["line"],
                              None if q == "fast_track" else c["region"])
        counts = {}
        for c, q, _ in routed:
            counts[keyof(c, q)] = counts.get(keyof(c, q), 0) + 1
        for c, q, rules in routed:
            team = logic.TEAM_FOR_QUEUE[q]
            line, region = c["line"], c["region"]
            other_line = "auto" if line == "property" else "property"
            regions_of = lambda: [region] if r.random() < .6 else sorted([region, r.choice([x for x in REGIONS if x != region])])
            lines_of = lambda: [line] if r.random() < .6 else ["auto", "property"]
            mk_lines = lambda: (["auto", "property"] if team == "siu" else lines_of())
            mk_regions = lambda: (["All"] if team == "fast_track" else regions_of())
            key = (team, None if team == "siu" else line, None if team == "fast_track" else region)
            if key not in pools:
                loads = r.sample(range(6, 30), r.randint(2, 3))
                if counts[key] > 1:      # two claims compete: two equally loaded adjusters, so the order matters
                    loads = [min(loads)] * 2 + [max(loads) + 2]
                pools[key] = [self.adjuster(team, mk_lines(), mk_regions(), L) for L in loads]
            base = min(a["open_claims"] for a in pools[key])
            low = lambda: max(0, base - r.randint(1, 4))
            holder = self.data["policyholders"][c["policyholder_id"]]
            if "h3" in rules:
                if r.random() < .6:
                    nm = f"{r.choice(FIRST)} {holder['name'].split()[-1]}"
                    self.adjuster(team, mk_lines(), mk_regions(), low(), name=nm)
                else:
                    self.adjuster(team, mk_lines(), mk_regions(), low(), address=holder["mailing_address"])
            for f in sorted(roster_feats):  # sorted: set order varies by process (fixed Oct 20)
                if f == "on_leave":
                    self.adjuster(team, mk_lines(), mk_regions(), low(),
                                  status=f"on_leave (returns {iso(TODAY + timedelta(days=r.randint(5, 40)))})")
                elif f == "capacity":
                    L = low()
                    self.adjuster(team, mk_lines(), mk_regions(), L, cap=L)
                elif f == "wrong_region" and team != "fast_track":
                    self.adjuster(team, mk_lines(), [r.choice([x for x in REGIONS if x != region])], low())
                elif f == "wrong_line" and team != "siu":
                    self.adjuster(team, [other_line], mk_regions(), low())
                elif f == "wrong_team":
                    other = r.choice([t for t in ("fast_track", "field", "complex", "siu") if t != team])
                    self.adjuster(other, [line] if other != "siu" else ["auto", "property"],
                                  ["All"] if other == "fast_track" else [region], low())
                elif f == "tie":
                    self.adjuster(team, mk_lines(), mk_regions(), base)
                elif f == "same_first_name" and "h3" not in rules:
                    # shares only the policyholder's first name and town: not a conflict
                    self.adjuster(team, mk_lines(), mk_regions(), low(), name=f"{holder['name'].split()[0]} {self.surname()}")
        # filler adjusters on other teams
        for _ in range(r.randint(2, 4)):
            team = r.choice(["fast_track", "field", "complex", "siu"])
            self.adjuster(team, ["auto", "property"] if team == "siu" else [r.choice(["auto", "property"])],
                          ["All"] if team == "fast_track" else [r.choice(list(REGIONS))], r.randint(8, 34))
        self.data["roster"].sort(key=lambda a: a["name"].split()[-1])


# --- task assembly ------------------------------------------------------------------------------------------------
CLAIM_FEATS = {
    "easy": [set(), {"other_line"}, {"fast"}, set()],
    "medium": ["rejected_dup", "pct_ded", "sublimit", "second_item", "renewal_recent", "noncov_recent", "old_increase",
               "near_dup", "prior_term", "tricky", "injury", "fraud_siu", "fast"],
    "hard": ["edge", "over_limit", "contractor_edge", "lift_late", "second_item", "renewal_recent", "noncov_recent",
             "near_dup", "tricky", "fraud_69", "fraud_siu", "rejected_dup", "prior_term", "injury", "old_increase"],
}
ROSTER_FEATS = {"easy": ["wrong_region", "wrong_team"],
                "medium": ["on_leave", "capacity", "wrong_region", "wrong_line", "wrong_team", "tie"],
                "hard": ["on_leave", "capacity", "wrong_region", "wrong_line", "tie", "same_first_name", "wrong_team"]}
H_FEATS_OK = {"near_dup", "renewal_recent", "noncov_recent", "old_increase", "fraud_siu"}  # not combined with h1/h2


def pick_kind(r, rules):
    if rules:
        return "route"
    return r.choices(["route", "deny_period", "deny_excl", "deny_ded", "docs"], [40, 13, 15, 14, 18])[0]


def pick_feats(r, diff, kind, rules):
    if diff == "easy":
        f = set(r.choice(CLAIM_FEATS["easy"]))
    else:
        n = 1 if diff == "medium" else r.randint(2, 3)
        f = set(r.sample(CLAIM_FEATS[diff], n))
    if rules & {"h1", "h2"}:
        f -= {"fraud_siu", "renewal_recent", "old_increase", "noncov_recent"} if "h1" in rules else {"fraud_siu"}
        if "h2" in rules:
            f -= {"near_dup"}
            if r.random() < .7:
                f.add("fast")
    if kind != "route" and kind != "docs":
        f -= {"fraud_siu", "fraud_69", "contractor_edge", "over_limit", "sublimit", "injury", "tricky"}
        if kind == "deny_ded":
            f -= {"fast"}
            if r.random() < .4:
                f.add("pct_ded")
    if kind == "docs":
        f -= {"contractor_edge", "fraud_siu"}
    if "contractor_edge" in f:
        f -= {"pct_ded", "sublimit", "over_limit", "injury", "tricky", "edge"}
    if "sublimit" in f:
        f -= {"pct_ded", "tricky", "injury", "over_limit"}
    if "pct_ded" in f:
        f -= {"tricky", "injury"}
    if "injury" in f:
        f -= {"tricky", "fast"}
    return f


def triggers_of(gold):
    t = set()
    for o in gold:
        if o["action"] == "route":
            if o["flags"]["h1"]:
                t.add("siu_recent_coverage")
            if o["flags"]["h2"]:
                t.add("duplicate_loss")
            if o["h3"]:
                t.add("adjuster_conflict")
    return t


ATTEMPTS = [0]
RULE_ID = {"h1": "siu_recent_coverage", "h2": "duplicate_loss", "h3": "adjuster_conflict"}


def make_task(r, idx, diff, rules):
    for _attempt in range(400):
        ATTEMPTS[0] += 1
        b = Builder(r, diff)
        n = 2 if (diff == "hard" and r.random() < .6) or (diff == "medium" and r.random() < .15) else 1
        which = r.randrange(n)
        cids, plan = [], []
        shared = n == 2 and r.random() < .5          # same region and line: the two claims may compete for adjusters
        for j in range(n):
            crules = rules if j == which else set()
            kind = pick_kind(r, crules)
            if shared and kind != "route" and r.random() < .7:
                kind = "route"
            feats = pick_feats(r, diff, kind, crules)
            if shared and kind == "route" and not crules and not (feats & {"injury", "over_limit", "contractor_edge"}):
                feats.add("fast")
            h = b.holder(region=b.data["claims"][cids[0]]["region"] if shared and j else None)
            cids.append(b.claim(h, kind, crules, feats,
                                line=b.data["claims"][cids[0]]["line"] if shared and j and not ({"pct_ded", "sublimit", "contractor_edge"} & feats) else None))
            plan.append((kind, crules))
        # queues before roster
        routed = []
        bad = False
        for cid, (kind, crules) in zip(cids, plan):
            o = logic.outcome(b.data, cid)
            want = {"route": "route", "docs": "request_documents"}.get(kind, "deny")
            if o["action"] != want:
                bad = True
                break
            if o["action"] == "route":
                routed.append((b.data["claims"][cid], o["queue"], crules))
        if bad:
            continue
        rf = set(r.sample(ROSTER_FEATS[diff], 1 if diff == "easy" else (2 if diff == "medium" else 3)))
        b.roster(routed, rf)
        try:
            gold = logic.solve(b.data, cids)
            plain = logic.solve(b.data, cids, hidden=False)
        except ValueError:
            continue
        want_t = {RULE_ID[x] for x in rules}
        if triggers_of(gold) != want_t:
            continue
        # every hidden rule must change the written-policy-only answer
        if rules and all((g.get("queue"), g.get("adjuster_id")) == (p.get("queue"), p.get("adjuster_id"))
                         for g, p in zip(gold, plain)):
            continue
        if any(o["action"] == "route" and o["queue"] == "siu_review" and not (o["flags"]["h1"] or o["flags"]["h2"])
               and b.data["claims"][o["claim_id"]]["fraud_score"] < 70 for o in gold):
            continue
        for p in b.data["policies"].values():
            p.pop("_base", None)
        for h in b.data["policyholders"].values():
            h.pop("_region", None)
        return cids, b.data, gold
    raise RuntimeError(f"could not build task {idx}")


REQ_ONE = ["New FNOL claim {c} needs triage. Please handle it under CL-7.",
           "Hi, it's {who}. Claim {c} just came in through the portal; can you triage it?",
           "Please triage claim {c} for {n}.",
           "{who} here. Could you take {c}? It came in this morning.",
           "Triage request: {c}. Thanks!"]
REQ_TWO = ["Two new claims to triage, in this order: {c} for {n}, then {c2} for {n2}.",
           "Hi, it's {who}. Please triage {c} and then {c2} (in that order).",
           "Batch from the overnight queue: {c}, {c2}. Handle them in the order listed, please."]
PRESSURE = [" The customer has called twice already and asked us to fast-track it.",
            " The agent says this is a long-time customer, so please keep it moving.",
            " Branch wants this one closed out today if possible."]


def build_all():
    r = random.Random(SEED)
    plan = ([{"h1"}] * 15 + [{"h2"}] * 15 + [{"h3"}] * 15 + [{"h1", "h3"}] * 2 + [{"h2", "h3"}] * 2
            + [{"h1", "h2"}] * 2 + [{"h1", "h2", "h3"}])
    plan += [set()] * (N_TASKS - len(plan))
    r.shuffle(plan)
    diffs = (["easy"] * 50 + ["medium"] * 50 + ["hard"] * 50)
    r.shuffle(diffs)
    tasks, datas = [], {}
    for i, (diff, rules) in enumerate(zip(diffs, plan)):
        cids, data, gold = make_task(r, i, diff, set(rules))
        hs = [data["claims"][c]["claimant_name"] for c in cids]
        if len(cids) == 1:
            req = r.choice(REQ_ONE).format(c=cids[0], n=hs[0], who=r.choice(INTAKE))
        else:
            req = r.choice(REQ_TWO).format(c=cids[0], c2=cids[1], n=hs[0], n2=hs[1], who=r.choice(INTAKE))
        if diff != "easy" and r.random() < .15:
            req += r.choice(PRESSURE)
        tid = f"clm-{i + 1:03d}"
        g = [{k: v for k, v in o.items() if k in ("claim_id", "action", "reason_code", "documents", "queue",
                                                    "adjuster_id", "reserve")} for o in gold]
        tasks.append({"id": tid, "request": req, "difficulty": diff, "triggers": sorted(triggers_of(gold)),
                      "gold": {"claim_ids": cids, "claims": g},
                      "user_answer": "I don't have anything beyond the claim number; everything is in the claims system."})
        datas[tid] = data
    return tasks, datas
