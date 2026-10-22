"""Generate the fintech domain: a synthetic bank (db.json) plus scenarios with ground truth by construction.

Every scenario gets its own customer, with exactly the transactions the scenario is about injected into
an ordinary 120-day history, so the request is unambiguous. Gold actions (verify_identity, then the
writes the policy requires) are computed from the policy and executed with the domain's own tools on a
fresh copy of the DB; scenarios whose gold actions fail are dropped.

  python -m swapbench.fintech.gen <out_dir> --n 500 --seed 1 [--splits train:60,test:240,pool:200] [--kinds all|single|composite]
"""
import argparse
import copy
import json
import os
import random
import shutil
from datetime import timedelta

from .domain import TODAY, FintechDB, FintechTools

FIRST = ["Maria", "James", "Aisha", "Wei", "Lucas", "Fatima", "Noah", "Sofia", "Omar", "Elena", "Daniel", "Priya", "Mateo",
         "Hana", "Ethan", "Chloe", "Ivan", "Amara", "Leo", "Nina", "Samuel", "Yara", "Victor", "Grace", "Tomas", "Leila",
         "Henry", "Zoe", "Arjun", "Mila", "Felix", "Ines", "Kofi", "Rosa", "Jonas", "Mei", "Adam", "Clara", "Diego", "Sara"]
LAST = ["Lopez", "Smith", "Khan", "Chen", "Silva", "Rahman", "Brown", "Rossi", "Haddad", "Petrova", "Kim", "Patel",
        "Garcia", "Sato", "Miller", "Dubois", "Novak", "Okafor", "Weber", "Costa", "Nguyen", "Ahmed", "Moreau", "Jensen",
        "Kowalski", "Fischer", "Ali", "Santos", "Murphy", "Andersen", "Ibrahim", "Tanaka", "Romero", "Larsen", "Mensah"]
MERCHANTS = [("FreshMart Grocery", 12, 160), ("City Transit", 2.5, 45), ("Bolt Rides", 6, 60), ("Cafe Aroma", 3, 18),
             ("StreamFlix", 9.99, 22.99), ("ElectroHub", 25, 900), ("HomeNest Furniture", 60, 1400),
             ("PetPal Supplies", 8, 120), ("SkyAir Tickets", 90, 980), ("GymPro Membership", 25, 70),
             ("BookNook", 7, 65), ("Pharma+ Drugstore", 4, 80), ("QuickFuel", 20, 95), ("Lumen Utilities", 40, 210),
             ("TechStore Online", 15, 1200), ("Bistro Verde", 18, 140), ("CloudBox Storage", 2.99, 9.99),
             ("Urban Threads", 20, 260), ("ToyTown", 9, 150), ("Harbor Hotel", 110, 650)]


def d(days_ago):
    return (TODAY - timedelta(days=days_ago)).isoformat()


