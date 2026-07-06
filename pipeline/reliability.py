#!/usr/bin/env python3
"""reliability.py — Engine orchestrator + deterministic rubric (the app that distrusts its input).

Walks every numeric field of the extraction JSON and, for each:
  localize (semantic, no value-match) -> reconcile (two-view, Engine 1) with the battery closure
  -> ground (Engine 3) -> rubric -> annotate OR quarantine (null the value).

Quarantine (value nulled in release, logged) when: a HARD or evaluable-GUARDED failure cannot be
confirmed/fixed, the number is unlocalizable, a correction is ambiguous, or a directly-reported
value is ungroundable. Otherwise the value is kept with a deterministically-assigned confidence
that OVERWRITES any model-supplied confidence.

`process(data, grids, spans, pdf_reader, image_reader, alpha, run_ts) -> (clean_data, report)`.
The report carries quarantine entries, per-field annotations, aggregate checks, and telemetry.
Deterministic: fixed sheet/field order, no wall-clock in the data.
"""
import copy
from typing import Optional, Callable, Dict, List

from . import numbers as N
from . import battery as B
from . import localize as L
from . import readers as RD
from . import reconcile as RC
from . import grounding as GR

SHEET_ORDER = ["study", "arms", "baseline", "outcomes", "comparisons", "armdata", "estimates", "rob"]
ID_FIELD = {"study": "study_id", "arms": "arm_id", "baseline": "characteristic", "outcomes": "outcome_id",
            "comparisons": "comparison_id", "armdata": "data_id", "estimates": "estimate_id", "rob": "rob_id"}
NUMERIC: Dict[str, List[str]] = {
    "estimates": ["point_estimate", "ci_lower", "ci_upper", "se", "p_value", "variance", "weight_pct", "oe", "var_oe"],
    "armdata": ["mean", "sd", "sem", "median", "iqr_low", "iqr_high", "value_min", "value_max",
                "change_mean", "change_sd", "change_se", "events", "total", "pct", "n", "rate"],
    "baseline": ["value", "dispersion_value", "dispersion_low", "dispersion_high", "n"],
    "arms": ["n_randomised", "n_analysed", "adherence_pct"],
    "study": ["n_randomised_total", "n_analysed_total", "n_centres"],
    "outcomes": ["timepoint_value"],
    "comparisons": ["control_split_factor", "n_arms_sharing_control"],
    "rob": [],
}
PRIMARY = {"estimates": "point_estimate", "armdata": "mean", "baseline": "value"}
_TRANSFORM_DERIV = {"From 95% CI", "From SE", "From t/F statistic", "From t/F", "From p-value",
                    "From IQR (Wan 2014)", "From range (Wan 2014)", "From median (Luo 2018)", "Pooled SD"}
_RANK = {"quarantine": 0, "low": 1, "medium": 2, "high": 3}
_RANK_INV = {v: k for k, v in _RANK.items()}


def _battery(sheet: str, rec: dict, alpha: float) -> List[B.Check]:
    if sheet == "estimates":
        return B.check_estimate(rec, alpha=alpha)
    if sheet == "armdata":
        return B.check_armdata(rec)
    if sheet == "baseline":
        return B.check_baseline(rec)
    out = []
    for f in NUMERIC.get(sheet, []):
        out.extend(B.check_number(rec.get(f), f))
    return out


def _field_ok(checks, field) -> bool:
    """HARD-clean AND no evaluable-GUARDED failure implicating the field (SOFT ignored)."""
    for c in checks:
        if c.status == B.FAIL and c.tier in (B.HARD, B.GUARDED) and field in c.fields:
            return False
    return True


def _make_ok(sheet, rec, field, alpha) -> Callable:
    def ok(cand):
        r2 = dict(rec)
        r2[field] = cand
        return _field_ok(_battery(sheet, r2, alpha), field)
    return ok


def _candidates(raw, canon) -> List[str]:
    cands = list(N.candidates(raw))
    f = N.to_float(canon) if canon else None
    if f is not None and f != 0:                      # dropped-minus / sign-flip hypothesis
        neg = N.format_canonical(-f, N.decimals(canon))
        if neg not in cands:
            cands.append(neg)
    return cands


