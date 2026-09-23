#!/usr/bin/env python3
"""
build_audit_list.py -- the two screened halves of the frame -> audit_list_<DATE>.csv

One row per PAPER to obtain in full text. Inputs, all of them screening outputs, never edited here:

  triage_final_2026-09-16.csv     venue sweep after triage + adjudications (CANDIDATE = 158)
  venue_sweep_keys_2026-09-21.csv sweep record keys, incl. the corrected frame_id links
  seed_screen_final_2026-09-22.csv seed references after the coarse screen + VG's rulings
  seed_frame_2026-09-21.csv       the frame itself (reference strings, dup_of)

DEDUPLICATION. A paper cited by a seed survey AND found by the sweep is ONE row, carrying both keys.
The link is the corrected frame_id join (28 sweep records). Seed-side duplicates were already
collapsed by `dup_of`, so a work cited by both surveys is one row too.

THE ONE RULE THAT NEEDED A DECISION (VG, 2026-09-22). Two works VG ruled BACKGROUND on the seed side
were CANDIDATE on the sweep side (SF0218/SW0240, SF0049/SW0370). They STAY IN: exclusions are
terminal only at full text, where Gates A and B are applied, and the two screens asked different
questions. `seed_bucket` records the disagreement rather than hiding it.

Rows are not PDFs-to-chase where we already hold the version of record; `have_official` marks those.
"""
import csv, os, re, collections

DATE = "2026-09-22"
HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.normpath(os.path.join(HERE, "..", "..", "data", "audit_journal"))
OUT = f"audit_list_{DATE}.csv"

# Files in papers/ verified 2026-09-22 to be the version of record (no arXiv stamp, publisher
# furniture present). Everything else in papers/ is an arXiv copy and must be re-obtained.
HAVE_OFFICIAL = {"SF0171": "LiuGrigas2021_RiskBoundsSPO.pdf",        # NeurIPS proceedings
                 "SF0184": "Mandi2022_LearningToRank.pdf"}           # PMLR
HAVE_OFFICIAL_SWEEP = {"SW0219": "Schutte2024_RobustLosses.pdf"}     # IJCAI proceedings

# Titles the 2026-09-10 bibliography parse cut short, read back off the printed reference string.
# The frame itself is NOT edited: it records the parse, and this is a downstream repair. The checks
# in check_titles() below are what found these two; anything they flag must be added here, so a
# damaged title can no longer reach a DOI search or a pull list silently.
TITLE_FIX = {
    "SF0033": "Quality vs. Quantity of data in contextual decision-making: Exact analysis under "
              "newsvendor loss",                      # parse stopped at the abbreviation "vs."
    "SF0054": "End-to-end Conditional Robust Optimization",   # entry prints "2024." with no
                                                              # parentheses, so the parser took the
                                                              # author list as the title
}


def check_titles(fid, title, entry):
    """Two cheap tests for a truncated title: it must appear in the reference string AFTER the year,
    and it must not end on an abbreviation that a sentence splitter would have stopped at."""
    if fid in TITLE_FIX:
        return TITLE_FIX[fid]
    flat = " ".join(entry.split())
    m = re.search(r"\(?(19|20)\d\d[a-z]?\)?\.?", flat)
    after = flat[m.end():] if m else flat
    bad_tail = title.split()[-1].rstrip(".").lower() in {"vs", "e.g", "i.e", "vol", "no", "eds", "ed"}
    if title[:25] not in after or bad_tail:
        raise SystemExit(f"{fid}: title looks truncated -- {title!r}\n  entry: {flat[:160]}\n"
                         "  add the printed title to TITLE_FIX with a one-line reason.")
    return title

rd = lambda n: list(csv.DictReader(open(os.path.join(DATA, n), encoding="utf-8-sig")))
tri = {r["sweep_id"]: r for r in rd("triage_final_2026-09-16.csv")}
keys = {r["sweep_id"]: r for r in rd("venue_sweep_keys_2026-09-21.csv")}
seedf = {r["frame_id"]: r for r in rd("seed_frame_2026-09-21.csv")}
seed = {r["frame_id"]: r for r in rd(f"seed_screen_final_{DATE}.csv")}
members = collections.defaultdict(list)
for f, r in seedf.items():
    members[r["dup_of"] or f].append(r)

