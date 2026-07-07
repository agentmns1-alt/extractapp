#!/usr/bin/env python3
"""demo.py — run the reliability layer on a small mixed dataset and write a workbook to ./out.

Shows the quarantine-over-guess gate end to end: a clean row, a normalization repair, a unique
constraint fix, and an impossible row that gets quarantined (nulled + logged) -> DRAFT workbook.
Deterministic: run_ts is fixed, so re-running produces byte-identical output.
"""
from pipeline import load as LD

RUN_TS = "2020-01-01T00:00:00+00:00"

DATA = {
    "outcomes": [{"outcome_id": "O1", "outcome_name": "ALSFRS-R"}],
    "estimates": [
        # clean, directly reported
        {"estimate_id": "E1", "outcome_id": "O1", "effect_measure": "MD", "point_estimate": -0.02,
         "ci_lower": -0.26, "ci_upper": 0.21, "p_value": 0.843, "p_sided": "Two-sided",
         "derivation_method": "Reported directly"},
        # en-dash minus in the text layer -> safely normalized
        {"estimate_id": "E2", "outcome_id": "O1", "effect_measure": "MD", "point_estimate": "–0.10",
         "ci_lower": -0.30, "ci_upper": 0.11, "derivation_method": "Reported directly"},
        # dropped minus makes the point fall outside its CI -> unique constraint fix to -0.53
        {"estimate_id": "E3", "outcome_id": "O1", "effect_measure": "MD", "point_estimate": "0.53",
         "ci_lower": "-1.02", "ci_upper": "-0.04"},
    ],
    # impossible: events > total, unconfirmable without an image -> quarantined (nulled + logged)
    "armdata": [{"data_id": "D1", "arm_id": "A1", "outcome_id": "O1", "events": 50, "total": 20}],
}


def main():
    res = LD.extract(DATA, "out", run_ts=RUN_TS)
    print(res["stamp"])
    print(f"  status      : {res['status']}")
    print(f"  workbook    : {res['path']}")
    print(f"  quarantined : {res['quarantined']}")
    print(f"  hard_fail   : {res['hard_fail']}")


if __name__ == "__main__":
    main()
