# Retail support API mock: notes

## State store
`data.json` as given: `products` (product_id -> name, variants{item_id -> options, available, price}),
`users` (profile, default address, payment_methods incl. gift-card `balance`, order list) and
`orders`. Every order also carries seven optional fields that the real API always prints, null until
an action sets them, in this order after `payment_history`:
`cancel_reason, exchange_items, exchange_new_items, exchange_payment_method_id,
exchange_price_difference, return_items, return_payment_method_id`.

## Inferred rules (all reproduced on replay)
- Reads return the stored object verbatim (same key order): `get_user_details`, `get_order_details`
  (with the 7 extra fields), `get_product_details`. `find_user_id_by_email` / `_by_name_zip` return
  the bare user id string. `calculate` returns `str(round(result, 2))`, e.g. "12.04".
- `cancel_pending_order`: status -> `cancelled`, `cancel_reason` = reason, appends
  `{"transaction_type": "refund", "amount": <payment amount>, "payment_method_id": <original>}`.
- `modify_pending_order_address`: replaces the order address (key order address1, address2, city,
  country, state, zip); status stays `pending`.
- `modify_pending_order_items`: each old item (first matching occurrence, duplicates allowed) is
  replaced in place by the new variant (item_id, price, options; name/product_id kept); status ->
  `pending (item modified)`; appends one transaction on the given payment method:
  diff = sum(new - old) accumulated in Python float order, unrounded (e.g. 12.039999999999964);
  `refund` of -diff if diff < 0, `payment` of diff if diff > 0. The method may differ from the
  original payment method.
- `exchange_delivered_order_items`: items unchanged; status -> `exchange requested`;
  `exchange_items` and `exchange_new_items` each **sorted** independently;
  `exchange_payment_method_id`; `exchange_price_difference` = round(diff, 2). No payment entry.
- `return_delivered_order_items`: status -> `return requested`; `return_items` sorted;
  `return_payment_method_id`. No payment entry.
- The traces contain **no errored call**, so every error path is a guess (below).

## state()
Users (addresses, gift-card balances) and orders (all fields) plus `transferred_to_human` (bool).
Normalised so incidental agent choices do not matter: payment amounts and balances rounded to
2 decimals (float summation order depends on argument order), order items sorted by item_id
(duplicate-item pairing order). Read-only lookups, calculate calls and transfer summaries do not
appear. Flags are not part of state.

## Guesses (all in `GUESSES`, flagged when executed)
- Errors (none observed): unknown user / order / product / item; payment method not owned by the
  order's user; cancel/modify on non-`pending` order (incl. `pending (item modified)`, so modify-items
  is once only); return/exchange on non-`delivered` order (so only once); invalid cancel reason;
  items not in order (counting duplicates); length mismatch; new item of another product, the same
  item, or unavailable; gift card balance below a positive difference / new total; return refund to a
  method that is neither original nor a gift card; payment change to the same method; empty item
  list; bad calculate expression. Error messages are invented (check.py compares only the error flag).
- Gift-card balances change immediately on cancel refunds and modify-items differences (policy says
  so; no trace reads a balance after such a change). Exchanges/returns do not touch balances.
- `modify_pending_order_payment` (never called): payment of the total on the new method + refund to
  the old, gift-card balances adjusted, status stays pending.
- `modify_user_address`, `get_item_details`, `list_all_product_types` (dict name -> id, sorted),
  `transfer_to_human_agents` ("Transfer successful") were never called: formats guessed.
- Case-insensitive user lookup fallback; zero price difference recorded as a 0.0 refund;
  calculate on whole numbers prints "4.0"; multi-payment orders refund each payment.

## Not inferable from the traces
Exact error messages and which validation fires first; whether ids are normalised (missing '#');
rounding of gift-card balances; output of the four never-called tools and of payment modification;
whether insufficient gift-card balance is enforced for exchanges; whether a transfer is recorded.

## Replay match rate
`python3 check.py`: **912/912 calls (100%)**, **100/100 conversations** fully match (outputs compared
as exact JSON strings, error flags compared), with no per-conversation special cases.
Only `cancel_gift_card_refund` and `modify_items_gift_card_balance` flags fire during replay
(unobservable balance side effects).
