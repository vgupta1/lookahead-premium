# The journal audit's data

One folder per step of the pipeline. The scripts live under `code/audit_journal/` in folders with
the same names, and each resolves this directory from its own location, so they run from anywhere.
The protocol they implement is `notes/journal_audit_protocol.md`, in the project folder outside this
repository.

**This is the *new* audit. Nothing in `../audit_workshop/` is touched** — those files back the
published workshop paper and must stay byte-identical, which the tag `workshop-submission`
guarantees.

    01_search/            where the candidate papers came from
    02_screen/            deciding which ones to read in full
    03_screen_accuracy/   evidence that the screen did not throw away what it should have kept
    04_retrieve/          the list of papers to obtain
    05_fulltext_review/   (empty) the inclusion gates and extraction, still to be built

## 01_search

Two independent sources of candidates.

| File | What it is |
|---|---|
| `survey_refs.csv` | **An input, not an output.** The 313 references printed in the two survey bibliographies (Mandi JAIR 2024, Sadana EJOR 2025) — 305 distinct works, 38 cited by both. Keyed by `frame_id` (`SF0001`–`SF0313`). |
| `scopus_export_2026-09-16.csv` | The Scopus search result of record. **Gitignored** — Elsevier restricts redistribution. |
| `venue_papers_with_abstracts_<DATE>.csv` | 379 papers at the eleven venues, 2023–2026. **Gitignored**: carries Scopus abstracts. |
| `venue_papers_no_abstracts_<DATE>.csv` | The same rows with the abstracts and keywords stripped — the shareable copy, and **the one source of truth for which papers the surveys already cite**. |
| `known_2023_papers_found.txt` | Of the 19 works the surveys cite that were published at these venues in 2023, how many the Scopus search returned: **14**. One line per paper, FOUND or MISSED. Rewritten on every build, so it carries no date. |

**`survey_refs.csv` cannot be regenerated from this repository.** It was extracted from the two
survey PDFs outside it, and that extractor was not kept. Ten rows were corrected afterwards — two
references restored that a parser had swallowed, eight marked as the same work cited twice — and
every one of those corrections is recorded in the file's own `dup_of` and `repair_note` columns.
Treat it the way you would treat data someone else published: an input you check, not a product you
rebuild.

## 02_screen

The screens are deliberately different, because the two sources carry different information.

- **Sweep records** are screened on **title and abstract**, by an LLM under a fixed prompt (the
  prompt *is* the method), pinned model, temperature 0, three runs with a majority vote.
- **Survey references** are screened on **the reference string alone** — a bibliography carries no
  abstract — into CANDIDATE / BORDERLINE / BACKGROUND, deliberately coarse.

Each screen produces three files, and the split is what keeps human judgement visible:

| Suffix | What it is |
|---|---|
| `_llm_labels_` | the machine's output, **never edited** — with a reason, a confidence, the prompt hash and the model id per record |
| `_vg_rulings_` | VG's decisions: on the sweep, the 4 records where the three runs split; on the surveys, a verdict on **all 127** non-candidates |
| `_labels_final_` | the two merged by a script — what everything downstream reads |

Results: sweep **158 CANDIDATE / 221 OUT**; surveys **186 candidates / 117 background** of 305 works.
`_cache/` holds the raw per-call model votes so a crashed run resumes without paying twice. **Gitignored:** every record's three votes and the majority reason are already in the committed labels, so the cache is plumbing, not evidence.

**The two sides use different column names for the same things.** Not worth rewriting data that has
already been ruled on, so here is the translation:

| Means | Venue sweep | Survey references |
|---|---|---|
| the record's id | `sweep_id` | `frame_id` |
| the machine's label | `run_bucket` | `machine_bucket` |
| VG's label | `vg_bucket` | `vg_ruling` |
| VG's comment | `note` | `vg_note` |
| the merged answer | `final_bucket` | `final_bucket` |

`final_bucket` is the one both sides agree on, which is why everything downstream reads only that.

## 03_screen_accuracy

None of this decides anything about a paper. It measures how often a screen was wrong to exclude.

**Two audits, two designs.** The venue side was audited on a **random sample** — 50 of the 221
excluded records, relabelled by VG with the machine's answers withheld: **0 misses**, so at most
**11 of 221** were wrongly excluded (95%, one-sided, hypergeometric). The survey side was audited
**exhaustively** — VG ruled on all 127 non-candidates, and none of the 85 background calls was
overturned, so no interval is needed. Those rulings live with the screen, in
`02_screen/survey_refs_vg_rulings_2026-09-22.csv`.

