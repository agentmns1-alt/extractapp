#!/usr/bin/env python3
"""battery.py — data-type / effect-measure self-consistency checks.

Three tiers (consumed by reliability.py):
  * HARD     — mathematically impossible. A failing value is quarantined unless it can be confirmed.
  * SOFT     — implausible but not impossible. Value is kept but marked `low` and logged.
  * GUARDED  — fires only when its preconditions (ci_level / p_sided / alpha) are known & consistent;
               otherwise returns `na` (never a failure — real papers legitimately differ).

Checks operate on the STRUCTURED fields of the v2 schema (ci_lower, ci_upper, point_estimate, se,
p_value, events, total, ...), not on raw strings. Ratio measures are checked on the log scale with
null = 1; difference measures with null = 0.
"""
import math
from collections import namedtuple
from typing import List, Optional

Check = namedtuple("Check", "name tier status detail fields")
HARD, SOFT, GUARDED = "HARD", "SOFT", "GUARDED"
PASS, FAIL, NA = "pass", "fail", "na"

RATIO_MEASURES = {"OR", "RR (risk ratio)", "RR", "HR", "Rate ratio", "DOR"}
DIFF_MEASURES = {"MD", "SMD (Hedges g)", "SMD (Cohen d)", "SMD", "RD", "Fisher z", "Correlation r"}
UNIT_INTERVAL_MEASURES = {"Proportion", "Sensitivity", "Specificity", "AUC"}
_Z = {80: 1.2816, 90: 1.6449, 95: 1.9600, 99: 2.5758}
DIRECT_METHODS = {"Reported directly", "Author-provided", None, ""}


def _num(x) -> Optional[float]:
    try:
        if x is None or (isinstance(x, float) and math.isnan(x)) or str(x).strip() == "":
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


def _z(ci_level) -> float:
    lv = _num(ci_level)
    return _Z.get(int(lv), 1.9600) if lv is not None else 1.9600


def is_ratio(measure) -> bool:
    return str(measure or "") in RATIO_MEASURES


def _excludes_null(lo: float, hi: float, null: float) -> bool:
    return not (lo <= null <= hi)


def _ok(name, tier, cond, detail, fields):
    return Check(name, tier, PASS if cond else FAIL, "" if cond else detail, tuple(fields))


def check_estimate(rec, alpha: float = 0.05) -> List[Check]:
    """HARD: ci ordering, point-in-CI, p in [0,1], unit-interval measures.
    SOFT: point ~ geomean(CI) for ratios, SE ~ CI-width/2z.
    GUARDED: CI-vs-p consistency."""
    out: List[Check] = []
    pt = _num(rec.get("point_estimate"))
    lo = _num(rec.get("ci_lower"))
    hi = _num(rec.get("ci_upper"))
    p = _num(rec.get("p_value"))
    se = _num(rec.get("se"))
    meas = str(rec.get("effect_measure") or "")
    ratio = is_ratio(meas)
    null = 1.0 if ratio else 0.0

    if lo is not None and hi is not None:
        out.append(_ok("ci_order", HARD, lo <= hi, f"ci_lower {lo} > ci_upper {hi}", ["ci_lower", "ci_upper"]))
    if pt is not None and lo is not None and hi is not None and lo <= hi:
        out.append(_ok("point_in_ci", HARD, lo - 1e-9 <= pt <= hi + 1e-9,
                       f"point {pt} outside CI [{lo},{hi}]", ["point_estimate"]))
    if p is not None:
        out.append(_ok("p_in_unit", HARD, 0.0 <= p <= 1.0, f"p_value {p} outside [0,1]", ["p_value"]))
    if meas in UNIT_INTERVAL_MEASURES and pt is not None:
        out.append(_ok("measure_in_unit", HARD, 0.0 <= pt <= 1.0,
                       f"{meas} point {pt} outside [0,1]", ["point_estimate"]))

    # SOFT: ratio point should sit at the geometric mean of its CI (symmetry on log scale)
    if ratio and pt and lo and hi and pt > 0 and lo > 0 and hi > 0:
        gm = math.exp((math.log(lo) + math.log(hi)) / 2)
        out.append(_ok("ratio_geomean", SOFT, abs(math.log(pt) - math.log(gm)) < 0.05,
                       f"{meas} point {pt} != geomean(CI) {gm:.3f}", ["point_estimate"]))
    # SOFT: reported SE must match the CI width (log scale for ratios)
    if se is not None and lo is not None and hi is not None and lo <= hi:
        z = _z(rec.get("ci_level"))
        if ratio and lo > 0 and hi > 0:
            se_ci = (math.log(hi) - math.log(lo)) / (2 * z)
        else:
            se_ci = (hi - lo) / (2 * z)
        if se_ci > 0:
            out.append(_ok("se_vs_ci", SOFT, abs(se - se_ci) <= 0.15 * max(se, se_ci, 1e-9),
                           f"reported SE {se} != CI-implied {se_ci:.4f}", ["se"]))

    # GUARDED: CI-vs-p — the check that catches a silently dropped sign whose CI is internally valid.
    out.append(_ci_vs_p(rec, pt, lo, hi, p, null, alpha))
    return out


