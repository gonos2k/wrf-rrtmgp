#!/usr/bin/env python3
"""Summarize same-state RRTMG/ RRTMGP audits and UDM cloud-fraction traces.

The CSV is the paired-seed product from the shadow-wrapper audit. Raw inputs
are the serial RRTMGP trace ``.raw`` files (RRTMGP_RAW_V1); values are never
interpreted as independent grid samples. The reported spread is descriptive
of the deterministic seed set.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any


def _float(token: str, where: str) -> float:
    try:
        value = float(token.replace("D", "E").replace("d", "e"))
    except ValueError as exc:
        raise ValueError(f"{where}: invalid numeric value {token!r}") from exc
    if not math.isfinite(value):
        raise ValueError(f"{where}: non-finite numeric value {token!r}")
    return value


def read_raw(path: Path) -> tuple[dict[str, Any], dict[str, list[float]]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RAW_V1":
        raise ValueError(f"{path}: expected RRTMGP_RAW_V1 raw capture")
    head = lines[1].split()
    if len(head) != 4:
        raise ValueError(f"{path}: malformed phase/i/j/nlay header")
    phase = head[0].upper()
    try:
        i, j, nlay = map(int, head[1:])
    except ValueError as exc:
        raise ValueError(f"{path}: malformed raw header integers") from exc
    if phase not in {"LW", "SW"} or min(i, j, nlay) < 1:
        raise ValueError(f"{path}: invalid raw header {head}")
    fields: dict[str, list[float]] = {}
    k = 2
    while k < len(lines):
        if not lines[k].strip():
            k += 1
            continue
        hdr = lines[k].split()
        line_no = k + 1
        k += 1
        if len(hdr) != 2:
            raise ValueError(f"{path}:{line_no}: expected FIELD count")
        name = hdr[0].upper()
        if name in fields:
            raise ValueError(f"{path}:{line_no}: duplicate field {name}")
        try:
            count = int(hdr[1])
        except ValueError as exc:
            raise ValueError(f"{path}:{line_no}: invalid count for {name}") from exc
        if count < 1:
            raise ValueError(f"{path}:{line_no}: invalid count for {name}")
        values: list[float] = []
        while len(values) < count and k < len(lines):
            for token in lines[k].split():
                values.append(_float(token, f"{path}:{k + 1}"))
            k += 1
            if len(values) > count:
                raise ValueError(f"{path}:{k}: too many values for {name}")
        if len(values) != count:
            raise ValueError(f"{path}: {name} expected {count} values, got {len(values)}")
        fields[name] = values
    return {"phase": phase, "i": i, "j": j, "nlay": nlay}, fields


def _first(fields: dict[str, list[float]], names: tuple[str, ...]) -> tuple[str, list[float]] | None:
    for name in names:
        if name in fields:
            return name, fields[name]
    return None


def raw_cloud_summary(path: Path) -> dict[str, Any]:
    header, fields = read_raw(path)
    cf_rad = _first(fields, ("CF",))  # Builder input after WRF cutoff.
    cf_source = _first(fields, ("RAD_CF_SOURCE", "SOURCE_CF", "CLDFRA_SOURCE"))
    cf_used = _first(fields, ("UDM_CF_USED", "CF_USED", "CF_LAST_USED"))
    cf_recomputed = _first(fields, ("UDM_CF_RECOMPUTED", "CF_RECOMPUTED"))
    if cf_rad is None:
        raise ValueError(f"{path}: missing builder CF field")
    n = len(cf_rad[1])
    if n != header["nlay"]:
        raise ValueError(f"{path}: CF has {n} entries, header has {header['nlay']} layers")
    for label, item in (("source", cf_source), ("used", cf_used), ("recomputed", cf_recomputed)):
        if item and len(item[1]) not in (1, n):
            raise ValueError(f"{path}: {label} CF length must be 1 or {n}")

    paths: dict[str, list[float]] = {}
    for phase in ("LWP", "IWP", "RWP", "SWP", "GWP", "HWP"):
        # Grid-space positive condensate is the definition of a wet layer.
        # Radiation paths can be zero where clear-sky condensate was omitted.
        val = _first(fields, (f"{phase}_GRID", f"{phase}_RADIATION"))
        if val:
            if len(val[1]) != n:
                raise ValueError(f"{path}: {val[0]} length differs from CF")
            paths[phase] = val[1]
    wet = [any(v[k] > 0 for v in paths.values()) for k in range(n)]
    cf = cf_rad[1]
    below = [k for k, v in enumerate(cf) if v < 0.5]
    wet_below = [k for k in below if wet[k]]

    def cf_stats(name: str, item: tuple[str, list[float]] | None) -> dict[str, Any] | None:
        if item is None:
            return None
        vals = item[1] * n if len(item[1]) == 1 else item[1]
        valid = [(k, v) for k, v in enumerate(vals) if 0.0 <= v <= 1.0]
        wet_valid = [(k, v) for k, v in valid if wet[k]]
        return {
            "field": item[0], "valid_layers": len(valid), "sentinel_or_out_of_range_layers": n - len(valid),
            "mean": statistics.fmean(v for _, v in valid) if valid else None,
            "min": min((v for _, v in valid), default=None),
            "max": max((v for _, v in valid), default=None),
            "fraction_below_0p5": sum(v < 0.5 for _, v in valid) / len(valid) if valid else None,
            "wet_layers": len(wet_valid),
            "wet_fraction_below_0p5": sum(v < 0.5 for _, v in wet_valid) / len(wet_valid) if wet_valid else None,
            "wet_layers_cf_between_0p01_and_0p5": sum(0.01 < v < 0.5 for _, v in wet_valid),
            "wet_fraction_cf_between_0p01_and_0p5":
                sum(0.01 < v < 0.5 for _, v in wet_valid) / len(wet_valid) if wet_valid else None,
        }

    # Ratios are intentionally omitted for zero denominators; positive
    # radiation CF with zero comparison CF is reported separately.
    def ratio_stats(denominator: tuple[str, list[float]] | None,
                    numerator: tuple[str, list[float]] | None = None) -> dict[str, Any] | None:
        if denominator is None:
            return None
        numerator = numerator or cf_rad
        den = denominator[1] * n if len(denominator[1]) == 1 else denominator[1]
        num = numerator[1] * n if len(numerator[1]) == 1 else numerator[1]
        ratios: list[float] = []
        positive_over_zero = 0
        for a, b in zip(num, den):
            if b > 0:
                ratios.append(a / b)
            elif b == 0 and a > 0:
                positive_over_zero += 1
        valid_pairs = [(a, b) for a, b in zip(num, den) if 0 <= b <= 1 and 0 <= a <= 1]
        return {
            "numerator_field": numerator[0], "denominator_field": denominator[0],
            "valid_positive_denominator_layers": len(ratios),
            "mean": statistics.fmean(ratios) if ratios else None,
            "min": min(ratios) if ratios else None, "max": max(ratios) if ratios else None,
            "mean_cf_difference": statistics.fmean(a-b for a, b in valid_pairs) if valid_pairs else None,
            "radiation_positive_when_denominator_zero_layers": positive_over_zero,
            "zero_denominator_ratios_omitted": True,
        }

    wet_path_sum = {name: math.fsum(vals) for name, vals in paths.items()}
    return {
        "path": str(path), "phase": header["phase"], "column": [header["i"], header["j"]], "nlay": n,
        "cf": {
            "radiation_builder": cf_stats("radiation_builder", cf_rad),
            "original_radiation_input": cf_stats("original_radiation_input", cf_source),
            "last_used": cf_stats("last_used", cf_used),
            "recomputed": cf_stats("recomputed", cf_recomputed),
            "layers_below_0p5": len(below), "layers_below_0p5_and_wet": len(wet_below),
            "fraction_below_0p5_and_wet_over_wet_layers": len(wet_below) / sum(wet) if any(wet) else None,
            "builder_to_last_used": ratio_stats(cf_used),
            "last_used_to_builder": ratio_stats(cf_rad, cf_used) if cf_used is not None else None,
            "builder_to_recomputed_current_state": ratio_stats(cf_recomputed),
            "recomputed_to_builder": ratio_stats(cf_rad, cf_recomputed) if cf_recomputed is not None else None,
        },
        "cloud_paths_g_m2_by_phase_sum_over_layers": wet_path_sum,
        "wet_layers_any_path_positive": sum(wet),
        "metadata": {
            "radiation_step": fields.get("RADIATION_STEP", []),
            "source_time_seconds": fields.get("SOURCE_TIME_SECONDS", []),
            "udm_cf_source_step": fields.get("UDM_CF_SOURCE_STEP", []),
            "udm_cf_dx_m": fields.get("UDM_CF_DX_M", []),
        },
    }


CSV_REQUIRED = {
    "phase", "domain", "step", "source_seconds", "i", "j", "metric",
    "value37", "value4", "sample_count", "mean37", "sd37", "mean4", "sd4",
}


def radius_mode_label(value: str | None) -> str:
    if value is None or not value.strip():
        return "PRODUCTION_WRAPPER_RADIUS"
    token = value.strip()
    if token == "0":
        return "PRODUCTION_GENERIC4_RADIUS"
    if token == "1":
        return "RRTMG4_NATIVE_RADIUS_COUNTERFACTUAL"
    return token


def read_audit_csv(path: Path) -> tuple[list[dict[str, str]], list[str]]:
    with path.open(newline="", encoding="utf-8") as stream:
        reader = csv.DictReader(stream)
        if reader.fieldnames is None:
            raise ValueError(f"{path}: CSV has no header")
        missing = sorted(CSV_REQUIRED - set(reader.fieldnames))
        if missing:
            raise ValueError(f"{path}: missing CSV columns: {', '.join(missing)}")
        if not ({"sd_delta", "sdDelta"} & set(reader.fieldnames)):
            raise ValueError(f"{path}: missing paired-seed spread column sd_delta")
        return list(reader), list(reader.fieldnames)


def summarize_csv(path: Path) -> dict[str, Any]:
    rows, headers = read_audit_csv(path)
    groups: dict[tuple[str, str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    heat: dict[tuple[str, str, str, str, str], list[dict[str, str]]] = defaultdict(list)
    for rowno, row in enumerate(rows, 2):
        ident = f"{path}:{rowno}"
        for key in ("value37", "value4", "mean37", "mean4"):
            _float(row[key], f"{ident} {key}")
        for key in ("sd37", "sd4", "sample_count", "step", "i", "j"):
            _float(row[key], f"{ident} {key}")
        radius_mode = radius_mode_label(row.get("radius_mode"))
        groups[(row["phase"], row["domain"], row["step"], row["source_seconds"], row["metric"], radius_mode)].append(row)
        if row["metric"].upper().startswith("HEAT_"):
            heat[(row["phase"], row["domain"], row["step"], row["source_seconds"], radius_mode)].append(row)

    metrics = []
    for key, items in sorted(groups.items()):
        domain_rows = [r for r in items if int(r["i"]) == 0 and int(r["j"]) == 0]
        chosen = domain_rows[0] if domain_rows else items[0]
        if len(domain_rows) > 1:
            raise ValueError(f"{path}: duplicate aggregate domain row for {key}")
        delta_sd_name = "sd_delta" if "sd_delta" in headers else "sdDelta" if "sdDelta" in headers else None
        metrics.append({
            "phase": key[0], "domain": key[1], "step": key[2], "source_seconds": key[3], "metric": key[4],
            "radius_mode": key[5],
            "rows": len(items), "aggregate_row_present": bool(domain_rows),
            "sample_count": int(float(chosen["sample_count"])),
            "mean37": float(chosen["mean37"]), "mean4": float(chosen["mean4"]),
            "mean_delta_37_minus_engine4": float(chosen["mean37"]) - float(chosen["mean4"]),
            "sd_paired_delta": _float(chosen[delta_sd_name], f"{path} {key} {delta_sd_name}")
                if delta_sd_name else None,
            "operational_value37": float(chosen["value37"]),
            "operational_engine4_value": float(chosen["value4"]),
        })
    heating = []
    for key, items in sorted(heat.items()):
        items = [r for r in items if int(r["i"]) == 0 and int(r["j"]) == 0] or items
        per_level = [(float(r["mean37"])-float(r["mean4"])) for r in items]
        heating.append({
            "phase": key[0], "domain": key[1], "step": key[2], "source_seconds": key[3],
            "radius_mode": key[4],
            "layers": len(items), "heating_delta_rms_k_day": math.sqrt(statistics.fmean(x*x for x in per_level)),
            "heating_delta_max_abs_k_day": max(map(abs, per_level), default=0.0),
        })
    return {"path": str(path), "rows": len(rows), "columns": headers, "metrics": metrics, "heating_profiles": heating}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--csv", type=Path, required=True, help="paired same_state.csv")
    ap.add_argument("--raw", action="append", type=Path, default=[],
                    help="RRTMGP V1 raw trace or directory containing *.raw; repeatable")
    ap.add_argument("--output", type=Path, required=True, help="JSON report path")
    args = ap.parse_args(argv)
    try:
        raw_paths: list[Path] = []
        for raw in args.raw:
            raw_paths.extend(sorted(raw.glob("*.raw")) if raw.is_dir() else [raw])
        report = {
            "schema": "RRTMGP_SAME_STATE_AUDIT_ANALYSIS_V1",
            "csv_summary": summarize_csv(args.csv),
            "raw_cloud_fraction": [raw_cloud_summary(path) for path in raw_paths],
            "interpretation": {
                "ensemble": "Seed-set spread is descriptive; deterministic seeds are not assumed IID.",
                "delta": "Paired difference is RRTMGP37 minus engine4 for the same captured state and seed index; radius_mode identifies the engine4 radius contract.",
                "native_radius_counterfactual": "radius_mode=1 enables the RRTMG4 wrapper's native-radius flag path; it retains legacy preprocessing and startup-background behavior and is not identical optical-input parity.",
                "heating": "HEAT_k is interpreted as layer K/day; profile RMS and max absolute paired difference are summarized.",
                "cf_ratios": "Ratios with zero last-used/recomputed denominator are omitted and counted separately.",
                "tile_scope": "i=j=0 rows summarize the audited WRF tile, not a global MPI domain mean.",
            },
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    except (OSError, ValueError, KeyError) as exc:
        print(f"analyse_udm_physics_audit: {exc}", file=sys.stderr)
        return 2
    print(json.dumps({"output": str(args.output), "csv_rows": report["csv_summary"]["rows"],
                      "raw_columns": len(report["raw_cloud_fraction"])}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
