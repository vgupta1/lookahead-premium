#!/usr/bin/env python3
"""
build_venue_sweep.py — journal-version literature audit, piece 1 (the frame).

Turns raw Scopus exports into the venue-sweep table, joins it to the seed frame,
and runs the search-recall validation.

    python3 build_venue_sweep.py            # writes venue_sweep_<DATE>.csv + validation_<DATE>.txt

INPUTS  (all in this directory)
  scopus_export_2026-09-16_v5.csv  THE export of record: one Scopus run, the query in
                                   journal_audit_protocol.md section 5A.3. Export fields must include
                                   Abstract, Source title, Conference name, DOI, Link,
                                   Document Type, EID, Author Keywords and Index Keywords.
  seed_frame_2026-09-21.csv        the 313 bibliography entries (305 distinct works) of the two seed
                                   surveys, keyed by frame_id; see repair_seed_frame.py.

  The query went through five revisions during development (journal_audit_protocol.md 5A.2). The export of
  record, v5, was verified to return exactly the union of all five -- 379 in-venue records, none
  missing, none new -- which is what makes a single run sufficient. The superseded exports are
  archived outside the repository and no code reads them.

OUTPUTS  (named by BUILD_DATE, not by the export date)
  venue_sweep_<BUILD_DATE>.csv       one row per paper at the eleven venues, 2023-2026 (gitignored:
                                     carries Scopus abstracts).
  venue_sweep_keys_<BUILD_DATE>.csv  the same rows without abstracts or keywords -- the shareable file.
  validation_<BUILD_DATE>.txt        the recall check against the 2023 overlap year.

  2026-09-21 rebuild: the seed-frame join matched on a space-preserving normalized title only, so
  five sweep records already in the frame carried no frame_id (hyphenation, a 'Technical Note--'
  prefix, an abbreviated title, a retitled arXiv entry, a workshop version), and the recall check,
  which used the same test, scored SF0133 a miss. Search recall on the 2023 year is 14/19, not 13/19.
  The join is now link_frame_id() below. Records, venues and sweep_ids are unchanged.

WHY THE VENUE FILTER IS LOCAL, NOT IN THE QUERY
  The Scopus query restricts SRCTITLE only loosely (see journal_audit_protocol.md 5A). Loose patterns
  such as SRCTITLE("Operations Research") also return *Annals of*, *Computers and*, and
  *Lecture Notes in* Operations Research, and SRCTITLE("Lecture Notes in Computer Science*")
  returns all of LNCS rather than CPAIOR alone. Deciding venue membership HERE, in code that is
  read and versioned, is reproducible; tightening the query instead would hide the decision
  inside a search box and risks silently dropping a venue whose source title varies by year.
"""

import csv, re, sys, glob, unicodedata, collections, datetime, os

csv.field_size_limit(10**9)
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "data", "audit_journal"))
DATE = "2026-09-16"          # date of the Scopus export of record
BUILD_DATE = "2026-09-21"    # date of this build; names the outputs
SEED_FRAME = "seed_frame_2026-09-21.csv"

# Irreducible seed<->sweep links: same work, titles that no normalization equates. Keyed on the
# Scopus EID so the link survives a title edit. Each needs a stated reason.
CROSSWALK = {
    "2-s2.0-85191167086": ("SF0133", "seed abbreviates 'Mixed Integer Linear Programs' as 'MILPs'"),
    "2-s2.0-85163285221": ("SF0064", "seed cites the AAAI-23 workshop version of this AAAI-23 paper "
                                     "(same five authors, retitled)"),
}

