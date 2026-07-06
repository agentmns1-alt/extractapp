"""Golden corpus runner — the CI acceptance gate.

Every planted corruption must be caught (repaired or quarantined), every clean control must pass,
the unconfirmable must be quarantined, and output must be byte-deterministic. Deterministic only:
no OCR/VLM, no network — the image view is a FixtureReader; the real ladder is exercised on a
fitz-built PDF with pdfplumber.
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import pytest
from pipeline import reliability as REL
from pipeline import readers as RD
from pipeline import load as LD
from pipeline import segment as SEG
from tests.golden.corpus import FIXTURES

TS = "2020-01-01T00:00:00+00:00"


def _run(fx):
    image = RD.FixtureReader(fx["image"]) if fx.get("image") else None
    return REL.process(fx["data"], grids=fx.get("grids"), pdf_reader=None, image_reader=image, run_ts=TS)


@pytest.mark.parametrize("fx", FIXTURES, ids=[f["name"] for f in FIXTURES])
def test_fixture(fx):
    clean, report = _run(fx)

    if "value" in fx:
        sheet, idx, field, expected = fx["value"]
        got = clean[sheet][idx].get(field)
        assert got == expected, f"{fx['name']}: {field} expected {expected!r} got {got!r}"

    if "confidence" in fx:
        field, exp = fx["confidence"]
        anns = [a for a in report["annotations"] if a["field"] == field]
        assert anns, f"{fx['name']}: no annotation for {field}"
        assert anns[0]["confidence"] == exp, f"{fx['name']}: {field} confidence {anns[0]['confidence']} != {exp}"

    if "quarantine_reason" in fx:
        reasons = " ".join(q["reason"] for q in report["quarantine"])
        assert fx["quarantine_reason"] in reasons, f"{fx['name']}: reasons={reasons!r}"

    if "quarantined" in fx:
        assert len(report["quarantine"]) == fx["quarantined"], \
            f"{fx['name']}: quarantined {len(report['quarantine'])} != {fx['quarantined']}"


def test_corpus_byte_deterministic(tmp_path):
    # every fixture's data merged, serialized twice -> identical bytes
    merged = {}
    for fx in FIXTURES:
        for k, v in fx["data"].items():
            merged.setdefault(k, [])
            merged[k].extend(v if isinstance(v, list) else [v])
    r1 = LD.extract(merged, str(tmp_path / "a"), run_ts=TS)
    r2 = LD.extract(merged, str(tmp_path / "b"), run_ts=TS)
    assert open(r1["path"], "rb").read() == open(r2["path"], "rb").read()


def _ruled_table_pdf(path):
    try:
        import pymupdf as fitz
    except ImportError:
        import fitz
    doc = fitz.open(); page = doc.new_page()
    xs, ys = [50, 170, 290, 410], [50, 82, 114]
    for y in ys:
        page.draw_line((xs[0], y), (xs[-1], y))
    for x in xs:
        page.draw_line((x, ys[0]), (x, ys[-1]))
    for r, row in enumerate([["Outcome", "Placebo", "Effect"], ["ALSFRS-R", "38.15", "0.51"]]):
        for c, val in enumerate(row):
            page.insert_text((xs[c] + 5, ys[r] + 20), val, fontsize=10)
    doc.save(path); doc.close()


def test_e2e_real_pdf_and_ladder(tmp_path):
    """Real rasterizer + pdfplumber reader run end-to-end (deterministic, no network)."""
    pdf = str(tmp_path / "t.pdf")
    _ruled_table_pdf(pdf)
    seg = SEG.segment(pdf)
    data = {"outcomes": [{"outcome_id": "O", "outcome_name": "ALSFRS-R"}],
            "estimates": [{"estimate_id": "E", "outcome_id": "O", "effect_measure": "MD",
                           "_col_label": "Effect", "_pdf_path": pdf, "point_estimate": 0.51,
                           "derivation_method": "Reported directly"}]}
    clean, report = REL.process(data, grids=seg["grids"], spans=seg["spans"],
                                pdf_reader=RD.pdfplumber_reader, image_reader=None, run_ts=TS)
    # value grounded/kept, nothing quarantined; confirmed if pdfplumber re-read the cell
    assert clean["estimates"][0]["point_estimate"] == "0.51"
    assert len(report["quarantine"]) == 0
    ann = [a for a in report["annotations"] if a["field"] == "point_estimate"][0]
    assert ann["confidence"] in ("high", "medium")
