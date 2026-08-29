"""
The two-action construction: True-Model Regret monotone, Look-Ahead Regret U-shaped.

Every reported quantity is computed by Monte Carlo from the primitives below; no
closed-form expression for the premium is used anywhere in the pipeline.
`selftest` checks the simulator against the analytic value of the premium at the
one point where it is a one-line integral.

Setup
-----
    Feasible set   Z = {e_1, e_2},  so  V(t) = min(t_1, t_2)
    Context        X in {A, B},  P(X = B) = q
    Conditional    f*(A) = (1, kappa),   f*(B) = (kappa, 1)
      means        kappa >= 1 is the separation of the two actions; it is the
                   swept parameter, the analogue of `deg` in Elmachtoub-Grigas.
    Outcome        Y = f*(X) * (1 + eps),  eps_j iid U[-ebar, ebar], independent
                   of X.  Multiplicative unit-mean uniform noise, matching the
                   Elmachtoub-Grigas generator.

Because z*(f*(A)) = e_1 and z*(f*(B)) = e_2 both cost exactly 1, the true-model
oracle costs 1 for every (kappa, q, ebar).  The natural normalizer is therefore
constant and normalized and absolute quantities coincide: no normalization
artifact can be mistaken for the premium.

The policy under study is the best NON-CONTEXTUAL policy -- the hypothesis class
is the constants, so the policy cannot see X.  This is the same object as the SAA
baseline, and as the "baseline that returns mean of training data" column in the
Elmachtoub-Grigas shortest-path CSV.  It is not "decision-blind": it is blind to
the context, not to the decision problem.

Quantities, in the notation of notation.md:
    E[V(f*(X))]        cost of the true-model oracle          (identically 1 here)
    E[V(Y)]            cost of the look-ahead oracle
    LAP               = E[V(f*(X))] - E[V(Y)]                  >= 0
    RegTM(pi)         = E[<Y, pi(X)>] - E[V(f*(X))]
    RegLA(pi)         = E[<Y, pi(X)>] - E[V(Y)] = RegTM(pi) + LAP

Running this module writes outputs/fig_two_action.pdf.
"""

from __future__ import annotations

import os
import numpy as np

Q = 0.05          # probability of the "hard" context
EBAR_DGP = 0.5    # noise held fixed while the DGP is swept
KAPPA_NOISE = 2.0 # separation held fixed while the noise is swept
N = 2_000_000     # Monte Carlo draws

# ----------------------------------------------------------------------------
# Primitives
# ----------------------------------------------------------------------------

def draw_sample(n, q, seed=0):
    """Draw (X, eps) once, to be reused across a whole sweep.

    Holding the draw fixed across the sweep (common random numbers) is what
    makes the swept curves smooth: sampling error is shared across grid points
    rather than independent at each one.  `eps` is returned on the unit scale
    and multiplied by ebar at use time, so the same draw serves every noise
    width as well.
    """
    rng = np.random.default_rng(seed)
    is_b = rng.random(n) < q                          # X = B indicator
    eps = rng.uniform(-1.0, 1.0, size=(n, 2))
    return is_b, eps


def evaluate(kappa, ebar, is_b, eps):
    """All four quantities at one (kappa, ebar).  Nothing here uses a closed form."""
    n = is_b.size

    # Conditional means f*(X): (1, kappa) on A, (kappa, 1) on B.
    fstar = np.empty((n, 2))
    fstar[:, 0] = np.where(is_b, kappa, 1.0)
    fstar[:, 1] = np.where(is_b, 1.0, kappa)

    y = fstar * (1.0 + ebar * eps)

    v_true_model = fstar.min(axis=1).mean()           # E[V(f*(X))]
    v_look_ahead = y.min(axis=1).mean()               # E[V(Y)]

    # Best non-contextual policy: the constant predictor's induced action is the
    # argmin of the sample mean of Y, and its expected cost is that column's mean.
    col_means = y.mean(axis=0)
    cost = col_means[int(np.argmin(col_means))]

    return {"LAP": v_true_model - v_look_ahead,
            "RegTM": cost - v_true_model,
            "RegLA": cost - v_look_ahead,
            "E_V_fstar": v_true_model,
            "E_V_Y": v_look_ahead}


def sweep(kappas, ebars, q=Q, n=N, seed=0):
    """Evaluate along a sweep.  Exactly one of kappas, ebars may be an array."""
    kappas, ebars = np.broadcast_arrays(np.atleast_1d(kappas), np.atleast_1d(ebars))
    is_b, eps = draw_sample(n, q, seed)
    rows = [evaluate(k, e, is_b, eps) for k, e in zip(kappas, ebars)]
    out = {k: np.array([r[k] for r in rows]) for k in rows[0]}
    out["kappa"], out["ebar"] = kappas, ebars
    return out


# ----------------------------------------------------------------------------
# Figure
# ----------------------------------------------------------------------------

TRUE = "#0072B2"      # True-Model Regret   (Okabe-Ito blue)
REPORTED = "#D55E00"  # Look-Ahead Regret   (Okabe-Ito vermillion)
INK, MUTED = "#1a1a1a", "#6b6b6b"


def _style():
    import matplotlib.pyplot as plt
    plt.rcParams.update({
        "font.family": "serif",
        "font.serif": ["Times New Roman", "STIXGeneral", "DejaVu Serif"],
        "mathtext.fontset": "stix",
        "font.size": 8, "axes.labelsize": 8, "axes.titlesize": 8,
        "xtick.labelsize": 7, "ytick.labelsize": 7,
        "axes.linewidth": 0.6, "xtick.major.width": 0.6, "ytick.major.width": 0.6,
        "xtick.major.size": 2.5, "ytick.major.size": 2.5, "lines.linewidth": 1.6,
    })


