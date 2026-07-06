"""Unit tests for localize.py — semantic (non-value) binding of numbers to cells/spans."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import localize as L

GRID = {
    "table_id": "T4", "page": 9,
    "col_labels": ["Placebo", "Mexiletine", "Treatment effect (95% CI)", "p-value"],
    "rows": [
        {"row_label": "ALSFRS-R", "cells": {
            "Treatment effect (95% CI)": {"text": "0.51 (-0.10 to 1.12)", "bbox": [1, 2, 3, 4]},
            "p-value": {"text": "0.094", "bbox": [5, 6, 7, 8]}}},
        {"row_label": "Tongue pressure, kPa", "cells": {
            "Treatment effect (95% CI)": {"text": "1.33 (0.20 to 2.45)", "bbox": [9, 10, 11, 12]}}},
    ],
}


def test_normalize_label_drops_units_and_parens():
    assert L.normalize_label("Tongue pressure, kPa") == "tongue pressure"
    assert L.normalize_label("Baseline (n = 20)") == "baseline"
    assert L.normalize_label("Treatment effect (95% CI)") == "treatment effect"


def test_find_cell_by_semantics_not_value():
    cell = L.find_cell([GRID], "ALSFRS-R", "Treatment effect (95% CI)")
    assert cell is not None
    assert cell.text == "0.51 (-0.10 to 1.12)"
    assert cell.bbox == (1, 2, 3, 4) and cell.page == 9


def test_find_cell_fuzzy_row_and_col_labels():
    # partial label ("Tongue pressure") + normalized column still resolve
    cell = L.find_cell([GRID], "Tongue pressure", "treatment effect")
    assert cell is not None and cell.text.startswith("1.33")


def test_unlocalized_returns_none():
    assert L.find_cell([GRID], "Nonexistent outcome", "p-value") is None
    assert L.find_cell([GRID], "ALSFRS-R", "No such column") is None


def test_ambiguous_returns_none():
    dup = dict(GRID)
    grids = [GRID, GRID]           # same row_label in two grids -> ambiguous -> None
    assert L.find_cell(grids, "ALSFRS-R", "p-value") is None


def test_find_text_span():
    spans = [{"page": 7, "start": 100, "end": 140, "text": "pain severity decreased (MD -0.53)", "bbox": [0, 0, 1, 1]}]
    sp = L.find_text_span(spans, 7, "pain severity")
    assert sp is not None and sp.page == 7
    assert L.find_text_span(spans, 9, "pain severity") is None   # wrong page
