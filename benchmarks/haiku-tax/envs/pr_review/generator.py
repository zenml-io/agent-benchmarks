"""Deterministic generator for the pull-request review environment.

Each task is one PR against a small synthetic Python service. The generator starts from clean code, plants zero to two
issues from a catalog, adds look-alike changes that are fine (decoys), and builds the CODEOWNERS rules, people
directory and CI result. Ground truth comes from construction: planted issues are tagged lines in the head file, and
the gold verdict and reviewer set are derived from the data with the written policy plus the hidden rules.
"""
from __future__ import annotations

import difflib
import random

SEED = 20261019
N_TASKS = 160

SERVICES = [
    {"repo": "ledger-svc", "pkg": "ledger", "team": "ledger", "noun": "entry", "table": "entries", "CONST": "ENTRY",
     "modules": ["postings", "balances"]},
    {"repo": "shipping-svc", "pkg": "shipping", "team": "logistics", "noun": "shipment", "table": "shipments",
     "CONST": "SHIPMENT", "modules": ["dispatch", "tracking"]},
    {"repo": "notify-svc", "pkg": "notify", "team": "messaging", "noun": "message", "table": "messages",
     "CONST": "MESSAGE", "modules": ["outbox", "templates"]},
    {"repo": "stock-svc", "pkg": "stock", "team": "inventory", "noun": "item", "table": "items", "CONST": "ITEM",
     "modules": ["levels", "reorders"]},
    {"repo": "identity-svc", "pkg": "identity", "team": "identity", "noun": "session", "table": "sessions",
     "CONST": "SESSION", "modules": ["profiles", "directory"], "sens": "auth", "sens_modules": ["tokens", "login"]},
    {"repo": "billing-svc", "pkg": "billing", "team": "billing", "noun": "invoice", "table": "invoices",
     "CONST": "INVOICE", "modules": ["statements", "credits"], "sens": "payments", "sens_modules": ["charges", "refunds"]},
]

FIRST = ["Mara", "Tobin", "Ines", "Kofi", "Liesl", "Dario", "Yuki", "Oren", "Priya", "Selim", "Wren", "Anouk", "Bram",
         "Calla", "Desmond", "Elif", "Fenna", "Gideon", "Hollis", "Ilka", "Jarek", "Keziah", "Lucan", "Mireille",
         "Nils", "Odette", "Pavel", "Quill", "Rosalind", "Soren", "Talia", "Umber", "Vesna", "Wilder", "Xenia",
         "Yannick", "Zora", "Amadou", "Beatrix", "Cyprian", "Delphine", "Emeric"]
LAST = ["Okafor", "Lindqvist", "Marchetti", "Asante", "Brennhall", "Castellan", "Dunmore", "Eskildsen", "Farrow",
        "Galloway", "Haverty", "Ivanko", "Jessop", "Kettering", "Larkspur", "Mendel", "Norcross", "Oyelaran",
        "Pellham", "Quarrie", "Rasmussen", "Stavros", "Thornbury", "Ulveng", "Vantongeren", "Whitlock", "Yarrow",
        "Zelenko", "Abernath", "Brightwater", "Coldicott", "Delacroix", "Ellingham", "Fairweather", "Greaves"]
SENIORITY = ["junior", "mid", "senior", "staff"]

CATEGORY = {"obo_recent": "bug", "obo_settled": "bug", "obo_page": "bug", "none": "bug", "swallow_pass": "bug",
            "swallow_return": "bug", "sql_concat": "security", "sql_fstring": "security", "secret": "security",
            "sig_break": "breaking_change", "sig_partial": "breaking_change", "branch_untested": "missing_test",
            "newfn_untested": "missing_test"}
# planted kind -> the "family" it uses (a family appears at most once per PR)
FAMILY = {"obo_recent": "recent", "obo_settled": "settled", "obo_page": "page", "none": "email",
          "swallow_pass": "sync", "swallow_return": "sync", "sql_concat": "sql", "sql_fstring": "sql",
          "secret": "secret", "sig_break": "sig", "sig_partial": "sig", "branch_untested": "branch",
          "newfn_untested": "archive"}
DECOY_FAMILY = {"recent_ok": "recent", "settled_ok": "settled", "page_ok": "page", "gaps": "gaps",
                "email_ok": "email", "sync_ok": "sync", "sql_param": "sql", "sql_const_table": "sql",
                "secret_env": "secret", "sig_default": "sig", "sig_updated": "sig", "branch_tested": "branch",
                "archive_ok": "archive"}
HARD_DECOYS = {"gaps", "sql_const_table", "sig_updated", "sync_ok", "secret_env"}
HARD_PLANTS = {"sig_partial", "swallow_return", "sql_fstring", "obo_page", "newfn_untested"}


