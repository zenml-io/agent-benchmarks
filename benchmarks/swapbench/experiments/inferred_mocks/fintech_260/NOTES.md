# Northbank support API mock: notes

Files: `mock.py` (the mock, `Mock` + `GUESSES`), `check.py` (replays the traces; `-v` prints mismatches).

## Replay match rate
`python3 check.py`: **1190/1190 calls (100%)** and **260/260 conversations** match, outputs and
error flags included. The traces contain **no errors at all**, so every error path is a guess.
The checker compares `stringify(mock output)` with the recording, because the recorder turned every
non-string scalar into its Python `str` (`True` -> `"True"`, `40.0` -> `"40.0"`) and kept `None` as `null`.
The mock returns native types (bool, float).

## Inferred state store
- `customers`, `accounts`, `cards`, `transactions` from `data.json`.
- A per-conversation **action log**. Each write returns its event:
  `{event_id: "evt_<n>", type, transaction_id, card_id, amount, reason, identity_verified}`, where
  `n` counts from 1 in each conversation, `type` is `refund_issued` / `dispute_opened` / `card_frozen`,
  and the fields that don't apply to the type are `null`.
- **Session verification**: `identity_verified` is stamped on each action. Writes are never refused
  for lack of verification. The API seems to record actions, not enforce policy.

## Inferred tool behaviour (supported by the traces)
- `verify_identity`: an exact match on all three fields gives `{"verified": true, "customer_id"}`, anything
  else gives `{"verified": false}` (no customer_id). It does not raise an error.
- `get_account`: `{customer_id, full_name, email, accounts:[{account_id, type, balance, cards:[{card_id,
  account_id, last4, status}]}]}`, with accounts in `account_ids` order. DOB and phone are not exposed.
- `get_transactions`: full transaction records with `account_id == id` and `date >= 2026-10-01 - days`,
  sorted **newest first, ties broken by transaction id descending**. `days` defaults to 90 (8 calls omitted it).
  All 329 calls match, including days 5..400.
- `open_dispute`: sets the transaction's `disputed=true`, which later `get_transactions` calls show (17 conversations).
- `issue_refund`: the event `amount` is `float(amount)` (an int 40 is recorded as `"40.0"`). **No new transaction
  is created and no balance changes**: 5 reads of a refunded account after the refund show the same set
  ("recorded for back-office processing").
- `freeze_card`: the event has `card_id`.
- `escalate_to_human`: returns the plain string `"Escalated. A specialist will take over this conversation."`.
- Every recorded refund and dispute follows the policy. The mock's policy checker (used only to flag guesses)
  flags none of them, which supports the reading of the fee cap, the 365-day rule and the duplicate rule.

## State used for grading (`state()`)
- `actions`: every refund, dispute, freeze and escalation with type, ids, amount, reason and
  `identity_verified`. Disputes also carry `card_status_at_open`, which keeps the "freeze before an
  unauthorized dispute" order. Escalations carry `after_two_failed_verifications`. The list is in a
  canonical sort order, not event-id order, so independent tasks done in a different order still compare
  equal. Event ids and escalation summaries (free text) are left out.
- `card_status_changes` (cards no longer `active`) and `disputed_transactions`.
- Reads, verification attempts and balances (never changed) are left out.

## Guesses (all in `GUESSES`, flagged when taken)
- **Errors** (none observed): unknown customer, account, transaction or card; a reason outside the schema
  enum; refund amount <= 0; `days` outside 1..400 or not an integer; a dispute on a non-card transaction
  (fee, deposit or refund); a dispute on an already-disputed transaction; freezing an already-frozen card.
  All of these raise an exception.
- **Policy violations are recorded, not refused** (`refund_policy_violation`, `dispute_policy_violation`,
  `write_unverified`, `refund_repeat_txn`, `escalate_twice`). This follows from the `identity_verified`
  stamp and the back-office wording. It also means a wrong action shows up in the graded state instead
  of being silently blocked.
- `identity_verified` is true only when the session's verified customer owns the target account.
  Traces only show the true case.
- `freeze_card` sets the card status to `frozen`. No read after a freeze exists to confirm it.
- An escalation takes an `evt_<n>` id. No write ever follows an escalation in the traces.
- Verification edge cases: a name that differs only in case or whitespace fails. A failed retry after a
  success keeps the earlier customer. A second success for another customer switches the session.
  Verification still works after two failures.
- Refund amounts are rounded to cents.

## Not inferable from the traces
- Any real error message or error shape. No call errored.
- Card status after a freeze, and whether a frozen card can be frozen again or unfrozen.
- Whether refunds ever affect balances or the transaction list later on (back-office processing).
- Whether the real API enforces any business rule (caps, eligibility, the 60-day window, pending status,
  the $500 limit). All recorded calls were compliant, so the traces can't tell recording from enforcing.
- What the escalation does to the session (later calls blocked?), and whether it counts in the event sequence.
- Whether verification is per customer or per conversation beyond the true case.
