#!/usr/bin/env python3
"""
merge_doi_lookups.py -- Scopus title-search exports -> doi_matches_<DATE>.csv

The survey references print no DOI, so the survey-side rows of `papers_to_obtain.csv` arrive without
one. `build_doi_lookup_queries.py` writes title queries; VG runs them in Scopus and saves the
exports as `04_retrieve/scopus_doi_lookup_<DATE>_{1..N}.csv` (gitignored, like every raw Scopus
download). This script matches those records back to our rows.

    python3 merge_doi_lookups.py            # writes doi_matches_<DATE>.csv, prints what needs review

MATCHING IS A VERIFICATION, NOT A LOOKUP (journal_audit_protocol.md section 5). A DOI is accepted
only when first-author surname, publication year and normalised title all agree, and the evidence
for the match is stored beside it -- the Scopus title, year, source and EID -- so a wrong DOI is
visible in the file rather than buried in a script. Everything else goes to `review`, never to
silent acceptance, because a wrong DOI sends a student to the wrong paper.

DECISIONS
  accepted  title similarity >= AUTO and the first author's surname agrees. **The year is recorded,
            not required** (VG, 2026-09-25, amending the +/-1 rule in journal_audit_protocol.md
            section 5). A ten-word title matching exactly, same first author, is already decisive,
            and the drift the old rule flagged pointed the right way: eight of the nine rows it sent
            to review were a preprint whose published version Scopus dates two to four years later,
            which is the version of record we want. `year_delta` carries the drift as evidence.
  review    similarity in [MANUAL, AUTO), a short title two papers could share, a surname that does
            not agree, or two different Scopus records matching equally well
  none      nothing scored above MANUAL: no Scopus record, which is expected for preprints,
            theses, workshop papers and books

The output is dated because it records one set of lookups run on one day. `papers_to_obtain.csv`
reads only the `accepted` rows.
"""
import csv, os, re, glob, difflib, unicodedata, collections

DATE = "2026-09-22"
AUTO, MANUAL = 0.93, 0.80
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "..", "data", "audit_journal"))
LIST = os.path.join(DATA, "04_retrieve", "papers_to_obtain.csv")
OUT = os.path.join(DATA, "04_retrieve", f"doi_matches_{DATE}.csv")


def norm(t):
    return re.sub(r"[^a-z0-9]", "", (t or "").lower())


def surname(s):
    """The first author's surname: accents folded, initials and punctuation removed. Compound
    surnames print inconsistently -- 'Bazier-Matte' is 'Matte' in Scopus, 'El Balghiti' loses its
    article, 'Rolinek' keeps its accent in one list and not the other -- so the comparison below is
    containment either way, not equality."""
    # Scopus separates authors with ";" and prints "Surname I.I."; our reference strings separate
    # with "," and print "Surname, I." Take the first author either way, then drop the initials.
    head = (s or "").split(";")[0].split(",")[0].strip()
    head = unicodedata.normalize("NFKD", head).encode("ascii", "ignore").decode()
    words = [w for w in head.split() if len(w.rstrip(".")) > 1 or not w.endswith(".")]
    return re.sub(r"[^A-Za-z]", "", " ".join(words)).lower()


def same_person(a, b):
    """Surnames printed by two different systems agree far less often than they should. Beyond
    compound names, the survey bibliographies were extracted from PDFs where accented letters lost
    their base character ("Esteban-P\u00e9rez" -> "EstebanPrez", "Mu\u00f1oz" -> "Muoz"), so an equality
    test rejects real matches. Three tolerant tests, any of which is enough:"""
    if not a or not b:
        return False
    if a == b or a.endswith(b) or b.endswith(a) or a.startswith(b) or b.startswith(a):
        return True                                   # compound name, or one list drops a particle
    m = difflib.SequenceMatcher(None, a, b).find_longest_match(0, len(a), 0, len(b))
    if m.size >= 5:
        return True                                   # a long shared run: "matte" in "bazier-matte"
    return difflib.SequenceMatcher(None, a, b).ratio() >= 0.6   # dropped letters from an accent


# Every survey-side row, including any whose DOI an earlier run of THIS script already filled in:
# skipping those would leave the evidence file covering only part of the list, and the file is the
# record. Rows whose DOI came with the venue search need no lookup.
rows = [r for r in csv.DictReader(open(LIST, encoding="utf-8"))
        if r["source"] == "survey_refs" and r["doi_source"] != "scopus_venue_search"]

exports = sorted(glob.glob(os.path.join(DATA, "04_retrieve", f"scopus_doi_lookup_{DATE}_*.csv")))
if not exports:
    raise SystemExit(f"no scopus_doi_lookup_{DATE}_*.csv in 04_retrieve/ -- run the queries in "
                     f"doi_lookup_queries_{DATE}.txt first")
scopus, by_eid = [], {}
for p in exports:
    for s in csv.DictReader(open(p, encoding="utf-8-sig")):
        s["_file"] = os.path.basename(p)
        # The query blocks overlap, so the same record comes back in more than one export. Keep the
        # first copy; a duplicate EID is the same Scopus record, not a second candidate paper.
        eid = (s.get("EID") or "").strip()
        if eid and eid in by_eid:
            continue
        by_eid[eid] = s
        scopus.append(s)