def _sub(s: str, ctx: dict) -> str:
    for k, v in ctx.items():
        s = s.replace("<" + k + ">", v)
    return s


def block(src: str, ctx: dict) -> list:
    """Template text -> [(line, tag)]. A line ending in `  #@tag` is tagged (the marker is removed)."""
    out = []
    for line in _sub(src, ctx).split("\n"):
        tag = None
        if "  #@" in line:
            line, tag = line.split("  #@")
        out.append((line, tag))
    return out


# --- code templates ---------------------------------------------------------------------------------------------------
E_REF = '''def format_<noun>_ref(ref):
    """Return the display form of one <noun> reference."""
    return ref.strip().upper()'''
E_REF_DOC = '''def format_<noun>_ref(ref):
    """Return the canonical display form of one <noun> reference (trimmed, upper case)."""
    return ref.strip().upper()'''
E_TOTAL = '''def <noun>_total(lines):
    """Sum the amount of every line item."""
    total = 0
    for line in lines:
        total += line.amount
    return total'''
E_TOTAL_SUM = '''def <noun>_total(lines):
    """Sum the amount of every line item."""
    return sum(line.amount for line in lines)'''
E_VALIDATE = '''def validate_<noun>_amount(amount):
    """Raise ValueError for amounts the service cannot accept."""
    if amount < 0:
        raise ValueError("negative amount")
    return amount'''
E_VALIDATE_LOG = '''def validate_<noun>_amount(amount):
    """Raise ValueError for amounts the service cannot accept."""
    log.debug("validating amount %s", amount)
    if amount < 0:
        raise ValueError("negative amount")
    return amount'''
E_VALIDATE_BRANCH = '''def validate_<noun>_amount(amount):
    """Raise ValueError for amounts the service cannot accept."""
    if amount < 0:
        raise ValueError("negative amount")
    if amount > MAX_<CONST>_AMOUNT:  #@T
        raise ValueError("amount over limit")
    return amount'''
E_FEE = '''def compute_<noun>_fee(amount):
    """Return the service fee for an amount, in cents."""
    return round(amount * FEE_RATE)'''
E_FEE_REQUIRED = '''def compute_<noun>_fee(amount, region):  #@T
    """Return the service fee for an amount and region, in cents."""
    return round(amount * FEE_RATE * REGION_FACTORS.get(region, 1.0))'''
E_FEE_DEFAULT = '''def compute_<noun>_fee(amount, region="us"):
    """Return the service fee for an amount and region, in cents."""
    return round(amount * FEE_RATE * REGION_FACTORS.get(region, 1.0))'''

NEW = {
    "recent": ('''def recent_<table>(items, n):
    """Return the last n <table>, oldest first."""
    if n <= 0:
        return []
    return items[len(items) - n:]''', '''def recent_<table>(items, n):
    """Return the last n <table>, oldest first."""
    if n <= 0:
        return []
    return items[len(items) - n + 1:]  #@T'''),
    "settled": ('''def settled_<noun>_amount(rows):
    """Sum the amount of every settled row."""
    total = 0
    for i in range(len(rows)):
        if rows[i].settled:
            total += rows[i].amount
    return total''', '''def settled_<noun>_amount(rows):
    """Sum the amount of every settled row."""
    total = 0
    for i in range(1, len(rows)):  #@T
        if rows[i].settled:
            total += rows[i].amount
    return total'''),
    "page": ('''def <noun>_page_bounds(page, size, total):
    """Return (start, end) for a 1-based page number; end is exclusive."""
    start = (page - 1) * size
    end = min(start + size, total)
    return start, end''', '''def <noun>_page_bounds(page, size, total):
    """Return (start, end) for a 1-based page number; end is exclusive."""
    start = page * size  #@T
    end = min(start + size, total)
    return start, end'''),
    "gaps": ('''def <noun>_gaps(timestamps):
    """Return the gap between each pair of consecutive timestamps."""
    gaps = []
    for i in range(len(timestamps) - 1):
        gaps.append(timestamps[i + 1] - timestamps[i])
    return gaps''', None),
    "email": ('''def <noun>_owner_email(store, ref):
    """Return the owner's email in lower case, or None if the ref is unknown."""
    record = store.get(ref)
    if record is None:
        return None
    return record.owner_email.lower()''', '''def <noun>_owner_email(store, ref):
    """Return the owner's email in lower case, or None if the ref is unknown."""
    record = store.get(ref)
    return record.owner_email.lower()  #@T'''),
    "sync": ('''def sync_<noun>(client, payload):
    """Push one <noun> to the upstream service and return its ref."""
    try:
        client.post("/<table>", payload)
    except TimeoutError:
        log.warning("timeout pushing %s", payload.get("ref"))
        raise
    return payload.get("ref")''', None),
    "sync_pass": '''def sync_<noun>(client, payload):
    """Push one <noun> to the upstream service and return its ref."""
    try:
        client.post("/<table>", payload)
    except Exception:  #@T
        pass
    return payload.get("ref")''',
    "sync_return": '''def sync_<noun>(client, payload):
    """Push one <noun> to the upstream service and return its ref."""
    try:
        client.post("/<table>", payload)
    except Exception:  #@T
        return None
    return payload.get("ref")''',
    "sql_param": '''def find_<noun>_by_ref(cur, ref):
    """Look up one <noun> by its reference."""
    cur.execute("SELECT id, status FROM <table> WHERE ref = %s", (ref,))
    return cur.fetchone()''',
    "sql_const_table": '''def find_<noun>_by_ref(cur, ref):
    """Look up one <noun> by its reference."""
    cur.execute(f"SELECT id, status FROM {<CONST>_TABLE} WHERE ref = %s", (ref,))
    return cur.fetchone()''',
    "sql_concat": '''def find_<noun>_by_ref(cur, ref):
    """Look up one <noun> by its reference."""
    cur.execute("SELECT id, status FROM <table> WHERE ref = '" + ref + "'")  #@T
    return cur.fetchone()''',
    "sql_fstring": '''def find_<noun>_by_ref(cur, ref):
    """Look up one <noun> by its reference."""
    cur.execute(f"SELECT id, status FROM <table> WHERE ref = '{ref}'")  #@T
    return cur.fetchone()''',
    "auth_header": '''def <noun>_auth_header():
    """Header for calls to the upstream <noun> API."""
    return {"Authorization": "Bearer " + <CONST>_API_KEY}''',
    "archive": '''def archive_<noun>(store, ref):
    """Mark one <noun> as archived and return it."""
    record = store[ref]
    record.archived = True
    return record''',
    "archive_untested": '''def archive_<noun>(store, ref):  #@T
    """Mark one <noun> as archived and return it."""
    record = store[ref]
    record.archived = True
    return record''',
}

