#!/usr/bin/env python3
"""Autopsy of the Elmachtoub-Grigas portfolio experiment.

Recomputes the Look-Ahead Premium directly from their generative model -- fitting
no model of any kind, since the premium is policy-independent -- and corrects the
per-replication results their replication code publishes.

USAGE
    python3 portfolio_autopsy.py --reps 50 --test 2000     # the real run (resumable)
    python3 portfolio_autopsy.py --from-cache              # rebuild the table only
    python3 portfolio_autopsy.py --selftest                # verify the cache is reproducible

Every (tau, deg, replication) cell is seeded from (BASE_SEED, tau, deg, rep), so a
cell's value does not depend on how many workers ran or in what order, and any
single cell can be recomputed on its own.  Completed cells are appended to
figs/portfolio_eta.csv as they finish; re-running skips what is already there, so
the job survives an interrupted machine.

GENERATOR, transcribed from their Julia source (NOT from Appendix D):
  solver/util.jl:253  generate_poly_kernel_data
  solver/util.jl:402  generate_poly_kernel_returns_data
  experiments/replication_functions.jl:318  portfolio_replication
  experiments/portfolio_run.jl              data_type = :poly_kernel

    X ~ N(0, I_p),  p = 5,  B* ~ Bernoulli(0.5)^{d x p},  d = 50
    rbar_j(x) = (alpha * (B* x)_j + 0.10^{1/deg})^deg,   alpha = 0.05/sqrt(p)
    r        = rbar + L f + sigma eps,  f ~ N(0,I_4),  eps ~ N(0,I_d)
    L_{jk} ~ U[-0.0025 tau, 0.0025 tau],  sigma = 0.01 tau
    c = -r,  so  f*(x) = -rbar(x)
    Sigma = L L' + sigma^2 I
    gamma = 2.25 * wbar' Sigma wbar   with   wbar = e/d          <-- THE CODE
    Z = {w : w' Sigma w <= gamma,  e'w <= 1,  w >= 0}

RISK BUDGET.  Appendix D of the paper writes wbar := e/10 and calls it "the equal
weight portfolio".  With d = 50 that vector sums to five, so it violates their own
constraint e'w <= 1 and is not the equal-weight portfolio; e/50 is.  The quadratic
form scales with ||wbar||^2, so the text implies a budget 25x looser than the code.
We follow the code.

Because w = 0 is feasible, V <= 0 throughout: V has constant sign.  Writing
W = |E[V(Y)]| and eta = LAP / W, their reported metric is Reg^LA / W and

    NReg^TM = (reported - eta) / (1 - eta).

B* and L are redrawn every replication, so Sigma, gamma and the feasible region
itself differ across replications; eta is a random variable over that ensemble,
and the standard errors we report are across replications.
"""

import argparse
import csv
import json
import os
import platform
import sys
import time
from multiprocessing import Pool

import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.environ.get("LAP_ROOT", os.path.join(HERE, ".."))
DATA = os.path.join(ROOT, "data")
OUTDIR = os.environ.get("LAP_OUT", os.path.join(ROOT, "outputs"))
CSV_IN = os.path.join(DATA, "eg", "portfolio.csv")
CACHE = os.path.join(DATA, "cache", "portfolio_eta.csv")
META = os.path.join(DATA, "cache", "portfolio_eta_meta.json")
OUT = os.path.join(OUTDIR, "tab_portfolio.tex")

BASE_SEED = 20260829
D_ASSETS, P_FEAT, N_FACTORS = 50, 5, 4
DEGREES = [1, 4, 8, 16]
TAUS = [1, 2]
N_TRAIN = 1000
METHODS = [("SPOplus", r"\textsc{spo+}"), ("LS", "least squares"),
           ("Absolute", "absolute loss"), ("RF", "random forest"),
           ("Baseline", "non-contextual")]
CACHE_COLS = ["tau", "deg", "rep", "n_test", "LAP", "W", "eta", "seconds"]


# ---------------------------------------------------------------- generator

