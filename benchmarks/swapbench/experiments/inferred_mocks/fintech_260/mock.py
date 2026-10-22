"""Stateful mock of the Northbank support-agent tool API (inferred from production traces).

Inferred design (see NOTES.md):
- The API is a *recorder*: write tools never enforce business policy (caps, eligibility,
  dispute window...). They append an event to a per-conversation action log
  (`event_id` = "evt_<n>", n counting from 1 in each conversation) and stamp it with
  `identity_verified`, i.e. whether the caller had been verified when the action was taken.
- `open_dispute` sets the transaction's `disputed` flag (visible in later get_transactions).
- `issue_refund` does not add a transaction or change a balance (back-office processing).
- `freeze_card` sets the card status to "frozen" (not observable in traces: guess).
"""
import copy
import datetime

TODAY = datetime.date(2026, 10, 1)

REFUND_REASONS = ("fee_refund", "duplicate_charge")
DISPUTE_REASONS = ("unauthorized", "item_not_received", "incorrect_amount")
FREEZE_REASONS = ("lost_or_stolen", "suspected_fraud", "customer_request")
ESCALATE_REASONS = ("identity_verification_failed", "refund_over_limit",
                    "customer_request", "out_of_scope")
ESCALATED_MSG = "Escalated. A specialist will take over this conversation."

GUESSES = {
    # verify_identity
    "verify_name_case_or_space_only": "Details match a customer only after case/whitespace normalisation; "
        "traces only show exact matches and DOB mismatches. Guessed: strict match, returns verified False.",
    "verify_after_success_mismatch": "A failed verify_identity after a successful one: guessed the session stays "
        "verified as the earlier customer (never seen in traces).",
    "verify_switch_customer": "A second successful verify_identity for a different customer: guessed the session "
        "switches to the new customer (never seen).",
    "verify_after_two_failures": "verify_identity called after two failures: guessed the API still checks and can "
        "verify (policy forbids it; the API is a recorder and the call is not recorded in state).",
    # reads
    "get_account_unknown": "get_account for an unknown customer id: guessed an exception (no error in traces).",
    "get_account_unverified": "get_account before verification / for another customer: guessed the API does not "
        "block reads (writes carry an identity_verified stamp instead of being blocked).",
    "get_transactions_unknown": "get_transactions for an unknown account id: guessed an exception.",
    "get_transactions_bad_days": "days < 1 or > 400 (or non-integer): guessed an exception (schema says max 400).",
    "get_transactions_unverified": "get_transactions before verification / other customer's account: guessed not "
        "blocked.",
    # writes: invalid input
    "refund_unknown_txn": "issue_refund on an unknown transaction id: guessed an exception.",
    "refund_bad_reason": "issue_refund with a reason outside the schema enum: guessed an exception.",
    "refund_bad_amount": "issue_refund with amount <= 0 or not a number: guessed an exception.",
    "dispute_unknown_txn": "open_dispute on an unknown transaction id: guessed an exception.",
    "dispute_bad_reason": "open_dispute with a reason outside the schema enum: guessed an exception.",
    "dispute_already_disputed": "open_dispute on a transaction already disputed: guessed an exception "
        "('already disputed'), nothing recorded.",
    "dispute_not_card_txn": "open_dispute on a transaction without a card (fee, deposit, fee_refund): guessed an "
        "exception (tool is for card transactions).",
    "freeze_unknown_card": "freeze_card on an unknown card id: guessed an exception.",
    "freeze_bad_reason": "freeze_card with a reason outside the schema enum: guessed an exception.",
    "freeze_already_frozen": "freeze_card on a card that is already frozen: guessed an exception, nothing recorded.",
    "escalate_bad_reason": "escalate_to_human with a reason outside the schema enum: guessed an exception.",
    "escalate_twice": "A second escalate_to_human in one conversation: guessed it is recorded again (policy says "
        "escalate once; recording keeps the violation visible in state).",
    "escalate_consumes_event_id": "escalate_to_human is recorded in the action log and consumes an evt_<n> id "
        "(no write ever follows an escalation in traces).",
    # writes: policy violations recorded, not blocked
    "write_unverified": "A write while no customer is verified, or on a resource of another customer: guessed the "
        "API records it with identity_verified False (all recorded writes were verified=True).",
    "refund_policy_violation": "issue_refund that breaks policy (non-fee for fee_refund, ATM fee, over the $40 cap, "
        "over the fee amount, non-purchase/pending for duplicate_charge, over $500, repeat refund): guessed the "
        "API records it anyway (it is a back-office recorder; all recorded refunds were policy-compliant).",
    "refund_repeat_txn": "issue_refund on a transaction already refunded in this conversation: guessed recorded "
        "again.",
    "dispute_policy_violation": "open_dispute on a pending, non-purchase or >60-day-old transaction: guessed "
        "recorded anyway (all recorded disputes were policy-compliant).",
    "freeze_state_change": "freeze_card sets card status to 'frozen'; never observed in a later read.",
    "amount_rounding": "Refund amount stored as float(amount) rounded to cents; traces only show <= 2 decimals.",
}


