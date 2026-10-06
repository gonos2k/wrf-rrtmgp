#!/usr/bin/env python3
"""Independently validate native dry-mass UDM inputs from an actual SCM capture.

The raw capture and its sibling ``.input`` must be from the same first
radiation call.  ``wrfinput`` provides the independently stored native dry
coordinate and seven mass mixing ratios; an optional history file binds the
capture to a timestamp and is required to match the initial input state.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np


G_M_S2 = 9.81
FLOAT32_EPS = float(np.finfo(np.float32).eps)
FLOAT32_TINY_SUBNORMAL = float(np.nextafter(np.float32(0.0), np.float32(1.0)))
MASS_VARIABLES = {
    "QV": "QVAPOR", "QC": "QCLOUD", "QR": "QRAIN", "QI": "QICE",
    "QS": "QSNOW", "QG": "QGRAUP", "QH": "QHAIL",
}
PHASES = {
    "LWP": ("QC", "LWP"), "IWP": ("QI", "IWP"), "RWP": ("QR", "RWP"),
    "SWP": ("QS", "SWP"), "GWP": ("QG", "GWP"), "HWP": ("QH", "HWP"),
}


class ValidationError(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ValidationError(message)


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def read_raw(path: Path) -> tuple[str, int, int, int, dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    require(len(lines) >= 2 and lines[0].strip() == "RRTMGP_RAW_V1",
            f"{path}: expected RRTMGP_RAW_V1")
    header = lines[1].split()
    require(len(header) == 4, f"{path}: malformed phase/index/layer header")
    phase = header[0].upper()
    try:
        i, j, nl = map(int, header[1:])
    except ValueError as exc:
        raise ValidationError(f"{path}: invalid raw header integers") from exc
    require(phase in {"LW", "SW"} and min(i, j, nl) > 0, f"{path}: invalid raw header")
    records: dict[str, np.ndarray] = {}
    pos = 2
    while pos < len(lines):
        if not lines[pos].strip():
            pos += 1
            continue
        line_no = pos + 1
        fields = lines[pos].split()
        pos += 1
        require(len(fields) == 2, f"{path}:{line_no}: malformed raw record header")
        name = fields[0].upper()
        require(name not in records, f"{path}:{line_no}: duplicate {name}")
        try:
            count = int(fields[1])
        except ValueError as exc:
            raise ValidationError(f"{path}:{line_no}: bad length for {name}") from exc
        require(count > 0, f"{path}:{line_no}: nonpositive {name} length")
        values: list[float] = []
        while len(values) < count and pos < len(lines):
            for token in lines[pos].split():
                try:
                    value = float(token.replace("D", "E").replace("d", "e"))
                except ValueError as exc:
                    raise ValidationError(f"{path}:{pos + 1}: invalid {name} number") from exc
                require(np.isfinite(value), f"{path}:{pos + 1}: nonfinite {name}")
                values.append(value)
            pos += 1
        require(len(values) == count, f"{path}: truncated {name}")
        records[name] = np.asarray(values, dtype=np.float64)
    for key in ("DRY_LAYER_MASS_KG_M2", "DP_HPA", "CF", "GRAVITY", "P_HPA"):
        require(key in records, f"{path}: missing required {key}")
    require(records["DRY_LAYER_MASS_KG_M2"].shape == (nl,),
            f"{path}: native dry mass length differs from header nl={nl}")
    return phase, i, j, nl, records


def read_input_sections(path: Path) -> tuple[str, int, int, dict[str, np.ndarray]]:
    """Read V1-V5 input sections as Fortran-order two-dimensional arrays."""
    lines = path.read_text(encoding="ascii").splitlines()
    require(len(lines) >= 2 and lines[0].strip().startswith("RRTMGP_REPLAY_V"),
            f"{path}: unsupported replay input")
    header = lines[1].split()
    require(len(header) == 6, f"{path}: malformed replay header")
    phase = header[0].upper()
    try:
        nc, nl = int(header[1]), int(header[2])
    except ValueError as exc:
        raise ValidationError(f"{path}: invalid replay dimensions") from exc
    require(phase in {"LW", "SW"} and nc > 0 and nl > 0,
            f"{path}: invalid replay phase/dimensions")
    rec: dict[str, np.ndarray] = {}
    pos = 2
    while pos < len(lines):
        if not lines[pos].strip():
            pos += 1
            continue
        line_no = pos + 1
        fields = lines[pos].split()
        pos += 1
        require(len(fields) == 3, f"{path}:{line_no}: malformed section header")
        name = fields[0].upper()
        require(name not in rec, f"{path}:{line_no}: duplicate section {name}")
        try:
            nrow, ncol = int(fields[1]), int(fields[2])
        except ValueError as exc:
            raise ValidationError(f"{path}:{line_no}: invalid {name} dimensions") from exc
        require(nrow > 0 and ncol > 0, f"{path}:{line_no}: invalid {name} extent")
        count = nrow * ncol
        values: list[float] = []
        while len(values) < count and pos < len(lines):
            for token in lines[pos].split():
                try:
                    value = float(token.replace("D", "E").replace("d", "e"))
                except ValueError as exc:
                    raise ValidationError(f"{path}:{pos + 1}: invalid {name} number") from exc
                require(np.isfinite(value), f"{path}:{pos + 1}: nonfinite {name}")
                values.append(value)
            pos += 1
        require(len(values) == count, f"{path}: truncated {name}")
        rec[name] = np.asarray(values, dtype=np.float64).reshape((nrow, ncol), order="F")
    return phase, nc, nl, rec


def _time_string(ds: netCDF4.Dataset, index: int) -> str | None:
    if "Times" not in ds.variables:
        return None
    values = ds.variables["Times"][index]
    return b"".join(np.asarray(values).reshape(-1).tolist()).decode("ascii").strip()


def _column(ds: netCDF4.Dataset, name: str, i: int, j: int,
            time_index: int | None) -> np.ndarray:
    require(name in ds.variables, f"NetCDF source missing {name}")
    var = ds.variables[name]
    dims = list(var.dimensions)
    slices: list[Any] = []
    for dim in dims:
        lower = dim.lower()
        if lower == "time":
            require(time_index is not None, f"{name}: time index required")
            slices.append(time_index)
        elif lower in {"west_east", "west_east_stag"}:
            require(i < var.shape[len(slices)], f"{name}: i={i+1} out of bounds")
            slices.append(i)
        elif lower in {"south_north", "south_north_stag"}:
            require(j < var.shape[len(slices)], f"{name}: j={j+1} out of bounds")
            slices.append(j)
        else:
            slices.append(slice(None))
    data = np.asarray(var[tuple(slices)])
    return np.asarray(data, dtype=np.float64).reshape(-1)


def _fixed_real32_tolerance(expected: np.ndarray) -> np.ndarray:
    """Eight REAL32 eps relative, plus two minimum subnormals for underflow."""
    expected = np.asarray(expected, dtype=np.float64)
    return 8.0 * FLOAT32_EPS * np.abs(expected) + 2.0 * FLOAT32_TINY_SUBNORMAL


def assert_real32_close(actual: np.ndarray, expected: np.ndarray, label: str) -> float:
    actual = np.asarray(actual, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    require(actual.shape == expected.shape, f"{label}: shape {actual.shape} != {expected.shape}")
    require(np.isfinite(actual).all() and np.isfinite(expected).all(), f"{label}: nonfinite")
    delta = np.abs(actual - expected)
    tol = _fixed_real32_tolerance(expected)
    if np.any(delta > tol):
        k = int(np.argmax(delta - tol))
        raise ValidationError(f"{label}: layer {k+1} differs by {delta[k]:.9g}; "
                              f"REAL32 tolerance {tol[k]:.9g}; actual={actual[k]:.9g}, "
                              f"expected={expected[k]:.9g}")
    return float(delta.max(initial=0.0))


def _raw_exact(raw: np.ndarray, source: np.ndarray, label: str) -> None:
    raw = np.asarray(raw, dtype=np.float64)
    source = np.asarray(source, dtype=np.float64)
    require(raw.shape == source.shape, f"{label}: raw/source shape mismatch")
    require(np.array_equal(raw, source), f"{label}: capture does not exactly match source state")


def _self_tests() -> dict[str, bool]:
    expected_mass = np.asarray([100.0, 200.0], dtype=np.float64)
    observed_mass = expected_mass.copy()
    assert_real32_close(observed_mass, expected_mass, "self-test mass")
    bad_mass = observed_mass.copy()
    bad_mass[0] += 0.1
    try:
        assert_real32_close(bad_mass, expected_mass, "corrupted mass")
    except ValidationError:
        mass_rejected = True
    else:
        raise ValidationError("self-test failed to reject corrupted native mass")
    source = np.asarray([0.001, 0.002], dtype=np.float64)
    _raw_exact(source.copy(), source, "self-test source q")
    bad_source = source.copy()
    bad_source[1] = np.nextafter(bad_source[1], np.inf)
    try:
        _raw_exact(bad_source, source, "mismatched source q")
    except ValidationError:
        source_rejected = True
    else:
        raise ValidationError("self-test failed to reject mismatched source q")
    return {"corrupted_native_mass_rejected": mass_rejected,
            "mismatched_source_q_rejected": source_rejected}


def _validate_capture(raw_path: Path, input_path: Path, wrfinput: Path,
                      history: Path | None, time_index: int) -> dict[str, Any]:
    phase, raw_i, raw_j, nl, raw = read_raw(raw_path)
    input_phase, ncol, input_nl, sections = read_input_sections(input_path)
    require(phase == input_phase, f"{raw_path}: phase differs from sibling input")
    require(ncol == 1 and input_nl >= nl, f"{input_path}: expected one column covering raw layers")
    require(input_nl > nl, f"{input_path}: fixture has no above-top extension layers to validate")
    require("CF" in sections, f"{input_path}: no CF section")
    cf = sections["CF"][0, :nl]
    require(np.isfinite(cf).all() and np.all((cf >= 0.) & (cf <= 1.)),
            f"{input_path}: CF outside [0,1]")
    require(raw["DRY_LAYER_MASS_KG_M2"].shape == (nl,), "captured mass dimensions do not equal raw native layers")
    require(np.isfinite(raw["DRY_LAYER_MASS_KG_M2"]).all() and
            np.all(raw["DRY_LAYER_MASS_KG_M2"] > 0.), "captured native dry mass must be positive finite kg/m2")
    require(raw["DP_HPA"].shape == raw["CF"].shape == (nl,), "pressure/CF dimensions do not match native layers")
    _raw_exact(raw["CF"], cf, "raw CF versus sibling physical input CF")
    require(np.all(raw["DP_HPA"] > 0.), "pressure thickness must be positive")
    require(raw["GRAVITY"].size == 1 and raw["GRAVITY"][0] > 0., "invalid gravity")
    g = float(raw["GRAVITY"][0])
    require(abs(g - G_M_S2) <= _fixed_real32_tolerance(np.asarray([G_M_S2]))[0],
            f"unexpected gravity {g}; expected WRF G={G_M_S2}")

    i, j = raw_i - 1, raw_j - 1
    source_path = history if history is not None else wrfinput
    ds = netCDF4.Dataset(source_path)
    ti = time_index if "Time" in ds.dimensions else None
    timestamp = _time_string(ds, time_index) if ti is not None else None
    require(ti is None or 0 <= time_index < len(ds.dimensions["Time"]), "history time index out of range")
    source_q: dict[str, np.ndarray] = {}
    for raw_name, var_name in MASS_VARIABLES.items():
        q = _column(ds, var_name, i, j, ti)
        require(q.shape == (nl,), f"{var_name}: source layer count {q.size} != raw nl={nl}")
        raw_q = raw.get(raw_name)
        require(raw_q is not None and raw_q.shape == (nl,), f"capture missing {raw_name}")
        source_q[raw_name] = q
        _raw_exact(raw_q, q, f"{raw_name} versus {var_name}")

    mu = _column(ds, "MU", i, j, ti)
    mub = _column(ds, "MUB", i, j, ti)
    dnw = _column(ds, "DNW", i, j, ti)
    c1h = _column(ds, "C1H", i, j, ti)
    c2h = _column(ds, "C2H", i, j, ti)
    require(mu.size == mub.size == 1, "MU/MUB must be 2-D column pressure fields")
    require(dnw.size == c1h.size == c2h.size == nl, "DNW/C1H/C2H must span physical mass layers")
    require(np.all(dnw < 0.), "expected bottom-to-top WRF eta ordering with DNW<0")
    native_mass64 = -dnw * (c1h * (mu[0] + mub[0]) + c2h) / g
    require(np.isfinite(native_mass64).all() and np.all(native_mass64 > 0.),
            "coordinate-derived native dry layer mass is not positive finite")
    captured_mass = raw["DRY_LAYER_MASS_KG_M2"]
    native_mass32 = np.asarray(native_mass64, dtype=np.float32).astype(np.float64)
    dry_error = assert_real32_close(captured_mass, native_mass32,
                                    "DRY_LAYER_MASS_KG_M2 vs independent MU/MUB/DNW/C1H/C2H")

    # If both files are supplied, prove selected history record is the same
    # initial coordinate and q state as wrfinput before using it for the capture.
    if history is not None:
        src = netCDF4.Dataset(wrfinput)
        try:
            for name in (*MASS_VARIABLES.values(), "MU", "MUB", "DNW", "C1H", "C2H"):
                hval = _column(ds, name, i, j, ti)
                ival = _column(src, name, i, j, 0 if "Time" in src.dimensions else None)
                _raw_exact(hval, ival, f"history/time-index vs wrfinput {name}")
        finally:
            src.close()

    # Every supplied q is a dry-air mass mixing ratio; use the native dry
    # layer mass and the wrapper's explicit radiation-local negative clipping.
    negative_limits = raw.get("NEGATIVE_Q_LIMITS")
    require(negative_limits is not None and negative_limits.shape == (6,),
            "capture must include six NEGATIVE_Q_LIMITS")
    path_stats: dict[str, Any] = {}
    for phase_name, (qname, section_name) in PHASES.items():
        q = raw.get(qname)
        clipped = raw.get(f"NUMERIC_CLIPPED_{qname}")
        correction = raw.get(f"NEGATIVE_GRID_CORRECTION_{phase_name}")
        grid = raw.get(f"{phase_name}_GRID")
        rad = raw.get(f"{phase_name}_RADIATION")
        omitted = raw.get(f"{phase_name}_OMITTED")
        for label, array in ((qname, q), (f"NUMERIC_CLIPPED_{qname}", clipped),
                             (f"NEGATIVE_GRID_CORRECTION_{phase_name}", correction),
                             (f"{phase_name}_GRID", grid), (f"{phase_name}_RADIATION", rad),
                             (f"{phase_name}_OMITTED", omitted)):
            require(array is not None and array.shape == (nl,), f"capture missing/malformed {label}")
        q = np.asarray(q)
        clipped_expected = np.minimum(q, 0.0)
        assert_real32_close(clipped, clipped_expected, f"{phase_name} clipped negative q")
        if np.any(q < 0.):
            limit_index = {"LWP": 0, "IWP": 1, "RWP": 2, "SWP": 3, "GWP": 4, "HWP": 5}[phase_name]
            require(np.all((-q[q < 0.]) < negative_limits[limit_index]),
                    f"{phase_name}: negative q at/above the strict clipping limit")
        q_nonnegative = np.maximum(q, 0.0)
        # After independently checking the capture against coordinate state,
        # use the actual passed REAL32 layer mass for the path reconstruction.
        expected_grid = q_nonnegative * captured_mass * 1000.0
        grid_err = assert_real32_close(grid, expected_grid, f"{phase_name} grid path from native dry mass")
        expected_correction = -clipped_expected * captured_mass * 1000.0
        corr_err = assert_real32_close(correction, expected_correction,
                                       f"{phase_name} accepted-negative correction from native dry mass")
        expected_rad = np.zeros(nl, dtype=np.float64)
        wet = cf > 0.
        expected_rad[wet] = expected_grid[wet] / cf[wet]
        if phase_name in {"GWP", "HWP"}:
            expected_rad[:] = 0.0  # GWP is omitted; HWP is unsupported and must remain zero.
        rad_err = assert_real32_close(rad, expected_rad, f"{phase_name} in-cloud radiation path")
        expected_omitted = np.where(~wet, expected_grid, 0.0)
        if phase_name == "GWP":
            expected_omitted = expected_grid.copy()  # Deliberately unmapped from radiation.
        omitted_err = assert_real32_close(omitted, expected_omitted,
                                          f"{phase_name} omitted grid path / CF contract")
        if section_name in sections:
            require(sections[section_name].shape == (ncol, input_nl),
                    f"sibling input {section_name} has wrong dimensions")
            input_path_values = sections[section_name][0, :nl]
            assert_real32_close(input_path_values, expected_rad,
                                 f"sibling input {section_name} native in-cloud path")
            extension = sections[section_name][0, nl:]
            require(np.all(extension == 0.),
                    f"{section_name}: above-top optical extension paths are not all zero")
        elif phase_name in {"LWP", "IWP", "RWP", "SWP"}:
            raise ValidationError(f"sibling input missing optical path {section_name}")
        path_stats[phase_name] = {
            "max_grid_abs_error_g_m2": grid_err,
            "max_negative_correction_abs_error_g_m2": corr_err,
            "max_radiation_path_abs_error_g_m2": rad_err,
            "max_omitted_path_abs_error_g_m2": omitted_err,
            "negative_q_count": int(np.count_nonzero(q < 0.0)),
            "grid_path_sum_g_m2": float(np.sum(grid)),
            "negative_correction_sum_g_m2": float(np.sum(correction)),
            "in_cloud_cf_count": int(np.count_nonzero(wet)),
            "clear_cf_condensate_count": int(np.count_nonzero((~wet) & (grid > 0.0))),
        }

    # DP_HPA/g is the moisture-loaded hydrostatic pressure mass. It is reported
    # separately from exact dry mass and checked with a fixed interface REAL32
    # cancellation bound based on mass-level pressure, not mistaken for path mass.
    pressure_mass = raw["DP_HPA"] * 100.0 / g
    qtot = np.sum(np.stack([source_q[n] for n in MASS_VARIABLES]), axis=0, dtype=np.float64)
    moisture_loaded_mass = native_mass64 * (1.0 + qtot)
    pressure_residual = pressure_mass - moisture_loaded_mass
    require("P_HPA" in raw and raw["P_HPA"].shape == (nl,), "P_HPA layer pressure missing/malformed")
    pressure_ulp_pa = np.abs(np.spacing(np.asarray(raw["P_HPA"], dtype=np.float32))).astype(np.float64)
    dp_ulp_pa = np.abs(np.spacing(np.asarray(raw["DP_HPA"], dtype=np.float32))).astype(np.float64)
    pressure_tolerance = (4.0 * pressure_ulp_pa + 2.0 * dp_ulp_pa) * 100.0 / g
    require(np.all(np.abs(pressure_residual) <= pressure_tolerance),
            "DP_HPA pressure mass does not close against moisture-loaded native mass within "
            "fixed REAL32 interface-subtraction precision bound")
    require(np.all(pressure_mass >= native_mass64),
            "pressure mass unexpectedly below native dry mass for nonnegative SCM moisture")

    ds.close()
    return {
        "phase": phase, "raw_i": raw_i, "raw_j": raw_j, "native_layers": nl,
        "timestamp": timestamp,
        "timestamp_basis": "selected history Times record; raw capture itself has no timestamp" if history else
                           "wrfinput source fingerprint only; no history timestamp supplied",
        "history_time_index": time_index if history else None,
        "native_mass_kg_m2": {
            "min": float(native_mass64.min()), "max": float(native_mass64.max()),
            "column_sum": float(native_mass64.sum()),
            "captured_vs_independent_max_abs_error": dry_error,
            "fixed_tolerance": "8*float32_epsilon*abs(expected)+2*minimum_float32_subnormals",
        },
        "pressure_loaded_mass_check": {
            "formula": "DP_HPA*100/g versus native dry mass*(1+sum of all seven UDM moist species)",
            "qtot_max_kg_kg": float(qtot.max()),
            "dry_only_pressure_mass_column_delta_kg_m2": float(np.sum(pressure_mass-native_mass64)),
            "moisture_loaded_residual_max_abs_kg_m2": float(np.max(np.abs(pressure_residual))),
            "moisture_loaded_residual_max_relative": float(np.max(np.abs(pressure_residual)/moisture_loaded_mass)),
            "fixed_tolerance_max_kg_m2": float(np.max(pressure_tolerance)),
            "precision_note": "REAL32 interface subtraction/serialization scale; pressure mass is not the UDM dry-mass denominator",
        },
        "paths": path_stats,
        "above_top_extension": {
            "checked_input_sections": [x for x in ("LWP", "IWP", "RWP", "SWP") if x in sections],
            "extension_layers": input_nl - nl,
            "all_checked_extension_values_zero": True,
        },
        "source_profiles_exact": True,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture_dir", type=Path, help="directory containing lw/sw.raw and sibling .input files")
    parser.add_argument("wrfinput", type=Path, help="same-run wrfinput_d01")
    parser.add_argument("--history", type=Path, help="same-run history file containing the matched initial state")
    parser.add_argument("--time-index", type=int, default=0, help="history time record, default 0")
    parser.add_argument("--executable", type=Path, help="WRF executable used for the captured run (for provenance)")
    parser.add_argument("--output", type=Path, required=True, help="JSON receipt path")
    parser.add_argument("--self-test-only", action="store_true", help="run rejection checks without case files")
    args = parser.parse_args()
    try:
        self_tests = _self_tests()
        if args.self_test_only:
            print(json.dumps({"self_tests": self_tests}, indent=2))
            return 0
        require(args.capture_dir.is_dir(), f"not a capture directory: {args.capture_dir}")
        require(args.wrfinput.is_file(), f"missing wrfinput: {args.wrfinput}")
        if args.history is not None:
            require(args.history.is_file(), f"missing history: {args.history}")
        if args.executable is not None:
            require(args.executable.is_file(), f"missing executable: {args.executable}")
        results = []
        for phase in ("lw", "sw"):
            raw_path = args.capture_dir / f"{phase}.raw"
            input_path = args.capture_dir / f"{phase}.input"
            if not raw_path.exists() and not input_path.exists():
                continue
            require(raw_path.is_file() and input_path.is_file(),
                    f"{phase}: expected paired .raw and .input capture")
            result = _validate_capture(raw_path, input_path, args.wrfinput,
                                       args.history, args.time_index)
            result.update({
                "raw_path": str(raw_path), "raw_sha256": digest(raw_path),
                "input_path": str(input_path), "input_sha256": digest(input_path),
            })
            results.append(result)
        require(bool(results), f"no paired lw/sw captures in {args.capture_dir}")
        receipt = {
            "status": "PASS", "validator": "test_udm_native_mass.py",
            "wrfinput": str(args.wrfinput), "wrfinput_sha256": digest(args.wrfinput),
            "history": str(args.history) if args.history else None,
            "history_sha256": digest(args.history) if args.history else None,
            "executable": str(args.executable) if args.executable else None,
            "executable_sha256": digest(args.executable) if args.executable else None,
            "self_tests": self_tests,
            "mass_definition": "-DNW*(C1H*(MU+MUB)+C2H)/g; kg dry air m-2; DNW<0",
            "mixing_ratio_basis": "kg hydrometeor per kg dry air; Registry udmscheme mp_physics=27 qv,qc,qr,qi,qs,qg,qh",
            "real32_path_tolerance": "8*eps32*abs(expected)+2*float32_min_subnormal",
            "captures": results,
        }
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": "PASS", "output": str(args.output),
                          "capture_count": len(results), "self_tests": self_tests}, indent=2))
        return 0
    except (OSError, ValidationError, ValueError, IndexError, KeyError) as exc:
        print(f"UDM native-mass validation failed: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
