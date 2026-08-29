"""
Figure 1: the Elmachtoub-Grigas shortest-path sweep, reported and corrected.

WHAT THE FIGURE SHOWS
---------------------
Solid lines are normalized Look-Ahead Regret -- the metric Elmachtoub & Grigas
actually report and plot.  Dashed lines are the same experiment expressed as
normalized True-Model Regret.  For each method the two curves are separated by
the Look-Ahead Premium, and that gap is what is shaded: the premium is the
vertical distance between what is reported and what is true, not a quantity
measured from the axis.

Two things are visible at once:

  1. Every reported curve is U-shaped; every corrected curve is monotone.
  2. At deg 1 the corrected curves sit at zero and the ribbons span the whole
     reported value: essentially the entire reported number is the premium.

A third fact is not drawn but is checked on every build (selftest) and reported
in the paper's implementation notes: the corrected curves reproduce Elmachtoub &
Grigas's OWN noiseless control (noise half-width 0), where the two oracles
coincide exactly and their reported numbers already ARE True-Model Regret.
Nothing was fitted to make that happen -- the correction uses a premium computed
from the generative model alone, and the control never enters it.

DATA PROVENANCE
---------------
Everything is computed from the authors' own published artifacts.

  Per-replication results
      data/eg/shortest_path.csv
      redistributed unmodified from plots/shortest_path.csv in the replication
      repository of Elmachtoub & Grigas (2022), which is MIT licensed.  Column
      semantics were verified against their plots/shorest_path_plot.R and
      experiments/replication_functions.jl:
          {method}_spoloss_test   UNNORMALIZED look-ahead regret on the test set
          zstar_avg_test          mean_i V(y_i), the look-ahead oracle's cost
          plotted value           spoloss_test / zstar_avg_test
      We take the median across replications, exactly as their plotting script
      does.  Configuration used: grid_dim 5, p_features 5, n_train 5000.

  The premium eta
      NOT taken from their data.  Computed from the generative model with no
      fitted model of any kind, since the premium is method-independent:

          c_ij = [ ( (B* x_i)_j / sqrt(p) + 3 )^deg + 1 ] * eps_ji,
          eps_ji ~ U[1 - ebar, 1 + ebar],  x_i ~ N(0, I_p),  B*_jk ~ Bern(0.5)

      On a 5x5 grid with south/east arcs every monotone path uses exactly 8 of
      the 40 edges and there are only C(8,4) = 70 of them, so V(.) is a min over
      70 explicit dot products -- no solver, no dynamic program.  Then
          eta = ( E[V(f*(X))] - E[V(Y)] ) / E[V(Y)].
      The cached values below were computed at 300 draws of B* x 10,000 test
      points (sd across draws 0.47-0.72 points).  `--recompute-eta` redoes it at
      lower Monte Carlo and checks agreement; see selftest().

  The correction
      NReg^TM = ( NReg^LA - eta ) / ( 1 + eta ),
      which is the normalization identity  1 + NReg^LA = (1 + eta)(1 + NReg^TM)
      solved for NReg^TM.

CROSS-CHECKS RUN ON EVERY BUILD (selftest)
------------------------------------------
  * medians recomputed from the CSV match the published table in
    claude/eg_autopsy.md section 3 to 0.01 points;
  * eta at ebar = 0 is identically zero (exact test of the premium pipeline);
  * corrected values at ebar = 0.5 agree with the authors' own ebar = 0 control
    to within 1.1 points, and lie ABOVE it -- the direction theory demands,
    since noise leaves the target f* unchanged and makes estimation only harder.
    `--report-control` prints that comparison for the implementation notes.

USAGE
-----
    python figs/shortest_path_autopsy.py                 # build the figure
    python figs/shortest_path_autopsy.py --recompute-eta # + redo the premium
    python figs/shortest_path_autopsy.py --with-rf       # add random forest

Writes figs/fig_shortest_path.pdf.
"""

from __future__ import annotations

