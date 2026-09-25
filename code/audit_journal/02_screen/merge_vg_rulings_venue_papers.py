"""merge_vg_rulings_venue_papers.py -- merges VG's hand decisions into the sweep screen's labels.

The run CSV is never modified: it is the machine output of record. Human rulings live in
venue_papers_vg_rulings_2026-09-16.csv and are applied here to produce venue_papers_labels_merged_2026-09-16.csv,
which is what the blind recheck and everything downstream read.
"""
import csv, os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "..", "data", "audit_journal"))
D = lambda n: os.path.join(DATA, n)

DATE = "2026-09-16"
RUN  = f"02_screen/venue_papers_llm_labels_{DATE}.csv"
ADJ  = f"02_screen/venue_papers_vg_rulings_{DATE}.csv"
OUT  = f"02_screen/venue_papers_labels_merged_{DATE}.csv"

adj = {r["sweep_id"]: r for r in csv.DictReader(open(D(ADJ)))}
rows = list(csv.DictReader(open(D(RUN))))

fields = list(rows[0].keys()) + ["final_bucket", "adjudicated", "adjudication_note"]
changed = 0
with open(D(OUT), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=fields)
    w.writeheader()
    for r in rows:
        a = adj.get(r["sweep_id"])
        r["final_bucket"] = a["vg_bucket"] if a else r["bucket"]
        r["adjudicated"] = "yes" if a else ""
        r["adjudication_note"] = a["note"] if a else ""
        if a and a["vg_bucket"] != r["bucket"]:
            changed += 1
        w.writerow(r)

from collections import Counter
final = Counter(r["final_bucket"] for r in rows)
print(f"{OUT}: {len(rows)} records, {len(adj)} adjudicated, {changed} overrode the machine bucket")
print(final)
unmatched = set(adj) - {r["sweep_id"] for r in rows}
if unmatched:
    print("WARNING adjudications with no matching record:", unmatched)
