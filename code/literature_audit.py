#!/usr/bin/env python3
"""Table 1 of the paper: what "regret" means across a sample of the DFL literature.

Reads ``data/audit.csv`` -- one row per paper, classified by what the paper itself
wrote -- and emits ``outputs/tab_litaudit.tex``.  Counting rules, as stated in the
paper's implementation notes:

  * counts are of PAPERS, not experiments;
  * a paper is classified by what it wrote, not by what its released code computes;
  * papers whose DGP is noiseless are excluded, because the two oracles coincide
    there and the premium is identically zero;
  * surveys and theory papers reporting no experimental regret-like metric are
    excluded;
  * "synthetic" means the DGP is not real data (``noise != "real"``).

WHAT THIS SCRIPT DOES AND DOES NOT REPRODUCE
--------------------------------------------
The **row structure** of Table 1 -- which oracle and which denominator each paper
uses, and therefore every sub-row and its **Papers** count -- is derived mechanically
from ``audit.csv`` and is asserted on every run.  A change to ``audit.csv`` that moves
a Papers count fails loudly.

Columns 2 (**Potentially contaminated**) and 3 (**Synthetic**) are NOT mechanically
reproducible from ``audit.csv`` as it stands, and are emitted from the hand assignment
recorded in ``PUBLISHED_SUBROW`` below.  Both were per-paper reading judgements whose
per-paper resolution was not recorded -- only the sub-row totals survive:

  * ``cross_regime`` carries hedged values (``mild``, ``partial``, ``cross_problem``)
    that *bracket* the printed column rather than reproducing it.  Counting only
    ``yes`` gives 13 of 26; counting every hedge gives 21; the paper prints 16.
  * ``noise`` records what kind of noise the DGP carries, which is not the same
    question as whether the data are synthetic.  Reading ``noise != "real"`` as
    synthetic gives 21 overall but disagrees with the paper in three sub-rows.

``--reconcile`` prints both gaps sub-row by sub-row and names the papers whose
classification decides them.  Making Table 1 fully generated is a matter of adding
two binary columns to ``audit.csv`` -- ``contaminated`` and ``synthetic`` -- with a
decision for each of those papers (``open_notes`` B0), after which
``--contaminated audit`` reproduces the table with no hand assignment anywhere.
"""

import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("LAP_ROOT", os.path.join(HERE, ".."))
AUDIT = os.path.join(ROOT, "data", "audit.csv")
OUTDIR = os.environ.get("LAP_OUT", os.path.join(ROOT, "outputs"))

# Values of cross_regime that are unambiguous.  Everything else is a hedge and is
# what the unrecorded judgement had to resolve.
HEDGES = ("mild", "partial", "cross_problem", "qualitative", "unknown")

# (papers, contaminated-as-printed, synthetic), exactly as Table 1 prints them.
# Columns 1 and 3 are asserted against audit.csv; column 2 is hand-assigned.
PUBLISHED_BLOCK = {
    "LA": (21, 13, 18),
    "TM": (3, 3, 3),
    "none": (2, 0, 0),
    "total": (26, 16, 21),
}
PUBLISHED_SUBROW = {
    ("LA", "raw"): (4, 1, 3),
    ("LA", "oracle_cost"): (7, 5, 7),
    ("LA", "ref_policy_regret"): (3, 1, 2),
    ("LA", "per_instance"): (3, 2, 3),
    ("LA", "not_stated"): (4, 4, 3),
    ("TM", "oracle_cost"): (2, 2, 2),
    ("TM", "ref_policy_regret"): (1, 1, 1),
}
LA_SUBROWS = [
    ("raw regret, unnormalized", "raw"),
    ("by the oracle's cost", "oracle_cost"),
    ("by a reference policy's regret", "ref_policy_regret"),
    ("per instance (mean of ratios)", "per_instance"),
    ("never stated", "not_stated"),
]
TM_SUBROWS = [
    ("by the oracle's cost", "oracle_cost"),
    ("by a reference policy's regret", "ref_policy_regret"),
]


def load(path=AUDIT):
    d = pd.read_csv(path)
    d["synthetic"] = d.noise != "real"
    d["strict"] = d.cross_regime == "yes"                 # lower bound on column 2
    d["broad"] = ~d.cross_regime.isin(["no"])             # upper bound on column 2
    return d[d.in_table1 == "yes"].copy()