def _panel(ax, x, d, xlabel, title, fixed):
    """One panel: the two regret curves with the premium shaded between them."""
    ax.fill_between(x, d["RegTM"], d["RegLA"], color=REPORTED, alpha=0.16,
                    linewidth=0, zorder=1)
    ax.plot(x, d["RegLA"], color=REPORTED, zorder=3)
    ax.plot(x, d["RegTM"], color=TRUE, zorder=3)

    ax.set_xlabel(xlabel)
    ax.set_title(title, pad=5)
    ax.set_xlim(x.min(), x.max())
    ax.set_ylim(0, 0.205)
    ax.set_yticks([0.00, 0.05, 0.10, 0.15, 0.20])
    ax.spines[["top", "right"]].set_visible(False)
    ax.spines[["left", "bottom"]].set_color(MUTED)
    ax.grid(axis="y", color="#e6e6e6", linewidth=0.5, zorder=0)
    ax.set_axisbelow(True)
    ax.tick_params(colors=MUTED)
    for lbl in ax.get_xticklabels() + ax.get_yticklabels():
        lbl.set_color(INK)
    ax.text(0.97, 0.05, fixed, transform=ax.transAxes, fontsize=7,
            color=MUTED, ha="right", va="bottom")


def _lap_label(ax, x, d, at):
    """Put 'LAP' inside the shaded band, centred on it."""
    i = int(np.argmin(np.abs(x - at)))
    ax.text(x[i], 0.5 * (d["RegTM"][i] + d["RegLA"][i]), "LAP", color=REPORTED,
            fontsize=7, alpha=0.9, ha="center", va="center", zorder=4)


_HERE = os.path.dirname(os.path.abspath(__file__))
_OUTDIR = os.environ.get("LAP_OUT",
                         os.path.join(os.environ.get("LAP_ROOT",
                                                     os.path.join(_HERE, "..")), "outputs"))


def build(path=None):
    path = path or os.path.join(_OUTDIR, "fig_two_action.pdf")
    _style()
    import matplotlib.pyplot as plt

    kappas = np.linspace(1.0, 4.0, 121)
    ebars = np.linspace(0.0, 0.95, 96)
    a = sweep(kappas, EBAR_DGP)
    b = sweep(KAPPA_NOISE, ebars)

    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(5.5, 2.45))

    _panel(ax1, kappas, a, r"separation $\kappa$", "(a) Changing DGP",
           r"$\bar\varepsilon = 0.5$")
    ax1.set_ylabel("regret")
    ax1.text(1.09, 0.184, "Look-Ahead Regret", color=REPORTED, fontsize=7.2,
             ha="left", va="center")
    ax1.text(2.45, 0.026, "True-Model Regret", color=TRUE, fontsize=7.2,
             ha="center", va="center")
    _lap_label(ax1, kappas, a, 1.52)

    _panel(ax2, ebars, b, r"noise half-width $\bar\varepsilon$",
           "(b) Increasing Noise", r"$\kappa = 2$")
    ratio = b["RegLA"][-1] / b["RegTM"][-1]
    ax2.annotate("", xy=(0.90, b["RegLA"][-6]), xytext=(0.90, b["RegTM"][-6]),
                 arrowprops=dict(arrowstyle="<->", color=MUTED, lw=0.6,
                                 shrinkA=0, shrinkB=0))
    ax2.text(0.87, 0.5 * (b["RegLA"][-6] + b["RegTM"][-6]),
             f"${ratio:.1f}" + r"\times$", fontsize=7, color=MUTED,
             ha="right", va="center")
    ax2.text(0.04, 0.176, "Look-Ahead Regret", color=REPORTED, fontsize=7.2,
             ha="left", va="center")
    ax2.text(0.04, 0.030, "True-Model Regret", color=TRUE, fontsize=7.2,
             ha="left", va="center")
    _lap_label(ax2, ebars, b, 0.70)

    fig.tight_layout(pad=0.35, w_pad=1.6)
    fig.savefig(path, bbox_inches="tight")
    plt.close(fig)

    j = int(np.argmin(a["RegLA"]))
    print(f"wrote {path}")
    print(f"  (a) RegLA falls {a['RegLA'][0] / a['RegLA'][j]:.2f}x to a minimum at "
          f"kappa = {kappas[j]:.2f}; RegTM rises to {a['RegTM'][-1]:.4f}")
    print(f"  (b) RegTM flat at {b['RegTM'].max():.5f}; "
          f"RegLA {b['RegLA'][0]:.5f} -> {b['RegLA'][-1]:.5f}  ({ratio:.2f}x)")


# ----------------------------------------------------------------------------
# Pipeline check
# ----------------------------------------------------------------------------

def selftest(tol=2e-3):
    """1. The true-model oracle costs exactly 1 at every kappa.
       2. At kappa = 1 the premium is E[(eps_1 - eps_2)^+] = ebar/3 -- the one
          point where the integral is a single line.
       3. The decomposition RegLA = RegTM + LAP holds to machine precision.
    """
    s = sweep([1.0, 1.5, 2.0, 3.0], 0.5)
    assert np.allclose(s["E_V_fstar"], 1.0), s["E_V_fstar"]
    assert abs(s["LAP"][0] - 0.5 / 3.0) < tol, s["LAP"][0]
    assert np.allclose(s["RegLA"], s["RegTM"] + s["LAP"], atol=1e-12)
    print(f"selftest OK   E[V(f*)] = {s['E_V_fstar'][0]:.6f}   "
          f"LAP(kappa=1) = {s['LAP'][0]:.5f}  (analytic {0.5 / 3:.5f})")


if __name__ == "__main__":
    selftest()
    build()
