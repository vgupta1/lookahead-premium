"""Apply recorded human adjudications to a triage run.

The run CSV is never modified: it is the machine output of record. Human rulings live in
triage_adjudications_2026-09-16.csv and are applied here to produce triage_final_2026-09-16.csv,
which is the corpus that Gate A / Gate B and the Phase 2 sample draw from.
"""
import csv

DATE = "2026-09-16"
RUN  = f"triage_{DATE}.csv"
ADJ  = f"triage_adjudications_{DATE}.csv"
OUT  = f"triage_final_{DATE}.csv"

adj = {r["sweep_id"]: r for r in csv.DictReader(open(ADJ))}
rows = list(csv.DictReader(open(RUN)))

fields = list(rows[0].keys()) + ["final_bucket", "adjudicated", "adjudication_note"]
changed = 0
with open(OUT, "w", newline="") as f:
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
