"""Generate fresh retail scenarios for tau2-bench with ground truth by construction.

Each scenario picks a real customer and real orders from the retail DB, a request type, and builds
the gold write actions deterministically from the DB (so the expected final DB state is exact).
Grading is DB-state only (reward_basis = ["DB"]): no LLM judge. Refusal scenarios have no write in
their gold sequence, so a policy-violating write fails the scenario.

Every scenario is validated by executing its gold actions with tau2's own tool implementations on a
fresh copy of the DB; scenarios whose gold actions raise are dropped.

  python -m swapbench.gen_retail <tau2_dir> <out_data_dir> --n 200 --seed 7 [--split fresh]

<out_data_dir> is a full TAU2_DATA_DIR (copied from <tau2_dir>/data without results/voice) whose
retail tasks.json holds only the generated scenarios and split_tasks.json = {<split>: ids, base: ids}.
"""
import argparse
import copy
import json
import os
import random
import shutil
import sys

PERSONAS = [
    "You are polite and patient.",
    "You are in a hurry and a bit impatient, and you keep your messages short.",
    "You are friendly and chatty, and you explain why you want things.",
    "You are cautious and ask the agent to repeat the details before you confirm.",
    "You are a private person who does not want to reveal more about yourself than needed.",
    "You are slightly confused about your orders and need the agent to help you find the right one.",
]

CONFIRM = ("When the agent lists the details of an action and asks you to confirm, check that they match "
           "what you want and answer yes. Do not ask for anything else.")


def item_desc(it):
    opts = ", ".join(f"{k} {v}" for k, v in it["options"].items())
    return f"{it['name']} ({opts})"


