# Retail tool API mock: notes

Files: `mock.py` (the `Mock` class plus `GUESSES`) and `check.py` (replays every trace on a fresh Mock).

## Replay match rate

`python3 check.py`: **448/448 calls match** (output string and error flag), **50/50 conversations**
fully match. No conversation is special-cased. The traces contain **no errored calls at all**, so every
error path is a guess.

## Inferred state store

- `products[product_id]` = `{name, product_id, variants{item_id: {item_id, options, available, price}}}`. No tool changes products (no inventory decrement was observed).
- `users[user_id]` = `{user_id, name, address, email, payment_methods{id: {source, id, [brand, last_four] | [balance]}}, orders}`.
- `orders[order_id]` = the data.json fields plus seven fields the API always returns, null until set:
  `cancel_reason, exchange_items, exchange_new_items, exchange_payment_method_id,
  exchange_price_difference, return_items, return_payment_method_id` (in that order, after `payment_history`).
  Orders cancelled in data.json come back with `cancel_reason: null`.
- Recorder format: dicts and lists are `json.dumps` with insertion order; strings are returned raw.

## Inferred tool behavior (observed)

- `find_user_id_by_email`: exact email match, returns the bare user id string.
- `find_user_id_by_name_zip`: exact first name, last name and address zip match, returns the user id.
- `get_user_details`, `get_product_details`: the stored record, unchanged.
- `get_order_details`: the stored order with the seven extra fields.
- `calculate`: evaluates the expression and returns `str(round(value, 2))` (`'268.77 - 256.73'` gives `'12.04'`).
- `cancel_pending_order`: status `cancelled`, `cancel_reason` = reason, and a `refund` transaction of the full paid amount to the original method is appended to `payment_history`. Returns the order.
- `modify_pending_order_address`: replaces `order.address` with keys ordered `address1, address2, city, country, state, zip`. Status stays `pending`.
- `modify_pending_order_items`: each listed item is replaced in place (same position, same name and product_id; new `item_id`, `price`, `options`). Status becomes **`pending (item modified)`** (the policy's spelling "items modifed" is not what the API writes). The price difference `sum(new - old)` is appended unrounded (raw float, e.g. `12.039999999999964`): as a `refund` when negative, a `payment` when positive (both observed), to the given method, which may differ from the original payment method (gift card refunds were observed).
- `return_delivered_order_items`: status `return requested`, `return_items` = the given ids **sorted**, `return_payment_method_id`. `payment_history` is unchanged.
- `exchange_delivered_order_items`: status `exchange requested`. `exchange_items` and `exchange_new_items` are each **sorted independently** (traces show cases where one list is reordered and the other isn't, so the old/new pairing is not kept). `exchange_payment_method_id` is set, `exchange_price_difference` = `round(sum(new) - sum(old), 2)`. Items and `payment_history` are unchanged. A method other than the original payment method was observed.
- Reads never reflect a write of the same record in any trace (no trace re-reads a modified order or user), so the visible read-after-write behavior follows directly from the stored state.

## State used for grading (`state()`)

`{users, orders, products, transferred_to_human}`:
- Full orders (status, items, address, payment_history, cancel/exchange/return fields) and full users (address and gift card balances). These hold everything the policy's actions change.
- Amounts (payments, refunds, balances, price differences) are rounded to 2 decimals, so float noise from summing items in a different order doesn't fail an otherwise correct agent. Return and exchange item lists are already sorted by the API, so the order an agent lists items in doesn't matter.
- Read-only lookups leave no trace in the state.
- `transferred_to_human` (a boolean, not the summary text): the policy makes transferring a graded decision ("if and only if" the request is out of scope), and a real system would log the handoff. **Design decision:** an agent that does every write correctly but transfers when it shouldn't (or fails to transfer when it should) fails.

## Guesses (each appends its label to `mock.flags` when it runs; see `GUESSES` in mock.py)

Errors (none observed; messages are invented, and only the fact that the call raises should matter):
- Not found: `user_email_not_found`, `user_name_zip_not_found` (exact, case-sensitive match), `order_not_found`, `user_not_found`, `product_not_found`, `item_not_found`, `calculate_error`.
- Status: `cancel_not_pending`, `modify_not_pending` (any status other than exactly `pending`, so a second item modification, or a cancellation after one, errors), `return_not_delivered`, `exchange_not_delivered`.
- Arguments: `cancel_bad_reason`, `items_not_in_order` (counts duplicates), `item_lists_length_mismatch`, `new_item_not_found` (not a variant of the same product), `new_item_unavailable`, `new_item_same_as_old`, `payment_method_not_found` (must belong to the order's user), `gift_card_insufficient`, `return_payment_not_allowed` (refund must go to the original method or a gift card), `modify_payment_same_method`, `modify_payment_multiple_payments`.

State effects not visible in the traces:
- `cancel_gift_card_refund_balance`: a gift card refund on cancellation is added to the card's balance (from the policy).
- `cancel_multiple_payment_methods`: cancelling after a payment change refunds the net amount on each method.
- `modify_items_gift_card_balance`: the gift card balance absorbs the price difference of an item modification.
- `modify_items_zero_difference`: no transaction is added when the difference is 0.
- Exchanges and returns are only *requested*: no balance or payment change (consistent with the observed unchanged `payment_history`).

Tools never called in the traces:
- `modify_pending_order_payment` (`modify_payment`): adds a `payment` of the total on the new method and a `refund` of it to the old one, adjusts gift card balances, and keeps status `pending`.
- `modify_user_address` (`modify_user_address`): replaces the user's address and returns the user.
- `get_item_details` (`get_item_details`): returns the stored variant dict.
- `list_all_product_types` (`list_all_product_types`): returns `{name: product_id}` sorted by name.
- `transfer_to_human_agents` (`transfer_to_human_agents`): returns `"Transfer successful"`.

## Could not be inferred

- Every error message and error condition. The traces contain zero errors.
- Whether gift card balances really change (never re-read after a write), and whether exchanges or returns move money later.
- Output formats of the five tools never called. The output of `modify_pending_order_payment` and the transaction order it writes are pure guesses.
- Whether lookups are case-insensitive or trim whitespace.
- How the unrounded refund float is accumulated for multi-item modifications. Only single-item modifications were recorded; the mock sums `new - old` per pair in order. The grading state rounds it anyway.
- Whether `calculate` accepts operators beyond `+ - * / ( )`.