def mean_returns(B, X, deg):
    """rbar, shape (n, d); X is (n, p)."""
    return (0.05 / np.sqrt(P_FEAT) * (X @ B.T) + 0.10 ** (1.0 / deg)) ** deg


def value_function(Sigma, gamma):
    """min c'w s.t. w'Sigma w <= gamma, e'w <= 1, w >= 0, as one reusable SOCP."""
    import cvxpy as cp
    w = cp.Variable(D_ASSETS)
    c = cp.Parameter(D_ASSETS)
    prob = cp.Problem(cp.Minimize(c @ w),
                      [cp.quad_form(w, cp.psd_wrap(Sigma)) <= gamma,
                       cp.sum(w) <= 1, w >= 0])

    def V(C):
        out = np.empty(len(C))
        for i, ci in enumerate(C):
            c.value = ci
            prob.solve(solver=cp.CLARABEL)
            out[i] = prob.value
        return out
    return V


def one_cell(task):
    """One (tau, deg, rep).  Seeded from the cell alone, never from run order."""
    tau, deg, rep, n_test = task
    t0 = time.time()
    rng = np.random.default_rng([BASE_SEED, tau, deg, rep])

    L = rng.uniform(-0.0025 * tau, 0.0025 * tau, (D_ASSETS, N_FACTORS))
    sigma = 0.01 * tau
    Sigma = L @ L.T + sigma ** 2 * np.eye(D_ASSETS)
    wbar = np.ones(D_ASSETS) / D_ASSETS            # the code, not Appendix D
    gamma = 2.25 * wbar @ Sigma @ wbar

    B = rng.binomial(1, 0.5, (D_ASSETS, P_FEAT)).astype(float)
    X = rng.normal(0, 1, (n_test, P_FEAT))
    rbar = mean_returns(B, X, deg)
    r = (rbar + rng.normal(0, 1, (n_test, N_FACTORS)) @ L.T
         + sigma * rng.normal(0, 1, (n_test, D_ASSETS)))

    V = value_function(Sigma, gamma)
    v_star = V(-rbar)                              # V(f*(x)),  f* = -rbar
    v_real = V(-r)                                 # V(Y)
    LAP = float(v_star.mean() - v_real.mean())
    W = float(-v_real.mean())                      # |E[V(Y)]|
    return dict(tau=tau, deg=deg, rep=rep, n_test=n_test, LAP=LAP, W=W,
                eta=LAP / W, seconds=round(time.time() - t0, 2))


# ---------------------------------------------------------------- cache

def read_cache(path=CACHE):
    if not os.path.exists(path):
        return pd.DataFrame(columns=CACHE_COLS)
    return pd.read_csv(path)


def append_cache(row, path=CACHE):
    new = not os.path.exists(path)
    with open(path, "a", newline="") as fh:
        wtr = csv.DictWriter(fh, fieldnames=CACHE_COLS)
        if new:
            wtr.writeheader()
        wtr.writerow({k: row[k] for k in CACHE_COLS})


def write_meta(reps, n_test, elapsed, path=META):
    import cvxpy as cp
    json.dump({
        "base_seed": BASE_SEED, "replications": reps, "test_points": n_test,
        "degrees": DEGREES, "taus": TAUS, "n_train": N_TRAIN,
        "wbar": "e/d (their code; Appendix D says e/10, see the module docstring)",
        "finished": time.strftime("%Y-%m-%d %H:%M:%S"),
        "elapsed_seconds": round(elapsed, 1),
        "python": sys.version.split()[0], "platform": platform.platform(),
        "numpy": np.__version__, "cvxpy": cp.__version__, "solver": "CLARABEL",
    }, open(path, "w"), indent=2)