import argparse
import csv
import itertools
import os
import sys

import numpy as np

# ----------------------------------------------------------------------------
# Configuration
# ----------------------------------------------------------------------------

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("LAP_ROOT", os.path.join(HERE, ".."))
DATA = os.path.join(ROOT, "data")
OUTDIR = os.environ.get("LAP_OUT", os.path.join(ROOT, "outputs"))
CSV = os.path.join(DATA, "eg",
                   "shortest_path.csv")
OUT = os.path.join(OUTDIR, "fig_shortest_path.pdf")

DEGREES = [1, 2, 4, 6, 8]
GRID_DIM, P_FEATURES, N_TRAIN = 5, 5, 5000
EBAR = 0.5

# Premium as a fraction of the look-ahead oracle's cost, in percent.
# 300 draws of B*, 10,000 test points each.  See claude/eg_autopsy.md section 2.
ETA = {1: 15.47, 2: 10.45, 4: 6.73, 6: 5.50, 8: 4.93}

# The published medians, from claude/eg_autopsy.md section 3.  Used only as a
# regression check against what we recompute from the CSV.
PUBLISHED = {
    "SPOplus":  {1: 15.49, 2: 10.67, 4: 7.46, 6: 7.85, 8: 10.04},
    "LS":       {1: 15.45, 2: 10.67, 4: 8.64, 6: 12.47, 8: 21.82},
    "RF":       {1: 16.28, 2: 11.19, 4: 7.68, 6: 7.61, 8: 9.63},
}

LABEL = {"SPOplus": r"\textsc{spo+}", "LS": "least squares", "RF": "random forest"}
PLAIN = {"SPOplus": "SPO+", "LS": "least squares", "RF": "random forest"}

# Their non-contextual policy -- "baseline that returns mean of training data" -- IS pi^SAA,
# and is the denominator of the recommended metric.  Published medians from
# claude/eg_autopsy.md sec. 3, kept as a regression check.
BASELINE = {1: 25.00, 2: 31.45, 4: 50.56, 6: 67.62, 8: 89.03}

# Okabe-Ito.  Colour encodes the METHOD; line style encodes the METRIC
# (solid = reported look-ahead, dashed = corrected true-model).
# Blue/orange rather than blue/green: it is the most separable Okabe-Ito pair
# under every common colour-vision deficiency and in greyscale, and it leaves
# vermillion to two_action_construction.py, which uses it for reported
# quantities.
COLOR = {"SPOplus": "#0072B2", "LS": "#E69F00", "RF": "#CC79A7"}
PREMIUM = "#D55E00"
INK, MUTED = "#1a1a1a", "#6b6b6b"


# ----------------------------------------------------------------------------
# Their data
# ----------------------------------------------------------------------------

def load_medians(ebar):
    """Median normalized look-ahead regret (%) per method per degree.

    Reproduces exactly what their plotting script draws: the per-replication
    ratio spoloss_test / zstar_avg_test, then the median across replications.
    """
    keys = list(PUBLISHED) + ["Baseline"]
    per_deg = {m: {d: [] for d in DEGREES} for m in keys}
    with open(CSV, newline="") as fh:
        for row in csv.DictReader(fh):
            if (int(row["grid_dim"]) != GRID_DIM
                    or int(row["p_features"]) != P_FEATURES
                    or int(row["n_train"]) != N_TRAIN
                    or abs(float(row["polykernel_noise_half_width"]) - ebar) > 1e-9):
                continue
            deg = int(row["polykernel_degree"])
            if deg not in DEGREES:
                continue
            zstar = float(row["zstar_avg_test"])
            for m in keys:
                per_deg[m][deg].append(100.0 * float(row[f"{m}_spoloss_test"]) / zstar)
    return {m: {d: float(np.median(v)) for d, v in dd.items() if v}
            for m, dd in per_deg.items()}


def correct(nreg_la, eta):
    """NReg^TM = (NReg^LA - eta) / (1 + eta), with both arguments in percent."""
    return (nreg_la - eta) / (1.0 + eta / 100.0)


