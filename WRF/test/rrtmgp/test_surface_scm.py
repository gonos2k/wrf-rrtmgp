#!/usr/bin/env python3
"""Run SCM surface-albedo cases and check the RRTMGP shortwave contract."""
from __future__ import annotations

import argparse
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

import netCDF4
import numpy as np


WRF_ROOT = Path(__file__).resolve().parents[2]
TEMPLATE = WRF_ROOT / "test/rrtmgp/namelist.scm37"
INPUT_DIR = WRF_ROOT / "test/em_scm_xy"
DATA_DIR = WRF_ROOT / "run"
REJECTION_MESSAGE = "RRTMGP37 requires swint_opt=0"
ALBEDOS = (0.0, 0.2, 0.99, 1.0)
TOL = dict(rtol=2.0e-5, atol=2.0e-3)


def fail(message: str) -> None:
    raise RuntimeError(message)


def make_namelist(swint_opt: int) -> str:
    text = TEMPLATE.read_text()
    start = text.index(" &physics")
    end = text.index(" /", start)
    block = text[start:end]
    block, count = re.subn(
        r"(?m)^\s*sf_surface_physics\s*=\s*[^,\n]+,",
        f" sf_surface_physics                  = 0,",
        block,
        count=1,
    )
    if count != 1:
        fail("namelist template lacks sf_surface_physics")
    if re.search(r"(?m)^\s*swint_opt\s*=", block):
        block, count = re.subn(
            r"(?m)^\s*swint_opt\s*=\s*[^,\n]+,",
            f" swint_opt                          = {swint_opt},",
            block,
            count=1,
        )
        if count != 1:
            fail("could not set swint_opt")
    else:
        block += f"\n swint_opt                          = {swint_opt},"
    # Preserve prescribed ALBBCK rather than replacing it from LANDUSE.TBL.
    block += "\n usemonalb                          = .true.,\n"
    return text[:start] + block + text[end:]


def prepare_case(case_dir: Path, swint_opt: int) -> None:
    case_dir.mkdir(parents=True)
    (case_dir / "namelist.input").write_text(make_namelist(swint_opt))
    shutil.copy2(WRF_ROOT / "test/rrtmgp/radiation_iofields.txt", case_dir)
    for name in ("input_sounding", "input_soil", "force_ideal.nc"):
        shutil.copy2(INPUT_DIR / name, case_dir / name)
    for source in DATA_DIR.iterdir():
        if source.is_file():
            target = case_dir / source.name
            if not target.exists():
                target.symlink_to(source.resolve())


def run_logged(executable: Path, case_dir: Path, logfile: str) -> subprocess.CompletedProcess[str]:
    with (case_dir / logfile).open("w") as stream:
        return subprocess.run(
            [str(executable)], cwd=case_dir, stdout=stream, stderr=subprocess.STDOUT,
            text=True, check=False,
        )


def set_surface_albedo(wrfinput: Path, value: float) -> None:
    with netCDF4.Dataset(wrfinput, "r+") as ds:
        # ALBEDO is history-only in this Registry. WRF initializes it from ALBBCK.
        if "ALBBCK" not in ds.variables:
            fail(f"{wrfinput}: missing ALBBCK needed for the controlled albedo case")
        ds.variables["ALBBCK"][:] = value
        if "ALBEDO" in ds.variables:
            ds.variables["ALBEDO"][:] = value


def numeric(ds: netCDF4.Dataset, name: str, case: Path) -> np.ndarray:
    if name not in ds.variables:
        fail(f"{case}: history file is missing {name}")
    data = ds.variables[name][:]
    if np.ma.getmaskarray(data).any():
        fail(f"{case}: {name} contains masked values")
    values = np.asarray(data, dtype=np.float64)
    if not np.isfinite(values).all():
        fail(f"{case}: {name} contains non-finite values")
    return values


def check_day_case(case_dir: Path, albedo: float) -> dict:
    wrf_log = (case_dir / "wrf.log").read_text(errors="replace")
    if "SUCCESS COMPLETE WRF" not in wrf_log:
        fail(f"{case_dir}: WRF success marker missing")
    outputs = sorted(case_dir.glob("wrfout_d01_*"))
    if not outputs:
        fail(f"{case_dir}: WRF produced no history file")
    with netCDF4.Dataset(outputs[-1]) as ds:
        option_lw, option_sw = int(ds.RA_LW_PHYSICS), int(ds.RA_SW_PHYSICS)
        if (option_lw, option_sw) != (37, 37):
            fail(f"{case_dir}: expected radiation 37/37, got {option_lw}/{option_sw}")
        swdown = numeric(ds, "SWDOWN", case_dir)
        swdnb = numeric(ds, "SWDNB", case_dir)
        swddir = numeric(ds, "SWDDIR", case_dir)
        swddif = numeric(ds, "SWDDIF", case_dir)
        gsw = numeric(ds, "GSW", case_dir)
        swupb = numeric(ds, "SWUPB", case_dir)
        output_albedo = numeric(ds, "ALBEDO", case_dir)
        np.testing.assert_allclose(output_albedo, albedo, rtol=0.0, atol=1.0e-6,
                                   err_msg=f"{case_dir}: output ALBEDO changed")
        np.testing.assert_allclose(swdown, swdnb, **TOL,
                                   err_msg=f"{case_dir}: SWDOWN != SWDNB")
        np.testing.assert_allclose(swdown, swddir + swddif, **TOL,
                                   err_msg=f"{case_dir}: SWDOWN != SWDDIR + SWDDIF")
        np.testing.assert_allclose(gsw, swdnb - swupb, **TOL,
                                   err_msg=f"{case_dir}: GSW != SWDNB - SWUPB")
        if not np.any(swdown > 0.0):
            fail(f"{case_dir}: no daytime shortwave flux was calculated")
        return {
            "case": str(case_dir),
            "albedo": albedo,
            "radiation_options": [option_lw, option_sw],
            "history_file": str(outputs[-1]),
            "time_count": int(swdown.shape[0]),
            "checks": ["finite fields", "ALBEDO persistence", "SWDOWN=SWDNB",
                       "SWDOWN=SWDDIR+SWDDIF", "GSW=SWDNB-SWUPB"],
        }