TESTS = {
    "recent": '''def test_recent_<table>_zero():
    assert m.recent_<table>([1, 2, 3], 0) == []''',
    "settled": '''def test_settled_<noun>_amount_empty():
    assert m.settled_<noun>_amount([]) == 0''',
    "page": '''def test_<noun>_page_bounds_width():
    start, end = m.<noun>_page_bounds(2, 10, 100)
    assert end - start == 10''',
    "gaps": '''def test_<noun>_gaps():
    assert m.<noun>_gaps([1, 4, 9]) == [3, 5]''',
    "email": '''def test_<noun>_owner_email_lowercases():
    store = {"r1": Owner(owner_email="A@Example.test")}
    assert m.<noun>_owner_email(store, "r1") == "a@example.test"''',
    "sync": '''def test_sync_<noun>_posts_payload():
    client = FakeClient()
    assert m.sync_<noun>(client, {"ref": "R1"}) == "R1"
    assert client.posts == [("/<table>", {"ref": "R1"})]''',
    "sql": '''def test_find_<noun>_by_ref_runs_one_query():
    cur = FakeCursor()
    m.find_<noun>_by_ref(cur, "R1")
    assert len(cur.calls) == 1''',
    "secret": '''def test_<noun>_auth_header_uses_bearer():
    assert m.<noun>_auth_header()["Authorization"].startswith("Bearer ")''',
    "archive": '''def test_archive_<noun>_sets_flag():
    store = {"r1": Rec()}
    assert m.archive_<noun>(store, "r1").archived is True''',
    "branch": '''def test_validate_rejects_over_limit():
    with pytest.raises(ValueError):
        m.validate_<noun>_amount(m.MAX_<CONST>_AMOUNT + 1)''',
}

T_HEADER = '''"""Tests for <pkg>.<modpath>."""
import pytest

import <pkg>.<modpath> as m
from tests.fakes import FakeClient, FakeCursor, Line, Owner, Rec'''
T_REF = '''def test_format_ref_strips_and_upcases():
    assert m.format_<noun>_ref("  ab12 ") == "AB12"'''
T_REF_SKIP = '''@pytest.mark.skip(reason="flaky on CI")
def test_format_ref_strips_and_upcases():
    assert m.format_<noun>_ref("  ab12 ") == "AB12"'''
T_TOTAL = '''def test_total_sums_lines():
    lines = [Line(amount=5), Line(amount=7)]
    assert m.<noun>_total(lines) == 12
    assert m.<noun>_total([]) == 0'''
T_TOTAL_WEAK = '''def test_total_sums_lines():
    lines = [Line(amount=5), Line(amount=7)]
    assert m.<noun>_total(lines) == 12'''
T_VALIDATE = '''def test_validate_rejects_negative():
    with pytest.raises(ValueError):
        m.validate_<noun>_amount(-1)
    assert m.validate_<noun>_amount(10) == 10'''