def _derive_labels(sheet, rec, arms, outcomes):
    row = rec.get("_row_label")
    col = rec.get("_col_label")
    if not row:
        if sheet in ("armdata", "estimates"):
            row = outcomes.get(rec.get("outcome_id"))
        elif sheet == "baseline":
            row = rec.get("characteristic")
    if not col:
        if sheet in ("armdata", "baseline"):
            col = arms.get(rec.get("arm_id"))
        elif sheet == "estimates":
            col = "treatment effect"
    return row, col


def _locate(sheet, rec, grids, spans, arms, outcomes):
    """Return (loc_obj_with_text_bbox_page, attempted). loc is None if unlocalizable."""
    if not grids and not spans:
        return None, False
    row, col = _derive_labels(sheet, rec, arms, outcomes)
    cell = L.find_cell(grids or [], row, col) if (row and col) else None
    if cell is not None:
        return cell, True
    if spans and row:
        sp = L.find_text_span(spans, rec.get("_page"), row)
        if sp is not None:
            return sp, True
    return None, True


def _rows(data, key):
    v = data.get(key)
    return [] if v is None else (v if isinstance(v, list) else [v])


def process(data, grids=None, spans=None, pdf_reader=RD.pdfplumber_reader,
            image_reader=RD.tesseract_reader, alpha=None, run_ts=None):
    data = copy.deepcopy(data)
    if alpha is None:
        rev = data.get("review") or {}
        alpha = B._num((rev.get("alpha_level"))) or 0.05
    arms = {a.get("arm_id"): a.get("arm_label") for a in _rows(data, "arms")}
    outcomes = {o.get("outcome_id"): o.get("outcome_name") for o in _rows(data, "outcomes")}

    quarantine, annotations = [], []
    tel = {"numbers": 0, "confirmed": 0, "needs_vision": 0, "quarantined": 0,
           "hard_fail": 0, "soft_fail": 0, "guarded_fail": 0,
           "confidence": {"high": 0, "medium": 0, "low": 0}}

    for sheet in SHEET_ORDER:
        recs = _rows(data, sheet)
        for idx, rec in enumerate(recs):
            if not isinstance(rec, dict):
                continue
            row_id = rec.get(ID_FIELD[sheet]) or f"{sheet}[{idx}]"
            checks = _battery(sheet, rec, alpha)
            hard, soft, guarded = B.worst(checks)
            tel["hard_fail"] += int(hard); tel["soft_fail"] += int(soft); tel["guarded_fail"] += int(guarded)
            loc, attempted = _locate(sheet, rec, grids, spans, arms, outcomes)
            cell_text = getattr(loc, "text", None)
            page = getattr(loc, "page", rec.get("_page"))
            bbox = list(getattr(loc, "bbox", ()) or []) or None

            row_rank = _RANK["medium"]                 # text row default
            row_mod, row_deriv = "text", None
            primary_field = PRIMARY.get(sheet)

            for field in NUMERIC.get(sheet, []):
                raw = rec.get(field)
                canon = N.canonical(raw)
                if canon is None:
                    continue
                tel["numbers"] += 1
                # unlocalizable -> quarantine (only when localization was attempted for a table sheet)
                if attempted and loc is None and sheet in PRIMARY:
                    _quarantine(rec, field, quarantine, sheet, row_id, "unlocalized", raw)
                    tel["quarantined"] += 1
                    row_rank = min(row_rank, _RANK["low"])
                    continue

                ok = _make_ok(sheet, rec, field, alpha)
                ctx = RD.Ctx(primary=canon, candidates=_candidates(raw, canon), hard_ok=ok)
                req = RD._req(page=page, bbox=bbox, cell_text=cell_text, target=canon,
                              pdf_path=rec.get("_pdf_path"), page_image_path=rec.get("_page_image"))
                d = RC.reconcile(ctx, req, pdf_reader=pdf_reader, image_reader=image_reader)

                if d.quarantine:
                    _quarantine(rec, field, quarantine, sheet, row_id, d.quarantine, raw)
                    tel["quarantined"] += 1
                    row_rank = min(row_rank, _RANK["low"])
                    continue

                deriv = d.derivation or rec.get("derivation_method")
                # Engine 3 grounding on the kept value (skip if we have no localized text)
                if cell_text is not None:
                    grounded, _r = GR.ground(d.value, cell_text, deriv)
                    if not grounded:
                        _quarantine(rec, field, quarantine, sheet, row_id, "ungrounded-value", raw)
                        tel["quarantined"] += 1
                        row_rank = min(row_rank, _RANK["low"])
                        continue

                # keep (possibly corrected) value in canonical form
                rec[field] = d.value
                field_soft = any(c.tier == B.SOFT and c.status == B.FAIL and field in c.fields for c in checks)
                conf = _rubric(d, deriv, field_soft)
                tel["confidence"][conf] += 1
                if d.confirmed:
                    tel["confirmed"] += 1
                if d.needs_vision:
                    tel["needs_vision"] += 1
                annotations.append({"sheet": sheet, "row_id": row_id, "field": field, "confidence": conf,
                                    "source_modality": d.modality or "text", "derivation_method": deriv,
                                    "needs_vision": d.needs_vision, "page": page, "bbox": bbox, "reason": d.reason})
                row_rank = min(row_rank, _RANK[conf])
                if field == primary_field or (primary_field is None):
                    row_mod = d.modality or row_mod
                    row_deriv = deriv

            rec["confidence"] = _RANK_INV[row_rank]
            rec["source_modality"] = row_mod
            if row_deriv:
                rec["derivation_method"] = row_deriv
            rec["extractor"] = rec.get("extractor") or f"extractapp/reliability/{run_ts}"

    tel["quarantine_rate"] = round(tel["quarantined"] / tel["numbers"], 4) if tel["numbers"] else 0.0
    tel["confirmed_rate"] = round(tel["confirmed"] / tel["numbers"], 4) if tel["numbers"] else 0.0
    report = {"quarantine": quarantine, "annotations": annotations, "telemetry": tel,
              "checks": _summary_checks(data, alpha), "run_ts": run_ts}
    return data, report


