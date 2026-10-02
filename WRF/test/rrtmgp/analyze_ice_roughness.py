#!/usr/bin/env python3
"""Summarize separate ice-roughness test runs without ranking categories physically."""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path

CLEAR_FIELDS = (
    "glw_clear_w_m2",
    "olr_clear_w_m2",
    "swdnb_clear_w_m2",
    "swupt_clear_w_m2",
)
FLUX_FIELDS = (
    "glw_w_m2",
    "olr_w_m2",
    "swdnb_w_m2",
    "swupt_w_m2",
    "swddir_w_m2",
    "swddif_w_m2",
    "lwhr_max_abs_k_day",
    "swhr_max_abs_k_day",
)


def read_run(path: Path, expected: int) -> dict[tuple[int, str], dict[str, float]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        required = {"roughness", "ncol", "scenario", *CLEAR_FIELDS, *FLUX_FIELDS}
        if not required.issubset(reader.fieldnames or ()):
            raise ValueError(f"{path}: missing columns {sorted(required - set(reader.fieldnames or ())) }")
        rows = {}
        for row in reader:
            category = int(row["roughness"])
            if category != expected:
                raise ValueError(f"{path}: row says roughness {category}, expected {expected}")
            key = (int(row["ncol"]), row["scenario"])
            values = {name: float(row[name]) for name in (*CLEAR_FIELDS, *FLUX_FIELDS)}
            if not all(math.isfinite(value) for value in values.values()):
                raise ValueError(f"{path}: non-finite value in {key}")
            if key in rows:
                raise ValueError(f"{path}: duplicate row {key}")
            rows[key] = values
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run", action="append", nargs=2, required=True, metavar=("ROUGHNESS", "CSV"),
                        help="provide exactly three runs, one each for roughness 1, 2, and 3")
    parser.add_argument("--output", type=Path, required=True, help="summary JSON output")
    args = parser.parse_args()
    if len(args.run) != 3:
        parser.error("provide exactly three category runs")
    runs = {int(level): read_run(Path(filename), int(level)) for level, filename in args.run}
    if set(runs) != {1, 2, 3}:
        parser.error("runs must contain categories 1, 2, and 3 exactly once")
    keys = set(runs[1])
    if any(set(rows) != keys for rows in runs.values()):
        raise ValueError("category CSV files do not contain identical (ncol, scenario) rows")
    if not any(scenario == "clear" for _, scenario in keys):
        raise ValueError("missing clear-sky reference rows")

    clear_checks = []
    cloudy_ranges = []
    for key in sorted(keys):
        ncol, scenario = key
        for name in CLEAR_FIELDS:
            values = [runs[level][key][name] for level in (1, 2, 3)]
            span = max(values) - min(values)
            scale = max(1.0, *(abs(value) for value in values))
            # Outputs are single-precision; permit a few arithmetic ULPs.
            tolerance = 8.0 * (2.0 ** -23) * scale
            if span > tolerance:
                raise ValueError(f"clear-sky {name} differs by {span:g} for {key} (limit {tolerance:g})")
            clear_checks.append({"ncol": ncol, "scenario": scenario, "field": name,
                                 "max_category_spread": span, "tolerance": tolerance})
        if scenario == "liquid-only":
            for name in FLUX_FIELDS:
                values = [runs[level][key][name] for level in (1, 2, 3)]
                span = max(values) - min(values)
                scale = max(1.0, *(abs(value) for value in values))
                tolerance = 8.0 * (2.0 ** -23) * scale
                if span > tolerance:
                    raise ValueError(
                        f"liquid-only {name} depends on ice roughness by {span:g} for {key} "
                        f"(limit {tolerance:g})"
                    )
        if scenario != "clear":
            for name in FLUX_FIELDS:
                values = [runs[level][key][name] for level in (1, 2, 3)]
                cloudy_ranges.append({"ncol": ncol, "scenario": scenario, "field": name,
                                      "minimum": min(values), "maximum": max(values),
                                      "category_spread": max(values) - min(values)})

    for level, rows in runs.items():
        by_ncol = {(ncol, scenario): data for (ncol, scenario), data in rows.items()}
        for ncol in sorted({key[0] for key in keys}):
            clear = by_ncol[(ncol, "clear")]
            sw_changed = any(
                abs(by_ncol[(ncol, scenario)][field] - clear[field]) > 1.0e-8
                for scenario in {scenario for row_ncol, scenario in keys if row_ncol == ncol and scenario != "clear"}
                for field in ("swdnb_w_m2", "swupt_w_m2", "swddir_w_m2", "swddif_w_m2")
            )
            if not sw_changed:
                raise ValueError(f"roughness {level}, ncol {ncol}: no cloudy SW response")

    roughness_response = any(
        row["field"] in {"swdnb_w_m2", "swupt_w_m2", "swddir_w_m2", "swddif_w_m2"}
        and row["category_spread"] > 1.0e-3
        for row in cloudy_ranges
    )
    if not roughness_response:
        raise ValueError("ice roughness setting produced no SW category response; setting may be ignored")

    output = {
        "roughness_response_detected": roughness_response,
        "status": "PASS",
        "interpretation": (
            "All three roughness settings produced finite results and clear-sky outputs agree within "
            "single-precision tolerance. Cloudy-category differences are descriptive only; this test "
            "does not identify which roughness setting is physically correct."
        ),
        "inputs": {str(level): str(Path(filename)) for level, filename in args.run},
        "clear_sky_invariance": clear_checks,
        "cloudy_category_ranges": cloudy_ranges,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(output, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {args.output}")


if __name__ == "__main__":
    main()