| File | What it shows |
|---|---|
| `venue_control_known_papers.json` | The twelve papers the control set is built from: title, abstract, and the answer each must get. A fixture, not a result. |
| `venue_control_result.txt`, `survey_control_result.txt` | The control sets passing before any real run: **12/12** and **26/26**. Rewritten every `--validate`, so no date. |
| `venue_human_audit_random_sample_2026-09-18.csv` | The 50 records drawn (seed 20260918). Regenerate the reading sheet with `draw_audit_sample.py`. |
| `venue_human_audit_vg_verdicts_2026-09-19.csv` | VG's 50 answers. The design, the bounds and the two limits on what they mean are in `notes/journal_audit_protocol.md` §2.7. |
| `venue_repeat_run_agreement.txt` | Decoding noise, on the model of record: a fresh run agrees with the frozen three-run majority on **100 of 100** buckets, 76 with identical wording. |
| `venue_prompt_v1_pre_rule2a.txt` | The first prompt (hash `6cdbe5801fa3`), superseded. Kept so the revision is legible; the labels it produced are not kept. |
| `venue_prompt_tuning_review_verdicts_2026-09-17.md` | The review of that first prompt's exclusions, which produced rule 2a. **Reports no statistic** — targeted, and it drove the revision. |

**What is deliberately not kept.** The full label sets from the superseded prompt and from the
Sonnet run: a model-versus-model diff has no ground truth in it, and the pipeline's accuracy rests on
the control set and the human audits, not on either comparison. Both runs are in the git history if
a referee ever asks.

## 04_retrieve

`papers_to_obtain_<DATE>.csv` — **318 papers to obtain**, 130 found only by the venue search, 160
cited only by the surveys, 28 by both; three are already held as versions of record, so 315 remain.
`doi_lookup_queries_<DATE>.txt` holds Scopus title queries for the survey-side rows that carry no
DOI; their results (`scopus_doi_lookup_*`) are gitignored like every other raw Scopus download.

**Not yet merged.** Seven `scopus_doi_lookup_*` exports are in hand, but nothing has folded their
DOIs back into `papers_to_obtain_*`, so that file still shows those rows as lacking a DOI. Doing the
merge is outstanding work on the audit, not part of the tidy-up.

## Two prefixes, and what the dates mean

Every file in `01_search` through `04_retrieve` is named for the thing it holds: **`venue_papers_`**
(what the Scopus search found at the eleven venues) or **`survey_refs_`** (what the two surveys
cite). The same two words are used in the scripts, in the protocol and in conversation.

A **date in the name means the file records something that happened once** — a screen run, a draw, a
set of rulings. **No date means the file is rewritten every time its script runs**, so only the
current state is meaningful.

**One correction worth knowing about.** The venue labels once carried a `frame_id` column, copied in
from the sweep table when the screen ran. Four of its cells were wrong — the pre-2026-09-21 join
linked 24 papers to the surveys where the corrected join links 28 — and nothing read it. The column
was dropped on 2026-09-25; links come from `venue_papers_no_abstracts_2026-09-21.csv` and nowhere
else.

## What is deliberately not in this repository

Publisher copyright, not squeamishness: raw Scopus downloads (`scopus_*.csv`), the sweep tables that
carry abstracts (`*_with_abstracts_*.csv`), and the three hand-review sheets that quote the abstract
of every record under review (`*_sheet_*.md`). **The rulings those sheets produced are committed** —
the reasons, not the abstracts. One deliberate exception is tracked: the twelve control-set
abstracts, without which the control set cannot be re-run.

## Re-running any of it

    python3 code/audit_journal/01_search/filter_scopus_to_relevant_venues.py
    python3 code/audit_journal/02_screen/screen_venue_abstracts.py --validate   # 12 calls, must print 12/12
    python3 code/audit_journal/02_screen/screen_venue_abstracts.py --run        # ~379 calls, roughly $2
    python3 code/audit_journal/04_retrieve/build_papers_to_obtain.py

Decoding is greedy, which sharply reduces run-to-run variation but does not eliminate it: expect
near-identical, not bit-identical, output from the two screens. Everything else reproduces exactly.
