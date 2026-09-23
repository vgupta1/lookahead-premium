# The Look-Ahead Premium in Decision-Focused Learning

Code and data for every experiment, figure and table in the paper.

Decision-focused learning papers report a quantity called *regret*, but they measure it
against two different oracles. **True-Model Regret** compares a policy with the decision
made under the true conditional model \(f^*\); **Look-Ahead Regret** compares it with the
decision made after seeing the realized \(Y\). The gap between them is the **Look-Ahead
Premium**, a property of the data-generating process alone — it does not depend on the
policy, so it cannot be reduced by a better method. The paper shows what happens when the
second is read as if it were the first. This repository is the evidence: the two published
experiments we re-analyze, the construction that isolates the mechanism, the audit of what
the literature reports, and the arithmetic behind the aggregation example.

Everything below runs from the data in this repository. No experiment is re-trained: the
autopsies recompute the premium from each paper's own generative model and correct that
paper's own published per-replication results.

## Quick start

```bash
git clone https://github.com/vgupta1/lookahead-premium.git
cd lookahead-premium
pip install -r requirements.txt

make all      # every figure and table  (~70 s)
make test     # the reproduction tests  (~40 s)
```

Outputs land in `outputs/`. Nothing else is written, and no network access is needed.

## What reproduces what

| Paper | Exhibit | Command | Output | Time |
|---|---|---|---|---|
| Fig. 1 | Elmachtoub–Grigas shortest path, reported vs corrected | `make figures` | `outputs/fig_shortest_path.pdf` | 5 s |
| Fig. 2 | The recommended metric and its limit | `make figures` | `outputs/fig_saa_normalized.pdf` | 3 s |
| Fig. 3 | Two-action construction, both panels | `make figures` | `outputs/fig_two_action.pdf` | 60 s |
| Table 1 | The literature audit | `make tables` | `outputs/tab_litaudit.tex` | 1 s |
| Table 2 | Artificially decreasing NRegLA and NRegTM (the cost shift) | `make tables` | `outputs/tab_shift.tex` | 3 s |
| Table 3 | Both autopsies on one page | `make tables` | `outputs/tab_autopsy.tex` | 5 s |
| Table 4 | Elmachtoub–Grigas portfolio, all eight regimes | `make tables` | `outputs/tab_portfolio.tex` | 2 s |

| Example 1 | Mean of ratios reverses a ranking | `python3 code/aggregation_example.py --example` | stdout | instant |
| §C notes | Reversal frequencies over random benchmarks | `python3 code/aggregation_example.py --frequencies` | stdout | 1 s |
| §C notes | Corrected vs their noiseless control | `python3 code/shortest_path_autopsy.py --report-control` | stdout | 5 s |
| — | Mean-of-ratios reversal on the E&G shortest-path generator | `python3 code/aggregation_reversal.py --deg 8 --reps 8` | stdout | 3 min |
| Table 4 | Re-run the portfolio Monte Carlo from scratch | `make portfolio` | `data/cache/portfolio_eta.csv` | ~2 h |

Table 5 (`tab:Claims`, which inferences are contaminated) is prose and has no computation
behind it.

**Tables are emitted as bare `tabular` blocks.** The float, the caption and the label live in
the paper's `.tex` files, where they can be edited without being overwritten on the next
rebuild; the generated file is the numbers only. `make paper` copies the rebuilt exhibits into
the paper tree — PDFs to `figs/`, tabulars to `tables/`:

```bash
make paper PAPER=/path/to/manuscript_workshop
```

`LAP_OUT` relocates the output directory and `LAP_ROOT` the data and cache directories; both
default to this repository.

## Layout

```
code/
  shortest_path_autopsy.py    Fig. 1, Fig. 2, Table 2; the shortest-path premium
  portfolio_autopsy.py        Table 4; the portfolio premium (the long computation)
  make_autopsy_table.py       Table 3, from the two autopsies above
  two_action_construction.py  Fig. 3; the construction of Appendix E
  literature_audit.py         Table 1, from data/audit.csv
  aggregation_example.py      Example 1 and the reversal frequencies
  aggregation_reversal.py     reversal on the E&G shortest-path generator
data/
  eg/                         Elmachtoub & Grigas's published replication results
  audit.csv                   the literature audit, one row per paper
  cache/portfolio_eta.csv     the portfolio premium, one row per replication
outputs/                      everything the paper prints
tests/                        the reproduction tests
```

Each script's module docstring states its generative model, its data provenance, and what it
checks on every run. Implementation details — sample construction, the risk-budget
discrepancy, the classification rules behind the audit — are in Appendix C of the paper and
are not repeated here.

## Data

**`data/eg/shortest_path.csv`, `data/eg/portfolio.csv`.** The per-replication results
published with Elmachtoub & Grigas, *Smart "Predict, then Optimize"* (Management Science,
2022), redistributed unmodified under their MIT license
(`data/eg/LICENSE-SmartPredictThenOptimize`). Column semantics were verified against their
plotting and replication scripts; the relevant mapping is recorded in the docstring of
`shortest_path_autopsy.py`. We take medians across replications exactly as their plotting
script does, so the "reported" row of every table in this repository is their number, not a
re-run.