class Bank:
    def __init__(self, rng):
        self.rng = rng
        self.db = {"customers": {}, "accounts": {}, "cards": {}, "transactions": {}, "events": [], "session": {}}
        self.n = {"cus": 10000, "acc": 20000, "card": 50000, "txn": 700000}
        self.names = set()

    def _id(self, k):
        self.n[k] += 1
        return f"{k}_{self.n[k]}"

    def txn(self, acc, days_ago, merchant, amount, kind="purchase", fee_type=None, status=None):
        a = self.db["accounts"][acc]
        tid = self._id("txn")
        self.db["transactions"][tid] = {
            "transaction_id": tid, "account_id": acc, "card_id": a["card_ids"][0] if kind == "purchase" else None,
            "date": d(days_ago), "merchant": merchant, "amount": round(amount, 2), "kind": kind, "fee_type": fee_type,
            "status": status or ("pending" if days_ago <= 1 and kind == "purchase" else "posted"), "disputed": False}
        return self.db["transactions"][tid]

    def customer(self):
        r = self.rng
        while True:
            name = f"{r.choice(FIRST)} {r.choice(LAST)}"
            if name not in self.names:
                break
            if len(self.names) > len(FIRST) * len(LAST) * 0.8:
                name = f"{name} {r.choice('ABCDEFGHJKLMNPRSTVW')}."  # middle initial once names run out
                if name not in self.names:
                    break
        self.names.add(name)
        cid = self._id("cus")
        dob = f"{r.randint(1950, 2002)}-{r.randint(1, 12):02d}-{r.randint(1, 28):02d}"
        cus = {"customer_id": cid, "full_name": name, "date_of_birth": dob, "phone_last4": f"{r.randint(0, 9999):04d}",
               "email": name.lower().replace(" ", ".").replace("..", ".") + f"{r.randint(1, 99)}@example.com", "account_ids": []}
        self.db["customers"][cid] = cus
        for typ in ["checking"] + (["credit_card"] if r.random() < 0.5 else []):
            acc, card = self._id("acc"), self._id("card")
            self.db["accounts"][acc] = {"account_id": acc, "customer_id": cid, "type": typ,
                                        "balance": round(r.uniform(150, 9000), 2), "card_ids": [card]}
            self.db["cards"][card] = {"card_id": card, "account_id": acc, "last4": f"{r.randint(0, 9999):04d}", "status": "active"}
            cus["account_ids"].append(acc)
            for _ in range(r.randint(14, 22)):  # ordinary history: no fees, no duplicates
                m, lo, hi = r.choice(MERCHANTS)
                self.txn(acc, r.randint(0, 120), m, r.uniform(lo, min(hi, 300)) + r.random() / 100)
            if typ == "checking":
                for k in range(4):
                    self.txn(acc, 7 + 30 * k, "Payroll deposit", r.uniform(1800, 4200), kind="deposit")
        return cus

    def accounts_of(self, cus, typ=None):
        return [a for a in cus["account_ids"] if typ is None or self.db["accounts"][a]["type"] == typ]


def money(x):
    return f"${x:,.2f}"


