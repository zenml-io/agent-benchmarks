# Northbank support API mock: notes

Files: `mock.py` (the mock), `check.py` (replays every trace on a fresh `Mock`).

## Replay match rate

`python3 check.py`: **454/454 calls (100%)**, **100/100 conversations**, with no
per-conversation special cases. Outputs are compared after stringifying leaves the way the
recorder does (`str(v)`, `None` kept as null). Escalation returns a plain string. The traces contain
**no errors and no failed verifications**, so every error path below is a guess.

## Inferred state store and rules (supported by traces)

- Store: `data.json` (customers, accounts, cards, transactions) plus a per-conversation **event log**
  and the **verified customer** for the session.
- `verify_identity`: exact match on full_name, date_of_birth and phone_last4 returns
  `{"verified": true, "customer_id": ...}` and marks the session verified.
- `get_account`: `{customer_id, full_name, email, accounts: [{account_id, type, balance, cards: [card
  record]}]}`, with accounts and cards in the snapshot's order. DOB, phone and account_ids are not exposed.
- `get_transactions(account_id, days=90)`: full transaction records with `date >= 2026-10-01 - days`
  (inclusive; confirmed at days=60 → 2026-08-02). Pending and every kind are included. Sorted by date,
  newest first; same-date ties come in reverse snapshot order (higher id first, 180 tie pairs matched).
  Disputes show up in later reads (`disputed: true`).
- Writes return an event `{event_id: "evt_N", type, transaction_id, card_id, amount, reason,
  identity_verified}`. N is a counter for the conversation, starting at 1.
  - `issue_refund` → `refund_issued`, amount as float (40 → 40.0), card_id null.
  - `open_dispute` → `dispute_opened`, amount/card_id null; it sets the transaction's `disputed` flag.
  - `freeze_card` → `card_frozen`, transaction_id/amount null; it sets the card's status.
  - `escalate_to_human` → returns `"Escalated. A specialist will take over this conversation."`.
- `state()`: the event log without event ids, order-insensitive (type, ids, amount, reason,
  identity_verified; the escalation summary is free text and excluded), plus the frozen cards and
  disputed transactions. Read-only calls and verification attempts are not included.

## Guesses (each flags `self.flags` at run time; full text in `GUESSES`)

- `verify_failed`: a failed match returns `{"verified": false, "customer_id": null}`, not an error.
- `verify_switch_customer`: a second successful verify replaces the session's customer.
- `unverified_action`: writes before verification are not blocked. They are recorded with
  `identity_verified: false`; the field exists for exactly this.
- `read_unverified_or_other`: reads are not restricted to the verified customer.
- `get_account_not_found`, `get_transactions_not_found`, `txn_not_found`, `card_not_found`: raise.
- `get_transactions_bad_days`: days outside 1..400 raises.
- `bad_reason`: a reason outside the schema enum raises. `bad_amount`: refund amount <= 0 raises.
- `refund_no_validation`: refunds that break the policy (wrong kind, over the $40 cap, ATM fee,
  over $500, another customer's transaction) are still recorded. The tool says "recorded for back-office
  processing". The violation shows in the event log.
- `refund_repeat`: a repeated refund is recorded again.
- `refund_no_ledger_effect`: a refund adds no transaction and changes no balance (never observed).
- `dispute_not_eligible`: disputes on pending, too-old, non-purchase or other-customer transactions
  are recorded.
- `dispute_already_disputed`: disputing an already-disputed transaction raises.
- `freeze_already_frozen`: freezing a frozen card raises.
- `frozen_status_value`: a frozen card reads `status: "frozen"`.
- `escalate_event_id` / `escalate_repeat`: escalation records an `escalated` event that uses the evt
  counter (never observed, because no write followed an escalation), and repeated escalations are recorded.

## Not inferable from the traces

- Any error message text or error behavior (no errors were recorded).
- The output of a failed verification, and whether failed attempts are counted or locked out server-side.
- Whether escalation consumes an event id, and whether the server stores the summary.
- Refund side effects on balances and transactions, and the card status label after a freeze.
- Whether the server enforces any business rule (365-day fee-refund limit, $40 cap, 60-day window,
  ownership). Every recorded write was policy-compliant, so no rule was ever seen to reject one.
- Whether the order of events matters for grading. I chose order-insensitive, which means the
  "freeze before unauthorized dispute" order is not checked.
