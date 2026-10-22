"""Stateful mock of the retail support-agent tool API.

Inferred from tools.json, policy.md, data.json and traces.jsonl only.
See NOTES.md for the inferred rules, the guesses and the replay match rate.
"""
import copy
import re

# Optional order fields the real API always shows (null until an action sets them),
# in the order the recordings print them.
ORDER_EXTRA_FIELDS = [
    "cancel_reason",
    "exchange_items",
    "exchange_new_items",
    "exchange_payment_method_id",
    "exchange_price_difference",
    "return_items",
    "return_payment_method_id",
]

GUESSES = {
    # --- errors (the traces contain no errored call at all) ---
    "err_user_not_found": "find_user_id_by_email / find_user_id_by_name_zip / get_user_details / modify_user_address "
                          "raise 'User not found' for an unknown user (descriptions say an error is returned; wording guessed).",
    "err_order_not_found": "Unknown order id raises 'Order not found' (wording guessed; no '#'-prefix normalisation).",
    "err_product_not_found": "Unknown product id raises 'Product not found' (wording guessed).",
    "err_item_not_found": "Unknown item id in get_item_details raises 'Item not found' (wording guessed).",
    "err_payment_method_not_found": "A payment_method_id not among the order owner's payment methods raises "
                                    "'Payment method not found' (guessed from policy: methods come from the user's profile).",
    "err_status_not_pending": "cancel / modify_* on an order whose status is not 'pending' raise "
                              "'Non-pending order cannot be ...' (policy says only pending; wording guessed). "
                              "'pending (item modified)' counts as not pending (policy: cannot modify or cancel anymore).",
    "err_status_not_delivered": "return / exchange on an order whose status is not 'delivered' raise "
                                "'Non-delivered order cannot be ...' (policy; wording guessed). After one return or exchange "
                                "the status changes, so a second one is refused (tool: only once).",
    "err_invalid_cancel_reason": "cancel_pending_order with a reason other than 'no longer needed' / 'ordered by mistake' "
                                 "raises 'Invalid reason' (schema/policy; behaviour guessed).",
    "err_item_not_in_order": "item_ids not present in the order (counting duplicates) raise an error (guessed).",
    "err_items_length_mismatch": "item_ids and new_item_ids of different lengths raise an error (guessed).",
    "err_new_item_wrong_product": "A new item that is not a variant of the same product as the old one raises an error "
                                  "(policy; guessed).",
    "err_new_item_unavailable": "A new item whose 'available' is false raises an error (policy: 'available new item'; guessed).",
    "err_same_item": "Modifying/exchanging an item to the same item id raises an error (policy: 'different product option'; guessed).",
    "err_insufficient_gift_card": "A gift card without enough balance for a positive price difference / new order total "
                                  "raises an error (policy; guessed).",
    "err_return_refund_method": "Return refund must go to the original payment method or an existing gift card; anything "
                                "else raises an error (policy; guessed).",
    "err_same_payment_method": "modify_pending_order_payment to the method already used raises an error (policy; guessed).",
    "err_empty_items": "Empty item_ids list raises an error (guessed).",
    "err_bad_expression": "calculate with characters other than digits, + - * / ( ) . and spaces, or that fails to "
                          "evaluate, raises an error (schema text; guessed).",
    # --- behaviours never exercised in the traces ---
    "modify_payment_effects": "modify_pending_order_payment: appends a 'payment' of the order total on the new method and a "
                              "'refund' of the same amount to the old method; charges/refunds gift card balances "
                              "immediately; status stays 'pending' (policy text; never seen in traces).",
    "modify_user_address": "modify_user_address replaces the user's default address (same key order as data.json) and "
                           "returns the user details (never seen in traces).",
    "get_item_details": "get_item_details returns the variant dict from the product catalogue (never seen in traces).",
    "list_all_product_types": "list_all_product_types returns {product name: product id} sorted by name (never seen).",
    "transfer_to_human_agents": "transfer_to_human_agents returns 'Transfer successful' and records the transfer in state "
                                "(never seen in traces).",
    "zero_price_difference": "modify_pending_order_items with a zero price difference still appends a 'refund' of 0.0 "
                             "(never seen; sign convention of the traces extended).",
    "calculate_integral_format": "calculate returns str(round(value, 2)); for a whole-number result this gives e.g. '4.0' "
                                 "(traces only show non-integral results).",
    "case_insensitive_lookup": "find_user_id_by_* matched the email / name only case-insensitively (exact matches are "
                               "what the traces show; case folding is guessed).",
    "modify_items_gift_card_balance": "modify_pending_order_items paid/refunded with a gift card changes its balance "
                                      "immediately (policy; not observable in traces).",
    "cancel_gift_card_refund": "cancel_pending_order of a gift-card-paid order adds the refund to the gift card balance "
                               "immediately (tool description; not observable in the traces).",
    "multi_payment_order": "cancel of an order with several payment entries refunds each payment to its own method "
                           "(guessed; the traces only show single-payment orders).",
}


