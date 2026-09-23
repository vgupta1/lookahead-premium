# The literature audit: `audit.csv` and `evidence.csv`

Table 1 of the paper is generated from `audit.csv` by `code/literature_audit.py`; every cell
is derived from the CSV. `evidence.csv` records, for every classification that decides a cell
of Table 1, the passage in the source PDF that supports it (or the protocol that failed to find
one), so a reader with the PDFs can check each row. PDFs are named in `pdf_file`; page numbers
are PDF page numbers of that file.

## Inclusion rules

A paper is counted in Table 1 if **at least one of its experiments** satisfies all four of:

1. **linear contextual optimization** -- the cost is linear in the uncertain quantity and the
   feasible region is known and not itself uncertain;
2. **offline predict-then-optimize** -- not an online or bandit setting reporting cumulative
   quantities over rounds;
3. **reports an experimental regret-like or objective-value metric** -- not theory or survey only;
4. **a noisy DGP** -- Y is not a deterministic function of X in that experiment, so the two
   oracles differ.

The classification columns describe the qualifying experiment(s), not the paper's full
experimental suite. Every `in_table1 = no` row names the rule it fails in `exclusion_reason`.
Two scope notes for the post-workshop version are recorded in `exclusion_reason` where they
arise (Kai Wang et al.'s portfolio objective is linear in (p, Q) jointly; Donti et al.'s
battery experiment is linear in prices plus a known quadratic penalty).

## `audit.csv` -- one row per paper

| column | meaning / vocabulary |
|---|---|
| `key` | bibtex key, matches `refs.bib` |
| `authors`, `venue`, `year` | as cited |
| `entry_route` | how the paper entered the sample: `library` (PyEPO; the JAIR benchmark suite), `library-method` (originates a method benchmarked by either library), `survey`, `true-model` (the OR-side line reporting a true-model oracle), `theory`, `search` (purposive search of recent venues and forward citation) |
| `pdf_file` | filename in `papers/` |
| `oracle` | oracle the reported regret is measured against: `LA` (look-ahead: the optimum for the realized cost), `TM` (true-model: the optimum under the conditional mean), `none` (no regret reported), `unknown` |
| `denominator` | `raw` (unnormalized), `oracle_cost` (the oracle's cost summed or averaged over the test set), `ref_policy_regret` (the regret of a reference policy), `per_instance` (each instance's own oracle cost, then averaged), `achieved_objective` (the cost the method's own decisions achieve), `not_stated` (a normalized / relative / percentage regret is reported but its denominator is never given), `none`, `true_sp_cost`, `unknown` |
| `aggregation` | `mean`, `sum`, `ratio_of_sums`, `mean_of_ratios`, `ratio_of_expectations` (defined on population expectations, estimated by ratios of means), `cumulative`, `indicators`, `none`, `unknown` |
| `noise` | what the DGP carries: `real`, `yes` (synthetic, stochastic Y given X), `none` (synthetic, deterministic), `mixed` (real and synthetic experiments, or noisy and noiseless settings, or semi-synthetic), `unknown`. Kept coarse deliberately; Table 1 does not use it. |
| `cross_regime` | the first pass's raw reading; superseded by `contaminated` and kept for provenance |
| `formula_stated` | `yes` (the reported quantity is written as a formula or an exact verbal definition), `partial` (the regret is defined but the reported normalization is not), `no`, `unknown` |
| `contaminated` | **binary, drives Table 1 column 2.** `yes` if the paper makes at least one written inference of a kind the paper's Table *tab:Claims* marks as potentially contaminated: a comparison of the metric across DGP regimes (degree, noise level, problem size, different problems, perturbed labels); a reading of the metric's magnitude as headroom or as how hard an instance is; a sized difference or percentage reduction of a normalized look-ahead regret; a captured share of a reference policy's regret; or a method ranking that rests on a mean of per-instance ratios. **Not counted**: comparisons across training-set size on one DGP (the premium is constant there), method rankings on a fixed DGP by any other metric, and the bare reporting of a level without interpretation. Papers whose oracle is the true model receive `no`: the premium enters none of their comparisons (they remain exposed to the shift-invariance point of Section 3, which the paper concedes separately). |
| `synthetic` | **binary, drives Table 1 column 3.** `yes` if at least one **qualifying** experiment (one meeting all four inclusion rules) uses a synthetic or semi-synthetic DGP; real inputs transformed and/or noised to produce the targets count as semi-synthetic. `no` otherwise -- note that a paper with synthetic experiments can be `no`, when those experiments are noiseless and so do not qualify (`shah2022lodl`, `berden2025solver`). |
| `in_table1` | `yes` / `no` |
| `exclusion_reason` | the rule an excluded paper fails, and why |
| `status_note` | free text, including the adjudication behind any label that differs from the evidence rows' `value` |

## `evidence.csv` -- one row per (paper, field) supporting a classification

| column | meaning |
|---|---|
| `key`, `field`, `value` | the `audit.csv` cell being supported; `value` is what the reader found |
| `evidence_type` | `quote` (verbatim passage, machine-checked against the page text), `equation` (a verbatim prose fragment next to the equation, then `::` and a transcription; the fragment is machine-checked), `absence` (the search protocol that found nothing: terms grepped with hit counts, sections read in full), `reconstruction` (value inferred from stated anchors; the reasoning is in `evidence`), `inference` (value taken from a named library or benchmark default that the paper says it uses), `repository` (value established from a paper's or benchmark's public code or data, not from its text), `adjudication` (a label set by the authors' ruling where the reader's finding was borderline or a policy applies; the reasoning is in `evidence`) |
| `evidence` | the passage, transcription, protocol, or reasoning |
| `pdf_file`, `page`, `section` | where to look |
| `note` | free text |

Where an `audit.csv` label differs from the `value` of the reader's rows, an `adjudication`
row or the `status_note` records why. Fields with evidence rows: `oracle`, `denominator`,
`aggregation`, `noise`, `synthetic`, `contaminated`, `formula_stated`, `metric_name`, and
`setting` (for exclusions under rule 1 or 2).

## The PDFs

`pdf_file` names the PDF each paper was read from. The working `papers/` folder also holds items
that are **not** part of this database: papers considered and set aside without an audit row, and
second copies of papers already in it (a published version of one preprint, and the full arXiv
version of a paper whose conference PDF omits the appendix that documents its DGP). A file in
`papers/` is part of the audit only if some row of `audit.csv` names it.

## How the audit was produced

Candidate papers were gathered as described under `entry_route`. Every paper was read from
its PDF for the eight fields above by an AI reader working from a fixed rubric, which was
required to copy passages verbatim from per-page extracted text and to flag rather than
resolve anything borderline (the rubric is reproduced in `RUBRIC.md`); every `quote` and `equation` fragment was then checked
mechanically against the page it cites (0 failures over 448 fragments). The authors
adjudicated every flagged item; those rulings are the `adjudication` rows. One fact could not
be settled from the papers' text and was established from a public repository
(`evidence_type = repository`): the noise on the knapsack targets shared by three papers.
