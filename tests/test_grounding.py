"""Unit tests for grounding.py — Engine 3 cell-local transcription fidelity."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import grounding as G


def test_grounded_when_value_in_cell():
    ok, _ = G.ground("0.51", "0.51 (-0.10 to 1.12)", "Reported directly")
    assert ok is True


def test_grounded_via_preimage_dropped_minus():
    # corrected value -0.10 grounds against its corrupted preimage "0.10" in the cell
    ok, reason = G.ground("-0.10", "0.10 (-0.37 to 0.18)", "Reported directly")
    assert ok is True and "preimage" in reason


def test_ungrounded_value_not_in_cell():
    ok, reason = G.ground("9.99", "0.51 (-0.10 to 1.12)", "Reported directly")
    assert ok is False and "not found" in reason


def test_computed_values_are_exempt():
    ok, reason = G.ground("0.1234", "", "From 95% CI")
    assert ok is True and "exempt" in reason
    assert G.is_exempt("From SE") is True
    assert G.is_exempt("Reported directly") is False


def test_empty_cell_directly_reported_is_ungrounded():
    ok, _ = G.ground("1.33", "", "Reported directly")
    assert ok is False


def test_numeric_match_ignores_trailing_zero():
    ok, _ = G.ground("0.50", "effect 0.5 units", "Author-provided")
    assert ok is True