def run_day_case(case_dir: Path, albedo: float, ideal_exe: Path, wrf_exe: Path) -> dict:
    prepare_case(case_dir, 0)
    ideal = run_logged(ideal_exe, case_dir, "ideal.log")
    wrfinput = case_dir / "wrfinput_d01"
    if ideal.returncode != 0 or not wrfinput.is_file():
        fail(f"{case_dir}: ideal.exe failed; inspect ideal.log")
    set_surface_albedo(wrfinput, albedo)
    wrf = run_logged(wrf_exe, case_dir, "wrf.log")
    if wrf.returncode != 0:
        fail(f"{case_dir}: wrf.exe returned {wrf.returncode}; inspect wrf.log")
    return check_day_case(case_dir, albedo)


def run_rejection_case(case_dir: Path, swint_opt: int, ideal_exe: Path,
                       wrf_exe: Path) -> dict:
    prepare_case(case_dir, swint_opt)
    ideal = run_logged(ideal_exe, case_dir, "ideal.log")
    ideal_log = (case_dir / "ideal.log").read_text(errors="replace")
    if REJECTION_MESSAGE in ideal_log:
        if "SUCCESS COMPLETE WRF" in ideal_log:
            fail(f"{case_dir}: ideal.exe logged rejection and success")
        return {
            "case": str(case_dir),
            "swint_opt": swint_opt,
            "rejected_during": "ideal.exe",
            "ideal_returncode": ideal.returncode,
            "checks": ["explicit RRTMGP swint_opt rejection in ideal.log"],
        }
    if ideal.returncode != 0 or not (case_dir / "wrfinput_d01").is_file():
        fail(f"{case_dir}: ideal.exe failed before swint_opt rejection check")
    wrf = run_logged(wrf_exe, case_dir, "wrf.log")
    wrf_log = (case_dir / "wrf.log").read_text(errors="replace")
    if REJECTION_MESSAGE not in wrf_log:
        fail(f"{case_dir}: expected explicit swint_opt={swint_opt} rejection missing")
    if "SUCCESS COMPLETE WRF" in wrf_log:
        fail(f"{case_dir}: unsupported swint_opt={swint_opt} completed successfully")
    return {
        "case": str(case_dir),
        "swint_opt": swint_opt,
        "wrf_returncode": wrf.returncode,
        "checks": ["explicit RRTMGP swint_opt rejection in wrf.log"],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("new_root_directory", type=Path,
                        help="new, nonexistent directory for all isolated SCM cases")
    args = parser.parse_args()
    root = args.new_root_directory.expanduser().resolve()
    if root.exists():
        parser.error(f"refusing existing case root: {root}")
    ideal_exe, wrf_exe = WRF_ROOT / "main/ideal.exe", WRF_ROOT / "main/wrf.exe"
    for executable in (ideal_exe, wrf_exe):
        if not executable.is_file() or not executable.stat().st_mode & 0o111:
            parser.error(f"missing executable {executable}; build em_scm_xy first")
    for needed in (TEMPLATE, INPUT_DIR / "input_sounding", INPUT_DIR / "input_soil",
                   INPUT_DIR / "force_ideal.nc", WRF_ROOT / "test/rrtmgp/radiation_iofields.txt"):
        if not needed.is_file():
            parser.error(f"missing SCM input {needed}")
    root.mkdir(parents=True)
    results = {"surface_cases": [], "swint_rejection_cases": []}
    for albedo in ALBEDOS:
        tag = f"alpha-{str(albedo).replace('.', 'p')}"
        results["surface_cases"].append(
            run_day_case(root / tag, albedo, ideal_exe, wrf_exe))
    for swint_opt in (1, 2):
        results["swint_rejection_cases"].append(
            run_rejection_case(root / f"reject-swint-{swint_opt}", swint_opt,
                               ideal_exe, wrf_exe))
    print(json.dumps(results, indent=2))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (RuntimeError, AssertionError, OSError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        sys.exit(1)
