#!/usr/bin/env python3
"""localize.py — bind each JSON number to a physical source location WITHOUT value-matching.

Value-matching is circular in the corrupted case (the value we hold may be the corruption), so we
bind by ROW/COLUMN SEMANTICS instead: the reconstructed table grid carries header (column) labels
and stub (row) labels; a number is located by matching its record's labels, not its digits.

A `Grid` is a plain dict (JSON-friendly) so the golden corpus can supply grids directly and the
PyMuPDF adapter (`build_grid`) can produce the same shape from `find_tables()` geometry:

    grid = {
        "table_id": "T1", "page": 9,
        "col_labels": ["Placebo", "Mexiletine", "Treatment effect (95% CI)", "p-value"],
        "rows": [
            {"row_label": "ALSFRS-R",
             "cells": {"Treatment effect (95% CI)": {"text": "0.51 (-0.10 to 1.12)",
                                                      "bbox": [x0, y0, x1, y1]}}},
            ...
        ],
    }

In-text numerics bind to a `(page, span)` via `find_text_span`. Anything that cannot be bound is
returned as None so the caller nulls + quarantines it (`unlocalized`) — never silently kept.
"""
import re
from collections import namedtuple
from typing import Optional, List, Dict

Cell = namedtuple("Cell", "page table_id row_label col_label text bbox")
Span = namedtuple("Span", "page start end text bbox")


def normalize_label(s) -> str:
    """Lowercase, drop parentheticals and trailing unit clauses, collapse whitespace."""
    s = str(s or "").lower()
    s = re.sub(r"\([^)]*\)", " ", s)        # drop "(n = 20)", "(95% ci)"
    s = s.split(",")[0]                      # drop ", msec" / ", kg" unit tails
    s = re.sub(r"[^a-z0-9%\s\-]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _labels_match(a: str, b: str) -> bool:
    na, nb = normalize_label(a), normalize_label(b)
    if not na or not nb:
        return False
    return na == nb or na in nb or nb in na


def find_cell(grids: List[Dict], row_label, col_label) -> Optional[Cell]:
    """Locate a cell by semantic labels across all grids. Returns None if unresolved/ambiguous."""
    hits = []
    for g in grids or []:
        col_key = None
        for cl in g.get("col_labels", []):
            if _labels_match(cl, col_label):
                col_key = cl
                break
        if col_key is None:
            continue
        for row in g.get("rows", []):
            if _labels_match(row.get("row_label", ""), row_label):
                cell = (row.get("cells") or {}).get(col_key)
                if cell is not None:
                    hits.append(Cell(g.get("page"), g.get("table_id"), row.get("row_label"),
                                     col_key, cell.get("text"), tuple(cell.get("bbox") or ())))
    if len(hits) == 1:
        return hits[0]
    return None                              # 0 (unlocalized) or >=2 (ambiguous) -> caller quarantines


def find_text_span(spans: List[Dict], page, anchor) -> Optional[Span]:
    """Bind an in-text number to a (page, span) by an anchor phrase near it. None if unresolved."""
    hits = []
    na = normalize_label(anchor)
    for sp in spans or []:
        if page is not None and sp.get("page") != page:
            continue
        if na and na in normalize_label(sp.get("text", "")):
            hits.append(Span(sp.get("page"), sp.get("start"), sp.get("end"),
                             sp.get("text"), tuple(sp.get("bbox") or ())))
    return hits[0] if len(hits) == 1 else None


def build_grid(fitz_table, page: int, table_id: str) -> Optional[Dict]:
    """Adapter: turn a PyMuPDF `find_tables()` table into a Grid (header + stub + cell bboxes).

    Defensive: any geometry hiccup returns None rather than raising (never crash a run).
    """
    try:
        matrix = fitz_table.extract()
        if not matrix or len(matrix) < 2:
            return None
        header = [str(h or "").strip() for h in matrix[0]]
        # per-cell bboxes, if exposed by this PyMuPDF version
        row_cell_bboxes = []
        for r in getattr(fitz_table, "rows", []) or []:
            row_cell_bboxes.append([tuple(cb) if cb else None for cb in getattr(r, "cells", [])])
        rows = []
        for i, raw in enumerate(matrix[1:], start=1):
            row_label = str(raw[0] or "").strip()
            cells = {}
            for j, val in enumerate(raw):
                if j == 0 or j >= len(header):
                    continue
                col = header[j] or f"col{j}"
                bbox = None
                if i < len(row_cell_bboxes) and j < len(row_cell_bboxes[i]):
                    bbox = row_cell_bboxes[i][j]
                cells[col] = {"text": str(val or "").strip(), "bbox": list(bbox) if bbox else None}
            rows.append({"row_label": row_label, "cells": cells})
        return {"table_id": table_id, "page": page,
                "col_labels": [h for h in header[1:] if h], "rows": rows}
    except Exception:
        return None
