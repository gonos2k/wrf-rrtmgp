#!/usr/bin/env python3
"""Test the independent RRTMGP replay SW band-optics override contract."""
from __future__ import annotations

import argparse
import os
import subprocess
import tempfile
from pathlib import Path

import netCDF4
import numpy as np

from compare_column_replay import compare, read_result


def write_input(path: Path) -> None:
    sections = [
        ("SOLAR", 1, 1, [1361.0]),
        ("PLAY", 1, 1, [500.0]),
        ("PLEV", 1, 2, [1000.0, 0.0]),
        ("TLAY", 1, 1, [260.0]),
        ("TLEV", 1, 2, [280.0, 220.0]),
        ("TSFC", 1, 1, [280.0]),
        ("H2O", 1, 1, [0.005]),
        ("CO2", 1, 1, [0.0004]),
        ("O3", 1, 1, [1.0e-8]),
        ("N2O", 1, 1, [3.0e-7]),
        ("CH4", 1, 1, [1.8e-6]),
        ("O2", 1, 1, [0.209]),
        ("EMIS", 1, 1, [0.98]),
        ("AVDIR", 1, 1, [0.2]),
        ("AVDIF", 1, 1, [0.2]),
        ("ANDIR", 1, 1, [0.2]),
        ("ANDIF", 1, 1, [0.2]),
        ("MU0", 1, 1, [0.5]),
        ("CF", 1, 1, [0.0]),
        ("LWP", 1, 1, [0.0]),
        ("IWP", 1, 1, [0.0]),
        ("SWP", 1, 1, [0.0]),
        ("REL", 1, 1, [10.0]),
        ("REI", 1, 1, [30.0]),
        ("RES", 1, 1, [30.0]),
    ]
    lines = ["RRTMGP_REPLAY_V1", "SW 1 1 0 1 1"]
    for name, nrow, ncol, values in sections:
        lines.append(f"{name} {nrow} {ncol}")
        lines.extend(f"{value:.16E}" for value in values)
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def write_override(path: Path, bands: np.ndarray, tau: np.ndarray,
                   ssa: np.ndarray, asym: np.ndarray) -> None:
    nc, nl, nb = tau.shape
    lines = ["WRF_SW_OPTICS_OVERRIDE_V1", f"{nc} {nl} {nb}", f"BAND_LIMITS 2 {nb}"]
    lines.extend(f"{value:.16E}" for value in bands.ravel(order="F"))
    for name, array in (("TAU", tau), ("SSA", ssa), ("ASYM", asym)):
        lines.append(f"{name} {nc} {nl} {nb}")
        lines.extend(f"{value:.16E}" for value in array.ravel(order="F"))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def run(exe: Path, data: Path, input_path: Path, output: Path,
        override: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [str(exe), str(data), str(input_path), str(output)]
    if override is not None:
        # Fourth argument is the default SW delta policy; fifth is override path.
        command.extend(["1", str(override)])
    return subprocess.run(command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, check=False, env=os.environ.copy())


def expect_failure(exe: Path, data: Path, input_path: Path, root: Path,
                   label: str, bands: np.ndarray, tau: np.ndarray, ssa: np.ndarray,
                   asym: np.ndarray, diagnostic: str, *, magic: str | None = None,
                   header_shape: tuple[int, int, int] | None = None) -> None:
    override = root / f"{label}.optics"
    write_override(override, bands, tau, ssa, asym)
    lines = override.read_text(encoding="ascii").splitlines()
    if magic is not None:
        lines[0] = magic
    if header_shape is not None:
        lines[1] = " ".join(str(value) for value in header_shape)
    override.write_text("\n".join(lines) + "\n", encoding="ascii")
    result = run(exe, data, input_path, root / f"{label}.result", override)
    if result.returncode == 0 or diagnostic not in result.stdout:
        raise RuntimeError(f"{label}: expected failure containing {diagnostic!r}; got rc={result.returncode}: {result.stdout[-900:]}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("reference_executable", type=Path)
    args = parser.parse_args()
    data, exe = args.data_directory.resolve(), args.reference_executable.resolve()
    if not data.is_dir() or not exe.is_file():
        parser.error("data directory and reference executable must exist")

    with tempfile.TemporaryDirectory(prefix="rrtmgp-sw-override-") as temp:
        root = Path(temp)
        input_path = root / "column.input"
        write_input(input_path)
        baseline_path = root / "baseline.result"
        baseline_run = run(exe, data, input_path, baseline_path)
        if baseline_run.returncode:
            raise RuntimeError(f"baseline reference failed: {baseline_run.stdout[-1000:]}")
        baseline = read_result(baseline_path)
        nb = baseline["sections"]["PREPARED_TAU"].shape[2]
        with netCDF4.Dataset(data / "rrtmgp-gas-sw-g112.nc") as nc:
            bands = np.asarray(nc.variables["bnd_limits_wavenumber"][:], dtype=np.float64).T
        if bands.shape != (2, nb):
            raise RuntimeError(f"gas band limits {bands.shape} differ from prepared optics bands {nb}")
        tau = baseline["sections"]["PREPARED_TAU"].copy()
        ssa = baseline["sections"]["PREPARED_SSA"].copy()
        asym = baseline["sections"]["PREPARED_G"].copy()

        identity_path = root / "identity.optics"
        write_override(identity_path, bands, tau, ssa, asym)
        identity_output = root / "identity.result"
        identity_run = run(exe, data, input_path, identity_output, identity_path)
        if identity_run.returncode:
            raise RuntimeError(f"identity override failed: {identity_run.stdout[-1000:]}")
        identity_report = compare(baseline, read_result(identity_output))
        if not identity_report.get("passed"):
            raise RuntimeError(f"identity override changed results: {identity_report.get('failed_sections')}")

        wrong_bands = bands.copy()
        wrong_bands[1, 0] += 1.0
        expect_failure(exe, data, input_path, root, "wrong-edge", wrong_bands, tau, ssa, asym,
                       "SW optics override bands differ")
        bad_tau = tau.copy(); bad_tau[0, 0, 0] = np.nan
        expect_failure(exe, data, input_path, root, "nonfinite", bands, bad_tau, ssa, asym,
                       "TAU must be finite")
        bad_ssa = ssa.copy(); bad_ssa[0, 0, 0] = 1.01
        expect_failure(exe, data, input_path, root, "ssa-range", bands, tau, bad_ssa, asym,
                       "SSA must be finite and in [0,1]")
        bad_asym = asym.copy(); bad_asym[0, 0, 0] = -1.01
        expect_failure(exe, data, input_path, root, "asym-range", bands, tau, ssa, bad_asym,
                       "ASYM must be finite and in [-1,1]")
        expect_failure(exe, data, input_path, root, "bad-magic", bands, tau, ssa, asym,
                       "invalid SW optics override magic", magic="UNKNOWN_OVERRIDE_V1")
        expect_failure(exe, data, input_path, root, "bad-shape", bands, tau, ssa, asym,
                       "dimensions do not match", header_shape=(2, 1, nb))

    print("PASS: synthetic bandwise SW optics override identity and negative-input checks")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