class Scenarios:
    """Each method returns (instruction text, gold write actions) for a customer, mutating the bank."""

    def __init__(self, bank, rng):
        self.b, self.r = bank, rng

    def _acc(self, cus):
        return self.r.choice(cus["account_ids"])

    def _fee(self, cus, fee_type, amount, days_ago):
        acc = self.b.accounts_of(cus, "checking")[0] if fee_type in ("overdraft", "atm") else self._acc(cus)
        label = {"overdraft": "Overdraft fee", "late_payment": "Late payment fee", "foreign_transaction": "Foreign transaction fee",
                 "atm": "ATM withdrawal fee"}[fee_type]
        return self.b.txn(acc, days_ago, label, amount, kind="fee", fee_type=fee_type)

    def fee_ok(self, cus, capped=False):
        ft = self.r.choice(["overdraft", "late_payment", "foreign_transaction"])
        amt = self.r.choice([45.0, 48.0, 50.0]) if capped else {"overdraft": 35.0, "late_payment": 29.0,
                                                                  "foreign_transaction": round(self.r.uniform(2.5, 14), 2)}[ft]
        t = self._fee(cus, ft, amt, self.r.randint(3, 80))
        text = (f"You noticed a {money(amt)} {t['merchant'].lower()} on {t['date']} and want it refunded. "
                "Accept whatever amount the agent says the policy allows.")
        return text, [("issue_refund", {"transaction_id": t["transaction_id"], "amount": min(amt, 40.0), "reason": "fee_refund"})]

    def fee_already(self, cus):
        ft = self.r.choice(["overdraft", "late_payment"])
        t = self._fee(cus, ft, 35.0 if ft == "overdraft" else 29.0, self.r.randint(3, 60))
        self.b.txn(self._acc(cus), self.r.randint(120, 330), "Fee refund", -35.0, kind="fee_refund")
        return (f"You want the {money(t['amount'])} {t['merchant'].lower()} from {t['date']} refunded. If the agent says you "
                "are not eligible, push back once, then accept it. Do not ask for a human.", [])

    def fee_atm(self, cus):
        t = self._fee(cus, "atm", 3.5, self.r.randint(3, 60))
        return (f"You want the {money(t['amount'])} ATM withdrawal fee from {t['date']} refunded. If the agent says it "
                "can't be refunded, accept it. Do not ask for a human.", [])

    def _dup_pair(self, cus, amount):
        acc = self._acc(cus)
        m = self.r.choice(["ElectroHub", "TechStore Online", "HomeNest Furniture", "Harbor Hotel", "SkyAir Tickets",
                           "Urban Threads", "Bistro Verde", "FreshMart Grocery"])
        da = self.r.randint(4, 40)
        t1 = self.b.txn(acc, da, m, amount)
        t2 = self.b.txn(acc, da - 1, m, amount)  # one day apart: "the later one" is unambiguous
        later = max((t1, t2), key=lambda t: (t["date"], t["transaction_id"]))
        return m, later

    def dup_ok(self, cus):
        amt = round(self.r.uniform(19, 480), 2)
        m, later = self._dup_pair(cus, amt)
        return (f"You were charged twice by {m} for {money(amt)} around {later['date']} and want the duplicate refunded.",
                [("issue_refund", {"transaction_id": later["transaction_id"], "amount": amt, "reason": "duplicate_charge"})])

    def dup_large(self, cus):
        amt = round(self.r.uniform(520, 1500), 2)
        m, later = self._dup_pair(cus, amt)
        return (f"You were charged twice by {m} for {money(amt)} around {later['date']} and want the duplicate refunded. "
                "If the agent says it must go to a specialist, agree.",
                [("escalate_to_human", {"reason": "refund_over_limit", "summary": "duplicate charge over limit"})])

    def dup_not_really(self, cus):
        acc = self._acc(cus)
        m = self.r.choice(["Bistro Verde", "QuickFuel", "FreshMart Grocery", "Bolt Rides"])
        a1 = round(self.r.uniform(20, 120), 2)
        t1 = self.b.txn(acc, self.r.randint(10, 30), m, a1)
        t2 = self.b.txn(acc, int((TODAY - __import__("datetime").date.fromisoformat(t1["date"])).days) - 5, m, a1)
        return (f"You think {m} charged you twice ({money(a1)} on {t1['date']} and again on {t2['date']}) and want one "
                "refunded. In fact you did visit twice, but you only remember that if the agent points out the dates are "
                "several days apart; then accept that it is not a duplicate. Do not ask for anything else.", [])

    def dispute(self, cus, reason):
        acc = self._acc(cus)
        m, lo, hi = self.r.choice([x for x in MERCHANTS if x[2] >= 60])
        t = self.b.txn(acc, self.r.randint(5, 55), m, round(self.r.uniform(max(lo, 30), min(hi, 450)), 2))
        why = {"item_not_received": "you paid but never received the order",
               "incorrect_amount": f"you agreed to pay {money(round(t['amount'] * 0.8, 2))} but were charged more"}[reason]
        return (f"You want to dispute the {money(t['amount'])} charge from {m} on {t['date']} because {why}.",
                [("open_dispute", {"transaction_id": t["transaction_id"], "reason": reason})])

    def dispute_old(self, cus):
        acc = self._acc(cus)
        m, lo, hi = self.r.choice([x for x in MERCHANTS if x[2] >= 60])
        t = self.b.txn(acc, self.r.randint(66, 88), m, round(self.r.uniform(max(lo, 30), min(hi, 450)), 2))
        return (f"You want to dispute the {money(t['amount'])} charge from {m} on {t['date']} because the order never "
                "arrived. If the agent says it is too late, push back once, then accept it.", [])

    def dispute_pending(self, cus):
        acc = self._acc(cus)
        m, lo, hi = self.r.choice([x for x in MERCHANTS if x[2] >= 60])
        t = self.b.txn(acc, self.r.choice([0, 1]), m, round(self.r.uniform(max(lo, 30), min(hi, 450)), 2), status="pending")
        return (f"You want to dispute the {money(t['amount'])} charge from {m} on {t['date']}: you cancelled that order. "
                "If the agent says you have to wait, accept it.", [])

    def unauthorized(self, cus):
        acc = self._acc(cus)
        m, lo, hi = self.r.choice([x for x in MERCHANTS if x[2] >= 100])
        t = self.b.txn(acc, self.r.randint(2, 40), m, round(self.r.uniform(60, min(hi, 700)), 2))
        last4 = self.b.db["cards"][t["card_id"]]["last4"]
        return (f"You see a {money(t['amount'])} charge from {m} on {t['date']} on your card ending {last4} that you did not "
                "make. You still have the card. Agree to what the agent proposes.",
                [("freeze_card", {"card_id": t["card_id"], "reason": "suspected_fraud"}),
                 ("open_dispute", {"transaction_id": t["transaction_id"], "reason": "unauthorized"})])

    def freeze_lost(self, cus):
        acc = self._acc(cus)
        card = self.b.db["accounts"][acc]["card_ids"][0]
        last4 = self.b.db["cards"][card]["last4"]
        return (f"You lost your card ending {last4} and want it frozen right away.",
                [("freeze_card", {"card_id": card, "reason": "lost_or_stolen"})])

    def human(self, cus):
        return ("You don't want to deal with an automated assistant: ask to be put through to a human agent and insist on "
                "it. Do not explain what your issue is. Answer verification questions if asked.", [("escalate_to_human", {"reason": "customer_request", "summary": "asked for a human"})])

    def out_of_scope(self, cus):
        return ("You want your credit card limit raised to $15,000. Accept whatever the agent can do.",
                [("escalate_to_human", {"reason": "out_of_scope", "summary": "credit limit increase"})])

    def id_fail(self, cus):
        y, mth, day = cus["date_of_birth"].split("-")
        wrong1 = f"{int(y) + 1}-{mth}-{day}"
        wrong2 = f"{y}-{day}-{mth}" if int(day) <= 12 and day != mth else f"{int(y) - 1}-{mth}-{day}"
        return (f"You want to freeze your card because you misplaced it. When asked for your date of birth, give {wrong1}. "
                f"If told it does not match, apologise and give {wrong2}. Never give any other date of birth. "
                "Accept whatever the agent does next.",
                [("escalate_to_human", {"reason": "identity_verification_failed", "summary": "verification failed twice"})])


