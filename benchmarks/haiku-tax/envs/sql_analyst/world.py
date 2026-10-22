"""Synthetic warehouse for Brindle & Finch Provisions (fictional), built in memory with sqlite3 from a fixed seed.

Each world is one small database (a few thousand rows). Worlds differ in seed, so customers, orders, QA test runs and
failed loads differ. The builder records the facts the task generator needs (gap dates, QA dates) in `World.meta`.
"""
from __future__ import annotations

import datetime as dt
import random
import sqlite3
import threading
import time

INTERNAL_DOMAIN = "brindlefinch.internal"
START = dt.date(2025, 1, 1)
END = dt.date(2026, 1, 31)
UTC_OFFSET_H = -5

PRODUCTS = [  # sku, name, category, list_price
    ("COF-101", "Ridgeline Espresso Blend 250g", "Coffee", 14.50),
    ("COF-102", "Ridgeline Espresso Blend 1kg", "Coffee", 46.00),
    ("COF-103", "Ridgeline Espresso Blend 1kg Decaf", "Coffee", 49.00),
    ("COF-110", "Harbor Light Roast 250g", "Coffee", 12.75),
    ("COF-111", "Harbor Light Roast 500g", "Coffee", 22.50),
    ("COF-120", "Ember Dark Roast 250g", "Coffee", 13.25),
    ("COF-121", "Ember Dark Roast Pods 30ct", "Coffee", 18.90),
    ("COF-130", "Cold Brew Concentrate 1L", "Coffee", 16.00),
    ("COF-131", "Cold Brew Concentrate 1L Vanilla", "Coffee", 17.50),
    ("TEA-201", "Cloudpeak Green Tea 50 bags", "Tea", 9.80),
    ("TEA-202", "Cloudpeak Green Tea Loose 200g", "Tea", 15.40),
    ("TEA-210", "Saffron Hill Chai 100g", "Tea", 11.20),
    ("TEA-211", "Saffron Hill Chai Concentrate 1L", "Tea", 14.60),
    ("TEA-220", "Moorland Breakfast 80 bags", "Tea", 8.90),
    ("PAN-301", "Oat Milk Barista 1L", "Pantry", 4.20),
    ("PAN-302", "Oat Milk Barista 1L 6-pack", "Pantry", 23.50),
    ("PAN-310", "Raw Cane Sugar Cubes 500g", "Pantry", 5.60),
    ("PAN-320", "Maple Syrup 250ml", "Pantry", 11.90),
    ("PAN-321", "Vanilla Syrup 250ml", "Pantry", 8.40),
    ("EQP-401", "Pour-Over Dripper Ceramic", "Equipment", 29.00),
    ("EQP-402", "Pour-Over Dripper Glass", "Equipment", 27.00),
    ("EQP-410", "Burr Grinder Hand", "Equipment", 64.00),
    ("EQP-411", "Burr Grinder Electric", "Equipment", 149.00),
    ("EQP-420", "Gooseneck Kettle 0.8L", "Equipment", 59.00),
    ("EQP-421", "Gooseneck Kettle 0.8L Electric", "Equipment", 89.00),
]
# exact product names that are a prefix of another product's name (LIKE 'name%' over-counts)
AMBIGUOUS_NAMES = {"Ridgeline Espresso Blend 1kg", "Cold Brew Concentrate 1L", "Oat Milk Barista 1L",
                   "Gooseneck Kettle 0.8L"}
PLANS = [("COFFEE_MONTHLY", 32.00), ("COFFEE_BIWEEKLY", 58.00), ("TEA_MONTHLY", 24.00), ("TRIAL_14D", 0.00)]
CHANNELS = ["web", "mobile_app", "marketplace"]
SOURCE_TABLES = ["orders", "order_items", "refunds", "subscriptions", "web_events"]

FIRST = ["Mara", "Tobin", "Odalys", "Lucan", "Imke", "Ravi", "Selene", "Quill", "Anouk", "Bram", "Cosima", "Dario",
         "Elske", "Fenwick", "Galia", "Hollis", "Ines", "Jory", "Kaveh", "Liesel", "Marek", "Nadia", "Orrin", "Pella",
         "Rosalind", "Sefton", "Talia", "Ulric", "Vesna", "Wren", "Yara", "Zeno"]