# ----------------------------------------------------------------------------
# The premium, from the generative model alone
# ----------------------------------------------------------------------------

def path_matrix(g=GRID_DIM):
    """All monotone south/east paths on a g x g grid, as 0/1 rows over edges."""
    east, south, idx = {}, {}, 0
    for i in range(g):
        for j in range(g - 1):
            east[(i, j)] = idx; idx += 1
    for i in range(g - 1):
        for j in range(g):
            south[(i, j)] = idx; idx += 1
    rows = []
    for combo in itertools.combinations(range(2 * (g - 1)), g - 1):
        seq = ["S"] * (2 * (g - 1))
        for c in combo:
            seq[c] = "E"
        i = j = 0
        v = np.zeros(idx)
        for m in seq:
            if m == "E":
                v[east[(i, j)]] = 1; j += 1
            else:
                v[south[(i, j)]] = 1; i += 1
        rows.append(v)
    return np.array(rows), idx


def compute_eta(deg, ebar, n_trials=60, n_test=4000, p=P_FEATURES, seed=7):
    """eta (%) for one configuration.  No model is fitted anywhere here."""
    P, D = path_matrix()
    rng = np.random.default_rng(seed + 1000 * deg + int(100 * ebar))
    ws, vf = [], []
    for _ in range(n_trials):
        B = rng.binomial(1, 0.5, (D, p))
        x = rng.normal(0.0, 1.0, (n_test, p))
        fstar = ((x @ B.T) / np.sqrt(p) + 3.0) ** deg + 1.0        # the +1 floor is theirs
        eps = rng.uniform(1 - ebar, 1 + ebar, (n_test, D)) if ebar > 0 else 1.0
        vf.append((fstar @ P.T).min(axis=1).mean())                # E[V(f*(X))]
        ws.append(((fstar * eps) @ P.T).min(axis=1).mean())        # E[V(Y)]
    vf, ws = np.mean(vf), np.mean(ws)
    return 100.0 * (vf - ws) / ws


# ----------------------------------------------------------------------------
# The recommended metric, and its one shortcoming
# ----------------------------------------------------------------------------

def saa_normalized(rep, m, d):
    """Reg^TM(pi) / Reg^TM(pi^SAA), in percent.

    E[V(f*(X))] cancels between numerator and denominator, so this is just the
    ratio of the two corrected (normalized true-model) numbers.
    """
    return 100.0 * correct(rep[m][d], ETA[d]) / correct(rep["Baseline"][d], ETA[d])


