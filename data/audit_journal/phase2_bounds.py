"""Confidence bounds on the triage false-exclusion rate from the Phase 2 blind sample.

Zero misses were observed, so the interval is one-sided and the upper bound carries all the
information. The sample is a substantial fraction of a finite population (50 of 221), so the
hypergeometric bound is the one reported; the Clopper-Pearson bound is printed alongside because it
is what a reader expects to see, and it is looser.

Run from data/audit_journal/.
"""
import csv
from math import comb

FINAL    = "triage_final_2026-09-16.csv"
VERDICTS = "phase2_verdicts_2026-09-19.csv"
CONF     = 0.95

final = list(csv.DictReader(open(FINAL)))
verd  = list(csv.DictReader(open(VERDICTS)))

N = sum(1 for r in final if r["final_bucket"] == "OUT")   # population of excluded records
n = len(verd)                                             # sample size
k = sum(1 for r in verd if r["vg_bucket"] != "OUT")       # misses found

print(f"population N = {N} excluded records; sample n = {n}; misses k = {k}")
assert k == 0, "bounds below assume zero observed misses; generalize before reusing"

alpha = 1 - CONF
cp1 = 1 - alpha ** (1 / n)          # Clopper-Pearson, one-sided
cp2 = 1 - (alpha / 2) ** (1 / n)    # Clopper-Pearson, two-sided upper
print(f"binomial (Clopper-Pearson) 95% one-sided upper: {cp1:.4f}  -> {cp1*N:.1f} records")
print(f"binomial (Clopper-Pearson) 95% two-sided upper: {cp2:.4f}  -> {cp2*N:.1f} records")

# Hypergeometric: the largest M such that observing zero misses is not yet improbable at alpha.
for M in range(N + 1):
    p0 = comb(N - M, n) / comb(N, n) if N - M >= n else 0.0
    if p0 < alpha:
        M_max = M - 1
        print(f"hypergeometric 95% one-sided upper: {M_max} of {N} records = {M_max/N:.4f}")
        break
