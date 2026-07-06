#!/usr/bin/env python3
"""grounding.py — Engine 3: transcription-fidelity guard (anti-hallucination).

A number's canonical string (or a battery-confirmed corruption preimage) must be locatable WITHIN
its own localized cell/span — not document-wide (document-wide matching is what lets a hallucinated
number "find itself" elsewhere). Computed values are exempt: a legitimate derivation (From CI / From
SE / Pooled SD / ...) need not appear verbatim in the source.

Ungroundable, directly-reported numbers are quarantined as `ungrounded-value`.
"""
import re
from typing import Optional, Tuple

from . import numbers as N

# a value is grounding-exempt when it was computed rather than transcribed
DIRECT_METHODS = {"Reported directly", "Author-provided", "", None}
_TOKEN_RE = re.compile(r"[-−–‐‑]?\s*\d[\d.,\s]*")


def _cell_numbers(cell_text: str):
    """Canonical numbers present in a cell/span."""
    out = set()
    for tok in _TOKEN_RE.findall(cell_text or ""):
        c = N.canonical(tok)
        if c is not None:
            out.add(c)
    return out


def is_exempt(derivation_method) -> bool:
    """True when the value was computed (not transcribed) and so need not appear verbatim."""
    return derivation_method not in DIRECT_METHODS


def ground(value_canonical: Optional[str], cell_text: Optional[str],
           derivation_method=None) -> Tuple[bool, str]:
    """Return (grounded, reason). Computed values are grounded-by-exemption."""
    if derivation_method not in DIRECT_METHODS:
        return True, f"exempt (computed: {derivation_method})"
    if value_canonical is None:
        return True, "no value to ground"
    present = _cell_numbers(cell_text or "")
    if not present:
        return False, "cell text has no numbers to ground against"
    if value_canonical in present:
        return True, "canonical present in cell"
    try:
        vf = float(value_canonical)
        if any(abs(vf - float(p)) < 1e-9 for p in present):
            return True, "numeric match in cell"
    except ValueError:
        pass
    for pre in N.preimages(value_canonical):
        cpre = N.canonical(pre)
        if cpre is not None and cpre in present:
            return True, f"preimage '{pre}' present in cell"
    return False, f"'{value_canonical}' not found in its own cell"
