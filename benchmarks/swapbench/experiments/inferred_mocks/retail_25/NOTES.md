# Retail support API mock: inference notes

## Replay match rate
`python3 check.py`: **212/212 calls** and **25/25 conversations** match the recorded outputs and
error flags, with no per-conversation special cases. The traces contain **no errored call**, so
every error path is a guess. Only one guessed path runs during replay: `gift_card_refund_balance`
(9 times). It is never checked, because no trace reads a user after a gift-card refund.

## State store
`data.json` holds `products` (50), `users` (500) and `orders` (1000). The mock deep-copies it.
Every order also gets 7 optional fields, null until set:
`cancel_reason, exchange_items, exchange_new_items, exchange_payment_method_id,
exchange_price_difference, return_items, return_payment_method_id`. The API always returns them
in that order, even for orders that were never changed.

`state()` returns users (address and gift-card balances), orders (status, items, address,
payment_history and the optional fields), products (never changed), and
`transferred_to_human` (bool). The bool is a judgment call: under the policy, transferring or not
transferring is part of handling the customer correctly. The summary text is left out because
its wording varies. Read-only lookups are not recorded.

## Inferred rules (observed)
- String-valued tools (`find_user_id_by_*`) return the bare user id. Everything else returns the
  JSON record.
- `get_user_details` / `get_product_details` return the stored record unchanged.
  `get_order_details` returns the order with the 7 extra fields.
- `cancel_pending_order`: status becomes `cancelled`, `cancel_reason` is set to the reason, and a
  `refund` entry equal to the payment amount is appended to `payment_history` with the same
  method. This holds for gift cards and other methods alike.
- `modify_pending_order_address`: replaces the order address. The key order is
  address1, address2, city, country, state, zip, whatever order the arguments came in.
  Status stays `pending`.
- `modify_pending_order_items`: each listed item is replaced in place (item_id, price, options
  from the new variant; name and product_id kept). Status becomes `pending (item modified)`.
  A price decrease appends a `refund` of `sum(old) - sum(new)`. That amount is **not rounded**
  (e.g. `12.039999999999964`) and goes to the given payment method.
- `exchange_delivered_order_items`: status becomes `exchange requested`. `exchange_items` and
  `exchange_new_items` are each **sorted independently**. `exchange_price_difference =
  round(sum(new) - sum(old), 2)` and can be negative. No payment_history entry is added, and
  the items are not changed.
- `return_delivered_order_items`: status becomes `return requested`, and `return_items` and
  `return_payment_method_id` are set. payment_history and items are unchanged.

## Guesses (all in `GUESSES`, flagged at runtime)
- **Errors.** Error messages are guesses, and so is each condition:
  - unknown user, order, product or item;
  - wrong status: cancel and all modifies need exactly `pending`, so nothing is allowed after
    `pending (item modified)`; return and exchange need `delivered`, so each happens only once;
  - an invalid cancel reason;
  - a payment method that is not in the owner's profile;
  - items not in the order (duplicates counted);
  - item_ids and new_item_ids of different lengths;
  - a new item from a different product, an unavailable one, or the same item id;
  - a gift card with too little balance to cover a positive difference (or the full total when
    changing payment);
  - a return refund method that is neither the original method nor a gift card;
  - a payment change to the same method;
  - an empty item list;
  - a bad calculate expression.
- **Gift-card balances.** A refund to a gift card is credited to its balance immediately (as the
  policy says). Charges are debited. Balances are rounded to 2 decimals.
- **Paths never observed.**
  - a positive price difference when modifying items: a `payment` entry is appended;
  - `modify_pending_order_payment`: a payment with the new method and a refund to the old one;
  - `modify_user_address`: returns the user record;
  - `get_item_details`: the variant plus product_id and name;
  - `list_all_product_types`: `{name: product_id}` sorted by name;
  - `calculate`: a float rounded to 2 decimals;
  - `transfer_to_human_agents`: returns "Transfer successful";
  - cancelling an order with more than one payment entry: refunds the net amount per method.
- **Matching and ordering.** Case-insensitive fallbacks for email and name lookups. `return_items`
  is stored sorted, by analogy with exchanges.

## Could not be inferred
- Any real error text or error condition, including whether the API itself enforces policy
  rules (e.g. modifying after `pending (item modified)`) or leaves them to the agent.
- Whether gift-card balances change on refund or charge, and when.
- The output shapes of `get_item_details`, `list_all_product_types`, `calculate`,
  `transfer_to_human_agents`, `modify_user_address` and `modify_pending_order_payment`.
- How a positive item-modification difference is recorded, and how a cancel refunds an order
  whose payment was changed.
