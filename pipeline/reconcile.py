#!/usr/bin/env python3
"""reconcile.py — Engine 1: two-view reconciliation for one localized number.

Takes the primary (model/text-layer) value plus a battery closure, asks the reader ladder for a
second view, and decides the outcome:

  primary passes HARD:
    - no second source        -> kept, text-only (unconfirmed)          [rubric -> medium]
    - second agrees           -> confirmed; modality per the source     [rubric -> high]
    - second disagrees        -> second wins (image/second-source)       [rubric -> high]
    - text-vs-text unresolved -> kept but needs_vision (two text views)  [rubric -> low]
  primary FAILS HARD:
    - unique constraint fix / image read -> corrected value              [rubric -> medium/high]
    - ambiguous / needs_vision / nothing -> QUARANTINE (value nulled)

`source_modality=table-image` is set only when an image rung actually produced the value.
"""
from collections import namedtuple
from typing import Optional, Callable

from . import readers as RD

Decision = namedtuple("Decision",
                      "value confirmed modality derivation needs_vision quarantine reason rung")

_IMAGE_RUNGS = {"fixture", "tesseract", "vlm"}


def reconcile(ctx: RD.Ctx, req: RD.Req,
              pdf_reader: Optional[Callable] = RD.pdfplumber_reader,
              image_reader: Optional[Callable] = RD.tesseract_reader) -> Decision:
    primary = ctx.primary
    primary_ok = primary is not None and ctx.hard_ok(primary)
    second = RD.run_ladder(ctx, req, pdf_reader=pdf_reader, image_reader=image_reader)

    if primary_ok:
        if second is None:
            return Decision(primary, False, "text", None, False, None, "text-only (battery-clean)", "primary")
        if second is RD.NEEDS_VISION:
            return Decision(primary, False, "text", None, True, None,
                            "text disagreement, image unavailable", "primary")
        if second is RD.AMBIGUOUS:                       # not expected on a clean primary
            return Decision(primary, False, "text", None, True, None, "ambiguous second view", "primary")
        if second.value == primary:
            mod = "table-image" if second.rung in _IMAGE_RUNGS else "text"
            return Decision(primary, True, mod, None, False, None, f"confirmed ({second.rung})", second.rung)
        # disagreement — second (image/second-source) wins
        mod = "table-image" if second.rung in _IMAGE_RUNGS else "text"
        return Decision(second.value, True, mod, None, False, None,
                        f"reconciled: text={primary} -> {second.rung}={second.value}", second.rung)

    # primary is hard-broken -> must confirm/fix or quarantine
    if second is None:
        return Decision(None, False, None, None, False, "hard-fail-unconfirmable",
                        f"hard-broken value {primary} could not be confirmed", "quarantine")
    if second is RD.AMBIGUOUS:
        return Decision(None, False, None, None, False, "ambiguous-correction",
                        f"multiple candidates satisfy the checks for {primary}", "quarantine")
    if second is RD.NEEDS_VISION:
        return Decision(None, False, None, None, True, "needs-vision-hard-fail",
                        f"hard-broken value {primary} needs an image read (unavailable)", "quarantine")
    # a concrete corrected value
    deriv = "derived" if second.rung == "constraint" else None
    mod = "table-image" if second.rung in _IMAGE_RUNGS else ("text" if second.rung == "pdfplumber" else None)
    return Decision(second.value, True, mod, deriv, False, None,
                    f"corrected via {second.rung}: {primary} -> {second.value}", second.rung)