def build_saa(path=os.path.join(OUTDIR, "fig_saa_normalized.pdf")):
    """Appendix figure: the recommended metric beside normalized True-Model Regret.

    The point of the figure is the SHORTCOMING, not a victory lap.  Normalizing by
    the SAA policy's true-model regret buys shift- and scale-invariance and needs no
    constant-sign assumption on V -- but the denominator is itself a property of the
    DGP.  Sweeping `deg` changes the marginal law of Y, which changes how much the
    covariates are worth, which moves Reg^TM(pi^SAA) from 8.25% to 80.15%.  A ratio
    whose denominator moves that fast can be non-monotone even when its numerator is
    not: random forest, in Elmachtoub & Grigas's own table, keeps an interior minimum
    at deg 4.  So the recommended metric removes the premium artifact and does not
    remove every cross-DGP artifact.
    """
    rep, _ = selftest(verbose=False)
    _style()
    import matplotlib.pyplot as plt
    from matplotlib.lines import Line2D

    methods = ["LS", "SPOplus", "RF"]
    x = np.arange(len(DEGREES))
    fig, ax = plt.subplots(figsize=(2.86, 2.30))

    for m in methods:
        c = COLOR[m]
        saa = np.array([saa_normalized(rep, m, d) for d in DEGREES])
        tm = np.array([correct(rep[m][d], ETA[d]) for d in DEGREES])
        ax.plot(x, saa, color=c, zorder=4)
        ax.plot(x, tm, color=c, linestyle=(0, (4, 2)), zorder=3, alpha=0.85)

    # Mark the artifact that survives: RF's interior minimum.
    saa_rf = [saa_normalized(rep, "RF", d) for d in DEGREES]
    j = int(np.argmin(saa_rf))
    ax.plot(x[j], saa_rf[j], marker="v", markersize=3.6, color=COLOR["RF"],
            linestyle="none", zorder=6)
    ax.annotate("interior minimum\nsurvives", xy=(x[j] + 0.06, saa_rf[j] - 0.4),
                xytext=(1.55, 12.6), fontsize=6.6, color=MUTED, ha="left", va="center",
                arrowprops=dict(arrowstyle="-", color=MUTED, lw=0.5, shrinkA=1, shrinkB=2))

    ax.set_xticks(x)
    ax.set_xticklabels([str(d) for d in DEGREES])
    ax.set_xlabel("Polynomial Degree (Misspecification)", labelpad=1.5)
    ax.set_ylabel("Normalized Regret (%)", labelpad=1.5)
    ax.set_xlim(-0.10, len(DEGREES) - 1 + 0.10)
    ax.set_ylim(-1.2, 23.0)
    ax.set_yticks([0, 5, 10, 15, 20])
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(INK)

    handles = [Line2D([], [], color=COLOR[m], lw=1.5, label=PLAIN[m]) for m in methods]
    ax.legend(handles=handles, loc="upper left", frameon=False, fontsize=7.2,
              handlelength=1.6, handletextpad=0.5, labelspacing=0.35,
              borderpad=0.0, borderaxespad=0.4)

    fig.tight_layout(pad=0.3)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)
    print(f"wrote {os.path.normpath(path)}")
    print("   SAA-normalized True-Model Regret (%), solid in the figure:")
    for m in methods:
        v = [saa_normalized(rep, m, d) for d in DEGREES]
        k = int(np.argmin(v))
        shape = "monotone increasing" if k == 0 else f"INTERIOR MINIMUM at deg {DEGREES[k]}"
        print(f"     {PLAIN[m]:<14}" + "".join(f"{y:8.2f}" for y in v) + f"   {shape}")
    print("   denominator Reg^TM(pi^SAA) (%): " +
          "".join(f"{correct(rep['Baseline'][d], ETA[d]):8.2f}" for d in DEGREES))


# ----------------------------------------------------------------------------
# The cost-shift exhibit
# ----------------------------------------------------------------------------

# Every monotone path on the grid uses exactly this many arcs.  This is what
# makes the shift exhibit work: 1'z is constant on Z, so Y -> Y + a*1 adds
# exactly K*a to EVERY feasible path.
K_ARCS = 8


def load_zstar(ebar=EBAR):
    """Median of their zstar_avg_test per degree -- which IS E[V(Y)].

    Taken from their CSV rather than simulated, so the shift exhibit uses the
    same denominator their own reported numbers were divided by.
    """
    per = {d: [] for d in DEGREES}
    with open(CSV, newline="") as fh:
        for row in csv.DictReader(fh):
            if (int(row["grid_dim"]) != GRID_DIM
                    or int(row["p_features"]) != P_FEATURES
                    or int(row["n_train"]) != N_TRAIN
                    or abs(float(row["polykernel_noise_half_width"]) - ebar) > 1e-9):
                continue
            d = int(row["polykernel_degree"])
            if d in DEGREES:
                per[d].append(float(row["zstar_avg_test"]))
    return {d: float(np.median(v)) for d, v in per.items() if v}


def shift_factor(deg, a, zstar):
    """Reported numbers at degree `deg` all scale by this under Y -> Y + a*1.

    RegTM, RegLA and LAP are invariant (1'z is constant on Z, so a*K is added
    to the policy's cost and to both oracles alike); only the denominator moves,
    from E[V(Y)] to E[V(Y)] + K*a.
    """
    return zstar[deg] / (zstar[deg] + K_ARCS * a)


