"""Stateful mock of the retail support-agent tool API.

Inferred from tools.json, policy.md, data.json and traces.jsonl only.
Every behavior not directly observed in the traces appends a label to
self.flags when it runs; the labels are explained in GUESSES.
"""
import copy
import json
import re

# Fields the real API attaches to every order it returns (all null until set).
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
    # lookups
    "user_email_not_found": "find_user_id_by_email with an unknown email errors ('User not found'). Traces only show hits; the tool description says it returns an error.",
    "user_name_zip_not_found": "find_user_id_by_name_zip with no exact (case-sensitive) first/last/zip match errors ('User not found'). Traces only show exact hits.",
    "order_not_found": "Unknown order id errors ('Order not found'). Never observed.",
    "user_not_found": "Unknown user id errors ('User not found'). Never observed.",
    "product_not_found": "Unknown product id errors ('Product not found'). Never observed.",
    "get_item_details": "get_item_details is never called in traces; returns the variant dict as stored in data.json products[*].variants (item_id, options, available, price), no product info added.",
    "item_not_found": "Unknown item id errors ('Item not found'). Never observed.",
    "list_all_product_types": "Never called in traces; returns a dict {product name: product_id} sorted by name.",
    "calculate_error": "calculate with characters outside digits/+-*/(). or a failing evaluation (e.g. division by zero) errors. Never observed.",
    "transfer_to_human_agents": "Never called in traces; returns 'Transfer successful' and records that a transfer happened (no summary text) in state.",
    # status checks
    "cancel_not_pending": "cancel_pending_order on a non-'pending' order errors ('Non-pending order cannot be cancelled'). Never observed; from policy and tool description.",
    "cancel_bad_reason": "cancel_pending_order with a reason other than 'no longer needed' / 'ordered by mistake' errors. Never observed; from policy.",
    "modify_not_pending": "modify_pending_order_* on an order whose status is not exactly 'pending' (including 'pending (item modified)') errors. Never observed; from policy ('can only be called once').",
    "return_not_delivered": "return_delivered_order_items on a non-'delivered' order errors. Never observed; from policy.",
    "exchange_not_delivered": "exchange_delivered_order_items on a non-'delivered' order errors. Never observed; from policy.",
    # argument validation
    "items_not_in_order": "Item ids (counting duplicates) that are not in the order error. Never observed.",
    "item_lists_length_mismatch": "item_ids and new_item_ids of different lengths error. Never observed.",
    "new_item_not_found": "A new item id that is not a variant of the old item's product errors ('New item ... not found or available'). Never observed; from tool description (same product).",
    "new_item_unavailable": "A new item whose variant has available=false errors. Never observed; from policy.",
    "new_item_same_as_old": "Exchanging/modifying an item to the very same item id errors (policy: 'different product option'). Never observed.",
    "payment_method_not_found": "A payment method id that is not one of the order owner's payment methods errors. Never observed.",
    "gift_card_insufficient": "A gift card whose balance is below the amount to charge (price difference > 0, or new order total for a payment change) errors. Never observed; from policy.",
    "return_payment_not_allowed": "Return refund to a method that is neither the order's original payment method nor a gift card of the user errors. Never observed; from policy.",
    "modify_payment_same_method": "modify_pending_order_payment to the order's current payment method errors. Never observed; from policy ('different from the original').",
    "modify_payment_multiple_payments": "modify_pending_order_payment on an order whose payment history is not a single payment errors. Never observed.",
    # state effects not visible in traces
    "cancel_gift_card_refund_balance": "Cancelling an order paid by gift card adds the refund to that gift card's balance immediately (policy/tool description). Balances are never re-read in traces.",
    "modify_items_gift_card_balance": "modify_pending_order_items with a gift card subtracts a positive price difference from / adds a refund to its balance. Not observable in traces.",
    "cancel_multiple_payment_methods": "Cancelling an order whose history involves several payment methods (only possible after modify_pending_order_payment) refunds the net amount held on each method. Never observed.",
    "modify_items_zero_difference": "modify_pending_order_items with zero price difference appends no transaction. Never observed.",
    "modify_payment": "modify_pending_order_payment is never called in traces: appends a 'payment' of the order total on the new method and a 'refund' of the same amount to the old method; gift card balances adjust; status stays 'pending'.",
    "modify_user_address": "modify_user_address is never called in traces: replaces the user's address (address1, address2, city, country, state, zip key order) and returns the user dict.",
}


