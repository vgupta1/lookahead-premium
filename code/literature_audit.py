#!/usr/bin/env python3
"""Table 1 of the paper: what "regret" means across a sample of the DFL literature.

Reads ``data/audit.csv`` -- one row per paper -- and emits ``outputs/tab_litaudit.tex``.
Every number in the table is derived from the CSV: the row structure from ``oracle`` and
``denominator``, column 2 from the binary ``contaminated`` column and column 3 from the
binary ``synthetic`` column.  The evidence behind each classification is in
``data/evidence.csv`` (one row per supporting passage, with file and page); the
vocabularies and inclusion rules are in ``data/SCHEMA.md``.

Counting rules, as stated in the paper's implementation notes:

  * counts are of PAPERS; a paper is counted if at least one of its experiments is
    (1) linear contextual optimization, (2) offline predict-then-optimize, (3) reports an
    experimental regret-like metric, (4) on a noisy DGP -- and its columns describe that
    experiment;
  * a paper is classified by what it wrote, not by what its released code computes,
    except where the CSV says otherwise (``evidence_type = repository`` / ``inference``);
  * ``contaminated = yes`` records at least one written inference of a kind Table
    tab:Claims marks as potentially contaminated -- a cross-DGP comparison of the metric,
    a magnitude or headroom reading, a sized difference of normalized look-ahead regrets,
    a captured share of a reference policy's regret, or a ranking by a mean of ratios.
    Comparisons across training-set size on one DGP do not count (the premium is constant
    there), and neither does the bare reporting of a level;
  * ``synthetic = yes`` if at least one counted experiment uses a synthetic or
    semi-synthetic DGP.

``EXPECTED`` holds the totals the paper's caption and prose quote.  A change to the CSV
that moves any of them fails loudly, so the paper cannot drift from its data silently.
"""

import argparse
import os
import sys

import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("LAP_ROOT", os.path.join(HERE, ".."))
AUDIT = os.path.join(ROOT, "data", "audit.csv")
OUTDIR = os.environ.get("LAP_OUT", os.path.join(ROOT, "outputs"))

# (papers, potentially contaminated, synthetic) as the paper prints them.
EXPECTED = {
    "LA": (20, 17, 18),
    "TM": (3, 0, 3),
    "none": (1, 0, 0),
    "total": (24, 17, 21),
}

# Sub-rows in display order.  A sub-row with no paper is omitted from the table.
LA_SUBROWS = [
    ("raw regret, unnormalized", "raw"),
    ("by the oracle's cost", "oracle_cost"),
    ("by a reference policy's regret", "ref_policy_regret"),
    ("per instance (mean of ratios)", "per_instance"),
    ("by the achieved objective", "achieved_objective"),
    ("\\textbf{never stated}", "not_stated"),
]
TM_SUBROWS = [
    ("by the oracle's cost", "oracle_cost"),
    ("by a reference policy's regret", "ref_policy_regret"),
]
KNOWN_DENOMS = {d for _, d in LA_SUBROWS} | {d for _, d in TM_SUBROWS} | {"none"}


def load(path=AUDIT):
    d = pd.read_csv(path, dtype=str).fillna("")
    t = d[d.in_table1 == "yes"].copy()
    bad = t[~t.contaminated.isin(["yes", "no"]) | ~t.synthetic.isin(["yes", "no"])]
    if len(bad):
        sys.exit("audit.csv: undecided contaminated/synthetic for: " + ", ".join(bad.key))
    unknown = t[~t.denominator.isin(KNOWN_DENOMS)]
    if len(unknown):
        sys.exit("audit.csv: denominator outside the table's sub-rows for: " + ", ".join(unknown.key))
    t["c"] = t.contaminated == "yes"
    t["s"] = t.synthetic == "yes"
    return t


def counts(sub):
    return len(sub), int(sub.c.sum()), int(sub.s.sum())


def blocks(t):
    out = {o: t[t.oracle == o] for o in ("LA", "TM", "none")}
    out["total"] = t
    return out


