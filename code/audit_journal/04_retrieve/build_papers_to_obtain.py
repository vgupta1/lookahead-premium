#!/usr/bin/env python3
"""
build_papers_to_obtain.py -- the two screened halves of the candidate list -> papers_to_obtain.csv

One row per PAPER to obtain in full text. **No date in the name: this file is rewritten on every
run** and only its current state is meaningful. Inputs, all of them recorded decisions, never
edited here:

  02_screen/venue_papers_labels_merged_2026-09-16.csv   venue papers after the screen + VG's rulings
  01_search/venue_papers_no_abstracts_2026-09-21.csv    venue record keys, and the ONLY source of
                                                        which venue papers the surveys also cite
  02_screen/survey_refs_labels_merged_2026-09-22.csv    survey refs after the screen + VG's rulings
  01_search/survey_refs.csv                             the reference list itself (strings, dup_of)
  04_retrieve/doi_matches_<DATE>.csv                    DOIs verified against Scopus, if present

DEDUPLICATION. A work cited by a survey AND found by the venue search is ONE row carrying both ids.
The link is the `frame_id` column of venue_papers_no_abstracts (28 papers). Survey-side duplicates
were already collapsed by `dup_of`, so a work both surveys cite is one row too.

COLUMN NAMES follow the folder's two prefixes: `source` is venue_papers / survey_refs / both,
`venue_paper_id` is what 02_screen calls `sweep_id`, `survey_ref_id` is its `frame_id`, and
`survey_refs_bucket` records the survey screen's verdict on a row the venue screen kept.

THE ONE RULE THAT NEEDED A DECISION (VG, 2026-09-22). Two works VG ruled BACKGROUND on the survey
side were CANDIDATE on the venue side (SF0218/SW0240, SF0049/SW0370). They STAY IN: exclusions are
terminal only at full text, where Gates A and B are applied, and the two screens asked different
questions. `survey_refs_bucket` records the disagreement rather than hiding it.

EVERY ROW IS A PAPER TO OBTAIN, INCLUDING THE THREE ALREADY ON DISK (VG, 2026-09-25). `papers/` is
an arXiv store -- 29 of its 36 readable PDFs carry the arXiv stamp -- and exactly three files were
versions of record, two of them missing the appendix they cite. Tracking that was more machinery
than three papers are worth against 318 to fetch, so this list does not track it: if those three
come back down with everything else, nothing is lost but three downloads.

WHAT AN APPENDIX IS, settled 2026-09-25 and recorded on the corpus entry when a paper arrives, not
here: `appendix_referenced_in_main`, `appendix_held`, `appendix_source`, with the gap between them
derived rather than stored. A paper is obtained only when the version of record AND its appendix are
in hand.
"""
import csv, os, re, collections

SCREEN_DATE = "2026-09-22"          # the survey screen's labels; a dated input, not our output
DOI_DATE = "2026-09-22"             # the Scopus DOI lookups, if they have been run
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "..", "data", "audit_journal"))
OUT = "04_retrieve/papers_to_obtain.csv"

rd = lambda n: list(csv.DictReader(open(os.path.join(DATA, n), encoding="utf-8-sig")))
venue_labels = {r["sweep_id"]: r for r in rd("02_screen/venue_papers_labels_merged_2026-09-16.csv")}
venue_keys = {r["sweep_id"]: r for r in rd("01_search/venue_papers_no_abstracts_2026-09-21.csv")}
refs = {r["frame_id"]: r for r in rd("01_search/survey_refs.csv")}
ref_labels = {r["frame_id"]: r for r in rd(f"02_screen/survey_refs_labels_merged_{SCREEN_DATE}.csv")}
members = collections.defaultdict(list)
for f, r in refs.items():
    members[r["dup_of"] or f].append(r)

