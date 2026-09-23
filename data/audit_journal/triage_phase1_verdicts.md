# Phase 1 triage review — verdicts (VG, 2026-09-17)

Design phase, targeted sample. **Reports no statistic** — targeted sampling deliberately oversamples
where errors are expected, so its error rate does not estimate the rate in the OUT pile, and these
rows drove a prompt revision, which contaminates them as a measurement. The reported figure comes
from Phase 2: a fresh random sample of the OUT bucket, drawn after the prompt was frozen.

Run reviewed: `triage_2026-09-16_prompt6cdbe5801fa3.csv` (model `claude-sonnet-4-5-20250929`,
temperature 0, prompt hash `6cdbe5801fa3`). Buckets: OUT 232, CANDIDATE 145, UNCLEAR 2.

Selection rule for the sample: OUT records with confidence below high, **or** at an OR-side venue
(OR / MS / M&SOM / IJOC, where off-topic noise is rare), **or** already cited by a seed survey.
Thirteen records.

## Verdicts

| Record | Venue | VG | Note |
|---|---|---|---|
| SW0124 | ICLR 2024 | AGREE | |
| SW0128 | ICLR 2024 | AGREE | |
| **SW0166** | ICML 2023 | **KEEP** | Meta Optimal Transport — see below |
| SW0227 | IJOC 2023 | AGREE | |
| SW0229 | IJOC 2024 | AGREE | |
| SW0233 | IJOC 2025 | AGREE | |
| SW0235 | IJOC 2026 | AGREE | |
| SW0238 | MS 2023 | AGREE | |
| SW0283 | NeurIPS 2023 | AGREE | |
| SW0297 | NeurIPS 2024 | AGREE | |
| SW0313 | NeurIPS 2024 | AGREE | |
| SW0366 | OR 2023 | AGREE | |
| SW0370 | OR 2025 | AGREE | Inverse Optimization survey; the one seed-frame paper the screen dropped |

Additionally reviewed, surfaced by a pattern scan rather than the sampling rule:

| Record | Venue | VG | Note |
|---|---|---|---|
| SW0273 | NeurIPS 2023 | AGREE | SATNet rule-learning — MaxSAT is machinery, not the object |

**12 of 13 agreed; one genuine miss.**

## The miss, and what it changed

**SW0166, "Meta Optimal Transport"** was classified OUT with the reason *"Optimal transport is used
as a computational tool, not as a decision problem being solved from predictions."* That is a
failure to follow the prompt, not a defect in the rule: rule 2 already said solver and proxy work is
CANDIDATE. The model read "a learned or predictive component" as requiring a predictor of *problem
data*, so a learned **solver** did not register as satisfying it.

A scan of all 232 OUT records for solver/proxy/amortization language in the stated reason returned
nine. Seven are correct (PDE solvers, kernel approximation, surrogate losses for classification).
The other two are SW0166 and SW0273, and SW0273 was adjudicated OUT on its merits. So the failure is
narrow and specific rather than systematic.

**Prompt revision.** Rule 2a added, stating that the learned component may be the solver itself, and
that both conjuncts still apply — a better classical algorithm with nothing learned is OUT for want
of a learned component, and physical simulation is OUT for want of a decision problem. The
discriminating question is what the paper takes as its object: solving the optimization problem
faster is CANDIDATE; using a solver as machinery for some other goal is not. Meta OT and SATNet
were added as contrasting worked examples.

**A first draft of 2a was wrong and is worth recording.** It read "it is CANDIDATE even when the
entire contribution is solving it faster," which drops the learned-component conjunct and would have
swept in classical optimization research — variance-reduced gradient methods, interior-point
variants. Caught by VG before it ran.

## Expected consequence

The revision should admit neural combinatorial optimization — learned TSP heuristics, neural
branch-and-bound — none of which predicts an uncertain parameter, so all of it should fail Gate A at
full text. That is the design working: triage is deliberately permissive, and the Gate-A count is
itself a reportable measure of how much of this literature is deterministic-solver work. If the
corpus grows more than the PDF-chasing budget allows, tighten then, and record the tightening.
