#!/usr/bin/env python3
"""
merge_vg_rulings_survey_refs.py -- merges VG's rulings into the survey screen's labels.

Same discipline as merge_vg_rulings_venue_papers.py: the machine output (survey_refs_llm_labels_<DATE>.csv) is
NEVER modified, so every human override is visible as a diff between the two files.

VG reviewed, one row per work, EVERY record the screen did not call CANDIDATE unanimously:
all BACKGROUND, all BORDERLINE, and any record whose three runs disagreed. In the review sheet
(survey_refs_vg_rulings_<DATE>.csv) a blank `vg_ruling` means "accept the machine bucket"; BORDERLINE
is not a terminal bucket and must be ruled either way.

Final buckets are CANDIDATE (goes to full text) and BACKGROUND (excluded, with a recorded reason).
Rows that are duplicates of another entry inherit their canonical row's final bucket.
"""
import csv, os, collections

DATE = "2026-09-22"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "..", "data", "audit_journal"))
SURVEY_REFS = "01_search/survey_refs.csv"
SCREEN = f"02_screen/survey_refs_llm_labels_{DATE}.csv"
REVIEW = f"02_screen/survey_refs_vg_rulings_{DATE}.csv"
OUT = f"02_screen/survey_refs_labels_merged_{DATE}.csv"

frame = {r["frame_id"]: r for r in csv.DictReader(open(os.path.join(DATA, SURVEY_REFS), encoding="utf-8"))}
scr = {r["frame_id"]: r for r in csv.DictReader(open(os.path.join(DATA, SCREEN), encoding="utf-8"))}
rev = {r["frame_id"]: r for r in csv.DictReader(open(os.path.join(DATA, REVIEW), encoding="utf-8"))}

unruled = [f for f, r in rev.items()
           if r["machine_bucket"] == "BORDERLINE" and not (r["vg_ruling"] or "").strip()]
assert not unruled, f"BORDERLINE rows left unruled: {unruled}"
bad = {(r["vg_ruling"] or "").strip() for r in rev.values()} - {"", "CANDIDATE", "BACKGROUND"}
assert not bad, f"unrecognised vg_ruling values: {bad}"

out, overrides = [], []
for fid, r in scr.items():
    canon = frame[fid]["dup_of"] or fid
    m = scr[canon]["bucket"]
    v = (rev.get(canon, {}).get("vg_ruling") or "").strip()
    final = v or m
    if final == "BORDERLINE":
        final = "CANDIDATE"          # cannot happen (asserted above); burden stays on exclusion
    if v and v != m:
        overrides.append((canon, m, v))
    out.append(dict(
        frame_id=fid, canonical_id=canon, final_bucket=final, machine_bucket=m,
        ruled_by=("VG" if v else ("structural" if m == "SEED" else "machine")),
        reviewed=("yes" if canon in rev else "no"),
        adjudicated=("yes" if v and v != m else ""),
        reason=(rev.get(canon, {}).get("vg_note") or "").strip() or r["reason"],
        agreement=r["agreement"], title=r["title"], year=r["year"],
        model_id=r["model_id"], prompt_hash=r["prompt_hash"], run_date=r["run_date"]))

with open(os.path.join(DATA, OUT), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)

works = [o for o in out if o["frame_id"] == o["canonical_id"]]
C = collections.Counter(o["final_bucket"] for o in works)
rv = [o for o in works if o["reviewed"] == "yes"]
mb = [o for o in rv if o["machine_bucket"] == "BACKGROUND"]
print(f"{OUT}: {len(out)} entries / {len(works)} works  {dict(C)}")
print(f"reviewed by VG: {len(rv)} works; overrides: {len(overrides)}  "
      f"({collections.Counter((a, b) for _, a, b in overrides)})")
print(f"machine BACKGROUND overturned to CANDIDATE: "
      f"{sum(1 for o in mb if o['final_bucket'] == 'CANDIDATE')} of {len(mb)}"
      "   <- the false-exclusion count, a census of the excluded pile, not a sample")