T_FEE = '''def test_compute_fee():
    assert m.compute_<noun>_fee(1000) == 25'''
T_FEE_REGION = '''def test_compute_fee():
    assert m.compute_<noun>_fee(1000, "us") == 25'''

HANDLERS = '''"""Request handlers for the <repo> API."""
from <pkg>.<modpath> import compute_<noun>_fee, format_<noun>_ref


def handle_quote(order):
    """Quote the fee for an order."""
    fee = compute_<noun>_fee(order.amount<ARG>)
    return {"ref": format_<noun>_ref(order.ref), "fee": fee}


def handle_lookup(order):
    """Return the display reference for an order."""
    return {"ref": format_<noun>_ref(order.ref)}'''
JOBS = '''"""Nightly jobs for the <pkg> service."""
from <pkg>.<modpath> import compute_<noun>_fee


def nightly_fee_report(orders):
    """Total fees for the night's orders."""
    return sum(compute_<noun>_fee(o.amount<ARG>) for o in orders)'''
FAKES = '''"""Small fakes shared by the unit tests."""
from collections import namedtuple

Line = namedtuple("Line", "amount")
Owner = namedtuple("Owner", "owner_email")


class Rec:
    archived = False


class FakeCursor:
    def __init__(self):
        self.calls = []

    def execute(self, *args):
        self.calls.append(args)

    def fetchone(self):
        return None


class FakeClient:
    def __init__(self):
        self.posts = []

    def post(self, path, payload):
        self.posts.append((path, payload))'''


def module_text(ctx, consts, funcs):
    out = block('''"""<Title> helpers for the <pkg> service."""
import logging
import os

log = logging.getLogger(__name__)

FEE_RATE = 0.025
REGION_FACTORS = {"us": 1.0, "eu": 1.1, "apac": 1.2}''', ctx)
    for c in consts:
        out += block(c, ctx)
    for f in funcs:
        out += [("", None), ("", None)] + block(f, ctx)
    return out


def tests_text(ctx, blocks):
    out = block(T_HEADER, ctx)
    for b in blocks:
        out += [("", None), ("", None)] + block(b, ctx)
    return out


def plain(lines):
    return [t for t, _ in lines]


def numbered(text_lines):
    w = len(str(len(text_lines)))
    return "\n".join(f"{i + 1:>{w}}| {t}" for i, t in enumerate(text_lines))


def udiff(path, base, head):
    d = difflib.unified_diff(base, head, fromfile=f"a/{path}", tofile=f"b/{path}", lineterm="", n=3)
    return "\n".join(d)


# --- people -------------------------------------------------------------------------------------------------------------
def build_people(rng):
    teams = [s["team"] for s in SERVICES] + ["platform", "qa", "security"]
    names, used = [], set()
    pairs = [(f, l) for f in FIRST for l in LAST]
    rng.shuffle(pairs)
    for f, l in pairs:
        h = "@" + (f[0] + l).lower()
        if h in used:
            continue
        used.add(h)
        names.append((h, f"{f} {l}"))
    people, roster, i = {}, {}, 0
    for team in teams:
        size = 6 if team in {s["team"] for s in SERVICES} else 3
        members = names[i:i + size]
        i += size
        lead = members[0][0]
        roster[team] = [h for h, _ in members]
        for j, (h, n) in enumerate(members):
            people[h] = {"handle": h, "name": n, "team": team,
                         "seniority": "staff" if j == 0 else SENIORITY[(j + i) % 3],
                         "is_team_lead": j == 0, "team_lead": None if j == 0 else lead,
                         "out_of_office": False, "back_on": None}
    return people, roster


def rule_for(path, rules):
    win = None
    for r in rules:
        p = r["pattern"]
        if p == "*" or (p.endswith("/") and path.startswith(p)) or p == path:
            win = r
    return win