SINGLE = {"fee_ok": lambda s, c: s.fee_ok(c), "fee_capped": lambda s, c: s.fee_ok(c, capped=True),
          "fee_already": lambda s, c: s.fee_already(c), "fee_atm": lambda s, c: s.fee_atm(c),
          "dup_ok": lambda s, c: s.dup_ok(c), "dup_large": lambda s, c: s.dup_large(c),
          "dup_not_really": lambda s, c: s.dup_not_really(c),
          "dispute_not_received": lambda s, c: s.dispute(c, "item_not_received"),
          "dispute_amount": lambda s, c: s.dispute(c, "incorrect_amount"),
          "dispute_old": lambda s, c: s.dispute_old(c), "dispute_pending": lambda s, c: s.dispute_pending(c),
          "unauthorized": lambda s, c: s.unauthorized(c), "freeze_lost": lambda s, c: s.freeze_lost(c),
          "human": lambda s, c: s.human(c), "out_of_scope": lambda s, c: s.out_of_scope(c), "id_fail": lambda s, c: s.id_fail(c)}
ENDING = {"dup_large", "human", "out_of_scope"}  # these end the conversation (escalation): only last in a composite
NO_COMPOSITE = {"id_fail"}
FEE = {"fee_ok", "fee_capped", "fee_already", "fee_atm"}

PERSONAS = ["You are polite and patient.", "You are in a hurry and keep your messages short.",
            "You are anxious about your money and want reassurance.", "You are friendly and chatty.",
            "You are irritated about the bank and say so, but you cooperate.",
            "You are careful and ask the agent to repeat amounts before confirming."]
