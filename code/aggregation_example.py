#!/usr/bin/env python3
"""Aggregation: a ratio of sums and a mean of ratios are different estimands.

Two things live here.

1. EXAMPLE 1 of the paper (``ex:Reversal``), exact arithmetic on four numbers.
   ``--example`` prints the table and asserts every entry against the published
   values.  Nothing is simulated.

2. THE REVERSAL FREQUENCIES quoted in the implementation notes
   (``sec:ImplAggregation``), over randomly generated benchmarks.  ``--frequencies``
   runs that simulation.  The generative model is arbitrary -- it is an illustration
   that reversal is common, not an estimate of its rate in any literature -- and is
   stated in full in the paper:

       between 2 and 40 instances;
       instance weights from a symmetric Dirichlet;
       optimal values V log-uniform across a thirtyfold range;
       per-instance regrets proportional to V times an exponential draw.

   Two methods are drawn independently per benchmark.  A *reversal* is a benchmark
   on which the ratio of sums and the mean of ratios rank the two methods opposite
   ways.  Because both methods face the same instances and the same weights, the
   ratio of sums ranks them exactly as True-Model Regret does; the mean of ratios
   need not.

   Reported frequencies are conditioned on how close the two methods are in
   True-Model Regret, since that is the case that matters -- benchmark tables
   compare methods that are close.

   STATUS.  The *overall* frequency reproduces: this model gives 19.6% against the
   20% printed.  The *conditional* frequencies do not, and are lower in every band.
   The published run put far more mass on benchmarks where the two methods differ by
   more than 2x than this model does, which points at a per-method scale that the
   appendix's description of the generative model does not mention.  The original
   script was not kept.  Until that is resolved (``open_notes`` B7) the conditional
   frequencies are not reproducible from this repository, and the safe reading is
   the one the paper already gives: reversal is common.  Example 1 is exact and is
   unaffected.

USAGE
    python3 aggregation_example.py                  # both
    python3 aggregation_example.py --example
    python3 aggregation_example.py --frequencies --benchmarks 195000
"""

import argparse

import numpy as np

BASE_SEED = 20260829

# Example 1, as printed.  (RegTM, ratio of sums %, mean of ratios %)
PUBLISHED_EXAMPLE = {"A": (0.50, 9.1, 50.0), "B": (1.00, 18.2, 10.0)}

# The frequencies as printed in sec:ImplAggregation, in percent.
PUBLISHED_FREQ = {"overall": 20, "<1.5x": 41, "1.5-2x": 27, "2-5x": 12, ">5x": 1.7}

N_MIN, N_MAX = 2, 40
V_RANGE = 30.0          # log-uniform across a thirtyfold range


# ---------------------------------------------------------------------------
# 1.  Example 1 -- exact arithmetic
# ---------------------------------------------------------------------------

def example():
    """Two instance types, equally frequent, two routes each.

        short trip   costs (1, 2)    so V = 1
        long trip    costs (10, 12)  so V = 10

    Method A is correct on long trips and wrong on short ones; B is the reverse.
    The data are noiseless, so the two oracles coincide and no premium is involved.
    """
    V = np.array([1.0, 10.0])                 # optimal value of each instance type
    w = np.array([0.5, 0.5])                  # equally often
    chosen = {"A": np.array([2.0, 10.0]),     # wrong on short, right on long
              "B": np.array([1.0, 12.0])}     # right on short, wrong on long

    print(f"{'':<10}{'RegTM':>9}{'ratio of sums':>16}{'mean of ratios':>17}")
    out = {}
    for name, c in chosen.items():
        regret = c - V
        reg_tm = float(w @ regret)                       # E[<Y, pi(X)> - V(Y)]
        ros = float((w @ regret) / (w @ V))              # sum loss / sum optimal cost
        mor = float(w @ (regret / V))                    # normalize, then average
        out[name] = (reg_tm, 100 * ros, 100 * mor)
        print(f"Method {name:<3}{reg_tm:>9.2f}{100 * ros:>15.1f}%{100 * mor:>16.1f}%")

    for name, (r, s, m) in out.items():
        pr, ps, pm = PUBLISHED_EXAMPLE[name]
        assert abs(r - pr) < 5e-3, (name, r, pr)
        assert abs(s - ps) < 5e-2, (name, s, ps)
        assert abs(m - pm) < 5e-2, (name, m, pm)

    assert out["A"][0] < out["B"][0], "A should have the smaller True-Model Regret"
    assert out["A"][1] < out["B"][1], "the ratio of sums should agree with True-Model Regret"
    assert out["A"][2] > out["B"][2], "the mean of ratios should reverse the ranking"
    factor = out["A"][2] / out["B"][2]
    print(f"\n  A has half the True-Model Regret; the mean of ratios prefers B "
          f"by a factor of {factor:.0f}.")
    print("  example matches the published values")
    return out


