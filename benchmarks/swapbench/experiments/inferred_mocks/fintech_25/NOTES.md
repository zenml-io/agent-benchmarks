# Northbank mock: notes

## Replay match rate
`python3 check.py`: **116/116 calls, 25/25 conversations** match the recordings (outputs and
error flags). The traces contain **no errors at all**, so every error path is a guess.
The recorder stringifies non-null scalars (`True` -> `"True"`, `40` -> `"40.0"`); the mock returns
native types and `check.py` applies the same stringification before comparing.

## Inferred state store and rules
- Store = `data.json` (customers, accounts, cards, transactions) + a per-conversation verified
  customer + an ordered **event log** of write actions + a list of escalations.
- `verify_identity`: exact match of full_name, date_of_birth, phone_last4 against a customer ->
  `{"verified": true, "customer_id": ...}`; sets the session's verified customer.
- `get_account`: `{customer_id, full_name, email, accounts:[{account_id, type, balance,
  cards:[full card records]}]}` (no DOB/phone), accounts and cards in stored order.
- `get_transactions`: full transaction records of the account with `date >= today - days`
  (inclusive; confirmed by boundary-dated rows in traces), sorted by date desc, ties by
  transaction_id desc (48 ties in traces confirm), default days=90. Reflects `disputed=true`
  after `open_dispute` (seen in c0).
- Writes return an event `{event_id: "evt_N", type, transaction_id, card_id, amount, reason,
  identity_verified}`; N counts writes in the conversation from 1.
  - `issue_refund` -> `refund_issued`, amount as float (int 40 -> 40.0), card_id null.
  - `open_dispute` -> `dispute_opened`, amount/card_id null; sets the transaction's `disputed`.
  - `freeze_card` -> `card_frozen`, transaction_id/amount null; sets card status.
- `escalate_to_human` returns the plain string
  `Escalated. A specialist will take over this conversation.` (no event).
- The `identity_verified` field on every event implies the back end records actions even when
  unverified, i.e. policy is enforced by the agent, not the API. The mock therefore records
  policy-violating writes (and flags them) rather than rejecting them, so a misbehaving agent
  changes the graded state.

## state() (grading)
- `actions`: write events without `event_id`, sorted canonically (order of independent actions
  doesn't matter). Dispute records carry `card_frozen_before` so "freeze before an unauthorized
  dispute" is still graded.
- `escalations`: reason + identity_verified (summary text excluded, it is free text); count matters.
- `card_statuses` (non-active cards), `disputed_transactions`.
- `verification_failures` capped at 3 (distinguishes "stopped after two failures" from retrying).
- Read-only lookups are not in state.

## Guesses (all in `GUESSES`, flagged at runtime)
verify_failed (returns verified false, customer_id null; no raise), verify_failed_keeps_previous,
verify_switch_customer, unverified_read, unverified_action (recorded with identity_verified
false), action_other_customer, customer/account/transaction/card_not_found (raise),
days_out_of_range (<1 or >400 raises), invalid_reason (enum violation raises), invalid_amount,
refund_policy_not_enforced, refund_repeat, refund_no_ledger_effect, dispute_policy_not_enforced,
dispute_already_disputed, freeze_already_frozen (all recorded, not rejected),
frozen_status_value ("frozen"), event_after_escalation (escalation doesn't consume evt_N),
escalate_unverified.

## Not inferable from the traces
- Any error message text or error behavior (zero errors recorded).
- Failed-verification output; whether verification is case/whitespace sensitive.
- The card status string after a freeze (never read back), and whether a refund changes balance
  or appends a `fee_refund` transaction (never read back after a refund).
- Whether escalation is an evt_N event (no write ever follows an escalation).
- Whether the API itself enforces any policy rule (no violating call was recorded).
