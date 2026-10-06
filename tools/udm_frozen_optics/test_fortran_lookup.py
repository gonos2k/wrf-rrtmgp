#!/usr/bin/env python3
"""Cross-language equivalence tests for the standalone Fortran optical lookup.

This checks implementation parity with the separately callable Python lookup,
not direct-Mie interpolation accuracy or WRF radiation validation.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

import numpy as np
from netCDF4 import Dataset

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import generate
import lookup

SPECIES = {1: ("graupel", 500.0), 2: ("hail", 912.0)}
PATHS_G_M2 = np.array([0.0, 1e-12, 1e-8, 0.25, 1.0, 50.0, 100.0])
RTOL = 5e-12
ATOL = 1e-24


def udm_query_lambdas(table: lookup.FrozenTable) -> list[float]:
    """Generate lambdas from fixed q/rho cases and source UDM constants."""
    values = []
    rho_micro = 0.8
    target = np.unique(np.concatenate((
        table.axes["lambda"],
        np.sqrt(table.axes["lambda"][:-1] * table.axes["lambda"][1:]),
    )))
    for species in ("graupel", "hail"):
        n0, rho_bulk = {"graupel": (4e6, 500.0), "hail": (4e4, 912.0)}[species]
        q = [0.0, 1e-15, 1e-9, 1.0001e-9]
        q.extend(math.pi * rho_bulk * n0 / (rho_micro * lam**4) for lam in target)
        lambdas = lookup.reconstructed_udm_slope(np.asarray(q), np.full(len(q), rho_micro), species)
        # The inverse q fixture can round an endpoint by a few ulps (for
        # example 300 m-1 as 299.99999999999966). Keep these endpoint cases
        # on the exact published table boundary; do not test extrapolation.
        values.extend(float(x) for x in np.clip(
            lambdas, table.axes["lambda"][0], table.axes["lambda"][-1]))
    return values


def query_axes(table: lookup.FrozenTable) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    lambda_axis = table.axes["lambda"]
    lambda_points = np.unique(np.concatenate((
        lambda_axis,
        np.sqrt(lambda_axis[:-1] * lambda_axis[1:]),
        np.asarray(udm_query_lambdas(table)),
    )))
    temperature_axis = table.axes["temperature"]
    temperature_points = np.unique(np.concatenate((
        temperature_axis,
        0.5 * (temperature_axis[:-1] + temperature_axis[1:]),
    )))
    return lambda_points, temperature_points, PATHS_G_M2


def pack_fortran(values: np.ndarray, nc: int, nl: int) -> np.ndarray:
    values = np.asarray(values, dtype=np.float64).reshape(-1)
    if values.size > nc * nl:
        raise ValueError("query count exceeds Fortran matrix shape")
    # Fortran ravel must be a writable view; a C-order matrix would return a
    # temporary copy and leave the emitted values uninitialized.
    result = np.empty((nc, nl), dtype=np.float64, order="F")
    result.ravel(order="F")[:values.size] = values
    if values.size < nc * nl:
        result.ravel(order="F")[values.size:] = values[0]
    return result


def write_query(path: Path, lam_sw: np.ndarray, path_sw: np.ndarray,
                lam_lw: np.ndarray, temp_lw: np.ndarray, path_lw: np.ndarray) -> tuple[int, int]:
    nc = 2
    nl = int(math.ceil(max(len(lam_sw), len(lam_lw)) / nc))
    arrays = [
        pack_fortran(lam_sw, nc, nl), pack_fortran(path_sw, nc, nl),
        pack_fortran(lam_lw, nc, nl), pack_fortran(temp_lw, nc, nl), pack_fortran(path_lw, nc, nl),
    ]
    # All five arrays have the same shape. Python writes Fortran column-major
    # order so an ordinary list-directed array read reconstructs identical cells.
    with path.open("w") as f:
        f.write(f"{nc} {nl}\n")
        for array in arrays:
            if array.shape != (nc, nl):
                raise AssertionError(f"query shape {array.shape} != {(nc, nl)}")
            f.write(" ".join(f"{x:.17e}" for x in array.ravel(order="F")) + "\n")
    return nc, nl


def run(executable: Path, table_file: Path, query_file: Path, output_csv: Path,
        alternate_table: Path | None = None) -> subprocess.CompletedProcess:
    command = [str(executable), str(table_file), str(query_file), str(output_csv)]
    if alternate_table is not None:
        command.append(str(alternate_table))
    return subprocess.run(command,
                          text=True, capture_output=True)


def make_invalid_table(source: Path, destination: Path, mutation: str) -> None:
    """Create a one-defect NetCDF copy for fill/sentinel loader checks."""
    target_name = "sw_extinction_times_density"
    fill = np.float64(9.969209968386869e36)
    with Dataset(source, "r") as src, Dataset(destination, "w", format="NETCDF4") as dst:
        for name, dim in src.dimensions.items():
            dst.createDimension(name, None if dim.isunlimited() else len(dim))
        for name in src.ncattrs():
            dst.setncattr(name, src.getncattr(name))
        for name, var in src.variables.items():
            fill_value = None
            if "_FillValue" in var.ncattrs():
                fill_value = var.getncattr("_FillValue")
            if name == target_name and mutation == "fill_attribute":
                fill_value = fill
            kwargs = {} if fill_value is None else {"fill_value": fill_value}
            out = dst.createVariable(name, var.datatype, var.dimensions, **kwargs)
            for attr in var.ncattrs():
                if attr == "_FillValue":
                    continue
                out.setncattr(attr, var.getncattr(attr))
            values = var[:]
            if name == target_name and mutation == "sentinel_data":
                values = np.asarray(values).copy()
                values.flat[0] = fill
            out[:] = values
            if name == target_name and mutation == "missing_value":
                out.setncattr("missing_value", fill)


def compare_output(table: lookup.FrozenTable, output_csv: Path,
                   lambda_sw: np.ndarray, paths_sw: np.ndarray,
                   lambda_lw: np.ndarray, temperature_lw: np.ndarray,
                   paths_lw: np.ndarray, nc: int, nl: int) -> dict:
    data = {}
    record_count = 0
    with output_csv.open(newline="") as f:
        for row in csv.DictReader(f):
            record_count += 1
            phase = row["phase"].strip()
            species = int(row["species"])
            col, layer, band = (int(row[k]) for k in ("column", "layer", "band"))
            index = (layer - 1) * nc + (col - 1)
            key = (phase, species, index, band)
            if key in data:
                raise AssertionError(f"duplicate Fortran output row {key}")
            data[key] = row
    expected_rows = 2 * nc * nl * (14 + 16)
    if record_count != expected_rows:
        raise AssertionError(f"Fortran wrote {record_count} rows; expected {expected_rows}")

    max_abs = {k: 0.0 for k in ("tau_ext", "tau_scat", "tau_scat_g", "tau_abs")}
    max_rel = {k: 0.0 for k in max_abs}
    compared = {k: 0 for k in max_abs}

    for species, (_, rho_bulk) in SPECIES.items():
        for idx, (lam, path) in enumerate(zip(lambda_sw, paths_sw)):
            moments = table.moments("SW", np.asarray([lam]))
            factor = path * 1e-3 / rho_bulk
            expected = {
                "tau_ext": moments["extinction"][0] * factor,
                "tau_scat": moments["scattering"][0] * factor,
                "tau_scat_g": moments["scatter_times_g"][0] * factor,
                "tau_abs": moments["absorption"][0] * factor,
            }
            for band in range(1, 15):
                row = data[("SW", species, idx, band)]
                assert np.isclose(float(row["lambda_m_inv"]), lam, rtol=0, atol=1e-13 * max(1, lam))
                assert np.isclose(float(row["path_g_m2"]), path, rtol=0, atol=1e-20)
                assert float(row["temperature_k"]) == -1.0
                for name, vector in expected.items():
                    # SW API deliberately returns extinction/scattering and
                    # scattering*g only. Its derived absorption is a closure
                    # residual and is checked below, not as an independent
                    # Fortran/Python lookup output.
                    if name == "tau_abs":
                        continue
                    got = float(row[name])
                    want = float(vector[band - 1])
                    np.testing.assert_allclose(got, want, rtol=RTOL, atol=ATOL,
                                               err_msg=f"SW species={species} query={idx} band={band} {name}")
                    max_abs[name] = max(max_abs[name], abs(got - want))
                    max_rel[name] = max(max_rel[name], abs(got - want) / max(abs(want), 1e-300))
                    compared[name] += 1
                assert float(row["tau_ext"]) + ATOL >= float(row["tau_scat"])
                assert abs(float(row["tau_scat_g"])) <= float(row["tau_scat"]) + ATOL

        for idx, (lam, temp, path) in enumerate(zip(lambda_lw, temperature_lw, paths_lw)):
            moments = table.moments("LW", np.asarray([lam]), np.asarray([temp]))
            want = moments["absorption"][0] * (path * 1e-3 / rho_bulk)
            for band in range(1, 17):
                row = data[("LW", species, idx, band)]
                assert np.isclose(float(row["lambda_m_inv"]), lam, rtol=0, atol=1e-13 * max(1, lam))
                assert np.isclose(float(row["temperature_k"]), temp, rtol=0, atol=1e-13 * max(1, temp))
                assert np.isclose(float(row["path_g_m2"]), path, rtol=0, atol=1e-20)
                got = float(row["tau_abs"])
                expected = float(want[band - 1])
                np.testing.assert_allclose(got, expected, rtol=RTOL, atol=ATOL,
                                           err_msg=f"LW species={species} query={idx} band={band}")
                max_abs["tau_abs"] = max(max_abs["tau_abs"], abs(got - expected))
                max_rel["tau_abs"] = max(max_rel["tau_abs"], abs(got - expected) / max(abs(expected), 1e-300))
                compared["tau_abs"] += 1
                assert got >= -ATOL

    # At every positive path, absorption is the extinction-minus-scattering
    # remainder in SW; zero-path queries remain exactly transparent.
    closure_abs = 0.0
    for (phase, species, idx, band), row in data.items():
        if phase != "SW" or idx >= len(lambda_sw):
            continue
        ext, sca, absorb = (float(row[k]) for k in ("tau_ext", "tau_scat", "tau_abs"))
        closure_abs = max(closure_abs, abs((ext - sca) - absorb))
        if paths_sw[idx] == 0:
            assert ext == sca == absorb == 0.0
        else:
            assert ext >= sca >= 0.0 and absorb >= -ATOL
    return {"max_abs_diff": max_abs, "max_relative_diff": max_rel,
            "compared_values": compared, "max_sw_absorption_closure_residual": closure_abs,
            "units": {"moments": "kappa*rho_bulk [m-1]", "path": "g m-2",
                      "tau": "dimensionless; (kappa*rho_bulk)*path[g m-2]*1e-3/rho_bulk[kg m-3]"}}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--executable", type=Path, required=True)
    p.add_argument("--generation", type=Path, required=True,
                   help="complete generated table directory with result.json")
    p.add_argument("--workdir", type=Path,
                   help="new, empty directory for query/table/output fixtures")
    p.add_argument("--output", type=Path, help="new path for the JSON result")
    p.add_argument("--ctest-output-root", type=Path,
                   help="create a unique run directory beneath this root; preserves prior runs")
    args = p.parse_args()
    explicit_paths = args.workdir is not None and args.output is not None
    if (args.workdir is None) != (args.output is None):
        p.error("--workdir and --output must be provided together")
    if explicit_paths == (args.ctest_output_root is not None):
        p.error("provide either --workdir with --output, or --ctest-output-root")
    if args.ctest_output_root is not None:
        args.ctest_output_root.mkdir(parents=True, exist_ok=True)
        run_root = Path(tempfile.mkdtemp(prefix="run-", dir=args.ctest_output_root))
        args.workdir = run_root / "work"
        args.output = run_root / "summary.json"
    if args.workdir.exists() or args.output.exists():
        p.error("Use new work and output paths; test evidence is preserved")
    args.workdir.mkdir(parents=True)
    table = lookup.FrozenTable(args.generation)
    table_file = args.generation / "frozen-ice-psd-moments.nc"
    lambda_sw, _, paths = query_axes(table)
    lambda_lw, temperatures, _ = query_axes(table)
    # Exercise all size knots and geometric midpoints crossed with every LW
    # temperature knot and arithmetic midpoint.
    lambda_lw = np.repeat(lambda_lw, len(temperatures))
    temperature_lw = np.tile(temperatures, len(lambda_sw))
    paths_sw = np.resize(paths, len(lambda_sw))
    paths_lw = np.resize(paths, len(lambda_lw))
    nc, nl = write_query(args.workdir / "queries.txt", lambda_sw, paths_sw,
                         lambda_lw, temperature_lw, paths_lw)
    bad_table = args.workdir / "bad-table.nc"
    shutil.copyfile(table_file, bad_table)
    with Dataset(bad_table, "a") as ncfile:
        ncfile.setncattr("status", "INVALID_TEST_ARTIFACT")
    output_csv = args.workdir / "fortran.csv"
    proc = run(args.executable.resolve(), table_file.resolve(),
               (args.workdir / "queries.txt").resolve(), output_csv.resolve(), bad_table.resolve())
    if proc.returncode != 0 or "FROZEN_LOOKUP_FORTRAN_PASS" not in proc.stdout:
        raise RuntimeError(f"Fortran lookup test failed ({proc.returncode}):\n{proc.stdout}\n{proc.stderr}")
    compared = compare_output(table, output_csv, lambda_sw, paths_sw,
                              lambda_lw, temperature_lw, paths_lw, nc, nl)

    bad_proc = run(args.executable.resolve(), bad_table,
                   (args.workdir / "queries.txt").resolve(), (args.workdir / "bad.csv").resolve())
    if bad_proc.returncode == 0:
        raise AssertionError("Fortran initializer accepted a table with wrong status metadata")
    missing_proc = run(args.executable.resolve(), args.workdir / "absent.nc",
                       (args.workdir / "queries.txt").resolve(), (args.workdir / "missing.csv").resolve())
    if missing_proc.returncode == 0:
        raise AssertionError("Fortran initializer accepted a missing table")

    for mutation in ("fill_attribute", "missing_value", "sentinel_data"):
        invalid = args.workdir / f"invalid-{mutation}.nc"
        make_invalid_table(table_file, invalid, mutation)
        invalid_proc = run(args.executable.resolve(), invalid,
                           (args.workdir / "queries.txt").resolve(),
                           (args.workdir / f"{mutation}.csv").resolve())
        if invalid_proc.returncode == 0:
            raise AssertionError(f"Fortran initializer accepted {mutation} table")

    result = {
        "status": "PASS_FORTRAN_PYTHON_LOOKUP_EQUIVALENCE",
        "scope": "Fortran/Python implementation parity and input rejection only; not interpolation accuracy or physical validation",
        "generation_receipt_sha256": table.receipt_sha256,
        "table_sha256": table.table_sha256,
        "lookup_algorithm": lookup.ALGORITHM,
        "query_axes": {"lambda_m_inv": lambda_sw.tolist(), "temperature_k": temperatures.tolist(),
                       "path_g_m2_pattern": paths.tolist(), "species": ["graupel", "hail"]},
        "shape": {"ncol": nc, "nlay": nl, "sw_bands": 14, "lw_bands": 16},
        "accuracy_tolerance": {"rtol": RTOL, "atol": ATOL,
                               "sw_tau_abs": "not an independent comparison; checked as ext-minus-scattering closure"},
        "fortran_stdout": proc.stdout.strip(),
        "expected_rejections": ["nonfinite lambda", "out-of-range lambda", "zero lambda",
                                "negative/nonfinite path", "invalid species", "shape mismatch",
                                "nonfinite/out-of-range temperature", "wrong table status", "missing table",
                                "_FillValue metadata", "missing_value metadata", "fill-value moment data"],
        **compared,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps({"status": result["status"], "compared_values": compared["compared_values"],
                      "max_abs_diff": compared["max_abs_diff"]}))


if __name__ == "__main__":
    main()