# DOIs verified against Scopus by merge_doi_lookups.py. Only `accepted` rows are used; `review`
# rows are VG's to rule on and stay blank here, so an unverified DOI can never reach a student.
doi_path = os.path.join(DATA, "04_retrieve", f"doi_matches_{DOI_DATE}.csv")
verified_doi = {}
if os.path.exists(doi_path):
    for r in csv.DictReader(open(doi_path, encoding="utf-8")):
        if r["decision"] == "accepted" and r["doi"].strip():
            verified_doi[r["survey_ref_id"]] = r["doi"].strip()

def surname(s):
    m = re.match(r"([A-Za-zÀ-ÿ'\-]+)", (s or "").split(",")[0].strip())
    return re.sub(r"[^A-Za-z]", "", m.group(1)) if m else "Unknown"

def best_title(rows):
    """Longest printed title: PDF extraction drops hyphens ('decisionmaking'), so the longest
    string is the least damaged one."""
    return max((r["title"] for r in rows), key=len)


rows, linked_refs = [], set()
for vid, lab in sorted(venue_labels.items()):
    if lab["final_bucket"] != "CANDIDATE":
        continue
    k = venue_keys[vid]
    rid = k["frame_id"]
    if rid:
        linked_refs.add(rid)
    rows.append(dict(
        source="both" if rid else "venue_papers", venue_paper_id=vid, survey_ref_id=rid,
        first_author=surname(k["authors"]), year=k["year"], venue=k["venue"],
        title=k["title"], doi=k["doi"], doi_source=("scopus_venue_search" if k["doi"] else ""),
        url=k["url"], eid=k["eid"],
        survey_refs_bucket=(ref_labels[rid]["final_bucket"] if rid else ""),
        reference="" if not rid else " ".join(members[rid][0]["full_entry"].split()),
        bibkey_prefix=f"{surname(k['authors'])}{k['year']}_"))

for rid, lab in sorted(ref_labels.items()):
    if lab["final_bucket"] != "CANDIDATE" or lab["canonical_id"] != rid or rid in linked_refs:
        continue
    m = members[rid]
    doi = verified_doi.get(rid, "")
    rows.append(dict(
        source="survey_refs", venue_paper_id="", survey_ref_id=rid,
        first_author=surname(m[0]["first_author"] + ","), year=m[0]["year"], venue="",
        title=best_title(m), doi=doi,
        doi_source=("scopus_title_lookup_verified" if doi else ""), url="", eid="",
        survey_refs_bucket="CANDIDATE",
        reference=" ".join(m[0]["full_entry"].split()),
        bibkey_prefix=f"{surname(m[0]['first_author'] + ',')}{m[0]['year']}_"))

blank = ["bibkey", "pdf_filename", "source_type", "version", "urldate", "appendixfile",
         "version_check", "notes"]
for r in rows:
    r.update({c: "" for c in blank})
cols = ["source", "venue_paper_id", "survey_ref_id", "first_author", "year", "venue", "title",
        "doi", "doi_source", "url", "eid", "survey_refs_bucket", "reference",
        "bibkey_prefix"] + blank
with open(os.path.join(DATA, OUT), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

C = collections.Counter(r["source"] for r in rows)
n_ref_cand = sum(1 for f, s in ref_labels.items()
                 if s["final_bucket"] == "CANDIDATE" and s["canonical_id"] == f)
assert C["venue_papers"] + C["both"] == 158, C
assert C["both"] + C["survey_refs"] == n_ref_cand + 2, (C, n_ref_cand)  # +2: kept under the rule above
print(f"{OUT}: {len(rows)} papers  {dict(C)}")
print(f"  carry a DOI              : {sum(1 for r in rows if r['doi'].strip())}"
      f"  (venue search {sum(1 for r in rows if r['doi_source'] == 'scopus_venue_search')}, "
      f"verified title lookup {sum(1 for r in rows if r['doi_source'] == 'scopus_title_lookup_verified')})")
print(f"  no DOI yet               : {sum(1 for r in rows if not r['doi'].strip())}")
print(f"  -> every one of the {len(rows)} is to be obtained: version of record plus appendix")
if not os.path.exists(doi_path):
    print(f"\n  note: {os.path.basename(doi_path)} not found -- run merge_doi_lookups.py to fill "
          "the survey-side DOIs")
