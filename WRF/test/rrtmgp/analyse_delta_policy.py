#!/usr/bin/env python3
"""Summarize the exploratory SW delta-scaling benchmark CSV."""
import argparse
import csv
import json
import math
from pathlib import Path


CASES = {
    "liquid", "ice", "rain", "snow", "liquid_plus_rain", "ice_plus_snow",
    "mixed", "graupel_omitted", "graupel_as_snow_assumed",
}
POLICIES = {"D(C)+D(P)", "C+D(P)", "D(C+P)"}
OPTICS = ("combined_tau", "combined_ssa", "combined_g")
FLUXES = (
    "surface_dn_w_m2", "surface_up_w_m2", "toa_dn_w_m2", "toa_up_w_m2",
    "surface_direct_w_m2", "max_abs_heating_k_day",
)
QG_METRICS = OPTICS + FLUXES


def finite_float(row, field, row_number):
    try:
        value = float(row[field])
    except (KeyError, ValueError) as exc:
        raise ValueError(f"row {row_number}: invalid {field}") from exc
    if not math.isfinite(value):
        raise ValueError(f"row {row_number}: non-finite {field}")
    return value


def max_delta(records, metric, left_name, right_name, pair_key):
    maximum = {"absolute": -1.0, "signed": 0.0, "key": None}
    for key, by_policy in records.items():
        left = by_policy[left_name]
        right = by_policy[right_name]
        signed = left[metric] - right[metric]
        if abs(signed) > maximum["absolute"]:
            maximum = {"absolute": abs(signed), "signed": signed, "key": pair_key(key)}
    return maximum


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("csv_path", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()

    data = {}
    row_count = 0
    with args.csv_path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"case", "roughness", "mu0", "policy", "band", *OPTICS, *FLUXES}
        if reader.fieldnames is None or not required.issubset(reader.fieldnames):
            raise ValueError("CSV is missing required columns")
        for row_count, row in enumerate(reader, start=2):
            case = row["case"]
            policy = row["policy"]
            if case not in CASES or policy not in POLICIES:
                raise ValueError(f"row {row_count}: unexpected case or policy")
            rough = int(row["roughness"])
            band = int(row["band"])
            mu0 = finite_float(row, "mu0", row_count)
            key = (case, rough, mu0, band)
            if policy in data.setdefault(key, {}):
                raise ValueError(f"row {row_count}: duplicate {key} / {policy}")
            data[key][policy] = {
                field: finite_float(row, field, row_count) for field in OPTICS + FLUXES
            }
    if row_count - 1 != 3402:
        raise ValueError(f"expected 3402 data rows, found {row_count - 1}")
    expected = {
        (case, rough, mu0, band)
        for case in CASES for rough in (1, 2, 3) for mu0 in (0.2, 0.5, 0.9)
        for band in range(1, 15)
    }
    if set(data) != expected or any(set(v) != POLICIES for v in data.values()):
        raise ValueError("CSV does not contain the complete 9 x 3 x 3 x 14 comparison grid")

    group_key = lambda key: (key[0], key[1], key[2], key[3])
    comparison = {}
    for policy in ("D(C)+D(P)", "D(C+P)"):
        comparison[policy] = {
            metric: max_delta(data, metric, policy, "C+D(P)", group_key)
            for metric in OPTICS + FLUXES
        }

    qg = {}
    for metric in QG_METRICS:
        maximum = {"absolute": -1.0, "signed": 0.0, "key": None}
        for case_key, policies in data.items():
            case, rough, mu0, band = case_key
            if case != "graupel_omitted" or band != 1:
                continue
            snow_key = ("graupel_as_snow_assumed", rough, mu0, band)
            for policy in POLICIES:
                signed = data[snow_key][policy][metric] - policies[policy][metric]
                if abs(signed) > maximum["absolute"]:
                    maximum = {
                        "absolute": abs(signed), "signed": signed,
                        "key": {"roughness": rough, "mu0": mu0, "policy": policy},
                    }
        qg[metric] = maximum

    result = {
        "description": "Exploratory one-layer SW optical composition benchmark; not a forecast validation or production policy selection.",
        "source_policy": "Pinned CCPP implements C+D(P): precipitation is manually delta-scaled before cloud increment and the later whole-cloud scaling call is commented out.",
        "grid": {"cases": sorted(CASES), "roughness": [1, 2, 3], "mu0": [0.2, 0.5, 0.9], "sw_bands": 14, "rows": row_count - 1},
        "policy_delta_vs_pinned_ccpp_C_plus_D_P": comparison,
        "graupel_as_snow_minus_omitted_counterfactual": qg,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote delta-policy summary to {args.output}")


if __name__ == "__main__":
    main()
