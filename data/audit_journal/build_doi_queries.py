#!/usr/bin/env python3
"""
build_doi_queries.py -- Scopus title queries for the audit-list rows that carry no DOI.

Only the seed-survey side needs this: sweep rows without a DOI have none in Scopus either (NeurIPS,
ICLR and PMLR papers frequently carry no DOI), so searching again cannot produce one.

Writes seed_doi_queries_<DATE>.txt: numbered blocks to paste into Scopus Advanced Search one at a
time. Titles are sanitised (punctuation stripped -- Scopus breaks on '+', and the seed strings carry
PDF-extraction artifacts) and truncated to the first TITLE_WORDS words, so a damaged tail cannot
sink an otherwise exact match.
"""
import csv, os, re

DATE = "2026-09-22"
HERE = os.path.dirname(os.path.abspath(__file__))
CHUNK, TITLE_WORDS = 25, 12

rows = [r for r in csv.DictReader(open(os.path.join(HERE, f"audit_list_{DATE}.csv"), encoding="utf-8"))
        if not r["doi"].strip() and r["source"] == "seed"]

def clean(t):
    t = re.sub(r"[^A-Za-z0-9 \-]", " ", t)
    return " ".join(t.split()[:TITLE_WORDS])

out = [f"Scopus title queries for DOI lookup -- {len(rows)} seed-frame papers, {DATE}",
       "",
       "Run each block in Scopus Advanced Search (Documents > Advanced document search).",
       "Export EVERY result of each search as CSV with 'Citation information' only",
       "(no abstracts, no keywords: they are not needed and carry licensing conditions).",
       f"Save the exports in this directory as scopus_doi_lookup_{DATE}_<block>.csv.",
       "Expect fewer hits than titles: preprints, theses, workshop papers and books are not indexed.",
       ""]
for i in range(0, len(rows), CHUNK):
    blk = rows[i:i + CHUNK]
    q = " OR ".join(f'TITLE("{clean(r["title"])}")' for r in blk)
    out += [f"--- block {i//CHUNK + 1} of {(len(rows)+CHUNK-1)//CHUNK}  "
            f"({blk[0]['frame_id']}-{blk[-1]['frame_id']}, {len(blk)} titles) ---", q, ""]
p = os.path.join(HERE, f"seed_doi_queries_{DATE}.txt")
open(p, "w", encoding="utf-8").write("\n".join(out) + "\n")
blocks = [(len(b) - 1) for b in [out]]
qlens = [len(l) for l in out if l.startswith("TITLE(")]
print(f"wrote {p}: {len(rows)} titles in {(len(rows)+CHUNK-1)//CHUNK} blocks; "
      f"longest query {max(qlens)} characters")