def _ci_vs_p(rec, pt, lo, hi, p, null, alpha) -> Check:
    fields = ["point_estimate", "ci_lower", "ci_upper", "p_value"]
    sided = str(rec.get("p_sided") or "")
    meas = rec.get("effect_measure")
    # preconditions: need CI bounds, a p-value, a two-sided test, a known measure (so null is known)
    if lo is None or hi is None or p is None or lo > hi:
        return Check("ci_vs_p", GUARDED, NA, "missing CI or p", tuple(fields))
    if sided and sided != "Two-sided":
        return Check("ci_vs_p", GUARDED, NA, f"p_sided={sided} (guard)", tuple(fields))
    if not (is_ratio(meas) or str(meas or "") in DIFF_MEASURES):
        return Check("ci_vs_p", GUARDED, NA, "measure/null unknown", tuple(fields))
    excludes = _excludes_null(lo, hi, null)
    significant = p < alpha
    if excludes == significant:
        return Check("ci_vs_p", GUARDED, PASS, "", tuple(fields))
    return Check("ci_vs_p", GUARDED, FAIL,
                 f"CI {'excludes' if excludes else 'includes'} null={null} but p={p} "
                 f"{'<' if significant else '>='} alpha={alpha}", tuple(fields))


def check_armdata(rec) -> List[Check]:
    out: List[Check] = []
    ev = _num(rec.get("events"))
    tot = _num(rec.get("total"))
    n = _num(rec.get("n"))
    sd = _num(rec.get("sd"))
    sem = _num(rec.get("sem"))
    pct = _num(rec.get("pct"))
    mean = _num(rec.get("mean"))
    med = _num(rec.get("median"))
    lo, hi = _num(rec.get("value_min")), _num(rec.get("value_max"))
    iql, iqh = _num(rec.get("iqr_low")), _num(rec.get("iqr_high"))

    if ev is not None:
        out.append(_ok("events_nonneg", HARD, ev >= 0, f"events {ev} < 0", ["events"]))
        out.append(_ok("events_integral", HARD, float(ev).is_integer(), f"events {ev} not integral", ["events"]))
    if tot is not None:
        out.append(_ok("total_pos", HARD, tot >= 1, f"total {tot} < 1", ["total"]))
    if ev is not None and tot is not None:
        out.append(_ok("events_le_total", HARD, ev <= tot, f"events {ev} > total {tot}", ["events", "total"]))
    if sd is not None:
        out.append(_ok("sd_nonneg", HARD, sd >= 0, f"sd {sd} < 0", ["sd"]))
    if n is not None:
        out.append(_ok("n_pos_integral", HARD, n >= 1 and float(n).is_integer(), f"n {n} invalid", ["n"]))
    # SOFT
    if pct is not None and ev is not None and tot and tot > 0:
        out.append(_ok("pct_matches", SOFT, abs(pct - 100 * ev / tot) <= 1.0,
                       f"pct {pct} != 100*{ev}/{tot}", ["pct"]))
    center = mean if mean is not None else med
    if center is not None and lo is not None and hi is not None:
        out.append(_ok("center_in_range", SOFT, lo <= center <= hi,
                       f"center {center} outside [{lo},{hi}]", ["mean", "median"]))
    if med is not None and iql is not None and iqh is not None:
        out.append(_ok("median_in_iqr", SOFT, iql <= med <= iqh,
                       f"median {med} outside IQR [{iql},{iqh}]", ["median"]))
    if sem is not None and sd is not None and n is not None and n > 0:
        out.append(_ok("sem_vs_sd", SOFT, abs(sem * math.sqrt(n) - sd) <= 0.15 * max(sd, 1e-9),
                       f"sem*sqrt(n) {sem*math.sqrt(n):.3f} != sd {sd}", ["sem", "sd"]))
    return out


def check_baseline(rec) -> List[Check]:
    out: List[Check] = []
    n = _num(rec.get("n"))
    val = _num(rec.get("value"))
    dv = _num(rec.get("dispersion_value"))
    lo, hi = _num(rec.get("dispersion_low")), _num(rec.get("dispersion_high"))
    dtype = str(rec.get("dispersion_type") or "")
    if n is not None:
        out.append(_ok("n_nonneg_integral", HARD, n >= 0 and float(n).is_integer(), f"n {n} invalid", ["n"]))
    if dv is not None and dtype in ("SD", "SEM"):
        out.append(_ok("dispersion_nonneg", HARD, dv >= 0, f"{dtype} {dv} < 0", ["dispersion_value"]))
    if lo is not None and hi is not None:
        out.append(_ok("dispersion_order", HARD, lo <= hi, f"dispersion_low {lo} > high {hi}",
                       ["dispersion_low", "dispersion_high"]))
    if val is not None and lo is not None and hi is not None and dtype in ("IQR", "Range", "95%CI"):
        out.append(_ok("value_in_dispersion", SOFT, lo <= val <= hi,
                       f"value {val} outside [{lo},{hi}]", ["value"]))
    return out


def check_number(val, field: str) -> List[Check]:
    """Generic per-field sanity: finiteness + known unit-interval / non-negative / integral ranges."""
    v = _num(val)
    if v is None:
        return []
    out = [_ok("finite", HARD, math.isfinite(v), f"{field}={v} not finite", [field])]
    unit = {"p_value", "pct_proportion", "proportion", "sensitivity", "specificity", "auc"}
    nonneg = {"sd", "se", "variance", "n", "total", "events", "weight_pct"}
    if field in unit:
        out.append(_ok(f"{field}_unit", HARD, 0 <= v <= 1, f"{field}={v} outside [0,1]", [field]))
    if field in nonneg:
        out.append(_ok(f"{field}_nonneg", HARD, v >= 0, f"{field}={v} < 0", [field]))
    return out


def worst(checks: List[Check]):
    """Summarize a set of checks: (has_hard_fail, has_soft_fail, has_guarded_fail)."""
    hard = any(c.tier == HARD and c.status == FAIL for c in checks)
    soft = any(c.tier == SOFT and c.status == FAIL for c in checks)
    guarded = any(c.tier == GUARDED and c.status == FAIL for c in checks)
    return hard, soft, guarded
