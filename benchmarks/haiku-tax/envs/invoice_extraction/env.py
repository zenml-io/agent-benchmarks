"""Invoice and document extraction for an accounts-payable team (Brindlewood Supply Co., fictional)."""
from __future__ import annotations

import json
import re
from pathlib import Path

from harness.core import Environment, State

from . import generator as G

HERE = Path(__file__).parent
GENERIC = {"ltd", "inc", "llc", "corp", "gmbh", "ag", "sas", "sarl", "bv", "sl", "plc", "dac", "group", "the", "and"}


def _s(x) -> str:
    return str(x if x is not None else "").strip()


def to_num(x):
    """Parse a number given as a number or as text like '1,234.56', '1.234,56', 'EUR 99.00'."""
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        return float(x)
    s = re.sub(r"[^0-9.,\-]", "", _s(x))
    if not s:
        return None
    if "," in s and "." in s:
        if s.rfind(",") > s.rfind("."):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", "")
    elif "," in s:
        tail = s.split(",")[-1]
        s = s.replace(",", "") if len(tail) == 3 and s.count(",") >= 1 and len(s.split(",")[0]) <= 3 else \
            s.replace(",", ".")
    try:
        return float(s)
    except ValueError:
        return None


def num_eq(a, b, tol=0.005) -> bool:
    a, b = to_num(a), to_num(b)
    return a is not None and b is not None and abs(a - b) <= tol


def norm_date(x) -> str:
    m = re.match(r"^\s*(\d{4})-(\d{1,2})-(\d{1,2})", _s(x))
    return f"{int(m[1]):04d}-{int(m[2]):02d}-{int(m[3]):02d}" if m else _s(x)


def _words(s: str) -> list[str]:
    return re.findall(r"[a-z0-9]+", s.lower().replace("&", " and "))


