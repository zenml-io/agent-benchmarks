"""Stateful mock of the retail support-agent tool API, inferred from production traces.

Standard library only. See NOTES.md for the inferred rules and the list of guesses.
"""
import ast
import copy
import operator

# Fields every order carries in API output (null until the matching action happens).
ORDER_EXTRA_FIELDS = [
    "cancel_reason",
    "exchange_items",
    "exchange_new_items",
    "exchange_payment_method_id",
    "exchange_price_difference",
    "return_items",
    "return_payment_method_id",
]

CANCEL_REASONS = ("no longer needed", "ordered by mistake")

GUESSES = {
    # lookups
    "user_not_found": "No trace shows a failed user lookup (email, name+zip, or user id); raises 'User not found' (tool descriptions say an error is returned).",
    "name_zip_case_insensitive": "Name+zip lookup matched only case-insensitively. Traces always use exact case; accepting a case difference is a guess.",
    "email_case_insensitive": "Email lookup matched only case-insensitively; traces always use exact case.",
    "order_not_found": "No trace shows an unknown order id; raises 'Order not found'.",
    "product_not_found": "No trace shows an unknown product id; raises 'Product not found'.",
    "item_not_found": "No trace shows an unknown item id; raises 'Item not found'.",
    # status / eligibility
    "cancel_not_pending": "Cancel on a non-'pending' order (incl. 'pending (item modified)') raises; policy + tool description, never seen in traces.",
    "cancel_bad_reason": "Cancel reason other than the two allowed values raises; from schema/policy, never seen in traces.",
    "modify_not_pending": "Modify (address/payment/items) on an order whose status is not exactly 'pending' raises; policy says modified orders cannot be modified again, never seen in traces.",
    "return_not_delivered": "Return on a non-'delivered' order raises; policy, never seen in traces.",
    "exchange_not_delivered": "Exchange on a non-'delivered' order raises; policy, never seen in traces.",
    # item validation
    "item_not_in_order": "An item id (counting duplicates) not present in the order raises; never seen in traces.",
    "item_count_mismatch": "item_ids and new_item_ids of different lengths raise; never seen in traces.",
    "new_item_not_found_or_other_product": "A new item id that is not a variant of the same product raises; never seen in traces.",
    "new_item_unavailable": "A new item that is not available raises; policy says 'available new item', never seen in traces.",
    "new_item_same_as_old": "Policy requires a different option; the real API may allow it. The mock ALLOWS identical old/new item (no error) and flags it.",
    "empty_item_list": "Empty item_ids list for return/exchange/modify raises; never seen in traces.",
    # payment validation
    "payment_method_not_found": "A payment method id not in the user's profile raises; never seen in traces.",
    "gift_card_insufficient": "Gift card balance below the amount to pay raises; policy, never seen in traces.",
    "return_payment_not_allowed": "Return refund method that is neither the original payment method nor a gift card of the user raises; policy, never seen in traces.",
    "payment_same_as_original": "modify_pending_order_payment to the same method as the original raises; policy, never seen.",
    # whole tools never exercised in traces
    "modify_pending_order_payment": "Tool never called in traces. Assumed: validate, append a 'payment' of the order total on the new method and a 'refund' of the same total to the old method; gift card balances updated (new -= total, old += total); status stays 'pending'; returns the order.",
    "modify_user_address": "Tool never called in traces. Assumed: replace the user's address (same key order as data: address1, address2, city, country, state, zip) and return the user dict.",
    "gift_card_balance_on_item_modify": "modify_pending_order_items paid/refunded with a gift card: the order's payment_history entry is seen, but the balance change was never observed; assumed balance -= difference (refund increases it).",
    "zero_price_difference": "modify_pending_order_items with a zero price difference: assumed no payment_history entry is added (never seen).",
    "duplicate_item_ids": "Duplicate ids in item_ids: assumed each consumes the next matching order line, in order (never seen).",
    "exchange_gift_card_untouched": "Exchange with a gift card: assumed no balance change at request time (output shows no payment entry; balance never observed afterwards).",
    "return_to_other_gift_card": "Return refunded to a gift card that is not the original payment method: allowed per policy, never seen in traces (all returns went to the original method).",
    "calculate_invalid": "Invalid/unsafe expression or division by zero raises; never seen in traces.",
    "calculate_integer_format": "Result formatting is str(round(x, 2)); integer-valued results would print like '4.0' (not seen).",
    "cancel_multi_payment": "Cancel refunds each payment transaction to its method; only single-payment pending orders seen.",
}


