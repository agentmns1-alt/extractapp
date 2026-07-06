"""Determinism gate — same input must produce byte-identical workbooks across two runs.

Run explicitly in CI after the main suite. Uses a mixed dataset (clean + corrupted + quarantined)
so normalization, correction, and quarantine paths are all exercised deterministically.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import load as LD

TS = "2020-01-01T00:00:00+00:00"

DATA = {
    "outcomes": [{"outcome_id": "O1", "outcome_name": "ALSFRS-R"}],
    "estimates": [
        {"estimate_id": "E1", "effect_measure": "MD", "point_estimate": "–0.10",
         "ci_lower": -0.26, "ci_upper": 0.21, "derivation_method": "Reported directly"},
        {"estimate_id": "E2", "effect_measure": "MD", "point_estimate": "0.53",
         "ci_lower": "-1.02", "ci_upper": "-0.04"},                       # constraint-fixed -> -0.53
        {"estimate_id": "E3", "effect_measure": "OR", "point_estimate": 1.24,
         "ci_lower": 0.87, "ci_upper": 1.77, "p_value": 0.3, "p_sided": "Two-sided"},
    ],
    "armdata": [{"data_id": "D1", "arm_id": "A1", "outcome_id": "O1", "events": 50, "total": 20}],  # quarantine
}


def test_byte_identical_across_two_runs(tmp_path):
    r1 = LD.extract(DATA, str(tmp_path / "run1"), run_ts=TS)
    r2 = LD.extract(DATA, str(tmp_path / "run2"), run_ts=TS)
    b1 = open(r1["path"], "rb").read()
    b2 = open(r2["path"], "rb").read()
    assert b1 == b2
    assert r1["status"] == r2["status"] == "DRAFT"          # the events>total row is quarantined
    assert r1["quarantined"] == 1
