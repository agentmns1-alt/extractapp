"""Unit tests for readers.py — constraint solver + ladder policy (deterministic, no PDF/OCR)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import readers as R


def hard_in(lo, hi):
    return lambda v: (v is not None) and (lo <= float(v) <= hi)


# ---- constraint solver ----
def test_constraint_no_fix_when_primary_clean():
    ctx = R.Ctx(primary="-0.53", candidates=["-0.53", "0.53"], hard_ok=hard_in(-1.02, -0.04))
    assert R.constraint_solver(ctx) is None


def test_constraint_unique_fix():
    # primary 0.53 is outside CI [-1.02,-0.04]; only -0.53 is hard-clean -> unique fix
    ctx = R.Ctx(primary="0.53", candidates=["0.53", "-0.53"], hard_ok=hard_in(-1.02, -0.04))
    fix = R.constraint_solver(ctx)
    assert fix is not None and fix.value == "-0.53" and fix.modality == "derived" and fix.reader_conf == "medium"


def test_constraint_ambiguous_two_candidates():
    ctx = R.Ctx(primary="9.99", candidates=["1.43", "-1.43"],
                hard_ok=lambda v: abs(abs(float(v)) - 1.43) < 1e-9)
    assert R.constraint_solver(ctx) is R.AMBIGUOUS


def test_constraint_no_candidate():
    ctx = R.Ctx(primary="9.99", candidates=["8.88"], hard_ok=hard_in(-1.0, 1.0))
    assert R.constraint_solver(ctx) is None


# ---- ladder policy ----
def test_ladder_image_wins_when_primary_broken():
    ctx = R.Ctx(primary="0.53", candidates=["0.53"], hard_ok=hard_in(-1.02, -0.04))
    req = R._req(page=9, bbox=[1, 2, 3, 4], cell_text="RAW")
    image = R.FixtureReader({"RAW": "-0.53"})
    out = R.run_ladder(ctx, req, pdf_reader=None, image_reader=image)
    assert out.value == "-0.53" and out.modality == "table-image" and out.rung == "fixture"


def test_ladder_text_vs_text_disagreement_escalates_to_needs_vision():
    ctx = R.Ctx(primary="0.10", candidates=["0.10"], hard_ok=lambda v: True)
    req = R._req(page=1, bbox=[0, 0, 1, 1], cell_text="RAW")
    pdf = lambda r: R.Reading("0.99", "high", "text", "pdfplumber")   # disagrees with primary
    out = R.run_ladder(ctx, req, pdf_reader=pdf, image_reader=lambda r: None)
    assert out is R.NEEDS_VISION


def test_ladder_pdf_agreement_confirms_text():
    ctx = R.Ctx(primary="0.10", candidates=["0.10"], hard_ok=lambda v: True)
    req = R._req(page=1, bbox=[0, 0, 1, 1], cell_text="RAW")
    pdf = lambda r: R.Reading("0.10", "high", "text", "pdfplumber")
    out = R.run_ladder(ctx, req, pdf_reader=pdf, image_reader=None)
    assert out.value == "0.10" and out.modality == "text"


def test_ladder_disagreement_resolved_by_image():
    ctx = R.Ctx(primary="0.10", candidates=["0.10"], hard_ok=hard_in(-0.5, 0.0))
    req = R._req(page=1, bbox=[0, 0, 1, 1], cell_text="RAW")
    pdf = lambda r: R.Reading("0.10", "high", "text", "pdfplumber")   # 0.10 fails hard (positive)
    image = R.FixtureReader({"RAW": "-0.10"})
    out = R.run_ladder(ctx, req, pdf_reader=pdf, image_reader=image)
    assert out.value == "-0.10" and out.modality == "table-image"


def test_ocr_disabled_in_env():
    os.environ["EXTRACTAPP_DISABLE_OCR"] = "1"
    assert R.ocr_available() is False
    assert R.tesseract_reader(R._req(page=1, bbox=[0, 0, 1, 1])) is R.NEEDS_VISION