class _Calc(ast.NodeVisitor):
    OPS = {ast.Add: operator.add, ast.Sub: operator.sub, ast.Mult: operator.mul, ast.Div: operator.truediv}

    def ev(self, node):
        if isinstance(node, ast.Expression):
            return self.ev(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)) and not isinstance(node.value, bool):
            return node.value
        if isinstance(node, ast.BinOp) and type(node.op) in self.OPS:
            return self.OPS[type(node.op)](self.ev(node.left), self.ev(node.right))
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            v = self.ev(node.operand)
            return -v if isinstance(node.op, ast.USub) else v
        raise ValueError("Invalid characters in expression")


class Mock:
    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)
        self.flags = []
        self.transfers = []  # summaries given when transferring to a human
        for o in self.data["orders"].values():
            for f in ORDER_EXTRA_FIELDS:
                o.setdefault(f, None)

    # ------------------------------------------------------------------ helpers
    def _flag(self, label):
        assert label in GUESSES, label
        self.flags.append(label)

    def _order(self, order_id):
        o = self.data["orders"].get(order_id)
        if o is None:
            self._flag("order_not_found")
            raise Exception("Error: order not found")
        return o

    def _user(self, user_id):
        u = self.data["users"].get(user_id)
        if u is None:
            self._flag("user_not_found")
            raise Exception("Error: user not found")
        return u

    def _payment_method(self, order, payment_method_id):
        u = self._user(order["user_id"])
        pm = u["payment_methods"].get(payment_method_id)
        if pm is None:
            self._flag("payment_method_not_found")
            raise Exception("Error: payment method not found")
        return pm

    def _find_variant(self, item_id):
        for p in self.data["products"].values():
            if item_id in p["variants"]:
                return p, p["variants"][item_id]
        return None, None

    def _check_items_in_order(self, order, item_ids):
        if not item_ids:
            self._flag("empty_item_list")
            raise Exception("Error: no items given")
        all_ids = [it["item_id"] for it in order["items"]]
        for iid in set(item_ids):
            if item_ids.count(iid) > all_ids.count(iid):
                self._flag("item_not_in_order")
                raise Exception(f"Error: {iid} not found")

    def _check_new_items(self, order, item_ids, new_item_ids):
        if len(item_ids) != len(new_item_ids):
            self._flag("item_count_mismatch")
            raise Exception("Error: the number of items to be exchanged should match")
        diff = 0.0
        by_id = {it["item_id"]: it for it in order["items"]}
        for old, new in zip(item_ids, new_item_ids):
            pid = by_id[old]["product_id"]
            variants = self.data["products"][pid]["variants"]
            v = variants.get(new)
            if v is None:
                self._flag("new_item_not_found_or_other_product")
                raise Exception(f"Error: new item {new} not found or not of the same product")
            if not v["available"]:
                self._flag("new_item_unavailable")
                raise Exception(f"Error: new item {new} not available")
            if new == old:
                self._flag("new_item_same_as_old")
            diff += v["price"] - by_id[old]["price"]
        return diff

    def _check_gift_card(self, pm, amount):
        if pm["source"] == "gift_card" and pm.get("balance", 0) < amount:
            self._flag("gift_card_insufficient")
            raise Exception("Error: insufficient gift card balance to pay for the price difference")

    @staticmethod
    def _round(x):
        return round(x, 2)

    # ------------------------------------------------------------------ tools
    def calculate(self, expression):
        if not all(c in "0123456789+-*/(). " for c in expression):
            self._flag("calculate_invalid")
            raise Exception("Error: invalid characters in expression")
        try:
            v = _Calc().ev(ast.parse(expression, mode="eval"))
        except Exception as e:
            self._flag("calculate_invalid")
            raise Exception(f"Error: {e}")
        r = round(float(v), 2)
        if r == int(r):
            self._flag("calculate_integer_format")
        return str(r)

    def find_user_id_by_email(self, email):
        for uid, u in self.data["users"].items():
            if u["email"] == email:
                return uid
        for uid, u in self.data["users"].items():
            if u["email"].lower() == str(email).lower():
                self._flag("email_case_insensitive")
                return uid
        self._flag("user_not_found")
        raise Exception("Error: user not found")

    def find_user_id_by_name_zip(self, first_name, last_name, zip):
        for uid, u in self.data["users"].items():
            if (u["name"]["first_name"], u["name"]["last_name"], u["address"]["zip"]) == (first_name, last_name, zip):
                return uid
        for uid, u in self.data["users"].items():
            if (u["name"]["first_name"].lower() == str(first_name).lower()
                    and u["name"]["last_name"].lower() == str(last_name).lower()
                    and u["address"]["zip"] == zip):
                self._flag("name_zip_case_insensitive")
                return uid
        self._flag("user_not_found")
        raise Exception("Error: user not found")

    def get_user_details(self, user_id):
        return copy.deepcopy(self._user(user_id))

    def get_order_details(self, order_id):
        return copy.deepcopy(self._order(order_id))

    def get_product_details(self, product_id):
        p = self.data["products"].get(product_id)
        if p is None:
            self._flag("product_not_found")
            raise Exception("Error: product not found")
        return copy.deepcopy(p)

    def get_item_details(self, item_id):
        _, v = self._find_variant(item_id)
        if v is None:
            self._flag("item_not_found")
            raise Exception("Error: item not found")
        return copy.deepcopy(v)

    def list_all_product_types(self):
        return dict(sorted((p["name"], pid) for pid, p in self.data["products"].items()))

    def transfer_to_human_agents(self, summary):
        self.transfers.append(summary)
        return "Transfer successful"

    def cancel_pending_order(self, order_id, reason):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._flag("cancel_not_pending")
            raise Exception("Error: non-pending order cannot be cancelled")
        if reason not in CANCEL_REASONS:
            self._flag("cancel_bad_reason")
            raise Exception("Error: invalid reason")
        payments = [p for p in o["payment_history"] if p["transaction_type"] == "payment"]
        if len(payments) != 1:
            self._flag("cancel_multi_payment")
        user = self.data["users"].get(o["user_id"], {})
        for p in payments:
            o["payment_history"].append({
                "transaction_type": "refund",
                "amount": p["amount"],
                "payment_method_id": p["payment_method_id"],
            })
            pm = user.get("payment_methods", {}).get(p["payment_method_id"])
            if pm is not None and pm["source"] == "gift_card":
                pm["balance"] = self._round(pm["balance"] + p["amount"])
        o["status"] = "cancelled"
        o["cancel_reason"] = reason
        return copy.deepcopy(o)

    def modify_pending_order_address(self, order_id, address1, address2, city, state, country, zip):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._flag("modify_not_pending")
            raise Exception("Error: non-pending order cannot be modified")
        o["address"] = {"address1": address1, "address2": address2, "city": city,
                        "country": country, "state": state, "zip": zip}
        return copy.deepcopy(o)

    def modify_user_address(self, user_id, address1, address2, city, state, country, zip):
        self._flag("modify_user_address")
        u = self._user(user_id)
        u["address"] = {"address1": address1, "address2": address2, "city": city,
                        "country": country, "state": state, "zip": zip}
        return copy.deepcopy(u)

    def modify_pending_order_payment(self, order_id, payment_method_id):
        self._flag("modify_pending_order_payment")
        o = self._order(order_id)
        if o["status"] != "pending":
            self._flag("modify_not_pending")
            raise Exception("Error: non-pending order cannot be modified")
        pm = self._payment_method(o, payment_method_id)
        payments = [p for p in o["payment_history"] if p["transaction_type"] == "payment"]
        old = payments[0]
        if old["payment_method_id"] == payment_method_id:
            self._flag("payment_same_as_original")
            raise Exception("Error: the new payment method should be different from the current one")
        amount = old["amount"]
        self._check_gift_card(pm, amount)
        o["payment_history"].append({"transaction_type": "payment", "amount": amount,
                                     "payment_method_id": payment_method_id})
        o["payment_history"].append({"transaction_type": "refund", "amount": amount,
                                     "payment_method_id": old["payment_method_id"]})
        if pm["source"] == "gift_card":
            pm["balance"] = self._round(pm["balance"] - amount)
        oldpm = self.data["users"][o["user_id"]]["payment_methods"].get(old["payment_method_id"])
        if oldpm is not None and oldpm["source"] == "gift_card":
            oldpm["balance"] = self._round(oldpm["balance"] + amount)
        return copy.deepcopy(o)

    def modify_pending_order_items(self, order_id, item_ids, new_item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._flag("modify_not_pending")
            raise Exception("Error: non-pending order cannot be modified")
        self._check_items_in_order(o, item_ids)
        diff = self._check_new_items(o, item_ids, new_item_ids)
        pm = self._payment_method(o, payment_method_id)
        self._check_gift_card(pm, diff)
        if len(set(item_ids)) < len(item_ids):
            self._flag("duplicate_item_ids")
        if diff == 0:
            self._flag("zero_price_difference")
        else:
            o["payment_history"].append({
                "transaction_type": "payment" if diff > 0 else "refund",
                "amount": diff if diff > 0 else -diff,
                "payment_method_id": payment_method_id,
            })
            if pm["source"] == "gift_card":
                self._flag("gift_card_balance_on_item_modify")
                pm["balance"] = self._round(pm["balance"] - diff)
        # replace items in place, one order line per id (duplicates consume successive lines)
        used = set()
        for old, new in zip(item_ids, new_item_ids):
            for idx, it in enumerate(o["items"]):
                if idx in used or it["item_id"] != old:
                    continue
                v = self.data["products"][it["product_id"]]["variants"][new]
                it["item_id"] = new
                it["price"] = v["price"]
                it["options"] = copy.deepcopy(v["options"])
                used.add(idx)
                break
        o["status"] = "pending (item modified)"
        return copy.deepcopy(o)

    def return_delivered_order_items(self, order_id, item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "delivered":
            self._flag("return_not_delivered")
            raise Exception("Error: non-delivered order cannot be returned")
        pm = self._payment_method(o, payment_method_id)
        original = [p["payment_method_id"] for p in o["payment_history"] if p["transaction_type"] == "payment"]
        if pm["source"] != "gift_card" and payment_method_id not in original:
            self._flag("return_payment_not_allowed")
            raise Exception("Error: payment method should be either the original payment method or a gift card")
        if payment_method_id not in original:
            self._flag("return_to_other_gift_card")
        if len(set(item_ids)) < len(item_ids):
            self._flag("duplicate_item_ids")
        self._check_items_in_order(o, item_ids)
        o["status"] = "return requested"
        o["return_items"] = sorted(item_ids)
        o["return_payment_method_id"] = payment_method_id
        return copy.deepcopy(o)

    def exchange_delivered_order_items(self, order_id, item_ids, new_item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "delivered":
            self._flag("exchange_not_delivered")
            raise Exception("Error: non-delivered order cannot be exchanged")
        self._check_items_in_order(o, item_ids)
        diff = self._check_new_items(o, item_ids, new_item_ids)
        pm = self._payment_method(o, payment_method_id)
        self._check_gift_card(pm, diff)
        if pm["source"] == "gift_card":
            self._flag("exchange_gift_card_untouched")
        if len(set(item_ids)) < len(item_ids):
            self._flag("duplicate_item_ids")
        o["status"] = "exchange requested"
        o["exchange_items"] = sorted(item_ids)
        o["exchange_new_items"] = sorted(new_item_ids)
        o["exchange_payment_method_id"] = payment_method_id
        o["exchange_price_difference"] = self._round(diff)
        return copy.deepcopy(o)

    # ------------------------------------------------------------------ grading
    def state(self) -> dict:
        s = copy.deepcopy(self.data)
        for o in s["orders"].values():
            for p in o["payment_history"]:
                p["amount"] = round(p["amount"], 2)
        s["transferred_to_human"] = bool(self.transfers)
        return s