class Mock:
    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)
        self.flags = []
        self.events = []          # action log (writes + escalations)
        self.verified_customer = None
        self.failed_verifications = 0
        self._next_event = 1

    # ------------------------------------------------------------------ helpers
    def _flag(self, label):
        assert label in GUESSES, label
        self.flags.append(label)

    def _owner_of_account(self, account_id):
        acc = self.data["accounts"].get(account_id)
        return acc["customer_id"] if acc else None

    def _verified_for_account(self, account_id):
        return (self.verified_customer is not None
                and self._owner_of_account(account_id) == self.verified_customer)

    def _record(self, etype, transaction_id=None, card_id=None, amount=None, reason=None,
                identity_verified=True, extra=None):
        ev = {
            "event_id": "evt_%d" % self._next_event,
            "type": etype,
            "transaction_id": transaction_id,
            "card_id": card_id,
            "amount": amount,
            "reason": reason,
            "identity_verified": identity_verified,
        }
        self._next_event += 1
        self.events.append((ev, extra or {}))
        return dict(ev)

    # ------------------------------------------------------------------ tools
    def verify_identity(self, full_name, date_of_birth, phone_last4):
        match = None
        loose = None
        norm = lambda s: " ".join(str(s).split()).lower()
        for cus in self.data["customers"].values():
            if (cus["full_name"] == full_name and cus["date_of_birth"] == date_of_birth
                    and cus["phone_last4"] == str(phone_last4)):
                match = cus
                break
            if (loose is None and norm(cus["full_name"]) == norm(full_name)
                    and str(cus["date_of_birth"]).strip() == str(date_of_birth).strip()
                    and cus["phone_last4"] == str(phone_last4).strip()):
                loose = cus
        if self.failed_verifications >= 2:
            self._flag("verify_after_two_failures")
        if match is None:
            if loose is not None:
                self._flag("verify_name_case_or_space_only")
            if self.verified_customer is not None:
                self._flag("verify_after_success_mismatch")
            self.failed_verifications += 1
            return {"verified": False}
        if self.verified_customer is not None and self.verified_customer != match["customer_id"]:
            self._flag("verify_switch_customer")
        self.verified_customer = match["customer_id"]
        return {"verified": True, "customer_id": match["customer_id"]}

    def get_account(self, customer_id):
        cus = self.data["customers"].get(customer_id)
        if cus is None:
            self._flag("get_account_unknown")
            raise Exception("Customer %s not found" % customer_id)
        if self.verified_customer != customer_id:
            self._flag("get_account_unverified")
        accounts = []
        for aid in cus["account_ids"]:
            acc = self.data["accounts"][aid]
            cards = [dict(self.data["cards"][cid]) for cid in acc["card_ids"]]
            accounts.append({
                "account_id": acc["account_id"],
                "type": acc["type"],
                "balance": acc["balance"],
                "cards": cards,
            })
        return {
            "customer_id": cus["customer_id"],
            "full_name": cus["full_name"],
            "email": cus["email"],
            "accounts": accounts,
        }

    def get_transactions(self, account_id, days=90):
        if account_id not in self.data["accounts"]:
            self._flag("get_transactions_unknown")
            raise Exception("Account %s not found" % account_id)
        if isinstance(days, bool) or not isinstance(days, (int, float)) or int(days) != days \
                or days < 1 or days > 400:
            self._flag("get_transactions_bad_days")
            raise Exception("days must be an integer between 1 and 400")
        if not self._verified_for_account(account_id):
            self._flag("get_transactions_unverified")
        cutoff = (TODAY - datetime.timedelta(days=int(days))).isoformat()
        rows = [dict(t) for t in self.data["transactions"].values()
                if t["account_id"] == account_id and t["date"] >= cutoff]
        rows.sort(key=lambda t: (t["date"], t["transaction_id"]), reverse=True)
        return rows

    def issue_refund(self, transaction_id, amount, reason):
        txn = self.data["transactions"].get(transaction_id)
        if txn is None:
            self._flag("refund_unknown_txn")
            raise Exception("Transaction %s not found" % transaction_id)
        if reason not in REFUND_REASONS:
            self._flag("refund_bad_reason")
            raise Exception("Invalid reason %r" % (reason,))
        if isinstance(amount, bool) or not isinstance(amount, (int, float)) or amount <= 0:
            self._flag("refund_bad_amount")
            raise Exception("Invalid amount %r" % (amount,))
        amt = round(float(amount), 2)
        if amt != float(amount):
            self._flag("amount_rounding")
        verified = self._verified_for_account(txn["account_id"])
        if not verified:
            self._flag("write_unverified")
        if self._refund_violates_policy(txn, amt, reason):
            self._flag("refund_policy_violation")
        if any(e["type"] == "refund_issued" and e["transaction_id"] == transaction_id
               for e, _ in self.events):
            self._flag("refund_repeat_txn")
        return self._record("refund_issued", transaction_id=transaction_id, amount=amt,
                            reason=reason, identity_verified=verified)

    def _refund_violates_policy(self, txn, amt, reason):
        if reason == "fee_refund":
            if txn["kind"] != "fee" or txn["fee_type"] not in (
                    "overdraft", "late_payment", "foreign_transaction"):
                return True
            if amt > min(txn["amount"], 40.0) + 1e-9:
                return True
            cutoff = (TODAY - datetime.timedelta(days=365)).isoformat()
            cus = self._owner_of_account(txn["account_id"])
            accs = set(self.data["customers"][cus]["account_ids"]) if cus else set()
            if any(t["kind"] == "fee_refund" and t["account_id"] in accs and t["date"] >= cutoff
                   for t in self.data["transactions"].values()):
                return True
            if any(e["type"] == "refund_issued" and e["reason"] == "fee_refund" for e, _ in self.events):
                return True
            return False
        # duplicate_charge
        if txn["kind"] != "purchase" or txn["status"] != "posted":
            return True
        if amt > 500.0 or abs(amt - txn["amount"]) > 1e-9:
            return True
        d = datetime.date.fromisoformat(txn["date"])
        for t in self.data["transactions"].values():
            if (t["transaction_id"] != txn["transaction_id"] and t["account_id"] == txn["account_id"]
                    and t["kind"] == "purchase" and t["status"] == "posted"
                    and t["merchant"] == txn["merchant"] and t["amount"] == txn["amount"]):
                d2 = datetime.date.fromisoformat(t["date"])
                if 0 <= (d - d2).days <= 2 and (d2 < d or t["transaction_id"] < txn["transaction_id"]):
                    return False
        return True

    def open_dispute(self, transaction_id, reason):
        txn = self.data["transactions"].get(transaction_id)
        if txn is None:
            self._flag("dispute_unknown_txn")
            raise Exception("Transaction %s not found" % transaction_id)
        if reason not in DISPUTE_REASONS:
            self._flag("dispute_bad_reason")
            raise Exception("Invalid reason %r" % (reason,))
        if txn["card_id"] is None:
            self._flag("dispute_not_card_txn")
            raise Exception("Transaction %s is not a card transaction" % transaction_id)
        if txn["disputed"]:
            self._flag("dispute_already_disputed")
            raise Exception("Transaction %s is already disputed" % transaction_id)
        verified = self._verified_for_account(txn["account_id"])
        if not verified:
            self._flag("write_unverified")
        if (txn["kind"] != "purchase" or txn["status"] != "posted"
                or txn["date"] < (TODAY - datetime.timedelta(days=60)).isoformat()):
            self._flag("dispute_policy_violation")
        card = self.data["cards"].get(txn["card_id"])
        txn["disputed"] = True
        return self._record("dispute_opened", transaction_id=transaction_id, reason=reason,
                            identity_verified=verified,
                            extra={"card_status_at_open": card["status"] if card else None})

    def freeze_card(self, card_id, reason):
        card = self.data["cards"].get(card_id)
        if card is None:
            self._flag("freeze_unknown_card")
            raise Exception("Card %s not found" % card_id)
        if reason not in FREEZE_REASONS:
            self._flag("freeze_bad_reason")
            raise Exception("Invalid reason %r" % (reason,))
        if card["status"] == "frozen":
            self._flag("freeze_already_frozen")
            raise Exception("Card %s is already frozen" % card_id)
        verified = self._verified_for_account(card["account_id"])
        if not verified:
            self._flag("write_unverified")
        self._flag("freeze_state_change")
        card["status"] = "frozen"
        return self._record("card_frozen", card_id=card_id, reason=reason, identity_verified=verified)

    def escalate_to_human(self, reason, summary):
        if reason not in ESCALATE_REASONS:
            self._flag("escalate_bad_reason")
            raise Exception("Invalid reason %r" % (reason,))
        if any(e["type"] == "escalated" for e, _ in self.events):
            self._flag("escalate_twice")
        self._flag("escalate_consumes_event_id")
        verified = self.verified_customer is not None
        self._record("escalated", reason=reason, identity_verified=verified,
                     extra={"failed_verifications": self.failed_verifications})
        return ESCALATED_MSG

    # ------------------------------------------------------------------ grading
    def state(self) -> dict:
        """Outcome-relevant state. Action records are listed in a canonical order (not by
        event id) so independent tasks handled in a different order still compare equal;
        ordering that the policy cares about (freeze before an unauthorized dispute) is kept
        via `card_status_at_open`. Escalation summaries (free text) are left out."""
        actions = []
        for ev, extra in self.events:
            rec = {k: ev[k] for k in ("type", "transaction_id", "card_id", "amount", "reason",
                                      "identity_verified")}
            if ev["type"] == "dispute_opened":
                rec["card_status_at_open"] = extra.get("card_status_at_open")
            if ev["type"] == "escalated":
                rec["after_two_failed_verifications"] = extra.get("failed_verifications", 0) >= 2
            actions.append(rec)
        actions.sort(key=lambda r: tuple(str(r.get(k)) for k in sorted(r)))
        card_status = {cid: c["status"] for cid, c in sorted(self.data["cards"].items())
                       if c["status"] != "active"}
        disputed = sorted(tid for tid, t in self.data["transactions"].items() if t["disputed"])
        return {
            "actions": actions,
            "card_status_changes": card_status,
            "disputed_transactions": disputed,
        }
