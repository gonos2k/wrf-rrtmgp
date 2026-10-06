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
import re
import signal
import resource
import shutil
import subprocess
import sys
from datetime import datetime, timedelta, timezone


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
        "run_days": "0",
        "run_minutes": "0",
        "run_seconds": "0",
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


def verify_namelist_paths(path: Path, preflight: dict) -> None:
    nml = namelist_assignments(path)
    def unquote(value: str) -> str:
        return value.strip().strip(",").strip().strip("'\"")
    expected = {
        "rrtmgp_udm_frozen_table": preflight["physics_and_static_data"]["frozen_table"],
        "rrtmgp_data_path": preflight["physics_and_static_data"]["run_path"],
    }
    for key, wanted in expected.items():
        got = nml.get(key)
        if got is None or unquote(got) != str(wanted):
            raise RuntimeError(f"namelist {key} does not match pinned path: expected {wanted!r}, got {got!r}")
    for key, expected in {
        "start_year": "2010, 2010",
        "start_month": "06, 06",
        "end_year": "2010, 2010",
        "end_month": "06, 06",
        "start_hour": "00, 01",
        "start_minute": "00, 00",
        "start_second": "00, 00",
        "end_hour": "02, 02",
        "end_minute": "00, 00",
        "end_second": "00, 00",
        "end_day": "11, 11",
        "history_interval": "10, 10",
        "frames_per_outfile": "1, 1",
        "interval_seconds": "21600",
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
        ("current guarded runner", Path(preflight["runner"]["path"]), preflight["runner"]["sha256"]),
        ("preserved pre-review runner", Path(preflight["runner"]["pre_review_path"]),
         preflight["runner"]["pre_review_sha256"]),
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


def stage_case(repo: Path, case_dir: Path, preflight: dict, nml_source: Path) -> list[dict]:
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
    manifest = []
    for src, dest in links:
        manifest.append({"name": dest.name, "path": str(dest), "target": str(src.resolve()),
                         "sha256": sha256(dest), "symlink": dest.is_symlink()})
    manifest.append({"name": "namelist.input", "path": str(case_dir / "namelist.input"),
                     "target": None, "sha256": sha256(case_dir / "namelist.input"), "symlink": False})
    return manifest


def verify_staged_assets(manifest: list[dict]) -> list[dict]:
    checked = []
    for item in manifest:
        path = Path(item["path"])
        if not path.exists():
            raise RuntimeError(f"staged asset missing: {path}")
        if path.is_symlink() != item["symlink"]:
            raise RuntimeError(f"staged asset symlink status changed: {path}")
        target = str(path.resolve()) if path.is_symlink() else None
        if target != item["target"]:
            raise RuntimeError(f"staged asset target changed: {path}: {target}")
        got = sha256(path)
        if got != item["sha256"]:
            raise RuntimeError(f"staged asset hash changed: {path}: expected {item['sha256']}, got {got}")
        checked.append({"name": item["name"], "path": str(path), "sha256": got})
    return checked


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

    summary: dict = {"domains": {}, "all_numeric_fields_finite": True,
                     "masked_numeric_values_rejected": True}
    base = datetime(2010, 6, 11)
    expected = {
        1: [(base + timedelta(minutes=10 * n)).strftime("%Y-%m-%d_%H:%M:%S") for n in range(13)],
        2: [(base + timedelta(minutes=60 + 10 * n)).strftime("%Y-%m-%d_%H:%M:%S") for n in range(7)],
    }
    expected_dims = {
        1: {"Time": 1, "DateStrLen": 19, "west_east": 289, "south_north": 189, "bottom_top": 39,
            "west_east_stag": 290, "south_north_stag": 190, "bottom_top_stag": 40},
        2: {"Time": 1, "DateStrLen": 19, "west_east": 60, "south_north": 60, "bottom_top": 39,
            "west_east_stag": 61, "south_north_stag": 61, "bottom_top_stag": 40},
    }
    required_vars = {"SWDOWN", "GLW", "OLR", "QGRAUP", "QHAIL", "Times"}
    for domain in (1, 2):
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
                if len(path_times) != 1:
                    raise RuntimeError(f"{path}: expected one record per history file, got {len(path_times)}")
                missing_vars = required_vars.difference(ds.variables)
                if missing_vars:
                    raise RuntimeError(f"{path}: missing required output variables {sorted(missing_vars)}")
                for name, size in expected_dims[domain].items():
                    if name not in ds.dimensions or len(ds.dimensions[name]) != size:
                        got = len(ds.dimensions[name]) if name in ds.dimensions else None
                        raise RuntimeError(f"{path}: dimension {name} expected {size}, got {got}")
                attrs = {
                    "GRID_ID": domain,
                    "PARENT_ID": 0 if domain == 1 else 1,
                    "PARENT_GRID_RATIO": 1 if domain == 1 else 3,
                    "I_PARENT_START": 1 if domain == 1 else 100,
                    "J_PARENT_START": 1 if domain == 1 else 80,
                    "MP_PHYSICS": 27,
                    "RA_LW_PHYSICS": 37,
                    "RA_SW_PHYSICS": 37,
                    "BL_PBL_PHYSICS": 1,
                    "SF_SURFACE_PHYSICS": 2,
                    "SF_SFCLAY_PHYSICS": 1,
                    "CU_PHYSICS": 1 if domain == 1 else 0,
                }
                for key, expected_attr in attrs.items():
                    if key not in ds.ncattrs() or int(np.asarray(ds.getncattr(key)).reshape(-1)[0]) != expected_attr:
                        raise RuntimeError(f"{path}: {key} missing or differs from expected {expected_attr}")
                expected_dx = 20000.0 if domain == 1 else 20000.0 / 3.0
                expected_dy = 20000.0 if domain == 1 else 20000.0 / 3.0
                for key, value in (("DX", expected_dx), ("DY", expected_dy)):
                    if key not in ds.ncattrs() or not np.isclose(float(ds.getncattr(key)), value, rtol=0., atol=1.e-3):
                        raise RuntimeError(f"{path}: {key} expected {value}, got {ds.getncattr(key) if key in ds.ncattrs() else None}")
                horizontal_shape = (1, expected_dims[domain]["south_north"], expected_dims[domain]["west_east"])
                hydro_shape = (1, expected_dims[domain]["bottom_top"],
                               expected_dims[domain]["south_north"], expected_dims[domain]["west_east"])
                for name in ("SWDOWN", "GLW", "OLR"):
                    if ds.variables[name].shape != horizontal_shape:
                        raise RuntimeError(f"{path}:{name} expected shape {horizontal_shape}, got {ds.variables[name].shape}")
                for name in ("QGRAUP", "QHAIL"):
                    if ds.variables[name].shape != hydro_shape:
                        raise RuntimeError(f"{path}:{name} expected shape {hydro_shape}, got {ds.variables[name].shape}")
                for name, var in ds.variables.items():
                    if np.dtype(var.dtype).kind not in "iuf":
                        continue
                    arr = np.ma.asarray(var[:])
                    mask = np.ma.getmaskarray(arr)
                    data = np.asarray(np.ma.getdata(arr))
                    if np.any(mask):
                        raise RuntimeError(f"masked numeric values in {path}:{name}: count={int(mask.sum())}")
                    if data.size and not np.all(np.isfinite(data)):
                        raise RuntimeError(f"nonfinite values in {path}:{name}")
                    checked_vars += 1
                    masked_values += int(mask.sum())
        if len(times) != len(set(times)):
            raise RuntimeError(f"duplicate d{domain:02d} history timestamps: {times}")
        if times != expected[domain]:
            raise RuntimeError(f"d{domain:02d} history timestamps differ from exact schedule: expected {expected[domain]}, got {times}")
        summary["domains"][f"d{domain:02d}"] = {
            "history_file_count": len(paths), "times": times,
            "numeric_variable_file_checks": checked_vars, "masked_numeric_value_count": masked_values,
            "dimensions": expected_dims[domain],
            "dx_m": 20000.0 if domain == 1 else 20000.0 / 3.0,
            "dy_m": 20000.0 if domain == 1 else 20000.0 / 3.0,
            "required_radiation_fields": sorted(required_vars - {"Times"}),
            "udm37_metadata": {"MP_PHYSICS": 27, "RA_LW_PHYSICS": 37, "RA_SW_PHYSICS": 37},
        }
    return summary


def check_runtime_loader(executable: Path, env: dict[str, str]) -> dict:
    """Resolve linked libraries without starting WRF."""
    result = subprocess.run(["ldd", str(executable)], env=env, text=True,
                            stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    text = result.stdout
    if result.returncode != 0 or "not found" in text:
        raise RuntimeError(f"ldd failed or found unresolved libraries (exit={result.returncode}):\n{text}")
    for token in ("libmpi", "libnetcdff", "libnetcdf", "libgomp"):
        if token not in text:
            raise RuntimeError(f"ldd did not resolve expected runtime {token}:\n{text}")
    return {"returncode": result.returncode, "output": text}


def child_stack_limit() -> None:
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    target = 512 * 1024 * 1024
    if hard != resource.RLIM_INFINITY and hard < target:
        raise RuntimeError(f"hard stack limit too small for WRF: {hard}")
    resource.setrlimit(resource.RLIMIT_STACK, (target, hard))


def check_stack_limit_available() -> dict:
    soft, hard = resource.getrlimit(resource.RLIMIT_STACK)
    target = 512 * 1024 * 1024
    if hard != resource.RLIM_INFINITY and hard < target:
        raise RuntimeError(f"hard stack limit too small for WRF: {hard} < {target}")
    return {"current_soft_bytes": soft, "hard_bytes": hard, "planned_child_soft_bytes": target}


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
    verify_namelist_paths(nml_path, preflight)
    verified_before = verify_pins(repo, preflight)
    mpi_bin = repo / "build/deps/mpich-sock/bin"
    mpi_lib = repo / "build/deps/mpich-sock/lib"
    nc_lib = repo / "build/deps/netcdf/lib"
    root_lib = repo / "build/deps/root/usr/lib/x86_64-linux-gnu"
    system_lib = Path("/usr/lib/x86_64-linux-gnu")
    lib_dirs = [nc_lib, mpi_lib, root_lib, system_lib]
    env = os.environ.copy()
    env["PATH"] = str(mpi_bin) + os.pathsep + env.get("PATH", "")
    env["LD_LIBRARY_PATH"] = os.pathsep.join(str(p) for p in lib_dirs) + os.pathsep + env.get("LD_LIBRARY_PATH", "")
    stack_check = check_stack_limit_available()
    loader = check_runtime_loader(Path(preflight["build"]["executable"]), env)
    mpi_version = subprocess.run([str(mpi_bin / "mpiexec"), "--version"], env=env, text=True,
                                  stdout=subprocess.PIPE, stderr=subprocess.STDOUT, check=False)
    if mpi_version.returncode != 0 or "HYDRA" not in mpi_version.stdout:
        raise RuntimeError(f"MPICH launcher preflight failed ({mpi_version.returncode}): {mpi_version.stdout}")
    if not args.execute:
        print(json.dumps({"status": "PLAN_PREFLIGHT_PASS_NOT_LAUNCHED", "verified_files": len(verified_before),
                          "namelist_sha256": sha256(nml_path), "child_input": "absent by design",
                          "runtime_library_dirs": [str(x) for x in lib_dirs],
                          "runtime_loader": {"returncode": loader["returncode"], "unresolved": False},
                          "mpich_launcher": {"returncode": mpi_version.returncode,
                                             "version_line": next((x.strip() for x in mpi_version.stdout.splitlines() if "Version:" in x), "")},
                          "stack_limit": stack_check,
                          "planned_openmp": {"OMP_NUM_THREADS": "1", "OMP_DYNAMIC": "FALSE", "OMP_STACKSIZE": "512M"}}, indent=2))
        return 0

    case_dir = Path(args.case_dir).resolve() if args.case_dir else repo / "build/udm-nested-domain-plan/case-v2"
    if case_dir.exists():
        raise RuntimeError(f"refusing existing case directory: {case_dir}")
    staged_manifest = stage_case(repo, case_dir, preflight, nml_path)
    if sha256(case_dir / "namelist.input") != sha256(nml_path):
        raise RuntimeError("staged namelist differs from pinned plan namelist")
    staged_before = verify_staged_assets(staged_manifest)
    verified_before = verify_pins(repo, preflight)
    receipt = {
        "status": "RUNNING",
        "case_dir": str(case_dir),
        "binary_sha256": preflight["build"]["executable_sha256"],
        "preflight_sha256": sha256(preflight_path),
        "namelist_sha256": sha256(case_dir / "namelist.input"),
        "source_namelist_sha256": sha256(nml_path),
        "staged_assets": staged_manifest,
        "staged_assets_before": staged_before,
        "pinned_files_before": verified_before,
        "input_sha256": preflight["parent_input"]["sha256"],
        "boundary_sha256": preflight["parent_boundary"]["sha256"],
        "frozen_table_sha256": preflight["physics_and_static_data"]["frozen_table_sha256"],
        "start_utc": datetime.now(timezone.utc).isoformat(),
        "runtime_seed_capture_audit": "disabled; cleared inherited variables",
    }
    receipt_path = case_dir / "execution.json"
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    env = env.copy()
    removed = []
    for key in list(env):
        if key.startswith("WRF_RRTMGP_") or key.startswith("WRF_UDM_BOUNDARY_CAPTURE"):
            removed.append(key)
            env.pop(key)
    env["MPICH_INTERFACE_HOSTNAME"] = "127.0.0.1"
    env["OMP_NUM_THREADS"] = "1"
    env["OMP_DYNAMIC"] = "FALSE"
    env["OMP_STACKSIZE"] = "512M"
    env["OPENBLAS_NUM_THREADS"] = "1"
    mpiexec = mpi_bin / "mpiexec"
    command = [str(mpiexec), "-launcher", "fork", "-iface", "lo", "-n", "4", str(Path(preflight["build"]["executable"]))]
    receipt["command"] = command
    receipt["environment"] = {k: env[k] for k in ("MPICH_INTERFACE_HOSTNAME", "OMP_NUM_THREADS", "OMP_DYNAMIC", "OMP_STACKSIZE", "OPENBLAS_NUM_THREADS", "LD_LIBRARY_PATH")}
    receipt["runtime_loader"] = loader
    receipt["main_stack_limit_bytes"] = 512 * 1024 * 1024
    receipt["removed_inherited_environment_keys"] = removed
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    try:
        with (case_dir / "run.log").open("wb") as log:
            proc = subprocess.Popen(command, cwd=case_dir, env=env, stdout=log, stderr=subprocess.STDOUT,
                                    start_new_session=True, preexec_fn=child_stack_limit)
            receipt["launcher_pid"] = proc.pid
            try:
                returncode = proc.wait(timeout=3600)
                receipt["launcher_timed_out"] = False
            except subprocess.TimeoutExpired:
                receipt["launcher_timed_out"] = True
                receipt["timeout_seconds"] = 3600
                try:
                    os.killpg(proc.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                try:
                    proc.wait(timeout=20)
                except subprocess.TimeoutExpired:
                    pass
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                returncode = proc.wait()
            receipt["launcher_returncode"] = returncode
        rank_logs = sorted(case_dir.glob("rsl.error.*"))
        rank_results = {p.name: "SUCCESS COMPLETE WRF" in p.read_text(errors="replace") for p in rank_logs}
        receipt["rank_success"] = rank_results
        receipt["rank_success_all"] = len(rank_logs) == 4 and all(rank_results.values())
        logs = "\n".join(p.read_text(errors="replace") for p in sorted(case_dir.glob("rsl.*")))
        interpolation_pattern = r"Initializing nest domain #\s*2 by horizontally interpolating parent domain #\s*1\."
        receipt["parent_interpolation_logged"] = re.search(interpolation_pattern, logs) is not None
        receipt["parent_interpolation_log_pattern"] = interpolation_pattern
        receipt["child_input_absent"] = not (case_dir / "wrfinput_d02").exists()
        receipt["output_validation"] = validate_outputs(case_dir)
        receipt["pinned_files_after"] = verify_pins(repo, preflight)
        receipt["staged_assets_after"] = verify_staged_assets(staged_manifest)
        receipt["staged_namelist_unchanged"] = sha256(case_dir / "namelist.input") == receipt["namelist_sha256"]
        ok = (returncode == 0 and not receipt.get("launcher_timed_out") and receipt["rank_success_all"]
              and receipt["parent_interpolation_logged"] and receipt["child_input_absent"]
              and receipt["staged_namelist_unchanged"])
        receipt["status"] = "PASS_BOUNDED_NESTED_RUNTIME" if ok else "FAIL_BOUNDED_NESTED_RUNTIME"
        exit_code = 0 if ok else 1
    except Exception as exc:
        receipt["status"] = "FAIL_BOUNDED_NESTED_RUNTIME"
        receipt["failure"] = f"{type(exc).__name__}: {exc}"
        try:
            receipt["pinned_files_after"] = verify_pins(repo, preflight)
        except Exception as pin_exc:
            receipt["postrun_pin_failure"] = f"{type(pin_exc).__name__}: {pin_exc}"
        try:
            receipt["staged_assets_after"] = verify_staged_assets(staged_manifest)
        except Exception as staged_exc:
            receipt["postrun_staged_asset_failure"] = f"{type(staged_exc).__name__}: {staged_exc}"
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