# ---------------------------------------------------------------------------
# 2.  Reversal frequencies over random benchmarks
# ---------------------------------------------------------------------------

def _batch(n, m, rng):
    """m benchmarks of n instances each.  Returns (ros, mor, regTM) for 2 methods."""
    w = rng.dirichlet(np.ones(n), size=m)                      # (m, n) weights
    V = np.exp(rng.uniform(0.0, np.log(V_RANGE), size=(m, n)))  # log-uniform values
    e = rng.exponential(size=(m, 2, n))                        # per-method draws
    regret = V[:, None, :] * e                                 # regret proportional to V

    tot_V = (w * V).sum(axis=1)                                # (m,)
    reg_tm = (w[:, None, :] * regret).sum(axis=2)              # (m, 2) weighted total
    ros = reg_tm / tot_V[:, None]                              # ratio of sums
    mor = (w[:, None, :] * e).sum(axis=2)                      # mean of ratios
    return ros, mor, reg_tm


def frequencies(n_benchmarks=195_000, seed=BASE_SEED, verbose=True):
    rng = np.random.default_rng(seed)
    sizes = np.arange(N_MIN, N_MAX + 1)
    per = int(np.ceil(n_benchmarks / len(sizes)))

    reversed_, ratios = [], []
    for n in sizes:
        ros, mor, tm = _batch(int(n), per, rng)
        # the ratio of sums ranks methods exactly as True-Model Regret does
        assert np.all(np.sign(ros[:, 0] - ros[:, 1]) == np.sign(tm[:, 0] - tm[:, 1]))
        reversed_.append(np.sign(ros[:, 0] - ros[:, 1]) != np.sign(mor[:, 0] - mor[:, 1]))
        ratios.append(tm.max(axis=1) / tm.min(axis=1))
    rev = np.concatenate(reversed_)[:n_benchmarks]
    rat = np.concatenate(ratios)[:n_benchmarks]

    bands = [("<1.5x", rat < 1.5), ("1.5-2x", (rat >= 1.5) & (rat < 2.0)),
             ("2-5x", (rat >= 2.0) & (rat < 5.0)), (">5x", rat >= 5.0)]
    res = {"overall": 100 * rev.mean()}
    for label, mask in bands:
        res[label] = 100 * rev[mask].mean() if mask.any() else float("nan")

    if verbose:
        print(f"{len(rev):,} random benchmarks, seed {seed}\n")
        print(f"{'True-Model Regret ratio':<26}{'benchmarks':>12}{'reversed':>10}"
              f"{'paper':>8}")
        print(f"{'all':<26}{len(rev):>12,}{res['overall']:>9.1f}%"
              f"{PUBLISHED_FREQ['overall']:>7}%")
        for label, mask in bands:
            print(f"{label:<26}{int(mask.sum()):>12,}{res[label]:>9.1f}%"
                  f"{PUBLISHED_FREQ[label]:>7}%")
        print("\n  The generative model is arbitrary.  Read these as an illustration that\n"
              "  reversal is common, not as an estimate of its rate in any literature.")
        off = [k for k in PUBLISHED_FREQ
               if abs(res[k] - PUBLISHED_FREQ[k]) > max(2.0, 0.2 * PUBLISHED_FREQ[k])]
        if off:
            print(f"\n  NOTE: {', '.join(off)} do not reproduce the printed frequencies.\n"
                  "  See STATUS in this module's docstring and open_notes B7.")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--example", action="store_true", help="Example 1 only")
    ap.add_argument("--frequencies", action="store_true", help="the simulation only")
    ap.add_argument("--benchmarks", type=int, default=195_000)
    ap.add_argument("--seed", type=int, default=BASE_SEED)
    a = ap.parse_args()
    both = not (a.example or a.frequencies)
    if a.example or both:
        print("Example 1 -- mean of ratios reverses a ranking\n")
        example()
    if a.frequencies or both:
        print("\nReversal frequencies over random benchmarks\n")
        frequencies(a.benchmarks, a.seed)


if __name__ == "__main__":
    main()