# ---------------------------------------------------------------- venue mapping
# Each rule is (label, field-to-test, regex). Scopus records the venue in TWO places and
# which one carries it differs by venue: journals use 'Source title', conferences often put
# the identifying string in 'Conference name' while 'Source title' holds the series.
#
# GOTCHAS encoded below - each one cost us a silent miss:
#   AAAI     'Proceedings of the 37th AAAI Conference on Artificial Intelligence, AAAI 2023'
#            for 2023, but the canonical 'Proceedings of the AAAI Conference on Artificial
#            Intelligence' for 2024-2026. An exact-phrase match returns ZERO AAAI 2023 papers.
#            Matched on a substring instead.
#   ICML /   Both publish through PMLR, so 'Source title' is 'Proceedings of Machine Learning
#   AISTATS  Research' for BOTH, as it is for UAI, CoRL, COLT, L4DC and others we do not want.
#            They are separable only via 'Conference name'.
#   ICLR     'Source title' is year-specific ('13th International Conference on Learning
#            Representations, ICLR 2025'), so it needs a substring match, not a phrase.
#   CPAIOR   Published in Springer LNCS, so 'Source title' is the LNCS series shared with dozens
#            of unrelated conferences. Identifiable only from 'Conference name'.
#   ICLR     The 'Tiny Papers' track appears under an ICLR source title but is a non-archival
#   Tiny     two-page track; excluded deliberately (set KEEP_ICLR_TINY to include it).
#   OR       'Operations Research' as a substring also matches *Annals of*, *Computers and*,
#            *Mathematics of*, *Operations Research Letters* and *Perspectives*. Exact only.
KEEP_ICLR_TINY = False

def venue(source_title, conference_name):
    s = (source_title or "").strip()
    c = (conference_name or "").strip()
    sc = s + " " + c
    if s == "Advances in Neural Information Processing Systems":            return "NeurIPS"
    if re.search(r"Conference on Machine Learning, ICML", c, re.I):          return "ICML"
    if re.search(r"Artificial Intelligence and Statistics, AISTATS", c, re.I): return "AISTATS"
    if re.search(r"Conference on Learning Representations", sc, re.I):
        if re.search(r"Tiny Papers", sc, re.I):
            return "ICLR-Tiny" if KEEP_ICLR_TINY else None
        return "ICLR"
    if re.search(r"AAAI Conference on Artificial Intelligence", s, re.I):    return "AAAI"
    if re.search(r"IJCAI", sc, re.I):                                        return "IJCAI"
    if re.search(r"Integration of Constraint Programming, Artificial Intelligence|CPAIOR",
                 sc, re.I):                                                  return "CPAIOR"
    return {"Operations Research": "OR",
            "Management Science": "MS",
            "Manufacturing and Service Operations Management": "MSOM",
            "INFORMS Journal on Computing": "IJOC"}.get(s)

YEARS = ("2023", "2024", "2025", "2026")   # window: 2023 - Sep 2026. Scopus also returns
                                           # 2027-dated online-first records; excluded here.

# ---------------------------------------------------------------- keyword record
# Recorded as a SEARCH RECORD, never as a screening decision (journal_audit_protocol.md 2.6).
# Note these do not reproduce Scopus exactly: Scopus TITLE-ABS-KEY also searches author and
# index KEYWORD fields, so a paper can be a legitimate hit with no phrase in title or abstract.
# Those rows are labelled rather than dropped - Scopus's match governs.
KEYWORDS = {
    "decision-focused learning":   r"decision[- ]focused learning",
    "predict-then-optimize":       r"predict\w*[- +,]{1,3}(then[- ]|and[- ])?optimi",
    "smart predict":               r"smart predict",
    "contextual optimization":     r"contextual (stochastic )?optimi[sz]ation",
    "integrated learning and optimization": r"integrated learning and optimi[sz]ation",
    "decision-aware learning":     r"decision[- ]aware learning",
    "task-based learning":         r"task[- ]based learning",
    "task loss":                   r"task loss",
    "differentiable optimization": r"differentiable optimi[sz]ation",
    "prescriptive analytics":      r"prescriptive analytics",
    "predictive to prescriptive":  r"predictive to prescriptive",
    "newsvendor (feature/data-driven)": r"(feature[- ]based|data[- ]driven) newsvendor",
    "end-to-end learning":         r"end[- ]to[- ]end learning",
    "optimization layers":         r"optimi[sz]ation layers?",
    "unrolled/folded solver":      r"unrolled solver|folded optimi[sz]ation",
    "differentiable combinatorial": r"differentiable (combinatorial|solver|algorithm|shortest path)",
    "implicit differentiation":    r"implicit differentiation",
    "data-driven optimization":    r"data[- ]driven optimi[sz]ation",
    "side/covariate information":  r"(side|covariate) information",
}

def norm(t):
    t = unicodedata.normalize("NFKD", t or "").lower()
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", t)).strip()

