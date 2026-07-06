"""Unit tests for reconcile.py — Engine 1 two-view decisions."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import reconcile as RC
from pipeline import readers as RD


def hard_in(lo, hi):
    return lambda v: v is not None and lo <= float(v) <= hi


REQ = RD._req(page=9, bbox=[1, 2, 3, 4], cell_text="RAW")


def test_clean_primary_text_only():
    ctx = RD.Ctx(primary="-0.10", candidates=["-0.10"], hard_ok=hard_in(-1, 1))
    d = RC.reconcile(ctx, REQ, pdf_reader=None, image_reader=None)
    assert d.value == "-0.10" and d.confirmed is False and d.modality == "text" and d.quarantine is None


def test_clean_primary_image_confirmed():
    ctx = RD.Ctx(primary="-0.10", candidates=["-0.10"], hard_ok=hard_in(-1, 1))
    img = RD.FixtureReader({"RAW": "-0.10"})
    d = RC.reconcile(ctx, REQ, pdf_reader=None, image_reader=img)
    assert d.confirmed is True and d.modality == "table-image"


def test_disagreement_image_wins():
    ctx = RD.Ctx(primary="0.10", candidates=["0.10"], hard_ok=hard_in(-0.5, 0.0))
    img = RD.FixtureReader({"RAW": "-0.10"})
    d = RC.reconcile(ctx, REQ, pdf_reader=None, image_reader=img)
    assert d.value == "-0.10" and d.modality == "table-image" and d.confirmed is True


def test_hard_broken_unique_fix_via_constraint():
    ctx = RD.Ctx(primary="0.53", candidates=["0.53", "-0.53"], hard_ok=hard_in(-1.02, -0.04))
    d = RC.reconcile(ctx, REQ, pdf_reader=None, image_reader=lambda r: None)
    assert d.value == "-0.53" and d.derivation == "derived" and d.quarantine is None


def test_hard_broken_unconfirmable_quarantines():
    ctx = RD.Ctx(primary="0.53", candidates=["0.53"], hard_ok=hard_in(-1.02, -0.04))
    d = RC.reconcile(ctx, REQ, pdf_reader=None, image_reader=lambda r: None)
    assert d.value is None and d.quarantine == "hard-fail-unconfirmable"


def test_hard_broken_ambiguous_quarantines():
    ctx = RD.Ctx(primary="9.99", candidates=["1.43", "-1.43"],
                 hard_ok=lambda v: abs(abs(float(v)) - 1.43) < 1e-9)
    d = RC.reconcile(ctx, REQ, pdf_reader=None, image_reader=lambda r: None)
    assert d.value is None and d.quarantine == "ambiguous-correction"


def test_text_vs_text_needs_vision_keeps_clean_primary():
    ctx = RD.Ctx(primary="0.10", candidates=["0.10"], hard_ok=lambda v: True)
    pdf = lambda r: RD.Reading("0.99", "high", "text", "pdfplumber")
    d = RC.reconcile(ctx, REQ, pdf_reader=pdf, image_reader=lambda r: None)
    assert d.value == "0.10" and d.needs_vision is True and d.quarantine is None
