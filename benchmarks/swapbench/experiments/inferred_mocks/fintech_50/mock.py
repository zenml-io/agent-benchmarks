"""Stateful mock of the Northbank support-agent tool API, inferred from production traces.

Standard library only. See NOTES.md for the inferred rules and the list of guesses.
"""
import copy
import datetime

TODAY = datetime.date(2026, 10, 1)

FEE_REFUND_REASONS = ("fee_refund", "duplicate_charge")
DISPUTE_REASONS = ("unauthorized", "item_not_received", "incorrect_amount")
FREEZE_REASONS = ("lost_or_stolen", "suspected_fraud", "customer_request")
ESCALATE_REASONS = ("identity_verification_failed", "refund_over_limit",
                    "customer_request", "out_of_scope")
ESCALATE_MESSAGE = "Escalated. A specialist will take over this conversation."

GUESSES = {
    "verify_failed": "verify_identity with no matching customer: traces never show a failure. "
                     "Returns {'verified': False, 'customer_id': None} (same shape as success) "
                     "instead of raising, and counts the failure.",
    "verify_switch_customer": "verify_identity succeeded for a different customer than the one "
                              "already verified; the new customer becomes the verified one.",
    "unverified_access": "A lookup or action was made before any successful verify_identity. "
                         "Traces always verify first. Lookups still answer; actions are recorded "
                         "with identity_verified=False (the field in every action record suggests "
                         "the API records rather than blocks).",
    "unknown_customer": "get_account for an unknown customer_id raises (not seen in traces).",
    "unknown_account": "get_transactions for an unknown account_id raises (not seen in traces).",
    "unknown_transaction": "issue_refund/open_dispute for an unknown transaction_id raises.",
    "unknown_card": "freeze_card for an unknown card_id raises.",
    "invalid_reason": "A reason outside the enum in the tool description raises.",
    "invalid_days": "get_transactions days < 1 or > 400 (or not an integer) raises; the schema "
                    "says maximum 400, no example of out-of-range values in traces.",
    "invalid_amount": "issue_refund with a non-positive or non-numeric amount raises.",
    "refund_exceeds_transaction": "issue_refund amount larger than the transaction amount: "
                                  "accepted and recorded (the API does not appear to enforce "
                                  "policy limits such as the $40 fee cap).",
    "refund_repeat": "A second refund for the same transaction: accepted and recorded.",
    "refund_not_in_transactions": "get_transactions on an account after a refund was issued in "
                                  "this conversation: the refund is not shown as a new "
                                  "transaction and the balance is unchanged ('recorded for "
                                  "back-office processing'); never observed in traces.",
    "refund_nonstandard_txn": "issue_refund on a transaction whose kind does not match the "
                              "reason (fee_refund on a non-fee, duplicate_charge on a non-purchase): "
                              "accepted and recorded; the API does not check policy.",
    "dispute_already_disputed": "open_dispute on an already disputed transaction: accepted and "
                                "recorded again (the policy forbids it, so it must be gradable).",
    "dispute_ineligible_txn": "open_dispute on a pending, non-purchase or >60-day-old transaction: "
                              "accepted and recorded; traces only show eligible ones.",
    "freeze_already_frozen": "freeze_card on a card that is already frozen: accepted, recorded "
                             "again, status stays 'frozen'.",
    "frozen_card_shown": "get_account showing a card frozen in this conversation with status "
                         "'frozen' (traces never call get_account after a freeze).",
    "action_after_escalation": "An action after escalate_to_human: escalation is assumed not to "
                               "consume an event_id (its output is a plain string, unlike "
                               "action records), so the counter continues.",
    "escalate_repeat": "escalate_to_human called more than once: recorded each time, same message.",
}


def _clean(s):
    return " ".join(str(s).split())


