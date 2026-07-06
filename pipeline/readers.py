#!/usr/bin/env python3
"""readers.py — second-source reader ladder behind a uniform `Reading` result.

Cheapest-first, stop as soon as a reading passes the HARD battery:
  (a) pdfplumber re-read of the cell (pure-Python, Poppler-free)  -> modality=text
  (b) constraint solver: the UNIQUE candidate that satisfies the hard checks -> modality=derived
  (c) image rung (Tesseract charset OCR / injected FixtureReader)  -> modality=table-image
  (d) VLM stub — off by default, never in CI

Policy:
  * A text-vs-text disagreement (pdfplumber != primary) does NOT auto-pick pdfplumber; it escalates
    to the image rung as tiebreak.
  * The image rung is authoritative when it reads a hard-clean value.
  * The constraint solver engages ONLY when the primary value is hard-broken, and applies a fix only
    if EXACTLY ONE candidate is hard-clean; 0 -> no fix, >=2 -> `ambiguous` (caller quarantines).
  * OCR/VLM absent -> the image rung degrades to `needs_vision`; it never crashes the run.

All PDF/OCR/VLM work is dependency-injected so the golden corpus supplies a deterministic image view
and CI never touches a real binary.
"""
import os
from collections import namedtuple
from typing import Optional, Callable, List

from . import numbers as N

Reading = namedtuple("Reading", "value reader_conf modality rung")
Req = namedtuple("Req", "page bbox cell_text pdf_path page_image_path")
Ctx = namedtuple("Ctx", "primary candidates hard_ok")

NEEDS_VISION = Reading(None, "low", "table-image", "needs_vision")
AMBIGUOUS = Reading(None, "low", "derived", "ambiguous")


def _req(page=None, bbox=None, cell_text=None, pdf_path=None, page_image_path=None) -> Req:
    return Req(page, bbox, cell_text, pdf_path, page_image_path)


# ---------- availability (never a hard dependency) ----------
def ocr_available() -> bool:
    if os.environ.get("EXTRACTAPP_DISABLE_OCR") == "1":
        return False
    from shutil import which
    return which("tesseract") is not None or bool(os.environ.get("TESSERACT_EXE"))


def vlm_enabled() -> bool:
    return os.environ.get("EXTRACTAPP_ENABLE_VLM") == "1" and os.environ.get("EXTRACTAPP_DISABLE_VLM") != "1"


# ---------- constraint solver (pure, deterministic, no I/O) ----------
def constraint_solver(ctx: Ctx) -> Optional[Reading]:
    """Fix a hard-broken primary iff exactly one candidate is hard-clean. Never invents digits."""
    if ctx.primary is not None and ctx.hard_ok(ctx.primary):
        return None                                   # nothing to fix
    seen, valid = set(), []
    for c in ctx.candidates or []:
        if c is None or c == ctx.primary or c in seen:
            continue
        seen.add(c)
        if ctx.hard_ok(c):
            valid.append(c)
    if len(valid) == 1:
        return Reading(valid[0], "medium", "derived", "constraint")
    if len(valid) >= 2:
        return AMBIGUOUS
    return None


# ---------- pdfplumber text rung ----------
def pdfplumber_reader(req: Req) -> Optional[Reading]:
    """Re-read the cell region with pdfplumber. Returns a text-modality Reading or None."""
    if not req.pdf_path or not req.bbox or req.page is None:
        return None
    try:
        import pdfplumber
    except ImportError:                               # pragma: no cover
        return None
    try:
        with pdfplumber.open(req.pdf_path) as pdf:
            page = pdf.pages[req.page - 1]
            crop = page.within_bbox(tuple(req.bbox))
            txt = (crop.extract_text() or "").strip()
    except Exception:
        return None
    val = _first_number(txt)
    return Reading(val, "high" if val else "low", "text", "pdfplumber") if val else None


def _first_number(text: str) -> Optional[str]:
    import re
    for tok in re.findall(r"[-−–+]?\s*\d[\d.,\s]*", text or ""):
        c = N.canonical(tok)
        if c is not None:
            return c
    return None


