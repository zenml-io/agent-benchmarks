# Northbank support API mock: notes

Files: `mock.py` (the mock, `GUESSES` dict), `check.py` (replays all traces and compares).

## Replay match rate

`python3 check.py`: **226/226 calls (100%)**, **50/50 conversations** fully match (outputs and
error flags). No guess flag fires during replay. The traces contain **no errors at all**, so every
error path is a guess.

The recorder stringifies scalars (`True` -> `"True"`, `40.0` -> `"40.0"`, `None` stays `null`). The
mock returns native values (bools, floats) and `check.py` applies the same stringification before
comparing.

## Inferred state store

From `data.json`: `customers`, `accounts`, `cards`, `transactions`, plus per-conversation session
state:
- `verified_customer`: set by a successful `verify_identity`.
- an **action log**: every `issue_refund`, `open_dispute` and `freeze_card` returns an action record
  `{event_id, type, transaction_id, card_id, amount, reason, identity_verified}`; `event_id` is
  `evt_1`, `evt_2`, ... sequential per conversation across all three action types; unused fields
  are `null`; `identity_verified` reflects the session's verification.
- escalations (reason, summary).

## Inferred tool behavior (supported by traces)

- `verify_identity`: exact match on name, DOB and phone last 4 -> `{"verified": true, "customer_id"}`.
- `get_account`: `{customer_id, full_name, email, accounts: [{account_id, type, balance, cards:
  [{card_id, account_id, last4, status}]}]}`, accounts and cards in data order; no DOB or phone.
- `get_transactions`: full transaction records for the account with `date >= today - days`
  (**inclusive**, confirmed at the 60- and 90-day boundaries), default 90 days. Sorted **newest first,
  same-day ties by transaction id descending**. Includes pending, deposits, fees and earlier
  `fee_refund` rows (negative amounts).
- `open_dispute`: sets the transaction's `disputed` to true (visible in a later `get_transactions`,
  c0). Returns a `dispute_opened` record (`card_id` null, `amount` null).
- `freeze_card`: returns a `card_frozen` record (`transaction_id`/`amount` null). The mock sets the card
  status to `"frozen"`.
- `issue_refund`: returns `refund_issued` with `amount` as a float (int 40 -> 40.0). No policy checks
  were seen. The $40 cap, the 365-day rule and the $500 limit are the agent's job. Amounts in traces
  always follow policy, so whether the API enforces them can't be tested.
- `escalate_to_human`: returns the plain string `Escalated. A specialist will take over this
  conversation.`

## Grading state (`state()`)

- `frozen_cards`: the ids of frozen cards.
- `disputed_transactions`: the ids of disputed transactions.
- `actions`: the action records **without `event_id`, sorted canonically**. A multiset, so the order
  of independent actions doesn't matter. The one ordering rule in the policy is kept: an
  `unauthorized` dispute carries `card_frozen_before` (was the transaction's card already frozen when
  the dispute was opened). Duplicate actions, wrong amounts or reasons, the wrong transaction or card,
  and actions taken before verification (`identity_verified: false`) all change the state.
- `escalations`: `{reason, identity_verified}` per call, so escalating twice, the wrong reason or
  escalating without verification all count. The free-text summary is left out.
- Left out: read-only lookups, verification attempts, the verified customer and the summaries.

## Guesses (each sets a flag when it runs; see `GUESSES` in mock.py)

- `verify_failed`: a failure returns `{"verified": false, "customer_id": null}` rather than raising.
- `verify_switch_customer`: a second successful verification of another customer replaces the first.
- `unverified_access`: before verification, lookups still answer and actions are recorded with
  `identity_verified=false`, not refused. Inferred from the field's existence.
- `unknown_customer` / `unknown_account` / `unknown_transaction` / `unknown_card`: raise.
- `invalid_reason`: a reason outside the description's enum raises.
- `invalid_days`: days outside 1..400, or not an integer, raises.
- `invalid_amount`: an amount <= 0 or not numeric raises.
- `refund_exceeds_transaction`, `refund_repeat`, `refund_nonstandard_txn`: accepted and recorded
  (no API-side policy enforcement).
- `refund_not_in_transactions`: a refund creates no new transaction and doesn't change the balance
  ("Recorded for back-office processing").
- `dispute_already_disputed`, `dispute_ineligible_txn`: accepted and recorded.
- `freeze_already_frozen`: accepted and recorded again.
- `frozen_card_shown`: `get_account` shows status `"frozen"`. The value is never observed.
- `action_after_escalation`: escalation doesn't use up an event_id.
- `escalate_repeat`: every escalation is recorded.

## Could not be inferred

- Any error message or error condition. None appear in the traces.
- The output of a failed verification, and whether failures are counted or locked server-side.
- Whether the API enforces any business rule: refund caps, the 365-day fee rule, the $500 limit,
  dispute eligibility, freeze-before-dispute.
- Whether a refund changes the balance or adds a `fee_refund` transaction during the conversation.
- The exact status string of a frozen card, and whether `card_frozen_before` is how the real system
  checks that order (it is the mock's way to grade it).
- Whether escalation shares the event counter.
