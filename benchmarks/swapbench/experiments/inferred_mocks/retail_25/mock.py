"""Stateful mock of the retail support-agent tool API, inferred from traces.

Only the standard library is used. See NOTES.md for the inference record.
"""
import ast
import copy
import operator

# Optional order fields that the API always appends (as null when unset), in this order.
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
    # --- error paths: the traces contain no errored call at all ---
    "err_user_not_found": "find_user_id_by_email / find_user_id_by_name_zip / get_user_details / modify_user_address raise 'User not found' for an unknown user (schema says lookups return an error; message text guessed).",
    "err_order_not_found": "Order-taking tools raise 'Order not found' for an unknown order id (message guessed).",
    "err_product_not_found": "get_product_details raises 'Product not found' for an unknown product id (message guessed).",
    "err_item_not_found": "get_item_details raises 'Item not found' for an unknown item id (message guessed).",
    "err_order_status": "Write tools raise when the order status is not the one the policy requires: cancel/modify need exactly 'pending' (policy: after 'pending (item modified)' the order can no longer be modified or cancelled), return/exchange need 'delivered'.",
    "err_cancel_reason": "cancel_pending_order raises for a reason other than 'no longer needed' / 'ordered by mistake' (policy).",
    "err_payment_method": "A payment method not in the order owner's profile raises 'Payment method not found'.",
    "err_items_not_in_order": "item_ids not present in the order (counting duplicates) raise.",
    "err_item_count_mismatch": "item_ids and new_item_ids of different lengths raise.",
    "err_new_item_invalid": "A new item that is not a variant of the same product, or is unavailable, raises (policy).",
    "err_same_item": "Modifying/exchanging an item to the identical item id raises (policy: 'different product option').",
    "err_gift_card_balance": "Gift card with insufficient balance for a positive price difference (or full total for payment change) raises (policy).",
    "err_return_payment": "Return refund method must be the original payment method or a gift card of the user (policy).",
    "err_same_payment_method": "modify_pending_order_payment to the method already used raises (policy: must be different).",
    "err_empty_items": "Empty item_ids list raises.",
    "err_calculate": "calculate raises on characters other than digits, + - * / ( ) . and spaces, or on division by zero.",
    # --- success paths not observed in traces ---
    "gift_card_refund_balance": "Refunds to a gift card are added to its balance immediately (policy); traces never showed a gift-card balance after a refund. Balance rounded to 2 decimals.",
    "gift_card_charge_balance": "Charging a gift card (modify items with positive difference, modify payment) deducts from its balance immediately; balance rounded to 2 decimals.",
    "cancel_multi_payment": "cancel_pending_order on an order with more than one payment-history entry: refunds the net amount still held per payment method (payments minus refunds), in order of first appearance.",
    "modify_items_payment": "modify_pending_order_items with a positive price difference appends a 'payment' entry of the (unrounded) difference; zero difference appends nothing. Only the refund case was observed.",
    "modify_payment": "modify_pending_order_payment (never observed): appends a 'payment' of the order total with the new method and a 'refund' of the same amount to the old method; status stays 'pending'.",
    "modify_user_address": "modify_user_address (never observed): replaces the user's address dict (key order address1,address2,city,country,state,zip as in data) and returns the full user record.",
    "get_item_details": "get_item_details (never observed): returns the variant record (item_id, options, available, price) plus product_id and name.",
    "list_all_product_types": "list_all_product_types (never observed): returns {product name: product id} sorted by name.",
    "calculate": "calculate (never observed): evaluates + - * / arithmetic and returns the result rounded to 2 decimals as a float.",
    "transfer_to_human_agents": "transfer_to_human_agents (never observed): returns 'Transfer successful' and records the transfer in state.",
    "return_items_sorted": "return_items stored sorted (observed exchange item lists are sorted; returns in traces were already sorted, so unconfirmed).",
    "name_zip_case": "find_user_id_by_name_zip matching is case-insensitive on names (traces only used canonical capitalisation).",
    "email_case": "find_user_id_by_email matching is case-insensitive (traces only used exact emails).",
    "exchange_twice": "exchange/return on an order already in 'exchange requested'/'return requested' raises via the status check (policy: only once).",
}