# ---------- Tesseract image rung (optional) ----------
def tesseract_reader(req: Req) -> Optional[Reading]:
    """OCR the cell raster with a pinned numeric charset. Degrades to needs_vision if unavailable."""
    if not ocr_available():
        return NEEDS_VISION
    raster = _rasterize_cell(req)
    if raster is None:
        return NEEDS_VISION
    from shutil import which
    import subprocess
    exe = os.environ.get("TESSERACT_EXE") or which("tesseract")
    try:
        out = subprocess.run(
            [exe, raster, "stdout", "--psm", "7", "-c", "tessedit_char_whitelist=0123456789.,()-"],
            capture_output=True, text=True, timeout=30)
        val = _first_number(out.stdout)
        return Reading(val, "high" if val else "low", "table-image", "tesseract") if val else NEEDS_VISION
    except Exception:                                 # pragma: no cover
        return NEEDS_VISION


def _rasterize_cell(req: Req) -> Optional[str]:       # pragma: no cover (needs a real PDF)
    if not req.pdf_path or not req.bbox or req.page is None:
        return None
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    try:
        import tempfile
        with fitz.open(req.pdf_path) as doc:
            page = doc.load_page(req.page - 1)
            pix = page.get_pixmap(dpi=300, clip=fitz.Rect(req.bbox))
            fd, path = tempfile.mkstemp(suffix=".png")
            os.close(fd)
            pix.save(path)
            return path
    except Exception:
        return None


class FixtureReader:
    """Deterministic image rung for the corpus/CI: maps a cell key -> known raster value.

    key = (page, tuple(bbox)) or the cell_text's id; value is the CORRECT number as printed.
    """
    def __init__(self, mapping):
        self.mapping = {self._key(k): v for k, v in (mapping or {}).items()}

    @staticmethod
    def _key(k):
        return tuple(k) if isinstance(k, (list, tuple)) else k

    def __call__(self, req: Req) -> Optional[Reading]:
        for key in ((req.page, tuple(req.bbox)) if req.bbox else None, req.cell_text):
            if key is not None and self._key(key) in self.mapping:
                v = N.canonical(self.mapping[self._key(key)])
                return Reading(v, "high", "table-image", "fixture") if v else None
        return None


# ---------- the ladder ----------
def run_ladder(ctx: Ctx, req: Req,
               pdf_reader: Optional[Callable] = pdfplumber_reader,
               image_reader: Optional[Callable] = tesseract_reader) -> Optional[Reading]:
    """Return the winning second-source reading, or a needs_vision / ambiguous sentinel, or None.

    `needs_vision` is returned only when an image is genuinely required — a text-vs-text
    disagreement, or a hard-broken primary — never merely because the image rung is unavailable
    for a clean value (that value is simply text-only, handled by the caller's rubric).
    """
    primary_broken = ctx.primary is not None and not ctx.hard_ok(ctx.primary)
    image_needed = False

    # (a) pdfplumber
    if pdf_reader is not None:
        pr = pdf_reader(req)
        if pr and pr.value is not None:
            if ctx.primary is None or pr.value == ctx.primary:
                if ctx.hard_ok(pr.value):
                    return pr._replace(modality="text")
            else:
                image_needed = True                   # text-vs-text disagreement -> raster tiebreak

    # (b) constraint solver (only engages on a hard-broken primary)
    cs = constraint_solver(ctx)
    if cs is not None:
        return cs                                     # unique fix, or AMBIGUOUS

    # (c) image rung (Tesseract / injected FixtureReader)
    if image_reader is not None:
        ir = image_reader(req)
        if ir is not None:
            if ir.rung == "needs_vision":
                if image_needed or primary_broken:
                    return ir                         # an image would settle it, but none available
            elif ir.value is not None and ctx.hard_ok(ir.value):
                return ir._replace(modality="table-image")

    # (d) VLM stub — off by default
    if image_needed:
        return NEEDS_VISION
    if primary_broken and image_reader is not None:
        return NEEDS_VISION                            # an image could settle it, but none read
    return None                                        # no image capability -> caller quarantines
