#!/usr/bin/env python3
"""Guarded runner for the proposed two-domain UDM27/RRTMGP37 smoke test.

Without --execute this only verifies pinned inputs and namelist values. The
model run creates a new case directory and never overwrites an existing one.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
from datetime import datetime, timezone


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def find_repo(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).resolve()
    for candidate in Path(__file__).resolve().parents:
        if (candidate / "WRF/Registry/Registry.EM_COMMON").is_file() and (candidate / "build/udm-sr-row-dm-sm/source/WRF/main/wrf.exe").is_file():
            return candidate
    raise RuntimeError("Could not locate repository root; pass --repo")


def namelist_assignments(path: Path) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in path.read_text().splitlines():
        stripped = line.split("!", 1)[0].strip()
        if "=" not in stripped:
            continue
        key, value = stripped.split("=", 1)
        values[key.strip().lower()] = value.strip().rstrip(",").strip()
    return values


def verify_namelist(path: Path) -> None:
    nml = namelist_assignments(path)
    scalar = {
        "max_dom": "2",
        "run_hours": "0",
        "input_from_file": ".true., .false.",
        "e_we": "290, 61",
        "e_sn": "190, 61",
        "e_vert": "40, 40",
        "dx": "20000, 6666.6666667",
        "dy": "20000, 6666.6666667",
        "grid_id": "1, 2",
        "parent_id": "0, 1",
        "i_parent_start": "1, 100",
        "j_parent_start": "1, 80",
        "parent_grid_ratio": "1, 3",
        "parent_time_step_ratio": "1, 3",
        "mp_physics": "27, 27",
        "ra_lw_physics": "37, 37",
        "ra_sw_physics": "37, 37",
        "bl_pbl_physics": "1, 1",
        "sf_surface_physics": "2, 2",
        "sf_sfclay_physics": "1, 1",
        "cu_physics": "1, 0",
        "radt": "10, 10",
        "use_mp_re": "1",
        "rrtmgp_udm_frozen_optics": "1",
    }
    for key, expected in scalar.items():
        actual = nml.get(key)
        if actual is None or ",".join(actual.lower().split()) != ",".join(expected.lower().split()):
            raise RuntimeError(f"namelist {key}: expected {expected!r}, got {actual!r}")
    for key, expected in {
        "start_hour": "00, 01",
        "end_hour": "02, 02",
        "end_day": "11, 11",
        "history_interval": "10, 10",
    }.items():
        actual = nml.get(key)
        if actual is None or ",".join(actual.lower().split()) != ",".join(expected.lower().split()):
            raise RuntimeError(f"namelist {key}: expected {expected!r}, got {actual!r}")


def pinned_files(repo: Path, preflight: dict) -> list[tuple[str, Path, str]]:
    build = preflight["build"]
    parent = preflight["parent_input"]
    boundary = preflight["parent_boundary"]
    data = preflight["physics_and_static_data"]
    nml = preflight["namelist"]
    pins = [
        ("wrf.exe", Path(build["executable"]), build["executable_sha256"]),
        ("source provenance", Path(build["source_provenance"]), build["source_provenance_sha256"]),
        ("configure.wrf", Path(build["configure_wrf"]), build["configure_wrf_sha256"]),
        ("wrfinput_d01", Path(parent["path"]), parent["sha256"]),
        ("wrfbdy_d01", Path(boundary["path"]), boundary["sha256"]),
        ("frozen table", Path(data["frozen_table"]), data["frozen_table_sha256"]),
        ("namelist", Path(nml["path"]), nml["sha256"]),
    ]
    pins.extend((item["path"], Path(item["path"]), item["sha256"]) for item in build["source_files"])
    pins.extend((item["path"], Path(item["path"]), item["sha256"]) for item in data["files"])
    return pins


def verify_pins(repo: Path, preflight: dict) -> list[dict]:
    checked = []
    for label, path, expected in pinned_files(repo, preflight):
        if not path.is_file():
            raise RuntimeError(f"pinned file missing ({label}): {path}")
        got = sha256(path)
        if got != expected:
            raise RuntimeError(f"pinned hash mismatch ({label}): {path}: expected {expected}, got {got}")
        checked.append({"label": label, "path": str(path), "sha256": got})
    return checked


def stage_case(repo: Path, case_dir: Path, preflight: dict, nml_source: Path) -> None:
    case_dir.parent.mkdir(parents=True, exist_ok=True)
    case_dir.mkdir(exist_ok=False)
    links = [
        (Path(preflight["parent_input"]["path"]), case_dir / "wrfinput_d01"),
        (Path(preflight["parent_boundary"]["path"]), case_dir / "wrfbdy_d01"),
        (Path(preflight["build"]["executable"]), case_dir / "wrf.exe"),
    ]
    for item in preflight["physics_and_static_data"]["files"]:
        src = Path(item["path"])
        if src.name in {"wrfinput_d01", "wrfbdy_d01", "wrfinput_d02", "wrf.exe", "real.exe", "namelist.input"}:
            continue
        links.append((src, case_dir / src.name))
    for src, dest in links:
        if dest.exists() or dest.is_symlink():
            raise RuntimeError(f"staging name collision: {dest}")
        dest.symlink_to(src)
    shutil.copyfile(nml_source, case_dir / "namelist.input")
    if (case_dir / "wrfinput_d02").exists() or (case_dir / "wrfinput_d02").is_symlink():
        raise RuntimeError("a child input file was staged; this plan requires parent interpolation")


def time_strings(ds) -> list[str]:
    values = ds.variables["Times"][:]
    result = []
    for row in values:
        if hasattr(row, "tobytes"):
            raw = row.tobytes()
        else:
            raw = bytes(row)
        result.append(raw.decode("ascii").replace("\x00", "").strip())
    return result


def validate_outputs(case_dir: Path) -> dict:
    import numpy as np
    from netCDF4 import Dataset

    summary: dict = {"domains": {}, "all_numeric_fields_finite": True}
    for domain, start, end in ((1, "2010-06-11_00:00:00", "2010-06-11_02:00:00"),
                               (2, "2010-06-11_01:00:00", "2010-06-11_02:00:00")):
        paths = sorted(case_dir.glob(f"wrfout_d{domain:02d}_*"))
        if not paths:
            raise RuntimeError(f"no wrfout files for d{domain:02d}")
        times, checked_vars, masked_values = [], 0, 0
        for path in paths:
            with Dataset(path) as ds:
                if "Times" not in ds.variables:
                    raise RuntimeError(f"{path} has no Times variable")
                path_times = time_strings(ds)
                times.extend(path_times)
                attrs = {
                    "GRID_ID": domain,
                    "MP_PHYSICS": 27,
                    "RA_LW_PHYSICS": 37,
                    "RA_SW_PHYSICS": 37,
                    "BL_PBL_PHYSICS": 1,
                    "SF_SURFACE_PHYSICS": 2,
                    "SF_SFCLAY_PHYSICS": 1,
                    "CU_PHYSICS": 1 if domain == 1 else 0,
                }
                for key, expected in attrs.items():
                    if key not in ds.ncattrs() or int(np.asarray(ds.getncattr(key)).reshape(-1)[0]) != expected:
                        raise RuntimeError(f"{path}: {key} missing or differs from expected {expected}")
                if domain == 2:
                    dx = float(ds.getncattr("DX"))
                    if abs(dx - 20000.0 / 3.0) > 1.e-3:
                        raise RuntimeError(f"d02 DX differs from parent ratio: {dx}")
                for name, var in ds.variables.items():
                    if np.dtype(var.dtype).kind not in "iuf":
                        continue
                    arr = np.ma.asarray(var[:])
                    mask = np.ma.getmaskarray(arr)
                    data = np.asarray(np.ma.getdata(arr))
                    active = data[~mask]
                    if active.size and not np.all(np.isfinite(active)):
                        raise RuntimeError(f"nonfinite values in {path}:{name}")
                    checked_vars += 1
                    masked_values += int(mask.sum())
        times = sorted(set(times))
        if len(times) < (2 if domain == 1 else 2):
            raise RuntimeError(f"too few history times for d{domain:02d}: {times}")
        if times[0] < start or times[-1] > end:
            raise RuntimeError(f"history times outside d{domain:02d} configured interval: {times[0]}..{times[-1]}")
        if domain == 1 and times[0] != start:
            raise RuntimeError(f"d01 output does not begin at {start}: {times[0]}")
        if domain == 2 and times[0] < start:
            raise RuntimeError(f"d02 output precedes child start {start}: {times[0]}")
        summary["domains"][f"d{domain:02d}"] = {
            "history_file_count": len(paths), "times": times,
            "numeric_variable_file_checks": checked_vars, "masked_numeric_value_count": masked_values,
        }
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", help="repository root (auto-detected by default)")
    parser.add_argument("--case-dir", help="new output directory; refuses an existing directory")
    parser.add_argument("--execute", action="store_true", help="after review, stage and launch the two-domain WRF case")
    args = parser.parse_args()

    repo = find_repo(args.repo)
    plan_dir = repo / "build/udm-nested-domain-plan/v2"
    preflight_path = plan_dir / "preflight.json"
    nml_path = plan_dir / "namelist.input"
    preflight = json.loads(preflight_path.read_text())
    if preflight.get("status") != "PLAN_ONLY_NOT_LAUNCHED":
        raise RuntimeError("unexpected preflight status")
    verify_namelist(nml_path)
    verified_before = verify_pins(repo, preflight)
    if not args.execute:
        print(json.dumps({"status": "PLAN_PREFLIGHT_PASS_NOT_LAUNCHED", "verified_files": len(verified_before),
                          "namelist_sha256": sha256(nml_path), "child_input": "absent by design"}, indent=2))
        return 0

    case_dir = Path(args.case_dir).resolve() if args.case_dir else repo / "build/udm-nested-domain-plan/case-v2"
    if case_dir.exists():
        raise RuntimeError(f"refusing existing case directory: {case_dir}")
    stage_case(repo, case_dir, preflight, nml_path)
    receipt = {
        "status": "RUNNING",
        "case_dir": str(case_dir),
        "binary_sha256": preflight["build"]["executable_sha256"],
        "preflight_sha256": sha256(preflight_path),
        "namelist_sha256": sha256(case_dir / "namelist.input"),
        "input_sha256": preflight["parent_input"]["sha256"],
        "boundary_sha256": preflight["parent_boundary"]["sha256"],
        "frozen_table_sha256": preflight["physics_and_static_data"]["frozen_table_sha256"],
        "start_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_seed_capture_audit": "disabled; cleared inherited variables",
    }
    receipt_path = case_dir / "execution.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    env = os.environ.copy()
    removed = []
    for key in list(env):
        if key.startswith("WRF_RRTMGP_") or key.startswith("WRF_UDM_BOUNDARY_CAPTURE"):
            removed.append(key)
            env.pop(key)
    mpi_bin = repo / "build/deps/mpich-sock/bin"
    mpi_lib = repo / "build/deps/mpich-sock/lib"
    nc_lib = repo / "build/deps/netcdf/lib"
    env["PATH"] = str(mpi_bin) + os.pathsep + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = os.pathsep.join(str(x) for x in (nc_lib, mpi_lib, Path("/usr/lib/x86_64-linux-gnu")) if str(x))
    env["MPICH_INTERFACE_HOSTNAME"] = "127.0.0.1"
    env["OMP_NUM_THREADS"] = "1"
    env["OMP_DYNAMIC"] = "FALSE"
    env["OPENBLAS_NUM_THREADS"] = "1"
    mpiexec = mpi_bin / "mpiexec"
    command = [str(mpiexec), "-launcher", "fork", "-iface", "lo", "-n", "4", str(Path(preflight["build"]["executable"]))]
    receipt["command"] = command
    receipt["environment"] = {k: env[k] for k in ("MPICH_INTERFACE_HOSTNAME", "OMP_NUM_THREADS", "OMP_DYNAMIC", "OPENBLAS_NUM_THREADS", "LD_LIBRARY_PATH")}
    receipt["removed_inherited_environment_keys"] = removed
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    try:
        with (case_dir / "run.log").open("wb") as log:
            proc = subprocess.run(command, cwd=case_dir, env=env, stdout=log, stderr=subprocess.STDOUT)
        receipt["launcher_returncode"] = proc.returncode
        rank_logs = sorted(case_dir.glob("rsl.error.*"))
        rank_results = {p.name: "SUCCESS COMPLETE WRF" in p.read_text(errors="replace") for p in rank_logs}
        receipt["rank_success"] = rank_results
        receipt["rank_success_all"] = len(rank_logs) == 4 and all(rank_results.values())
        interpolation_phrase = "Initializing nest domain # 2 by horizontally interpolating parent domain # 1."
        logs = "\n".join(p.read_text(errors="replace") for p in sorted(case_dir.glob("rsl.*")))
        receipt["parent_interpolation_logged"] = interpolation_phrase in logs
        receipt["child_input_absent"] = not (case_dir / "wrfinput_d02").exists()
        receipt["output_validation"] = validate_outputs(case_dir)
        receipt["pinned_files_after"] = verify_pins(repo, preflight)
        ok = (proc.returncode == 0 and receipt["rank_success_all"] and receipt["parent_interpolation_logged"]
              and receipt["child_input_absent"])
        receipt["status"] = "PASS_BOUNDED_NESTED_RUNTIME" if ok else "FAIL_BOUNDED_NESTED_RUNTIME"
        exit_code = 0 if ok else 1
    except Exception as exc:
        receipt["status"] = "FAIL_BOUNDED_NESTED_RUNTIME"
        receipt["failure"] = f"{type(exc).__name__}: {exc}"
        try:
            receipt["pinned_files_after"] = verify_pins(repo, preflight)
        except Exception as pin_exc:
            receipt["postrun_pin_failure"] = f"{type(pin_exc).__name__}: {pin_exc}"
        exit_code = 1
    receipt["end_utc"] = datetime.now(timezone.utc).isoformat()
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": receipt["status"], "case_dir": str(case_dir),
                      "rank_success_all": receipt.get("rank_success_all"),
                      "parent_interpolation_logged": receipt.get("parent_interpolation_logged"),
                      "output_validation": receipt.get("output_validation"),
                      "failure": receipt.get("failure")}, indent=2))
    return exit_code


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(2)
