#!/usr/bin/env python3
"""Cross-language regression for expanded Planck-temperature table coverage.

Checks interpolation implementation parity and preservation of old knots; it
does not validate the Mie model or establish forecast accuracy.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
import tempfile

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import lookup
import test_fortran_lookup as helper

TEMPERATURES_K = np.asarray([150.0, 179.996, 180.0, 233.0, 330.0], dtype=np.float64)
POSITIVE_PATH_G_M2 = 6.054224e-4
RTOL = helper.RTOL
ATOL = helper.ATOL


def require(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def compare_old_knots(new: lookup.FrozenTable, old: lookup.FrozenTable) -> dict:
    new_lambda = new.axes["lambda"]
    old_lambda = old.axes["lambda"]
    new_temp = new.axes["temperature"]
    old_temp = old.axes["temperature"]
    require(all(float(x) in set(new_lambda.tolist()) for x in old_lambda),
            "Expanded generation does not retain every old lambda knot exactly")
    require(all(float(x) in set(new_temp.tolist()) for x in old_temp),
            "Expanded generation does not retain every old temperature knot exactly")

    li = [int(np.flatnonzero(new_lambda == x)[0]) for x in old_lambda]
    ti = [int(np.flatnonzero(new_temp == x)[0]) for x in old_temp]
    checks = 0
    for moment in ("extinction", "scattering", "scatter_times_g", "absorption"):
        name = "sw_" + moment + "_times_density"
        require(np.array_equal(new.arrays[name][li, :], old.arrays[name]),
                f"Old SW values changed for {moment}")
        checks += int(old.arrays[name].size)
        name = "lw_" + moment + "_times_density"
        require(np.array_equal(new.arrays[name][np.ix_(li, ti, range(new.arrays[name].shape[2]))],
                               old.arrays[name]), f"Old LW knot values changed for {moment}")
        checks += int(old.arrays[name].size)
    return {"old_lambda_knots": old_lambda.tolist(), "old_temperature_knots_K": old_temp.tolist(),
            "exact_old_moment_values_checked": checks, "SW_exact": True, "LW_old_knots_exact": True}


def query_fortran(executable: Path, table_path: Path, run_dir: Path,
                  lambdas_sw: np.ndarray, paths_sw: np.ndarray,
                  lambdas_lw: np.ndarray, temps_lw: np.ndarray,
                  paths_lw: np.ndarray, stem: str) -> tuple[dict, Path]:
    query = run_dir / f"{stem}-query.txt"
    output = run_dir / f"{stem}-fortran.csv"
    nc, nl = helper.write_query(query, lambdas_sw, paths_sw, lambdas_lw, temps_lw, paths_lw)
    proc = helper.run(executable.resolve(), table_path.resolve(), query.resolve(), output.resolve())
    if proc.returncode != 0 or "FROZEN_LOOKUP_FORTRAN_PASS" not in proc.stdout:
        raise AssertionError(f"Fortran {stem} lookup failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    table = lookup.FrozenTable(table_path.parent)
    metrics = helper.compare_output(table, output, lambdas_sw, paths_sw, lambdas_lw,
                                    temps_lw, paths_lw, nc, nl)
    return {"stdout": proc.stdout.strip(), "returncode": proc.returncode,
            "query_shape": {"ncol": nc, "nlay": nl}, **metrics}, output


def assert_lw_range_rejected(executable: Path, table_path: Path, lam: float,
                             temp: float, run_dir: Path, label: str) -> None:
    query = run_dir / f"{label}-query.txt"
    output = run_dir / f"{label}-fortran.csv"
    # One real query cell; helper packs/pads the remaining matrix cell.
    helper.write_query(query, np.asarray([lam]), np.asarray([POSITIVE_PATH_G_M2]),
                       np.asarray([lam]), np.asarray([temp]), np.asarray([POSITIVE_PATH_G_M2]))
    proc = helper.run(executable.resolve(), table_path.resolve(), query.resolve(), output.resolve())
    require(proc.returncode != 0, f"Fortran accepted out-of-range temperature in {label}")
    require("FROZEN_LOOKUP_LW_FAILED" in proc.stdout,
            f"Fortran rejection lacked the expected LW diagnostic in {label}: {proc.stdout!r}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--generation", type=Path, required=True,
                        help="expanded-temperature generation directory")
    parser.add_argument("--old-generation", type=Path, required=True,
                        help="previous temperature-coverage generation directory")
    parser.add_argument("--executable", type=Path, required=True,
                        help="existing test_rrtmgp_frozen_lookup executable")
    parser.add_argument("--ctest-output-root", type=Path, required=True,
                        help="parent for a unique, isolated test run directory")
    args = parser.parse_args()
    require(args.executable.is_file(), f"Fortran test executable missing: {args.executable}")
    require((args.generation / "result.json").is_file(), "Expanded generation receipt is missing")
    require((args.old_generation / "result.json").is_file(), "Old generation receipt is missing")
    args.ctest_output_root.mkdir(parents=True, exist_ok=True)
    run_dir = Path(tempfile.mkdtemp(prefix="run-", dir=args.ctest_output_root))

    new = lookup.FrozenTable(args.generation)
    old = lookup.FrozenTable(args.old_generation)
    lambdas = old.axes["lambda"].copy()
    require(lambdas.size == 9, f"Expected nine legacy lambda knots, found {lambdas.size}")
    old_knot_check = compare_old_knots(new, old)

    # Duplicate every physical query with a zero-path counterpart. This checks
    # transparency while exercising the complete positive-path query too.
    sw_lambdas = np.repeat(lambdas, 2)
    sw_paths = np.tile(np.asarray([POSITIVE_PATH_G_M2, 0.0]), lambdas.size)
    lw_lambdas = np.repeat(np.repeat(lambdas, TEMPERATURES_K.size), 2)
    lw_temps = np.repeat(np.tile(TEMPERATURES_K, lambdas.size), 2)
    lw_paths = np.tile(np.asarray([POSITIVE_PATH_G_M2, 0.0]), lambdas.size * TEMPERATURES_K.size)
    new_lookup, output_csv = query_fortran(args.executable, args.generation / "frozen-ice-psd-moments.nc",
                                           run_dir, sw_lambdas, sw_paths, lw_lambdas,
                                           lw_temps, lw_paths, "expanded")
    with output_csv.open(newline="") as stream:
        for row in csv.DictReader(stream):
            if row["phase"] == "LW" and float(row["path_g_m2"]) == 0.0:
                require(float(row["tau_abs"]) == 0.0,
                        "LW zero-path query was not exactly transparent")

    # Both temperature endpoints and the formerly unsupported 179.996 K value
    # must be accepted by the expanded table and Fortran implementation.
    require(np.array_equal(new.axes["temperature"][[0, -1]], np.asarray([150.0, 330.0])),
            "Expanded table temperature endpoints are not exactly 150 and 330 K")
    old_reject_python = False
    try:
        old.moments("LW", np.asarray([lambdas[0]]), np.asarray([179.996]))
    except ValueError as exc:
        old_reject_python = "outside table range" in str(exc)
    require(old_reject_python, "Old Python table unexpectedly accepts 179.996 K")
    for outside in (149.999, 330.001):
        try:
            new.moments("LW", np.asarray([lambdas[0]]), np.asarray([outside]))
        except ValueError as exc:
            require("outside table range" in str(exc), "Unexpected Python rejection cause")
        else:
            raise AssertionError(f"Expanded Python table accepts {outside} K")
    assert_lw_range_rejected(args.executable, args.old_generation / "frozen-ice-psd-moments.nc",
                             float(lambdas[0]), 179.996, run_dir, "old-179.996K")
    assert_lw_range_rejected(args.executable, args.generation / "frozen-ice-psd-moments.nc",
                             float(lambdas[0]), 149.999, run_dir, "expanded-below-150K")
    assert_lw_range_rejected(args.executable, args.generation / "frozen-ice-psd-moments.nc",
                             float(lambdas[0]), 330.001, run_dir, "expanded-above-330K")

    result = {
        "status": "PASS_PLANCK_TEMPERATURE_COVERAGE_PARITY",
        "scope": "Fortran/Python interpolation parity, exact preservation at old knots, and temperature range contracts; not a Mie accuracy or forecast validation",
        "expanded_generation": {"path": str(args.generation.resolve()),
                                "receipt_sha256": new.receipt_sha256,
                                "table_sha256": new.table_sha256},
        "old_generation": {"path": str(args.old_generation.resolve()),
                           "receipt_sha256": old.receipt_sha256,
                           "table_sha256": old.table_sha256},
        "fortran_executable": {"path": str(args.executable.resolve()),
                               "sha256": sha256(args.executable)},
        "expanded_temperature_queries_K": TEMPERATURES_K.tolist(),
        "lambda_queries_m_inv": lambdas.tolist(),
        "positive_path_g_m2": POSITIVE_PATH_G_M2,
        "zero_path_counterparts": True,
        "old_coverage_rejected_179_996_K": {"python": old_reject_python, "fortran": True},
        "expanded_range_rejections_K": [149.999, 330.001],
        "old_knot_preservation": old_knot_check,
        "parity_tolerances": {"rtol": RTOL, "atol": ATOL},
        "expanded_fortran_python": new_lookup,
        "fortran_csv_sha256": sha256(output_csv),
        "run_directory": str(run_dir.resolve()),
    }
    result_path = run_dir / "result.json"
    result_path.write_text(json.dumps(result, indent=2, allow_nan=False) + "\n")
    print(json.dumps({"status": result["status"], "run_directory": str(run_dir)}))


if __name__ == "__main__":
    main()
