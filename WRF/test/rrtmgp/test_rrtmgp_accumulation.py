#!/usr/bin/env python3
"""Check cumulative surface fluxes against the full SCM history time series.

Use this on an SCM run with history every model step and radiation called less
often. The history fluxes are held between radiation calls; the accumulators
must still advance by one DT times the held flux on every model step.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

import netCDF4
import numpy as np


def namelist_number(text: str, key: str) -> float:
    match = re.search(rf"^\s*{re.escape(key)}\s*=\s*([-+0-9.eEdD]+)", text,
                      flags=re.IGNORECASE | re.MULTILINE)
    if not match:
        raise RuntimeError(f"namelist.input has no {key}")
    return float(match.group(1).replace("D", "E").replace("d", "e"))


def decode_times(raw: np.ndarray) -> list[str]:
    return [b"".join(row).decode("ascii").strip() for row in raw]


def recurrence_error(accumulated: np.ndarray, instantaneous: np.ndarray,
                     dt: float, name: str) -> float:
    increment = np.diff(accumulated, axis=0)
    expected = instantaneous[1:] * dt
    if not np.allclose(increment, expected, rtol=2.e-5, atol=2.e-3):
        error = np.abs(increment - expected)
        where = np.unravel_index(np.argmax(error), error.shape)
        raise RuntimeError(
            f"{name} recurrence fails: max abs error {float(error[where]):.6g} "
            f"at increment/grid index {where}; observed={float(increment[where]):.8g}, "
            f"expected={float(expected[where]):.8g}"
        )
    return float(np.max(np.abs(increment - expected)))


def replace_namelist_value(text: str, key: str, value: str) -> str:
    updated, count = re.subn(rf"(^\s*{re.escape(key)}\s*=\s*).+?([,\s]*(?:!.*)?$)",
                             rf"\g<1>{value}\2", text, count=1,
                             flags=re.IGNORECASE | re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"could not update {key} in namelist.input")
    return updated


def prepare_and_run_hold_case(seed: Path, case: Path, duration: int,
                              radt_minutes: float) -> Path:
    """Create a small SCM hold-flux fixture and run the existing WRF binary."""
    seed, case = seed.resolve(), case.resolve()
    if not seed.is_dir():
        raise RuntimeError(f"seed SCM directory does not exist: {seed}")
    if case.exists():
        raise RuntimeError(f"hold-case output directory already exists: {case}")
    if duration < 40 or duration % 10:
        raise RuntimeError("duration must be at least 40 seconds and a multiple of 10 seconds")
    if radt_minutes <= 0 or not (radt_minutes * 60 > 10):
        raise RuntimeError("radt must be greater than the 10-second model timestep")
    if not np.isclose(radt_minutes * 60 / 10,
                      round(radt_minutes * 60 / 10)):
        raise RuntimeError("radt must be an integer multiple of the 10-second timestep")

    excluded = {"wrf.log", "namelist.output", "capture"}
    case.mkdir(parents=True)
    for path in seed.iterdir():
        if (path.name in excluded or path.name.startswith(("wrfout_", "wrfrst_", "rsl."))
                or path.name.startswith("namelist.input.backup")):
            continue
        target = case / path.name
        if path.is_symlink():
            target.symlink_to(path.readlink())
        elif path.is_dir():
            shutil.copytree(path, target, symlinks=True)
        else:
            shutil.copy2(path, target)

    namelist_path = case / "namelist.input"
    namelist = namelist_path.read_text()
    dt = namelist_number(namelist, "time_step")
    if dt != 10 or namelist_number(namelist, "history_interval_s") != 10:
        raise RuntimeError("hold fixture requires the seed's DT=10s and history_interval_s=10s")
    start_fields = {
        key: int(namelist_number(namelist, f"start_{key}"))
        for key in ("year", "month", "day", "hour", "minute", "second")
    }
    start = datetime(start_fields["year"], start_fields["month"], start_fields["day"],
                     start_fields["hour"], start_fields["minute"], start_fields["second"])
    end = start + timedelta(seconds=duration)
    run_minutes, run_seconds = divmod(duration, 60)
    namelist = replace_namelist_value(namelist, "run_days", "0")
    namelist = replace_namelist_value(namelist, "run_hours", "0")
    namelist = replace_namelist_value(namelist, "run_minutes", str(run_minutes))
    namelist = replace_namelist_value(namelist, "run_seconds", str(run_seconds))
    for key, value in (("year", end.year), ("month", end.month), ("day", end.day),
                       ("hour", end.hour), ("minute", end.minute), ("second", end.second)):
        namelist = replace_namelist_value(namelist, f"end_{key}", f"{value:02d}")
    namelist = replace_namelist_value(namelist, "radt", f"{radt_minutes:g}")
    namelist_path.write_text(namelist)

    executable = case / "wrf.exe"
    if not executable.exists():
        raise RuntimeError(f"WRF executable is not available through {executable}")
    env = os.environ.copy()
    # Preserve configured runtime library paths; do not inject workspace paths.
    for name in tuple(env):
        if name.startswith("WRF_RRTMGP"):
            env.pop(name)
    env["OMP_NUM_THREADS"] = "1"
    with (case / "wrf.log").open("w") as log:
        completed = subprocess.run([str(executable)], cwd=case, env=env, stdout=log,
                                   stderr=subprocess.STDOUT, check=False)
    if completed.returncode:
        raise RuntimeError(f"WRF hold-case run failed ({completed.returncode}); inspect {case / 'wrf.log'}")
    return case


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("case", type=Path, nargs="?",
                        help="completed WRF SCM run directory to validate")
    parser.add_argument("--run-hold-case", action="store_true",
                        help="make and run a DT=10s SCM case with radiation less frequent than history")
    parser.add_argument("--seed-dir", type=Path,
                        default=Path("build/udm-runtime-contracts-scm/control/ra37-call1"),
                        help="completed SCM case supplying wrfinput and linked run data")
    parser.add_argument("--case-dir", type=Path,
                        help="new output directory for --run-hold-case (must not already exist)")
    parser.add_argument("--duration-seconds", type=int, default=120)
    parser.add_argument("--radt-minutes", type=float, default=0.5)
    args = parser.parse_args()
    if args.run_hold_case:
        if args.case is not None or args.case_dir is None:
            parser.error("--run-hold-case takes --case-dir and no positional case")
        case = prepare_and_run_hold_case(args.seed_dir, args.case_dir,
                                         args.duration_seconds, args.radt_minutes)
    elif args.case is not None and args.case_dir is None:
        case = args.case.resolve()
    else:
        parser.error("provide a case directory, or use --run-hold-case --case-dir")
    namelist = (case / "namelist.input").read_text()
    dt = namelist_number(namelist, "time_step")
    radt_minutes = namelist_number(namelist, "radt")
    if dt <= 0 or radt_minutes <= 0:
        raise RuntimeError("case must use a positive timestep and explicit positive radt")
    radt_seconds = radt_minutes * 60.0
    if radt_seconds <= dt or not np.isclose(radt_seconds / dt,
                                             round(radt_seconds / dt)):
        raise RuntimeError("case must have radt as an integer multiple of DT, greater than DT")
    if "SUCCESS COMPLETE WRF" not in (case / "wrf.log").read_text(errors="replace"):
        raise RuntimeError(f"{case}: WRF success marker missing")
    paths = sorted(case.glob("wrfout_d01_*"))
    if len(paths) != 1:
        raise RuntimeError(f"{case}: expected one complete history file, found {len(paths)}")

    results: dict[str, object] = {}
    with netCDF4.Dataset(paths[0]) as ds:
        if not np.isclose(float(ds.DT), dt):
            raise RuntimeError(f"history DT={ds.DT} disagrees with namelist DT={dt}")
        times = decode_times(ds["Times"][:])
        if len(times) < 4:
            raise RuntimeError("need at least four history records to cover a held-flux interval")
        time_seconds = np.asarray([
            datetime.strptime(value, "%Y-%m-%d_%H:%M:%S").timestamp()
            for value in times
        ], dtype=np.float64)
        spacing = np.diff(time_seconds)
        if not np.allclose(spacing, dt, rtol=0, atol=1.e-6):
            raise RuntimeError(f"history records are not every DT={dt}s: {spacing.tolist()}")
        for accumulator, flux in (("ACSWDNB", "SWDNB"), ("ACLWDNB", "LWDNB")):
            if accumulator not in ds.variables or flux not in ds.variables:
                raise RuntimeError(f"history is missing {accumulator} or {flux}")
            accumulated_raw = ds[accumulator][:]
            instantaneous_raw = ds[flux][:]
            if (np.ma.getmaskarray(accumulated_raw).any()
                    or np.ma.getmaskarray(instantaneous_raw).any()):
                raise RuntimeError(f"{accumulator}/{flux} contains masked values")
            accumulated = np.asarray(accumulated_raw, dtype=np.float64)
            instantaneous = np.asarray(instantaneous_raw, dtype=np.float64)
            if (not np.isfinite(accumulated).all()
                    or not np.isfinite(instantaneous).all()):
                raise RuntimeError(f"{accumulator}/{flux} contains masked or non-finite values")
            # Differences cancel any constant startup offset in ACC[0]. The
            # driver adds the current flux times DT at every model step, so
            # include the first recorded interval in the recurrence check.
            max_error = recurrence_error(accumulated, instantaneous, dt, accumulator)
            if accumulator == "ACSWDNB":
                # Negative control: corrupt only the first post-startup sample.
                # The validator must catch this first interval, which guards
                # against accidentally skipping it in future edits.
                corrupted = accumulated.copy()
                corrupted[1] += max(100.0, dt * 10.0)
                try:
                    recurrence_error(corrupted, instantaneous, dt,
                                     f"{accumulator} negative control")
                except RuntimeError:
                    pass
                else:
                    raise RuntimeError("negative control failed to detect a corrupted first interval")
            increment = np.diff(accumulated, axis=0)
            expected = instantaneous[1:] * dt
            adjacent = np.isclose(instantaneous[:-1], instantaneous[1:],
                                  rtol=2.e-6, atol=2.e-4)
            held_pairs = adjacent.reshape((adjacent.shape[0], -1)).all(axis=1)
            changed_pairs = (~adjacent).reshape((adjacent.shape[0], -1)).any(axis=1)
            results[accumulator] = {
                "flux": flux,
                "compared_model_step_increments": int(increment.shape[0]),
                "max_abs_recurrence_error": max_error,
                "adjacent_held_flux_samples": int(np.count_nonzero(held_pairs)),
                "adjacent_updated_flux_samples": int(np.count_nonzero(changed_pairs)),
            }
        if any(int(entry["adjacent_held_flux_samples"]) < 1
               or int(entry["adjacent_updated_flux_samples"]) < 1
               for entry in results.values()):
            raise RuntimeError("history must show both held flux records and flux updates")
    print(json.dumps({
        "status": "PASS",
        "case": str(case),
        "history_file": str(paths[0]),
        "time_records": len(times),
        "model_timestep_seconds": dt,
        "radiation_call_period_seconds": radt_seconds,
        "history_samples_between_radiation_calls": int(round(radt_seconds / dt)) - 1,
        "accumulation_checks": results,
        "recurrence": "ACC[n] - ACC[n-1] = flux[n] * DT for every recorded interval",
        "negative_control": "PASS (corrupted first accumulation sample was rejected)",
    }, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
