# Phase 2 — false-exclusion rate of the triage screen

**Result: 0 misses in 50.** Every record in the sample was confirmed OUT.

## Design

Measurement phase, random, reported. Distinct from the Phase 1 targeted review
(`triage_phase1_verdicts.md`), which oversampled where errors were expected and drove a prompt
revision, and therefore reports no statistic. Phase 2 was drawn only after the prompt was frozen.

- Population: the 221 records with `final_bucket == OUT` in `triage_final_2026-09-16.csv`, i.e. the
  Opus run with the four hand adjudications applied.
- Sample: 50 records, simple random sample without replacement, seed 20260918, drawn and shuffled by
  `phase2_sample.py`.
- Blinding: the reading sheet `phase2_sheet_2026-09-18.md` carried title, venue, year and abstract
  only. The machine bucket, stated reason and confidence were withheld, so the human label was not
  anchored on the machine's.
- Labeller: VG, 2026-09-19, applying the frozen triage rule as restated on the sheet.
- Verdicts: `phase2_verdicts_2026-09-19.csv`.

## Interpretation

With zero misses observed, the upper confidence bounds are what carry the information:

| Bound | Rate | Records in the OUT pile |
|---|---|---|
| Clopper–Pearson, 95% one-sided | 5.8% | 12.9 |
| Clopper–Pearson, 95% two-sided | 7.1% | 15.7 |
| Hypergeometric, 95% one-sided (finite population, N = 221) | 5.0% | 11 |

The hypergeometric bound is the honest one to quote: the sample is 23% of the population, so
treating the draw as binomial discards real information and overstates the bound. **At most about
eleven of the 221 excluded records are misses, with 95% confidence.**

Two limits on what this measures. First, it measures agreement between the screen and one human
applying the same written rule; it does not measure whether the rule itself is the right one, which
is a matter of the scope predicate and is argued rather than estimated. Second, it is an estimate for
this pipeline as specified by prompt hash `4bc0e50d09eb` under model `claude-opus-4-5-20251101`; it
does not license a claim about LLM triage in general. Sensitivity to paraphrases of the prompt that
preserve the rule remains unmeasured.

*Corrected 2026-09-21: the prompt hash above previously read `6cdbe5801fa3`, which is the
pre-rule-2a Sonnet prompt. Every row of `triage_2026-09-16.csv` carries `4bc0e50d09eb`.*