class Gen:
    def __init__(self, db, rng):
        self.db, self.rng = db, rng
        self.users = list(db["users"].values())

    def identity(self, u):
        if self.rng.random() < 0.5:
            return f"Your email is {u['email']}.", "find_user_id_by_email", {"email": u["email"]}
        n = u["name"]
        return (f"You are {n['first_name']} {n['last_name']} and your zip code is {u['address']['zip']}.",
                "find_user_id_by_name_zip",
                {"first_name": n["first_name"], "last_name": n["last_name"], "zip": u["address"]["zip"]})

    def orders(self, u, status):
        return [self.db["orders"][o] for o in u["orders"] if self.db["orders"][o]["status"] == status]

    def payment(self, u, exclude=None, need=0.0):
        """A payment method the user owns (paypal/credit card preferred; gift card only if balance covers need)."""
        pms = [p for p in u["payment_methods"].values() if p["id"] != exclude]
        ok = [p for p in pms if p["source"] in ("paypal", "credit_card")] + \
             [p for p in pms if p["source"] == "gift_card" and p.get("balance", 0) >= need]
        return self.rng.choice(ok) if ok else None

    def pm_words(self, p):
        if p["source"] == "paypal":
            return "your PayPal account"
        if p["source"] == "credit_card":
            return f"your {p.get('brand', 'credit')} card ending in {p.get('last_four', '')}"
        return "your gift card"

    def swap_target(self, it):
        """A different available variant of the same product that differs in exactly one option."""
        prod = self.db["products"][it["product_id"]]
        cands = []
        for v in prod["variants"].values():
            if not v["available"] or v["item_id"] == it["item_id"]:
                continue
            diff = [k for k in it["options"] if v["options"].get(k) != it["options"][k]]
            if len(diff) == 1:
                cands.append((diff[0], v))
        self.rng.shuffle(cands)
        for key, v in cands:
            # unique: no other available variant with the same option values
            same = [w for w in prod["variants"].values() if w["available"] and w["options"] == v["options"]]
            if len(same) == 1:
                return key, v
        return None

    # ---- scenario types -------------------------------------------------------------------------------------
    def cancel(self, u):
        pend = self.orders(u, "pending")
        if not pend:
            return None
        o = self.rng.choice(pend)
        reason = self.rng.choice(["no longer needed", "ordered by mistake"])
        why = "you no longer need it" if reason == "no longer needed" else "you ordered it by mistake"
        items = ", ".join(item_desc(i) for i in o["items"])  # all items: a careful agent reads the full order back
        return (f"You want to cancel your pending order {o['order_id']} (it contains {items}) because {why}.",
                "", [("cancel_pending_order", {"order_id": o["order_id"], "reason": reason})])

    def cancel_refuse(self, u):
        # Prefer processed orders: a delivered one can legitimately be returned, so a helpful agent's offer of a
        # return would change the end state (found in the Oct 14 scenario review; 50 of 240 hidden retail scenarios).
        done = self.orders(u, "processed") or self.orders(u, "delivered")
        if not done:
            return None
        o = self.rng.choice(done)
        return (f"You want to cancel your order {o['order_id']} ({item_desc(o['items'][0])}) because you no longer "
                "need it. If the agent says it cannot be cancelled, ask once whether there is any way to cancel it; "
                "if the answer is still no, thank them and end the conversation. Do not ask for a return or anything else, "
                "and if the agent offers a return or an exchange instead, decline it.",
                "", [])

    def ret(self, u, wrong_card=False):
        dl = [o for o in self.orders(u, "delivered") if o["items"]]
        if not dl:
            return None
        o = self.rng.choice(dl)
        k = min(len(o["items"]), self.rng.choice([1, 1, 2]))
        its = self.rng.sample(o["items"], k)
        orig = o["payment_history"][0]["payment_method_id"]
        upm = u["payment_methods"]
        if orig not in upm:
            return None
        names = " and ".join(item_desc(i) for i in its)
        if wrong_card:
            other = [p for p in upm.values() if p["id"] != orig and p["source"] == "credit_card"]
            if not other or upm[orig]["source"] == "gift_card":
                return None
            text = (f"You want to return the {names} from order {o['order_id']}. You want the refund to go to "
                    f"{self.pm_words(other[0])}. If the agent says the refund cannot go to that card, accept the refund "
                    "to the original payment method instead.")
        else:
            text = (f"You want to return the {names} from order {o['order_id']} and get the refund to the original "
                    "payment method.")
        return (text, "", [("return_delivered_order_items",
                            {"order_id": o["order_id"], "item_ids": [i["item_id"] for i in its], "payment_method_id": orig})])

    def swap(self, u, status):
        os_ = [o for o in self.orders(u, status) if o["items"]]
        if not os_:
            return None
        o = self.rng.choice(os_)
        it = self.rng.choice(o["items"])
        tgt = self.swap_target(it)
        if not tgt:
            return None
        key, v = tgt
        diff = round(v["price"] - it["price"], 2)
        pm = self.payment(u, need=max(diff, 0))
        if not pm:
            return None
        verb = "exchange" if status == "delivered" else "change"
        text = (f"In order {o['order_id']} you have a {item_desc(it)}. You want to {verb} it for the same item but with "
                f"{key} {v['options'][key]}, keeping everything else the same. Nothing else in the order should change. "
                f"For any price difference, use {self.pm_words(pm)}.")
        tool = "exchange_delivered_order_items" if status == "delivered" else "modify_pending_order_items"
        return (text, "", [(tool, {"order_id": o["order_id"], "item_ids": [it["item_id"]],
                                   "new_item_ids": [v["item_id"]], "payment_method_id": pm["id"]})])

    def address(self, u):
        pend = self.orders(u, "pending")
        if not pend:
            return None
        o = self.rng.choice(pend)
        src = self.rng.choice(self.users)["address"]  # a real-looking address from another customer
        if src == o["address"]:
            return None
        a = {k: src[k] for k in ("address1", "address2", "city", "state", "country", "zip")}
        line = f"{a['address1']}, {a['address2']}, {a['city']}, {a['state']} {a['zip']}, {a['country']}"
        return (f"You moved. You want the shipping address of your pending order {o['order_id']} changed to {line}. "
                "Only that order; do not change your default profile address.",
                "", [("modify_pending_order_address", {"order_id": o["order_id"], **a})])

    def combo(self, u):
        a, b = self.cancel(u), self.ret(u)
        if not a or not b:
            return None
        return (a[0] + " " + b[0] + " Handle the cancellation first.", "", a[2] + b[2])

    # ---- harder types (v2) -------------------------------------------------------------------------------------
    def unique_desc(self, u, it):
        """Describe an item without its order id, if it is unambiguous among the user's orders."""
        same = [i for oid in u["orders"] for i in self.db["orders"][oid]["items"] if i["name"] == it["name"]]
        return f"the {item_desc(it)}" if len(same) == 1 else None

    def exchange_by_desc(self, u):
        for o in self.rng.sample(self.orders(u, "delivered"), len(self.orders(u, "delivered"))):
            for it in o["items"]:
                d, tgt = self.unique_desc(u, it), self.swap_target(it)
                if not d or not tgt:
                    continue
                key, v = tgt
                pm = self.payment(u, need=max(v["price"] - it["price"], 0))
                if not pm:
                    continue
                return (f"You received {d} but want the same item with {key} {v['options'][key]} instead. You do not "
                        f"know the order id. For any price difference, use {self.pm_words(pm)}.", "",
                        [("exchange_delivered_order_items", {"order_id": o["order_id"], "item_ids": [it["item_id"]],
                          "new_item_ids": [v["item_id"]], "payment_method_id": pm["id"]})])
        return None

    def two_item(self, u, status, staged):
        for o in self.rng.sample(self.orders(u, status), len(self.orders(u, status))):
            pairs = [(it, self.swap_target(it)) for it in o["items"]]
            pairs = [(it, t) for it, t in pairs if t]
            if len(pairs) < 2:
                continue
            (a, (ka, va)), (b, (kb, vb)) = pairs[:2]
            diff = va["price"] - a["price"] + vb["price"] - b["price"]
            pm = self.payment(u, need=max(diff, 0))
            if not pm:
                continue
            first = f"the {item_desc(a)} for the same item with {ka} {va['options'][ka]}"
            second = f"the {item_desc(b)} for the same item with {kb} {vb['options'][kb]}"
            verb = "exchange" if status == "delivered" else "change"
            if staged:
                text = (f"In order {o['order_id']} you want to {verb} {first}. Only mention this one at first. After the "
                        f"agent has looked up the options, but before you confirm anything, say you also want to {verb} "
                        f"{second}. For any price difference, use {self.pm_words(pm)}.")
            else:
                text = (f"In order {o['order_id']} you want to {verb} {first}, and {second}. "
                        f"For any price difference, use {self.pm_words(pm)}.")
            tool = "exchange_delivered_order_items" if status == "delivered" else "modify_pending_order_items"
            return (text, "", [(tool, {"order_id": o["order_id"], "item_ids": [a["item_id"], b["item_id"]],
                                       "new_item_ids": [va["item_id"], vb["item_id"]], "payment_method_id": pm["id"]})])
        return None

    def giftcard_short(self, u):
        gcs = [p for p in u["payment_methods"].values() if p["source"] == "gift_card"]
        others = [p for p in u["payment_methods"].values() if p["source"] in ("paypal", "credit_card")]
        if not gcs or not others:
            return None
        gc = gcs[0]
        for o in self.orders(u, "delivered"):
            for it in o["items"]:
                tgt = self.swap_target(it)
                if not tgt:
                    continue
                key, v = tgt
                diff = round(v["price"] - it["price"], 2)
                if diff > gc.get("balance", 0) > 0:
                    pm = self.rng.choice(others)
                    return (f"In order {o['order_id']} you want to exchange your {item_desc(it)} for the same item with "
                            f"{key} {v['options'][key]}. You want to pay the difference with your gift card. If the agent "
                            f"says the gift card balance is not enough, pay with {self.pm_words(pm)} instead.", "",
                            [("exchange_delivered_order_items", {"order_id": o["order_id"], "item_ids": [it["item_id"]],
                              "new_item_ids": [v["item_id"]], "payment_method_id": pm["id"]})])
        return None

    def cancel_bad_reason(self, u):
        pend = self.orders(u, "pending")
        if not pend:
            return None
        o = self.rng.choice(pend)
        return (f"You want to cancel your pending order {o['order_id']} because you found the items cheaper at another "
                "store. If the agent says that reason cannot be accepted, say that you no longer need the items.", "",
                [("cancel_pending_order", {"order_id": o["order_id"], "reason": "no longer needed"})])

    def return_processed(self, u):
        pr = self.orders(u, "processed")
        if not pr:
            return None
        o = self.rng.choice(pr)
        return (f"You want to return the {item_desc(o['items'][0])} from order {o['order_id']} and get your money back. "
                "If the agent says it cannot be returned yet, ask once if they can make an exception; if not, end the "
                "conversation politely. Do not ask to cancel or for anything else.", "", [])

    def unavailable(self, u):
        for o in self.orders(u, "delivered"):
            for it in o["items"]:
                prod = self.db["products"][it["product_id"]]
                for v in prod["variants"].values():
                    diff = [k for k in it["options"] if v["options"].get(k) != it["options"][k]]
                    if not v["available"] and len(diff) == 1:
                        k = diff[0]
                        return (f"In order {o['order_id']} you want to exchange your {item_desc(it)} for the same item "
                                f"with {k} {v['options'][k]}. If that exact variant is not available, you prefer to keep "
                                "your current item: say so and end the conversation. Do not accept any other variant.",
                                "", [])
        return None

    def cheaper_return(self, u):
        for o in self.orders(u, "delivered"):
            its = [i for i in o["items"]]
            if len(its) >= 2 and abs(its[0]["price"] - its[1]["price"]) > 5:
                a, b = its[0], its[1]
                cheap = a if a["price"] < b["price"] else b
                orig = o["payment_history"][0]["payment_method_id"]
                if orig not in u["payment_methods"]:
                    continue
                return (f"In order {o['order_id']} you are unsure whether to return the {item_desc(a)} or the "
                        f"{item_desc(b)}. Ask the agent how much each would refund, then return only the one with the "
                        "smaller refund, to the original payment method.", "",
                        [("return_delivered_order_items", {"order_id": o["order_id"], "item_ids": [cheap["item_id"]],
                          "payment_method_id": orig})])
        return None

    SUBS = ["cancel", "return", "exchange_by_desc", "modify_items", "address", "cancel_refuse", "return_processed",
            "unavailable", "giftcard_short", "cheaper_return", "cancel_bad_reason", "exchange_two", "return_wrong_card"]
    SOFTEN = [("if the answer is still no, thank them and end the conversation. Do not ask for a return or anything else.",
               "if the answer is still no, accept it and move on."),
              ("if not, end the conversation politely. Do not ask to cancel or for anything else.",
               "if not, accept it and move on."),
              ("say so and end the conversation. Do not accept any other variant.",
               "say so and move on. Do not accept any other variant.")]

    def composite(self, u, k):
        """k requests on k distinct orders of one customer in one conversation; gold = all their writes in order."""
        import re
        parts, writes, used = [], [], set()
        for _ in range(40):
            if len(parts) == k:
                break
            sub = self.make(self.rng.choice(self.SUBS), u)
            if not sub:
                continue
            text, _, w = sub
            oids = set(re.findall(r"#W\d+", text)) | {a.get("order_id") for _, a in w if a.get("order_id")}
            if not oids or oids & used:
                continue
            used |= oids
            for a_, b_ in self.SOFTEN:
                text = text.replace(a_, b_)
            parts.append(text)
            writes += w
        if len(parts) < k:
            return None
        order = ["First", "Second", "Third", "Fourth"]
        text = ("You have several things to sort out, and you raise them one at a time, only moving to the next once "
                "the current one is resolved. " + " ".join(f"{order[i]}: {t}" for i, t in enumerate(parts)))
        return text, "", writes

    def make(self, kind, u):
        return {"cancel": self.cancel, "cancel_refuse": self.cancel_refuse, "return": self.ret,
                "return_wrong_card": lambda x: self.ret(x, wrong_card=True),
                "exchange": lambda x: self.swap(x, "delivered"), "modify_items": lambda x: self.swap(x, "pending"),
                "address": self.address, "combo": self.combo,
                "exchange_by_desc": self.exchange_by_desc,
                "exchange_two": lambda x: self.two_item(x, "delivered", False),
                "modify_two_staged": lambda x: self.two_item(x, "pending", True),
                "exchange_two_staged": lambda x: self.two_item(x, "delivered", True),
                "giftcard_short": self.giftcard_short, "cancel_bad_reason": self.cancel_bad_reason,
                "return_processed": self.return_processed, "unavailable": self.unavailable,
                "cheaper_return": self.cheaper_return,
                "composite3": lambda x: self.composite(x, 3), "composite4": lambda x: self.composite(x, 4)}[kind](u)


