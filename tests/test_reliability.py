"""Unit tests for reliability.py — the orchestrator + rubric + quarantine behavior."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import reliability as REL
from pipeline import readers as RD


def _ann(report, field):
    return [a for a in report["annotations"] if a["field"] == field]


def test_clean_no_source_is_medium():
    data = {"estimates": [{"estimate_id": "E1", "effect_measure": "MD", "point_estimate": -0.10,
                           "ci_lower": -0.26, "ci_upper": 0.21, "derivation_method": "Reported directly"}]}
    clean, report = REL.process(data, grids=None, pdf_reader=None, image_reader=None)
    assert report["telemetry"]["quarantined"] == 0
    assert _ann(report, "point_estimate")[0]["confidence"] == "medium"
    assert clean["estimates"][0]["point_estimate"] == "-0.1"       # canonical string (float input)


def test_invisible_dropped_sign_corrected_by_image():
    # 0.02 sits inside its own CI, so the battery cannot see the dropped sign — only the image can.
    grids = [{"table_id": "T4", "page": 9, "col_labels": ["treatment effect"],
              "rows": [{"row_label": "ALSFRS-R",
                        "cells": {"treatment effect": {"text": "0.02 (-0.26 to 0.21)", "bbox": [1, 2, 3, 4]}}}]}]
    data = {"outcomes": [{"outcome_id": "O1", "outcome_name": "ALSFRS-R"}],
            "estimates": [{"estimate_id": "E1", "outcome_id": "O1", "effect_measure": "MD",
                           "point_estimate": 0.02, "ci_lower": -0.26, "ci_upper": 0.21,
                           "derivation_method": "Reported directly"}]}
    image = RD.FixtureReader({"0.02": "-0.02"})
    clean, report = REL.process(data, grids=grids, pdf_reader=None, image_reader=image)
    assert clean["estimates"][0]["point_estimate"] == "-0.02"
    pt = _ann(report, "point_estimate")[0]
    assert pt["confidence"] == "high" and pt["source_modality"] == "table-image"
    assert report["telemetry"]["quarantined"] == 0


def test_hard_broken_events_over_total_quarantined():
    data = {"armdata": [{"data_id": "D1", "arm_id": "A1", "outcome_id": "O1", "events": 50, "total": 20}]}
    clean, report = REL.process(data, grids=None, pdf_reader=None, image_reader=None)
    assert clean["armdata"][0]["events"] is None                  # nulled in release
    q = [x for x in report["quarantine"] if x["field"] == "events"]
    assert q and q[0]["reason"] == "hard-fail-unconfirmable"
    assert clean["armdata"][0]["total"] == "20"                   # the clean field survives


def test_unlocalizable_number_quarantined():
    grids = [{"table_id": "T", "page": 1, "col_labels": ["treatment effect"],
              "rows": [{"row_label": "Some other outcome", "cells": {}}]}]
    data = {"outcomes": [{"outcome_id": "O1", "outcome_name": "Missing outcome"}],
            "estimates": [{"estimate_id": "E1", "outcome_id": "O1", "effect_measure": "MD",
                           "point_estimate": 0.5}]}
    clean, report = REL.process(data, grids=grids, pdf_reader=None, image_reader=None)
    assert clean["estimates"][0]["point_estimate"] is None
    assert any(x["reason"] == "unlocalized" for x in report["quarantine"])


def test_ungrounded_value_quarantined():
    grids = [{"table_id": "T", "page": 1, "col_labels": ["treatment effect"],
              "rows": [{"row_label": "ALSFRS-R",
                        "cells": {"treatment effect": {"text": "0.99 units", "bbox": [0, 0, 1, 1]}}}]}]
    data = {"outcomes": [{"outcome_id": "O1", "outcome_name": "ALSFRS-R"}],
            "estimates": [{"estimate_id": "E1", "outcome_id": "O1", "effect_measure": "MD",
                           "point_estimate": 0.51, "derivation_method": "Reported directly"}]}
    clean, report = REL.process(data, grids=grids, pdf_reader=None, image_reader=None)
    assert clean["estimates"][0]["point_estimate"] is None
    assert any(x["reason"] == "ungrounded-value" for x in report["quarantine"])


def test_computed_value_not_ungrounded():
    # a From-95%-CI derivation need not appear in the cell -> not quarantined
    grids = [{"table_id": "T", "page": 1, "col_labels": ["se"],
              "rows": [{"row_label": "ALSFRS-R", "cells": {"se": {"text": "", "bbox": [0, 0, 1, 1]}}}]}]
    data = {"outcomes": [{"outcome_id": "O1", "outcome_name": "ALSFRS-R"}],
            "estimates": [{"estimate_id": "E1", "outcome_id": "O1", "effect_measure": "MD",
                           "_col_label": "se", "se": 0.31, "derivation_method": "From 95% CI"}]}
    clean, report = REL.process(data, grids=grids, pdf_reader=None, image_reader=None)
    assert clean["estimates"][0]["se"] == "0.31"
    assert not any(x["field"] == "se" for x in report["quarantine"])


def test_telemetry_shape():
    data = {"estimates": [{"estimate_id": "E1", "effect_measure": "MD", "point_estimate": -0.1,
                           "ci_lower": -0.3, "ci_upper": 0.2}]}
    _, report = REL.process(data, grids=None, pdf_reader=None, image_reader=None)
    t = report["telemetry"]
    assert set(["numbers", "quarantined", "confirmed", "confidence"]).issubset(t)
    assert t["numbers"] >= 3