def eta_table(cache, n_test=None):
    """(mean, standard error, count) per (tau, deg), across replications.

    Rows from different resolutions are never mixed: unless told otherwise we
    report the finest resolution present in the cache.
    """
    if len(cache) == 0:
        return {}
    n_test = int(cache["n_test"].max()) if n_test is None else n_test
    cache = cache[cache.n_test == n_test]
    out = {}
    for tau in TAUS:
        for deg in DEGREES:
            e = cache[(cache.tau == tau) & (cache.deg == deg)]["eta"].to_numpy()
            if len(e) == 0:
                continue
            se = e.std(ddof=1) / np.sqrt(len(e)) if len(e) > 1 else float("nan")
            out[(tau, deg)] = (e.mean(), se, len(e))
    return out


# ---------------------------------------------------------------- their data

def reported_medians(path=CSV_IN):
    df = pd.read_csv(path)
    df = df[(df.grid_dim == D_ASSETS) & (df.p_features == P_FEAT)
            & (df.n_train == N_TRAIN) & (df.polykernel_degree.isin(DEGREES))]
    med = {}
    for tau in TAUS:
        for deg in DEGREES:
            sub = df[(df.polykernel_noise_half_width == tau)
                     & (df.polykernel_degree == deg)]
            med[(tau, deg)] = {k: float(np.median(-sub[f"{k}_spoloss_test"]
                                                  / sub["zstar_avg_test"]))
                               for k, _ in METHODS}
    return med


def correct(reported, eta):
    return (reported - eta) / (1.0 - eta)


# ---------------------------------------------------------------- output

def write_table(eta, med, path=OUT):
    reps = max(v[2] for v in eta.values())
    n_test = int(read_cache()["n_test"].max())   # eta_table used this resolution
    lines = [
        "% !TEX root = ../00_main.tex",
        "% GENERATED by figs/portfolio_autopsy.py.  Do not hand-edit; edit the script",
        "% and regenerate, or rebuild from the cache with --from-cache.",
        f"% {reps} replications x {n_test} test points per regime; cache in figs/portfolio_eta.csv.",
        "\\begin{table}[t]",
        "\\centering",
        "\\caption{\\textbf{The portfolio experiment of \\citet{elmachtoub2022smart}, corrected.}",
        "For each regime, the normalized premium \\(\\eta\\) with its standard error across",
        "replications, then each method's median reported \\(\\NRegLA\\) followed by the",
        "corresponding \\(\\NRegTM\\).  Reported values are medians over their replications;",
        f"\\(\\eta\\) is recomputed from their generative model over {reps} replications of",
        f"\\((B^*, L)\\) with {n_test} test points each, fitting no model.  Corrected entries",
        "inherit the standard error of \\(\\eta\\) up to a factor \\((1-\\eta)^{-2}\\).",
        "All figures are percentages, \\(n = 1000\\); see \\cref{sec:ImplPortfolio}.}",
        "\\label{tab:Portfolio}",
        "\\footnotesize",
        "\\setlength{\\tabcolsep}{4pt}",
        "\\begin{tabular}{@{}llr" + "r@{\\,$\\to$\\,}l" * len(METHODS) + "@{}}",
        "\\toprule",
        "& & & " + " & ".join("\\multicolumn{2}{c}{%s}" % lab for _, lab in METHODS) + " \\\\",
        "\\(\\tau\\) & \\(\\mathrm{deg}\\) & \\(\\eta\\) (s.e.) & "
        + " & ".join(["rep. & corr."] * len(METHODS)) + " \\\\",
        "\\midrule",
    ]
    for tau in TAUS:
        for k, deg in enumerate(DEGREES):
            e, se, _ = eta[(tau, deg)]
            cells = [f"{100*med[(tau,deg)][key]:.2f} & {100*correct(med[(tau,deg)][key], e):.2f}"
                     for key, _ in METHODS]
            head = f"\\({tau}\\)" if k == 0 else ""
            lines.append(f"{head} & \\({deg}\\) & {100*e:.2f} ({100*se:.2f}) & "
                         + " & ".join(cells) + " \\\\")
        if tau != TAUS[-1]:
            lines.append("\\addlinespace")
    lines += ["\\bottomrule", "\\end{tabular}", "\\end{table}", ""]
    open(path, "w").write("\n".join(lines))
    print("wrote", os.path.normpath(path), flush=True)