out = []
for r in rows:
    a, want = norm(r["title"]), surname(r["first_author"] + ",")
    # Sort by title score, then prefer a record that carries a DOI: Scopus often holds both a
    # conference record and its journal version, identical in title, only one with a DOI.
    scored = sorted(((difflib.SequenceMatcher(None, a, norm(s["Title"])).ratio(), s)
                     for s in scopus),
                    key=lambda x: (-x[0], 0 if (x[1].get("DOI") or "").strip() else 1))
    best, s = scored[0] if scored else (0.0, None)
    runner = scored[1][0] if len(scored) > 1 else 0.0
    if s is None or best < MANUAL:
        out.append(dict(survey_ref_id=r["survey_ref_id"], decision="none", title_score=round(best, 3),
                        our_title=r["title"], our_year=r["year"], our_first_author=r["first_author"],
                        doi="", scopus_title="", scopus_year="", scopus_source="", scopus_eid="",
                        year_delta="", surname_match="", export_file="",
                        why="no Scopus record scored above the manual-review threshold"))
        continue
    sn = surname(s["Authors"])
    delta = abs(int(r["year"]) - int(s["Year"])) if (r["year"].isdigit() and s["Year"].isdigit()) else ""
    ok_name = same_person(sn, want)
    # A tie only matters if the two records are actually different papers: same title, same DOI (or
    # the runner-up has none) is one record seen twice.
    tie = (best - runner) <= 0.02 and len(scored) > 1 and \
        (scored[1][1].get("DOI") or "").strip() not in ("", (s.get("DOI") or "").strip())
    # A 10-word title matching exactly is already strong evidence; the surname test is there for
    # short, generic titles, where two different papers can share one.
    long_title = len(r["title"].split()) >= 6
    # A long title matching exactly, with the same first author, is decisive on its own, so the
    # year is recorded rather than required. A SHORT title is weak evidence -- two papers can share
    # "Differentiable linearized ADMM" -- so there the year still has to agree.
    if best >= AUTO and ok_name and not tie and (long_title or (delta != "" and delta <= 1)):
        d = "accepted"
        why = ("title and surname agree" if delta in ("", 0) or (delta != "" and delta <= 1) else
               f"title and surname agree; the year moved {delta} ({r['year']} -> {s['Year']}), "
               "which is a preprint reaching publication -- the version we want")
    elif best >= AUTO and not ok_name:
        d, why = "review", f"title agrees but the first author differs ({sn or 'none'} vs {want})"
    elif best >= AUTO and not long_title:
        d, why = "review", ("title matches but is short enough that two papers could share it, and "
                            f"the year moved {delta or 'to an unknown value'}")
    elif best >= AUTO and tie:
        d, why = "review", "two different Scopus records match this title equally well"
    else:
        d, why = "review", "title similarity is below the automatic threshold"
    out.append(dict(survey_ref_id=r["survey_ref_id"], decision=d, title_score=round(best, 3),
                    our_title=r["title"], our_year=r["year"], our_first_author=r["first_author"],
                    doi=(s.get("DOI") or "").strip(), scopus_title=s["Title"], scopus_year=s["Year"],
                    scopus_source=s.get("Source title", ""), scopus_eid=s.get("EID", ""),
                    year_delta=delta, surname_match="yes" if ok_name else "no",
                    export_file=s["_file"], why=why))

# A DOI that lands on two different papers is a data error, not a judgement call.
dup = [d for d, n in collections.Counter(o["doi"] for o in out
                                         if o["decision"] == "accepted" and o["doi"]).items() if n > 1]
assert not dup, f"the same DOI was accepted for more than one row: {dup}"

for o in out:
    if o["decision"] == "accepted" and not o["doi"]:
        o["decision"], o["why"] = "none", "matched a Scopus record that carries no DOI"

with open(OUT, "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=list(out[0].keys())); w.writeheader(); w.writerows(out)

# VG's rulings on the review rows live in their own file, on the pattern 02_screen uses: the
# machine's output is rewritten on every run and never edited, the rulings are written once by hand.
# Created only if absent, so re-running this script cannot overwrite decisions already made.
RULINGS = os.path.join(DATA, "04_retrieve", f"doi_matches_vg_rulings_{DATE}.csv")
review = [o for o in out if o["decision"] == "review"]
if review and not os.path.exists(RULINGS):
    with open(RULINGS, "w", newline="", encoding="utf-8") as f:
        cols = ["survey_ref_id", "vg_ruling", "vg_doi", "vg_note", "why", "title_score",
                "our_title", "our_year", "our_first_author", "proposed_doi", "scopus_title",
                "scopus_year", "scopus_source"]
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for o in review:
            w.writerow({"survey_ref_id": o["survey_ref_id"], "vg_ruling": "", "vg_doi": "",
                        "vg_note": "", "why": o["why"], "title_score": o["title_score"],
                        "our_title": o["our_title"], "our_year": o["our_year"],
                        "our_first_author": o["our_first_author"], "proposed_doi": o["doi"],
                        "scopus_title": o["scopus_title"], "scopus_year": o["scopus_year"],
                        "scopus_source": o["scopus_source"]})
    print(f"wrote {os.path.basename(RULINGS)} -- fill vg_ruling with accept / reject "
          "(or put a different DOI in vg_doi)")
elif review:
    print(f"{os.path.basename(RULINGS)} already exists; left untouched")

C = collections.Counter(o["decision"] for o in out)
print(f"{os.path.relpath(OUT, DATA)}: {len(out)} survey-side rows needing a lookup, "
      f"{len(scopus)} Scopus records from {len(exports)} exports")
print(f"  accepted : {C['accepted']}")
print(f"  review   : {C['review']}")
print(f"  none     : {C['none']}")
if C["review"]:
    print("\nfor VG, in the order they appear in the file:")
    for o in out:
        if o["decision"] == "review":
            print(f"  {o['survey_ref_id']}  score {o['title_score']}  {o['why']}")
            print(f"      ours  : {o['our_title'][:78]} ({o['our_year']})")
            print(f"      scopus: {o['scopus_title'][:78]} ({o['scopus_year']}) {o['doi']}")
