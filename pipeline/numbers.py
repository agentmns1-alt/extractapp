#!/usr/bin/env python3
"""numbers.py — normalize a raw numeric token to a canonical string, preserving reported decimals.

Two tiers, per spec:
  * SAFE unifications are applied directly (they cannot change the value): dash/minus variants,
    footnote/reference superscripts glued to a number, thousands separators, decimal mark,
    intra-number spaces.
  * LOSSY glyph swaps (x/x/9, O/0, l/1) are NEVER applied eagerly. They are returned by
    `candidates()` as position-guarded hypotheses for the battery / constraint solver to test.

Canonical form preserves the reported number of decimals ("-0.10", not "-0.1") and uses an ASCII
"-" sign, so cross-run diffs are meaningful and output is byte-stable.
"""
import re
from typing import Optional, List, Set, Tuple

# leading-sign dash/minus variants unified to ASCII "-"
_DASHES = "−–—‐‑‒―－"          # − – — ‐ ‑ ‒ ― －
_DASH_RE = re.compile("[" + re.escape(_DASHES) + "]")
# superscript reference markers glued to a number (footnote digits/letters, [12], daggers, *)
_SUPERS = "¹²³⁰ⁱ⁴⁵⁶⁷⁸⁹†‡§¶"
_TRAIL_MARK_RE = re.compile(
    r"(?<=\d)(?:\[[0-9,\s]+\]|[" + re.escape(_SUPERS) + r"]+|\*+|[a-z](?![a-z]))$"
)
_NUMBER_BODY = re.compile(r"^-?\d[\d]*(?:\.\d+)?$")


def _strip_marks(s: str) -> str:
    prev = None
    while prev != s:                     # peel possibly-stacked markers: "1.33[12]*"
        prev = s
        s = _TRAIL_MARK_RE.sub("", s).strip()
    return s


def _apply_separators(s: str) -> Optional[str]:
    """Resolve thousands vs decimal separators to a plain `[-]int[.frac]` string. None if not numeric."""
    neg = s.startswith("-")
    body = s[1:] if neg else s
    if not re.fullmatch(r"[0-9.,]+", body or ""):
        return None
    has_dot, has_com = "." in body, "," in body
    if has_dot and has_com:
        dec = "." if body.rfind(".") > body.rfind(",") else ","      # rightmost is the decimal
        thou = "," if dec == "." else "."
        body = body.replace(thou, "")
        if dec == ",":
            body = body.replace(",", ".")
    elif has_com:
        if re.fullmatch(r"\d{1,3}(,\d{3})+", body):                  # 1,234 / 12,345,678 -> thousands
            body = body.replace(",", "")
        else:
            body = body.replace(",", ".")                            # 0,53 -> decimal
    # a period is left as the decimal mark by default (English convention)
    if body.count(".") > 1:
        return None
    if not re.fullmatch(r"\d+(?:\.\d+)?", body):
        return None
    return ("-" + body) if neg else body


def canonical(token) -> Optional[str]:
    """Return the SAFE canonical string for a single numeric token, or None if not a number.

    Preserves the reported decimals. Applies only value-preserving unifications.
    """
    if token is None:
        return None
    s = str(token).strip()
    if s == "":
        return None
    s = _DASH_RE.sub("-", s)
    s = s.replace(" ", " ")
    # collapse spaces that sit *inside* a single number ("- 0.21", "0. 51", "1 234")
    if re.fullmatch(r"-?\s*[0-9][0-9.,\s]*", s):
        s = re.sub(r"\s+", "", s)
    s = _strip_marks(s)
    # keep at most one leading '-'
    neg = s.startswith("-")
    s = "-" + s.lstrip("-") if neg else s.lstrip("-")
    out = _apply_separators(s)
    if out is None or not _NUMBER_BODY.match(out):
        return None
    return out


def to_float(canonical_str) -> Optional[float]:
    try:
        return float(canonical_str)
    except (TypeError, ValueError):
        return None


