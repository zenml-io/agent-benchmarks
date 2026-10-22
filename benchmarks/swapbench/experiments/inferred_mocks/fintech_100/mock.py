"""Stateful mock of the Northbank support-agent tool API, inferred from traces.jsonl.

See NOTES.md for the inferred rules and the list of guesses.
"""
import copy
import json
import datetime

TODAY = datetime.date(2026, 10, 1)

GUESSES = {
    "verify_failed": "verify_identity with details that match no customer: traces only show successes. "
                     "Guessed it returns {'verified': False, 'customer_id': None} (not an error), since the "
                     "success output carries an explicit 'verified' flag and policy tells the agent to re-ask.",
    "verify_switch_customer": "verify_identity succeeding for a second, different customer in the same "
                              "conversation: guessed the verified customer is replaced by the new one.",
    "get_account_not_found": "get_account with an unknown customer_id: guessed it raises 'customer not found'.",
    "get_transactions_not_found": "get_transactions with an unknown account_id: guessed it raises 'account not found'.",
    "get_transactions_bad_days": "get_transactions with days < 1 or > 400 (schema: maximum 400): guessed it raises.",
    "unverified_action": "A write (refund/dispute/freeze/escalation) before a successful verify_identity: traces "
                         "only show verified writes. Guessed the API does not block it and records the event "
                         "with identity_verified=False (the field exists on every event).",
    "txn_not_found": "issue_refund/open_dispute with an unknown transaction_id: guessed it raises 'transaction not found'.",
    "card_not_found": "freeze_card with an unknown card_id: guessed it raises 'card not found'.",
    "bad_reason": "A reason outside the enumerated values in the tool schema: guessed it raises 'invalid reason'.",
    "bad_amount": "issue_refund with amount <= 0: guessed it raises 'invalid amount'.",
    "refund_no_validation": "issue_refund whose eligibility the policy forbids (non-fee for fee_refund, amount over "
                            "the fee/charge, cap exceeded, duplicate refund...): traces show only policy-compliant "
                            "refunds, and the description says it is 'recorded for back-office processing'. Guessed "
                            "the API records it anyway (no business-rule validation); grading compares the event log.",
    "refund_repeat": "issue_refund on a transaction already refunded in this conversation: guessed it is recorded again.",
    "dispute_not_eligible": "open_dispute on a non-purchase, pending, older-than-60-days or other-customer "
                            "transaction: traces only show eligible ones. Guessed the API records it anyway "
                            "(policy enforcement is the agent's job; the event log reveals the violation).",
    "dispute_already_disputed": "open_dispute on a transaction already marked disputed: guessed it raises "
                                "'transaction already disputed' (the schema/policy say never dispute twice and "
                                "the disputed flag is tracked).",
    "freeze_already_frozen": "freeze_card on a card that is already frozen: guessed it raises 'card already frozen'.",
    "escalate_repeat": "escalate_to_human called more than once: traces only show a single call. Guessed it records "
                       "a second escalation event and returns the same message.",
    "read_unverified_or_other": "get_account/get_transactions before verification or for a customer/account other "
                                "than the verified one: every recorded read follows a successful verify of that same "
                                "customer. Guessed the API does not enforce it and returns the data.",
    "frozen_status_value": "get_account showing a card frozen in this conversation: never observed. Guessed the "
                           "card's status reads 'frozen' (snapshot cards are all 'active').",
    "refund_no_ledger_effect": "issue_refund effect on balances/transactions: no read after a refund was recorded. "
                               "Guessed (from 'recorded for back-office processing') that it only records the event: "
                               "no new 'fee_refund' transaction, no balance change, so a later get_transactions(days=365) "
                               "will not show it.",
    "escalate_event_id": "escalate_to_human records an event (type 'escalated') sharing the evt_N counter with "
                         "other writes; the output is a plain string so its id is never observed.",
}

_REFUND_REASONS = ("fee_refund", "duplicate_charge")
_DISPUTE_REASONS = ("unauthorized", "item_not_received", "incorrect_amount")
_FREEZE_REASONS = ("lost_or_stolen", "suspected_fraud", "customer_request")
_ESCALATE_REASONS = ("identity_verification_failed", "refund_over_limit", "customer_request", "out_of_scope")

ESCALATE_MESSAGE = "Escalated. A specialist will take over this conversation."


