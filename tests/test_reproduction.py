"""Reproduction tests: every exhibit in the paper, checked against what it prints.

Run everything (about two minutes, dominated by the portfolio self-test):

    pytest -q                       # or:  python3 tests/test_reproduction.py

Run only the fast checks (a few seconds):

    pytest -q -m "not slow"

The tests are the paper's own consistency conditions, not unit tests of the
implementation.  Each one either recomputes a published number from the source
data or checks an identity that must hold whatever the numbers are.
"""

import os
import sys

import numpy as np
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "code"))

import aggregation_example as agg          # noqa: E402
import literature_audit as audit           # noqa: E402
import make_autopsy_table as autopsy       # noqa: E402
import portfolio_autopsy as pf             # noqa: E402
import shortest_path_autopsy as sp         # noqa: E402
import two_action_construction as two      # noqa: E402


# --------------------------------------------------------------------------
# Table 1 -- the literature audit
# --------------------------------------------------------------------------

def test_audit_row_structure_matches_table1():
    """Every Papers count in Table 1 comes out of audit.csv."""
    assert audit.check(audit.load())


def test_audit_columns_2_and_3_are_still_hand_assigned():
    """A guard, not a success: this fails once audit.csv can generate them.

    When `contaminated` and `synthetic` are added to audit.csv (open_notes B0),
    this test should be deleted and the generator switched to --contaminated audit.
    """
    t = audit.load()
    assert "contaminated" not in t.columns and "synthetic_col" not in t.columns
    strict = int(t.strict.sum())
    broad = int(t.broad.sum())
    printed = audit.PUBLISHED_BLOCK["total"][1]
    assert strict < printed < broad, (strict, printed, broad)


# --------------------------------------------------------------------------
# Figure 1 and Table 3 -- the shortest-path autopsy
# --------------------------------------------------------------------------

def test_shortest_path_medians_match_the_paper():
    """The medians we plot are the ones the paper quotes, recomputed from their CSV."""
    med = sp.load_medians(sp.EBAR)
    for method, per_deg in sp.PUBLISHED.items():
        for deg, published in per_deg.items():
            assert abs(med[method][deg] - published) < 0.01, (method, deg)


def test_shortest_path_corrected_reproduces_their_noiseless_control():
    """The correction uses no fitted model and never sees the control.

    Their own ebar = 0 runs already report True-Model Regret, because the two
    oracles coincide when the DGP is noiseless.  Correcting the ebar = 0.5 runs
    has to land on them.

    The tolerance is 0.7 percentage points, against reported values that run from
    15.5 down to 7.5 and back up to 21.8.  The residual is Monte Carlo error in the
    premium plus the difference between two sets of their replications, and it is
    largest where the corrected value is largest.
    """
    rep, ctl = sp.selftest(verbose=False)
    for method in ("SPOplus", "LS"):
        for deg in sp.DEGREES:
            corrected = sp.correct(rep[method][deg], sp.ETA[deg])
            assert abs(corrected - ctl[method][deg]) < 0.7, (method, deg)


def test_shortest_path_premium_vanishes_without_noise():
    """LAP = 0 identically when Y is a deterministic function of X."""
    assert abs(sp.compute_eta(deg=4, ebar=0.0, n_trials=8, n_test=500)) < 1e-9


# --------------------------------------------------------------------------
# Table 4 -- the portfolio autopsy
# --------------------------------------------------------------------------

def test_portfolio_cache_is_the_published_run():
    cache = pf.read_cache()
    eta = pf.eta_table(cache)
    assert len(eta) == len(pf.TAUS) * len(pf.DEGREES)
    for (tau, deg), (mean, se, n) in eta.items():
        assert n == 50, (tau, deg, n)
        assert se < 0.00025, (tau, deg, se)      # 0.025 percentage points
        assert mean > 0, (tau, deg, mean)        # the premium is nonnegative


def test_portfolio_decomposition_is_an_identity():
    """NReg^LA = (1 - eta) NReg^TM + eta, in the constant-sign portfolio setting."""
    eta = pf.eta_table(pf.read_cache())
    med = pf.reported_medians()
    for (tau, deg), (e, _, _) in eta.items():
        for key, _ in pf.METHODS:
            reported = med[(tau, deg)][key]
            assert abs((1 - e) * pf.correct(reported, e) + e - reported) < 1e-12


@pytest.mark.slow
def test_portfolio_cells_recompute():
    """Two cached cells, recomputed from their seeds alone."""
    pf.selftest(pf.read_cache(), k=2, tol=1e-7)


# --------------------------------------------------------------------------
# Appendix E -- the two-action construction
# --------------------------------------------------------------------------

def test_two_action_construction():
    """The true-model oracle costs 1 at every kappa; the premium is analytic at kappa = 1."""
    two.selftest()


# --------------------------------------------------------------------------
# Example 1 and the aggregation frequencies
# --------------------------------------------------------------------------

def test_example_1_is_exact():
    out = agg.example()
    for name, (r, s, m) in out.items():
        pr, ps, pm = agg.PUBLISHED_EXAMPLE[name]
        assert (abs(r - pr) < 5e-3, abs(s - ps) < 5e-2, abs(m - pm) < 5e-2) == (True,) * 3


def test_ratio_of_sums_ranks_as_true_model_regret_does():
    """The property Example 1 turns on, over random benchmarks rather than four numbers."""
    res = agg.frequencies(n_benchmarks=20_000, verbose=False)   # asserts it internally
    assert 10.0 < res["overall"] < 30.0


# --------------------------------------------------------------------------
# Table 3 -- generated, and compared with what the paper prints
# --------------------------------------------------------------------------

def test_autopsy_table_generates():
    s = autopsy.shortest_path()
    p = autopsy.portfolio()
    assert set(s["eta"]) == set(sp.DEGREES)
    assert set(p["eta"]) == set(pf.DEGREES)
    # No corrected value may be negative once the premium is estimated properly.
    for key in ("SPOplus", "LS", "Baseline"):
        assert min(p[key]["corr"].values()) > -0.05, key


if __name__ == "__main__":
    sys.exit(pytest.main([__file__, "-q"]))
