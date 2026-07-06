"""Synthetic golden corpus — the acceptance gate. One fixture per corruption-taxonomy item, plus
clean controls and a disagreement (image-only) fixture. Synthetic => copyright/PHI-safe.

Each fixture asserts the END-TO-END reliability outcome:
  value:            (sheet, idx, field, expected_canonical_or_None)  -- None means nulled/quarantined
  confidence:       (field, expected_label)
  quarantine_reason: substring expected among quarantine reasons
  quarantined:      exact expected count
"""

FIXTURES = [
    # ---------------- safe normalization (numbers.py flows through) ----------------
    {"name": "en_dash_minus", "item": "en-dash as minus",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": "–0.10"}]},
     "value": ("estimates", 0, "point_estimate", "-0.10"), "quarantined": 0},

    {"name": "merged_superscript", "item": "footnote/reference superscript",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": "1.33²"}]},
     "value": ("estimates", 0, "point_estimate", "1.33"), "quarantined": 0},

    {"name": "reference_bracket", "item": "reference marker glued",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": "0.51[12]"}]},
     "value": ("estimates", 0, "point_estimate", "0.51"), "quarantined": 0},

    {"name": "thousands_sep", "item": "thousands separator",
     "data": {"armdata": [{"data_id": "D", "events": "12", "total": "1,234"}]},
     "value": ("armdata", 0, "total", "1234"), "quarantined": 0},

    {"name": "decimal_comma", "item": "decimal-mark confusion",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": "0,53"}]},
     "value": ("estimates", 0, "point_estimate", "0.53"), "quarantined": 0},

    {"name": "intra_space", "item": "intra-number space",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": "- 0.21"}]},
     "value": ("estimates", 0, "point_estimate", "-0.21"), "quarantined": 0},

    # ---------------- lossy glyph swaps (candidate-tested, never eager) ----------------
    {"name": "glyph_l_to_1", "item": "l/1 swap",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": "l.43"}]},
     "value": ("estimates", 0, "point_estimate", "1.43"), "confidence": ("point_estimate", "medium"),
     "quarantined": 0},

    {"name": "glyph_O_to_0", "item": "O/0 swap",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": "O.06"}]},
     "value": ("estimates", 0, "point_estimate", "0.06"), "quarantined": 0},

    # ---------------- engine-level corruptions ----------------
    {"name": "dropped_minus_constraint", "item": "dropped minus (unique constraint fix)",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": "0.53",
                             "ci_lower": "-1.02", "ci_upper": "-0.04"}]},
     "value": ("estimates", 0, "point_estimate", "-0.53"), "confidence": ("point_estimate", "medium"),
     "quarantined": 0},

    {"name": "dropped_minus_invisible_image", "item": "dropped minus (invisible; image wins)",
     "data": {"outcomes": [{"outcome_id": "O", "outcome_name": "ALSFRS-R"}],
              "estimates": [{"estimate_id": "E", "outcome_id": "O", "effect_measure": "MD",
                             "point_estimate": 0.02, "ci_lower": -0.26, "ci_upper": 0.21,
                             "derivation_method": "Reported directly"}]},
     "grids": [{"table_id": "T", "page": 9, "col_labels": ["treatment effect"],
                "rows": [{"row_label": "ALSFRS-R",
                          "cells": {"treatment effect": {"text": "0.02 (-0.26 to 0.21)", "bbox": [1, 2, 3, 4]}}}]}],
     "image": {"0.02": "-0.02"},
     "value": ("estimates", 0, "point_estimate", "-0.02"), "confidence": ("point_estimate", "high"),
     "quarantined": 0},

    {"name": "hard_events_over_total", "item": "impossible events>total (quarantine)",
     "data": {"armdata": [{"data_id": "D", "arm_id": "A", "outcome_id": "O", "events": 50, "total": 20}]},
     "value": ("armdata", 0, "events", None), "quarantine_reason": "hard-fail", "quarantined": 1},

    {"name": "pct_without_n", "item": "percent inconsistent with events/total",
     "data": {"armdata": [{"data_id": "D", "events": 41, "total": 87, "pct": 60}]},
     "value": ("armdata", 0, "pct", "60"), "confidence": ("pct", "low"), "quarantined": 0},

    {"name": "median_iqr_mislabel", "item": "median/IQR mislabeled as mean/SD",
     "data": {"armdata": [{"data_id": "D", "median": 5, "iqr_low": 1, "iqr_high": 3}]},
     "confidence": ("median", "low"), "quarantined": 0},

    # ---------------- clean controls (must NOT be flagged) ----------------
    {"name": "control_difference", "item": "clean control (difference)",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "MD", "point_estimate": -0.02,
                             "ci_lower": -0.26, "ci_upper": 0.21, "p_value": 0.843, "p_sided": "Two-sided",
                             "derivation_method": "Reported directly"}]},
     "quarantined": 0},

    {"name": "control_ratio_logscale", "item": "clean control (ratio, log-scale CI)",
     "data": {"estimates": [{"estimate_id": "E", "effect_measure": "OR", "point_estimate": 1.24,
                             "ci_lower": 0.87, "ci_upper": 1.77, "p_value": 0.3, "p_sided": "Two-sided",
                             "derivation_method": "Reported directly"}]},
     "quarantined": 0},
]