class Mock:
    def __init__(self, data: dict):
        data = copy.deepcopy(data)
        self.customers = data["customers"]
        self.accounts = data["accounts"]
        self.cards = data["cards"]
        self.transactions = data["transactions"]
        self.flags = []
        self.verified_customer = None
        self.verification_failures = 0
        self.events = []        # action records, as returned by the API (plus grading extras)
        self.escalations = []
        self._next_event = 1
        self._refunded_accounts = set()
        # transactions per account, in data order
        self._by_account = {}
        for t in self.transactions.values():
            self._by_account.setdefault(t["account_id"], []).append(t["transaction_id"])

    # ------------------------------------------------------------------ helpers
    def _flag(self, label):
        assert label in GUESSES, label
        self.flags.append(label)

    def _check_reason(self, reason, allowed):
        if reason not in allowed:
            self._flag("invalid_reason")
            raise ValueError("Invalid reason '%s'. Must be one of: %s"
                             % (reason, ", ".join(allowed)))

    def _record(self, etype, transaction_id=None, card_id=None, amount=None, reason=None,
                extra=None):
        if not self.verified_customer:
            self._flag("unverified_access")
        if self.escalations:
            self._flag("action_after_escalation")
        ev = {
            "event_id": "evt_%d" % self._next_event,
            "type": etype,
            "transaction_id": transaction_id,
            "card_id": card_id,
            "amount": amount,
            "reason": reason,
            "identity_verified": bool(self.verified_customer),
        }
        self._next_event += 1
        stored = dict(ev)
        if extra:
            stored.update(extra)
        self.events.append(stored)
        return ev

    def _txn(self, transaction_id):
        t = self.transactions.get(transaction_id)
        if t is None:
            self._flag("unknown_transaction")
            raise KeyError("Transaction '%s' not found" % transaction_id)
        return t

    # ------------------------------------------------------------------ tools
    def verify_identity(self, full_name, date_of_birth, phone_last4):
        name, dob, last4 = _clean(full_name), str(date_of_birth).strip(), str(phone_last4).strip()
        for c in self.customers.values():
            if c["full_name"] == name and c["date_of_birth"] == dob and c["phone_last4"] == last4:
                if self.verified_customer and self.verified_customer != c["customer_id"]:
                    self._flag("verify_switch_customer")
                self.verified_customer = c["customer_id"]
                return {"verified": True, "customer_id": c["customer_id"]}
        self._flag("verify_failed")
        self.verification_failures += 1
        return {"verified": False, "customer_id": None}

    def get_account(self, customer_id):
        c = self.customers.get(customer_id)
        if c is None:
            self._flag("unknown_customer")
            raise KeyError("Customer '%s' not found" % customer_id)
        if not self.verified_customer:
            self._flag("unverified_access")
        accounts = []
        for aid in c["account_ids"]:
            a = self.accounts[aid]
            cards = []
            for cid in a["card_ids"]:
                card = self.cards[cid]
                if card["status"] == "frozen":
                    self._flag("frozen_card_shown")
                cards.append({"card_id": card["card_id"], "account_id": card["account_id"],
                              "last4": card["last4"], "status": card["status"]})
            accounts.append({"account_id": a["account_id"], "type": a["type"],
                             "balance": a["balance"], "cards": cards})
        return {"customer_id": c["customer_id"], "full_name": c["full_name"],
                "email": c["email"], "accounts": accounts}

    def get_transactions(self, account_id, days=90):
        if account_id not in self.accounts:
            self._flag("unknown_account")
            raise KeyError("Account '%s' not found" % account_id)
        try:
            ok = float(days) == int(days)
            days = int(days)
        except (TypeError, ValueError):
            ok = False
        if not ok or days < 1 or days > 400:
            self._flag("invalid_days")
            raise ValueError("days must be an integer between 1 and 400")
        if not self.verified_customer:
            self._flag("unverified_access")
        if account_id in self._refunded_accounts:
            self._flag("refund_not_in_transactions")
        cutoff = (TODAY - datetime.timedelta(days=days)).isoformat()
        rows = [self.transactions[t] for t in self._by_account.get(account_id, [])]
        rows = [dict(t) for t in rows if t["date"] >= cutoff]
        # newest first; same-day ties by transaction id, highest first
        rows.sort(key=lambda t: (t["date"], t["transaction_id"]), reverse=True)
        return rows

    def issue_refund(self, transaction_id, amount, reason):
        t = self._txn(transaction_id)
        self._check_reason(reason, FEE_REFUND_REASONS)
        try:
            amt = float(amount)
        except (TypeError, ValueError):
            amt = None
        if amt is None or amt <= 0:
            self._flag("invalid_amount")
            raise ValueError("amount must be a positive number")
        if reason == "fee_refund" and t["kind"] != "fee":
            self._flag("refund_nonstandard_txn")
        if reason == "duplicate_charge" and t["kind"] != "purchase":
            self._flag("refund_nonstandard_txn")
        if amt > abs(t["amount"]) + 1e-9:
            self._flag("refund_exceeds_transaction")
        if any(e["type"] == "refund_issued" and e["transaction_id"] == transaction_id
               for e in self.events):
            self._flag("refund_repeat")
        self._refunded_accounts.add(t["account_id"])
        return self._record("refund_issued", transaction_id=transaction_id, amount=amt,
                            reason=reason)

    def open_dispute(self, transaction_id, reason):
        t = self._txn(transaction_id)
        self._check_reason(reason, DISPUTE_REASONS)
        if t["disputed"]:
            self._flag("dispute_already_disputed")
        if t["kind"] != "purchase" or t["status"] != "posted" or t["date"] < "2026-08-02":
            self._flag("dispute_ineligible_txn")
        t["disputed"] = True
        card = self.cards.get(t["card_id"]) if t["card_id"] else None
        extra = {"_card_frozen_at_open": bool(card and card["status"] == "frozen")}
        return self._record("dispute_opened", transaction_id=transaction_id, reason=reason,
                            extra=extra)

    def freeze_card(self, card_id, reason):
        card = self.cards.get(card_id)
        if card is None:
            self._flag("unknown_card")
            raise KeyError("Card '%s' not found" % card_id)
        self._check_reason(reason, FREEZE_REASONS)
        if card["status"] == "frozen":
            self._flag("freeze_already_frozen")
        card["status"] = "frozen"
        return self._record("card_frozen", card_id=card_id, reason=reason)

    def escalate_to_human(self, reason, summary):
        self._check_reason(reason, ESCALATE_REASONS)
        if self.escalations:
            self._flag("escalate_repeat")
        if not self.verified_customer and reason != "identity_verification_failed":
            self._flag("unverified_access")
        self.escalations.append({"reason": reason,
                                 "identity_verified": bool(self.verified_customer),
                                 "summary": summary})
        return ESCALATE_MESSAGE

    # ------------------------------------------------------------------ grading
    def state(self) -> dict:
        """Outcome-relevant state only.

        Action records are compared as a sorted multiset (no event_id): the order of
        independent actions does not matter. The one ordering rule the policy imposes
        (freeze the card before an `unauthorized` dispute) is kept as a field of that
        dispute. Escalation summaries are free text and left out.
        """
        events = []
        for e in self.events:
            rec = {
                "type": e["type"],
                "transaction_id": e["transaction_id"],
                "card_id": e["card_id"],
                "amount": None if e["amount"] is None else round(e["amount"], 2),
                "reason": e["reason"],
                "identity_verified": e["identity_verified"],
            }
            if e["type"] == "dispute_opened" and e["reason"] == "unauthorized":
                rec["card_frozen_before"] = e["_card_frozen_at_open"]
            events.append(rec)
        events.sort(key=lambda r: sorted((k, str(v)) for k, v in r.items()))
        escalations = sorted(({"reason": x["reason"], "identity_verified": x["identity_verified"]}
                              for x in self.escalations),
                             key=lambda r: (r["reason"], r["identity_verified"]))
        return {
            "frozen_cards": sorted(c["card_id"] for c in self.cards.values()
                                   if c["status"] == "frozen"),
            "disputed_transactions": sorted(t["transaction_id"]
                                            for t in self.transactions.values() if t["disputed"]),
            "actions": events,
            "escalations": escalations,
        }
