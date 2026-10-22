"""A small tau2 domain: banking/payments customer support ("fintech").

Seven tools over a mocked state store. Money-moving and card actions are never executed: they are
appended to `events` (with whether the customer's identity had been verified at that moment), so the
final state captures what the agent did, in what order, and with what amounts. tau2's DB check compares
that state with the one produced by the scenario's gold actions, so a refund issued before identity
verification, a wrong amount, a dispute outside the window or a missing card freeze all fail.

Data lives in $SWAPBENCH_FINTECH_DIR: db.json, policy.md, tasks.json, split_tasks.json.
SWAPBENCH_GUARDS=1 turns on hard guardrails: write tools refuse calls that break the policy's checkable
rules (identity, fee cap and eligibility, duplicate definition, dispute window, escalate once), so a model
mistake becomes a tool error instead of a recorded action. SWAPBENCH_POLICY_ADDENDUM=<file> appends text
to the policy the agent sees (grading is unchanged).
Register with `register()` before using tau2 (swapbench/fintech/run.py does this for the CLI).
"""
import json
import os
from datetime import date, timedelta
from typing import Dict, List, Literal, Optional

from pydantic import BaseModel, Field

from tau2.data_model.tasks import Task
from tau2.environment.db import DB
from tau2.environment.environment import Environment
from tau2.environment.toolkit import ToolKitBase, ToolType, is_tool

TODAY = date(2026, 10, 1)
HERE = os.path.dirname(os.path.abspath(__file__))


def data_dir():
    return os.environ.get("SWAPBENCH_FINTECH_DIR", os.path.join(HERE, "data"))


class Customer(BaseModel):
    customer_id: str
    full_name: str
    date_of_birth: str = Field(description="YYYY-MM-DD")
    phone_last4: str
    email: str
    account_ids: List[str]


class Card(BaseModel):
    card_id: str
    account_id: str
    last4: str
    status: Literal["active", "frozen"] = "active"


class Account(BaseModel):
    account_id: str
    customer_id: str
    type: Literal["checking", "credit_card"]
    balance: float
    card_ids: List[str]


class Transaction(BaseModel):
    transaction_id: str
    account_id: str
    card_id: Optional[str] = None
    date: str = Field(description="YYYY-MM-DD")
    merchant: str
    amount: float = Field(description="Positive = money out of the customer's account")
    kind: Literal["purchase", "fee", "fee_refund", "refund", "payment", "deposit"]
    fee_type: Optional[Literal["overdraft", "late_payment", "foreign_transaction", "atm"]] = None
    status: Literal["posted", "pending"] = "posted"
    disputed: bool = False


class Event(BaseModel):
    event_id: str
    type: Literal["refund_issued", "dispute_opened", "card_frozen", "escalated"]
    transaction_id: Optional[str] = None
    card_id: Optional[str] = None
    amount: Optional[float] = None
    reason: str
    identity_verified: bool = Field(description="Was the owner's identity verified when this happened")


class Session(BaseModel):
    verified_customer_id: Optional[str] = None


class FintechDB(DB):
    customers: Dict[str, Customer]
    accounts: Dict[str, Account]
    cards: Dict[str, Card]
    transactions: Dict[str, Transaction]
    events: List[Event] = Field(default_factory=list)
    session: Session = Field(default_factory=Session)


REFUND_REASONS = ("fee_refund", "duplicate_charge")
DISPUTE_REASONS = ("unauthorized", "item_not_received", "incorrect_amount")
FREEZE_REASONS = ("lost_or_stolen", "suspected_fraud", "customer_request")
ESCALATION_REASONS = ("identity_verification_failed", "refund_over_limit", "customer_request", "out_of_scope")


