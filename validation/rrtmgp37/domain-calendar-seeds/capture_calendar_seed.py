#!/usr/bin/env python3
"""Capture and independently validate production MCICA year/day keys."""
from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import netCDF4

HERE = Path(__file__).resolve().parent


def discover_repo(start: Path) -> Path:
    for parent in (start, *start.parents):
        if (parent / "WRF/test/rrtmgp").is_dir() and (parent / "WRF/main").is_dir():
            return parent
    raise RuntimeError(f"cannot discover WRF checkout from {start}")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def fresh_copy(source: Path, destination: Path, *, restart_name: str | None) -> None:
    destination.mkdir(parents=True, exist_ok=False)
    for item in source.iterdir():
        if item.name in {"wrf.log", "ideal.log", "namelist.output", "capture"}:
            continue
        if item.name.startswith("wrfout_d01_"):
            continue
        if item.name.startswith("wrfrst_d01_") and item.name != restart_name:
            continue
        target = destination / item.name
        if item.is_symlink():
            target.symlink_to(item.resolve())
        elif item.is_file():
            shutil.copy2(item, target)
        elif item.is_dir():
            shutil.copytree(item, target, symlinks=True)
    if restart_name and not (destination / restart_name).is_file():
        raise RuntimeError(f"checkpoint missing from copied case: {restart_name}")
    nml_path = destination / "namelist.input"
    text = nml_path.read_text()
    for key in ("ra_lw_physics", "ra_sw_physics"):
        text, count = re.subn(rf"(?im)^(\s*{key}\s*=\s*)[^,\n]+,", rf"\g<1>37,", text, count=1)
        if count != 1:
            raise RuntimeError(f"could not set {key}=37 in {nml_path}")
    nml_path.write_text(text)
    (destination / "capture").mkdir()


def require_37_case(case: Path, restart_name: str | None = None) -> None:
    text = (case / "namelist.input").read_text()
    if not re.search(r"(?im)^\s*ra_lw_physics\s*=\s*37\s*,", text):
        raise RuntimeError(f"{case}: namelist is not LW physics 37")
    if not re.search(r"(?im)^\s*ra_sw_physics\s*=\s*37\s*,", text):
        raise RuntimeError(f"{case}: namelist is not SW physics 37")
    if not re.search(r"(?im)^\s*mp_physics\s*=\s*27\s*,", text):
        raise RuntimeError(f"{case}: namelist is not UDM mp_physics 27")
    candidates = list(case.glob("wrfout_d01_*"))
    if not candidates:
        raise RuntimeError(f"{case}: no source history file to verify physics options")
    with netCDF4.Dataset(candidates[-1]) as ds:
        options = (int(ds.getncattr("RA_LW_PHYSICS")), int(ds.getncattr("RA_SW_PHYSICS")),
                   int(ds.getncattr("MP_PHYSICS")))
    if options != (37, 37, 27):
        raise RuntimeError(f"{case}: source history options {options}, expected 37/37/27")
    if restart_name:
        with netCDF4.Dataset(case / restart_name) as ds:
            options = (int(ds.getncattr("RA_LW_PHYSICS")), int(ds.getncattr("RA_SW_PHYSICS")),
                       int(ds.getncattr("MP_PHYSICS")))
        if options != (37, 37, 27):
            raise RuntimeError(f"{case / restart_name}: checkpoint options {options}, expected 37/37/27")


