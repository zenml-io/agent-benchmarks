"""Stateful mock of the Northbank support-agent tool API (inferred from traces).

Return values use native JSON types (bool, float, None). The production recorder stringified
scalar values (True -> "True", 40.0 -> "40.0"); check.py applies the same stringification.
"""
import copy
import datetime

TODAY = datetime.date(2026, 10, 1)

REFUND_REASONS = ("fee_refund", "duplicate_charge")
DISPUTE_REASONS = ("unauthorized", "item_not_received", "incorrect_amount")
FREEZE_REASONS = ("lost_or_stolen", "suspected_fraud", "customer_request")
ESCALATION_REASONS = ("identity_verification_failed", "refund_over_limit",
                      "customer_request", "out_of_scope")
ESCALATION_MESSAGE = "Escalated. A specialist will take over this conversation."

GUESSES = {
    "verify_failed": "No failed verification is recorded. On mismatch (or unknown name) we return "
                     "{'verified': False, 'customer_id': None} instead of raising, because the "
                     "success payload carries a 'verified' flag; failures are counted for state().",
    "verify_failed_keeps_previous": "A failed verification after a successful one keeps the "
                                    "earlier verified customer (not observable in traces).",
    "verify_switch_customer": "A second successful verification for a different customer replaces "
                              "the verified customer (policy: one customer per conversation).",
    "unverified_read": "Reads (get_account/get_transactions) before verification succeed; traces "
                       "only show reads after verification.",
    "unverified_action": "Write actions before verification are recorded with "
                         "identity_verified=False rather than rejected (the event record has an "
                         "'identity_verified' field, implying unverified actions are recorded).",
    "action_other_customer": "Actions on resources not owned by the verified customer are "
                             "recorded (identity_verified stays True); not observed.",
    "customer_not_found": "get_account with an unknown customer_id raises (never observed).",
    "account_not_found": "get_transactions with an unknown account_id raises (never observed).",
    "transaction_not_found": "issue_refund/open_dispute with an unknown transaction_id raises.",
    "card_not_found": "freeze_card with an unknown card_id raises.",
    "days_out_of_range": "get_transactions with days < 1 or > 400 raises (schema says max 400).",
    "invalid_reason": "A reason outside the schema's enumerated values raises ValueError.",
    "invalid_amount": "A non-positive or non-numeric refund amount raises ValueError.",
    "refund_policy_not_enforced": "issue_refund records refunds that break policy (non-fee txn, "
                                  "ATM fee, amount > fee or > $40, over $500, second refund, "
                                  "365-day limit) instead of rejecting; the API is 'recorded for "
                                  "back-office processing' and every write carries "
                                  "identity_verified, suggesting no server-side policy checks.",
    "refund_repeat": "Refunding the same transaction again is recorded again (not rejected).",
    "refund_no_ledger_effect": "A refund does not change balances or add a transaction to "
                               "get_transactions output (no read-after-refund in traces).",
    "dispute_policy_not_enforced": "open_dispute records disputes on pending, non-purchase or "
                                   ">60-day-old transactions instead of rejecting.",
    "dispute_already_disputed": "Disputing an already disputed transaction is recorded again.",
    "freeze_already_frozen": "Freezing an already frozen card is recorded again.",
    "frozen_status_value": "A frozen card shows status 'frozen' in get_account (traces never "
                           "read an account after a freeze).",
    "event_after_escalation": "escalate_to_human returns a plain string, not an event; we assume "
                              "it does not consume an evt_N number (no trace shows a write after "
                              "an escalation).",
    "escalate_unverified": "Escalation before verification is accepted and recorded with "
                           "identity_verified=False.",
}