class FintechTools(ToolKitBase):
    db: FintechDB

    def __init__(self, db: FintechDB) -> None:
        super().__init__(db)

    # ---- helpers ------------------------------------------------------------------------------------------------
    def _txn(self, transaction_id):
        if transaction_id not in self.db.transactions:
            raise ValueError("Transaction not found")
        return self.db.transactions[transaction_id]

    def _owner(self, account_id):
        return self.db.accounts[account_id].customer_id

    def _verified_for(self, account_id):
        return self.db.session.verified_customer_id == self._owner(account_id)

    def _guard(self, ok, why):
        if GUARDS and not ok:
            raise ValueError(f"Blocked by policy guardrail: {why}")

    def _guard_verified(self, account_id):
        self._guard(self._verified_for(account_id), "verify the customer's identity before acting on this account")

    def _event(self, **kw):
        ev = Event(event_id=f"evt_{len(self.db.events) + 1}", **kw)
        self.db.events.append(ev)
        return ev

    # ---- tools --------------------------------------------------------------------------------------------------
    @is_tool(ToolType.WRITE)
    def verify_identity(self, full_name: str, date_of_birth: str, phone_last4: str) -> dict:
        """Verify the caller's identity. All three must match the customer record.

        Args:
            full_name: The customer's full name, e.g. 'Maria Lopez'.
            date_of_birth: Date of birth in YYYY-MM-DD format.
            phone_last4: The last four digits of the phone number on file.

        Returns:
            {"verified": true, "customer_id": ...} on success, otherwise {"verified": false}.
        """
        for c in self.db.customers.values():
            if (c.full_name.lower() == full_name.strip().lower() and c.date_of_birth == date_of_birth.strip()
                    and c.phone_last4 == str(phone_last4).strip()):
                self.db.session.verified_customer_id = c.customer_id
                if MACRO:  # trajectory compression: bundle the lookups that nearly always follow a verification
                    acct = self.get_account(c.customer_id)
                    return {"verified": True, "customer_id": c.customer_id, "account": acct,
                            "transactions_last_365_days": {a["account_id"]: self.get_transactions(a["account_id"], 365)
                                                           for a in acct.get("accounts", [])}}
                return {"verified": True, "customer_id": c.customer_id}
        return {"verified": False}

    @is_tool(ToolType.READ)
    def get_account(self, customer_id: str) -> dict:
        """Get a customer's profile, accounts and cards.

        Args:
            customer_id: The customer id, such as 'cus_10293'.

        Returns:
            The customer's name, email, accounts (id, type, balance) and cards (id, last4, status).
        """
        if customer_id not in self.db.customers:
            raise ValueError("Customer not found")
        c = self.db.customers[customer_id]
        accts = [self.db.accounts[a] for a in c.account_ids]
        return {"customer_id": c.customer_id, "full_name": c.full_name, "email": c.email,
                "accounts": [{"account_id": a.account_id, "type": a.type, "balance": a.balance,
                              "cards": [self.db.cards[k].model_dump() for k in a.card_ids]} for a in accts]}

    @is_tool(ToolType.READ)
    def get_transactions(self, account_id: str, days: int = 90) -> List[dict]:
        """List an account's transactions from the last `days` days (today is 2026-10-01), newest first.

        Args:
            account_id: The account id, such as 'acc_20481'.
            days: How many days back to look (default 90, maximum 400).

        Returns:
            Transactions with id, date, merchant, amount, kind (purchase, fee, fee_refund, refund,
            payment, deposit), fee_type for fees, status (posted or pending), card_id and disputed.
        """
        if account_id not in self.db.accounts:
            raise ValueError("Account not found")
        since = (TODAY - timedelta(days=min(int(days), 400))).isoformat()
        rows = [t for t in self.db.transactions.values() if t.account_id == account_id and t.date >= since]
        return [t.model_dump() for t in sorted(rows, key=lambda t: (t.date, t.transaction_id), reverse=True)]

    @is_tool(ToolType.WRITE)
    def issue_refund(self, transaction_id: str, amount: float, reason: str) -> dict:
        """Refund money to the customer for a transaction. Recorded for back-office processing.

        Args:
            transaction_id: The transaction being refunded.
            amount: The refund amount in dollars.
            reason: One of 'fee_refund' or 'duplicate_charge'.

        Returns:
            The recorded refund event.
        """
        if reason not in REFUND_REASONS:
            raise ValueError(f"reason must be one of {REFUND_REASONS}")
        t = self._txn(transaction_id)
        if GUARDS:
            self._guard_refund(t, round(float(amount), 2), reason)
        return self._event(type="refund_issued", transaction_id=transaction_id, amount=round(float(amount), 2),
                           reason=reason, identity_verified=self._verified_for(t.account_id)).model_dump()

    @is_tool(ToolType.WRITE)
    def open_dispute(self, transaction_id: str, reason: str) -> dict:
        """Open a dispute (chargeback) for a card transaction.

        Args:
            transaction_id: The disputed transaction.
            reason: One of 'unauthorized', 'item_not_received' or 'incorrect_amount'.

        Returns:
            The recorded dispute event.
        """
        if reason not in DISPUTE_REASONS:
            raise ValueError(f"reason must be one of {DISPUTE_REASONS}")
        t = self._txn(transaction_id)
        if GUARDS:
            self._guard_verified(t.account_id)
            self._guard(t.kind == "purchase", "only purchases can be disputed")
            self._guard(t.status == "posted", "pending charges can be disputed only once posted")
            self._guard(t.date >= (TODAY - timedelta(days=60)).isoformat(), "the 60-day dispute window has closed")
            self._guard(not t.disputed, "this transaction is already disputed")
            if reason == "unauthorized":
                self._guard(t.card_id is None or self.db.cards[t.card_id].status == "frozen",
                            "freeze the card (suspected_fraud) before disputing an unauthorized charge")
        t.disputed = True
        return self._event(type="dispute_opened", transaction_id=transaction_id, reason=reason,
                           identity_verified=self._verified_for(t.account_id)).model_dump()

    @is_tool(ToolType.WRITE)
    def freeze_card(self, card_id: str, reason: str) -> dict:
        """Freeze a card so no new charges can be made with it.

        Args:
            card_id: The card id, such as 'card_55120'.
            reason: One of 'lost_or_stolen', 'suspected_fraud' or 'customer_request'.

        Returns:
            The recorded freeze event.
        """
        if reason not in FREEZE_REASONS:
            raise ValueError(f"reason must be one of {FREEZE_REASONS}")
        if card_id not in self.db.cards:
            raise ValueError("Card not found")
        card = self.db.cards[card_id]
        if GUARDS:
            self._guard_verified(card.account_id)
        card.status = "frozen"
        return self._event(type="card_frozen", card_id=card_id, reason=reason,
                           identity_verified=self._verified_for(card.account_id)).model_dump()

    @is_tool(ToolType.WRITE)
    def escalate_to_human(self, reason: str, summary: str) -> str:
        """Hand the conversation to a human specialist.

        Args:
            reason: One of 'identity_verification_failed', 'refund_over_limit', 'customer_request', 'out_of_scope'.
            summary: A short summary of the issue for the specialist.

        Returns:
            Confirmation that the conversation was escalated.
        """
        if reason not in ESCALATION_REASONS:
            raise ValueError(f"reason must be one of {ESCALATION_REASONS}")
        if GUARDS:
            self._guard(reason == "identity_verification_failed" or self.db.session.verified_customer_id is not None,
                        "verify the customer's identity before escalating")
            self._guard(not any(e.type == "escalated" for e in self.db.events), "already escalated in this conversation")
        self._event(type="escalated", reason=reason, identity_verified=self.db.session.verified_customer_id is not None)
        return "Escalated. A specialist will take over this conversation."

    def _guard_refund(self, t, amount, reason):
        self._guard_verified(t.account_id)
        owner = self._owner(t.account_id)
        if reason == "fee_refund":
            self._guard(t.kind == "fee" and t.fee_type in ("overdraft", "late_payment", "foreign_transaction"),
                        "only overdraft, late payment and foreign transaction fees are refundable")
            self._guard(amount <= min(round(t.amount, 2), 40.0), "fee refunds are capped at the fee amount and $40.00")
            since = (TODAY - timedelta(days=365)).isoformat()
            accts = set(self.db.customers[owner].account_ids)
            prior = any(x.kind == "fee_refund" and x.account_id in accts and x.date >= since
                        for x in self.db.transactions.values())
            prior = prior or any(e.type == "refund_issued" and e.reason == "fee_refund" for e in self.db.events)
            self._guard(not prior, "the customer already had a fee refund in the last 365 days")
        else:
            self._guard(t.kind == "purchase" and t.status == "posted", "only posted purchases can be duplicates")
            d = date.fromisoformat(t.date)
            earlier = [x for x in self.db.transactions.values()
                       if x.transaction_id != t.transaction_id and x.account_id == t.account_id and x.kind == "purchase"
                       and x.status == "posted" and x.merchant == t.merchant and abs(x.amount - t.amount) < 0.005
                       and 0 <= (d - date.fromisoformat(x.date)).days <= 2
                       and (x.date, x.transaction_id) < (t.date, t.transaction_id)]
            self._guard(bool(earlier), "not a duplicate: no earlier posted charge, same merchant and amount, within 2 days")
            self._guard(t.amount <= 500.0, "duplicates over $500.00 must be escalated (refund_over_limit), not refunded")
            self._guard(abs(amount - round(t.amount, 2)) < 0.005, "refund the duplicate's full amount")


