"""
Collect German statutory health insurance disputes (Sozialgericht, first instance, register "KR")
from the Open Legal Data API (https://de.openlegaldata.io), label each from its operative
ruling (Tenor) and keep the facts section (Tatbestand) as the case file.

    python de_kr_fetch.py                                    # walk the API (newest first), writes work/de_kr/cases_raw.jsonl
    python de_kr_fetch.py --ids ../data/de_kr_case_index.json  # re-fetch the published 684 cases by ID, in order

Label: "Die Klage wird abgewiesen" (claim dismissed: the insurer's refusal stands) -> "uphold";
the insurer is ordered to pay / its decision is set aside, with nothing dismissed -> "overturn".
Partial outcomes, settlements and procedural decisions are skipped.
"""
import argparse
import html
import json
import os
import re
import time
import urllib.request
from pathlib import Path

WORK = Path(os.environ.get("DECISION_WORK_DIR") or Path(__file__).resolve().parent.parent / "work")
OUT = WORK / "de_kr" / "cases_raw.jsonl"
API = "https://de.openlegaldata.io/api/cases/"
FILE_RE = re.compile(r"^S \d+ KR \d+/\d+")


def get(url):
    for i in range(4):
        try:
            return json.load(urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "agent-benchmarks decision-agents research"}), timeout=60))
        except Exception:  # noqa: BLE001
            time.sleep(5 * (i + 1))
    return None


def text_of(content):
    t = re.sub(r"<br\s*/?>|</p>|</h\d>", "\n", content or "")
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t]+", " ", t)


def split(t):
    m_ten = re.search(r"Tenor(.*?)(Tatbestand|Gründe|Entscheidungsgründe)", t, re.S)
    m_tat = re.search(r"Tatbestand(.*?)Entscheidungsgründe", t, re.S)
    if not (m_ten and m_tat):
        return None, None
    ten = re.sub(r"\s+", " ", m_ten.group(1)).lower()
    dismissed = "klage wird abgewiesen" in ten or "klagen werden abgewiesen" in ten
    partial = "im übrigen" in ten
    won = bool(re.search(r"(beklagte|antragsgegnerin) wird (unter aufhebung .{0,200})?verurteilt|bescheid .{0,200} wird aufgehoben", ten))
    if partial or dismissed == won:
        return None, None
    return ("uphold" if dismissed else "overturn"), m_tat.group(1).strip()


def months(start=(2026, 10), stop=(2012, 1)):
    y, m = start
    while (y, m) >= stop:
        ny, nm = (y, m + 1) if m < 12 else (y + 1, 1)
        yield f"{y}-{m:02d}-01", f"{ny}-{nm:02d}-01"
        y, m = (y, m - 1) if m > 1 else (y - 1, 12)


def fetch_ids(index_path):
    """Re-fetch a fixed list of cases by ID (in the index's order) and relabel each from its text.

    The month walk below depends on what the API holds on the day it runs; this reproduces the
    published case set. A case whose label or facts no longer parse the same way is reported."""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    index = json.load(open(index_path))
    bad = 0
    with OUT.open("w") as f:
        for i, r in enumerate(index):
            c = get(f"{API}{r['id']}/?format=json")
            time.sleep(0.5)
            lab, facts = split(text_of((c or {}).get("content")))
            if not (c and lab and facts and 800 < len(facts) < 20000) or lab != r["truth"]:
                bad += 1
                print(f"case {r['id']}: label {lab!r} (published {r['truth']!r}), facts {len(facts or '')} chars", flush=True)
                continue
            f.write(json.dumps({"id": c["id"], "court": c["court"]["name"], "file_number": c["file_number"],
                                "date": c["date"], "truth": lab, "facts": facts}, ensure_ascii=False) + "\n")
            if (i + 1) % 100 == 0:
                print(f"{i + 1}/{len(index)} fetched", flush=True)
    print(f"wrote {len(index) - bad} of {len(index)} cases; {bad} differ or failed", flush=True)


def main():
    """The API serves at most 10 pages per query, so walk month by month (newest first)."""
    OUT.parent.mkdir(parents=True, exist_ok=True)
    seen = {json.loads(l)["id"] for l in open(OUT)} if OUT.exists() else set()
    kept, scanned = len(seen), 0
    with OUT.open("a") as f:
        for lo, hi in months():
            url = f"{API}?court__jurisdiction=Sozialgerichtsbarkeit&date_after={lo}&date_before={hi}&page_size=100&format=json"
            while url and kept < 700:
                page = get(url)
                if not page:
                    break
                for r in page["results"]:
                    scanned += 1
                    if r["id"] in seen or not FILE_RE.match(r.get("file_number") or ""):
                        continue
                    seen.add(r["id"])
                    c = get(f"{API}{r['id']}/?format=json")
                    time.sleep(0.5)
                    if not c:
                        continue
                    lab, facts = split(text_of(c.get("content")))
                    if lab and facts and 800 < len(facts) < 20000:
                        f.write(json.dumps({"id": r["id"], "court": r["court"]["name"], "file_number": r["file_number"],
                                            "date": r["date"], "truth": lab, "facts": facts}, ensure_ascii=False) + "\n")
                        f.flush()
                        kept += 1
                url = page.get("next")
                time.sleep(1)
            print(f"{lo}: scanned {scanned}, kept {kept}", flush=True)
            if kept >= 700:
                break


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ids", help="JSON list of {id, truth} to re-fetch in order (data/de_kr_case_index.json)")
    a = ap.parse_args()
    fetch_ids(a.ids) if a.ids else main()
