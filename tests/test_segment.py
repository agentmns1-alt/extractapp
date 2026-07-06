"""Segment tests — real PyMuPDF table geometry -> grids with cell bboxes (fitz-built PDF)."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import segment as SEG

try:
    import pymupdf as fitz
except ImportError:
    import fitz


def _ruled_table_pdf(path):
    doc = fitz.open()
    page = doc.new_page()
    xs = [50, 170, 290, 410]
    ys = [50, 82, 114]
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    cells = [["Outcome", "Placebo", "Effect"],
             ["ALSFRS-R", "38.15", "0.51"]]
    for r, row in enumerate(cells):
        for c, val in enumerate(row):
            page.insert_text((xs[c] + 5, ys[r] + 20), val, fontsize=10)
    doc.save(path)
    doc.close()


def test_segment_extracts_grid_with_cell_bboxes(tmp_path):
    pdf = str(tmp_path / "table.pdf")
    _ruled_table_pdf(pdf)
    seg = SEG.segment(pdf)
    assert seg["n_pages"] == 1
    assert seg["grids"], "no table grid extracted"
    grid = seg["grids"][0]
    assert "Effect" in grid["col_labels"] or "Placebo" in grid["col_labels"]
    # the ALSFRS-R row resolves and carries a bbox
    from pipeline import localize as L
    cell = L.find_cell(seg["grids"], "ALSFRS-R", "Effect")
    assert cell is not None
    assert cell.text.strip() == "0.51"
    assert len(cell.bbox) == 4


def test_segment_spans_and_manifest(tmp_path):
    pdf = str(tmp_path / "t.pdf")
    _ruled_table_pdf(pdf)
    seg = SEG.segment(pdf)
    assert seg["spans"] and seg["spans"][0]["page"] == 1
    assert isinstance(seg["missing_images"], list)


def test_rasterize_region_writes_png(tmp_path):
    pdf = str(tmp_path / "t.pdf")
    _ruled_table_pdf(pdf)
    out = SEG.rasterize_region(pdf, 1, [50, 50, 410, 114], dpi=150, out_png=str(tmp_path / "cell.png"))
    assert out and os.path.exists(out) and os.path.getsize(out) > 0