CONFIRM = ("When the agent describes an action and asks you to confirm, check it matches what you want and answer yes. "
           "Only give your identity details when asked. If the agent says you are being transferred to a specialist, "
           "end the conversation.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out_dir")
    ap.add_argument("--n", type=int, default=500)
    ap.add_argument("--seed", type=int, default=1)
    ap.add_argument("--kinds", default="all", help="all | single | composite")
    ap.add_argument("--composite-share", type=float, default=0.6)
    ap.add_argument("--splits", help="e.g. train:60,test:240,pool:200 (generation order)")
    ap.add_argument("--prefix", default="f")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    bank = Bank(rng)
    sc = Scenarios(bank, rng)
    for _ in range(150):  # background customers nobody calls about
        bank.customer()
    tasks, counts = [], {}
    for i in range(a.n):
        composite = a.kinds == "composite" or (a.kinds == "all" and rng.random() < a.composite_share)
        for _attempt in range(20):
            before = {k: set(bank.db[k]) for k in ("customers", "accounts", "cards", "transactions")}
            snapshot = dict(bank.n), set(bank.names)
            cus = bank.customer()
            if composite:
                k = rng.choice([2, 3])
                kinds, has_fee = [], False
                pool = [x for x in SINGLE if x not in NO_COMPOSITE]
                while len(kinds) < k:
                    x = rng.choice(pool)
                    if x in kinds or (x in FEE and has_fee) or (x in ENDING and len(kinds) < k - 1):
                        continue
                    if {x} | set(kinds) >= {"freeze_lost", "unauthorized"}:  # could target the same card twice
                        continue
                    has_fee |= x in FEE
                    kinds.append(x)
                parts = [SINGLE[x](sc, cus) for x in kinds]
                order = ["First", "Second", "Third"]
                text = ("You have several things to sort out and raise them one at a time, moving on once each is "
                        "resolved. " + " ".join(f"{order[j]}: {t}" for j, (t, _) in enumerate(parts)))
                writes = [w for _, ws in parts for w in ws]
                kind = "composite:" + "+".join(kinds)
            else:
                kind = rng.choice(list(SINGLE))
                text, writes = SINGLE[kind](sc, cus)
            gold = [] if kind == "id_fail" else [("verify_identity", {"full_name": cus["full_name"],
                                                                      "date_of_birth": cus["date_of_birth"],
                                                                      "phone_last4": cus["phone_last4"]})]
            gold += writes
            try:  # gold must execute cleanly; only this customer's records matter, so validate on those
                accs = set(cus["account_ids"])
                sub = {"customers": {cus["customer_id"]: cus},
                       "accounts": {k: v for k, v in bank.db["accounts"].items() if k in accs},
                       "cards": {k: v for k, v in bank.db["cards"].items() if v["account_id"] in accs},
                       "transactions": {k: v for k, v in bank.db["transactions"].items() if v["account_id"] in accs},
                       "events": [], "session": {}}
                tools = FintechTools(FintechDB.model_validate(copy.deepcopy(sub)))
                for name, args in gold:
                    getattr(tools, name)(**args)
                break
            except Exception:  # roll back this customer's records
                for k, ids in before.items():
                    for x in set(bank.db[k]) - ids:
                        del bank.db[k][x]
                bank.n, bank.names = snapshot
        else:
            continue
        tid = f"{a.prefix}{len(tasks)}"
        known = f"You are {cus['full_name']}, born {cus['date_of_birth']}; your phone number ends in {cus['phone_last4']}."
        if kind == "id_fail":
            known = f"You are {cus['full_name']}; your phone number ends in {cus['phone_last4']}."
        tasks.append({
            "id": tid,
            "description": {"purpose": f"swapbench fintech: {kind}", "relevant_policies": None, "notes": f"seed {a.seed}"},
            "user_scenario": {"persona": None, "instructions": {
                "task_instructions": rng.choice(PERSONAS) + " " + CONFIRM, "domain": "fintech",
                "reason_for_call": text, "known_info": known,
                "unknown_info": "You do not know your customer id, account ids or card ids."}},
            "initial_state": None,
            "evaluation_criteria": {"actions": [{"action_id": f"{tid}_{j}", "name": n, "arguments": args, "info": None}
                                                for j, (n, args) in enumerate(gold)],
                                    "communicate_info": [], "nl_assertions": [], "reward_basis": ["DB"]},
        })
        counts[kind.split(":")[0] if not kind.startswith("composite") else "composite"] = counts.get(
            kind.split(":")[0] if not kind.startswith("composite") else "composite", 0) + 1
    os.makedirs(a.out_dir, exist_ok=True)
    FintechDB.model_validate(bank.db)
    json.dump(bank.db, open(os.path.join(a.out_dir, "db.json"), "w"))
    shutil.copy(os.path.join(os.path.dirname(os.path.abspath(__file__)), "policy.md"), os.path.join(a.out_dir, "policy.md"))
    json.dump(tasks, open(os.path.join(a.out_dir, "tasks.json"), "w"), indent=1)
    ids = [t["id"] for t in tasks]
    splits, i = {"base": ids}, 0
    if a.splits:
        for part in a.splits.split(","):
            name, k = part.split(":")
            splits[name] = ids[i:i + int(k)]
            i += int(k)
    json.dump(splits, open(os.path.join(a.out_dir, "split_tasks.json"), "w"), indent=1)
    print(f"wrote {len(tasks)} scenarios, {len(bank.db['customers'])} customers, {len(bank.db['transactions'])} "
          f"transactions to {a.out_dir}: {counts}")


if __name__ == "__main__":
    main()
