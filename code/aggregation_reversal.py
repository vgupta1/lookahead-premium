#!/usr/bin/env python3
"""Does a mean of ratios reverse a ranking on a generator this literature actually uses?

\\Cref{ex:Reversal} in the paper is four numbers chosen to make the mechanism visible.
This script asks the same question of the shortest-path generator of Elmachtoub &
Grigas (2022), which \\textsc{PredOpt} also adopts, using two methods that appear in
their own figure.

GENERATOR, transcribed from their Julia source (the same transcription
shortest_path_autopsy.py uses for the premium):

    x ~ N(0, I_p),  B*_{jk} ~ Bern(0.5),  p = 5,  5 x 5 grid (40 arcs, 70 paths)
    c_ij = [ ((B* x_i)_j / sqrt(p) + 3)^deg + 1 ] * eps_ji,  eps ~ U[1-ebar, 1+ebar]

METHODS.  Ordinary least squares and a random forest, both fit here.  We do NOT
reimplement \\textsc{spo+}: that needs their Julia solver, and the point does not
depend on it.  A shrunk least squares and the non-contextual policy are included as
a spread of quality levels.

PER-INSTANCE QUANTITIES.  For a policy pi,
    r_i = <y_i, pi(x_i)> - V(y_i),    V(y_i) = min over the 70 paths,
and the two aggregations are  sum_i r_i / sum_i V(y_i)  (ratio of sums) and
mean_i r_i / V(y_i)  (mean of ratios).  A *reversal* is a pair of methods that the
two aggregations order differently.

WHAT IT FINDS.  At deg 8 the ratio of sums prefers the random forest in every
replication, while the mean of ratios prefers least squares in a quarter of them.
The mean of ratios is also far noisier across replications, because instances with
small V(y) dominate it.

USAGE
    python3 aggregation_reversal.py                 # one replication, every degree
    python3 aggregation_reversal.py --deg 8 --reps 8
"""

import argparse
import itertools
import os
import sys

import numpy as np

BASE_SEED = 20260830
GRID, P_FEATURES, EBAR = 5, 5, 0.5
N_TRAIN, N_TEST = 5000, 10000
DEGREES = [1, 2, 4, 6, 8]
METHODS = ["OLS", "RF", "shrunkOLS", "noncontextual"]


def path_matrix(g=GRID):
    """Every monotone path on a g x g grid, as 0/1 rows over the arc list."""
    arcs, idx = [], {}
    for i in range(g):
        for j in range(g):
            for nxt in (((i, j + 1)) if j + 1 < g else None,
                        ((i + 1, j)) if i + 1 < g else None):
                if nxt is not None:
                    idx[((i, j), nxt)] = len(arcs)
                    arcs.append(((i, j), nxt))
    rows = []
    for combo in itertools.combinations(range(2 * (g - 1)), g - 1):
        seq = ["D"] * (2 * (g - 1))
        for c in combo:
            seq[c] = "R"
        r = np.zeros(len(arcs))
        i = j = 0
        for m in seq:
            nxt = (i, j + 1) if m == "R" else (i + 1, j)
            r[idx[((i, j), nxt)]] = 1.0
            i, j = nxt
        rows.append(r)
    return np.array(rows), len(arcs)


PATHS, N_ARCS = path_matrix()


def generate(rng, n, deg, B):
    X = rng.normal(size=(n, P_FEATURES))
    base = ((X @ B.T) / np.sqrt(P_FEATURES) + 3.0) ** deg + 1.0
    return X, base * rng.uniform(1 - EBAR, 1 + EBAR, size=(n, N_ARCS))


def per_instance(pred, Y):
    """(regret_i, V_i) for the policy that optimizes against `pred`."""
    z = PATHS[np.argmin(pred @ PATHS.T, axis=1)]
    V = (Y @ PATHS.T).min(axis=1)
    return (Y * z).sum(axis=1) - V, V


def one_replication(deg, rng, n_test=N_TEST):
    from sklearn.ensemble import RandomForestRegressor
    B = rng.integers(0, 2, size=(N_ARCS, P_FEATURES)).astype(float)
    Xtr, Ytr = generate(rng, N_TRAIN, deg, B)
    Xte, Yte = generate(rng, n_test, deg, B)

    A = np.hstack([np.ones((N_TRAIN, 1)), Xtr])
    W, *_ = np.linalg.lstsq(A, Ytr, rcond=None)
    ols = np.hstack([np.ones((n_test, 1)), Xte]) @ W
    rf = RandomForestRegressor(n_estimators=60, min_samples_leaf=20, n_jobs=-1,
                               random_state=0).fit(Xtr, Ytr).predict(Xte)
    flat = np.tile(Ytr.mean(axis=0), (n_test, 1))

    preds = {"OLS": ols, "RF": rf, "shrunkOLS": 0.5 * ols + 0.5 * flat,
             "noncontextual": flat}
    out = {}
    for name, pred in preds.items():
        r, V = per_instance(pred, Yte)
        out[name] = (100 * r.sum() / V.sum(), 100 * float(np.mean(r / V)))
    return out


def reversals(res):
    out = []
    for a, b in itertools.combinations(res, 2):
        if np.sign(res[a][0] - res[b][0]) != np.sign(res[a][1] - res[b][1]):
            out.append((a, b))
    return out


def sweep(degrees=DEGREES):
    print(f"{N_TEST} test instances, n_train = {N_TRAIN}, ebar = {EBAR}, "
          f"{len(PATHS)} paths\n")
    total = 0
    for deg in degrees:
        res = one_replication(deg, np.random.default_rng([BASE_SEED, deg, 0]))
        print(f"deg {deg}   {'ratio of sums':>20}{'mean of ratios':>17}")
        for k in METHODS:
            print(f"  {k:<16}{res[k][0]:>17.3f}%{res[k][1]:>16.3f}%")
        for a, b in reversals(res):
            total += 1
            print(f"  REVERSAL: {a} vs {b}")
        print()
    print(f"{total} reversals in this replication")


def study(deg, reps, pair=("OLS", "RF")):
    a, b = pair
    print(f"deg {deg}, {reps} replications, {a} vs {b}\n")
    rows = []
    for r in range(reps):
        res = one_replication(deg, np.random.default_rng([BASE_SEED, deg, r]))
        ra, rb = res[a][0], res[b][0]
        ma, mb = res[a][1], res[b][1]
        rev = np.sign(ra - rb) != np.sign(ma - mb)
        rows.append((ra, rb, ma, mb, rev))
        print(f"  rep {r}: ros {a} {ra:7.3f} {b} {rb:7.3f} | "
              f"mor {a} {ma:7.3f} {b} {mb:7.3f}  {'REVERSAL' if rev else ''}",
              flush=True)
    n = len(rows)
    print(f"\n  {sum(x[4] for x in rows)}/{n} replications reverse")
    print(f"  ratio of sums prefers {b} in {sum(x[1] < x[0] for x in rows)}/{n}; "
          f"mean of ratios prefers {b} in {sum(x[3] < x[2] for x in rows)}/{n}")
    ros = np.array([x[0] for x in rows]); mor = np.array([x[2] for x in rows])
    print(f"  spread across replications for {a}: ratio of sums "
          f"{ros.min():.1f}-{ros.max():.1f}%, mean of ratios {mor.min():.1f}-{mor.max():.1f}%")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--deg", type=int, help="run a replication study at this degree")
    ap.add_argument("--reps", type=int, default=8)
    a = ap.parse_args()
    if a.deg:
        study(a.deg, a.reps)
    else:
        sweep()


if __name__ == "__main__":
    main()