def report(eta, med):
    print("\n  eta and corrected NReg^TM, percent", flush=True)
    for tau in TAUS:
        for deg in DEGREES:
            e, se, n = eta[(tau, deg)]
            row = "  ".join(f"{k}:{100*correct(med[(tau,deg)][k], e):6.2f}"
                            for k, _ in METHODS)
            print(f"   tau={tau} deg={deg:2d}  eta={100*e:5.2f} ({100*se:.2f}, n={n})   {row}",
                  flush=True)


# ---------------------------------------------------------------- selftest

def selftest(cache, k=2, tol=1e-7):
    """Recompute a few cached cells and check they agree.

    The draws are bit-identical for a given seed, so any discrepancy is the
    conic solver, not the sampling.  Within one solver build the agreement is
    exact; across builds it is at solver tolerance, which is why this compares
    to `tol` rather than to zero.  Reported figures are percentages of order
    1e-2, so 1e-7 on eta is far below anything the paper prints.
    """
    if len(cache) == 0:
        print("selftest: cache is empty", flush=True)
        return False
    sample = cache.sample(min(k, len(cache)), random_state=0)
    ok = True
    for _, row in sample.iterrows():
        got = one_cell((int(row.tau), int(row.deg), int(row.rep), int(row.n_test)))
        d = abs(got["eta"] - row.eta)
        flag = "ok" if d < tol else "MISMATCH"
        if d >= tol:
            ok = False
        print(f"  tau={int(row.tau)} deg={int(row.deg)} rep={int(row.rep)}: "
              f"cached {row.eta:.10f}  recomputed {got['eta']:.10f}  "
              f"delta {d:.2e}  {flag}", flush=True)
    return ok


# ---------------------------------------------------------------- main

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reps", type=int, default=50)
    ap.add_argument("--test", type=int, default=2000)
    ap.add_argument("--procs", type=int, default=os.cpu_count())
    ap.add_argument("--from-cache", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--csv", default=CSV_IN, help="their published portfolio.csv")
    ap.add_argument("--max-seconds", type=float, default=0.0,
                    help="stop dispatching new cells after this long and exit cleanly; "
                         "re-run to resume.  0 means run to completion.")
    a = ap.parse_args()

    globals()["CSV_IN"] = a.csv
    if a.selftest:
        sys.exit(0 if selftest(read_cache()) else 1)

    if not a.from_cache:
        cache = read_cache()
        done = (set(zip(cache.tau, cache.deg, cache.rep, cache.n_test))
                if len(cache) else set())
        tasks = [(t, d, r, a.test) for t in TAUS for d in DEGREES
                 for r in range(a.reps) if (t, d, r, a.test) not in done]
        print(f"{len(tasks)} cells to compute ({len(done)} already cached), "
              f"{a.test} test points, {a.procs} processes", flush=True)
        t0 = time.time()
        stopped_early = False
        if tasks:
            with Pool(a.procs) as pool:
                it = pool.imap_unordered(one_cell, tasks)
                for i, row in enumerate(it, 1):
                    append_cache(row)
                    el = time.time() - t0
                    if i % 10 == 0 or i == len(tasks):
                        print(f"  {i}/{len(tasks)} cells, {el/60:.1f} min elapsed, "
                              f"{el/i*(len(tasks)-i)/60:.1f} min left", flush=True)
                    if a.max_seconds and el > a.max_seconds:
                        stopped_early = True
                        print(f"  time budget reached at {i}/{len(tasks)} cells; "
                              f"exiting cleanly, re-run to resume", flush=True)
                        pool.terminate()
                        break
        if stopped_early:
            print("partial run; re-run to resume, then rebuild with --from-cache",
                  flush=True)
            return
        write_meta(a.reps, a.test, time.time() - t0)

    cache = read_cache()
    eta = eta_table(cache)
    med = reported_medians()
    report(eta, med)
    write_table(eta, med)


if __name__ == "__main__":
    main()
