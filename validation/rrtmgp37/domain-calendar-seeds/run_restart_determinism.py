#!/usr/bin/env python3
"""Run isolated 120-second SCM restart-equivalence probes.

The script writes only under --output-root.  It runs control and mixed PR15
wrfinput states both continuously and split at 60 s, then checks history at
matching timestamps plus the saved checkpoint using compare_restart.py.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime, timedelta
from pathlib import Path

import netCDF4
import numpy as np


HERE = Path(__file__).resolve().parent
SUCCESS = "SUCCESS COMPLETE WRF"


def discover_repo(start: Path = HERE) -> Path:
    for candidate in (start, *start.parents):
        if (candidate / "WRF/test/rrtmgp").is_dir() and (candidate / "WRF/main").is_dir():
            return candidate
    raise RuntimeError(f"cannot locate WRF checkout from {start}")


DEFAULT_REPO = discover_repo()
DEFAULT_BASE = DEFAULT_REPO / "build/udm-native-dry-mass-pr15/scm"


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def nc_payload_sha256(path: Path) -> str:
    """Hash numeric/state payload, excluding date-only fields used for retiming."""
    digest = hashlib.sha256()
    excluded = {"Times", "JULYR", "JULDAY", "GMT"}
    with netCDF4.Dataset(path) as ds:
        for name in sorted(ds.variables):
            if name in excluded:
                continue
            var = ds.variables[name]
            values = np.asarray(var[:])
            digest.update(name.encode("utf-8") + b"\0")
            digest.update(repr((var.dimensions, str(var.dtype), values.shape)).encode("ascii"))
            digest.update(values.tobytes(order="C"))
    return digest.hexdigest()


def replace(text: str, key: str, value: str, block: str) -> str:
    start = text.lower().find("&" + block.lower())
    if start < 0:
        raise RuntimeError(f"missing namelist block {block}")
    end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", text[start:])
    if end_match is None:
        raise RuntimeError(f"unterminated namelist block {block}")
    end = start + end_match.start()
    part = text[start:end]
    pattern = rf"(?im)^(\s*{re.escape(key)}\s*=\s*)[^,\n]+,"
    part, count = re.subn(pattern, rf"\g<1>{value},", part, count=1)
    if not count:
        part += f"\n {key} = {value},\n"
    return text[:start] + part + text[end:]


def nml_for(source: str, start: datetime, end: datetime, restart: bool) -> str:
    values = {
        "run_days": "0", "run_hours": "0", "run_minutes": "0",
        "run_seconds": str(int((end - start).total_seconds())),
        "start_year": f"{start.year:04d}", "start_month": f"{start.month:02d}",
        "start_day": f"{start.day:02d}", "start_hour": f"{start.hour:02d}",
        "start_minute": f"{start.minute:02d}", "start_second": f"{start.second:02d}",
        "end_year": f"{end.year:04d}", "end_month": f"{end.month:02d}",
        "end_day": f"{end.day:02d}", "end_hour": f"{end.hour:02d}",
        "end_minute": f"{end.minute:02d}", "end_second": f"{end.second:02d}",
        "restart": ".true." if restart else ".false.",
        "restart_interval": "1", "history_interval": "0",
        "history_interval_s": "10", "radt": "0.5",
    }
    for name in ("start_year", "start_month", "start_day", "start_hour", "start_minute", "start_second",
                 "end_year", "end_month", "end_day", "end_hour", "end_minute", "end_second",
                 "run_days", "run_hours", "run_minutes", "run_seconds", "restart", "restart_interval",
                 "history_interval", "history_interval_s"):
        source = replace(source, name, values[name], "time_control")
    for name in ("ra_lw_physics", "ra_sw_physics"):
        source = replace(source, name, "37", "physics")
    source = replace(source, "mp_physics", "27", "physics")
    source = replace(source, "use_mp_re", "1", "physics")
    source = replace(source, "radt", values["radt"], "physics")
    return source


def require_options(history_paths: list[Path], label: str) -> None:
    if not history_paths:
        raise RuntimeError(f"{label}: expected history output")
    for path in history_paths:
        with netCDF4.Dataset(path) as ds:
            options = (int(ds.getncattr("RA_LW_PHYSICS")), int(ds.getncattr("RA_SW_PHYSICS")))
            microphysics = int(ds.getncattr("MP_PHYSICS"))
        if options != (37, 37) or microphysics != 27:
            raise RuntimeError(f"{label}: {path} reports options RA={options}, MP={microphysics}; expected 37/37 and 27")


def time_text(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d_%H:%M:%S")


def prepare_case(case: Path, baseline: Path, wrf_run: Path, namelist: str) -> None:
    case.mkdir(parents=True, exist_ok=False)
    for filename in ("input_sounding", "input_soil", "force_ideal.nc", "radiation_iofields.txt"):
        source = (baseline / filename) if (baseline / filename).exists() else (wrf_run / filename)
        if source.exists():
            shutil.copy2(source, case / filename)
    for asset in wrf_run.iterdir():
        if asset.is_file() and asset.name not in {"wrf.exe", "ideal.exe", "namelist.input", "wrfinput_d01"}:
            target = case / asset.name
            if not target.exists():
                target.symlink_to(asset.resolve())
    shutil.copy2(baseline / "wrfinput_d01", case / "wrfinput_d01")
    (case / "namelist.input").write_text(namelist)


def retime_file(path: Path, start: datetime, original_start: datetime) -> dict:
    changed = {}
    delta = start - original_start
    with netCDF4.Dataset(path, "r+") as ds:
        if "Times" not in ds.variables:
            raise RuntimeError(f"{path} has no Times variable")
        times = ds.variables["Times"]
        rendered_times = []
        for row_index, row in enumerate(times[:]):
            old = b"".join(row).decode("ascii")
            old_dt = datetime.strptime(old, "%Y-%m-%d_%H:%M:%S")
            rendered = time_text(old_dt + delta)
            times[row_index, :] = np.frombuffer(rendered.encode("ascii"), dtype="S1")
            rendered_times.append(rendered)
        rendered = rendered_times[0]
        changed["Times"] = rendered_times
        for attr, value in (("START_DATE", rendered), ("SIMULATION_START_DATE", rendered)):
            if attr in ds.ncattrs():
                setattr(ds, attr, value)
                changed[attr] = value
        date_metadata = {"JULYR": start.year, "JULDAY": int(start.strftime("%j")),
                         "GMT": start.hour + start.minute / 60.0 + start.second / 3600.0}
        for name, value in date_metadata.items():
            if name in ds.variables:
                ds.variables[name][...] = value
                changed[name + "_variable"] = value
            if name in ds.ncattrs():
                setattr(ds, name, value)
                changed[name + "_attribute"] = value
    return changed


def run(exe: Path, case: Path, label: str, env: dict[str, str]) -> dict:
    before = sha256(exe.resolve())
    log = case / f"{label}.log"
    with log.open("w") as stream:
        proc = subprocess.run([str(exe.resolve())], cwd=case, env=env,
                              stdout=stream, stderr=subprocess.STDOUT, check=False)
    output = log.read_text(errors="replace")
    return {"returncode": proc.returncode, "log": str(log),
            "success_marker": SUCCESS in output,
            "binary": str(exe.resolve()), "binary_sha256_before": before,
            "binary_sha256_after": sha256(exe.resolve())}


def merge_history(paths: list[Path], output: Path) -> None:
    """Concatenate WRF history time records into a scratch comparison file."""
    if not paths:
        raise RuntimeError("no WRF history files found to merge")
    with netCDF4.Dataset(paths[0]) as first, netCDF4.Dataset(output, "w", format=first.file_format) as out:
        for name, dim in first.dimensions.items():
            out.createDimension(name, None if dim.isunlimited() else len(dim))
        for name in first.ncattrs():
            out.setncattr(name, first.getncattr(name))
        variables = {}
        for name, src in first.variables.items():
            dst = out.createVariable(name, src.datatype, src.dimensions,
                                     fill_value=src.getncattr("_FillValue") if "_FillValue" in src.ncattrs() else None)
            for attr in src.ncattrs():
                if attr != "_FillValue":
                    dst.setncattr(attr, src.getncattr(attr))
            variables[name] = dst
        seen_times: set[str] = set()
        offset = 0
        for path in paths:
            with netCDF4.Dataset(path) as ds:
                if set(ds.variables) != set(variables):
                    raise RuntimeError(f"history variable set mismatch in {path}")
                ntime = len(ds.dimensions["Time"])
                times = [b"".join(row).decode("ascii") for row in ds.variables["Times"][:]]
                indices = [i for i, value in enumerate(times) if value not in seen_times]
                seen_times.update(times)
                kept = len(indices)
                for name, src in ds.variables.items():
                    dst = variables[name]
                    if "Time" in src.dimensions:
                        axis = src.dimensions.index("Time")
                        values = np.take(src[:], indices, axis=axis)
                        sl = [slice(None)] * src.ndim
                        sl[axis] = slice(offset, offset + kept)
                        dst[tuple(sl)] = values
                    elif offset == 0:
                        dst[:] = src[:]
                offset += kept


def require_run(result: dict) -> None:
    if result["returncode"] or not result["success_marker"]:
        raise RuntimeError(f"WRF failed; inspect {result['log']}")
    if result["binary_sha256_before"] != result["binary_sha256_after"]:
        raise RuntimeError("WRF executable changed during an invocation")



UDM_CF_DIAGNOSTICS = ("UDM_CLDFRA", "UDM_CF_STEP", "UDM_CF_TOP")


def require_restart_diagnostics(checkpoint: Path, history: Path, physical_time: str) -> dict:
    """Check the actual restart boundary before merging duplicate history times.

    merge_history retains the pre-restart record at a duplicate timestamp. That
    record cannot demonstrate preservation in the restarted initial output.
    """
    compared = []
    with netCDF4.Dataset(checkpoint) as donor, netCDF4.Dataset(history) as restored:
        for ds, label in ((donor, "checkpoint"), (restored, "restarted history")):
            if "Times" not in ds.variables:
                raise RuntimeError(f"{label}: missing Times")
            time = b"".join(ds.variables["Times"][0]).decode("ascii")
            if time != physical_time:
                raise RuntimeError(f"{label}: first timestamp {time} != {physical_time}")
        for name in UDM_CF_DIAGNOSTICS:
            if name not in donor.variables or name not in restored.variables:
                raise RuntimeError(f"restart boundary: missing {name}")
            left, right = donor.variables[name], restored.variables[name]
            if left.dimensions != right.dimensions or left.dtype != right.dtype:
                raise RuntimeError(f"restart boundary: {name} dimensions/dtype differ")
            for raw in (True, False):
                left.set_auto_maskandscale(not raw)
                right.set_auto_maskandscale(not raw)
                x, y = left[0], right[0]
                if np.ma.getmaskarray(x).any() or np.ma.getmaskarray(y).any():
                    raise RuntimeError(f"restart boundary: {name} contains masked values")
                x, y = np.asarray(x), np.asarray(y)
                if not np.isfinite(x).all() or not np.isfinite(y).all():
                    raise RuntimeError(f"restart boundary: {name} contains nonfinite values")
                if x.shape != y.shape or x.dtype != y.dtype or x.tobytes() != y.tobytes():
                    raise RuntimeError(f"restart boundary: {name} differs ({'raw' if raw else 'decoded'})")
            compared.append(name)
    return {"status": "PASS", "physical_time": physical_time,
            "checkpoint": str(checkpoint), "checkpoint_sha256": sha256(checkpoint),
            "restarted_initial_history": str(history), "history_sha256": sha256(history),
            "fields": compared, "raw_and_decoded_exact": True}


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--repo", type=Path, default=DEFAULT_REPO)
    p.add_argument("--baseline-root", type=Path, default=None)
    p.add_argument("--output-root", type=Path, default=HERE / "run")
    p.add_argument("--cases", nargs="+", choices=("control", "mixed"), default=("control", "mixed"))
    p.add_argument("--calendar-boundary", action="store_true",
                   help="also run a control split crossing 1999-12-31 to 2000-01-01")
    args = p.parse_args()
    repo = args.repo.resolve()
    baseline_root = (args.baseline_root or (repo / "build/udm-native-dry-mass-pr15/scm")).resolve()
    wrf_root = repo / "WRF"
    wrf_run = wrf_root / "run"
    exe = wrf_root / "main/wrf.exe"
    comparator = repo / "validation/rrtmgp37/cpu-openmp/runtime/compare_restart.py"
    if not exe.is_file() or not comparator.is_file():
        raise RuntimeError(f"WRF executable or comparator missing: {exe}, {comparator}")
    outroot = args.output_root.resolve()
    if outroot.exists():
        raise RuntimeError(f"refusing to overwrite existing output root: {outroot}")
    outroot.mkdir(parents=True)
    env = os.environ.copy()
    for key in ("WRF_RRTMGP_CAPTURE_DIR", "WRF_RRTMGP_CAPTURE_CALL", "WRF_RRTMGP_AUDIT_DIR",
                "WRF_RRTMGP_CAPTURE_ALL", "WRF_RRTMGP_AUDIT_SEEDS", "WRF_RRTMGP_HYDRO_DIAG_DIR"):
        env.pop(key, None)
    env["OMP_NUM_THREADS"] = "1"
    baseline_start = datetime(1999, 10, 22, 19, 0, 0)
    all_reports = []
    invocations = []
    for label in list(args.cases) + (["calendar"] if args.calendar_boundary else []):
        source_case = baseline_root / ("control" if label == "calendar" else label) / "ra4"
        start = datetime(1999, 12, 31, 23, 59, 0) if label == "calendar" else baseline_start
        stop = start + timedelta(seconds=120)
        checkpoint = start + timedelta(seconds=60)
        case_root = outroot / label
        if case_root.exists():
            raise RuntimeError(f"refusing to overwrite existing case directory: {case_root}")
        case_root.mkdir(parents=True)
        base_nml = (source_case / "namelist.input").read_text()
        initial = source_case / "wrfinput_d01"

        continuous = case_root / "continuous"
        prepare_case(continuous, source_case, wrf_run, nml_for(base_nml, start, stop, False))
        retime = label == "calendar"
        if retime:
            retime_file(continuous / "wrfinput_d01", start, baseline_start)
            retime_file(continuous / "force_ideal.nc", start, baseline_start)
        baseline_state_hash = nc_payload_sha256(initial)
        if nc_payload_sha256(continuous / "wrfinput_d01") != baseline_state_hash:
            raise RuntimeError(f"{label}: continuous initial-state payload differs from PR15 source")
        result = run(exe, continuous, "wrf", env)
        require_run(result)
        invocations.append({"case": label, "phase": "continuous", **result})
        continuous_history = sorted(continuous.glob("wrfout_d01_*"))
        if len(continuous_history) != 1:
            raise RuntimeError(f"continuous run expected one history file, got {continuous_history}")
        require_options(continuous_history, f"{label} continuous")

        phase1 = case_root / "split-1"
        prepare_case(phase1, source_case, wrf_run, nml_for(base_nml, start, checkpoint, False))
        if retime:
            retime_file(phase1 / "wrfinput_d01", start, baseline_start)
            retime_file(phase1 / "force_ideal.nc", start, baseline_start)
        if nc_payload_sha256(phase1 / "wrfinput_d01") != baseline_state_hash:
            raise RuntimeError(f"{label}: split-1 initial-state payload differs from PR15 source")
        result = run(exe, phase1, "wrf", env)
        require_run(result)
        invocations.append({"case": label, "phase": "split-1", **result})
        restart_files = sorted(phase1.glob("wrfrst_d01_*"))
        if len(restart_files) != 1:
            raise RuntimeError(f"split phase 1 expected one checkpoint, got {restart_files}")
        require_options(restart_files, f"{label} split-1 checkpoint")
        history1 = sorted(phase1.glob("wrfout_d01_*"))
        require_options(history1, f"{label} split-1")

        phase2 = case_root / "split-2"
        prepare_case(phase2, source_case, wrf_run, nml_for(base_nml, checkpoint, stop, True))
        if retime:
            retime_file(phase2 / "wrfinput_d01", checkpoint, baseline_start)
            retime_file(phase2 / "force_ideal.nc", start, baseline_start)
        if nc_payload_sha256(phase2 / "wrfinput_d01") != baseline_state_hash:
            raise RuntimeError(f"{label}: split-2 initial-state payload differs from PR15 source")
        shutil.copy2(restart_files[0], phase2 / restart_files[0].name)
        result = run(exe, phase2, "wrf", env)
        require_run(result)
        invocations.append({"case": label, "phase": "split-2", **result})
        history2 = sorted(phase2.glob("wrfout_d01_*"))
        if not history2:
            raise RuntimeError("split phase 2 produced no history output")
        require_options(history2, f"{label} split-2")
        diagnostic_boundary = require_restart_diagnostics(
            restart_files[0], history2[0], time_text(checkpoint))
        restarted_merged = case_root / "restarted_merged.nc"
        merge_history(history1 + history2, restarted_merged)

        checkpoint_time = time_text(checkpoint)
        command = [sys.executable, str(comparator), str(continuous_history[0]), str(restarted_merged),
                   "--checkpoint", str(restart_files[0]), "--checkpoint-time", checkpoint_time]
        completed = subprocess.run(command, capture_output=True, text=True, check=False)
        if completed.returncode:
            raise RuntimeError(f"restart comparator failed for {label}: {completed.stdout}\n{completed.stderr}")
        comparison = json.loads(completed.stdout)
        (case_root / "comparison.json").write_text(json.dumps(comparison, indent=2) + "\n")
        if comparison["summary"]["differing_variable_time_pairs"] != 0:
            raise RuntimeError(f"restart histories differ for {label}; see {case_root / 'comparison.json'}")
        if comparison.get("checkpoint", {}).get("differing_variables"):
            raise RuntimeError(f"checkpoint mismatch for {label}; see {case_root / 'comparison.json'}")
        if comparison["summary"]["matching_time_count"] != 13:
            raise RuntimeError(f"{label}: expected 13 matching history times, got {comparison['summary']['matching_time_count']}")
        all_reports.append({"case": label, "continuous_history": str(continuous_history[0]),
                            "restart_checkpoint": str(restart_files[0]),
                            "restart_history_files": [str(x) for x in history1 + history2],
                            "merged_restart_history": str(restarted_merged),
                            "comparison": str(case_root / "comparison.json"),
                            "matching_times": comparison["summary"]["matching_time_count"],
                            "variables": comparison["common_variable_count"],
                            "exact_time_matches": comparison["summary"]["exact_match_times"],
                            "checkpoint_time": checkpoint_time,
                            "diagnostic_restart_boundary": diagnostic_boundary,
                            "start_time": time_text(start), "end_time": time_text(stop),
                            "calendar_retimed": retime,
                            "calendar_changed_metadata": ("wrfinput_d01 and force_ideal.nc Times; "
                                "START_DATE/SIMULATION_START_DATE; available JULYR/JULDAY/GMT variables and attributes")
                                if retime else None,
                            "baseline_wrfinput_sha256": sha256(initial),
                            "staged_wrfinput_state_payload_sha256": baseline_state_hash,
                            "baseline_force_ideal_sha256": sha256(source_case / "force_ideal.nc"),
                            "staged_force_ideal_payload_sha256": nc_payload_sha256(continuous / "force_ideal.nc")})
    receipt = {"status": "PASS", "scope": "serial actual WRF UDM/RRTMGP 37/37 SCM restart determinism; not a long forecast claim",
               "physics_options": {"ra_lw_physics": 37, "ra_sw_physics": 37, "mp_physics": 27, "use_mp_re": 1},
               "requested_run_seconds": 120, "timestep_seconds": 10, "radiation_timestep_minutes": 0.5,
               "checkpoint_seconds": 60, "history_interval_seconds": 10,
               "executable": str(exe.resolve()), "executable_sha256": sha256(exe.resolve()),
               "comparison_tool": str(comparator), "runner": str(Path(__file__).resolve()),
               "runner_sha256": sha256(Path(__file__).resolve()),
               "baseline_root": str(baseline_root), "invocations": invocations, "cases": all_reports,
               "calendar_boundary_included": args.calendar_boundary,
               "calendar_note": ("The boundary case retimes Times, restart/history namelists, and available date metadata; "
                                 "it checks restart reproducibility only, not meteorological validity at the retimed date.")}
    (outroot / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps(receipt, indent=2))


if __name__ == "__main__":
    main()
