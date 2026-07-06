#!/usr/bin/env python3
"""segment.py — PDF adapter: text, table GRIDS (with cell bboxes), text spans, missing-image manifest.

Unlike a naive segmenter, this keeps the `find_tables()` geometry so downstream engines can localize
a number to a cell and rasterize that cell on demand. Poppler-free (PyMuPDF only). OCR of scanned
pages is optional and never a hard dependency.

Returns a JSON-friendly dict:
    { n_pages, full_text, pages:[{page, chars, image_only}],
      grids:[ localize.Grid ], spans:[{page,start,end,text,bbox}],
      missing_images:[{page, reason}] }
"""
import os
from typing import Optional, List, Dict

from . import localize as L

try:
    import pymupdf as fitz
except ImportError:                                    # pragma: no cover
    import fitz

IMAGE_ONLY_CHAR_THRESHOLD = 25


def rasterize_region(pdf_path: str, page: int, bbox, dpi: int = 300, out_png: Optional[str] = None):
    """Rasterize a (page, bbox) region to PNG for the OCR/VLM rungs. Returns the path or None."""
    try:
        with fitz.open(pdf_path) as doc:
            pg = doc.load_page(page - 1)
            pix = pg.get_pixmap(dpi=dpi, clip=fitz.Rect(bbox))
            if out_png is None:
                import tempfile
                fd, out_png = tempfile.mkstemp(suffix=".png")
                os.close(fd)
            pix.save(out_png)
            return out_png
    except Exception:                                  # pragma: no cover
        return None


def segment(pdf_path: str, outdir: Optional[str] = None, dpi: int = 150) -> Dict:
    pages, grids, spans, missing = [], [], [], []
    full_parts: List[str] = []
    with fitz.open(pdf_path) as doc:
        for idx in range(doc.page_count):
            page = doc.load_page(idx)
            page_no = idx + 1
            text = page.get_text("text") or ""
            image_only = len(text.strip()) < IMAGE_ONLY_CHAR_THRESHOLD
            if image_only:
                missing.append({"page": page_no, "reason": "image-only page (no text layer); OCR/VLM required"})

            start = sum(len(p) for p in full_parts)
            full_parts.append(text)
            spans.append({"page": page_no, "start": start, "end": start + len(text),
                          "text": text, "bbox": list(page.rect)})

            # table grids with cell geometry
            try:
                finder = page.find_tables()
                for ti, tb in enumerate(getattr(finder, "tables", []) or [], 1):
                    grid = L.build_grid(tb, page_no, f"p{page_no}t{ti}")
                    if grid:
                        grids.append(grid)
                    else:
                        missing.append({"page": page_no, "reason": f"table {ti} geometry unusable"})
            except Exception:                          # pragma: no cover
                missing.append({"page": page_no, "reason": "find_tables failed"})

            pages.append({"page": page_no, "chars": len(text.strip()), "image_only": image_only})

    return {"n_pages": len(pages), "full_text": "".join(full_parts), "pages": pages,
            "grids": grids, "spans": spans, "missing_images": missing}
