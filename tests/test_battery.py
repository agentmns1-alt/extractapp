"""Unit tests for battery.py — HARD/SOFT/GUARDED tiers and the CI-vs-p dropped-sign detector."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import battery as B


def _find(checks, name):
    return next(c for c in checks if c.name == name)


# ---- HARD checks ----
def test_hard_ci_order_and_point_in_ci():
    c = B.check_estimate({"effect_measure": "MD", "point_estimate": 0.5, "ci_lower": 0.9, "ci_upper": 0.1})
    assert _find(c, "ci_order").tier == B.HARD and _find(c, "ci_order").status == B.FAIL
    c2 = B.check_estimate({"effect_measure": "MD", "point_estimate": 9.0, "ci_lower": -1.0, "ci_upper": 1.0})
    assert _find(c2, "point_in_ci").status == B.FAIL


def test_hard_events_over_total():
    c = B.check_armdata({"events": 50, "total": 20})
    assert _find(c, "events_le_total").tier == B.HARD and _find(c, "events_le_total").status == B.FAIL


def test_hard_p_and_sd():
    assert _find(B.check_estimate({"point_estimate": 0.1, "ci_lower": 0, "ci_upper": 1, "p_value": 1.4}),
                 "p_in_unit").status == B.FAIL
    assert _find(B.check_armdata({"sd": -0.5}), "sd_nonneg").status == B.FAIL


def test_clean_estimate_all_pass():
    c = B.check_estimate({"effect_measure": "MD", "point_estimate": -0.02, "ci_lower": -0.26,
                          "ci_upper": 0.21, "p_value": 0.843, "p_sided": "Two-sided"})
    assert not any(ch.status == B.FAIL for ch in c)


# ---- GUARDED: CI-vs-p ----
def test_ci_vs_p_catches_dropped_sign_class():
    # CI excludes 0 (both positive) but p is non-significant -> internal contradiction
    c = _find(B.check_estimate({"effect_measure": "MD", "point_estimate": 0.10, "ci_lower": 0.02,
                                "ci_upper": 0.18, "p_value": 0.475, "p_sided": "Two-sided"}), "ci_vs_p")
    assert c.tier == B.GUARDED and c.status == B.FAIL


def test_ci_vs_p_pass_consistent():
    incl = _find(B.check_estimate({"effect_measure": "MD", "point_estimate": -0.10, "ci_lower": -0.26,
                                   "ci_upper": 0.21, "p_value": 0.475, "p_sided": "Two-sided"}), "ci_vs_p")
    assert incl.status == B.PASS
    sig = _find(B.check_estimate({"effect_measure": "MD", "point_estimate": 1.33, "ci_lower": 0.20,
                                  "ci_upper": 2.45, "p_value": 0.023, "p_sided": "Two-sided"}), "ci_vs_p")
    assert sig.status == B.PASS


def test_ci_vs_p_guarded_off_when_preconditions_unmet():
    # one-sided -> not evaluable (never a fail)
    assert _find(B.check_estimate({"effect_measure": "MD", "point_estimate": 0.1, "ci_lower": 0.02,
                                   "ci_upper": 0.18, "p_value": 0.5, "p_sided": "One-sided"}),
                 "ci_vs_p").status == B.NA
    # missing p -> na
    assert _find(B.check_estimate({"effect_measure": "MD", "point_estimate": 0.1, "ci_lower": 0.02,
                                   "ci_upper": 0.18}), "ci_vs_p").status == B.NA


# ---- ratio measures on the log scale ----
def test_ratio_geomean_soft():
    ok = B.check_estimate({"effect_measure": "OR", "point_estimate": 1.24, "ci_lower": 0.87, "ci_upper": 1.77})
    assert _find(ok, "ratio_geomean").status == B.PASS
    bad = B.check_estimate({"effect_measure": "OR", "point_estimate": 1.50, "ci_lower": 0.87, "ci_upper": 1.77})
    g = _find(bad, "ratio_geomean")
    assert g.tier == B.SOFT and g.status == B.FAIL


def test_ratio_null_is_one():
    # OR CI (1.2, 3.4) excludes null=1 -> must be significant; p=0.3 -> contradiction
    c = _find(B.check_estimate({"effect_measure": "OR", "point_estimate": 2.0, "ci_lower": 1.2,
                                "ci_upper": 3.4, "p_value": 0.3, "p_sided": "Two-sided"}), "ci_vs_p")
    assert c.status == B.FAIL


# ---- soft armdata ----
def test_pct_mismatch_soft():
    c = _find(B.check_armdata({"events": 41, "total": 87, "pct": 60.0}), "pct_matches")
    assert c.tier == B.SOFT and c.status == B.FAIL


def test_worst_summary():
    hard, soft, guarded = B.worst(B.check_armdata({"events": 50, "total": 20}))
    assert hard and not soft