def counts(sub):
    """(papers, contaminated-strict, contaminated-broad, synthetic)."""
    return len(sub), int(sub.strict.sum()), int(sub.broad.sum()), int(sub.synthetic.sum())


def blocks(t):
    out = {o: t[t.oracle == o] for o in ("LA", "TM", "none")}
    out["total"] = t
    return out


def check(t):
    """Assert the Papers column, block by block and sub-row by sub-row."""
    ok = True
    for name, sub in blocks(t).items():
        n = len(sub)
        if n != PUBLISHED_BLOCK[name][0]:
            print(f"  MISMATCH {name}: {n} papers, Table 1 prints "
                  f"{PUBLISHED_BLOCK[name][0]}", file=sys.stderr)
            ok = False
    for (oracle, den), pub in PUBLISHED_SUBROW.items():
        n = len(t[(t.oracle == oracle) & (t.denominator == den)])
        if n != pub[0]:
            print(f"  MISMATCH {oracle}/{den}: {n} papers, Table 1 prints {pub[0]}",
                  file=sys.stderr)
            ok = False
    print("  Papers column and row structure match Table 1" if ok
          else "  Papers column DOES NOT match Table 1", flush=True)
    return ok


def _rows(t):
    out = [(f"{o}: {den}", t[(t.oracle == o) & (t.denominator == den)], p)
           for (o, den), p in PUBLISHED_SUBROW.items()]
    out += [(f"{o} (block)", t[t.oracle == o], PUBLISHED_BLOCK[o]) for o in
            ("LA", "TM", "none")]
    return out + [("TOTAL", t, PUBLISHED_BLOCK["total"])]


def reconcile(t):
    """Print both non-mechanical columns against audit.csv, and name the open papers."""
    print("\nColumn 2, potentially contaminated: audit.csv brackets the printed value.")
    print(f"{'sub-row':<36}{'yes only':>10}{'+hedges':>9}{'printed':>9}")
    for label, sub, pub in _rows(t):
        _, st, br, _ = counts(sub)
        flag = "" if st <= pub[1] <= br else "   <-- outside the bracket"
        print(f"{label:<36}{st:>10}{br:>9}{pub[1]:>9}{flag}")
    hedged = t[t.cross_regime.isin(HEDGES)]
    print(f"\n  {len(hedged)} papers carry a hedged cross_regime value:")
    for _, r in hedged.iterrows():
        print(f"    {r.key:<28}{r.oracle:<4}{r.denominator:<20}{r.cross_regime}")

    print("\nColumn 3, synthetic: `noise != real` disagrees with the printed value.")
    print(f"{'sub-row':<36}{'noise!=real':>12}{'printed':>9}")
    open_rows = []
    for label, sub, pub in _rows(t):
        _, _, _, s = counts(sub)
        flag = "" if s == pub[2] else "   <-- disagrees"
        if s != pub[2] and "block" not in label and label != "TOTAL":
            open_rows.append(sub)
        print(f"{label:<36}{s:>12}{pub[2]:>9}{flag}")
    if open_rows:
        undecided = pd.concat(open_rows)
        print(f"\n  {len(undecided)} papers sit in the disagreeing sub-rows:")
        for _, r in undecided.iterrows():
            print(f"    {r.key:<28}{r.denominator:<20}noise={r.noise}")

    print("\nAdd binary `contaminated` and `synthetic` columns to data/audit.csv with a\n"
          "decision for each paper above, then run with --contaminated audit.")


def pct(n, d):
    return "---" if d == 0 else f"{round(100 * n / d)}\\%"


def _pub(key):
    return (PUBLISHED_SUBROW if isinstance(key, tuple) else PUBLISHED_BLOCK)[key]


def row(label, sub, mode, key, bold=False, indent=0):
    n, st, br, syn = counts(sub)
    if mode == "published":
        c, s = _pub(key)[1], _pub(key)[2]
    else:
        c, s = (st if mode != "broad" else br), syn
    lead = {0: "", 1: "\\quad ", 2: "\\qquad "}[indent]
    lab = f"\\textbf{{{label}}}" if bold else label
    fmt = (lambda x: f"\\textbf{{{x}}}") if bold else (lambda x: str(x))
    return (f"{lead}{lab} & {fmt(n)} & {fmt(c)} ({pct(c, n)}) "
            f"& {fmt(s)} ({pct(s, n)}) \\\\")