LAST = ["Okafor", "Achterberg", "Brennick", "Ferreira-Holt", "Sadowsky", "Lindqvist", "Marchetti", "Quaresma",
        "Thornbury", "Vasquez-Lowe", "Haldane", "Ibarguen", "Kestrel", "Mbeki-Ross", "Nakashima", "Oyelaran",
        "Pemberton", "Rautio", "Szabo", "Tennant", "Ulloa", "Varga", "Whitlock", "Zeller"]
MAIL_DOMAINS = ["mailbox.example", "postnest.example", "inboxly.example", "letterbay.example"]

METRIC_DEFS = [
    ("line_amount", "quantity * unit_price - discount_amount from order_items (use the line unit_price, not "
     "products.list_price). Shipping and tax are never revenue."),
    ("gross_revenue", "Sum of line amounts of orders with status = 'completed' whose business date "
     "date(order_ts_utc, '-5 hours') is in the period."),
    ("refunds", "Sum of refunds.amount whose refund_date is in the period, regardless of when the order was placed. "
     "A refund belongs to the order line in order_item_id."),
    ("net_revenue", "Gross revenue minus refunds for the same period. Filters (category, product, channel, customer) "
     "apply to both parts, through the refunded line's product and its order's channel and customer."),
    ("orders", "Number of distinct completed orders whose business date is in the period."),
    ("aov", "Average order value = gross revenue / orders, same period and filters."),
    ("units_sold", "Sum of order_items.quantity on completed orders in the period. Refunds do not reduce units."),
    ("active_subscribers", "On date D: distinct customers with at least one subscription where plan <> 'TRIAL_14D', "
     "start_date <= D and (end_date IS NULL OR end_date > D). subscriptions.status is today's status only."),
    ("mrr", "On date D: sum of monthly_price over the subscriptions counted for active_subscribers on D (each "
     "subscription counts)."),
    ("new_subscribers", "Distinct customers whose earliest non-trial start_date falls in the period."),
    ("churned_subscribers", "For a month: distinct customers active on the first day of the month and not active on "
     "the last day of the month."),
    ("fiscal_calendar", "FY N runs Feb 1 of year N-1 to Jan 31 of year N. Q1 Feb-Apr, Q2 May-Jul, Q3 Aug-Oct, "
     "Q4 Nov-Jan. P1 = February ... P12 = January. Business time is UTC-5 all year."),
]

TABLE_DOCS = {
    "customers": "One row per customer account.",
    "products": "Product catalog; list_price is the current catalog price.",
    "orders": "One row per order; order_ts_utc is UTC. status is 'completed' or 'cancelled'.",
    "order_items": "Order lines: quantity, unit_price actually charged, discount_amount per line.",
    "refunds": "Refunds per order line, dated by refund_date (business date).",
    "subscriptions": "Subscription contracts; end_date null while running. status is today's status.",
    "metric_definitions": "Official metric definitions.",
    "etl_load_log": "Nightly warehouse loads: one row per source table, business date and attempt.",
}

SCHEMA = """
CREATE TABLE customers (customer_id TEXT PRIMARY KEY, full_name TEXT, email TEXT, signup_date TEXT, country TEXT,
  segment TEXT, is_test INTEGER);
CREATE TABLE products (product_id INTEGER PRIMARY KEY, sku TEXT, name TEXT, category TEXT, list_price REAL);
CREATE TABLE orders (order_id INTEGER PRIMARY KEY, customer_id TEXT, order_ts_utc TEXT, status TEXT, channel TEXT,
  shipping_fee REAL, tax REAL);
CREATE TABLE order_items (order_item_id INTEGER PRIMARY KEY, order_id INTEGER, product_id INTEGER, quantity INTEGER,
  unit_price REAL, discount_amount REAL);
CREATE TABLE refunds (refund_id INTEGER PRIMARY KEY, order_id INTEGER, order_item_id INTEGER, refund_date TEXT,
  amount REAL, reason TEXT);
CREATE TABLE subscriptions (subscription_id INTEGER PRIMARY KEY, customer_id TEXT, plan TEXT, start_date TEXT,
  end_date TEXT, status TEXT, monthly_price REAL);
CREATE TABLE metric_definitions (metric TEXT PRIMARY KEY, definition TEXT);
CREATE TABLE etl_load_log (load_date TEXT, table_name TEXT, attempt INTEGER, status TEXT, rows_loaded INTEGER,
  finished_at_utc TEXT);
"""