GUARDS = os.environ.get("SWAPBENCH_GUARDS") == "1"
MACRO = os.environ.get("SWAPBENCH_MACRO") == "1"  # verify_identity also returns the account and 365 days of transactions


def get_environment(db: Optional[FintechDB] = None, solo_mode: bool = False) -> Environment:
    if solo_mode:
        raise ValueError("fintech does not support solo mode")
    if db is None:
        db = FintechDB.load(os.path.join(data_dir(), "db.json"))
    policy = open(os.path.join(data_dir(), "policy.md")).read()
    if os.environ.get("SWAPBENCH_POLICY_ADDENDUM"):
        policy += "\n" + open(os.environ["SWAPBENCH_POLICY_ADDENDUM"]).read()
    return Environment(domain_name="fintech", policy=policy, tools=FintechTools(db))


def get_tasks_split() -> dict:
    return json.load(open(os.path.join(data_dir(), "split_tasks.json")))


def get_tasks(task_split_name: Optional[str] = "base") -> list:
    tasks = [Task.model_validate(t) for t in json.load(open(os.path.join(data_dir(), "tasks.json")))]
    if task_split_name is None:
        return tasks
    ids = set(get_tasks_split()[task_split_name])
    return [t for t in tasks if t.id in ids]


def register():
    from tau2.registry import registry
    if "fintech" not in registry.get_domains():
        registry.register_domain(get_environment, "fintech")
        registry.register_tasks(get_tasks, "fintech", get_task_splits=get_tasks_split)