class InvoiceExtractionEnv(Environment):
    name = "invoice_extraction"
    description = ("an accounts-payable team: reading incoming vendor invoices, extracting their fields and "
                   "submitting, holding or rejecting each one")

    def __init__(self):
        self._tasks = None

    # ------------------------------------------------------------------------------------------- static parts
    def tasks(self):
        if self._tasks is None:
            self._tasks = G.build_tasks()
        return self._tasks

    def policy(self):
        return (HERE / "policy.md").read_text()

    def hidden_rules(self):
        return dict(G.HIDDEN_RULES)

    def read_tools(self):
        return {"get_document", "search_vendors", "get_vendor", "list_invoices_for_vendor", "get_purchase_order"}

    def write_tools(self):
        return {"submit_invoice", "hold_invoice", "reject_invoice"}

    def tool_schemas(self):
        def fn(name, desc, props, req):
            return {"type": "function", "function": {"name": name, "description": desc, "parameters": {
                "type": "object", "properties": props, "required": req}}}
        S = {"type": "string"}
        N = {"type": "number"}
        return [
            fn("get_document", "Get an incoming document from the AP inbox (raw text as received or scanned).",
               {"document_id": S}, ["document_id"]),
            fn("search_vendors", "Search the vendor master by name words or tax ID. Returns matching vendors "
               "(id, name, country, tax ID, status).", {"query": S}, ["query"]),
            fn("get_vendor", "Get a vendor master record: address, tax ID, status, billing currency, payment terms, "
               "registered bank account and the date the bank details last changed.", {"vendor_id": S},
               ["vendor_id"]),
            fn("list_invoices_for_vendor", "List invoices already received from a vendor (number, date, total, "
               "currency, status).", {"vendor_id": S}, ["vendor_id"]),
            fn("get_purchase_order", "Get a purchase order by number: vendor, currency, amount, amount invoiced to "
               "date and status.", {"po_number": S}, ["po_number"]),
            fn("submit_invoice", "Submit an invoice for payment approval with its extracted fields.", {
                "document_id": S, "vendor_id": S, "invoice_number": S,
                "invoice_date": {"type": "string", "description": "YYYY-MM-DD"},
                "due_date": {"type": "string", "description": "YYYY-MM-DD"},
                "currency": S, "subtotal": N, "tax": N, "total": N,
                "po_number": {"type": "string", "description": "PO-##########, or empty string if none"},
                "line_items": {"type": "array", "items": {"type": "object", "properties": {
                    "description": S, "quantity": N, "unit_price": N, "amount": N},
                    "required": ["description", "quantity", "unit_price", "amount"]}},
            }, ["document_id", "vendor_id", "invoice_number", "invoice_date", "due_date", "currency", "subtotal",
                "tax", "total", "po_number", "line_items"]),
            fn("hold_invoice", "Put an invoice on hold so a person reviews it before payment.",
               {"document_id": S, "reason_code": {"type": "string", "enum": G.HOLD_CODES}, "note": S},
               ["document_id", "reason_code"]),
            fn("reject_invoice", "Reject an invoice and return it to the vendor.",
               {"document_id": S, "reason_code": {"type": "string", "enum": G.REJECT_CODES}, "note": S},
               ["document_id", "reason_code"]),
        ]

    def initial_data(self, task):
        d = task["data"]
        d = dict(d)
        d["actioned"] = {}
        return d

    # ------------------------------------------------------------------------------------------- tools
    def handle(self, state: State, name: str, args: dict):
        D = state.data
        args = args or {}
        if name == "get_document":
            doc = D["documents"].get(_s(args.get("document_id")).upper())
            return doc if doc else {"error": "document not found"}
        if name == "search_vendors":
            q = _s(args.get("query"))
            if not q:
                return {"error": "query is required"}
            qt = G.norm_taxid(q)
            qw = [w for w in _words(q)]
            hits = []
            for v in D["vendors"].values():
                nw = " ".join(_words(v["name"]))
                if (len(qt) >= 6 and qt in G.norm_taxid(v["tax_id"])) or (qw and all(w in nw for w in qw)):
                    hits.append(v)
            if not hits:  # fall back to any distinctive word
                key = [w for w in qw if len(w) >= 4 and w not in GENERIC]
                hits = [v for v in D["vendors"].values() if any(w in _words(v["name"]) for w in key)]
            return {"results": [{k: v[k] for k in ("vendor_id", "name", "country", "tax_id", "status")}
                                for v in sorted(hits, key=lambda v: v["name"])][:10]}
        if name == "get_vendor":
            v = D["vendors"].get(_s(args.get("vendor_id")).upper())
            return v if v else {"error": "vendor not found"}
        if name == "list_invoices_for_vendor":
            vid = _s(args.get("vendor_id")).upper()
            if vid not in D["vendors"]:
                return {"error": "vendor not found"}
            return {"vendor_id": vid, "invoices": D["invoices"].get(vid, [])}
        if name == "get_purchase_order":
            dg = G.digits(args.get("po_number"))
            po = D["pos"].get(f"PO-{dg}") if dg else None
            return po if po else {"error": "purchase order not found"}
        # writes
        doc_id = _s(args.get("document_id")).upper()
        if doc_id not in D["documents"]:
            return {"error": "document not found"}
        if doc_id in D["actioned"]:
            return {"error": f"document {doc_id} was already actioned ({D['actioned'][doc_id]}); actions are final"}
        if name == "submit_invoice":
            req = ["vendor_id", "invoice_number", "invoice_date", "due_date", "currency", "subtotal", "tax", "total",
                   "line_items"]
            missing = [k for k in req if args.get(k) in (None, "")]
            if missing:
                return {"error": f"missing fields: {', '.join(missing)}"}
            vid = _s(args["vendor_id"]).upper()
            if vid not in D["vendors"]:
                return {"error": "vendor_id not found in vendor master"}
            if not isinstance(args["line_items"], list):
                return {"error": "line_items must be a list"}
            D["actioned"][doc_id] = "submitted"
            D["invoices"].setdefault(vid, []).insert(0, {
                "invoice_number": _s(args["invoice_number"]), "invoice_date": norm_date(args["invoice_date"]),
                "total": to_num(args["total"]), "currency": _s(args["currency"]).upper(),
                "status": "submitted (today)"})
            return {"status": "submitted", "document_id": doc_id, "ap_reference": f"AP-{doc_id[4:]}-S"}
        code = _s(args.get("reason_code")).upper()
        allowed = G.HOLD_CODES if name == "hold_invoice" else G.REJECT_CODES
        if code not in allowed:
            return {"error": f"reason_code must be one of {', '.join(allowed)}"}
        D["actioned"][doc_id] = "on hold" if name == "hold_invoice" else "rejected"
        return {"status": D["actioned"][doc_id], "document_id": doc_id, "reason_code": code}

    # ------------------------------------------------------------------------------------------- grading
    @staticmethod
    def _ok(w) -> bool:
        try:
            return "error" not in json.loads(w["result"])
        except Exception:  # noqa: BLE001
            return True

    def _check_fields(self, gold: dict, args: dict) -> list[str]:
        bad = []
        if _s(args.get("vendor_id")).upper() != gold["vendor_id"]:
            bad.append("vendor_id")
        if G.norm_inv(args.get("invoice_number")) != G.norm_inv(gold["invoice_number"]):
            bad.append("invoice_number")
        for k in ("invoice_date", "due_date"):
            if norm_date(args.get(k)) != gold[k]:
                bad.append(k)
        if _s(args.get("currency")).upper() != gold["currency"]:
            bad.append("currency")
        for k in ("subtotal", "tax", "total"):
            if not num_eq(args.get(k), gold[k]):
                bad.append(k)
        if G.digits(args.get("po_number")) != G.digits(gold["po_number"]):
            bad.append("po_number")
        try:
            got = sorted((round(to_num(l.get("quantity")), 3), round(to_num(l.get("unit_price")), 2),
                          round(to_num(l.get("amount")), 2)) for l in args.get("line_items") or [])
        except Exception:  # noqa: BLE001
            got = None
        want = sorted((round(l["quantity"], 3), round(l["unit_price"], 2), round(l["amount"], 2))
                      for l in gold["line_items"])
        if got != want:
            bad.append("line_items")
        return bad

    def grade(self, state: State) -> dict:
        gold = state.task["gold"]
        docs = gold["docs"]
        writes = [w for w in state.writes if self._ok(w)]
        rule_breaks, details, extra = set(), {}, []
        by_doc: dict[str, list] = {}
        for w in writes:
            d = _s(w["args"].get("document_id")).upper()
            if d in docs:
                by_doc.setdefault(d, []).append(w)
            else:
                extra.append({"tool": w["tool"], "document_id": d})
            if w["tool"] == "submit_invoice" and d in docs:
                rule_breaks.update(docs[d]["hidden"])
        ok = not extra
        for d, g in docs.items():
            ws = by_doc.get(d, [])
            info = {"expected": g["action"] + (f":{g['reason']}" if g["reason"] else
                                                (":any hold reason" if g["any_hold_reason"] else "")),
                    "scenario": g["scenario"]}
            if len(ws) != 1:
                info["error"] = "no action" if not ws else "more than one action"
                ok = False
            else:
                w = ws[0]
                act = {"submit_invoice": "submit", "hold_invoice": "hold", "reject_invoice": "reject"}[w["tool"]]
                info["got"] = act + (f":{_s(w['args'].get('reason_code')).upper()}" if act != "submit" else "")
                if act != g["action"]:
                    info["error"] = "wrong action"
                    ok = False
                elif act == "submit":
                    bad = self._check_fields(g["fields"], w["args"])
                    if bad:
                        info["error"] = "wrong fields: " + ", ".join(bad)
                        ok = False
                elif not g["any_hold_reason"] and _s(w["args"].get("reason_code")).upper() != g["reason"]:
                    info["error"] = "wrong reason code"
                    ok = False
            details[d] = info
        if extra:
            details["extra_writes"] = extra
        return {"success": ok, "rule_breaks": sorted(rule_breaks), "details": details}
