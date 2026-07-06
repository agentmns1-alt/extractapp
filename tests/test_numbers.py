"""Unit tests for numbers.py — the safe/lossy normalization tiers + candidates + preimages."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from pipeline import numbers as N


# ---- SAFE unifications (applied directly, value-preserving) ----
def test_dash_variants_unify_to_ascii_minus():
    assert N.canonical("−0.10") == "-0.10"     # U+2212 minus
    assert N.canonical("–0.10") == "-0.10"     # en dash
    assert N.canonical("‑0.10") == "-0.10"     # non-breaking hyphen
    assert N.canonical("-0.10") == "-0.10"


def test_decimals_preserved():
    assert N.canonical("0.10") == "0.10"            # trailing zero kept
    assert N.canonical("0.1") == "0.1"
    assert N.decimals("-0.10") == 2
    assert N.decimals("5") == 0


def test_strip_footnote_and_reference_markers():
    assert N.canonical("1.33a") == "1.33"           # trailing footnote letter
    assert N.canonical("1.33[12]") == "1.33"        # bracket reference
    assert N.canonical("1.33²") == "1.33"      # superscript 2
    assert N.canonical("6.39*") == "6.39"           # asterisk
    assert N.canonical("0.51†") == "0.51"      # dagger


def test_intra_number_spaces_collapse():
    assert N.canonical("- 0.21") == "-0.21"
    assert N.canonical("0. 51") == "0.51"
    assert N.canonical("1 234") == "1234"


def test_thousands_and_decimal_marks():
    assert N.canonical("1,234") == "1234"           # comma thousands
    assert N.canonical("12,345,678") == "12345678"
    assert N.canonical("0,53") == "0.53"            # EU decimal comma
    assert N.canonical("1,234.56") == "1234.56"     # both -> comma is thousands
    assert N.canonical("1.234,56") == "1234.56"     # EU both -> dot thousands


def test_non_numbers_return_none():
    assert N.canonical("") is None
    assert N.canonical(None) is None
    assert N.canonical("n/a") is None
    assert N.canonical("(-0.26 to 0.21)") is None   # a CI, not a single number
    assert N.canonical("1.2.3") is None


def test_value_and_format():
    assert N.value("−0.10") == -0.10
    assert N.format_canonical(-0.1, 2) == "-0.10"
    assert N.format_canonical(0.0, 2) == "0.00"     # no "-0.00"


# ---- LOSSY glyph swaps: candidates only, never eager ----
def test_glyph_swaps_are_candidates_not_eager():
    assert N.canonical("l.43") is None              # not silently turned into 1.43
    cands = N.candidates("l.43")
    assert "1.43" in cands
    assert "0.06" in N.candidates("O.06")


def test_candidates_include_separator_alternatives():
    c = N.candidates("1,234")
    assert "1234" in c                              # thousands reading
    c2 = N.candidates("1.234")
    assert "1.234" in c2 and "1234" in c2           # decimal AND thousands hypotheses


def test_split_mean_sd():
    assert N.split_mean_sd("2.59 ± 0.75") == ("2.59", "0.75")
    assert N.split_mean_sd("2.59 +/- 0.75") == ("2.59", "0.75")
    assert N.split_mean_sd("2.59") is None


# ---- grounding preimages ----
def test_preimages_cover_dropped_minus_and_dashes():
    pre = N.preimages("-0.10")
    assert "-0.10" in pre and "0.10" in pre          # canonical + dropped-minus
    assert any(p.startswith("−") for p in pre)  # a unicode-minus spelling
    assert "0.1" in N.preimages("0.10")              # trailing-zero-insensitive