def _quarantine(rec, field, quarantine, sheet, row_id, reason, original):
    rec[field] = None                                 # null in the release table
    quarantine.append({"sheet": sheet, "row_id": str(row_id), "field": field,
                       "reason": reason, "original": str(original)})


def _rubric(d: RC.Decision, deriv, field_soft) -> str:
    """Deterministic, sole authority. Overwrites model confidence."""
    directly = deriv in GR.DIRECT_METHODS
    if d.needs_vision:
        return "low"
    if field_soft:
        return "low"
    if d.confirmed and directly:
        return "high"
    if (deriv in _TRANSFORM_DERIV) or d.derivation == "derived":
        return "medium"
    if directly:
        return "medium"                               # text-only, battery-clean, directly reported
    return "medium"


def _summary_checks(data, alpha):
    """Aggregate the battery over the CLEANED data -> per-check pass/fail counts for VALIDATION."""
    agg = {}
    for sheet in ("estimates", "armdata", "baseline"):
        for rec in _rows(data, sheet):
            if not isinstance(rec, dict):
                continue
            for c in _battery(sheet, rec, alpha):
                k = (c.name, c.tier)
                a = agg.setdefault(k, {"name": c.name, "tier": c.tier, "fail": 0, "na": 0, "pass": 0})
                a[c.status] = a.get(c.status, 0) + 1
    out = []
    for (name, tier), a in sorted(agg.items()):
        if a["fail"] and tier == B.HARD:
            status = "FAIL"                            # a hard fail after cleaning blocks release
        elif a["fail"]:
            status = "WARN"                            # soft / guarded residue
        else:
            status = "PASS"
        out.append({"name": name, "tier": tier, "status": status, "fail": a["fail"], "detail": ""})
    return out
