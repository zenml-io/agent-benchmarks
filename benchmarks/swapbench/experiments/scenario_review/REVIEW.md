# Scenario audit: 50 packets (30 fintech, 20 retail)

## Protocol as applied

For each packet, in order:

1. **Derive.** I read `customer_instructions` and the data, then wrote down the actions the policy requires. The retail packets were reviewed with order and variant tables. Expected actions were printed in the same view, but I wrote each derivation before comparing.
2. **Facts.** I checked every fact the customer states against the data:
   - **Fintech:** name, date of birth, phone digits, card last4, merchant, amount, date, posted/pending status, the 60-day window (on or after 2026-08-02), and earlier `fee_refund` rows within 365 days on any account.
   - **Retail:** email or name+zip, order id and status, item options, payment-method brand/last4 and gift-card balance.
   - **Script checks:** a script confirmed that every amount in each fintech instruction exists in the data. The only exceptions are the "agreed to pay $X" prices for `incorrect_amount` disputes, which are customer-side facts and are meant to be absent. The script also confirmed that no transaction is already disputed and listed every same-merchant, same-amount pair, to test the duplicate rule.
3. **Compare.** A script checked each gold action for:
   - **Order and item checks:** the order status fits the tool; the item is in the order; the new item is the same product, available and has changed options. It also printed which option changed, to compare with the request.
   - **Payment checks:** gift-card balances, tracked across actions; return refunds go to the original method or a gift card.
   - **Policy rules:** cancel reasons are allowed; at most one item-change call per order; no action on an order after its items were modified.
   - **Result:** no gold action broke a policy rule. I then compared the gold with my derivation by hand.
4. **Ambiguity.** I looked for other policy-compliant paths that end in a different state: two matching transactions or items, items with no order id, alternative refund targets, and alternative offers the agent might make.
5. **Drivability.** I checked whether the customer can supply every needed fact and can answer the agent's natural follow-up questions consistently.
6. **Verdict:** PASS, MINOR or FAIL, as defined in the task.

## Counts

| Domain  | PASS | MINOR | FAIL | Total |
|---------|-----:|------:|-----:|------:|
| fintech | 26   | 4     | 0    | 30    |
| retail  | 13   | 3     | 4    | 20    |
| **all** | 39   | 7     | 4    | 50    |

Every gold action list matched my derivation: no wrong ids, amounts, reasons or order. The FAILs are ambiguity and drivability problems, not wrong gold.

## FAIL

**40 (g86), 45 (g211), 48 (g67), 50 (g115): "cancel" request on a delivered order.**
The customer asks to cancel an order whose status is `delivered`. The gold takes no action, which is right for a minimal agent: only pending orders can be cancelled. But the policy explicitly lets the agent return delivered orders, so a natural, compliant reply is "I can't cancel it, but I can start a return." The customer script only covers a flat no ("ask once whether there is any way to cancel it; if the answer is still no, accept it"). It is silent on a return offer, and the stated motive ("no longer need it") makes acceptance likely. If the customer accepts, `return_delivered_order_items` runs and the end state no longer matches the gold. The more proactive and helpful the agent, the more likely it fails. That bias runs against good agents.

The return would also be underspecified:
- **40:** the instruction names only the Pet Bed, but the order has 5 items.
- **45:** the order holds the same Tea Kettle twice (item 7292993796 x2), but the customer speaks of one.
- **48:** only the Headphones are named, out of 5 items.
- **50:** a single-item order, so a return is easy to accept.

**Fix:** use a `processed` order, as in 34, 47 and 49, which are clean. Or add "If the agent offers a return instead, decline it."

## MINOR

**09 (f248), 22 (f189): "you cancelled that order" for a GymPro Membership charge.**
Template wording that doesn't fit a membership. The charge is pending, so no action follows either way. End state unaffected.

**24 (f297), 29 (f239): "the order never arrived" for a Harbor Hotel charge.**
Template wording that doesn't fit a hotel stay. The charge is outside the 60-day window, so no action follows either way. End state unaffected.

**43 (g199), 44 (g82), 47 (g68): incomplete item list on cancellations.**
The cancel request says "it contains X, Y" but names only some of the order's items:
- **43:** #W1170711, 2 of 4 items.
- **44:** #W8642391, 2 of 4, and #W9474165, 2 of 4.
- **47:** #W3043531, 2 of 5, leaving out a $2,009 wristwatch.

A careful agent reads back the full order before confirming. A strict simulated customer may then decline because the contents differ from what they were told. 44's persona is explicitly "cautious, asks to repeat the details". The order id is given, so most simulators will confirm, and the gold is correct. This is a drivability risk, not a wrong gold.

## Systematic patterns

1. **Retail "cannot cancel" generator (FAIL pattern).** It draws any non-pending order. When it draws a `delivered` order (4 of 7 instances), a return alternative opens that the customer script doesn't cover. The "cannot return yet" generator always used `processed` orders (38, 41, 42, 46), which have no alternative path, so it is clean.
2. **Retail cancel template lists a subset of the order's items** as "it contains ...". Listing all items, or saying "including", would remove the risk.
3. **Fintech purpose templates ignore merchant type.** "Order never arrived" and "cancelled that order" are applied to hotels and gym memberships. This is harmless in this sample, because every affected case is a no-action case. It would matter if it hit an actionable `item_not_received` dispute, where the reason would sound implausible to the agent.
4. **Free-text `summary` in gold `escalate_to_human`.** Affected packets: 02, 06, 07, 14, 18, 25, 28 and 30, with summaries like "verification failed twice" and "asked for a human". If the end-state grader compares the stored escalation including `summary`, no real agent will reproduce the exact text, and every escalation scenario fails. Confirm that the grader ignores `summary`, or compares only `reason`.
5. **Clean areas:**
   - **Fintech:** the 365-day fee-refund look-back across accounts (10 puts the prior refund on a different account, which is a good test), the $40 cap, the $500 duplicate limit, the 2-day duplicate window, pending and 60-day rules, the unauthorized freeze-then-dispute order, and the two-wrong-DOB escalations.
   - **Retail:** unavailable-variant "keep current item" cases, multi-item exchanges batched into one call, refusals of a non-original card refund (37, 46), and gift-card balance coverage.