def derive(data, planted, weakened):
    """Gold from the data: written policy plus hidden rules."""
    pr, ci, co, people = data["pr"], data["ci"], data["codeowners"], data["people"]
    author = pr["author"]
    paths = [f["path"] for f in pr["files"]]
    sensitive = any(part in ("auth", "payments") for p in paths for part in p.split("/")[:-1])
    stale = ci["commit"] != pr["head_sha"]
    ci_block = ci["status"] != "passed" or ci["coverage_delta"] < -1.0
    reviewers, requested, sole_owner = {}, set(pr["requested_reviewers"]), False
    for p in paths:
        rule = rule_for(p, co["rules"])
        cands = [o for o in rule["owners"] if o != author]
        if not cands:
            sole_owner = True
            lead = people[author]["team_lead"]
            reviewers.setdefault(lead, set()).add("team_lead")
            continue
        if any(c in requested or c in reviewers for c in cands):
            continue
        pick = next(c for c in cands if not people[c]["out_of_office"])
        reviewers.setdefault(pick, set()).add("codeowner")
    if sensitive or any(f["category"] == "security" for f in planted):
        reviewers.setdefault(co["security_reviewer"], set()).add("security_review")
    if planted or ci_block:
        verdicts = ["request_changes"]
    elif weakened or sole_owner or stale:
        verdicts = ["comment", "request_changes"]
    else:
        verdicts = ["approve"]
    flags = {"tests_weakened": weakened, "sensitive_path": sensitive, "author_sole_owner": sole_owner,
             "stale_ci": stale}
    triggers = [rid for rid, f in (("no_approve_weakened_tests", weakened),
                                   ("security_review_sensitive_paths", sensitive),
                                   ("second_owner_for_self_owned", sole_owner),
                                   ("no_approve_stale_ci", stale)) if f]
    return {"verdicts": verdicts, "findings": planted,
            "reviewers": {k: sorted(v) for k, v in reviewers.items()},
            "security_reviewer": co["security_reviewer"], "flags": flags,
            "ignore_finding_files": [p for p in paths if p.startswith("tests/")] if weakened else []}, triggers


def _sha(rng, n=12):
    return "".join(rng.choice("0123456789abcdef") for _ in range(n))


