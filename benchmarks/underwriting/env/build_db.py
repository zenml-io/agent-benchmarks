"""Rebuild the underwriting environment (SQLite database + guidelines) that Snorkel's agents queried.

  python -I env/build_db.py env/extracted.json env/census env/insurance.db env/guidelines.txt

Tables and columns match the schemas the agents saw (env/extracted.json and the traces):
  naics, naics_2digit, naics_2022_2017, naics_2012_2017  US Census Bureau files, downloaded to env/census
  states, lobs                                           as listed in the traces (51 states incl. DC; 6 LOBs in order)
  small_business_definition                              the 750 SBA size-standard rows observed in the traces
                                                         (the SBA table of that era, keyed by 2012 NAICS); others absent
  appetite_guide                                         one row per 2022 6-digit NAICS x state x LOB. Value: the
                                                         observed value for that NAICS and LOB (never varies by state),
                                                         else the observed value for its 2-digit sector and LOB, else
                                                         left out (the agent then sees no row, as for unknown codes)
The index column follows the original ordering (NAICS block of 51 states x 6 LOBs), which the observed index values
confirm when the NAICS order matches.
"""
import json
import os
import sqlite3
import sys
import urllib.request
from collections import Counter, defaultdict

import openpyxl

CENSUS = {
    "descriptions": "https://www.census.gov/naics/2022NAICS/2022_NAICS_Descriptions.xlsx",
    "codes": "https://www.census.gov/naics/2022NAICS/2-6%20digit_2022_Codes.xlsx",
    "c2022_2017": "https://www.census.gov/naics/concordances/2022_to_2017_NAICS.xlsx",
    "c2012_2017": "https://www.census.gov/naics/concordances/2012_to_2017_NAICS.xlsx",
}
STATES = [("Alabama", "AL"), ("Alaska", "AK"), ("Arizona", "AZ"), ("Arkansas", "AR"), ("California", "CA"),
          ("Colorado", "CO"), ("Connecticut", "CT"), ("Delaware", "DE"), ("District of Columbia", "DC"),
          ("Florida", "FL"), ("Georgia", "GA"), ("Hawaii", "HI"), ("Idaho", "ID"), ("Illinois", "IL"),
          ("Indiana", "IN"), ("Iowa", "IA"), ("Kansas", "KS"), ("Kentucky", "KY"), ("Louisiana", "LA"),
          ("Maine", "ME"), ("Maryland", "MD"), ("Massachusetts", "MA"), ("Michigan", "MI"), ("Minnesota", "MN"),
          ("Mississippi", "MS"), ("Missouri", "MO"), ("Montana", "MT"), ("Nebraska", "NE"), ("Nevada", "NV"),
          ("New Hampshire", "NH"), ("New Jersey", "NJ"), ("New Mexico", "NM"), ("New York", "NY"),
          ("North Carolina", "NC"), ("North Dakota", "ND"), ("Ohio", "OH"), ("Oklahoma", "OK"), ("Oregon", "OR"),
          ("Pennsylvania", "PA"), ("Rhode Island", "RI"), ("South Carolina", "SC"), ("South Dakota", "SD"),
          ("Tennessee", "TN"), ("Texas", "TX"), ("Utah", "UT"), ("Vermont", "VT"), ("Virginia", "VA"),
          ("Washington", "WA"), ("West Virginia", "WV"), ("Wisconsin", "WI"), ("Wyoming", "WY")]
LOBS = ["workers compensation", "property", "general liability", "auto", "cyber", "bop"]


def fetch(census_dir):
    os.makedirs(census_dir, exist_ok=True)
    paths = {}
    for k, url in CENSUS.items():
        p = os.path.join(census_dir, k + ".xlsx")
        if not os.path.exists(p):
            urllib.request.urlretrieve(url, p)
        paths[k] = p
    return paths


def rows(path):
    ws = openpyxl.load_workbook(path, read_only=True).worksheets[0]
    return [r for r in ws.iter_rows(values_only=True)]