def check(t):
    """Assert the printed totals and that every counted paper sits in exactly one sub-row."""
    ok = True
    for name, sub in blocks(t).items():
        if counts(sub) != EXPECTED[name]:
            print(f"  MISMATCH {name}: audit.csv gives {counts(sub)}, the paper prints "
                  f"{EXPECTED[name]}", file=sys.stderr)
            ok = False
    for o, rows_ in (("LA", LA_SUBROWS), ("TM", TM_SUBROWS)):
        blk = t[t.oracle == o]
        placed = sum(len(blk[blk.denominator == den]) for _, den in rows_)
        if placed != len(blk):
            print(f"  MISMATCH {o}: {len(blk) - placed} papers fall in no sub-row",
                  file=sys.stderr)
            ok = False
    print("  Table 1 matches the totals the paper prints" if ok
          else "  Table 1 DOES NOT match the paper -- update EXPECTED and the caption together",
          flush=True)
    return ok


def report(t):
    for name, sub in blocks(t).items():
        print(f"  {name:<6}{counts(sub)}")
    for o, rows_ in (("LA", LA_SUBROWS), ("TM", TM_SUBROWS)):
        for lab, den in rows_:
            sub = t[(t.oracle == o) & (t.denominator == den)]
            if len(sub):
                print(f"    {o}/{den:<20}{counts(sub)}  {' '.join(sub.key)}")


def pct(n, d):
    return "---" if d == 0 else f"{round(100 * n / d)}\\%"


def row(label, sub, bold=False, indent=0):
    n, c, s = counts(sub)
    lead = {0: "", 1: "\\quad ", 2: "\\qquad "}[indent]
    lab = f"\\textbf{{{label}}}" if bold else label
    fmt = (lambda x: f"\\textbf{{{x}}}") if bold else (lambda x: str(x))
    return f"{lead}{lab} & {fmt(n)} & {fmt(c)} ({pct(c, n)}) & {fmt(s)} ({pct(s, n)}) \\\\"


def build(t, path=None):
    path = path or os.path.join(OUTDIR, "tab_litaudit.tex")
    L, T = t[t.oracle == "LA"], t[t.oracle == "TM"]
    lines = [
        "% !TEX root = ../00_main.tex",
        "% GENERATED by code/literature_audit.py from data/audit.csv.  Do not hand-edit.",
        "% Every cell is derived from the CSV; evidence per cell in data/evidence.csv.",
        "% The float, caption and label live in 01_intro.tex; this file is the tabular only.",
        "\\begin{tabular}{@{}lrrr@{}}", "\\toprule",
        "Benchmarking metric & Papers & \\makecell[r]{Potentially\\\\contaminated} & Synthetic \\\\",
        "\\midrule",
        row("Look-Ahead Regret", L, bold=True),
    ]
    raw = L[L.denominator == "raw"]
    if len(raw):
        lines.append(row(LA_SUBROWS[0][0], raw, indent=1))
    lines.append("\\quad \\emph{normalized\\dots} & & & \\\\")
    for lab, den in LA_SUBROWS[1:]:
        sub = L[L.denominator == den]
        if len(sub):
            lines.append(row(lab, sub, indent=2))
    lines += ["\\addlinespace", row("True-Model Regret", T, bold=True),
              "\\quad \\emph{normalized\\dots} & & & \\\\"]
    for lab, den in TM_SUBROWS:
        sub = T[T.denominator == den]
        if len(sub):
            lines.append(row(lab, sub, indent=2))
    lines += ["\\addlinespace",
              row("No regret reported", t[t.oracle == "none"], bold=True),
              "\\midrule", row("Total", t, bold=True),
              "\\bottomrule", "\\end{tabular}", ""]
    os.makedirs(os.path.dirname(path), exist_ok=True)
    open(path, "w").write("\n".join(lines))
    print("wrote", os.path.normpath(path))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print every block and sub-row with its papers")
    ap.add_argument("--no-build", action="store_true")
    a = ap.parse_args()
    d = pd.read_csv(AUDIT, dtype=str).fillna("")
    t = load()
    print(f"{len(d)} papers audited, {len(t)} in Table 1, "
          f"{len(d) - len(t)} documented exclusions")
    ok = check(t)
    if a.report:
        report(t)
    if not a.no_build:
        build(t)
    sys.exit(0 if ok else 1)


if __name__ == "__main__":
    main()