def _days(a: dt.date, b: dt.date):
    d = a
    while d <= b:
        yield d
        d += dt.timedelta(days=1)


class World:
    def __init__(self, seed: int):
        self.seed = seed
        self.lock = threading.Lock()
        self.meta: dict = {}
        self.conn = sqlite3.connect(":memory:", check_same_thread=False)
        self._build(random.Random(1000 + seed))
        self._deadline = 0.0
        self.conn.set_authorizer(self._authorize)
        self.conn.set_progress_handler(self._progress, 20000)

    # ---- read-only guard -----------------------------------------------------------------------------------------
    @staticmethod
    def _authorize(action, *_):
        ok = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION, getattr(sqlite3, "SQLITE_RECURSIVE", 33)}
        return sqlite3.SQLITE_OK if action in ok else sqlite3.SQLITE_DENY

    def _progress(self):
        return 1 if self._deadline and time.monotonic() > self._deadline else 0

    def query(self, sql: str, params=(), timeout: float = 3.0):
        with self.lock:
            self._deadline = time.monotonic() + timeout
            try:
                cur = self.conn.execute(sql, params)
                cols = [d[0] for d in cur.description] if cur.description else []
                return cols, cur.fetchall()
            finally:
                self._deadline = 0.0

    def scalar(self, sql: str):
        return self.query(sql)[1][0][0]

    # ---- builder -------------------------------------------------------------------------------------------------
    def _build(self, r: random.Random):
        c = self.conn
        c.executescript(SCHEMA)
        c.executemany("INSERT INTO metric_definitions VALUES (?,?)", METRIC_DEFS)
        for i, (sku, name, cat, price) in enumerate(PRODUCTS, start=1):
            c.execute("INSERT INTO products VALUES (?,?,?,?,?)", (i, sku, name, cat, price))
        prod = {p[0]: (i, p[3], p[2]) for i, p in enumerate(PRODUCTS, start=1)}
        skus = [p[0] for p in PRODUCTS]
        sku_w = [6 if s.startswith("COF") else 4 if s.startswith("TEA") else 4 if s.startswith("PAN") else 1.2
                 for s in skus]

        # customers: real ones (with a few duplicate full names), then internal test accounts
        customers, used = [], set()
        n_real = 200
        names = []
        for i in range(n_real):
            while True:
                nm = f"{r.choice(FIRST)} {r.choice(LAST)}"
                if nm not in used:
                    break
            used.add(nm)
            names.append(nm)
        for k in range(6):  # duplicate names: two different customers share a full name
            names[150 + k] = names[10 + k * 7]
        for i, nm in enumerate(names):
            cid = f"C-{1001 + i}"
            fn, ln = nm.split(" ", 1)
            email = f"{fn.lower()}.{ln.lower().replace('-', '')}{r.randint(1, 99)}@{r.choice(MAIL_DOMAINS)}"
            signup = START - dt.timedelta(days=r.randint(0, 700)) + dt.timedelta(days=r.randint(0, 390))
            customers.append((cid, nm, email, signup.isoformat(), r.choice(["US", "US", "US", "CA"]),
                              r.choice(["consumer", "consumer", "consumer", "office"]), 0))
        test_ids_flag, test_ids_domain = [], []
        for k in range(4):  # flagged QA bots
            cid = f"C-{1001 + n_real + k * 3}"
            customers.append((cid, f"QA Checkout Bot {k + 1}", f"qa.bot{k + 1}@{INTERNAL_DOMAIN}", "2024-11-02", "US",
                              "consumer", 1))
            test_ids_flag.append(cid)
        for k in range(2):  # unflagged staff test accounts on the internal domain
            cid = f"C-{1002 + n_real + k * 3}"
            customers.append((cid, f"Ops Test Account {k + 1}", f"ops.test{k + 1}@{INTERNAL_DOMAIN}", "2024-12-15",
                              "US", "office", 0))
            test_ids_domain.append(cid)
        customers.sort(key=lambda x: x[0])
        c.executemany("INSERT INTO customers VALUES (?,?,?,?,?,?,?)", customers)
        real_ids = [x[0] for x in customers if x[6] == 0 and INTERNAL_DOMAIN not in x[2]]
        weights = [r.choice([1, 1, 1, 2, 3, 6]) for _ in real_ids]

        # special dates
        fy = [d for d in _days(dt.date(2025, 2, 3), dt.date(2026, 1, 28))]
        picks = r.sample(fy, 18)
        gap_dates = sorted(picks[0:2])          # orders + order_items load failed, never reloaded
        retried = sorted(picks[2:4])            # failed first attempt, then succeeded
        web_fail = sorted(picks[4:6])           # irrelevant source failed
        qa_dates = sorted(picks[6:13])          # test accounts place orders
        qa_sub_dates = sorted(picks[13:16])     # test accounts start short subscriptions
        gap_set = set(gap_dates)

        orders, items, refunds = [], [], []
        oid, iid, rid = 50001, 900001, 7001
        counts: dict = {}

        def add_order(cust, local_dt, status, channel, lines, refundable=True, refund_p=0.1, refund_lag=(2, 40)):
            nonlocal oid, iid, rid
            utc = local_dt - dt.timedelta(hours=UTC_OFFSET_H)
            sub = 0.0
            my_lines = []
            for sku, qty in lines:
                pid, price, _cat = prod[sku]
                unit = price if r.random() < 0.8 else round(price * 0.9, 2)
                disc = 0.0 if r.random() < 0.85 else round(r.choice([1.0, 2.5, 5.0]) * min(qty, 2), 2)
                disc = min(disc, round(unit * qty * 0.5, 2))
                items.append((iid, oid, pid, qty, unit, disc))
                my_lines.append((iid, round(unit * qty - disc, 2)))
                sub += unit * qty - disc
                iid += 1
            ship = 0.0 if sub >= 40 else 5.95
            orders.append((oid, cust, utc.strftime("%Y-%m-%d %H:%M:%S"), status, channel, ship, round(sub * 0.08, 2)))
            if status == "completed" and refundable:
                for (lid, amt) in my_lines:
                    if r.random() < refund_p:
                        rd = local_dt.date() + dt.timedelta(days=r.randint(*refund_lag))
                        if rd <= END:
                            part = amt if r.random() < 0.6 else round(amt * r.choice([0.25, 0.5]), 2)
                            refunds.append((rid, oid, lid, rd.isoformat(), part,
                                            r.choice(["damaged", "late", "wrong_item", "taste", "duplicate"])))
                            rid += 1
            oid += 1

        for day in _days(START, END):
            n = r.randint(2, 7) + (2 if day.month in (11, 12) else 0)
            if day in gap_set:
                counts[day] = 0
                continue  # these orders never made it into the warehouse
            counts[day] = n
            for _ in range(n):
                cust = r.choices(real_ids, weights)[0]
                sec = r.randint(0, 86399)
                local_dt = dt.datetime.combine(day, dt.time()) + dt.timedelta(seconds=sec)
                nl = r.choice([1, 1, 2, 2, 3])
                lines = [(r.choices(skus, sku_w)[0], r.choice([1, 1, 1, 2, 3])) for _ in range(nl)]
                status = "completed" if r.random() < 0.92 else "cancelled"
                add_order(cust, local_dt, status, r.choices(CHANNELS, [5, 3, 2])[0], lines)
        test_all = test_ids_flag + test_ids_domain
        for day in qa_dates:
            for cust in r.sample(test_all, r.randint(2, 3)):
                for _ in range(r.randint(1, 2)):
                    # QA runs happen late in the evening company time (often already the next day in UTC)
                    local_dt = dt.datetime.combine(day, dt.time(17, 0)) + dt.timedelta(seconds=r.randint(0, 25000))
                    lines = [(r.choice(["EQP-411", "EQP-421", "COF-102", "EQP-410"]), r.randint(2, 4))]
                    if r.random() < 0.5:
                        lines.append((r.choice(skus), r.randint(1, 3)))
                    add_order(cust, local_dt, "completed", r.choice(CHANNELS), lines, refund_p=0.35,
                              refund_lag=(1, 6))
        orders.sort(key=lambda o: o[0])
        c.executemany("INSERT INTO orders VALUES (?,?,?,?,?,?,?)", orders)
        c.executemany("INSERT INTO order_items VALUES (?,?,?,?,?,?)", items)
        c.executemany("INSERT INTO refunds VALUES (?,?,?,?,?,?)", refunds)

        # subscriptions
        subs, sid = [], 3001
        subscribers = r.sample(real_ids, 110)
        for k, cust in enumerate(subscribers):
            n_subs = 1 if r.random() < 0.8 else 2
            for _ in range(n_subs):
                if r.random() < 0.25:  # trial first
                    ts = START + dt.timedelta(days=r.randint(-60, 380))
                    subs.append([sid, cust, "TRIAL_14D", ts.isoformat(), (ts + dt.timedelta(days=14)).isoformat(),
                                 0.0])
                    sid += 1
                plan, price = r.choice(PLANS[:3])
                st = START + dt.timedelta(days=r.randint(-200, 385))
                end = None if r.random() < 0.55 else st + dt.timedelta(days=r.randint(20, 300))
                if end and end > dt.date(2026, 2, 9):
                    end = None
                subs.append([sid, cust, plan, st.isoformat(), end.isoformat() if end else None, price])
                sid += 1
        for day in qa_sub_dates:
            for cust in r.sample(test_all, 2):
                plan, price = r.choice(PLANS[:3])
                subs.append([sid, cust, plan, day.isoformat(), (day + dt.timedelta(days=r.randint(2, 6))).isoformat(),
                             price])
                sid += 1
        rows = []
        for s in subs:
            status = "active" if s[4] is None else "cancelled"
            rows.append((s[0], s[1], s[2], s[3], s[4], status, s[5]))
        c.executemany("INSERT INTO subscriptions VALUES (?,?,?,?,?,?,?)", rows)

        # load log
        log = []
        for day in _days(START, END):
            fin = (dt.datetime.combine(day + dt.timedelta(days=1), dt.time(7, 10))).strftime("%Y-%m-%d %H:%M:%S")
            for t in SOURCE_TABLES:
                rows_loaded = counts[day] if t == "orders" else r.randint(1, 15) if t != "web_events" else \
                    r.randint(800, 2500)
                if t in ("orders", "order_items") and day in gap_set:
                    log.append((day.isoformat(), t, 1, "FAILED", 0, fin))
                elif t in ("orders", "order_items") and day in retried:
                    fin2 = fin.replace("07:10", "09:42")
                    log.append((day.isoformat(), t, 1, "FAILED", 0, fin))
                    log.append((day.isoformat(), t, 2, "SUCCESS", rows_loaded, fin2))
                elif t == "web_events" and day in web_fail:
                    log.append((day.isoformat(), t, 1, "FAILED", 0, fin))
                else:
                    log.append((day.isoformat(), t, 1, "SUCCESS", rows_loaded, fin))
        c.executemany("INSERT INTO etl_load_log VALUES (?,?,?,?,?,?)", log)
        c.commit()
        self.meta = {"gap_dates": [d.isoformat() for d in gap_dates], "retried": [d.isoformat() for d in retried],
                     "web_fail": [d.isoformat() for d in web_fail], "qa_dates": [d.isoformat() for d in qa_dates],
                     "qa_sub_dates": [d.isoformat() for d in qa_sub_dates],
                     "test_ids": sorted(test_all), "test_ids_domain": sorted(test_ids_domain)}
        self.names = sorted({x[1] for x in customers})
        self.emails = sorted({x[2] for x in customers})


