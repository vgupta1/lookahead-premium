# Journal-version literature audit — the frame

Piece 1 of the journal version: the sampling frame and the stage-1 screen. The protocol this
implements is `search_protocol.md` (Dropbox folder root, outside this repository).

**This directory is the *new* audit. Nothing in `../` is touched.** The workshop-version audit
(`../audit.csv`, `../evidence.csv`, `../SCHEMA.md`, `../RUBRIC.md`,
`../../code/literature_audit.py`) must remain byte-identical so the published workshop results stay
reproducible. Read from those files; never edit them.

---

## What is not in this repository, and why

**The raw Scopus exports are not distributed here.** Elsevier's terms restrict redistribution of
downloaded records, and the abstracts in them are publisher copyright. What is committed instead is
`venue_sweep_keys_2026-09-16.csv`: every record's Scopus **EID**, DOI where one exists, title,
authors, venue and year, plus our own `sweep_id` and `frame_id`. Anyone with Scopus access can
recover the exact record set from the EIDs, or re-run the query below and compare.

Two deliberate exceptions, both small and both necessary to check the method rather than to
redistribute a database:

- `triage_control_abstracts.json` holds the abstracts of **twelve** papers, quoted so that the
  control set is reproducible. Without them, the one validation that matters cannot be re-run.
- `triage_<DATE>.csv` records our own classifications and rationales. That is our output, not
  Elsevier's.

Also absent: the superseded query-development exports (v1–v4). They are archived outside the
repository, and no code reads them — `build_venue_sweep.py` opens one named file.

---

## Reproducing the frame

**1. Obtain the Scopus export.** In Scopus Advanced Search, run the query in
`search_protocol.md` §5A.3 verbatim. It returned 829 records on 2026-09-16; a later run will return
more, since the venues keep publishing. Export to CSV including **Abstract, Source title, Conference
name, DOI, Link, Document Type, EID, Author Keywords** and **Index Keywords**, and save it in this
directory as

    scopus_export_2026-09-16_v5.csv

To reproduce our result exactly rather than refresh it, filter the export to the EIDs in
`venue_sweep_keys_2026-09-16.csv` before proceeding.

**2. Build the sweep table.**

    python3 build_venue_sweep.py

Reads that one export, assigns venues, applies the 2023–2026 window, joins `frame_id` from
`seed_frame_2026-09-10.csv`, and writes `venue_sweep_<DATE>.csv` (379 rows) plus
`validation_<DATE>.txt`, the search-recall check against the 2023 overlap year (13/19).

The venue assignment is done here in code rather than in the Scopus query, deliberately: the
`SRCTITLE` clauses are loose, and several venues need the `Conference name` field to be identified
at all. `search_protocol.md` §5A.5 lists the eight indexing quirks encoded in the mapping — AAAI
2023's ordinal source title and ICML/AISTATS sharing one PMLR title are the two that silently drop
whole venue-years if you get them wrong.

**3. Run the triage screen.**

    export ANTHROPIC_API_KEY=...
    python3 triage_screen.py --validate     # 12 calls; must print 12/12
    python3 triage_screen.py --run          # ~379 calls, roughly $2

`--run` re-runs the control set first and aborts if it fails. Output is `triage_<DATE>.csv` with a
bucket, the model's own one-sentence rationale, a confidence, the model id, a prompt hash and the run
date for every record.

**On determinism.** Decoding is greedy (`temperature=0`), which sharply reduces run-to-run variation
but does not eliminate it: floating-point non-determinism and provider-side model revisions can move
a borderline record. This is why the prompt hash and model id are stored per row, and why the control
set runs on every execution. Expect near-identical, not bit-identical, output.

---

## Files

| File | What it is |
|---|---|
| `build_venue_sweep.py` | Export → sweep table, plus the search-recall validation |
| `triage_screen.py` | Stage-1 topic triage; the prompt *is* the method and lives in this file |
| `triage_control_abstracts.json` | 12-paper labelled positive control, abstracts verbatim |
| `seed_frame_2026-09-10.csv` | 311 references of the two seed surveys, keyed by `frame_id` |
| `venue_sweep_keys_2026-09-16.csv` | Shareable record keys for the 379 (no abstracts) |
| `venue_sweep_2026-09-16.csv` | Full sweep table *with* abstracts — **gitignored**, local only |
| `scopus_export_2026-09-16_v5.csv` | Raw export — **gitignored**, local only |
| `validation_2026-09-16.txt` | Search-recall check: 13 of 19 known 2023 papers recovered |
| `triage_validation.txt` | Control-set result |
| `ec_triage_draft.tex` | Draft of the e-companion section describing this stage |

---

## What this stage does not decide

Triage is a retrieval decision: which full texts to obtain. Gates A and B
(`search_protocol.md` §2.7) and the four inclusion rules are answered from full text, never from
abstracts. An earlier design screened Gate A from abstracts and wrongly excluded 4 of the 12 control
papers, because machine-learning abstracts describe the method and leave the setting to the
experiments. The prompt now carries two rules whose only purpose is to prevent that failure from
recurring.
