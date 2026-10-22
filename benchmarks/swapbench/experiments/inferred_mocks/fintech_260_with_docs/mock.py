"""Stateful mock of the Northbank customer-support tool API.

See NOTES.md for what was inferred from the traces and what was assumed.
"""
import copy
import json
import datetime

TODAY = datetime.date(2026, 10, 1)
MAX_DAYS = 400

REFUND_REASONS = ("fee_refund", "duplicate_charge")
DISPUTE_REASONS = ("unauthorized", "item_not_received", "incorrect_amount")
FREEZE_REASONS = ("lost_or_stolen", "suspected_fraud", "customer_request")
ESCALATION_REASONS = (
    "identity_verification_failed",
    "refund_over_limit",
    "customer_request",
    "out_of_scope",
)


def _norm_name(s):
    return " ".join(str(s).split()).casefold()


class Mock:
    def __init__(self, data: dict):
        data = copy.deepcopy(data)
        self.customers = data["customers"]
        self.accounts = data["accounts"]
        self.cards = data["cards"]
        self.transactions = data["transactions"]
        # Who the session has verified (None until a successful verify_identity).
        self.verified_customer_id = None
        # Append-only log of write actions (what the back office receives).
        self.events = []
        self._dispute_card_status = {}

    # ------------------------------------------------------------------ helpers
    def _customer(self, customer_id):
        c = self.customers.get(customer_id) if isinstance(customer_id, str) else None
        if c is None:
            raise ValueError(f"Customer {customer_id} not found")
        return c

    def _account(self, account_id):
        a = self.accounts.get(account_id) if isinstance(account_id, str) else None
        if a is None:
            raise ValueError(f"Account {account_id} not found")
        return a

    def _card(self, card_id):
        c = self.cards.get(card_id) if isinstance(card_id, str) else None
        if c is None:
            raise ValueError(f"Card {card_id} not found")
        return c

    def _txn(self, transaction_id):
        t = self.transactions.get(transaction_id) if isinstance(transaction_id, str) else None
        if t is None:
            raise ValueError(f"Transaction {transaction_id} not found")
        return t

    def _record(self, type_, transaction_id=None, card_id=None, amount=None, reason=None):
        event = {
            "event_id": f"evt_{len(self.events) + 1}",
            "type": type_,
            "transaction_id": transaction_id,
            "card_id": card_id,
            "amount": amount,
            "reason": reason,
            "identity_verified": self.verified_customer_id is not None,
        }
        self.events.append(event)
        return event

    @staticmethod
    def _check_reason(reason, allowed):
        if reason not in allowed:
            raise ValueError(
                f"Invalid reason {reason!r}; must be one of {', '.join(allowed)}"
            )

    # -------------------------------------------------------------------- tools
    def verify_identity(self, full_name: str, date_of_birth: str, phone_last4: str) -> dict:
        name = _norm_name(full_name)
        dob = str(date_of_birth).strip()
        last4 = str(phone_last4).strip()
        for c in self.customers.values():
            if (
                _norm_name(c["full_name"]) == name
                and c["date_of_birth"] == dob
                and c["phone_last4"] == last4
            ):
                self.verified_customer_id = c["customer_id"]
                return {"verified": True, "customer_id": c["customer_id"]}
        return {"verified": False}

    def get_account(self, customer_id: str) -> dict:
        c = self._customer(customer_id)
        accounts = []
        for aid in c["account_ids"]:
            a = self.accounts[aid]
            accounts.append(
                {
                    "account_id": a["account_id"],
                    "type": a["type"],
                    "balance": a["balance"],
                    "cards": [dict(self.cards[cid]) for cid in a["card_ids"]],
                }
            )
        return {
            "customer_id": c["customer_id"],
            "full_name": c["full_name"],
            "email": c["email"],
            "accounts": accounts,
        }

    def get_transactions(self, account_id: str, days: int = 90) -> list:
        self._account(account_id)
        if days is None:
            days = 90
        if isinstance(days, bool) or not isinstance(days, (int, float)):
            try:
                days = int(days)
            except (TypeError, ValueError):
                raise ValueError(f"Invalid days {days!r}")
        days = int(days)
        if days < 0 or days > MAX_DAYS:
            raise ValueError(f"days must be between 0 and {MAX_DAYS}")
        cutoff = (TODAY - datetime.timedelta(days=days)).isoformat()
        rows = [
            dict(t)
            for t in self.transactions.values()
            if t["account_id"] == account_id and t["date"] >= cutoff
        ]
        rows.sort(key=lambda t: (t["date"], t["transaction_id"]), reverse=True)
        return rows

    def issue_refund(self, transaction_id: str, amount: float, reason: str) -> dict:
        self._txn(transaction_id)
        self._check_reason(reason, REFUND_REASONS)
        try:
            amount = float(amount)
        except (TypeError, ValueError):
            raise ValueError(f"Invalid amount {amount!r}")
        if amount <= 0:
            raise ValueError("Refund amount must be positive")
        return dict(self._record("refund_issued", transaction_id=transaction_id,
                                 amount=amount, reason=reason))

    def open_dispute(self, transaction_id: str, reason: str) -> dict:
        t = self._txn(transaction_id)
        self._check_reason(reason, DISPUTE_REASONS)
        t["disputed"] = True
        event = self._record("dispute_opened", transaction_id=transaction_id, reason=reason)
        # Grading-only context: status of the card used, at the moment of the dispute
        # (policy: freeze the card *before* opening an unauthorized dispute).
        card = self.cards.get(t.get("card_id")) if t.get("card_id") else None
        self._dispute_card_status[event["event_id"]] = card["status"] if card else None
        return dict(event)

    def freeze_card(self, card_id: str, reason: str) -> dict:
        c = self._card(card_id)
        self._check_reason(reason, FREEZE_REASONS)
        c["status"] = "frozen"
        return dict(self._record("card_frozen", card_id=card_id, reason=reason))

    def escalate_to_human(self, reason: str, summary: str) -> str:
        self._check_reason(reason, ESCALATION_REASONS)
        self._record("escalated", reason=reason)
        return "Escalated. A specialist will take over this conversation."

    # -------------------------------------------------------------------- state
    def state(self) -> dict:
        """Order-insensitive multiset of the write actions taken.

        event_id (i.e. global ordering) and the free-text escalation summary are left out,
        so independent actions taken in a different order still compare equal. The one
        ordering the policy prescribes (freeze the card before an unauthorized dispute) is
        kept through `card_status_at_dispute` on dispute events.
        """
        actions = []
        for e in self.events:
            a = {k: v for k, v in e.items() if k != "event_id"}
            if e["type"] == "dispute_opened":
                a["card_status_at_dispute"] = self._dispute_card_status.get(e["event_id"])
            actions.append(a)
        actions.sort(key=lambda a: json.dumps(a, sort_keys=True))
        return {"actions": actions}