def run_capture(source: Path, destination: Path, expected_time: str, restart_name: str | None,
                repo: Path, seed_validator) -> dict:
    require_37_case(source, restart_name)
    fresh_copy(source, destination, restart_name=restart_name)
    env = os.environ.copy()
    for key in ("WRF_RRTMGP_CAPTURE_DIR", "WRF_RRTMGP_CAPTURE_CALL", "WRF_RRTMGP_CAPTURE_ALL",
                "WRF_RRTMGP_AUDIT_DIR", "WRF_RRTMGP_AUDIT_SEEDS", "WRF_RRTMGP_HYDRO_DIAG_DIR"):
        env.pop(key, None)
    env["WRF_RRTMGP_CAPTURE_DIR"] = str((destination / "capture").resolve())
    env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
    env["OMP_NUM_THREADS"] = "1"
    wrf_exe = repo / "WRF/main/wrf.exe"
    validator_path = repo / "WRF/test/rrtmgp/test_domain_seed_capture.py"
    exe_hash_before = sha(wrf_exe)
    log = destination / "wrf.log"
    with log.open("w") as stream:
        run = subprocess.run([str(wrf_exe.resolve())], cwd=destination, env=env,
                             stdout=stream, stderr=subprocess.STDOUT, check=False)
    log_text = log.read_text(errors="replace")
    exe_hash_after = sha(wrf_exe)
    if run.returncode != 0 or "SUCCESS COMPLETE WRF" not in log_text:
        raise RuntimeError(f"WRF capture run failed: {log}")
    if exe_hash_before != exe_hash_after:
        raise RuntimeError("executable changed during capture run")
    require_37_case(destination)
    validation = destination / "domain_seed_validation.json"
    phase_checks = []
    for phase in ("lw", "sw"):
        raw, inp = destination / "capture" / f"{phase}.raw", destination / "capture" / f"{phase}.input"
        if raw.is_file() and inp.is_file():
            checked = seed_validator.validate_raw(raw, inp, expected_domain=1, expected_time=expected_time)
            checked.update({"raw_path": str(raw), "raw_sha256": sha(raw),
                            "input_path": str(inp), "input_sha256": sha(inp)})
            phase_checks.append(checked)
    if not any(item["phase"] == "LW" for item in phase_checks):
        raise RuntimeError("capture did not include a valid LW seed record")
    if len({item["phase"] for item in phase_checks}) != len(phase_checks):
        raise RuntimeError("duplicate phase seed records in capture")
    report = {"status": "PASS", "validator": "test_domain_seed_capture.validate_raw",
              "expected_domain_id": 1, "expected_time": expected_time, "captures": phase_checks}
    validation.write_text(json.dumps(report, indent=2) + "\n")
    return {"case": str(destination), "source_case": str(source), "expected_time": expected_time,
            "checkpoint": restart_name, "success_marker": True, "wrf_returncode": run.returncode,
            "physics_options": [37, 37, 27], "executable": str(wrf_exe.resolve()), "executable_sha256_before": exe_hash_before,
            "executable_sha256_after": exe_hash_after, "capture_directory": str(destination / "capture"),
            "capture_files": {p.name: sha(p) for p in sorted((destination / "capture").iterdir())},
            "validator": str(validator_path), "validator_sha256": sha(validator_path),
            "validation_receipt": str(validation),
            "phase_seed_year_day": {item["phase"]: [item["metadata"]["year"], item["metadata"]["day_of_year"]]
                                     for item in report["captures"]},
            "phase_seed_values": {item["phase"]: item["header_seed"] for item in report["captures"]},
            "independent_validation": "PASS"}


def main() -> None:
    import argparse
    import importlib

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo", type=Path, default=discover_repo(HERE))
    parser.add_argument("--restart-root", type=Path, default=None,
                        help="run_restart_determinism.py output containing calendar/split-2 and control/continuous")
    parser.add_argument("--output-root", type=Path, default=HERE / "seed-capture-yearproof")
    args = parser.parse_args()
    repo = args.repo.resolve()
    root = (args.restart_root or (repo / "build/udm-domain-seeds-pr16/restart/run-final-37")).resolve()
    sys.path.insert(0, str(repo / "WRF/test/rrtmgp"))
    seed_validator = importlib.import_module("test_domain_seed_capture")
    boundary_source = root / "calendar/split-2"
    standard_source = root / "control/continuous"
    out = args.output_root.resolve()
    if out.exists():
        raise RuntimeError(f"refusing to overwrite {out}")
    out.mkdir()
    boundary = run_capture(boundary_source, out / "calendar-resume-2000",
                           "2000-01-01_00:00:10", "wrfrst_d01_2000-01-01_00:00:00", repo, seed_validator)
    standard = run_capture(standard_source, out / "continuous-1999",
                           "1999-10-22_19:00:00", None, repo, seed_validator)
    receipt = {"status": "PASS", "scope": "actual RRTMGP 37/37 WRF trace proves production seed metadata is read from each run's calendar; no forecast claim",
               "repository": str(repo), "restart_root": str(root), "output_root": str(out),
               "radiation_options": [37, 37], "microphysics_option": 27,
               "environment": {"WRF_RRTMGP_CAPTURE_CALL": "1", "WRF_RRTMGP_CAPTURE_ALL": "unset",
                               "WRF_RRTMGP_AUDIT_DIR": "unset", "OMP_NUM_THREADS": "1"},
               "runs": [boundary, standard]}
    (out / "receipt.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(json.dumps({"status": "PASS", "receipt": str(out / "receipt.json"),
                      "calendar_year_day": [boundary["phase_seed_year_day"], standard["phase_seed_year_day"]]}, indent=2))


if __name__ == "__main__":
    main()