def _r2(x):
    return round(x + 0.0, 2)


class Mock:
    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)
        self.products = self.data["products"]
        self.users = self.data["users"]
        self.orders = self.data["orders"]
        for o in self.orders.values():
            for f in ORDER_EXTRA_FIELDS:
                o.setdefault(f, None)
        self.transfers = []
        self.flags = []

    # ------------------------------------------------------------ helpers
    def _flag(self, label):
        assert label in GUESSES, label
        self.flags.append(label)

    def _err(self, label, msg):
        self._flag(label)
        raise Exception(msg)

    def _order(self, order_id):
        o = self.orders.get(order_id)
        if o is None:
            self._err("err_order_not_found", "Error: order not found")
        return o

    def _user(self, user_id):
        u = self.users.get(user_id)
        if u is None:
            self._err("err_user_not_found", "Error: user not found")
        return u

    def _order_view(self, o):
        return copy.deepcopy(o)

    def _payment_method(self, o, payment_method_id):
        u = self.users.get(o["user_id"])
        if u is None or payment_method_id not in u["payment_methods"]:
            self._err("err_payment_method_not_found", "Error: payment method not found")
        return u["payment_methods"][payment_method_id]

    def _variant(self, item_id):
        for p in self.products.values():
            if item_id in p["variants"]:
                return p, p["variants"][item_id]
        return None, None

    def _check_items_in_order(self, o, item_ids):
        if not item_ids:
            self._err("err_empty_items", "Error: no items given")
        all_ids = [it["item_id"] for it in o["items"]]
        for iid in set(item_ids):
            if item_ids.count(iid) > all_ids.count(iid):
                self._err("err_item_not_in_order", "Error: %s not found" % iid)

    def _check_new_items(self, o, item_ids, new_item_ids):
        if len(item_ids) != len(new_item_ids):
            self._err("err_items_length_mismatch", "Error: the number of items to be exchanged should match")
        diff = 0.0
        for old_id, new_id in zip(item_ids, new_item_ids):
            item = next(it for it in o["items"] if it["item_id"] == old_id)
            product = self.products.get(item["product_id"])
            if product is None or new_id not in product["variants"]:
                self._err("err_new_item_wrong_product", "Error: new item %s not found or not of the same product" % new_id)
            variant = product["variants"][new_id]
            if new_id == old_id:
                self._err("err_same_item", "Error: new item %s is the same as the old item" % new_id)
            if not variant["available"]:
                self._err("err_new_item_unavailable", "Error: new item %s not available" % new_id)
            diff += variant["price"] - item["price"]
        return diff

    # ------------------------------------------------------------ read tools
    def calculate(self, expression):
        if not re.fullmatch(r"[0-9+\-*/(). ]+", expression or ""):
            self._err("err_bad_expression", "Error: invalid characters in expression")
        try:
            value = eval(expression, {"__builtins__": {}}, {})
        except Exception as e:  # noqa
            self._err("err_bad_expression", "Error: %s" % e)
        value = round(float(value), 2)
        if value == int(value):
            self._flag("calculate_integral_format")
        return str(value)

    def find_user_id_by_email(self, email):
        for uid, u in self.users.items():
            if u["email"] == email:
                return uid
        for uid, u in self.users.items():
            if u["email"].lower() == (email or "").lower():
                self._flag("case_insensitive_lookup")
                return uid
        self._err("err_user_not_found", "Error: user not found")

    def find_user_id_by_name_zip(self, first_name, last_name, zip):
        for uid, u in self.users.items():
            if (u["name"]["first_name"] == first_name and u["name"]["last_name"] == last_name
                    and u["address"]["zip"] == zip):
                return uid
        for uid, u in self.users.items():
            if (u["name"]["first_name"].lower() == (first_name or "").lower()
                    and u["name"]["last_name"].lower() == (last_name or "").lower()
                    and u["address"]["zip"] == zip):
                self._flag("case_insensitive_lookup")
                return uid
        self._err("err_user_not_found", "Error: user not found")

    def get_user_details(self, user_id):
        return copy.deepcopy(self._user(user_id))

    def get_order_details(self, order_id):
        return self._order_view(self._order(order_id))

    def get_product_details(self, product_id):
        p = self.products.get(product_id)
        if p is None:
            self._err("err_product_not_found", "Error: product not found")
        return copy.deepcopy(p)

    def get_item_details(self, item_id):
        self._flag("get_item_details")
        _, v = self._variant(item_id)
        if v is None:
            self._err("err_item_not_found", "Error: item not found")
        return copy.deepcopy(v)

    def list_all_product_types(self):
        self._flag("list_all_product_types")
        return dict(sorted((p["name"], pid) for pid, p in self.products.items()))

    def transfer_to_human_agents(self, summary):
        self._flag("transfer_to_human_agents")
        self.transfers.append(summary)
        return "Transfer successful"

    # ------------------------------------------------------------ write tools
    def cancel_pending_order(self, order_id, reason):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("err_status_not_pending", "Error: non-pending order cannot be cancelled")
        if reason not in ("no longer needed", "ordered by mistake"):
            self._err("err_invalid_cancel_reason", "Error: invalid reason")
        payments = [p for p in o["payment_history"] if p["transaction_type"] == "payment"]
        if len(o["payment_history"]) != 1:
            self._flag("multi_payment_order")
        refunds = []
        for p in payments:
            refunds.append({"transaction_type": "refund", "amount": p["amount"],
                            "payment_method_id": p["payment_method_id"]})
            pm = self.users.get(o["user_id"], {}).get("payment_methods", {}).get(p["payment_method_id"])
            if pm is not None and pm["source"] == "gift_card":
                self._flag("cancel_gift_card_refund")
                pm["balance"] = _r2(pm["balance"] + p["amount"])
        o["payment_history"].extend(refunds)
        o["status"] = "cancelled"
        o["cancel_reason"] = reason
        return self._order_view(o)

    def modify_pending_order_address(self, order_id, address1, address2, city, state, country, zip):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("err_status_not_pending", "Error: non-pending order cannot be modified")
        o["address"] = {"address1": address1, "address2": address2, "city": city,
                        "country": country, "state": state, "zip": zip}
        return self._order_view(o)

    def modify_pending_order_items(self, order_id, item_ids, new_item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("err_status_not_pending", "Error: non-pending order cannot be modified")
        self._check_items_in_order(o, item_ids)
        diff = self._check_new_items(o, item_ids, new_item_ids)
        pm = self._payment_method(o, payment_method_id)
        if pm["source"] == "gift_card" and pm["balance"] < diff:
            self._err("err_insufficient_gift_card", "Error: insufficient gift card balance to pay for the new item")
        if diff == 0:
            self._flag("zero_price_difference")
        o["payment_history"].append({
            "transaction_type": "payment" if diff > 0 else "refund",
            "amount": abs(diff),
            "payment_method_id": payment_method_id,
        })
        if pm["source"] == "gift_card":
            self._flag("modify_items_gift_card_balance")
            pm["balance"] = _r2(pm["balance"] - diff)
        for old_id, new_id in zip(item_ids, new_item_ids):
            for it in o["items"]:
                if it["item_id"] == old_id:
                    v = self.products[it["product_id"]]["variants"][new_id]
                    it["item_id"] = new_id
                    it["price"] = v["price"]
                    it["options"] = copy.deepcopy(v["options"])
                    break
        o["status"] = "pending (item modified)"
        return self._order_view(o)

    def modify_pending_order_payment(self, order_id, payment_method_id):
        self._flag("modify_payment_effects")
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("err_status_not_pending", "Error: non-pending order cannot be modified")
        pm = self._payment_method(o, payment_method_id)
        payments = [p for p in o["payment_history"] if p["transaction_type"] == "payment"]
        if len(o["payment_history"]) != 1:
            self._flag("multi_payment_order")
        old = payments[0]
        if old["payment_method_id"] == payment_method_id:
            self._err("err_same_payment_method", "Error: the new payment method should be different from the current one")
        amount = old["amount"]
        if pm["source"] == "gift_card" and pm["balance"] < amount:
            self._err("err_insufficient_gift_card", "Error: insufficient gift card balance to pay for the order")
        o["payment_history"].extend([
            {"transaction_type": "payment", "amount": amount, "payment_method_id": payment_method_id},
            {"transaction_type": "refund", "amount": amount, "payment_method_id": old["payment_method_id"]},
        ])
        if pm["source"] == "gift_card":
            pm["balance"] = _r2(pm["balance"] - amount)
        old_pm = self.users[o["user_id"]]["payment_methods"].get(old["payment_method_id"])
        if old_pm is not None and old_pm["source"] == "gift_card":
            old_pm["balance"] = _r2(old_pm["balance"] + amount)
        return self._order_view(o)

    def modify_user_address(self, user_id, address1, address2, city, state, country, zip):
        self._flag("modify_user_address")
        u = self._user(user_id)
        u["address"] = {"address1": address1, "address2": address2, "city": city,
                        "country": country, "state": state, "zip": zip}
        return copy.deepcopy(u)

    def return_delivered_order_items(self, order_id, item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "delivered":
            self._err("err_status_not_delivered", "Error: non-delivered order cannot be returned")
        pm = self._payment_method(o, payment_method_id)
        original = [p["payment_method_id"] for p in o["payment_history"] if p["transaction_type"] == "payment"]
        if payment_method_id not in original and pm["source"] != "gift_card":
            self._err("err_return_refund_method", "Error: payment method should be the original payment method or a gift card")
        self._check_items_in_order(o, item_ids)
        o["status"] = "return requested"
        o["return_items"] = sorted(item_ids)
        o["return_payment_method_id"] = payment_method_id
        return self._order_view(o)

    def exchange_delivered_order_items(self, order_id, item_ids, new_item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "delivered":
            self._err("err_status_not_delivered", "Error: non-delivered order cannot be exchanged")
        self._check_items_in_order(o, item_ids)
        diff = self._check_new_items(o, item_ids, new_item_ids)
        pm = self._payment_method(o, payment_method_id)
        if pm["source"] == "gift_card" and pm["balance"] < diff:
            self._err("err_insufficient_gift_card", "Error: insufficient gift card balance to pay for the price difference")
        o["status"] = "exchange requested"
        o["exchange_items"] = sorted(item_ids)
        o["exchange_new_items"] = sorted(new_item_ids)
        o["exchange_payment_method_id"] = payment_method_id
        o["exchange_price_difference"] = _r2(diff)
        return self._order_view(o)

    # ------------------------------------------------------------ grading
    def state(self) -> dict:
        """Everything a correct handling changes, normalised so that argument order and float
        summation order (which the real API exposes, e.g. 12.039999999999964) do not matter.
        Read-only lookups leave no trace here."""
        users = copy.deepcopy(self.users)
        for u in users.values():
            for pm in u["payment_methods"].values():
                if "balance" in pm:
                    pm["balance"] = _r2(pm["balance"])
        orders = copy.deepcopy(self.orders)
        for o in orders.values():
            for p in o["payment_history"]:
                p["amount"] = _r2(p["amount"])
            o["items"] = sorted(o["items"], key=lambda it: it["item_id"])
        return {
            "users": users,
            "orders": orders,
            "transferred_to_human": len(self.transfers) > 0,
        }
