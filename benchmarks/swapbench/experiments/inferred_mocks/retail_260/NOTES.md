# Retail support API mock: notes

Files: `mock.py` (the `Mock` class and `GUESSES`), `check.py` (replays every trace on a fresh Mock).

## Replay match rate

`python3 check.py`: **2393/2393 calls (100%)**, **260/260 conversations (100%)**. Outputs are compared as
exact strings: `json.dumps(result)` for dicts, the raw string for string results. Error flags are compared too.
The traces contain **no errored calls**, so every error path is a guess.
Guess flags raised during replay: `exchange_gift_card_untouched` (34), `gift_card_balance_on_item_modify` (30).
These mark state effects (gift card balances) that the traces never let us observe, not output mismatches.

## Inferred state store

`data.json` = `products` (by product id; `variants` by item id with `options`, `available`, `price`),
`users` (by user id; `payment_methods` by id: gift cards have `balance`, credit cards `brand`/`last_four`,
paypal only `source`/`id`; `orders` list), `orders` (by order id).
Every order returned by the API has seven extra fields after `payment_history`, `null` until set:
`cancel_reason, exchange_items, exchange_new_items, exchange_payment_method_id, exchange_price_difference,
return_items, return_payment_method_id`. This holds even for orders that were cancelled in data.json, whose `cancel_reason` stays `null`.
The mock adds them on load.

## Inferred rules (all verified against recordings)

- `find_user_id_by_email` / `find_user_id_by_name_zip`: return the bare user id string (exact match).
- `get_user_details`, `get_order_details`, `get_product_details`, `get_item_details` (the variant dict): stored record, key order as in data.
- `list_all_product_types`: `{name: product_id}` sorted by name.
- `calculate`: `str(round(value, 2))`, e.g. `'-5.02'`.
- `transfer_to_human_agents`: returns `"Transfer successful"`.
- `cancel_pending_order`: status -> `cancelled`, `cancel_reason` = reason, appends a `refund` of the payment amount
  to the original method. A gift card refund raises its balance immediately (seen in later `get_user_details`).
- `modify_pending_order_address`: replaces the order address (keys stored as address1, address2, city, country, state, zip); status unchanged.
- `modify_pending_order_items`: replaces each order line in place (item_id, price, options of the new variant;
  name/product_id kept), status -> `pending (item modified)`, appends a `payment` (difference > 0) or `refund`
  (difference < 0) of the **unrounded** float difference (e.g. `12.039999999999964`) with the given method.
- `exchange_delivered_order_items`: status -> `exchange requested`; `exchange_items` and `exchange_new_items`
  are **each sorted independently** (so their pairing is lost); `exchange_price_difference` = new - old, rounded to 2 decimals;
  no payment_history entry.
- `return_delivered_order_items`: status -> `return requested`; `return_items` sorted; `return_payment_method_id` set; no payment entry.
- Product availability and prices never change after modifications or exchanges (product reads after writes match data.json).

## Guesses (each appends its label to `mock.flags` when it runs; see `GUESSES` in mock.py)

Errors (none recorded): `user_not_found`, `order_not_found`, `product_not_found`, `item_not_found`,
`cancel_not_pending`, `cancel_bad_reason`, `modify_not_pending` (status must be exactly `pending`, so a
`pending (item modified)` order cannot be modified or cancelled again, as the policy says), `return_not_delivered`, `exchange_not_delivered`,
`item_not_in_order`, `item_count_mismatch`, `new_item_not_found_or_other_product`, `new_item_unavailable`,
`empty_item_list`, `payment_method_not_found`, `gift_card_insufficient`, `return_payment_not_allowed`,
`payment_same_as_original`, `calculate_invalid`. Error message texts are invented. Only "raises vs not" is meaningful.

Behaviors: `email_case_insensitive`, `name_zip_case_insensitive` (fallback matching), `new_item_same_as_old`
(allowed, flagged), `gift_card_balance_on_item_modify` (balance -= difference), `zero_price_difference` (no
transaction), `duplicate_item_ids` (consume successive lines), `exchange_gift_card_untouched`,
`return_to_other_gift_card` (allowed), `cancel_multi_payment`, `calculate_integer_format` ('4.0'),
and two tools that were never called: `modify_pending_order_payment` (payment on new method + refund to old,
gift card balances adjusted, status stays pending) and `modify_user_address` (replaces the address, returns the user).

## Could not be inferred

- Any error message text or error conditions (no errors in the traces).
- Whether validation order matters (e.g. status check before item check).
- Gift card balance effects of item modification / exchange, and the whole behavior of
  `modify_pending_order_payment` and `modify_user_address`.
- Whether the API rejects identical old/new items, unavailable items, or the same payment method.

## Grading state (`state()`)

The full products/users/orders store (order statuses, items, addresses, payment histories, return/exchange/cancel
fields, gift card balances, user addresses) plus `transferred_to_human` (a boolean: whether a transfer happened;
the free-text summary is excluded). Payment amounts are rounded to 2 decimals so float-summation order
(item order in the agent's call) does not matter. Return/exchange item lists are already sorted by the API.
Read-only lookups and `calculate` leave no trace in the state.
