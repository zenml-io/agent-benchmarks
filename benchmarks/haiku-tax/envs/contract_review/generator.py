"""Deterministic generator for the contract review environment.

Every contract is built from structured term specs; clause text is rendered from those specs, and the gold (flags,
redlines, final action) is computed from the same specs, so ground truth holds by construction.
"""
from __future__ import annotations

import datetime as dt
import random

SEED = 20261019
N_TASKS = 150
QUILLMERE = "Quillmere Analytics, Inc."

# ------------------------------------------------------------------------------------------------ number formatting
_ONES = ("zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen "
         "seventeen eighteen nineteen").split()
_TENS = "_ _ twenty thirty forty fifty sixty seventy eighty ninety".split()


def words(n: int) -> str:
    if n < 20:
        return _ONES[n]
    if n < 100:
        return _TENS[n // 10] + ("" if n % 10 == 0 else "-" + _ONES[n % 10])
    if n < 1000:
        return _ONES[n // 100] + " hundred" + ("" if n % 100 == 0 else " " + words(n % 100))
    if n < 1_000_000:
        return words(n // 1000) + " thousand" + ("" if n % 1000 == 0 else " " + words(n % 1000))
    return words(n // 1_000_000) + " million" + ("" if n % 1_000_000 == 0 else " " + words(n % 1_000_000))


def fmt(n: int, st: str) -> str:
    if st == "digits":
        return str(n)
    if st == "both":
        return f"{words(n)} ({n})"
    return words(n)


def days(n: int, st: str, unit: str = "day") -> str:
    return f"{fmt(n, st)} {unit}{'' if n == 1 else 's'}"


def months(n: int, st: str) -> str:
    return days(n, st, "month")


def money(a: int, st: str) -> str:
    d = f"${a:,}"
    if st == "digits":
        return d
    if st == "both":
        return f"{words(a)} US dollars ({d})"
    return f"{words(a)} US dollars"


def add_months(d: dt.date, m: int) -> dt.date:
    y, mo = divmod(d.month - 1 + m, 12)
    y, mo = d.year + y, mo + 1
    for day in (d.day, 30, 29, 28):
        try:
            return dt.date(y, mo, day)
        except ValueError:
            continue
    raise ValueError(d)


# ------------------------------------------------------------------------------------------------ playbook
JUR_TEXT = {
    "Delaware": "the State of Delaware", "New York": "the State of New York",
    "California": "the State of California", "Illinois": "the State of Illinois", "England and Wales": "England and Wales",
    "Texas": "the State of Texas", "Nevada": "the State of Nevada", "Cayman Islands": "the Cayman Islands",
    "Singapore": "the Republic of Singapore", "Florida": "the State of Florida",
}
JUR_LEVEL = {"Delaware": "pref", "New York": "pref", "California": "fallback", "Illinois": "fallback",
             "England and Wales": "fallback", "Texas": "dev", "Nevada": "dev", "Cayman Islands": "dev",
             "Singapore": "dev", "Florida": "dev"}
HQ_TEXT = {k: v[4:] if v.startswith("the ") else v for k, v in JUR_TEXT.items()}

PLAYBOOK = {
    "LIABILITY_CAP": {
        "preferred": "Each party's total liability is capped at no less than the fees paid or payable in the 12 months "
                     "before the claim.",
        "fallback": "Cap of no less than 6 months of fees.",
        "issue_codes": {"LIAB_UNCAPPED": "CRITICAL", "LIAB_CAP_LOW": "HIGH"},
        "notes": "Measure the cap in months of fees. Carve-outs for indemnification obligations, breach of "
                 "confidentiality, and gross negligence or willful misconduct are standard and acceptable.",
    },
    "INDEMNITY": {
        "preferred": "Mutual indemnity for third-party claims arising from a party's breach or IP infringement.",
        "fallback": "Indemnity given only by the counterparty to Quillmere, or a mutual indemnity limited to IP "
                    "infringement.",
        "issue_codes": {"INDEM_ONE_SIDED": "HIGH"},
        "notes": "Deviation: Quillmere indemnifies the counterparty and receives no indemnity in return.",
    },
    "AUTO_RENEWAL": {
        "preferred": "No automatic renewal, or automatic renewal for terms of at most 12 months with a non-renewal "
                     "notice period of at most 30 days.",
        "fallback": "Automatic renewal for terms of at most 12 months with a non-renewal notice period of at most "
                    "60 days.",
        "issue_codes": {"RENEWAL_TERMS": "MEDIUM"},
        "notes": "Deviation: renewal terms longer than 12 months, or a non-renewal notice period longer than 60 days.",
    },
    "TERMINATION_NOTICE": {
        "preferred": "Quillmere may terminate for convenience on at most 30 days' notice.",
        "fallback": "Quillmere may terminate for convenience on at most 90 days' notice.",
        "issue_codes": {"TERM_NOTICE_LONG": "MEDIUM"},
        "notes": "Deviation: notice longer than 90 days, or Quillmere has no right to terminate for convenience. "
                 "A right to terminate for convenience held only by Quillmere is acceptable.",
    },
    "GOVERNING_LAW": {
        "preferred": "Laws of the State of Delaware or the State of New York.",
        "fallback": "Laws of the State of California, the State of Illinois, or England and Wales.",
        "issue_codes": {"GOV_LAW_NONSTANDARD": "HIGH"},
        "notes": "Any other governing law is a deviation. The courts or venue chosen do not matter.",
    },
    "DATA_PROTECTION": {
        "preferred": "Personal data processed only on documented instructions; breach notification within 48 hours.",
        "fallback": "Breach notification within 72 hours.",
        "issue_codes": {"DPA_BREACH_NOTICE": "HIGH", "DPA_SECONDARY_USE": "CRITICAL"},
        "notes": "Deviations: breach notification period longer than 72 hours (a day or business day counts as 24 "
                 "hours); the counterparty may use Quillmere's personal data for its own purposes. Aggregated, "
                 "de-identified statistics are acceptable.",
    },
    "PAYMENT_TERMS": {
        "preferred": "Vendor contracts: Quillmere pays within 45 days or more. Customer contracts: customer pays "
                     "within 30 days or less.",
        "fallback": "Vendor contracts: 30 days or more. Customer contracts: 45 days or less.",
        "issue_codes": {"PAY_TERMS_SHORT": "MEDIUM", "PAY_TERMS_LONG": "MEDIUM"},
        "notes": "Vendor contract shorter than 30 days: PAY_TERMS_SHORT. Customer contract longer than 45 days: "
                 "PAY_TERMS_LONG.",
    },
}
SEVERITY = {c: s for p in PLAYBOOK.values() for c, s in p["issue_codes"].items()}
REASONS = ["CRITICAL_DEVIATION", "MULTIPLE_HIGH", "VALUE_THRESHOLD", "CONFLICTING_TERMS", "RENEWAL_DEADLINE",
           "SIGNATORY_AUTHORITY"]

HIDDEN_RULES = {
    "conflicting_terms": "If two clauses of the contract (for example the main body and the Order Form) state "
                         "different terms on the same matter, do not approve; escalate with CONFLICTING_TERMS (flag "
                         "whichever clause deviates as usual). This covers a clause making liability unlimited even "
                         "when another clause caps it.",
    "renewal_deadline": "Do not approve an auto-renewing contract whose first non-renewal notice deadline (end of the "
                        "Initial Term minus the notice period) has already passed or falls within 30 days of today; "
                        "escalate with RENEWAL_DEADLINE.",
    "signatory_authority": "Do not approve a contract whose counterparty signatory is not one of the authorized "
                           "signatories in the counterparty profile; escalate with SIGNATORY_AUTHORITY.",
}
HIDDEN_REASON = {"conflicting_terms": "CONFLICTING_TERMS", "renewal_deadline": "RENEWAL_DEADLINE",
                 "signatory_authority": "SIGNATORY_AUTHORITY"}

# ------------------------------------------------------------------------------------------------ names
PREFIXES = ["Larkspur", "Oakline", "Tamberlane", "Vossberg", "Quenwick", "Marrowby", "Ellisond", "Corvane",
            "Fennimore", "Saltreach", "Brindlecomb", "Hollowmere", "Ivelton", "Juniperra", "Kestrelby", "Lunewater",
            "Mossgrove", "Norrikan", "Ostrander", "Pellwick", "Rookhaven", "Sablemont", "Thistlecroft", "Umberly",
            "Varnholt", "Wrenfield", "Yarrowby", "Zephyrine", "Gallowtree", "Dovecrest"]
SUFFIX_PAIRS = [("Data Systems", "Data Services"), ("Freight Lines", "Freight Links"), ("Cloudworks", "Cloudwork"),
                ("Analytics Group", "Analytic Group"), ("Payroll Partners", "Payroll Partner"),
                ("Supply Co.", "Supply Corp."), ("Media Labs", "Media Lab"), ("Logistics", "Logistic Solutions"),
                ("Health Software", "Health Softworks"), ("Security", "Securities")]
ENTITY = ["LLC", "Inc.", "Ltd."]
FIRST = ["Mara", "Tobias", "Ines", "Kofi", "Lena", "Rafael", "Priya", "Dmitri", "Aiyana", "Selwyn", "Noor", "Haruto",
         "Greer", "Odile", "Bastian", "Yetunde", "Corin", "Mirela", "Ansel", "Tamsin"]
LAST = ["Okafor", "Lindqvist", "Abernathy", "Moreau-Diallo", "Halloran", "Szabo", "Vantongeren", "Achterberg",
        "Quist", "Ferreira-Lam", "Ostrowski", "Nakashima", "Delacroix-Hart", "Whitlock", "Brannagh", "Ekwueme",
        "Castellanos", "Ivanova", "Pembrook", "Rasmussen"]
AUTH_TITLES = ["Chief Executive Officer", "Chief Financial Officer", "General Counsel", "VP, Legal",
               "Chief Operating Officer"]
OTHER_TITLES = ["Account Executive", "Regional Sales Director", "Procurement Specialist", "Operations Manager",
                "Chief Executive Officer", "Head of Partnerships"]
VENDOR_TITLES = ["Master Services Agreement", "Software Subscription Agreement", "Professional Services Agreement",
                 "Data Processing Services Agreement", "Managed Hosting Agreement"]
CUSTOMER_TITLES = ["Customer Subscription Agreement", "Enterprise License Agreement", "Analytics Services Agreement"]
BUYER_ROLES = ["Customer", "Client", "Subscriber"]
SELLER_ROLES = ["Provider", "Supplier", "Vendor"]

ANNUAL_LOW = [60000, 84000, 96000, 120000, 144000, 180000, 216000, 240000]
ANNUAL_HIGH = [264000, 300000, 360000, 480000]


# ------------------------------------------------------------------------------------------------ term specs
class Ctx:
    def __init__(self, rng, diff, kind, buyer, seller, annual, T, cp):
        self.rng, self.diff, self.kind, self.buyer, self.seller = rng, diff, kind, buyer, seller
        self.annual, self.T, self.cp = annual, T, cp
        self.q_role = buyer if kind == "vendor" else seller
        self.c_role = seller if kind == "vendor" else buyer

    def st(self):
        r = self.rng
        if self.diff == "easy":
            return r.choice(["digits", "both"])
        if self.diff == "medium":
            return r.choice(["both", "both", "digits", "words"])
        return r.choice(["words", "both", "words"])


def liab_equiv(v, annual):
    if v[0] == "months":
        return v[1]
    if v[0] == "fixed":
        return v[1] * 12 / annual
    if v[0] == "greater":
        return max(v[1] * 12 / annual, v[2])
    return float("inf")


def code_of(typ, v, ctx):
    if typ == "LIABILITY_CAP":
        if v[0] == "unlimited":
            return "LIAB_UNCAPPED"
        return "LIAB_CAP_LOW" if liab_equiv(v, ctx.annual) < 6 else None
    if typ == "INDEMNITY":
        return "INDEM_ONE_SIDED" if v[0] == "against" else None
    if typ == "AUTO_RENEWAL":
        return "RENEWAL_TERMS" if v[0] == "auto" and (v[1] > 12 or v[2] > 60) else None
    if typ == "TERMINATION_NOTICE":
        if v[0] in ("either", "ours"):
            return "TERM_NOTICE_LONG" if v[1] > 90 else None
        return "TERM_NOTICE_LONG"
    if typ == "GOVERNING_LAW":
        j = ctx.cp["_hq_key"] if v[0] == "hq" else v[1]
        return "GOV_LAW_NONSTANDARD" if JUR_LEVEL[j] == "dev" else None
    if typ == "BREACH":
        return "DPA_BREACH_NOTICE" if v[0] * (1 if v[1] == "hour" else 24) > 72 else None
    if typ == "DATA_USE":
        return "DPA_SECONDARY_USE" if v[0] == "secondary" else None
    if typ == "PAYMENT_TERMS":
        if ctx.kind == "vendor":
            return "PAY_TERMS_SHORT" if v[0] < 30 else None
        return "PAY_TERMS_LONG" if v[0] > 45 else None
    raise KeyError(typ)


def norm_value(typ, v, ctx):
    """Comparable value, used to make sure a conflicting clause really differs."""
    if typ == "LIABILITY_CAP":
        return round(liab_equiv(v, ctx.annual), 3)
    if typ == "BREACH":
        return v[0] * (1 if v[1] == "hour" else 24)
    if typ == "GOVERNING_LAW":
        return ctx.cp["_hq_key"] if v[0] == "hq" else v[1]
    if typ == "TERMINATION_NOTICE":
        return (v[0], v[1] if len(v) > 1 else None)
    return v


def pick_value(typ, level, ctx):
    r, diff = ctx.rng, ctx.diff
    fixed_ok = diff != "easy" and ctx.annual % 12000 == 0
    if typ == "LIABILITY_CAP":
        if level == "dev":
            if diff != "easy" and r.random() < 0.08:
                return ("unlimited",)
            opts = [("months", 3), ("months", 2), ("months", 4)]
            if diff != "easy":
                opts += [("months", 1)] * (5 if diff == "hard" else 2)
            if fixed_ok:
                opts += [("fixed", e * ctx.annual // 12) for e in (2, 3, 4)]
            return r.choice(opts)
        if level == "fallback":
            opts = [("months", 6), ("months", 9)]
            if fixed_ok:
                opts += [("fixed", e * ctx.annual // 12) for e in (6, 8)]
            return r.choice(opts)
        opts = [("months", 12), ("months", 12), ("months", 24)]
        if diff != "easy":
            opts += [("greater", r.choice([25000, 50000]), 12)]
        if fixed_ok:
            opts += [("fixed", e * ctx.annual // 12) for e in (12, 18)]
        return r.choice(opts)
    if typ == "INDEMNITY":
        return {"dev": ("against",), "fallback": ("ours",), "pref": ("mutual",)}[level]
    if typ == "AUTO_RENEWAL":
        if level == "dev":
            return r.choice([("auto", 12, 90), ("auto", 12, 120), ("auto", 24, 30), ("auto", 36, 60)])
        if level == "fallback":
            return r.choice([("auto", 12, 60), ("auto", 12, 45), ("auto", 6, 60)])
        return r.choice([("none",), ("none",), ("auto", 12, 30), ("auto", 12, 15)])
    if typ == "TERMINATION_NOTICE":
        if level == "dev":
            return r.choice([("either", 120), ("either", 180), ("theirs", 30), ("none",)])
        if level == "fallback":
            return r.choice([("either", 60), ("either", 90), ("ours", 90)])
        return r.choice([("either", 30), ("ours", 30), ("either", 15)])
    if typ == "GOVERNING_LAW":
        hq = ctx.cp["_hq_key"]
        if diff != "easy" and JUR_LEVEL[hq] == level and r.random() < 0.35:
            return ("hq",)
        return ("named", r.choice([j for j, lv in JUR_LEVEL.items() if lv == level]))
    if typ == "BREACH":
        if level == "dev":
            return r.choice([(96, "hour"), (5, "business day"), (7, "day"), (10, "day")])
        if level == "fallback":
            return r.choice([(72, "hour"), (3, "day"), (60, "hour")])
        return r.choice([(24, "hour"), (48, "hour"), (2, "business day")])
    if typ == "DATA_USE":
        if level == "dev":
            return ("secondary",)
        return r.choice([("plain",), ("aggregated",)]) if diff != "easy" else ("plain",)
    if typ == "PAYMENT_TERMS":
        if ctx.kind == "vendor":
            pools = {"dev": [10, 15, 20, 25], "fallback": [30, 40], "pref": [45, 60]}
        else:
            pools = {"dev": [60, 75, 90], "fallback": [45, 40], "pref": [30, 15]}
        return (r.choice(pools[level]),)
    raise KeyError(typ)


DEF_NAMES = {"LIABILITY_CAP": "Liability Cap", "INDEMNITY": "Indemnifying Party", "AUTO_RENEWAL": None,
             "TERMINATION_NOTICE": "Convenience Notice Period", "BREACH": "Breach Notice Period",
             "DATA_USE": "Permitted Purposes", "PAYMENT_TERMS": "Payment Period"}


def can_define(typ, v):
    if typ == "LIABILITY_CAP":
        return v[0] in ("months", "fixed")
    if typ == "TERMINATION_NOTICE":
        return v[0] == "either"
    if typ == "AUTO_RENEWAL":
        return v[0] == "auto"
    if typ == "DATA_USE":
        return v[0] in ("secondary", "plain")
    return typ in DEF_NAMES and DEF_NAMES[typ] is not None


def dur(v, st):
    n, unit = v
    return days(n, st, unit)


def render(typ, v, ctx, use_def):
    """Return (main clause text, definition text or None)."""
    st = ctx.st()
    b, s, q, c = ctx.buyer, ctx.seller, ctx.q_role, ctx.c_role
    if typ == "LIABILITY_CAP":
        lead = "Each party's total aggregate liability arising out of or relating to this Agreement shall not exceed"
        if v[0] == "unlimited":
            return ("Nothing in this Agreement limits or excludes either party's liability for any claim arising out "
                    "of or relating to this Agreement.", None)
        if v[0] == "months":
            phrase = f"the total fees paid or payable by {b} under this Agreement in the {months(v[1], st)} preceding " \
                     f"the event giving rise to the claim"
        elif v[0] == "fixed":
            phrase = money(v[1], st)
        else:
            phrase = f"the greater of {money(v[1], st)} and the total fees paid or payable by {b} in the " \
                     f"{months(v[2], st)} preceding the event giving rise to the claim"
        if use_def:
            return f"{lead} the Liability Cap.", f'"Liability Cap" means {phrase}.'
        return f"{lead} {phrase}.", None
    if typ == "INDEMNITY":
        if use_def:
            who = {"against": q, "ours": c, "mutual": "each party, as to claims arising from its own breach or "
                                                      "infringement"}[v[0]]
            return ("The Indemnifying Party shall defend, indemnify and hold harmless the other party against "
                    "third-party claims arising from a breach of this Agreement or the infringement of a third "
                    "party's intellectual property rights.", f'"Indemnifying Party" means {who}.')
        if v[0] == "mutual":
            return ("Each party shall defend, indemnify and hold harmless the other party against third-party claims "
                    "arising from its breach of this Agreement or its infringement of a third party's intellectual "
                    "property rights.", None)
        giver, taker = (c, q) if v[0] == "ours" else (q, c)
        scope = ("arising from its breach of this Agreement or its infringement of a third party's intellectual "
                 "property rights") if v[0] == "ours" else f"arising from or relating to {q}'s use of the services " \
                                                           f"or performance under this Agreement"
        return (f"{giver} shall defend, indemnify and hold harmless {taker} against all third-party claims {scope}. "
                f"{taker} gives no indemnity under this Agreement.", None)
    if typ == "AUTO_RENEWAL":
        if v[0] == "none":
            return "This Agreement expires at the end of the Initial Term unless the parties agree in writing to " \
                   "renew it.", None
        _, R, D = v
        if use_def:
            if R > 12:
                return (f"After the Initial Term, this Agreement renews automatically for successive Renewal Terms "
                        f"unless either party gives written notice of non-renewal at least {days(D, st)} before the "
                        f"end of the then-current term.", f'"Renewal Term" means a period of {months(R, st)}.')
            return (f"After the Initial Term, this Agreement renews automatically for successive renewal terms of "
                    f"{months(R, st)} each unless either party gives written notice of non-renewal at least the "
                    f"Non-Renewal Notice Period before the end of the then-current term.",
                    f'"Non-Renewal Notice Period" means {days(D, st)}.')
        return (f"After the Initial Term, this Agreement renews automatically for successive renewal terms of "
                f"{months(R, st)} each unless either party gives written notice of non-renewal at least "
                f"{days(D, st)} before the end of the then-current term.", None)
    if typ == "TERMINATION_NOTICE":
        if v[0] == "none":
            return "Neither party may terminate this Agreement for convenience.", None
        D = v[1]
        if use_def:
            return ("Either party may terminate this Agreement for convenience by giving the other party written "
                    "notice of at least the Convenience Notice Period.",
                    f'"Convenience Notice Period" means {days(D, st)}.')
        who = {"either": "Either party", "ours": q, "theirs": f"Only {c}"}[v[0]]
        return f"{who} may terminate this Agreement for convenience on {days(D, st)}' written notice.", None
    if typ == "GOVERNING_LAW":
        if v[0] == "hq":
            law = f"the laws of the jurisdiction in which {c} has its principal place of business"
        else:
            law = f"the laws of {JUR_TEXT[v[1]]}"
        text = f"This Agreement is governed by {law}, without regard to its conflict-of-laws rules."
        if ctx.diff != "easy" and ctx.rng.random() < 0.4:
            venue = ctx.rng.choice(["Harris County, Texas", "Clark County, Nevada", "Wilmington, Delaware",
                                    "New York County, New York", "Cook County, Illinois"])
            text += f" The courts located in {venue} have exclusive jurisdiction over any dispute."
        return text, None
    if typ == "BREACH":
        if use_def:
            return (f"{s} shall notify {b} of any Personal Data Breach without undue delay and in any event within "
                    f"the Breach Notice Period after becoming aware of it.",
                    f'"Breach Notice Period" means {dur(v, st)}.')
        return (f"{s} shall notify {b} of any Personal Data Breach without undue delay and in any event within "
                f"{dur(v, st)} of becoming aware of it.", None)
    if typ == "DATA_USE":
        if use_def:
            purpose = (f"performing the services and developing, training and improving {s}'s own products"
                       if v[0] == "secondary" else f"performing the services on {b}'s documented instructions")
            return (f"{s} shall process Personal Data only for the Permitted Purposes and shall not sell it.",
                    f'"Permitted Purposes" means {purpose}.')
        if v[0] == "secondary":
            return (f"{s} shall process Personal Data to provide the services and may also use Personal Data received "
                    f"under this Agreement to develop, train and improve its products and for its other legitimate "
                    f"business purposes.", None)
        if v[0] == "aggregated":
            return (f"{s} shall process Personal Data only on {b}'s documented instructions, except that {s} may "
                    f"compile aggregated, de-identified statistics that do not identify any individual or {b}.", None)
        return f"{s} shall process Personal Data only on {b}'s documented instructions and shall not sell it.", None
    if typ == "PAYMENT_TERMS":
        if use_def:
            return (f"{b} shall pay each undisputed invoice within the Payment Period.",
                    f'"Payment Period" means {days(v[0], st)} from the invoice date.')
        return f"{b} shall pay each undisputed invoice within {days(v[0], st)} of the invoice date.", None
    raise KeyError(typ)


def render_order_form(typ, v, ctx):
    st = ctx.st()
    if typ == "PAYMENT_TERMS":
        return ctx.rng.choice([f"Payment terms: Net {v[0]}.", f"Invoices are payable within {days(v[0], st)}."])
    if typ == "LIABILITY_CAP":
        if v[0] == "unlimited":
            return "Liability: neither party's liability under the Agreement is limited for claims under this Order Form."
        return f"Liability cap: fees paid or payable in the prior {months(v[1], st)}."
    if typ == "GOVERNING_LAW":
        return f"This Order Form and the Agreement are governed by the laws of {JUR_TEXT[v[1]]}."
    if typ == "TERMINATION_NOTICE":
        return f"Either party may terminate for convenience on {days(v[1], st)}' notice."
    if typ == "BREACH":
        return f"Security incidents: {ctx.seller} will report any Personal Data Breach within {dur(v, st)}."
    raise KeyError(typ)


# ------------------------------------------------------------------------------------------------ builders
def person(rng, avoid=()):
    while True:
        n = f"{rng.choice(FIRST)} {rng.choice(LAST)}"
        if n not in avoid:
            return n


def make_counterparty(rng, cp_id, name, diff):
    hq = rng.choice(list(JUR_LEVEL))
    signers, names = [], set()
    for _ in range(rng.choice([2, 2, 3])):
        n = person(rng, names)
        names.add(n)
        signers.append({"name": n, "title": rng.choice(AUTH_TITLES)})
    roll = rng.random()
    if roll < 0.15:
        tier, prior, risk = "STRATEGIC", rng.randint(0, 9), rng.choice(["LOW", "MEDIUM", "HIGH"])
    else:
        tier = "STANDARD"
        if diff == "hard" and rng.random() < 0.5:   # edge cases around the eligibility rule
            prior, risk = rng.choice([(3, "LOW"), (2, "LOW"), (6, "MEDIUM"), (4, "LOW"), (3, "HIGH")])
        else:
            prior, risk = rng.randint(0, 7), rng.choice(["LOW", "LOW", "MEDIUM", "HIGH"])
    return {
        "counterparty_id": cp_id, "legal_name": name,
        "size": f"{rng.choice([40, 120, 350, 900, 2400, 7800])} employees",
        "tier": tier, "risk_rating": risk, "prior_agreements": prior,
        "principal_place_of_business": HQ_TEXT[hq],
        "authorized_signatories": signers,
        "relationship_notes": rng.choice(["Onboarded through procurement portal.", "Referred by the finance team.",
                                          "Renewal of a lapsed pilot.", "No notes.", "Prefers email notices."]),
        "_hq_key": hq,
    }


def eligible(cp):
    return cp["tier"] == "STRATEGIC" or (cp["prior_agreements"] >= 3 and cp["risk_rating"] == "LOW")


DEV_WEIGHTS = {"LIABILITY_CAP": 3, "PAYMENT_TERMS": 3, "TERMINATION_NOTICE": 2, "AUTO_RENEWAL": 2,
               "GOVERNING_LAW": 2, "BREACH": 2, "INDEMNITY": 2, "DATA_USE": 1}
TYPES = list(DEV_WEIGHTS)
CONFLICT_TYPES = ["PAYMENT_TERMS", "LIABILITY_CAP", "GOVERNING_LAW", "TERMINATION_NOTICE", "BREACH"]


def build_contract(rng, diff, review, cid, title, kind, cp, received, *, n_dev, conflict=False, h2=False, h3=False,
                   annual=None):
    buyer, seller = rng.choice(BUYER_ROLES), rng.choice(SELLER_ROLES)
    T = rng.choice([12, 12, 24, 36]) if diff != "easy" else rng.choice([12, 24])
    if annual is None:
        annual = rng.choice(ANNUAL_HIGH) if rng.random() < 0.12 else rng.choice(ANNUAL_LOW)
    total = annual * T // 12
    ctx = Ctx(rng, diff, kind, buyer, seller, annual, T, cp)

    # pick deviating types
    pool = [t for t in TYPES if not (t == "DATA_USE" and kind == "customer")]
    devs = set()
    while len(devs) < n_dev:
        devs.add(rng.choices(pool, weights=[DEV_WEIGHTS[t] for t in pool])[0])
    terms = {}
    for t in TYPES:
        if t in devs:
            level = "dev"
        elif diff == "easy":
            level = "pref" if rng.random() < 0.85 else "fallback"
        elif diff == "medium":
            level = "pref" if rng.random() < 0.6 else "fallback"
        else:
            level = "pref" if rng.random() < 0.4 else "fallback"
        if t == "DATA_USE" and level == "fallback":
            level = "pref"
        if t == "INDEMNITY" and level == "fallback" and diff == "easy":
            level = "pref"
        v = pick_value(t, level, ctx)
        if t == "AUTO_RENEWAL" and h2 and v[0] == "none":
            v = ("auto", 12, rng.choice([30, 60, 45]))
        terms[t] = v
    # never let the order form unlimited-liability case and a main-clause unlimited coexist
    # decide definitions
    p_def = {"easy": 0.0, "medium": 0.15, "hard": 0.35}[diff]
    use_def = {t: can_define(t, v) and rng.random() < p_def for t, v in terms.items()}
    if diff == "hard" and devs and not any(use_def[t] for t in devs):
        cands = [t for t in devs if can_define(t, terms[t])]
        if cands and rng.random() < 0.6:
            use_def[rng.choice(cands)] = True

    # dates
    if h2:
        D = terms["AUTO_RENEWAL"][2]
        deadline = review + dt.timedelta(days=rng.randint(-50, 20))
        eff = deadline + dt.timedelta(days=D)
        eff = add_months(eff, -T)
    else:
        eff = review + dt.timedelta(days=rng.randint(-20, 30))
    rendered = {t: render(t, v, ctx, use_def[t]) for t, v in terms.items()}

    # order form
    order_form = []
    conflict_term = None
    has_of = conflict or rng.random() < (0.3 if diff == "easy" else 0.55)
    if has_of:
        order_form.append((None, f"Service tier: {rng.choice(['Standard', 'Professional', 'Enterprise'])}."))
        order_form.append((None, f"Authorized users: {rng.choice([25, 50, 120, 300, 750])}."))
        if rng.random() < 0.5:
            order_form.append((None, "Support hours: 8:00 to 18:00 Eastern Time, Monday to Friday."))
        if conflict:
            cands = [t for t in CONFLICT_TYPES if not (t == "LIABILITY_CAP" and terms[t][0] == "unlimited")
                     and not (t == "TERMINATION_NOTICE" and terms[t][0] != "either")]
            ctype = rng.choices(cands, weights=[3 if t == "LIABILITY_CAP" else 1 for t in cands])[0]
            main_dev = code_of(ctype, terms[ctype], ctx) is not None
            for _ in range(100):
                if ctype == "LIABILITY_CAP" and not main_dev and rng.random() < 0.6:
                    ov = ("unlimited",)
                else:
                    lvl = rng.choice(["pref", "fallback"]) if main_dev else rng.choice(["dev", "dev", "pref", "fallback"])
                    ov = pick_value(ctype, lvl, ctx)
                    if ctype == "LIABILITY_CAP" and ov[0] != "months":
                        continue
                    if ctype == "GOVERNING_LAW" and ov[0] != "named":
                        continue
                    if ctype == "TERMINATION_NOTICE" and ov[0] != "either":
                        continue
                if norm_value(ctype, ov, ctx) != norm_value(ctype, terms[ctype], ctx):
                    break
            else:
                raise RuntimeError("no conflicting value")
            conflict_term = (ctype, ov)
            order_form.append(("OF_CONFLICT", render_order_form(ctype, ov, ctx)))
        elif (diff != "easy" and rng.random() < 0.4 and code_of("PAYMENT_TERMS", terms["PAYMENT_TERMS"], ctx) is None):
            order_form.append((None, render_order_form("PAYMENT_TERMS", terms["PAYMENT_TERMS"], ctx)))
        rng.shuffle(order_form)

    # definitions
    defs = [(None, f'"Services" means the services described in the Order Form and any statement of work.'),
            (None, '"Personal Data" means any information relating to an identified or identifiable individual.'),
            (None, '"Effective Date" means the effective date shown in the contract header.')]
    if rng.random() < 0.5:
        defs.append((None, '"Confidential Information" means non-public information disclosed by one party to the '
                           'other that is marked or reasonably understood to be confidential.'))
    for t in TYPES:
        if rendered[t][1]:
            defs.append((f"{t}_DEF", rendered[t][1]))
    rng.shuffle(defs)

    S = lambda t: (f"{t}_MAIN", rendered[t][0])  # noqa: E731
    mid = [
        ("Term and Renewal", [(None, f'This Agreement starts on the Effective Date and continues for '
                                     f'{months(T, ctx.st())} (the "Initial Term").'), S("AUTO_RENEWAL")]),
        ("Fees and Payment", [(None, f"{buyer} shall pay {seller} total fees of {money(total, ctx.st())} for the "
                                     f"Initial Term, invoiced {rng.choice(['annually', 'quarterly'])} in advance."),
                              S("PAYMENT_TERMS")]),
        ("Termination", [S("TERMINATION_NOTICE"),
                         (None, "Either party may terminate this Agreement if the other party materially breaches it "
                                "and fails to cure the breach within thirty (30) days of written notice.")]),
        ("Data Protection", [S("DATA_USE"), S("BREACH")]),
        ("Indemnification", [S("INDEMNITY")]),
        ("Limitation of Liability", [(None, "Neither party is liable for any indirect, consequential, special or "
                                            "punitive damages."), S("LIABILITY_CAP")]
         + ([(None, "The limits in this Section do not apply to a party's indemnification obligations, breach of "
                    "confidentiality, or gross negligence or willful misconduct.")] if rng.random() < 0.6 else [])),
        ("Governing Law", [S("GOVERNING_LAW")]),
    ]
    rng.shuffle(mid)
    sections = [("Definitions", defs),
                ("Services", [(None, f"{seller} shall provide the Services with reasonable skill and care."),
                              (None, f"{buyer} shall provide timely access to the information {seller} reasonably "
                                     f"needs to perform the Services.")])] + mid + [
        ("General", [(None, "This Agreement is the entire agreement between the parties on its subject matter."),
                     (None, "Notices must be in writing and sent to the addresses in the contract header.")])]
    if order_form:
        sections.append(("Order Form", order_form))
    out_sections, key_to_id = [], {}
    for i, (head, clauses) in enumerate(sections, 1):
        cl = []
        for j, (key, text) in enumerate(clauses, 1):
            cid_ = f"{i}.{j}"
            if key:
                key_to_id[key] = cid_
            cl.append({"clause_id": cid_, "text": text})
        out_sections.append({"section": i, "heading": head, "clauses": cl})

    # flags (gold)
    flags = []
    for t, v in terms.items():
        code = code_of(t, v, ctx)
        if code:
            key = f"{t}_DEF" if use_def[t] else f"{t}_MAIN"
            flags.append((key_to_id[key], code, SEVERITY[code]))
    if conflict_term:
        code = code_of(conflict_term[0], conflict_term[1], ctx)
        if code:
            flags.append((key_to_id["OF_CONFLICT"], code, SEVERITY[code]))

    # signatory
    if h3:
        auth_names = [s["name"] for s in cp["authorized_signatories"]]
        if rng.random() < 0.5:
            first = rng.choice(auth_names).split()[0]
            name = next(n for n in (f"{first} {rng.choice(LAST)}" for _ in range(100)) if n not in auth_names)
        else:
            name = person(rng, auth_names)
        signatory = {"name": name, "title": rng.choice(OTHER_TITLES)}
    else:
        signatory = dict(rng.choice(cp["authorized_signatories"]))

    ar = terms["AUTO_RENEWAL"]
    deadline = None
    if ar[0] == "auto":
        deadline = add_months(eff, T) - dt.timedelta(days=ar[2])
    meta = {
        "annual_fees": annual, "flags": flags, "conflict": conflict_term is not None,
        "renewal_deadline": deadline.isoformat() if deadline else None,
        "renewal_deadline_hit": bool(deadline and deadline <= review + dt.timedelta(days=30)),
        "signatory_ok": not h3, "terms": {t: list(v) for t, v in terms.items()},
        "conflict_term": list(conflict_term) if conflict_term else None,
    }
    contract = {
        "contract_id": cid, "title": title, "contract_type": kind,
        "parties": [{"name": QUILLMERE, "role": ctx.q_role},
                    {"name": cp["legal_name"], "role": ctx.c_role, "counterparty_id": cp["counterparty_id"]}],
        "effective_date": eff.isoformat(), "received_date": received.isoformat(),
        "counterparty_signatory": signatory,
        "quillmere_signatory": {"name": "Wilhelmina Strand", "title": "General Counsel"},
        "sections": out_sections, "_meta": meta,
    }
    return contract


def gold_for(contract, cp):
    m = contract["_meta"]
    flags = m["flags"]
    elig = eligible(cp)
    redlines = {c: ("FALLBACK" if elig and sev != "CRITICAL" else "PREFERRED") for c, _, sev in flags}
    reasons = set()
    if any(sev == "CRITICAL" for *_, sev in flags):
        reasons.add("CRITICAL_DEVIATION")
    if sum(sev == "HIGH" for *_, sev in flags) >= 2:
        reasons.add("MULTIPLE_HIGH")
    if m["annual_fees"] >= 250000:
        reasons.add("VALUE_THRESHOLD")
    triggers = []
    if m["conflict"]:
        triggers.append("conflicting_terms")
    if m["renewal_deadline_hit"]:
        triggers.append("renewal_deadline")
    if not m["signatory_ok"]:
        triggers.append("signatory_authority")
    for t in triggers:
        reasons.add(HIDDEN_REASON[t])
    return {
        "contract_id": contract["contract_id"],
        "flags": [list(f) for f in sorted(flags)],
        "redlines": redlines,
        "action": "escalate" if reasons else "approve",
        "reasons": sorted(reasons),
    }, triggers


def build_tasks(seed: int = SEED, n: int = N_TASKS):
    rng = random.Random(seed)
    diffs = ["easy", "medium", "hard"] * (n // 3) + ["hard"] * (n % 3)
    idx = list(range(n))
    nonEasy = [i for i in idx if diffs[i] != "easy"]
    h1 = set(rng.sample(nonEasy, 21))
    h2 = set(rng.sample(idx, 20))
    h3 = set(rng.sample(idx, 20))
    tasks, used_ids = [], set()

    def new_cid():
        while True:
            c = f"QA-C-{rng.randint(1000, 9999)}"
            if c not in used_ids:
                used_ids.add(c)
                return c

    for i in range(n):
        diff = diffs[i]
        review = dt.date(2026, 9, 1) + dt.timedelta(days=rng.randint(0, 100))
        prefixes = rng.sample(PREFIXES, 4)
        pair = rng.choice(SUFFIX_PAIRS)
        kind = "vendor" if rng.random() < 0.65 else "customer"
        title = rng.choice(VENDOR_TITLES if kind == "vendor" else CUSTOMER_TITLES)
        name = f"{prefixes[0]} {pair[0]} {rng.choice(ENTITY)}"
        cp = make_counterparty(rng, f"CP-{rng.randint(10000, 99999)}", name, diff)
        received = review - dt.timedelta(days=rng.randint(1, 9))
        n_dev = {"easy": rng.choice([0, 1, 1]), "medium": rng.choice([1, 1, 2]), "hard": rng.choice([1, 2, 2, 3])}[diff]
        hidden = (i in h1) + (i in h2) + (i in h3)
        if hidden and rng.random() < 0.7:    # keep most hidden-rule tasks otherwise approvable
            n_dev = min(n_dev, 1)
        annual = None
        if diff == "hard" and rng.random() < 0.2:
            annual = rng.choice([250000, 249600])
        cid = new_cid()
        target = build_contract(rng, diff, review, cid, title, kind, cp, received, n_dev=n_dev, conflict=i in h1,
                                h2=i in h2, h3=i in h3, annual=annual)
        contracts = {cid: target}
        cps = {cp["counterparty_id"]: cp}

        by_description = diff == "hard" and rng.random() < 0.6 or diff == "medium" and rng.random() < 0.2
        if by_description:
            # twin 1: near-identical counterparty name, same title, same received date
            tname = f"{prefixes[0]} {pair[1]} {rng.choice(ENTITY)}"
            tcp = make_counterparty(rng, f"CP-{rng.randint(10000, 99999)}", tname, "medium")
            tc = build_contract(rng, "medium", review, new_cid(), title, kind, tcp, received, n_dev=rng.choice([0, 1, 2]))
            contracts[tc["contract_id"]] = tc
            cps[tcp["counterparty_id"]] = tcp
            # twin 2: same counterparty, same title, different received date
            tc2 = build_contract(rng, "medium", review, new_cid(), title, kind, cp,
                                 received - dt.timedelta(days=rng.randint(10, 40)), n_dev=rng.choice([0, 1, 2]))
            contracts[tc2["contract_id"]] = tc2
        for k in range(rng.choice([1, 2])):
            okind = rng.choice(["vendor", "customer"])
            oname = f"{prefixes[1 + k]} {rng.choice(SUFFIX_PAIRS)[0]} {rng.choice(ENTITY)}"
            ocp = make_counterparty(rng, f"CP-{rng.randint(10000, 99999)}", oname, "easy")
            oc = build_contract(rng, "easy", review, new_cid(), rng.choice(VENDOR_TITLES if okind == "vendor"
                                                                           else CUSTOMER_TITLES),
                                okind, ocp, review - dt.timedelta(days=rng.randint(1, 15)), n_dev=rng.choice([0, 1]))
            contracts[oc["contract_id"]] = oc
            cps[ocp["counterparty_id"]] = ocp

        gold, triggers = gold_for(target, cp)
        today = review.isoformat()
        if by_description:
            request = rng.choice([
                f"Today is {today}. {name} sent over their {title} on {received.isoformat()}. Please run the playbook "
                f"review on it and take the final action.",
                f"Can you review the {title} we received from {name} on {received.isoformat()}? Flag, redline, then "
                f"approve or escalate per the procedure. Today is {today}.",
            ])
        else:
            request = rng.choice([
                f"Please review contract {cid} ({title} with {name}) against the playbook and take the final review "
                f"action. Today is {today}.",
                f"New inbound {title} from {name} is in the queue as {cid}. Review it per the playbook and approve or "
                f"escalate. Today is {today}.",
                f"Today is {today}. Run the standard playbook review on {cid} from {name} and close it out.",
            ])
        tasks.append({
            "id": f"cr-{i + 1:03d}", "request": request, "difficulty": diff, "triggers": triggers, "gold": gold,
            "_data": {"today": today, "contracts": contracts, "counterparties": cps},
        })
    return tasks
