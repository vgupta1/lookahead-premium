#!/usr/bin/env python3
"""
repair_seed_frame.py -- seed_frame_2026-09-10.csv -> seed_frame_2026-09-21.csv

The 2026-09-10 frame matched references across the two surveys on normalized title only. That
left two defects, found 2026-09-21 while sizing the seed-frame screen:

1. A PARSE COLLISION DROPPED A REFERENCE. Two EJOR entries print their volume before their title
   ("Vol. 616, Implicit functions ..." and "Vol. 2, The elements of statistical learning ..."), so
   both parsed to the title "Vol" and collapsed into one row. Hastie-Tibshirani-Friedman vanished.
   The same pass merged El Balghiti et al.'s NeurIPS 2019 and MOR 2022 entries on their identical
   title, silently dropping the journal version. That is why the frame carried 189 Sadana rows,
   not the 191 references the survey prints and Crossref deposits. Both are restored here as rows,
   so every row is again exactly one printed bibliography entry: 153 + 191 - 31 = 313.

2. SAME WORK, DIFFERENT STRING. Seven works appear once in each survey under strings the title
   normalization did not equate (hyphenation lost in PDF extraction, an arXiv title vs the
   proceedings title, a preprint vs its published version). Plus the El Balghiti version pair
   inside EJOR. These are recorded in a new column `dup_of` pointing at the canonical row; rows are
   never deleted, so every frame_id keeps its meaning and downstream joins stay valid.

frame_ids SF0001-SF0311 are unchanged. The two restored entries are APPENDED as SF0312-SF0313
rather than slotted into the (first author, year, title) order, which would renumber everything.

Unit of the frame from here on: 313 bibliography entries; 305 distinct works (313 - 8 dup_of).
Works cited by both surveys: 38 (31 title matches + 7 dup_of links across surveys).
"""
import csv, os
HERE = os.path.dirname(os.path.abspath(__file__))
SRC, OUT = "seed_frame_2026-09-10.csv", "seed_frame_2026-09-21.csv"

TITLE_FIX = {"SF0081": "Implicit functions and solution mappings: A view from variational analysis"}

APPEND = [
    dict(frame_id="SF0312", title="The elements of statistical learning: data mining, inference, and prediction",
         year="2009", first_author="Hastie", in_jair="", in_sadana="Y",
         full_entry="Hastie, T., Tibshirani, R., & Friedman, J. H. (2009). Vol. 2, The elements of statistical "
                    "learning: data mining, inference, and prediction. Springer.",
         dup_of="", repair_note="restored 2026-09-21: dropped by 'Vol' title collision with SF0081"),
    dict(frame_id="SF0313", title="Generalization bounds in the predict-then-optimize framework",
         year="2022", first_author="El Balghiti", in_jair="", in_sadana="Y",
         full_entry="El Balghiti, O., Elmachtoub, A. N., Grigas, P., & Tewari, A. (2022). Generalization bounds in "
                    "the predict-then-optimize framework. Mathematics of Operations Research, 48(4), 1811–2382.",
         dup_of="SF0086", repair_note="restored 2026-09-21: journal version, merged into NeurIPS 2019 entry on title"),
]

# (row, canonical, evidence). Canonical = the lower frame_id in every case.
DUP = [
    ("SF0088", "SF0087", "SPO Trees, ICML 2020: 'decisionmaking' vs 'decision-making' (hyphen lost)"),
    ("SF0161", "SF0160", "Kotary et al. IJCAI-23: arXiv title 'Folded optimization for end-to-end "
                         "model-based learning' vs proceedings title"),
    ("SF0172", "SF0171", "Liu & Grigas NeurIPS 2021: 'predict-thenoptimize' vs 'predict-then-optimize'"),
    ("SF0175", "SF0174", "Liu et al. active learning PtO: 'predictthen-optimize' vs 'predict-thenoptimize'"),
    ("SF0228", "SF0227", "Qi & Shen, INFORMS TutORials 2022: same entry, one string lacks the book title"),
    ("SF0272", "SF0270", "PyEPO: arXiv 2022 (EJOR) vs 2023 (JAIR), same work"),
    ("SF0294", "SF0293", "Wilder et al. AAAI 2019: 'Decisionfocused' vs 'Decision-focused'"),
]

rows = list(csv.DictReader(open(os.path.join(HERE, SRC), encoding="utf-8")))
assert len(rows) == 311
for r in rows:
    r["dup_of"], r["repair_note"] = "", ""
    if r["frame_id"] in TITLE_FIX:
        assert r["title"] == "Vol"
        r["title"] = TITLE_FIX[r["frame_id"]]; r["repair_note"] = "title re-parsed 2026-09-21 (was 'Vol')"
by = {r["frame_id"]: r for r in rows}
for d, c, ev in DUP:
    assert by[d]["first_author"].split()[0][:4].lower() == by[c]["first_author"].split()[0][:4].lower(), (d, c)
    by[d]["dup_of"], by[d]["repair_note"] = c, "same work: " + ev
rows += APPEND
by = {r["frame_id"]: r for r in rows}

# ---- the totals this file is quoted with; a change that moves any of them fails here
J = sum(bool(r["in_jair"]) for r in rows); S = sum(bool(r["in_sadana"]) for r in rows)
title_both = sum(bool(r["in_jair"]) and bool(r["in_sadana"]) for r in rows)
assert (len(rows), J, S, title_both) == (313, 153, 191, 31), (len(rows), J, S, title_both)
works = {}
for r in rows:
    c = r["dup_of"] or r["frame_id"]
    assert not by[c]["dup_of"]
    w = works.setdefault(c, set())
    if r["in_jair"]: w.add("J")
    if r["in_sadana"]: w.add("S")
both = sum(w == {"J", "S"} for w in works.values())
assert (len(works), both) == (305, 38), (len(works), both)
jw = sum("J" in w for w in works.values()); sw = sum("S" in w for w in works.values())
assert (jw, sw) == (153, 190), (jw, sw)   # EJOR prints El Balghiti twice

cols = ["frame_id", "title", "year", "first_author", "in_jair", "in_sadana", "dup_of", "repair_note", "full_entry"]
with open(os.path.join(HERE, OUT), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)
print(f"{OUT}: {len(rows)} entries (JAIR {J}, EJOR {S}, title-matched in both {title_both}); "
      f"{len(works)} distinct works (JAIR {jw}, EJOR {sw}, both {both})")