class Mock:
    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)
        self.flags = []
        self.verified_customer = None
        self.verify_failures = 0
        self.events = []        # write actions, in order
        self.escalations = []   # escalate_to_human records, in order
        self._escalated = False

    # ------------------------------------------------------------------ helpers
    def _flag(self, label):
        self.flags.append(label)

    def _txn(self, transaction_id):
        t = self.data["transactions"].get(transaction_id)
        if t is None:
            self._flag("transaction_not_found")
            raise KeyError(f"Transaction {transaction_id} not found")
        return t

    def _owner_of_account(self, account_id):
        acc = self.data["accounts"].get(account_id)
        return acc["customer_id"] if acc else None

    def _check_actor(self, owner_customer_id):
        if self.verified_customer is None:
            self._flag("unverified_action")
            return False
        if owner_customer_id != self.verified_customer:
            self._flag("action_other_customer")
        return True

    def _record(self, etype, transaction_id=None, card_id=None, amount=None, reason=None,
                verified=True, extra=None):
        if self._escalated:
            self._flag("event_after_escalation")
        ev = {
            "event_id": f"evt_{len(self.events) + 1}",
            "type": etype,
            "transaction_id": transaction_id,
            "card_id": card_id,
            "amount": amount,
            "reason": reason,
            "identity_verified": verified,
        }
        self.events.append((ev, extra or {}))
        return dict(ev)

    # ------------------------------------------------------------------ tools
    def verify_identity(self, full_name, date_of_birth, phone_last4):
        for cid, c in self.data["customers"].items():
            if (c["full_name"] == full_name and c["date_of_birth"] == date_of_birth
                    and c["phone_last4"] == str(phone_last4)):
                if self.verified_customer is not None and self.verified_customer != cid:
                    self._flag("verify_switch_customer")
                self.verified_customer = cid
                return {"verified": True, "customer_id": cid}
        self._flag("verify_failed")
        if self.verified_customer is not None:
            self._flag("verify_failed_keeps_previous")
        self.verify_failures += 1
        return {"verified": False, "customer_id": None}

    def get_account(self, customer_id):
        c = self.data["customers"].get(customer_id)
        if c is None:
            self._flag("customer_not_found")
            raise KeyError(f"Customer {customer_id} not found")
        if self.verified_customer is None:
            self._flag("unverified_read")
        accounts = []
        for aid in c["account_ids"]:
            a = self.data["accounts"][aid]
            cards = [dict(self.data["cards"][k]) for k in a["card_ids"]]
            accounts.append({"account_id": a["account_id"], "type": a["type"],
                             "balance": a["balance"], "cards": cards})
        return {"customer_id": c["customer_id"], "full_name": c["full_name"],
                "email": c["email"], "accounts": accounts}

    def get_transactions(self, account_id, days=90):
        if account_id not in self.data["accounts"]:
            self._flag("account_not_found")
            raise KeyError(f"Account {account_id} not found")
        try:
            days = int(days)
        except (TypeError, ValueError):
            self._flag("days_out_of_range")
            raise ValueError("days must be an integer")
        if days < 1 or days > 400:
            self._flag("days_out_of_range")
            raise ValueError("days must be between 1 and 400")
        if self.verified_customer is None:
            self._flag("unverified_read")
        cutoff = (TODAY - datetime.timedelta(days=days)).isoformat()
        out = [dict(t) for t in self.data["transactions"].values()
               if t["account_id"] == account_id and t["date"] >= cutoff]
        # newest first; ties broken by transaction id descending (matches traces)
        out.sort(key=lambda t: (t["date"], t["transaction_id"]), reverse=True)
        return out

    def issue_refund(self, transaction_id, amount, reason):
        if reason not in REFUND_REASONS:
            self._flag("invalid_reason")
            raise ValueError(f"Invalid reason {reason!r}")
        t = self._txn(transaction_id)
        try:
            amt = round(float(amount), 2)
        except (TypeError, ValueError):
            self._flag("invalid_amount")
            raise ValueError("Invalid amount")
        if amt <= 0:
            self._flag("invalid_amount")
            raise ValueError("Amount must be positive")
        if any(e["type"] == "refund_issued" and e["transaction_id"] == transaction_id
               for e, _ in self.events):
            self._flag("refund_repeat")
        ok = True
        if reason == "fee_refund":
            if t["kind"] != "fee" or t["fee_type"] == "atm" or amt > min(t["amount"], 40.0):
                ok = False
        else:
            if t["kind"] != "purchase" or t["status"] != "posted" or amt != t["amount"] \
                    or t["amount"] > 500:
                ok = False
        if not ok:
            self._flag("refund_policy_not_enforced")
        verified = self._check_actor(self._owner_of_account(t["account_id"]))
        return self._record("refund_issued", transaction_id=transaction_id, amount=amt,
                            reason=reason, verified=verified)

    def open_dispute(self, transaction_id, reason):
        if reason not in DISPUTE_REASONS:
            self._flag("invalid_reason")
            raise ValueError(f"Invalid reason {reason!r}")
        t = self._txn(transaction_id)
        if t["kind"] != "purchase" or t["status"] != "posted" or t["date"] < "2026-08-02":
            self._flag("dispute_policy_not_enforced")
        if t["disputed"]:
            self._flag("dispute_already_disputed")
        verified = self._check_actor(self._owner_of_account(t["account_id"]))
        card = self.data["cards"].get(t["card_id"]) if t["card_id"] else None
        frozen_before = bool(card and card["status"] == "frozen")
        t["disputed"] = True
        return self._record("dispute_opened", transaction_id=transaction_id, reason=reason,
                            verified=verified, extra={"card_frozen_before": frozen_before})

    def freeze_card(self, card_id, reason):
        if reason not in FREEZE_REASONS:
            self._flag("invalid_reason")
            raise ValueError(f"Invalid reason {reason!r}")
        card = self.data["cards"].get(card_id)
        if card is None:
            self._flag("card_not_found")
            raise KeyError(f"Card {card_id} not found")
        if card["status"] == "frozen":
            self._flag("freeze_already_frozen")
        verified = self._check_actor(self._owner_of_account(card["account_id"]))
        card["status"] = "frozen"
        self._flag("frozen_status_value")
        return self._record("card_frozen", card_id=card_id, reason=reason, verified=verified)

    def escalate_to_human(self, reason, summary):
        if reason not in ESCALATION_REASONS:
            self._flag("invalid_reason")
            raise ValueError(f"Invalid reason {reason!r}")
        if self.verified_customer is None:
            self._flag("escalate_unverified")
        self.escalations.append({"reason": reason,
                                 "identity_verified": self.verified_customer is not None})
        self._escalated = True
        return ESCALATION_MESSAGE

    # ------------------------------------------------------------------ grading
    def state(self) -> dict:
        actions = []
        for ev, extra in self.events:
            rec = {k: v for k, v in ev.items() if k != "event_id"}
            rec.update(extra)
            actions.append(rec)
        actions.sort(key=lambda r: (r["type"], r["transaction_id"] or "", r["card_id"] or "",
                                    r["reason"] or "", r["amount"] or 0.0,
                                    r["identity_verified"], r.get("card_frozen_before", False)))
        frozen = {cid: c["status"] for cid, c in sorted(self.data["cards"].items())
                  if c["status"] != "active"}
        disputed = sorted(tid for tid, t in self.data["transactions"].items() if t["disputed"])
        return {
            "actions": actions,
            "escalations": sorted(self.escalations,
                                  key=lambda e: (e["reason"], e["identity_verified"])),
            "card_statuses": frozen,
            "disputed_transactions": disputed,
            "verification_failures": min(self.verify_failures, 3),
        }
