#!/usr/bin/env python3
"""validate.py — run the full battery over an extraction dataset and summarize per check.

Used in two places: reliability.py (to summarize the CLEANED data for the VALIDATION sheet) and the
release gate in load.py (RELEASE iff zero HARD checks fail after reliability). One battery, one
source of truth. Deterministic: checks are aggregated and sorted by name.
"""
from typing import Dict, List

from . import battery as B

_SHEET_CHECK = {"estimates": B.check_estimate, "armdata": B.check_armdata, "baseline": B.check_baseline}


def _rows(data, key):
    v = data.get(key)
    return [] if v is None else (v if isinstance(v, list) else [v])


def validate_data(data: Dict, alpha: float = 0.05) -> Dict:
    """Return {checks:[{name,tier,status,fail,detail}], hard_fail, soft_fail, guarded_fail}."""
    agg: Dict = {}
    for sheet, fn in _SHEET_CHECK.items():
        for rec in _rows(data, sheet):
            if not isinstance(rec, dict):
                continue
            checks = fn(rec, alpha=alpha) if sheet == "estimates" else fn(rec)
            for c in checks:
                a = agg.setdefault((c.name, c.tier), {"name": c.name, "tier": c.tier,
                                                       "fail": 0, "detail": ""})
                if c.status == B.FAIL:
                    a["fail"] += 1
                    if not a["detail"]:
                        a["detail"] = c.detail
    checks: List = []
    hard = soft = guarded = 0
    for (name, tier), a in sorted(agg.items()):
        if a["fail"] and tier == B.HARD:
            status, hard = "FAIL", hard + a["fail"]
        elif a["fail"] and tier == B.SOFT:
            status, soft = "WARN", soft + a["fail"]
        elif a["fail"] and tier == B.GUARDED:
            status, guarded = "WARN", guarded + a["fail"]
        else:
            status = "PASS"
        checks.append({"name": name, "tier": tier, "status": status, "fail": a["fail"], "detail": a["detail"]})
    return {"checks": checks, "hard_fail": hard, "soft_fail": soft, "guarded_fail": guarded}