# --- one task -------------------------------------------------------------------------------------------------------------
def build_task(idx, rng, people0, roster, diff, hidden):
    h1, h2, h3, h4 = ("H1" in hidden, "H2" in hidden, "H3" in hidden, "H4" in hidden)
    if h2:
        svc = rng.choice([s for s in SERVICES if "sens" in s])
        module = rng.choice(svc["sens_modules"])
        modpath, mod_file = f'{svc["sens"]}.{module}', f'src/{svc["pkg"]}/{svc["sens"]}/{module}.py'
    else:
        svc = rng.choice(SERVICES)
        module = rng.choice(svc["modules"])
        modpath, mod_file = module, f'src/{svc["pkg"]}/{module}.py'
    ctx = {"noun": svc["noun"], "table": svc["table"], "CONST": svc["CONST"], "pkg": svc["pkg"],
           "modpath": modpath, "repo": svc["repo"], "Title": module.capitalize()}
    handlers_file, jobs_file = f'src/{svc["pkg"]}/handlers.py', f'src/{svc["pkg"]}/jobs.py'
    test_file = f"tests/test_{module}.py"

    # how many plants and decoys
    hidden_noapprove = h1 or h3 or h4
    if diff == "easy":
        n_plant = rng.choice([0, 0, 1])
        n_decoy, n_clean_new, harmless = 0, (1 if True else 0), 0
    elif diff == "medium":
        n_plant = rng.choice([0, 1])
        n_decoy, n_clean_new, harmless = 1, rng.choice([0, 1]), rng.choice([0, 1])
    else:
        n_plant = rng.choice([0, 1, 1, 2])
        n_decoy, n_clean_new, harmless = rng.choice([1, 2]), rng.choice([0, 1]), rng.choice([1, 2])
    if hidden_noapprove and rng.random() < 0.8:
        n_plant = 0
    if h2 and rng.random() < 0.8:
        # keep the hidden security-review rule decisive: no planted security issue
        plant_pool = [k for k in CATEGORY if CATEGORY[k] != "security"]
    else:
        plant_pool = list(CATEGORY)
    if diff != "hard":
        plant_pool = [k for k in plant_pool if k not in HARD_PLANTS]
    used_fam = set()
    plants = []
    for _ in range(n_plant):
        k = rng.choice([k for k in plant_pool if FAMILY[k] not in used_fam])
        plants.append(k)
        used_fam.add(FAMILY[k])
    decoy_pool = [k for k in DECOY_FAMILY if diff == "hard" or k not in HARD_DECOYS]
    decoys = []
    for _ in range(n_decoy):
        opts = [k for k in decoy_pool if DECOY_FAMILY[k] not in used_fam]
        k = rng.choice(opts)
        decoys.append(k)
        used_fam.add(DECOY_FAMILY[k])
    clean_new = []
    if n_plant == 0 and n_decoy == 0:
        n_clean_new = max(n_clean_new, 1)
    for _ in range(n_clean_new):
        opts = [f for f in ("recent", "settled", "page", "gaps", "email", "archive") if f not in used_fam]
        f = rng.choice(opts)
        clean_new.append(f)
        used_fam.add(f)

    # --- assemble head versions
    consts, funcs_new, tests_new = [], [], []
    ref_t, total_t, val_t, fee_t = E_REF, E_TOTAL, E_VALIDATE, E_FEE
    test_fee = T_FEE
    handlers_arg = jobs_arg = ""
    planted_tags = []   # (tag_name, file, category)
    tests_changed_for = set()

    def add_new(fam, variant):
        """variant: 'ok' or a planted kind."""
        nonlocal val_t, fee_t, test_fee, handlers_arg, jobs_arg
        tag = f"P{len(planted_tags)}"
        if fam in ("recent", "settled", "page", "email"):
            src = NEW[fam][0] if variant == "ok" else NEW[fam][1]
            funcs_new.append(src.replace("#@T", "#@" + tag))
            tests_new.append(TESTS[fam])
        elif fam == "gaps":
            funcs_new.append(NEW["gaps"][0])
            tests_new.append(TESTS["gaps"])
        elif fam == "sync":
            src = {"ok": NEW["sync"][0], "swallow_pass": NEW["sync_pass"], "swallow_return": NEW["sync_return"]}[variant]
            funcs_new.append(src.replace("#@T", "#@" + tag))
            tests_new.append(TESTS["sync"])
        elif fam == "sql":
            src = NEW[variant]
            if variant == "sql_const_table":
                consts.append('<CONST>_TABLE = "<table>"')
            funcs_new.append(src.replace("#@T", "#@" + tag))
            tests_new.append(TESTS["sql"])
        elif fam == "secret":
            if variant == "secret":
                key = "sk_live_" + "".join(rng.choice("abcdefghijkmnpqrstuvwxyz23456789") for _ in range(20))
                consts.append(f'<CONST>_API_KEY = "{key}"  #@{tag}')
            else:
                consts.append('<CONST>_API_KEY = os.environ.get("<CONST>_API_KEY", "")')
            funcs_new.append(NEW["auth_header"])
            tests_new.append(TESTS["secret"])
        elif fam == "archive":
            if variant == "newfn_untested":
                funcs_new.append(NEW["archive_untested"].replace("#@T", "#@" + tag))
            else:
                funcs_new.append(NEW["archive"])
                tests_new.append(TESTS["archive"])
        elif fam == "branch":
            consts.append("MAX_<CONST>_AMOUNT = 50000")
            val_t = E_VALIDATE_BRANCH.replace("#@T", "#@" + tag)
            if variant == "branch_tested":
                tests_new.append(TESTS["branch"])
        elif fam == "sig":
            if variant == "sig_default":
                fee_t = E_FEE_DEFAULT
            else:
                fee_t = E_FEE_REQUIRED.replace("#@T", "#@" + tag)
                test_fee = T_FEE_REGION
                if variant in ("sig_partial", "sig_updated"):
                    handlers_arg = ", order.region"
                if variant == "sig_updated":
                    jobs_arg = ", o.region"
        if variant not in ("ok",) and variant in CATEGORY:
            file = mod_file
            planted_tags.append((tag, file, CATEGORY[variant], variant))

    decoy_variant = {"recent_ok": ("recent", "ok"), "settled_ok": ("settled", "ok"), "page_ok": ("page", "ok"),
                     "gaps": ("gaps", "ok"), "email_ok": ("email", "ok"), "sync_ok": ("sync", "ok"),
                     "sql_param": ("sql", "sql_param"), "sql_const_table": ("sql", "sql_const_table"),
                     "secret_env": ("secret", "env"), "sig_default": ("sig", "sig_default"),
                     "sig_updated": ("sig", "sig_updated"), "branch_tested": ("branch", "branch_tested"),
                     "archive_ok": ("archive", "ok")}
    order = [("p", k) for k in plants] + [("d", k) for k in decoys] + [("c", f) for f in clean_new]
    rng.shuffle(order)
    for kind, k in order:
        if kind == "p":
            add_new(FAMILY[k], k)
        elif kind == "d":
            add_new(*decoy_variant[k])
        else:
            add_new(k, "ok")

    harmless_opts = ["ref_doc", "total_sum"] + ([] if val_t != E_VALIDATE else ["validate_log"])
    for hk in rng.sample(harmless_opts, min(harmless, len(harmless_opts))):
        if hk == "ref_doc":
            ref_t = E_REF_DOC
        elif hk == "total_sum":
            total_t = E_TOTAL_SUM
        else:
            val_t = E_VALIDATE_LOG

    # tests file
    weak_kind = None
    t_ref, t_total = T_REF, T_TOTAL
    if h1:
        weak_kind = rng.choice(["del_assert", "skip", "delete_fn"])
        if weak_kind == "del_assert":
            t_total = T_TOTAL_WEAK
        elif weak_kind == "skip":
            t_ref = T_REF_SKIP
    base_tests = [T_REF, T_TOTAL, T_VALIDATE, T_FEE]
    head_tests = ([] if weak_kind == "delete_fn" else [t_ref]) + [t_total, T_VALIDATE, test_fee] + tests_new

    base_mod = module_text(ctx, [], [E_REF, E_TOTAL, E_VALIDATE, E_FEE])
    head_mod = module_text(ctx, consts, [ref_t, total_t, val_t, fee_t] + funcs_new)
    files_base = {
        mod_file: plain(base_mod),
        handlers_file: plain(block(HANDLERS.replace("<ARG>", ""), ctx)),
        jobs_file: plain(block(JOBS.replace("<ARG>", ""), ctx)),
        test_file: plain(tests_text(ctx, base_tests)),
        "tests/fakes.py": plain(block(FAKES, ctx)),
        f'src/{svc["pkg"]}/__init__.py': [f'"""The {svc["pkg"]} service."""'],
    }
    files_head = dict(files_base)
    files_head[mod_file] = plain(head_mod)
    files_head[handlers_file] = plain(block(HANDLERS.replace("<ARG>", handlers_arg), ctx))
    files_head[jobs_file] = plain(block(JOBS.replace("<ARG>", jobs_arg), ctx))
    files_head[test_file] = plain(tests_text(ctx, head_tests))

    # planted line numbers
    planted = []
    for tag, file, cat, kind in planted_tags:
        line = next(i + 1 for i, (_, t) in enumerate(head_mod) if t == tag)
        planted.append({"file": file, "line": line, "category": cat, "kind": kind})

    changed = [p for p in (mod_file, handlers_file, jobs_file, test_file) if files_base[p] != files_head[p]]
    diffs, pr_files = {}, []
    for p in changed:
        d = udiff(p, files_base[p], files_head[p])
        diffs[p] = d
        adds = sum(1 for x in d.split("\n") if x.startswith("+") and not x.startswith("+++"))
        dels = sum(1 for x in d.split("\n") if x.startswith("-") and not x.startswith("---"))
        pr_files.append({"path": p, "additions": adds, "deletions": dels})

    # --- people, codeowners
    people = {h: dict(p) for h, p in people0.items()}
    team = roster[svc["team"]]
    lead, members = team[0], team[1:]
    author = rng.choice(members)
    others = [m for m in members if m != author]
    rng.shuffle(others)
    src_owners = others[:2]
    if diff != "easy" and rng.random() < 0.4:
        src_owners = [author] + src_owners          # author co-owns: skip them
    if rng.random() < 0.3:
        src_owners.append(lead)
    qa = roster["qa"]
    tests_owners = [rng.choice(qa), others[2]] if rng.random() < 0.5 else [others[2], rng.choice(qa)]
    platform = roster["platform"]
    rules = [{"pattern": "*", "owners": [rng.choice(platform)]},
             {"pattern": f'src/{svc["pkg"]}/', "owners": src_owners}]
    if "sens" in svc:
        sens_owners = [others[3], others[1]] if rng.random() < 0.5 else [others[1], others[3]]
        rules.append({"pattern": f'src/{svc["pkg"]}/{svc["sens"]}/', "owners": sens_owners})
    if diff == "hard":
        rules.append({"pattern": f'src/{svc["pkg"]}/legacy/', "owners": [rng.choice(others)]})
        if rng.random() < 0.5:
            rules.append({"pattern": jobs_file, "owners": [rng.choice(platform)]})
    rules.append({"pattern": "tests/", "owners": tests_owners})
    rules.append({"pattern": "docs/", "owners": [rng.choice(platform)]})
    if h3:
        rules.append({"pattern": mod_file, "owners": [author]})
    elif diff != "easy" and rng.random() < 0.25:
        rules.append({"pattern": mod_file, "owners": [author, rng.choice(others[:2])]})
    sec_reviewer = rng.choice(roster["security"])
    codeowners = {"repo": svc["repo"], "rules": rules, "security_reviewer": sec_reviewer}

    # requested reviewers already on the PR
    requested = []
    mod_rule = rule_for(mod_file, rules)
    mod_cands = [o for o in mod_rule["owners"] if o != author]
    if diff != "easy" and len(mod_cands) >= 2 and rng.random() < 0.4:
        requested = [mod_cands[1]]

    # out of office: hard tasks put the first candidate of the module's rule out
    protected = set(requested) | {lead, author, sec_reviewer}
    if diff == "hard" and len(mod_cands) >= 2 and not requested and mod_cands[0] not in protected \
            and rng.random() < 0.6:
        people[mod_cands[0]]["out_of_office"] = True
        people[mod_cands[0]]["back_on"] = f"2026-11-{rng.randint(2, 20):02d}"
    owners_all = {o for r in rules for o in r["owners"]}
    noise = [h for h in people if h not in owners_all and h not in protected]
    for h in rng.sample(noise, 2):
        people[h]["out_of_office"] = True
        people[h]["back_on"] = f"2026-11-{rng.randint(2, 20):02d}"

    # CI
    head_sha = _sha(rng)
    ci_commit = head_sha
    if h4:
        ci_commit = head_sha[:4] + _sha(rng, 8) if diff == "hard" else _sha(rng)
    other_tests = rng.randint(40, 120)
    n_tests = other_tests + len(head_tests)
    status, failing, cov = "passed", [], round(rng.uniform(-0.6, 1.4), 1)
    roll = rng.random()
    if not hidden_noapprove and not h2:
        if roll < 0.08:
            status = "failed"
            failing = [f"{test_file}::test_total_sums_lines"]
        elif roll < 0.15:
            cov = round(rng.uniform(-3.0, -1.1), 1)
        elif roll < 0.22 and diff == "hard":
            cov = -1.0
    skipped = 1 if weak_kind == "skip" else 0
    ci = {"pr": None, "commit": ci_commit, "status": status,
          "tests": {"passed": n_tests - skipped - len(failing), "failed": len(failing), "skipped": skipped},
          "failing_tests": failing, "coverage_delta": cov,
          "finished_at": f"2026-10-{rng.randint(10, 17):02d}T{rng.randint(8, 18):02d}:{rng.randint(0, 59):02d}:00Z"}

    pr_num = 1100 + idx * 7 + rng.randint(0, 5)
    new_names = []
    for f in funcs_new:
        name = f.split("(")[0].replace("def ", "")
        new_names.append(_sub(name, ctx))
    title_bits = []
    if new_names:
        title_bits.append("Add " + ", ".join(f"`{n}`" for n in new_names[:2]))
    if fee_t != E_FEE:
        title_bits.append("regional fees")
    if val_t == E_VALIDATE_BRANCH or "MAX_" in "".join(consts):
        title_bits.append("amount limit")
    if not title_bits:
        title_bits.append("Tidy up helpers")
    title = "; ".join(title_bits)
    title = title[0].upper() + title[1:]
    desc = f"Changes in `{mod_file}`."
    if weak_kind and rng.random() < 0.5:
        desc += {"del_assert": " Dropped an assertion that kept flaking.",
                 "skip": " Skipping a flaky test for now, will fix in a follow-up.",
                 "delete_fn": " Removed an outdated test."}[weak_kind]
    if h4 and rng.random() < 0.3:
        desc += " Pushed a small follow-up commit after review comments."
    if harmless:
        desc += " Also a small cleanup."
    labels = sorted(set(rng.sample(["feature", "refactor", "chore", "backend", "needs-review"], 2)))
    updated = f"2026-10-{rng.randint(10, 17):02d}T{rng.randint(8, 18):02d}:{rng.randint(0, 59):02d}:00Z"
    pr = {"number": pr_num, "repo": svc["repo"], "title": title, "description": desc, "author": author,
          "labels": labels, "files": pr_files, "head_sha": head_sha, "base_branch": "main",
          "requested_reviewers": requested, "draft": False, "updated_at": updated}
    ci["pr"] = pr_num

    data = {"repo": svc["repo"], "pr": pr, "diffs": diffs,
            "files": {p: "\n".join(v) for p, v in files_head.items()},
            "ci": ci, "codeowners": codeowners, "people": people}
    gold, triggers = derive(data, [{k: v for k, v in f.items()} for f in planted], weak_kind is not None)
    req = rng.choice([
        f"Please review PR #{pr_num} in {svc['repo']}.",
        f"Can you review {svc['repo']} PR #{pr_num}? {people[author]['name']} wants to merge it today.",
        f"Review request: {svc['repo']}#{pr_num}. Submit your review and request any reviewers it needs.",
        f"PR #{pr_num} ({svc['repo']}) is ready for review.",
    ])
    task = {"id": f"prr-{idx:03d}", "request": req, "difficulty": diff, "triggers": triggers, "gold": gold,
            "meta": {"plants": plants, "decoys": decoys, "clean_new": clean_new, "weak_kind": weak_kind,
                     "pr": pr_num, "repo": svc["repo"]}}
    return task, data


def build_all():
    rng = random.Random(SEED)
    people, roster = build_people(rng)
    diffs = (["easy", "medium", "hard"] * (N_TASKS // 3 + 1))[:N_TASKS]
    rng.shuffle(diffs)
    idx = list(range(N_TASKS))
    rng.shuffle(idx)
    hidden = {i: set() for i in range(N_TASKS)}
    plan = [("H2", 17), ("H1", 16), ("H3", 15), ("H4", 15)]
    pos = 0
    groups = {}
    for h, n in plan:
        groups[h] = idx[pos:pos + n]
        for i in groups[h]:
            hidden[i].add(h)
        pos += n
    for i in groups["H2"][:3]:
        hidden[i].add("H3")
    for i in groups["H1"][:2]:
        hidden[i].add("H4")
    tasks, data = [], {}
    for i in range(N_TASKS):
        t, d = build_task(i, rng, people, roster, diffs[i], hidden[i])
        tasks.append(t)
        data[t["id"]] = d
    return tasks, data
