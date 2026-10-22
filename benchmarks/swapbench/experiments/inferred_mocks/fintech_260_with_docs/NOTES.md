# Northbank support API mock: notes

Files: `mock.py` (the mock), `check.py` (replays every traced tool call on a fresh `Mock`).

## Replay match rate
`python3 check.py`: **1190/1190 calls, 260/260 conversations** (outputs and error flags).
The traces contain **no errors at all**, so the error behaviour below is inferred, not observed.

Comparison detail: the trace recorder stringifies every non-null scalar (`true` -> `"True"`,
`40` -> `"40.0"`, `false` -> `"False"`, `null` stays `null`). The mock returns native JSON
types as the docs describe (`{"verified": true}`); `check.py` stringifies the mock's leaves
before comparing. `"40.0"` for an input amount of `40` shows the API coerces amount to float.

## Inferred from the traces (verified by replay)
- `verify_identity`: exact match on name, DOB and phone_last4 -> `{"verified": true,
  "customer_id"}`; otherwise `{"verified": false}` (no error). Failures in the traces are
  wrong DOBs.
- `get_account`: `{customer_id, full_name, email, accounts: [{account_id, type, balance,
  cards: [{card_id, account_id, last4, status}]}]}`, accounts and cards in data order.
  Works for any customer id (no verification check).
- `get_transactions`: all raw transaction fields; filter `date >= today - days`
  (inclusive boundary; exercised by 23 calls); default 90; sorted by
  `(date, transaction_id)` descending (ties on the same date are common and all match).
- Writes return an event `{event_id: "evt_N", type, transaction_id, card_id, amount, reason,
  identity_verified}`. `N` is a per-conversation counter over write actions (verify and reads
  don't consume ids). Types: `refund_issued` (card_id null), `dispute_opened` (card_id and
  amount null, even for card purchases), `card_frozen` (transaction_id and amount null).
- `identity_verified` is recorded rather than enforced: the system lets actions through and
  logs whether the caller was verified. In the traces it is always `True` (agents always
  verified first).
- `open_dispute` sets the transaction's `disputed` to true (seen in 20 later reads).
- `issue_refund` does not create a transaction or change the balance (5 later reads of the
  same account match the unchanged snapshot): it only records the event for the back office.
- `escalate_to_human` returns `"Escalated. A specialist will take over this conversation."`.

## Not determinable; how resolved
- **Errors** (none observed): unknown customer/account/card/transaction id -> exception;
  reason outside the documented enum (refund, dispute, freeze, escalation) -> exception;
  `days` outside 0..400 -> exception (not clamped); non-positive or non-numeric refund
  amount -> exception. Policy checks (fee cap, 365-day limit, dispute window, pending,
  already disputed, already frozen, ownership) are **not** enforced by the API: the policy
  tells the agent to check them, and the API's design (logging `identity_verified` rather
  than refusing) suggests a permissive back end.
- **Frozen card status**: never read back in the traces; the mock sets `status: "frozen"`.
- **Escalation as an event**: escalation was always the last call, so whether it consumes
  an `evt_N` id is unobservable. The mock logs it as an `escalated` event (consuming an id)
  with its reason and `identity_verified`.
- **verify_identity details**: name compared case-insensitively with whitespace collapsed;
  DOB and last4 compared exactly as strings. A later failed verification does not undo an
  earlier success; a later success for another customer switches the verified customer.
  `identity_verified` is session-level (true once any customer is verified), not per resource.

## state()
`{"actions": [...]}`: the multiset (canonically sorted) of write events without `event_id`
and without the free-text escalation summary. Each entry has type, transaction_id, card_id,
amount, reason and identity_verified, so acting before verifying, wrong reasons, wrong
amounts, extra/missing/duplicate actions and wrong escalations all change the state.
Dispute entries also carry `card_status_at_dispute` (status of the card used at that
moment) so that "freeze before an unauthorized dispute" is graded while the order of
independent actions isn't. Reads, verification attempts and escalation summaries are
excluded. Card statuses and `disputed` flags follow from the actions, so they are not
duplicated.