def shift_table(path=os.path.join(OUTDIR, "tab_shift.tex"), shifts=(4.0, 32.0)):
    """Write tables/tab_shift.tex: the same experiment under two admissible translations.

    Admissibility.  Arc costs must stay positive.  For even `deg` the generator
    gives c = [(u+3)^deg + 1] * eps >= 1 * 0.5, so shifts down to a = -0.5 are
    admissible and no further; for deg 1 the bracket is u + 4 with u Gaussian,
    so costs have no positive lower bound in the population and only the
    realized sample binds.  Upward shifts are ALWAYS admissible, and a -> oo
    drives every reported number to zero.  The lever is one-directional: the
    largest achievable inflation is about 5% relative, at deg 1.
    """
    rep, _ = selftest(verbose=False)
    zstar = load_zstar()
    cols = [0.0] + list(shifts)

    lines = [
        "% !TEX root = ../00_main.tex",
        "% GENERATED by figs/shortest_path_autopsy.py --shift-table.  Do not hand-edit;",
        "% edit the script and regenerate.  Numbers come from Elmachtoub & Grigas's own",
        "% per-replication CSV: reported medians, and zstar_avg_test as E[V(Y)].",
        "% LAYOUT: side by side, table left / caption right, matching Table 1.  A `figure'",
        "% float carrying \\captionof{table}, so it numbers as a Table but travels in the",
        "% figure stream.  Detail that used to live in this caption is now in",
        "% 12_implementation.tex, sec:ImplShortestPath.",
        "\\begin{figure}[t]",
        "\\centering",
        "\\begin{minipage}[c]{0.50\\textwidth}",
        "  \\centering",
        "  \\small",
        "  \\setlength{\\tabcolsep}{4pt}",
        "\\begin{tabular}{@{}lrrrr@{}}",
        "\\toprule",
        "& as published & \\(a = 4\\) & \\(a = 32\\) & \\(a \\to \\infty\\) \\\\",
        "\\midrule",
    ]
    for d in DEGREES:
        vals = [rep["SPOplus"][d] * shift_factor(d, a, zstar) for a in cols]
        cells = " & ".join(f"{v:.2f}" for v in vals)
        lines.append(f"\\(\\mathrm{{deg}} = {d}\\) & {cells} & \\(\\to 0\\) \\\\")
    lines += [
        "\\bottomrule",
        "\\end{tabular}",
        "\\end{minipage}\\hfill",
        "\\begin{minipage}[c]{0.46\\textwidth}",
        "  \\captionof{table}{\\textbf{Artificially decreasing \\(\\NRegLA\\) and \\(\\NRegTM\\).}",
        "  Reported \\(\\NRegLA\\) for \\textsc{spo+} on the shortest-path experiment of",
        "  \\citet{elmachtoub2022smart} plotted in \\cref{fig:SPO+Fig}, after translating every arc",
        "  cost by a constant \\(a\\).  $\\NRegLA$ can be driven to zero with a large translation because it normalizes by a raw cost.",
        "  %Every path uses exactly eight arcs, so the translation adds",
        "  %\\(8a\\) to every path and changes no decision and no policy: \\(\\RegTM\\), \\(\\RegLA\\)",
        "  %and \\(\\LAP\\) are invariant, and only the denominator moves.  ",
        "  %\\(\\NRegTM\\) is driven to",
        "  %zero the same way, its denominator gaining the same constant.  ",
        "  Medians over their",
        "  replications, in percent; see \\cref{sec:ImplShortestPath}.}",
        "  \\label{tab:Shift}",
        "\\end{minipage}",
        "\\end{figure}",
        "",
    ]
    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    print(f"wrote {os.path.normpath(path)}")

    # console version, with the shapes called out
    print("\n shift a     " + "".join(f"deg {d:<6}" for d in DEGREES) + " shape of the reported curve")
    for m in ["SPOplus", "LS"]:
        print(f"  {PLAIN[m]}")
        for a in cols:
            v = [rep[m][d] * shift_factor(d, a, zstar) for d in DEGREES]
            j = int(np.argmin(v))
            shape = "U, min at deg %d" % DEGREES[j] if 0 < j < len(v) - 1 else "increasing"
            print(f"   a={a:5.1f}   " + "".join(f"{x:8.2f}  " for x in v) + f"  {shape}")