EASY = ["cancel", "cancel_refuse", "return", "return_wrong_card", "exchange", "modify_items", "address", "combo"]
HARD = ["exchange_by_desc", "exchange_two", "modify_two_staged", "exchange_two_staged", "giftcard_short",
        "cancel_bad_reason", "return_processed", "unavailable", "cheaper_return"]
COMPOSITE = ["composite3", "composite4"]
KINDS = EASY + HARD


def validate(tau2_src, db_path, actions):
    """Execute gold actions with tau2's tools on a fresh DB; raise on any error."""
    sys.path.insert(0, tau2_src)
    from tau2.domains.retail.data_model import RetailDB
    from tau2.domains.retail.tools import RetailTools
    tools = RetailTools(RetailDB.load(db_path))
    for name, args in actions:
        getattr(tools, name)(**args)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("tau2_dir")
    ap.add_argument("out_data_dir")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--split", default="fresh")
    ap.add_argument("--kinds", default="all", help="all | hard | composite | comma list")
    ap.add_argument("--prefix", default="g", help="scenario id prefix (keep pools disjoint)")
    ap.add_argument("--splits", help="partition in generation order, e.g. train:60,test:240 (default: all in --split)")
    a = ap.parse_args()
    src_data = os.path.join(a.tau2_dir, "data")
    db_path = os.path.join(src_data, "tau2", "domains", "retail", "db.json")
    db = json.load(open(db_path))
    rng = random.Random(a.seed)
    g = Gen(db, rng)
    tasks, counts, tries = [], {}, 0
    global KINDS
    KINDS = {"all": EASY + HARD, "hard": HARD, "composite": COMPOSITE}.get(a.kinds) or a.kinds.split(",")
    per_kind = a.n // len(KINDS) + 1
    while len(tasks) < a.n and tries < a.n * 200:
        tries += 1
        kind = KINDS[len(tasks) % len(KINDS)] if counts.get(KINDS[len(tasks) % len(KINDS)], 0) < per_kind else rng.choice(KINDS)
        u = rng.choice(g.users)
        sc = g.make(kind, u)
        if not sc:
            continue
        text, _, writes = sc
        who, find_tool, find_args = g.identity(u)
        gold = [(find_tool, find_args)] + writes
        try:
            validate(os.path.join(a.tau2_dir, "src"), db_path, gold)
        except Exception:
            continue
        tid = f"{a.prefix}{len(tasks)}"
        tasks.append({
            "id": tid,
            "description": {"purpose": f"swapbench generated: {kind}", "relevant_policies": None, "notes": f"seed {a.seed}"},
            "user_scenario": {"persona": None, "instructions": {
                "task_instructions": rng.choice(PERSONAS) + " " + CONFIRM,
                "domain": "retail", "reason_for_call": text, "known_info": who,
                "unknown_info": "You do not remember your user id."}},
            "initial_state": None,
            "evaluation_criteria": {
                "actions": [{"action_id": f"{tid}_{i}", "name": n, "arguments": args, "info": None}
                            for i, (n, args) in enumerate(gold)],
                "communicate_info": [], "nl_assertions": [], "reward_basis": ["DB"]},
        })
        counts[kind] = counts.get(kind, 0) + 1
    # write a full data dir with only the generated retail tasks
    if os.path.exists(a.out_data_dir):
        shutil.rmtree(a.out_data_dir)
    shutil.copytree(src_data, a.out_data_dir, ignore=shutil.ignore_patterns("results", "voice"))
    d = os.path.join(a.out_data_dir, "tau2", "domains", "retail")
    json.dump(tasks, open(os.path.join(d, "tasks.json"), "w"), indent=1)
    ids = [t["id"] for t in tasks]
    splits = {a.split: ids}
    if a.splits:
        splits, i = {}, 0
        for part in a.splits.split(","):
            name, k = part.split(":")
            splits[name] = ids[i:i + int(k)]
            i += int(k)
    json.dump({**splits, "base": ids}, open(os.path.join(d, "split_tasks.json"), "w"), indent=1)
    for extra in ("tasks_voice.json", "task_issues", "audio_difficulty.json"):
        p = os.path.join(d, extra)
        shutil.rmtree(p) if os.path.isdir(p) else (os.remove(p) if os.path.exists(p) else None)
    print(f"wrote {len(tasks)} scenarios ({counts}) to {d}")


if __name__ == "__main__":
    main()
