#!/usr/bin/env python3
"""Verify standalone coefficient loaders fail through the common callback."""
from __future__ import annotations

import argparse
import subprocess
import tempfile
from pathlib import Path

import netCDF4


GAS_LW = "rrtmgp-gas-lw-g128.nc"
GAS_SW = "rrtmgp-gas-sw-g112.nc"
CLOUD_LW = "rrtmgp-clouds-lw-bnd.nc"
CLOUD_SW = "rrtmgp-clouds-sw-bnd.nc"


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


def empty_netcdf(path: Path) -> None:
    with netCDF4.Dataset(path, "w", format="NETCDF4"):
        pass


def prepare_case(root: Path, source: Path, omitted: str | None, corrupt: str | None) -> Path:
    data = root / "data"
    data.mkdir()
    for filename in (GAS_LW, GAS_SW, CLOUD_LW, CLOUD_SW):
        target = data / filename
        if filename == omitted:
            continue
        if filename == corrupt:
            empty_netcdf(target)
        else:
            target.symlink_to(source / filename)
    return data


def run_case(executable: Path, source: Path, input_path: Path,
             name: str, omitted: str | None, corrupt: str | None,
             diagnostic: str) -> None:
    with tempfile.TemporaryDirectory(prefix=f"rrtmgp-{name}-") as tmp:
        root = Path(tmp)
        data = prepare_case(root, source, omitted, corrupt)
        result = subprocess.run(
            [str(executable), str(data), str(input_path), str(root / "out.result")],
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False,
        )
        if result.returncode == 0:
            raise RuntimeError(f"{name}: loader unexpectedly succeeded")
        if diagnostic not in result.stdout:
            raise RuntimeError(f"{name}: expected {diagnostic!r} in failure output; got {result.stdout[-1200:]!r}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("data_directory", type=Path)
    parser.add_argument("reference_executable", type=Path)
    args = parser.parse_args()
    data, executable = args.data_directory.resolve(), args.reference_executable.resolve()
    for name, path in (("data directory", data), ("reference executable", executable)):
        if not path.exists():
            parser.error(f"{name} does not exist: {path}")
    with tempfile.TemporaryDirectory(prefix="rrtmgp-failure-input-") as tmp:
        input_path = Path(tmp) / "valid.input"
        write_input(input_path)
        run_case(executable, data, input_path, "missing-gas", GAS_LW, None,
                 "load_and_init(): can't open file")
        run_case(executable, data, input_path, "corrupt-gas", None, GAS_LW,
                 "read_char_vec: can't find variable gas_names")
        run_case(executable, data, input_path, "missing-cloud", CLOUD_LW, None,
                 "load_cld_lutcoeff(): can't open file")
        run_case(executable, data, input_path, "corrupt-cloud", None, CLOUD_LW,
                 "read_field: can't find variable bnd_limits_wavenumber")
    print("PASS: missing/corrupt gas and cloud coefficients reached the standalone fatal handler")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