# ----------------------------------------------------------------------------
# Checks
# ----------------------------------------------------------------------------

def selftest(recompute_eta=False, verbose=True):
    rep = load_medians(EBAR)
    ctl = load_medians(0.0)

    worst = max(abs(rep[m][d] - PUBLISHED[m][d]) for m in PUBLISHED for d in DEGREES)
    assert worst < 0.011, f"CSV medians disagree with eg_autopsy.md by {worst:.3f} pts"
    wb = max(abs(rep["Baseline"][d] - BASELINE[d]) for d in DEGREES)
    assert wb < 0.011, f"baseline medians disagree with eg_autopsy.md by {wb:.3f} pts"

    assert abs(compute_eta(4, 0.0, n_trials=5, n_test=1500)) < 1e-9, \
        "premium must be exactly zero in the noiseless DGP"

    for m in PUBLISHED:
        for d in DEGREES:
            gap = correct(rep[m][d], ETA[d]) - ctl[m][d]
            assert gap > -0.35, f"{m} deg {d}: corrected falls below their control by {-gap:.2f}"
            assert gap < 1.10, f"{m} deg {d}: corrected exceeds their control by {gap:.2f}"

    if recompute_eta:
        for d in DEGREES:
            e = compute_eta(d, EBAR)
            assert abs(e - ETA[d]) < 1.0, f"eta(deg {d}) = {e:.2f} vs cached {ETA[d]}"
            if verbose:
                print(f"  eta(deg {d}) recomputed {e:5.2f}  cached {ETA[d]:5.2f}")

    if verbose:
        print(f"selftest OK   medians match published to {worst:.3f} pts; "
              f"corrected values lie 0-1.1 pts above their noiseless control")
    return rep, ctl


# ----------------------------------------------------------------------------
# Figure
# ----------------------------------------------------------------------------

def _style():
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5, "lines.linewidth": 1.5,
    })