class Mock:
    def __init__(self, data: dict):
        self.data = copy.deepcopy(data)
        self.flags = []
        self.transfers = []
        for o in self.data["orders"].values():
            for f in ORDER_EXTRA_FIELDS:
                o.setdefault(f, None)

    # ------------------------------------------------------------- helpers
    def _flag(self, label):
        assert label in GUESSES, label
        self.flags.append(label)

    def _err(self, label, msg):
        self._flag(label)
        raise Exception(msg)

    def _order(self, order_id):
        o = self.data["orders"].get(order_id)
        if o is None:
            self._err("err_order_not_found", "Error: order not found")
        return o

    def _user(self, user_id):
        u = self.data["users"].get(user_id)
        if u is None:
            self._err("err_user_not_found", "Error: user not found")
        return u

    def _out_order(self, o):
        return copy.deepcopy(o)

    def _variant(self, item_id):
        for p in self.data["products"].values():
            if item_id in p["variants"]:
                return p, p["variants"][item_id]
        return None, None

    def _pm(self, order, payment_method_id):
        user = self._user(order["user_id"])
        pm = user["payment_methods"].get(payment_method_id)
        if pm is None:
            self._err("err_payment_method", "Error: payment method not found")
        return pm

    def _gift_adjust(self, pm, delta, label):
        if pm.get("source") == "gift_card":
            self._flag(label)
            pm["balance"] = round(pm.get("balance", 0) + delta, 2)

    def _check_items(self, order, item_ids, new_item_ids=None):
        if not item_ids:
            self._err("err_empty_items", "Error: no items given")
        pool = [it["item_id"] for it in order["items"]]
        for iid in item_ids:
            if iid in pool:
                pool.remove(iid)
            else:
                self._err("err_items_not_in_order", "Error: %s not found" % iid)
        if new_item_ids is None:
            return
        if len(item_ids) != len(new_item_ids):
            self._err("err_item_count_mismatch",
                      "Error: the number of items to be exchanged should match")
        for old, new in zip(item_ids, new_item_ids):
            old_it = next(it for it in order["items"] if it["item_id"] == old)
            prod = self.data["products"].get(old_it["product_id"])
            var = prod["variants"].get(new) if prod else None
            if var is None or not var.get("available"):
                self._err("err_new_item_invalid",
                          "Error: new item %s not found or available" % new)
            if new == old:
                self._err("err_same_item", "Error: new item %s is the same as the old item" % new)

    def _price_diff(self, order, item_ids, new_item_ids):
        old_total = 0
        for iid in item_ids:
            old_total += next(it["price"] for it in order["items"] if it["item_id"] == iid)
        new_total = 0
        for nid in new_item_ids:
            _, var = self._variant(nid)
            new_total += var["price"]
        return new_total - old_total

    # ------------------------------------------------------------- read tools
    def calculate(self, expression):
        self._flag("calculate")
        if not all(c in "0123456789+-*/(). " for c in expression):
            self._err("err_calculate", "Error: invalid characters in expression")
        ops = {ast.Add: operator.add, ast.Sub: operator.sub,
               ast.Mult: operator.mul, ast.Div: operator.truediv}

        def ev(n):
            if isinstance(n, ast.Expression):
                return ev(n.body)
            if isinstance(n, ast.Constant) and isinstance(n.value, (int, float)):
                return n.value
            if isinstance(n, ast.BinOp) and type(n.op) in ops:
                return ops[type(n.op)](ev(n.left), ev(n.right))
            if isinstance(n, ast.UnaryOp) and isinstance(n.op, (ast.USub, ast.UAdd)):
                v = ev(n.operand)
                return -v if isinstance(n.op, ast.USub) else v
            raise ValueError("bad expression")
        try:
            return round(float(ev(ast.parse(expression, mode="eval"))), 2)
        except Exception:
            self._err("err_calculate", "Error: invalid expression")

    def find_user_id_by_email(self, email):
        for uid, u in self.data["users"].items():
            if u["email"] == email:
                return uid
        for uid, u in self.data["users"].items():
            if u["email"].lower() == email.strip().lower():
                self._flag("email_case")
                return uid
        self._err("err_user_not_found", "Error: user not found")

    def find_user_id_by_name_zip(self, first_name, last_name, zip):
        for uid, u in self.data["users"].items():
            if (u["name"]["first_name"] == first_name and u["name"]["last_name"] == last_name
                    and u["address"]["zip"] == zip):
                return uid
        for uid, u in self.data["users"].items():
            if (u["name"]["first_name"].lower() == first_name.strip().lower()
                    and u["name"]["last_name"].lower() == last_name.strip().lower()
                    and u["address"]["zip"] == zip.strip()):
                self._flag("name_zip_case")
                return uid
        self._err("err_user_not_found", "Error: user not found")

    def get_order_details(self, order_id):
        return self._out_order(self._order(order_id))

    def get_product_details(self, product_id):
        p = self.data["products"].get(product_id)
        if p is None:
            self._err("err_product_not_found", "Error: product not found")
        return copy.deepcopy(p)

    def get_item_details(self, item_id):
        self._flag("get_item_details")
        p, v = self._variant(item_id)
        if v is None:
            self._err("err_item_not_found", "Error: item not found")
        out = copy.deepcopy(v)
        out["product_id"] = p["product_id"]
        out["name"] = p["name"]
        return out

    def get_user_details(self, user_id):
        return copy.deepcopy(self._user(user_id))

    def list_all_product_types(self):
        self._flag("list_all_product_types")
        return dict(sorted((p["name"], pid) for pid, p in self.data["products"].items()))

    def transfer_to_human_agents(self, summary):
        self._flag("transfer_to_human_agents")
        self.transfers.append(summary)
        return "Transfer successful"

    # ------------------------------------------------------------- write tools
    def cancel_pending_order(self, order_id, reason):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("err_order_status", "Error: non-pending order cannot be cancelled")
        if reason not in ("no longer needed", "ordered by mistake"):
            self._err("err_cancel_reason", "Error: invalid reason")
        if len(o["payment_history"]) > 1:
            self._flag("cancel_multi_payment")
        net = {}
        for h in o["payment_history"]:
            sign = 1 if h["transaction_type"] == "payment" else -1
            net[h["payment_method_id"]] = net.get(h["payment_method_id"], 0) + sign * h["amount"]
        user = self.data["users"].get(o["user_id"], {"payment_methods": {}})
        refunds = []
        for pmid, amt in net.items():
            if len(o["payment_history"]) > 1:
                amt = round(amt, 2)
            if amt > 0:
                refunds.append({"transaction_type": "refund", "amount": amt,
                                "payment_method_id": pmid})
                pm = user["payment_methods"].get(pmid)
                if pm is not None:
                    self._gift_adjust(pm, amt, "gift_card_refund_balance")
        o["payment_history"].extend(refunds)
        o["status"] = "cancelled"
        o["cancel_reason"] = reason
        return self._out_order(o)

    def modify_pending_order_address(self, order_id, address1, address2, city, state,
                                     country, zip):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("err_order_status", "Error: non-pending order cannot be modified")
        o["address"] = {"address1": address1, "address2": address2, "city": city,
                        "country": country, "state": state, "zip": zip}
        return self._out_order(o)

    def modify_pending_order_items(self, order_id, item_ids, new_item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("err_order_status", "Error: non-pending order cannot be modified")
        self._check_items(o, item_ids, new_item_ids)
        pm = self._pm(o, payment_method_id)
        diff = self._price_diff(o, item_ids, new_item_ids)
        if pm.get("source") == "gift_card" and diff > 0 and pm.get("balance", 0) < diff:
            self._err("err_gift_card_balance", "Error: insufficient gift card balance to pay for the new item")
        if diff > 0:
            self._flag("modify_items_payment")
            o["payment_history"].append({"transaction_type": "payment", "amount": diff,
                                         "payment_method_id": payment_method_id})
            self._gift_adjust(pm, -diff, "gift_card_charge_balance")
        elif diff < 0:
            o["payment_history"].append({"transaction_type": "refund", "amount": -diff,
                                         "payment_method_id": payment_method_id})
            self._gift_adjust(pm, -diff, "gift_card_refund_balance")
        else:
            self._flag("modify_items_payment")
        used = set()
        for old, new in zip(item_ids, new_item_ids):
            for idx, it in enumerate(o["items"]):
                if idx in used or it["item_id"] != old:
                    continue
                _, var = self._variant(new)
                it["item_id"] = new
                it["price"] = var["price"]
                it["options"] = copy.deepcopy(var["options"])
                used.add(idx)
                break
        o["status"] = "pending (item modified)"
        return self._out_order(o)

    def modify_pending_order_payment(self, order_id, payment_method_id):
        self._flag("modify_payment")
        o = self._order(order_id)
        if o["status"] != "pending":
            self._err("err_order_status", "Error: non-pending order cannot be modified")
        pm = self._pm(o, payment_method_id)
        pays = [h for h in o["payment_history"] if h["transaction_type"] == "payment"]
        if len(pays) != 1:
            self._err("err_order_status", "Error: there should be exactly one payment for a pending order")
        old = pays[0]
        if old["payment_method_id"] == payment_method_id:
            self._err("err_same_payment_method",
                      "Error: the new payment method should be different from the current one")
        amount = old["amount"]
        if pm.get("source") == "gift_card" and pm.get("balance", 0) < amount:
            self._err("err_gift_card_balance", "Error: insufficient gift card balance to pay for the order")
        o["payment_history"].extend([
            {"transaction_type": "payment", "amount": amount, "payment_method_id": payment_method_id},
            {"transaction_type": "refund", "amount": amount, "payment_method_id": old["payment_method_id"]},
        ])
        self._gift_adjust(pm, -amount, "gift_card_charge_balance")
        old_pm = self.data["users"][o["user_id"]]["payment_methods"].get(old["payment_method_id"])
        if old_pm is not None:
            self._gift_adjust(old_pm, amount, "gift_card_refund_balance")
        return self._out_order(o)

    def modify_user_address(self, user_id, address1, address2, city, state, country, zip):
        self._flag("modify_user_address")
        u = self._user(user_id)
        u["address"] = {"address1": address1, "address2": address2, "city": city,
                        "country": country, "state": state, "zip": zip}
        return copy.deepcopy(u)

    def return_delivered_order_items(self, order_id, item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "delivered":
            if o["status"] in ("return requested", "exchange requested"):
                self._flag("exchange_twice")
            self._err("err_order_status", "Error: non-delivered order cannot be returned")
        pm = self._pm(o, payment_method_id)
        orig = {h["payment_method_id"] for h in o["payment_history"]
                if h["transaction_type"] == "payment"}
        if payment_method_id not in orig and pm.get("source") != "gift_card":
            self._err("err_return_payment",
                      "Error: payment method should be either the original payment method or a gift card")
        self._check_items(o, item_ids)
        if sorted(item_ids) != list(item_ids):
            self._flag("return_items_sorted")
        o["status"] = "return requested"
        o["return_items"] = sorted(item_ids)
        o["return_payment_method_id"] = payment_method_id
        return self._out_order(o)

    def exchange_delivered_order_items(self, order_id, item_ids, new_item_ids, payment_method_id):
        o = self._order(order_id)
        if o["status"] != "delivered":
            if o["status"] in ("return requested", "exchange requested"):
                self._flag("exchange_twice")
            self._err("err_order_status", "Error: non-delivered order cannot be exchanged")
        self._check_items(o, item_ids, new_item_ids)
        pm = self._pm(o, payment_method_id)
        diff = self._price_diff(o, item_ids, new_item_ids)
        if pm.get("source") == "gift_card" and diff > 0 and pm.get("balance", 0) < diff:
            self._err("err_gift_card_balance", "Error: insufficient gift card balance to pay for the price difference")
        o["status"] = "exchange requested"
        o["exchange_items"] = sorted(item_ids)
        o["exchange_new_items"] = sorted(new_item_ids)
        o["exchange_payment_method_id"] = payment_method_id
        o["exchange_price_difference"] = round(diff, 2)
        return self._out_order(o)

    # ------------------------------------------------------------- grading
    def state(self) -> dict:
        return {
            "users": copy.deepcopy(self.data["users"]),
            "orders": copy.deepcopy(self.data["orders"]),
            "products": copy.deepcopy(self.data["products"]),
            "transferred_to_human": len(self.transfers) > 0,
        }
