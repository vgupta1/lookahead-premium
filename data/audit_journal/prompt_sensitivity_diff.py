"""Reproduces the prompt-sensitivity diagnostic reported in the triage appendix.

Claim backed by this script: the rule-2a prompt revision moved 15 of the 379 records, and all 15
lie on the boundary that revision redrew rather than being scattered drift. Also reports the
model-choice comparison (final Sonnet run vs the Opus run of record).

Run from data/audit_journal/. Prints a table; writes nothing.
"""
import csv
from collections import Counter

PRE   = "triage_2026-09-16_prompt6cdbe5801fa3.csv"       # sonnet, prompt BEFORE rule 2a
POST  = "triage_2026-09-16_sonnet_prompt4bc0e50d09eb.csv" # sonnet, prompt AFTER rule 2a
FINAL = "triage_2026-09-16.csv"                           # opus, post-2a prompt, run of record

def load(path):
    return {r["sweep_id"]: r for r in csv.DictReader(open(path))}

def diff(a, b, label):
    flips = [(k, a[k]["bucket"], b[k]["bucket"], a[k]["title"][:60], b[k]["reason"][:120])
             for k in a if k in b and a[k]["bucket"] != b[k]["bucket"]]
    print(f"\n=== {label}: {len(flips)} of {len(set(a) & set(b))} records moved ===")
    for (x, y), n in sorted(Counter((f[1], f[2]) for f in flips).items()):
        print(f"  {x:9s} -> {y:9s}  {n}")
    for f in sorted(flips, key=lambda z: (z[1], z[2])):
        print(f"  {f[0]}  {f[1]:9s} -> {f[2]:9s} | {f[3]} | {f[4]}")
    return flips

pre, post, final = load(PRE), load(POST), load(FINAL)
diff(pre, post, "Prompt revision (rule 2a), model held fixed at sonnet-4-5")
diff(post, final, "Model change (sonnet-4-5 -> opus-4-5), prompt held fixed")