_WORLDS: dict[int, World] = {}
_WLOCK = threading.Lock()


def world(seed: int) -> World:
    with _WLOCK:
        if seed not in _WORLDS:
            _WORLDS[seed] = World(seed)
        return _WORLDS[seed]


# ---- reference SQL -------------------------------------------------------------------------------------------------
TEST_FILTER = {
    "all": "",
    "flag": " AND c.is_test = 0",
    "full": f" AND c.is_test = 0 AND c.email NOT LIKE '%@{INTERNAL_DOMAIN}'",
}


def _ctes(v: str) -> str:
    tf = TEST_FILTER[v]
    return ("WITH lines AS (SELECT o.order_id, o.customer_id, o.channel, date(o.order_ts_utc, '-5 hours') AS d, "
            "p.sku, p.category, oi.quantity AS qty, oi.quantity * oi.unit_price - oi.discount_amount AS amt "
            "FROM orders o JOIN order_items oi ON oi.order_id = o.order_id JOIN products p ON p.product_id = "
            "oi.product_id JOIN customers c ON c.customer_id = o.customer_id WHERE o.status = 'completed'" + tf +
            "), rf AS (SELECT r.refund_date AS d, r.amount AS amt, o.customer_id, o.channel, p.sku, p.category "
            "FROM refunds r JOIN order_items oi ON oi.order_item_id = r.order_item_id JOIN orders o ON o.order_id = "
            "oi.order_id JOIN products p ON p.product_id = oi.product_id JOIN customers c ON c.customer_id = "
            "o.customer_id WHERE 1 = 1" + tf + ") ")