def value(token) -> Optional[float]:
    """Convenience: canonical then float."""
    c = canonical(token)
    return to_float(c) if c is not None else None


def decimals(canonical_str: Optional[str]) -> int:
    if canonical_str and "." in canonical_str:
        return len(canonical_str.split(".", 1)[1])
    return 0


def format_canonical(val: float, dec: int) -> str:
    """Render a float to a canonical string with `dec` decimals and ASCII minus."""
    s = f"{val:.{dec}f}"
    if s.startswith("-0") and float(s) == 0.0:      # avoid "-0.00"
        s = s[1:]
    return s


# ---- LOSSY glyph-swap hypotheses (never applied eagerly) ----
_GLYPH_SWAPS = {"O": "0", "o": "0", "l": "1", "I": "1", "i": "1", "S": "5", "B": "8", "Z": "2"}


def _swap_candidates(raw: str) -> List[str]:
    """Position-guarded single-glyph swaps in a token that ALMOST looks numeric."""
    out = []
    core = raw.strip()
    if not re.fullmatch(r"[-0-9.,OolIiSBZx×\s]+", core or ""):
        return out
    # x / × used as a multiplier or mis-read digit -> try dropping/《9》 is context-specific; handled by caller
    swapped = "".join(_GLYPH_SWAPS.get(ch, ch) for ch in core)
    c = canonical(swapped)
    if c is not None:
        out.append(c)
    return out


def candidates(token) -> List[str]:
    """Ordered, de-duplicated canonical interpretations to TEST against the battery.

    Includes the safe canonical, the ambiguous-separator alternative, and lossy glyph-swap
    hypotheses. The caller (battery / constraint solver) decides which survives; nothing here
    is emitted without being checked.
    """
    out: List[str] = []

    def add(c):
        if c is not None and c not in out:
            out.append(c)

    add(canonical(token))
    s = _DASH_RE.sub("-", str(token or "").strip())
    s = _strip_marks(re.sub(r"\s+", "", s)) if re.fullmatch(r"-?\s*[0-9][0-9.,\s]*", s) else _strip_marks(s)
    neg = s.startswith("-")
    body = s[1:] if neg else s
    # ambiguous single-comma or single-dot: offer the other reading as a candidate
    if re.fullmatch(r"\d{1,3},\d{3}", body):                         # 1,234 -> also 1234
        add(("-" if neg else "") + body.replace(",", ""))
    if re.fullmatch(r"\d{1,3}\.\d{3}", body):                        # 1.234 -> also 1234
        add(("-" if neg else "") + body.replace(".", ""))
    for c in _swap_candidates(str(token)):
        add(c)
    return out


def split_mean_sd(token) -> Optional[Tuple[str, str]]:
    """Split 'a ± b' (any ± / +- variant, or a lost-± single space) into two canonical numbers."""
    s = str(token or "").strip()
    m = re.split(r"\s*(?:±|\+/-|\+-)\s*", s)
    if len(m) == 2:
        a, b = canonical(m[0]), canonical(m[1])
        return (a, b) if a is not None and b is not None else None
    return None


_NUM_IN_TEXT = re.compile(r"-?\d[\d.,]*")


def preimages(canonical_str: str) -> Set[str]:
    """Source strings that could have produced this canonical value under the SAFE corruptions.

    Used by grounding to search a cell's own text: we accept the canonical form, its dropped-minus
    form, and dash-variant spellings.
    """
    out: Set[str] = set()
    if not canonical_str:
        return out
    out.add(canonical_str)
    neg = canonical_str.startswith("-")
    bare = canonical_str[1:] if neg else canonical_str
    out.add(bare)                                     # dropped-minus preimage
    if neg:
        for d in "-−–‐‑":
            out.add(d + bare)
    # trailing-zero-insensitive form (0.1 <-> 0.10)
    if "." in bare:
        out.add(bare.rstrip("0").rstrip("."))
    return out
