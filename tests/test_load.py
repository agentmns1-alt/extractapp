"""Tests for validate.py + load.py — release gate, sheets, and byte-determinism."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pandas as pd
from pipeline import load as LD
from pipeline import validate as V
from pipeline import readers as RD

TS = "2020-01-01T00:00:00+00:00"


def _clean_data():
    return {"estimates": [{"estimate_id": "E1", "effect_measure": "MD", "point_estimate": -0.1,
                           "ci_lower": -0.3, "ci_upper": 0.2, "derivation_method": "Reported directly"}]}


def test_validate_data_flags_hard():
    r = V.validate_data({"armdata": [{"data_id": "D1", "events": 50, "total": 20}]})
    assert r["hard_fail"] >= 1
    assert any(c["status"] == "FAIL" for c in r["checks"])


def test_release_when_clean(tmp_path):
    res = LD.extract(_clean_data(), str(tmp_path), run_ts=TS)
    assert res["status"] == "RELEASE"
    assert res["path"].endswith("_RELEASE.xlsx")
    xl = pd.read_excel(res["path"], sheet_name=None)
    assert set(["README", "VALIDATION", "QUARANTINE", "RELIABILITY", "8_Estimate"]).issubset(xl)
    assert str(pd.read_excel(res["path"], sheet_name="README", header=None).iloc[0, 0]).startswith("STATUS: RELEASE")


def test_draft_when_quarantined(tmp_path):
    data = {"armdata": [{"data_id": "D1", "arm_id": "A1", "outcome_id": "O1", "events": 50, "total": 20}]}
    res = LD.extract(data, str(tmp_path), run_ts=TS)
    assert res["status"] == "DRAFT" and res["path"].endswith("_DRAFT.xlsx")
    q = pd.read_excel(res["path"], sheet_name="QUARANTINE")
    assert (q["field"] == "events").any()
    # the withheld value is nulled in the data sheet
    ad = pd.read_excel(res["path"], sheet_name="7_ArmData")
    assert pd.isna(ad.loc[0, "events"])


def test_byte_deterministic_two_runs(tmp_path):
    d1, d2 = str(tmp_path / "a"), str(tmp_path / "b")
    r1 = LD.extract(_clean_data(), d1, run_ts=TS)
    r2 = LD.extract(_clean_data(), d2, run_ts=TS)
    assert open(r1["path"], "rb").read() == open(r2["path"], "rb").read()


def test_reliability_sheet_has_telemetry(tmp_path):
    res = LD.extract(_clean_data(), str(tmp_path), run_ts=TS)
    rel = pd.read_excel(res["path"], sheet_name="RELIABILITY")
    metrics = set(rel["metric"])
    assert {"numbers", "quarantined", "confirmed", "conf_high"}.issubset(metrics)
