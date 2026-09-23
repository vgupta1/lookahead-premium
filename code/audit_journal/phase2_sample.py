"""Phase 2 measurement sample: blind labelling of the OUT bucket.

Draws a fixed-seed random sample from final_bucket == OUT and writes two files:
  phase2_sample_<DRAW>.csv  - the record of what was drawn (machine buckets withheld)
  phase2_sheet_<DRAW>.md    - the reading sheet, ordered randomly, no machine output shown
The machine's bucket, reason and confidence are deliberately absent from both so the human
label is not anchored. Verdicts are recorded separately in phase2_verdicts_<DRAW>.csv.
"""
import csv, random
import os
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "data", "audit_journal"))
D = lambda n: os.path.join(DATA, n)

DATE, DRAW, N, SEED = "2026-09-16", "2026-09-18", 50, 20260918

final = list(csv.DictReader(open(D(f"triage_final_{DATE}.csv"))))
sweep = {r["sweep_id"]: r for r in csv.DictReader(open(D(f"venue_sweep_{DATE}.csv")))}

pool = sorted([r for r in final if r["final_bucket"] == "OUT"], key=lambda r: r["sweep_id"])
sample = random.Random(SEED).sample(pool, N)
random.Random(SEED + 1).shuffle(sample)

with open(D(f"phase2_sample_{DRAW}.csv"), "w", newline="") as f:
    w = csv.writer(f)
    w.writerow(["order", "sweep_id", "venue", "year", "title"])
    for i, r in enumerate(sample, 1):
        w.writerow([i, r["sweep_id"], r["venue"], r["year"], r["title"]])

with open(D(f"phase2_sheet_{DRAW}.md"), "w") as f:
    f.write(f"""# Phase 2 — blind labelling of the OUT bucket

Sample: {N} records drawn at random (seed {SEED}) from the {len(pool)} records with
`final_bucket == OUT` in `triage_final_{DATE}.csv`. The prompt was frozen before this draw.
The machine's bucket, reason and confidence are withheld.

**Task.** Read each abstract and decide whether it should go to full text. Apply the triage rule:
a decision or optimization problem is the object of the work, AND a learned or predictive component
enters the pipeline — including when the learned component is the solver itself. Physical simulation
with no decision is out; a classical algorithm with nothing learned is out.

**Recording.** List the numbers you would pull back in as CANDIDATE. Anything you do not list is
taken as agreeing with OUT. If a record is genuinely unclear, mark it and say so.

---
""")
    for i, r in enumerate(sample, 1):
        a = sweep[r["sweep_id"]]
        f.write(f"\n### {i}. {a['title']}\n\n*{a['venue']} {a['year']}*\n\n{a['abstract'].strip()}\n\n")

print(f"pool = {len(pool)} OUT records; drew {N}")
print(f"wrote phase2_sample_{DRAW}.csv and phase2_sheet_{DRAW}.md")