def surname(s):
    m = re.match(r"([A-Za-zÀ-ÿ'\-]+)", (s or "").split(",")[0].strip())
    return re.sub(r"[^A-Za-z]", "", m.group(1)) if m else "Unknown"

def best_title(rows):
    """Longest printed title: PDF extraction drops hyphens ('decisionmaking'), so the longest
    string is the least damaged one."""
    return max((r["title"] for r in rows), key=len)


def seed_title(fid, rows):
    """Check the chosen title against the entry it was parsed from, not an arbitrary member: when a
    work is cited by both surveys the two strings differ (that is why the longest wins)."""
    t = best_title(rows)
    src = next(r for r in rows if r["title"] == t)
    return check_titles(fid, t, src["full_entry"])

rows, seen_frames = [], set()
for sid, t in sorted(tri.items()):
    if t["final_bucket"] != "CANDIDATE":
        continue
    k = keys[sid]
    fid = k["frame_id"]
    if fid:
        seen_frames.add(fid)
    rows.append(dict(
        source="both" if fid else "sweep", sweep_id=sid, frame_id=fid,
        first_author=surname(k["authors"]), year=k["year"], venue=k["venue"],
        title=k["title"], doi=k["doi"], url=k["url"], eid=k["eid"],
        seed_bucket=(seed[fid]["final_bucket"] if fid else ""),
        reference="" if not fid else " ".join(members[fid][0]["full_entry"].split()),
        have_official=HAVE_OFFICIAL_SWEEP.get(sid, HAVE_OFFICIAL.get(fid, "")),
        bibkey_prefix=f"{surname(k['authors'])}{k['year']}_"))

for fid, s in sorted(seed.items()):
    if s["final_bucket"] != "CANDIDATE" or s["canonical_id"] != fid or fid in seen_frames:
        continue
    m = members[fid]
    rows.append(dict(
        source="seed", sweep_id="", frame_id=fid,
        first_author=surname(m[0]["first_author"] + ","), year=m[0]["year"], venue="",
        title=seed_title(fid, m), doi="", url="", eid="", seed_bucket="CANDIDATE",
        reference=" ".join(m[0]["full_entry"].split()),
        have_official=HAVE_OFFICIAL.get(fid, ""),
        bibkey_prefix=f"{surname(m[0]['first_author'] + ',')}{m[0]['year']}_"))

blank = ["bibkey", "pdf_filename", "source_type", "version", "urldate", "appendix",
         "appendixfile", "version_check", "notes"]
for r in rows:
    r.update({c: "" for c in blank})
cols = ["source", "sweep_id", "frame_id", "first_author", "year", "venue", "title", "doi", "url",
        "eid", "seed_bucket", "have_official", "reference", "bibkey_prefix"] + blank
with open(os.path.join(DATA, OUT), "w", newline="", encoding="utf-8") as f:
    w = csv.DictWriter(f, fieldnames=cols); w.writeheader(); w.writerows(rows)

C = collections.Counter(r["source"] for r in rows)
n_seed_cand = sum(1 for f, s in seed.items() if s["final_bucket"] == "CANDIDATE" and s["canonical_id"] == f)
assert C["sweep"] + C["both"] == 158, C
assert C["both"] + C["seed"] == n_seed_cand + 2, (C, n_seed_cand)   # +2: the two kept under the rule above
print(f"{OUT}: {len(rows)} papers  {dict(C)}")
print(f"  carry a DOI            : {sum(1 for r in rows if r['doi'].strip())}")
print(f"  need a DOI lookup      : {sum(1 for r in rows if not r['doi'].strip())}")
print(f"  already held, official : {sum(1 for r in rows if r['have_official'])}")
print(f"  -> to obtain           : {sum(1 for r in rows if not r['have_official'])}")