def build(t, mode="published", path=None):
    path = path or os.path.join(OUTDIR, "tab_litaudit.tex")
    L, T = t[t.oracle == "LA"], t[t.oracle == "TM"]
    note = {"published": "columns 2 and 3 are HAND-ASSIGNED (see the module docstring; open_notes B0)",
            "audit": "columns 2 and 3 computed from audit.csv, cross_regime == yes only",
            "broad": "columns 2 and 3 computed from audit.csv, every hedge read as yes"}[mode]
    lines = [
        "% !TEX root = ../00_main.tex",
        "% GENERATED by code/literature_audit.py from data/audit.csv.  Do not hand-edit.",
        f"% {note}",
        "\\begin{figure}[t]", "\\centering",
        "\\begin{minipage}[c]{0.615\\textwidth}", "  \\footnotesize",
        "  \\setlength{\\tabcolsep}{4pt}",
        "\\begin{tabular}{@{}lrrr@{}}", "\\toprule",
        "Benchmarking metric & Papers & \\makecell[r]{Potentially\\\\contaminated} & Synthetic \\\\",
        "\\midrule",
        row("Look-Ahead Regret", L, mode, "LA", bold=True),
        "\\quad \\emph{normalized\\dots} & & & \\\\",
    ]
    # `raw` is not a normalization; it sits above the normalized group.
    lines.insert(-1, row("raw regret, unnormalized", L[L.denominator == "raw"],
                         mode, ("LA", "raw"), indent=1))
    for lab, den in LA_SUBROWS[1:]:
        lines.append(row("\\textbf{never stated}" if den == "not_stated" else lab,
                         L[L.denominator == den], mode, ("LA", den), indent=2))
    lines += ["\\addlinespace", row("True-Model Regret", T, mode, "TM", bold=True),
              "\\quad \\emph{normalized\\dots} & & & \\\\"]
    for lab, den in TM_SUBROWS:
        lines.append(row(lab, T[T.denominator == den], mode, ("TM", den), indent=2))
    lines += ["\\addlinespace",
              row("No regret reported", t[t.oracle == "none"], mode, "none", bold=True),
              "\\midrule", row("Total", t, mode, "total", bold=True),
              "\\bottomrule", "\\end{tabular}", "\\end{minipage}\\hfill",
              "\\begin{minipage}[c]{0.355\\textwidth}",
              "  \\captionof{table}{\\textbf{Benchmark metrics across literature.}",
              f"  {len(t)} highly cited and recent publications on DFL.",
              "  See \\cref{sec:ImplAudit} for selection criteria.",
              "  Metrics based on a look-ahead oracle dominate the literature, and those papers make potentially",
              "  contaminated claims (cf. \\cref{tab:Claims}).",
              "  Both benchmarking libraries \\textsc{PyEPO} \\citep{tang2024pyepo}  and \\textsc{PredOpt} \\cite{mandi2024decision} use normalized look-ahead regret, but differ in aggregation; \\textsc{PredOpt} aggregates per instance (a mean of ratios). Most papers use synthetic data.}",
              "  \\label{tab:LitAudit}", "\\end{minipage}", "\\end{figure}", ""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("\n".join(lines))
    print("wrote", os.path.normpath(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--contaminated", choices=("published", "audit", "broad"),
                    default="published",
                    help="how to fill columns 2 and 3: the recorded hand assignment, "
                         "or computed from audit.csv")
    ap.add_argument("--reconcile", action="store_true",
                    help="show the gap between audit.csv and the printed column 2")
    ap.add_argument("--open", action="store_true", help="list the unresolved cells")
    a = ap.parse_args()
    d = pd.read_csv(AUDIT)
    t = load()
    if a.open:
        print("Unresolved (open_notes B0/B1):")
        pat = "OPEN|unread|undocumented"
        for _, r in d[d.status_note.astype(str).str.contains(pat, case=False,
                                                             na=False)].iterrows():
            print(f"  {r.key}: {r.status_note}")
        return
    print(f"{len(d)} papers audited, {len(t)} in Table 1")
    ok = check(t)
    if a.reconcile:
        reconcile(t)
    build(t, a.contaminated)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