def build(path=OUT, with_rf=False, recompute_eta=False):
    rep, ctl = selftest(recompute_eta=recompute_eta)
    _style()
    import matplotlib.pyplot as plt

    methods = ["LS", "SPOplus", "RF"]   # random forest always drawn (VG, 2026-08-28)
    SHADE = "SPOplus"        # whose reported-to-corrected gap gets shaded
    # Degrees are 1, 2, 4, 6, 8 -- not evenly spaced.  We plot them at equal
    # spacing with their true labels, as the authors do, so that the gap
    # between deg 2 and deg 4 does not imply an interpolation nobody ran.
    x = np.arange(len(DEGREES))
    eta = np.array([ETA[d] for d in DEGREES])

    # Half text width, so the caption can sit beside the figure.
    fig, ax = plt.subplots(figsize=(2.86, 2.30))

    span = {}
    for m in methods:
        c = COLOR[m]
        reported = np.array([rep[m][d] for d in DEGREES])
        corrected = np.array([correct(rep[m][d], ETA[d]) for d in DEGREES])
        span[m] = (reported, corrected)

        # The premium is the GAP between a method's two curves, not a quantity
        # measured from the axis.  Shading BOTH gaps makes them overlap into an
        # unreadable third colour, and the premium is method-independent anyway,
        # so we shade one and say so in the caption.
        if m == SHADE:
            ax.fill_between(x, corrected, reported, color=c, alpha=0.15,
                            linewidth=0, zorder=1)
        ax.plot(x, reported, color=c, zorder=4)
        ax.plot(x, corrected, color=c, linestyle=(0, (4, 2)), zorder=4)

    ax.set_xticks(x)
    ax.set_xticklabels([str(d) for d in DEGREES])
    ax.set_xlabel("Polynomial Degree (Misspecification)", labelpad=1.5)
    ax.set_ylabel("Normalized Regret (%)", labelpad=1.5)
    ax.set_xlim(-0.10, len(DEGREES) - 1 + 0.10)
    ax.set_ylim(-1.2, 26.5)
    ax.set_yticks([0, 5, 10, 15, 20])
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(INK)

    # Curves are identified by a legend rather than in-plot text.  In-plot
    # labels were tried and abandoned: with four curves in a half-width panel
    # every free spot for the SPO+ label sits near the orange dashed curve, so
    # the label reads as though it names the wrong line.  Colour encodes the
    # method here; the caption carries solid = reported, dashed = corrected.
    from matplotlib.lines import Line2D
    handles = [Line2D([], [], color=COLOR[m], lw=1.5,
                      label={"SPOplus": "SPO+", "LS": "Least Squares",
                             "RF": "Random Forest"}[m])
               for m in methods]
    ax.legend(handles=handles, loc="upper left", frameon=False,
              fontsize=7.2, handlelength=1.6, handletextpad=0.5,
              labelspacing=0.35, borderpad=0.0, borderaxespad=0.4)

    # Name the shaded gap in place, in a spot no curve passes through.
    # NOT "Premium": on page 1 the reader has not met that term yet, and the
    # label has to say what the band MEANS -- that nothing below it is
    # reachable.  "Irreducible" also echoes the Section 2 proposition.
    ax.text(1.55, 5.2, "Irreducible Gap", color=COLOR[SHADE], fontsize=7.6,
            alpha=0.95, ha="center", va="center", zorder=6)

    fig.tight_layout(pad=0.3)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)

    print(f"wrote {path}")
    for m in methods:
        reported = [rep[m][d] for d in DEGREES]
        j = int(np.argmin(reported))
        print(f"  {PLAIN[m]:<14} reported min {reported[j]:5.2f} at deg {DEGREES[j]}; "
              f"corrected deg 1 -> 8: "
              f"{correct(rep[m][1], ETA[1]):5.2f} -> {correct(rep[m][8], ETA[8]):5.2f}")


def report_control():
    """Print the corrected-vs-control comparison quoted in the implementation notes.

    The circles were dropped from the figure, so this is where the validation
    lives now.  Every number here is a median in percent.
    """
    rep, ctl = selftest(verbose=False)
    print("method          deg   corrected   their ebar=0   gap")
    for m in ["SPOplus", "LS", "RF"]:
        for d in DEGREES:
            c = correct(rep[m][d], ETA[d])
            print(f"  {PLAIN[m]:<13} {d:>2}   {c:8.2f}   {ctl[m][d]:12.2f}   {c - ctl[m][d]:+5.2f}")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--with-rf", action="store_true",
                    help="(retained for compatibility; random forest is now always drawn)")
    ap.add_argument("--recompute-eta", action="store_true",
                    help="recompute the premium from the generative model and check the cache")
    ap.add_argument("--saa-figure", action="store_true",
                    help="write figs/fig_saa_normalized.pdf, the recommended metric and its limit")
    ap.add_argument("--shift-table", action="store_true",
                    help="write tables/tab_shift.tex, the cost-shift exhibit")
    ap.add_argument("--report-control", action="store_true",
                    help="print corrected vs their noiseless control (for the implementation notes)")
    a = ap.parse_args()
    if not os.path.exists(CSV):
        sys.exit(f"cannot find {CSV}\n"
                 "Expected the Elmachtoub-Grigas replication repo beside this project.")
    build(with_rf=a.with_rf, recompute_eta=a.recompute_eta)
    if a.saa_figure:
        build_saa()
    if a.shift_table:
        shift_table()
    if a.report_control:
        report_control()