def main(extracted, census_dir, db_path, guidelines_path):
    ex = json.load(open(extracted))
    paths = fetch(census_dir)
    desc = {}
    for r in rows(paths["descriptions"])[1:]:
        if r[0] is not None:
            desc[str(r[0]).strip()] = (str(r[1] or "").strip().rstrip("T").strip(), str(r[2] or "").strip())
    six, two = [], []
    for r in rows(paths["codes"])[2:]:
        code, title = (str(r[1]).strip() if r[1] is not None else ""), str(r[2] or "").strip()
        if code.isdigit() and len(code) == 6:
            six.append((int(code), title, desc.get(code, ("", ""))[1]))
        elif len(code) == 2 or (len(code) == 5 and "-" in code):
            two.append((code, title, desc.get(code, ("", ""))[1]))
    c22 = [(int(r[0]), int(r[2])) for r in rows(paths["c2022_2017"])[3:] if r[0] and r[2] and str(r[0]).isdigit()]
    c12 = [(int(r[0]), int(r[2])) for r in rows(paths["c2012_2017"])[3:] if r[0] and r[2] and str(r[0]).isdigit()]

    observed = {(n, lob): v for n, _, lob, v in ex["appetite_rows"]}
    sector = defaultdict(Counter)
    for (n, lob), v in observed.items():
        sector[(n // 10000, lob)][v] += 1
    appetite, unknown = [], Counter()
    for i, (code, _, _) in enumerate(six):
        for j, (_, abbr) in enumerate(STATES):
            for k, lob in enumerate(LOBS):
                if (code, lob) in observed:
                    v = observed[(code, lob)]
                elif sector[(code // 10000, lob)]:
                    v = sector[(code // 10000, lob)].most_common(1)[0][0]
                else:
                    unknown[(code // 10000, lob)] += 1
                    continue
                appetite.append((i * len(STATES) * len(LOBS) + j * len(LOBS) + k, code, abbr, lob, v, code // 10000))

    if os.path.exists(db_path):
        os.remove(db_path)
    con = sqlite3.connect(db_path)
    ddl = {
        "naics": '("index" INTEGER, "Code" INTEGER, "Title" TEXT, "Description" TEXT)',
        "naics_2digit": '("index" INTEGER, "Code" TEXT, "Title" TEXT, "Description" TEXT)',
        "naics_2022_2017": '("index" INTEGER, "2022 NAICS" INTEGER, "2017 NAICS" INTEGER)',
        "naics_2012_2017": '("index" INTEGER, "2012 NAICS" INTEGER, "2017 NAICS" INTEGER)',
        "small_business_definition": '("index" INTEGER, "NAICS Codes" INTEGER, '
                                     '"Size Standards in millions of dollars" REAL, '
                                     '"Size standards in number of employees" REAL)',
        "states": '("index" INTEGER, "State" TEXT, "Abbreviation" TEXT)',
        "lobs": '("index" INTEGER, "lob" TEXT)',
        "appetite_guide": '("index" INTEGER, "naics" INTEGER, "state" TEXT, "lob" TEXT, "appetite" TEXT, '
                          '"naics_2digit" INTEGER)',
    }
    for t, cols in ddl.items():
        con.execute(f'CREATE TABLE "{t}" {cols}')
    ins = lambda t, data: con.executemany(f'INSERT INTO "{t}" VALUES ({",".join("?" * len(data[0]))})', data)  # noqa
    ins("naics", [(i, *r) for i, r in enumerate(six)])
    ins("naics_2digit", [(i, *r) for i, r in enumerate(two)])
    ins("naics_2022_2017", [(i, *r) for i, r in enumerate(c22)])
    ins("naics_2012_2017", [(i, *r) for i, r in enumerate(c12)])
    sba = sorted((int(k), v[0], v[1]) for k, v in ex["sba_rows"].items())
    ins("small_business_definition", [(i, *r) for i, r in enumerate(sba)])
    ins("states", [(i, *r) for i, r in enumerate(STATES)])
    ins("lobs", [(i, lob) for i, lob in enumerate(LOBS)])
    ins("appetite_guide", appetite)
    con.commit()
    open(guidelines_path, "w").write(ex["guidelines"])
    # Fidelity: observed (naics, state, lob, value) rows reproduced, and observed index values matched.
    got = {(r[1], r[2], r[3]): r[4] for r in appetite}
    match = sum(got.get((n, s, lob)) == v for n, s, lob, v in ex["appetite_rows"])
    print(f"naics {len(six)}  2digit {len(two)}  c22 {len(c22)}  c12 {len(c12)}  sba {len(sba)}  "
          f"appetite {len(appetite)}  unknown sector-lob {dict(unknown)}")
    print(f"observed appetite rows reproduced: {match}/{len(ex['appetite_rows'])}")


if __name__ == "__main__":
    main(*sys.argv[1:5])