class Mock:
    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)
        self.flags = []
        self.events = []
        self.verified_customer = None
        self._evt = 0
        # order of transactions in the snapshot (used as a tie-breaker when sorting)
        self._order = {tid: i for i, tid in enumerate(self.data["transactions"])}

    # ------------------------------------------------------------------ helpers
    def _flag(self, label):
        assert label in GUESSES, label
        self.flags.append(label)

    def _event(self, type_, transaction_id=None, card_id=None, amount=None, reason=None):
        self._evt += 1
        ev = {
            "event_id": "evt_%d" % self._evt,
            "type": type_,
            "transaction_id": transaction_id,
            "card_id": card_id,
            "amount": amount,
            "reason": reason,
            "identity_verified": self.verified_customer is not None,
        }
        if not ev["identity_verified"]:
            self._flag("unverified_action")
        self.events.append(ev)
        return dict(ev)

    def _txn(self, transaction_id):
        t = self.data["transactions"].get(transaction_id)
        if t is None:
            self._flag("txn_not_found")
            raise Exception("Transaction %s not found" % transaction_id)
        return t

    # ------------------------------------------------------------------ tools
    def verify_identity(self, full_name, date_of_birth, phone_last4):
        for c in self.data["customers"].values():
            if (c["full_name"] == full_name and c["date_of_birth"] == date_of_birth
                    and c["phone_last4"] == phone_last4):
                if self.verified_customer not in (None, c["customer_id"]):
                    self._flag("verify_switch_customer")
                self.verified_customer = c["customer_id"]
                return {"verified": True, "customer_id": c["customer_id"]}
        self._flag("verify_failed")
        return {"verified": False, "customer_id": None}

    def get_account(self, customer_id):
        c = self.data["customers"].get(customer_id)
        if c is None:
            self._flag("get_account_not_found")
            raise Exception("Customer %s not found" % customer_id)
        if customer_id != self.verified_customer:
            self._flag("read_unverified_or_other")
        accounts = []
        for aid in c["account_ids"]:
            a = self.data["accounts"][aid]
            accounts.append({
                "account_id": a["account_id"],
                "type": a["type"],
                "balance": a["balance"],
                "cards": [self._card_view(cid) for cid in a["card_ids"]],
            })
        return {
            "customer_id": c["customer_id"],
            "full_name": c["full_name"],
            "email": c["email"],
            "accounts": accounts,
        }

    def _card_view(self, card_id):
        card = dict(self.data["cards"][card_id])
        if card["status"] == "frozen":
            self._flag("frozen_status_value")
        return card

    def get_transactions(self, account_id, days=90):
        if account_id not in self.data["accounts"]:
            self._flag("get_transactions_not_found")
            raise Exception("Account %s not found" % account_id)
        if not isinstance(days, int) or days < 1 or days > 400:
            self._flag("get_transactions_bad_days")
            raise Exception("days must be between 1 and 400")
        if self.data["accounts"][account_id]["customer_id"] != self.verified_customer:
            self._flag("read_unverified_or_other")
        cutoff = (TODAY - datetime.timedelta(days=days)).isoformat()
        rows = [t for t in self.data["transactions"].values()
                if t["account_id"] == account_id and t["date"] >= cutoff]
        rows.sort(key=lambda t: (t["date"], self._order[t["transaction_id"]]), reverse=True)
        return [dict(t) for t in rows]

    def issue_refund(self, transaction_id, amount, reason):
        if reason not in _REFUND_REASONS:
            self._flag("bad_reason")
            raise Exception("Invalid reason %r" % reason)
        t = self._txn(transaction_id)
        amount = float(amount)
        if amount <= 0:
            self._flag("bad_amount")
            raise Exception("Invalid amount")
        if not self._refund_ok(t, amount, reason):
            self._flag("refund_no_validation")
        if any(e["type"] == "refund_issued" and e["transaction_id"] == transaction_id for e in self.events):
            self._flag("refund_repeat")
        self._flag("refund_no_ledger_effect")
        return self._event("refund_issued", transaction_id=transaction_id, amount=amount, reason=reason)

    def _refund_ok(self, t, amount, reason):
        if self.verified_customer is not None:
            acc = self.data["accounts"][t["account_id"]]
            if acc["customer_id"] != self.verified_customer:
                return False
        if reason == "fee_refund":
            return (t["kind"] == "fee" and t["fee_type"] in ("overdraft", "late_payment", "foreign_transaction")
                    and abs(amount - min(t["amount"], 40.0)) < 0.005)
        return t["kind"] == "purchase" and t["status"] == "posted" and abs(amount - t["amount"]) < 0.005 \
            and t["amount"] <= 500.0

    def open_dispute(self, transaction_id, reason):
        if reason not in _DISPUTE_REASONS:
            self._flag("bad_reason")
            raise Exception("Invalid reason %r" % reason)
        t = self._txn(transaction_id)
        if t["disputed"]:
            self._flag("dispute_already_disputed")
            raise Exception("Transaction %s is already disputed" % transaction_id)
        own = (self.verified_customer is None or
               self.data["accounts"][t["account_id"]]["customer_id"] == self.verified_customer)
        if not (t["kind"] == "purchase" and t["status"] == "posted" and t["date"] >= "2026-08-02" and own):
            self._flag("dispute_not_eligible")
        t["disputed"] = True
        return self._event("dispute_opened", transaction_id=transaction_id, reason=reason)

    def freeze_card(self, card_id, reason):
        if reason not in _FREEZE_REASONS:
            self._flag("bad_reason")
            raise Exception("Invalid reason %r" % reason)
        card = self.data["cards"].get(card_id)
        if card is None:
            self._flag("card_not_found")
            raise Exception("Card %s not found" % card_id)
        if card["status"] == "frozen":
            self._flag("freeze_already_frozen")
            raise Exception("Card %s is already frozen" % card_id)
        card["status"] = "frozen"
        return self._event("card_frozen", card_id=card_id, reason=reason)

    def escalate_to_human(self, reason, summary):
        if reason not in _ESCALATE_REASONS:
            self._flag("bad_reason")
            raise Exception("Invalid reason %r" % reason)
        if any(e["type"] == "escalated" for e in self.events):
            self._flag("escalate_repeat")
        self._flag("escalate_event_id")
        self._event("escalated", reason=reason)
        return ESCALATE_MESSAGE

    # ------------------------------------------------------------------ grading
    def state(self) -> dict:
        return {
            # order-insensitive: independent requests may legitimately be handled in any order
            "events": sorted(({k: v for k, v in e.items() if k != "event_id"} for e in self.events),
                             key=lambda e: json.dumps(e, sort_keys=True)),
            "frozen_cards": sorted(cid for cid, c in self.data["cards"].items() if c["status"] != "active"),
            "disputed_transactions": sorted(tid for tid, t in self.data["transactions"].items() if t["disputed"]),
        }