def _subs_cte(v: str) -> str:
    return ("WITH s AS (SELECT s.customer_id, s.plan, s.start_date, s.end_date, s.monthly_price FROM subscriptions s "
            "JOIN customers c ON c.customer_id = s.customer_id WHERE s.plan <> 'TRIAL_14D'" + TEST_FILTER[v] + ") ")


def reference_sql(q: dict, v: str = "full") -> str:
    """SQL computing the answer to question spec `q` with test-account handling `v`."""
    m = q["metric"]
    a, b = q.get("start"), q.get("end")
    per = f"d BETWEEN '{a}' AND '{b}'"
    f = "".join(f" AND {col} = '{val}'" for col, val in (q.get("filter") or {}).items())
    if m in ("active_subscribers", "mrr"):
        dd = q["date"]
        act = f"start_date <= '{dd}' AND (end_date IS NULL OR end_date > '{dd}')"
        agg = "COUNT(DISTINCT customer_id)" if m == "active_subscribers" else "ROUND(COALESCE(SUM(monthly_price), 0), 2)"
        return _subs_cte(v) + f"SELECT {agg} FROM s WHERE {act}"
    if m == "new_subscribers":
        return _subs_cte(v) + (f"SELECT COUNT(*) FROM (SELECT customer_id, MIN(start_date) AS first_start FROM s "
                               f"GROUP BY customer_id) WHERE first_start BETWEEN '{a}' AND '{b}'")
    if m == "churned_subscribers":
        return _subs_cte(v) + (f"SELECT COUNT(*) FROM (SELECT DISTINCT customer_id FROM s WHERE start_date <= '{a}' "
                               f"AND (end_date IS NULL OR end_date > '{a}')) WHERE customer_id NOT IN (SELECT "
                               f"customer_id FROM s WHERE start_date <= '{b}' AND (end_date IS NULL OR end_date > "
                               f"'{b}'))")
    base = _ctes(v)
    if m == "gross_revenue":
        return base + f"SELECT ROUND(COALESCE(SUM(amt), 0), 2) FROM lines WHERE {per}{f}"
    if m == "refunds":
        return base + f"SELECT ROUND(COALESCE(SUM(amt), 0), 2) FROM rf WHERE {per}{f}"
    if m == "net_revenue":
        return base + (f"SELECT ROUND((SELECT COALESCE(SUM(amt), 0) FROM lines WHERE {per}{f}) - "
                       f"(SELECT COALESCE(SUM(amt), 0) FROM rf WHERE {per}{f}), 2)")
    if m == "orders":
        return base + f"SELECT COUNT(DISTINCT order_id) FROM lines WHERE {per}{f}"
    if m == "aov":
        return base + f"SELECT ROUND(SUM(amt) / COUNT(DISTINCT order_id), 2) FROM lines WHERE {per}{f}"
    if m == "units_sold":
        return base + f"SELECT COALESCE(SUM(qty), 0) FROM lines WHERE {per}{f}"
    if m == "top_customers":
        return base + (f"SELECT customer_id, ROUND(SUM(amt), 2) AS v FROM (SELECT customer_id, amt FROM lines WHERE "
                       f"{per}{f} UNION ALL SELECT customer_id, -amt FROM rf WHERE {per}{f}) GROUP BY customer_id "
                       f"ORDER BY v DESC LIMIT {q['n'] + 1}")
    if m == "top_products":
        return base + (f"SELECT sku, SUM(qty) AS v FROM lines WHERE {per}{f} GROUP BY sku ORDER BY v DESC "
                       f"LIMIT {q['n'] + 1}")
    if m == "net_by_channel":
        return base + (f"SELECT channel, ROUND(SUM(amt), 2) AS v FROM (SELECT channel, amt FROM lines WHERE {per}{f} "
                       f"UNION ALL SELECT channel, -amt FROM rf WHERE {per}{f}) GROUP BY channel ORDER BY channel")
    raise ValueError(m)