def _r2(x):
    return round(x + 0.0, 2)


class Mock:
    def __init__(self, data: dict):
        data = copy.deepcopy(data)
        self.products = data["products"]
        self.users = data["users"]
        self.orders = data["orders"]
        for o in self.orders.values():
            for k in ORDER_EXTRA_FIELDS:
                o.setdefault(k, None)
        self.transfers = 0
        self.flags = []
        # item_id -> (product_id, variant)
        self._items = {}
        for pid, p in self.products.items():
            for iid, v in p["variants"].items():
                self._items[iid] = (pid, v)

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
            self._err("order_not_found", "Order not found")
        return o

    def _user(self, user_id):
        u = self.users.get(user_id)
        if u is None:
            self._err("user_not_found", "User not found")
        return u

    def _user_payment(self, order, payment_method_id):
        u = self.users.get(order["user_id"])
        pm = (u or {}).get("payment_methods", {}).get(payment_method_id)
        if pm is None:
            self._err("payment_method_not_found", "Payment method not found")
        return pm

    def _check_items(self, order, item_ids):
        have = [it["item_id"] for it in order["items"]]
        for iid in item_ids:
            if item_ids.count(iid) > have.count(iid):
                self._err("items_not_in_order", f"{iid} not found")

    def _price_diff(self, order, item_ids, new_item_ids):
        """Validate new items and return (diff, new_variants)."""
        if len(item_ids) != len(new_item_ids):
            self._err("item_lists_length_mismatch",
                      "The number of items to be exchanged should match")
        self._check_items(order, item_ids)
        diff = 0.0
        news = []
        for old_id, new_id in zip(item_ids, new_item_ids):
            old = next(it for it in order["items"] if it["item_id"] == old_id)
            prod = self.products.get(old["product_id"], {})
            var = prod.get("variants", {}).get(new_id)
            if var is None:
                self._err("new_item_not_found", f"New item {new_id} not found or available")
            if not var.get("available"):
                self._err("new_item_unavailable", f"New item {new_id} not found or available")
            if new_id == old_id:
                self._err("new_item_same_as_old", f"New item {new_id} is the same as the old item")
            diff += var["price"] - old["price"]
            news.append(var)
        return diff, news

    @staticmethod
    def _out(order):
        out = {k: v for k, v in order.items() if k not in ORDER_EXTRA_FIELDS}
        for k in ORDER_EXTRA_FIELDS:
            out[k] = order.get(k)
        return copy.deepcopy(out)

    # ------------------------------------------------------------ tools
    def calculate(self, expression):
        if not re.fullmatch(r"[0-9+\-*/(). ]*", expression or ""):
            self._err("calculate_error", "Invalid characters in expression")
        try:
            val = eval(expression, {"__builtins__": {}}, {})
        except Exception as e:
            self._err("calculate_error", f"Error: {e}")
        return str(round(float(val), 2))

    def find_user_id_by_email(self, email):
        for u in self.users.values():
            if u["email"] == email:
                return u["user_id"]
        self._err("user_email_not_found", "User not found")

    def find_user_id_by_name_zip(self, first_name, last_name, zip):
        for u in self.users.values():
            if (u["name"]["first_name"] == first_name and u["name"]["last_name"] == last_name
                    and u["address"]["zip"] == zip):
                return u["user_id"]
        self._err("user_name_zip_not_found", "User not found")

    def get_user_details(self, user_id):
        return copy.deepcopy(self._user(user_id))

    def get_order_details(self, order_id):
        return self._out(self._order(order_id))

    def get_product_details(self, product_id):
        p = self.products.get(product_id)
        if p is None:
            self._err("product_not_found", "Product not found")
        return copy.deepcopy(p)

    def get_item_details(self, item_id):
        self._flag("get_item_details")
        hit = self._items.get(item_id)
        if hit is None:
            self._err("item_not_found", "Item not found")
        return copy.deepcopy(hit[1])

    def list_all_product_types(self):
        self._flag("list_all_product_types")
        return dict(sorted((p["name"], pid) for pid, p in self.products.items()))

    def transfer_to_human_agents(self, summary):
        self._flag("transfer_to_human_agents")
        self.transfers += 1
        return "Transfer successful"

    def cancel_pending_order(self, order_id, reason):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("cancel_not_pending", "Non-pending order cannot be cancelled")
        if reason not in ("no longer needed", "ordered by mistake"):
            self._err("cancel_bad_reason", "Invalid reason")
        # Refund the net amount still held on each payment method (for an untouched
        # pending order: the single payment, as observed in the traces).
        net = {}
        for p in o["payment_history"]:
            sign = 1 if p["transaction_type"] == "payment" else -1
            net[p["payment_method_id"]] = net.get(p["payment_method_id"], 0.0) + sign * p["amount"]
        if len(net) > 1:
            self._flag("cancel_multiple_payment_methods")
        refunds = []
        for pmid, amount in net.items():
            if amount <= 0.005:
                continue
            if len(net) > 1:
                amount = _r2(amount)
            refunds.append({"transaction_type": "refund", "amount": amount,
                            "payment_method_id": pmid})
            pm = self.users.get(o["user_id"], {}).get("payment_methods", {}).get(pmid)
            if pm is not None and pm.get("source") == "gift_card":
                self._flag("cancel_gift_card_refund_balance")
                pm["balance"] = _r2(pm.get("balance", 0) + amount)
        o["payment_history"].extend(refunds)
        o["status"] = "cancelled"
        o["cancel_reason"] = reason
        return self._out(o)

    def modify_pending_order_address(self, order_id, address1, address2, city, state, country, zip):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("modify_not_pending", "Non-pending order cannot be modified")
        o["address"] = {"address1": address1, "address2": address2, "city": city,
                        "country": country, "state": state, "zip": zip}
        return self._out(o)

    def modify_pending_order_payment(self, order_id, payment_method_id):
        self._flag("modify_payment")
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("modify_not_pending", "Non-pending order cannot be modified")
        pm = self._user_payment(o, payment_method_id)
        ph = o["payment_history"]
        if len(ph) != 1 or ph[0]["transaction_type"] != "payment":
            self._err("modify_payment_multiple_payments",
                      "There should be exactly one payment for a pending order")
        old_id = ph[0]["payment_method_id"]
        if old_id == payment_method_id:
            self._err("modify_payment_same_method",
                      "The new payment method should be different from the current one")
        amount = ph[0]["amount"]
        if pm.get("source") == "gift_card" and pm.get("balance", 0) < amount:
            self._err("gift_card_insufficient", "Insufficient gift card balance to pay for the order")
        ph.append({"transaction_type": "payment", "amount": amount, "payment_method_id": payment_method_id})
        ph.append({"transaction_type": "refund", "amount": amount, "payment_method_id": old_id})
        if pm.get("source") == "gift_card":
            pm["balance"] = _r2(pm["balance"] - amount)
        old_pm = self.users.get(o["user_id"], {}).get("payment_methods", {}).get(old_id)
        if old_pm is not None and old_pm.get("source") == "gift_card":
            old_pm["balance"] = _r2(old_pm.get("balance", 0) + amount)
        return self._out(o)

    def modify_pending_order_items(self, order_id, item_ids, new_item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("modify_not_pending", "Non-pending order cannot be modified")
        item_ids, new_item_ids = list(item_ids), list(new_item_ids)
        diff, news = self._price_diff(o, item_ids, new_item_ids)
        pm = self._user_payment(o, payment_method_id)
        if pm.get("source") == "gift_card" and pm.get("balance", 0) < diff:
            self._err("gift_card_insufficient", "Insufficient gift card balance to pay for the price difference")
        if diff > 0:
            o["payment_history"].append({"transaction_type": "payment", "amount": diff,
                                         "payment_method_id": payment_method_id})
        elif diff < 0:
            o["payment_history"].append({"transaction_type": "refund", "amount": -diff,
                                         "payment_method_id": payment_method_id})
        else:
            self._flag("modify_items_zero_difference")
        if pm.get("source") == "gift_card" and diff != 0:
            self._flag("modify_items_gift_card_balance")
            pm["balance"] = _r2(pm["balance"] - diff)
        replaced = set()
        for old_id, var in zip(item_ids, news):
            for idx, it in enumerate(o["items"]):
                if it["item_id"] == old_id and idx not in replaced:
                    replaced.add(idx)
                    it["item_id"] = var["item_id"]
                    it["price"] = var["price"]
                    it["options"] = copy.deepcopy(var["options"])
                    break
        o["status"] = "pending (item modified)"
        return self._out(o)

    def return_delivered_order_items(self, order_id, item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "delivered":
            self._err("return_not_delivered", "Non-delivered order cannot be returned")
        pm = self._user_payment(o, payment_method_id)
        original = [p["payment_method_id"] for p in o["payment_history"]
                    if p["transaction_type"] == "payment"]
        if payment_method_id not in original[:1] and pm.get("source") != "gift_card":
            self._err("return_payment_not_allowed",
                      "Payment method should be either the original payment method or a gift card")
        item_ids = list(item_ids)
        self._check_items(o, item_ids)
        o["status"] = "return requested"
        o["return_items"] = sorted(item_ids)
        o["return_payment_method_id"] = payment_method_id
        return self._out(o)

    def exchange_delivered_order_items(self, order_id, item_ids, new_item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "delivered":
            self._err("exchange_not_delivered", "Non-delivered order cannot be exchanged")
        item_ids, new_item_ids = list(item_ids), list(new_item_ids)
        diff, _ = self._price_diff(o, item_ids, new_item_ids)
        pm = self._user_payment(o, payment_method_id)
        if pm.get("source") == "gift_card" and pm.get("balance", 0) < diff:
            self._err("gift_card_insufficient", "Insufficient gift card balance to pay for the price difference")
        o["status"] = "exchange requested"
        o["exchange_items"] = sorted(item_ids)
        o["exchange_new_items"] = sorted(new_item_ids)
        o["exchange_payment_method_id"] = payment_method_id
        o["exchange_price_difference"] = _r2(diff)
        return self._out(o)

    def modify_user_address(self, user_id, address1, address2, city, state, country, zip):
        self._flag("modify_user_address")
        u = self._user(user_id)
        u["address"] = {"address1": address1, "address2": address2, "city": city,
                        "country": country, "state": state, "zip": zip}
        return copy.deepcopy(u)

    # ------------------------------------------------------------ grading
    def state(self) -> dict:
        orders = {}
        for oid, o in self.orders.items():
            s = copy.deepcopy(o)
            for p in s["payment_history"]:
                p["amount"] = _r2(p["amount"])
            if s.get("exchange_price_difference") is not None:
                s["exchange_price_difference"] = _r2(s["exchange_price_difference"])
            orders[oid] = s
        users = {}
        for uid, u in self.users.items():
            s = copy.deepcopy(u)
            for pm in s["payment_methods"].values():
                if "balance" in pm:
                    pm["balance"] = _r2(pm["balance"])
            users[uid] = s
        return {"users": users, "orders": orders, "products": copy.deepcopy(self.products),
                "transferred_to_human": self.transfers > 0}
