"""Builds the PDF acquisition list handed to the student, from the adjudicated triage output.

One row per CANDIDATE record, sorted by venue then year, carrying everything needed to find the
paper plus the blank columns that become corpus.bib fields (journal_audit_protocol.md section 5).

Reads and writes data/audit_journal/; run from anywhere.
"""
import csv, re
import os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "data", "audit_journal"))
D = lambda n: os.path.join(DATA, n)

DATE, OUT = "2026-09-16", "pdf_pull_list_2026-09-19.csv"

sweep = {r["sweep_id"]: r for r in csv.DictReader(open(D(f"venue_sweep_{DATE}.csv")))}
cands = [r for r in csv.DictReader(open(D(f"triage_final_{DATE}.csv")))
         if r["final_bucket"] == "CANDIDATE"]
cands.sort(key=lambda r: (r["venue"], r["year"], r["sweep_id"]))

def surname(authors):
    first = (authors or "").split(",")[0].strip()
    m = re.match(r"([A-Za-zÀ-ÿ'\-]+)", first)
    return re.sub(r"[^A-Za-z]", "", m.group(1)) if m else "Unknown"

cols = ["sweep_id", "venue", "year", "first_author", "title", "doi", "url", "eid",
        "bibkey_prefix", "bibkey", "pdf_filename", "source_type", "version", "urldate",
        "appendix", "appendixfile", "notes"]

with open(D(OUT), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=cols)
    w.writeheader()
    for r in cands:
        a = sweep[r["sweep_id"]]
        w.writerow({"sweep_id": r["sweep_id"], "venue": r["venue"], "year": r["year"],
                    "first_author": (a["authors"] or "").split(",")[0].strip(),
                    "title": a["title"], "doi": a["doi"], "url": a["url"], "eid": a["eid"],
                    "bibkey_prefix": f"{surname(a['authors'])}{r['year']}_",
                    "bibkey": "", "pdf_filename": "", "source_type": "", "version": "",
                    "urldate": "", "appendix": "", "appendixfile": "", "notes": ""})

print(f"{OUT}: {len(cands)} rows; "
      f"{sum(1 for r in cands if sweep[r['sweep_id']]['doi'].strip())} carry a DOI")