def key(t):
    """Join key for seed<->sweep matching: letters and digits only (PDF extraction drops hyphens,
    so 'datadriven' must equal 'data driven'), minus a leading 'Technical Note'."""
    k = re.sub(r"[^a-z0-9]", "", unicodedata.normalize("NFKD", t or "").lower())
    return k[len("technicalnote"):] if k.startswith("technicalnote") else k

def get(row, key):
    return (row.get(key) or "").strip()

# ---------------------------------------------------------------- load
RECORD_EXPORT = "scopus_export_2026-09-16_v5.csv"

def load_export():
    p = os.path.join(DATA, RECORD_EXPORT)
    if not os.path.exists(p):
        sys.exit(f"Scopus export of record not found:\n  {p}\n\n"
                 "It is deliberately not distributed with this repository (Elsevier's terms\n"
                 "restrict redistributing downloaded records). See README.md in this directory\n"
                 "for the query to run, the export fields required, and how to recover the exact\n"
                 "record set from the EIDs in venue_sweep_keys_2026-09-21.csv.")
    with open(p, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    required = ["Title", "Abstract", "Source title", "Conference name", "Year", "EID"]
    missing = [c for c in required if c not in rows[0]]
    if missing:
        sys.exit("export is missing required fields: " + ", ".join(missing))
    if "Index Keywords" not in rows[0]:
        print("WARNING: no Index Keywords column. Scopus TITLE-ABS-KEY matches keyword fields,\n"
              "         so some hits will not be explicable from title+abstract alone.\n")
    return rows, os.path.basename(p)

def main():
    rows, name = load_export()
    print(f"Scopus export of record: {name}  ({len(rows)} rows)\n")

    # seed frame, for the frame_id join and the validation
    seed = []
    sp = os.path.join(DATA, SEED_FRAME)
    if os.path.exists(sp):
        with open(sp, encoding="utf-8-sig", newline="") as f:
            seed = list(csv.DictReader(f))
    canon = {r["frame_id"]: (r.get("dup_of") or r["frame_id"]) for r in seed}
    seed_by_key = {}
    for r in seed:
        if key(r["title"]) and r["title"] != "Vol":
            seed_by_key.setdefault(key(r["title"]), canon[r["frame_id"]])

    def link_frame_id(r):
        """Canonical frame_id of a sweep record, or ''. Returns (frame_id, method)."""
        if get(r, "EID") in CROSSWALK:
            return canon[CROSSWALK[get(r, "EID")][0]], "crosswalk"
        fid = seed_by_key.get(key(get(r, "Title")), "")
        return fid, ("title" if fid else "")

    keep = []
    for r in rows:
        v = venue(get(r, "Source title"), get(r, "Conference name"))
        if v and get(r, "Year") in YEARS:
            keep.append((v, r))
    keep.sort(key=lambda vr: (vr[0], get(vr[1], "Year"), norm(get(vr[1], "Title"))))

    out = []
    for i, (v, r) in enumerate(keep, 1):
        blob = (get(r, "Title") + " " + get(r, "Abstract")).lower()
        hits = [k for k, p in KEYWORDS.items() if re.search(p, blob)]
        out.append(dict(
            sweep_id=f"SW{i:04d}", venue=v, year=get(r, "Year"), title=get(r, "Title"),
            authors=get(r, "Authors"), abstract=get(r, "Abstract"), url=get(r, "Link"),
            doi=get(r, "DOI"),
            matched_keywords=";".join(hits) or "(scopus keyword-field match only)",
            frame_id=link_frame_id(r)[0], frame_link=link_frame_id(r)[1],
            author_keywords=get(r, "Author Keywords"), index_keywords=get(r, "Index Keywords"),
            source_title=get(r, "Source title"), conference_name=get(r, "Conference name"),
            doc_type=get(r, "Document Type"), eid=get(r, "EID")))

    outp = os.path.join(DATA, f"venue_sweep_{BUILD_DATE}.csv")
    cols = ["sweep_id","venue","year","title","authors","abstract","url","doi",
            "matched_keywords","frame_id","frame_link","author_keywords","index_keywords",
            "source_title","conference_name","doc_type","eid"]
    with open(outp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(out)
    kp = os.path.join(DATA, f"venue_sweep_keys_{BUILD_DATE}.csv")
    kcols = ["sweep_id","venue","year","title","authors","doi","url","frame_id","frame_link",
             "source_title","conference_name","doc_type","eid"]
    with open(kp, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=kcols, extrasaction="ignore"); w.writeheader(); w.writerows(out)
    linked = [o["frame_id"] for o in out if o["frame_id"]]
    assert len(linked) == len(set(linked)), "two sweep records linked to one seed work"

    vy = collections.Counter((o["venue"], o["year"]) for o in out)
    print("Papers at the eleven venues, 2023-2026:\n")
    print("  venue        2023 2024 2025 2026  tot")
    for v in sorted({o["venue"] for o in out}):
        c = [vy[(v, y)] for y in YEARS]
        print(f"  {v:<12}{c[0]:5d}{c[1]:5d}{c[2]:5d}{c[3]:5d}{sum(c):5d}")
    print(f"  {'TOTAL':<12}{'':20}{len(out):5d}")
    print(f"\n  already in the seed frame: {sum(1 for o in out if o['frame_id'])}"
          f"  -> new from the sweep: {sum(1 for o in out if not o['frame_id'])}")
    print(f"  keyword-field-only matches (not reproducible from title+abstract): "
          f"{sum(1 for o in out if o['matched_keywords'].startswith('(scopus'))}")
    print(f"\nwrote {outp}")

    # ------------------------------------------------------------ validation
    # The overlap year exists for this: 2023 is covered BOTH by the seed surveys and by the
    # sweep, so the surveys supply a known answer the sweep can be scored against. This
    # measures SEARCH RECALL. It is not a measure of the corpus: every paper counted as a
    # miss below is already in the frame via the seed surveys.
    VPAT = [("NeurIPS", r"Neural Information Processing Systems"),
            ("ICML", r"International Conference on Machine Learning"),
            ("ICLR", r"International Conference on Learning Representations|ICLR"),
            ("AAAI", r"\bAAAI\b"), ("IJCAI", r"\bIJCAI\b"),
            ("AISTATS", r"Artificial Intelligence and Statistics|AISTATS"),
            ("CPAIOR", r"CPAIOR|Integration of Constraint Programming"),
            ("OR", r"(?<!of )(?<!and )(?<!European Journal of )Operations Research\b(?! Letters| Perspectives)"),
            ("MS", r"\bManagement Science\b"),
            ("MSOM", r"Manufacturing (and|&) Service Operations Management"),
            ("IJOC", r"INFORMS Journal on Computing")]
    # Scored per WORK, not per bibliography entry: a paper both surveys cite counts once, under
    # its canonical frame_id. A work counts as FOUND iff some sweep record links to it.
    found = {o["frame_id"] for o in out if o["frame_id"]}
    lines, tot, rec, seen = [], 0, 0, set()
    for r in seed:
        if r.get("year") != "2023" or canon[r["frame_id"]] in seen:
            continue
        v = next((n for n, p in VPAT if re.search(p, r.get("full_entry", ""))), None)
        if not v:
            continue
        seen.add(canon[r["frame_id"]])
        tot += 1
        ok = canon[r["frame_id"]] in found
        rec += ok
        lines.append(f"  {r['frame_id']}  {v:<8} {'FOUND  ' if ok else 'MISSED '} {r['title'][:80]}")
    report = ([f"Search-recall validation, build {BUILD_DATE} (Scopus export of {DATE})",
               "Scored against 2023 seed-survey entries published at the eleven venues.",
               "A MISS is a search-recall failure, NOT a gap in the corpus: these papers are",
               "already in the frame via the seed surveys.", "",
               f"known 2023 papers at the eleven venues : {tot}",
               f"recovered by the sweep                 : {rec}  ({rec/tot:.0%})" if tot else "",
               f"missed                                 : {tot-rec}", ""] + lines)
    vp = os.path.join(DATA, f"validation_{BUILD_DATE}.txt")
    open(vp, "w", encoding="utf-8").write("\n".join(report) + "\n")
    print("\n" + "\n".join(report))
    print(f"\nwrote {vp}")

if __name__ == "__main__":
    main()
