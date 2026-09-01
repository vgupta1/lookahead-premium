# Reader rubric — the instructions issued to the AI readers

This is the rubric referred to in the paper's implementation notes, reproduced as it was issued
on 2026-08-31, so that a reader can see exactly what the AI readers were and were not told.

Two notes on reading it. The paths it names (`/home/claude/audit/...`, `work/<key>.*`) are those
of the working environment: `papers/` held the PDFs, `text/` a per-page plain-text extraction of
each, and each reader wrote one evidence file and one notes file per paper. Those per-paper files
were consolidated, after the authors' adjudication, into `data/evidence.csv` in this repository;
the labels they support are in `data/audit.csv`, and `data/SCHEMA.md` documents both. Rule 7
below -- readers record and flag, never relabel -- is why every disagreement between a reader's
finding and a label reached the authors rather than being resolved silently; those rulings are
the `adjudication` rows in `evidence.csv`.

---

## Definitions you must apply exactly

- **oracle**: which oracle the reported regret is measured against. `LA` = the optimum for
  the *realized* cost vector (the paper computes regret as c^T(x(ĉ) - x*(c)) with c the
  realized/true cost of the test instance; often called "full-information", "hindsight",
  "perfect foresight", or simply "the true optimal solution" for that instance). `TM` = the
  optimum under the *conditional mean* E[Y|X=x] (the paper compares to a policy that knows
  the true model but not the realization). `none` = the paper reports no regret (e.g. only
  an objective value or accuracy).
- **denominator**: what the regret is divided by, if anything. `raw` (nothing),
  `oracle_cost` (the oracle's objective, summed or averaged over the test set),
  `per_instance` (each instance's own oracle cost, before averaging), `ref_policy_regret`
  (the regret of a reference policy: SAA, random predictions, worst case, a two-stage
  baseline), `achieved_objective`, `not_stated` (a normalized/relative/percentage regret is
  reported but the paper never says what the denominator is), `none` (no regret).
- **aggregation**: how per-instance quantities are combined: `ratio_of_sums` (sum of regrets
  over sum of oracle costs, or mean over mean), `mean_of_ratios` (average of per-instance
  ratios), `mean`, `sum`, `cumulative` (over rounds), `indicators` (% optimal), `aggregates`
  (defined on population-level expectations), `unknown` (not stated).
- **noise**: what the data-generating process (DGP) carries: `real` (real-world data),
  `yes` (synthetic with a stochastic component in Y given X), `none` (synthetic but Y is a
  deterministic function of X, e.g. fixed terrain costs), `mixed` (both real and synthetic,
  or both noisy and noiseless settings), `unknown`.
- **synthetic** (binary): `yes` if at least one regret-reporting experiment uses a
  synthetic DGP; `no` if every regret-reporting experiment is on real data.
- **contaminated** (binary): `yes` if the paper draws at least one conclusion by comparing
  its reported metric **across DGP regimes** -- across polynomial degree / misspecification
  level, across noise level, across training-set size, across problem sizes, or across
  different problems -- or reads the *magnitude* of its normalized metric as how much room
  for improvement remains. Comparing *methods* against each other within one fixed DGP is
  **not** contamination. `no` if every conclusion is a within-regime method ranking.
  Quote the actual sentence that makes the cross-regime comparison. Typical forms: "as the
  degree increases, regret ...", "the gap widens with the noise level", "performance
  improves with more training data", "regret is higher for the harder problem".
- **formula_stated**: `yes` if the paper writes the reported metric as a formula (or a
  precise verbal definition naming numerator and denominator); `partial` if it defines the
  regret but not the normalization (or vice versa); `no` if the reported quantity is never
  defined.
- **metric_name**: the paper's own name for what it reports (e.g. "normalized regret",
  "relative regret", "percentage regret", "decision quality"). Quote it.
- **setting** (for excluded papers only): the passage showing why the paper falls outside
  the inclusion rules in SCHEMA.md (nonlinear objective / uncertainty in constraints /
  online setting / noiseless DGP / no experimental metric).

## Evidence rules -- these matter more than speed

1. **Every quote must be copied verbatim from `text/<stem>/pNNN.txt`**, and `page` must be
   NNN of the file it came from. Never quote from memory, never paraphrase inside the
   `evidence` field, never edit a quote to read better. One to three sentences is ideal.
   A quote will be checked mechanically against the page text; a quote that is not on its
   page is worse than no quote.
2. For an **equation**, use `evidence_type = equation` and write the evidence as
   `<a verbatim prose fragment from the page that appears next to the equation> :: Eq. (k): <your transcription>`.
   The part before `::` is checked mechanically; the transcription is not.
3. For a claim of **absence** (`denominator = not_stated`, `formula_stated = no`,
   `contaminated = no`), use `evidence_type = absence` and write the protocol you actually
   ran: which terms you grepped in the whole-paper text (e.g. `regret`, `normaliz`,
   `relative`, `percent`, `divid`, `denominator`, `ratio`), how many hits, and which sections
   you read in full. Be specific enough that someone could redo it.
4. `reconstruction` is for a value inferred from stated anchors (e.g. a metric pinned at 0
   and 1 by two named baselines) -- give the reasoning in `evidence` and quote the anchors
   in separate `quote` rows.
5. `inference` is for a value taken from a named library default (e.g. "we use PyEPO" with
   no formula) -- quote the sentence naming the library.
6. Prefer the passage where the paper **defines** the metric over passages that merely use
   it. Give `section` as the paper's own section heading or number.
7. **Do not change labels.** If what you find contradicts the current row in `audit.csv`,
   record the evidence for what you found and flag the disagreement in your notes file.
   Do not silently fix it and do not silently keep the old label.

## What to write

For each paper with key `<key>`:

`work/<key>.evidence.csv` -- header exactly:
`key,field,value,evidence_type,evidence,pdf_file,page,section,note`
One row per (field, supporting passage). Fields for a **counted** paper (in_table1 = yes):
`metric_name, oracle, denominator, aggregation, noise, synthetic, contaminated, formula_stated`
-- at least one row each; more when one passage does not settle it. For an **excluded**
paper: `setting` (and `noise` where the exclusion is noiselessness; `oracle`/`metric_name`
if it reports a regret at all) -- two to four rows total.

`work/<key>.notes.md` -- three short sections:
1. **Labels**: the value you would assign to each field, with `agrees` / `DISAGREES` against
   the current audit.csv row, and one line of reasoning each.
2. **Judgement calls**: anything a careful second reader could reasonably decide the other
   way. State both readings, cite the pages, say which you lean to and why. Include
   borderline `contaminated` calls (e.g. a single sentence noting a trend across degree,
   without drawing a conclusion from it), mixed real/synthetic papers, and metrics whose
   denominator is implied but never written.
3. **Anything else**: naming hazards, multiple metrics across experiments, appendices that
   define what the body does not, page-numbering quirks.

Work paper by paper. Write each paper's two files before starting the next, so partial
progress survives. When finished, reply with only: the list of files written, and a
one-line summary per paper of any DISAGREES or judgement calls.