**`data/audit.csv`.** One row per paper: which oracle, which denominator, which aggregation,
whether the DGP carries noise, and whether the paper draws conclusions across regimes. Papers
are classified by *what they wrote*, not by what their released code computes. The two
exclusion rules — noiseless DGPs, and papers reporting no experimental regret-like metric —
are applied through the `in_table1` column, and every excluded row carries the reason in
`status_note`. The audit was assembled with AI support and every cell then checked against the
source document; the paper says so, and the disclosure is in Appendix C.

**`data/cache/portfolio_eta.csv`.** The portfolio premium, one row per
`(tau, degree, replication)`, with the companion `portfolio_eta_meta.json` recording package
versions, solver, host and wall time. This is a cache, not a result to be trusted on faith:
`--selftest` recomputes sampled cells from their seeds and checks them against the cache. It
exists because the computation takes about two hours and every other exhibit depends on it.

## Determinism

Every random quantity is drawn from a seed derived from the cell it belongs to —
`np.random.default_rng([BASE_SEED, tau, deg, rep])` for the portfolio, and similarly
elsewhere — so a cell's value does not depend on how many workers ran, in what order, or on
whether an earlier run was interrupted. Any single cell can be recomputed on its own.

The premium in the portfolio experiment is the expectation of the optimal value of a second
-order cone program, solved with CLARABEL. Its values reproduce to about `1e-7` across solver
builds rather than bit for bit; the self-test uses that tolerance and prints the observed
difference. Everything else is exact arithmetic or plain Monte Carlo and reproduces bit for
bit at a fixed NumPy version.

Matplotlib stamps a creation date into every PDF it writes, so an unchanged figure would
otherwise regenerate as a different file. The plotting scripts fix `SOURCE_DATE_EPOCH`, which
removes the stamp: rebuilding an unchanged figure produces a byte-identical PDF and no diff.

The published numbers were produced with Python 3.10.12 and the versions pinned in
`requirements.txt`, on Linux (glibc 2.35).

## Table 1: the literature audit

Every cell of Table 1 is generated from `data/audit.csv` by `code/literature_audit.py`, which
also asserts the totals the paper prints, so a change to the data that would move a printed
number fails loudly.

The audit is a hand-built dataset, and the point of shipping it is that a reader can check it.
`data/SCHEMA.md` documents the four inclusion rules, every column's vocabulary, and the
definitions behind the two binary judgement columns (*potentially contaminated* and *synthetic*).
`data/evidence.csv` carries one row per classification -- 497 rows over the 35 papers in the pool
-- each giving the verbatim passage that supports it, with the PDF and page, or, where the claim
is that a paper never states something, the search protocol that established it. Every quoted
passage was checked mechanically against the page it cites. `data/RUBRIC.md` reproduces the
instructions the AI readers worked from; the paper's implementation-notes appendix describes the
process and its limitations.

Judgement calls that a second reader could reasonably decide differently were adjudicated by the
authors rather than resolved silently, and each is recorded as an `adjudication` row in
`evidence.csv` with its reasoning. Three cases are worth knowing about: two papers are counted on
a single qualifying experiment while their other experiments fall outside the paper's scope; one
paper's metric is labelled from the benchmark suite its code derives from, because the paper
itself never defines it; and the noise in a knapsack benchmark shared by three papers could not
be settled from the papers' text and was established from the benchmark's public data.

The audit is a sample, not a census, and a fuller version -- counting (paper, configuration)
pairs rather than papers -- is future work.

## What this repository does not reproduce

One number in the paper does not come out of this code, and it is better to say so than to have a
reader discover it.

**The conditional reversal frequencies** quoted in Appendix C are not reproducible from the
generative model as the appendix states it. The overall frequency is: this repository gives
19.6% against the 20% printed. The conditional figures are lower in every band, because the
published run put far more mass on benchmarks where the two methods differ widely than this
model does — which points at a per-method scale that the appendix's description omits. The
original script was not kept. Example 1 itself is exact arithmetic and is unaffected.

## Citation

Shammas Ahmed, Computational Applied Mathematics & Operations Research, Rice University
(<shammasahmed@rice.edu>) · Vishal Gupta, Data Sciences and Operations, University of Southern
California (<guptavis@usc.edu>).

```bibtex
@inproceedings{ahmed2026lookahead,
  title  = {The Look-Ahead Premium in Decision-Focused Learning},
  author = {Ahmed, Shammas and Gupta, Vishal},
  year   = {2026},
  note   = {Second Workshop on ML$\times$OR, NeurIPS 2026}
}
```

## License

MIT, except the vendored Elmachtoub–Grigas data, which carries their own MIT license. See
`LICENSE`.
