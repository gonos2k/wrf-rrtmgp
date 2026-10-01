#!/usr/bin/env python3
"""Run auditable paired WRF SCM comparisons for RRTMG (4) and RRTMGP (37)."""
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
from typing import Any

import netCDF4
import numpy as np


CHECKOUT_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = CHECKOUT_ROOT.parent
WRF_ROOT = CHECKOUT_ROOT / "WRF"
SCM_DIR = WRF_ROOT / "test/rrtmgp"
INPUT_DIR = WRF_ROOT / "test/em_scm_xy"
RUN_DIR = WRF_ROOT / "run"
TEMPLATE = SCM_DIR / "namelist.scm37"
VALIDATOR = SCM_DIR / "validate_scm.py"
sys.path.insert(0, str(SCM_DIR))
import test_cloud_scm  # noqa: E402
import test_column_replay  # noqa: E402
import test_surface_scm  # noqa: E402

SUCCESS_TOKEN = "SUCCESS COMPLETE WRF"
OPTIONS = (4, 37)
REQUIRED_VARS = (
    "SWDOWN", "GLW", "SWDDIR", "SWDDIF", "SWDNT", "LWUPT", "SWDNB", "GSW",
    "SWUPB", "LWDNB", "ACSWDNB", "ACLWDNB", "RTHRATEN", "RTHRATLW", "RTHRATSW",
    "T", "P", "PB", "QVAPOR", "MU", "MUB", "CLDFRA",
)
OMITTED_RE = re.compile(
    r"\b(?P<phase>LW|SW)\s+i=\s*\d+\s+j=\s*\d+:\s+"
    r"RRTMGP_CLEAR_CONDENSATE_EXCLUDED\s+layer=\s*(?P<layer>\d+)\s+"
    r"reason=\s*(?P<reason>\d+)\s+grid_path_g_m2=\s*"
    r"(?P<path>[-+]?(?:\d+(?:\.\d*)?|\.\d+)(?:[EeDd][-+]?\d+)?)"
)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def fail(message: str) -> None:
    raise RuntimeError(message)


def set_physics(namelist: str, *, mp: int, radiation: int, overlap: int) -> str:
    start = namelist.lower().find("&physics")
    end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", namelist[start:]) if start >= 0 else None
    if start < 0 or end_match is None:
        fail("cannot locate &physics namelist block")
    end = start + end_match.start()
    block = namelist[start:end]
    replacements = {"mp_physics": mp, "ra_lw_physics": radiation,
                    "ra_sw_physics": radiation, "cldovrlp": overlap}
    for key, value in replacements.items():
        block, count = re.subn(rf"(?im)^(\s*{key}\s*=\s*)[^,\n]+,",
                               rf"\g<1>{value},", block, count=1)
        if count != 1:
            fail(f"namelist &physics must contain one {key} assignment")
    return namelist[:start] + block + namelist[end:]


def set_clock(namelist: str, run_minutes: int, run_seconds: int = 0) -> str:
    start = namelist.lower().find("&time_control")
    end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", namelist[start:]) if start >= 0 else None
    if start < 0 or end_match is None:
        fail("cannot locate &time_control namelist block")
    end = start + end_match.start()
    block = namelist[start:end]
    values: dict[str, int] = {}
    keys = ("start_year", "start_month", "start_day", "start_hour", "start_minute", "start_second")
    for key in keys:
        match = re.search(rf"(?im)^\s*{key}\s*=\s*(\d+)\s*,", block)
        if match is None:
            fail(f"time_control is missing {key}")
        values[key] = int(match.group(1))
    beginning = datetime(values["start_year"], values["start_month"], values["start_day"],
                         values["start_hour"], values["start_minute"], values["start_second"])
    finish = beginning + timedelta(minutes=run_minutes, seconds=run_seconds)
    updates = {"run_days": 0, "run_hours": 0, "run_minutes": run_minutes,
               "run_seconds": run_seconds,
               "end_year": finish.year, "end_month": finish.month, "end_day": finish.day,
               "end_hour": finish.hour, "end_minute": finish.minute, "end_second": finish.second,
               "history_interval": 0, "history_interval_s": 10}
    for key, value in updates.items():
        pattern = rf"(?im)^(\s*{key}\s*=\s*)\d+\s*,"
        block, count = re.subn(pattern, rf"\g<1>{value},", block, count=1)
        if count == 0 and key == "history_interval_s":
            block = block.rstrip() + "\n history_interval_s                  = 10,\n"
        elif count != 1:
            fail(f"time_control must contain exactly one {key} assignment")
    return namelist[:start] + block + namelist[end:]


def set_grid_width(namelist: str, first_call_grid: int | None) -> str:
    if first_call_grid is None:
        return namelist
    start = namelist.lower().find("&domains")
    end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", namelist[start:]) if start >= 0 else None
    if start < 0 or end_match is None:
        fail("cannot locate &domains namelist block")
    end = start + end_match.start()
    block = namelist[start:end]
    for key in ("e_we", "e_sn"):
        block, count = re.subn(rf"(?im)^(\s*{key}\s*=\s*)\d+\s*,",
                               rf"\g<1>{first_call_grid + 1},", block, count=1)
        if count != 1:
            fail(f"domains namelist must contain one {key} assignment")
    return namelist[:start] + block + namelist[end:]


def configured_namelist(mp: int, radiation: int, overlap: int, minutes: int,
                        first_call_grid: int | None = None) -> str:
    # Both cases use the same original SCM/LSM2 template and debug output.
    text = test_cloud_scm.original_lsm2_namelist()
    total_seconds = minutes * 60
    run_minutes, run_seconds = divmod(total_seconds, 60)
    text = set_clock(set_physics(text, mp=mp, radiation=radiation, overlap=overlap),
                     run_minutes, run_seconds)
    return set_grid_width(text, first_call_grid)


def run_logged(executable: Path, workdir: Path, logfile: str, env: dict[str, str]) -> dict[str, Any]:
    with (workdir / logfile).open("w", encoding="utf-8") as stream:
        proc = subprocess.run([str(executable)], cwd=workdir, env=env,
                              stdout=stream, stderr=subprocess.STDOUT, check=False)
    return {"returncode": proc.returncode, "log": str(workdir / logfile),
            "log_sha256": sha256(workdir / logfile)}


def create_case(case: Path, namelist: str) -> None:
    case.mkdir(parents=True)
    (case / "namelist.input").write_text(namelist, encoding="utf-8")
    shutil.copy2(SCM_DIR / "radiation_iofields.txt", case / "radiation_iofields.txt")
    for name in ("input_sounding", "input_soil", "force_ideal.nc"):
        shutil.copy2(INPUT_DIR / name, case / name)
    for source in RUN_DIR.iterdir():
        if source.is_file():
            target = case / source.name
            if not target.exists():
                target.symlink_to(source.resolve())


def apply_fixture(wrfinput: Path, mp: int, species: str | None) -> dict[str, Any] | None:
    if species is None:
        return None
    fixture = test_column_replay.initialize_cloud_fixture(wrfinput, mp)
    fields = fixture["registered_condensate_fields"]
    active = {"mixed": set(fields), "liquid-only": {"QCLOUD"},
              "ice-only": {"QICE"}, "snow-only": {"QSNOW"}}[species]
    with netCDF4.Dataset(wrfinput, "r+") as ds:
        for var in fields:
            if var not in active:
                ds.variables[var][:] = 0.0
    fixture["scenario_species"] = species
    fixture["active_fields"] = sorted(active)
    return fixture


def variable_hashes(path: Path) -> dict[str, str]:
    out = {}
    with netCDF4.Dataset(path) as ds:
        for name, variable in ds.variables.items():
            data = np.ascontiguousarray(variable[:])
            h = hashlib.sha256()
            h.update(str(data.dtype).encode())
            h.update(repr(data.shape).encode())
            h.update(data.tobytes())
            out[name] = h.hexdigest()
    return out


def check_initial_homogeneity(path: Path) -> dict[str, Any]:
    fields = ("T", "P", "PB", "QVAPOR", "QCLOUD", "QICE", "QSNOW")
    result: dict[str, Any] = {}
    with netCDF4.Dataset(path) as ds:
        for name in fields:
            if name not in ds.variables:
                continue
            values = np.asarray(ds.variables[name][0], dtype=np.float64)
            if values.ndim < 2:
                continue
            reference = values[..., :1, :1]
            delta = np.abs(values - reference)
            uniform = bool(np.allclose(values, reference, rtol=1e-7, atol=1e-12, equal_nan=True))
            result[name] = {"spatially_uniform": uniform,
                            "max_abs_horizontal_difference": float(np.nanmax(delta))}
            if not uniform:
                fail(f"{path}: expected horizontally uniform SCM initializer field {name}")
    if not all(result.get(name, {}).get("spatially_uniform", False)
               for name in ("T", "P", "PB", "QVAPOR")):
        fail(f"{path}: required initial pressure/temperature/vapor fields are missing or nonuniform")
    return result


def copy_initial_state(source: Path, target: Path, option: int) -> None:
    shutil.copy2(source, target)
    with netCDF4.Dataset(target, "r+") as ds:
        ds.setncattr("RA_LW_PHYSICS", option)
        ds.setncattr("RA_SW_PHYSICS", option)


def parse_times(ds: netCDF4.Dataset) -> list[str]:
    if "Times" not in ds.variables:
        fail("history file lacks Times")
    result = []
    for row in ds.variables["Times"][:]:
        if isinstance(row[0], (bytes, np.bytes_)):
            result.append(b"".join(row).decode("ascii").strip())
        else:
            result.append("".join(str(x) for x in row).strip())
    return result


def read_numeric(ds: netCDF4.Dataset, name: str, case: Path) -> np.ndarray:
    if name not in ds.variables:
        fail(f"{case}: history missing {name}")
    raw = ds.variables[name][:]
    if np.ma.getmaskarray(raw).any():
        fail(f"{case}: {name} has masked values")
    values = np.asarray(raw, dtype=np.float64)
    if not np.isfinite(values).all():
        fail(f"{case}: {name} has non-finite values")
    return values


def check_log(case: Path) -> dict[str, Any]:
    text = (case / "wrf.log").read_text(errors="replace")
    if SUCCESS_TOKEN not in text:
        fail(f"{case}: success marker absent")
    omissions = {phase: {"count": 0, "max_grid_path_g_m2": 0.0}
                 for phase in ("LW", "SW")}
    for match in OMITTED_RE.finditer(text):
        phase = match.group("phase")
        reason = int(match.group("reason"))
        path = float(match.group("path").replace("D", "E").replace("d", "e"))
        if reason != 6 or not np.isfinite(path) or path <= 0:
            fail(f"{case}: malformed clear-condensate diagnostic {match.group(0)}")
        omissions[phase]["count"] += 1
        omissions[phase]["max_grid_path_g_m2"] = max(
            omissions[phase]["max_grid_path_g_m2"], path)
    negative_lines = [line.strip() for line in text.splitlines()
                      if re.search(r"negative|non.?finite|not finite", line, re.I)]
    clipping_lines = [line.strip() for line in text.splitlines()
                      if re.search(r"clip(?:ped|ping)?|clamp(?:ed|ing)?", line, re.I)]
    invalid_input_lines = [line.strip() for line in text.splitlines()
                           if "RRTMGP_INPUT_" in line]
    return {"success_marker": True, "omitted_clear_condensate": omissions,
            "negative_or_nonfinite_log_lines": negative_lines,
            "clipping_log_lines": clipping_lines,
            "invalid_input_log_lines": invalid_input_lines}


def validate_case(case: Path, option: int) -> dict[str, Any]:
    proc = subprocess.run([sys.executable, str(VALIDATOR), str(case), "--expected-options", str(option)],
                          cwd=WRF_ROOT, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, check=False)
    if proc.returncode != 0:
        fail(f"validate_scm failed for {case} (exit {proc.returncode}):\n{proc.stdout[-4000:]}")
    report = json.loads(proc.stdout)
    key = str(case)
    if key not in report:
        fail(f"validate_scm output omitted {case}")
    return report[key]


def summarize_history(case: Path, option: int, duration_seconds: int,
                      first_call_grid: int | None = None) -> dict[str, Any]:
    files = sorted(case.glob("wrfout_d01_*"))
    if not files:
        fail(f"{case}: no wrfout_d01 history file")
    # The wider-grid mode remains strict: short-run state/tendency failures
    # make the case fail even when radiation flux outputs are finite.
    validation = validate_case(case, option)
    with netCDF4.Dataset(files[-1]) as ds:
        times = parse_times(ds)
        if len(times) < 2:
            fail(f"{case}: fewer than two history records")
        if int(ds.RA_LW_PHYSICS) != option or int(ds.RA_SW_PHYSICS) != option:
            fail(f"{case}: history radiation attrs do not match option {option}")
        variables = {}
        for name in REQUIRED_VARS:
            variables[name] = read_numeric(ds, name, case)
        sw_parts = variables["SWDDIR"] + variables["SWDDIF"]
        if not np.allclose(variables["SWDOWN"], sw_parts, rtol=2e-5, atol=2e-3):
            fail(f"{case}: SWDOWN != SWDDIR+SWDDIF")
        if not np.allclose(variables["RTHRATEN"], variables["RTHRATLW"] + variables["RTHRATSW"],
                           rtol=1e-5, atol=1e-9):
            fail(f"{case}: total radiative tendency does not equal LW+SW")
        if not np.any(variables["SWDOWN"] > 0):
            fail(f"{case}: no positive shortwave flux")
        area = np.asarray(ds.variables["AREA2D"][-1], dtype=np.float64) if "AREA2D" in ds.variables else None
        if area is None or not np.isfinite(area).all() or np.any(area <= 0):
            fail(f"{case}: missing/non-finite positive AREA2D weights")
        area2 = np.broadcast_to(area, variables["SWDOWN"].shape[1:])
        spatial_flux = {}
        for name in ("SWDOWN", "GLW", "SWDNT", "LWUPT"):
            sample = variables[name][1:]
            weights = np.broadcast_to(area2, sample.shape[1:])
            spatial_means = np.sum(sample * weights[None, ...], axis=tuple(range(1, sample.ndim))) / np.sum(weights)
            spatial_flux[name] = {
                "area_weighted_post_initial_sample_mean_w_m2": float(np.mean(spatial_means)),
                "area_weighted_endpoint_w_m2": float(spatial_means[-1]),
            }
        integrated = {}
        for name in ("ACSWDNB", "ACLWDNB"):
            array = variables[name]
            endpoint = array[-1] - array[0]
            weights = np.broadcast_to(area2, endpoint.shape)
            energy = float(np.sum(endpoint * weights) / np.sum(weights))
            integrated[name] = {"initial_mean_j_m2": float(np.sum(array[0] * weights) / np.sum(weights)),
                                "endpoint_minus_initial_mean_j_m2": energy,
                                "run_mean_w_m2": energy / duration_seconds}
        spatial_ensemble = None
        if first_call_grid is not None:
            ncolumns = first_call_grid * first_call_grid
            if area.size != ncolumns:
                fail(f"{case}: expected {ncolumns} area cells, found {area.size}")
            spatial_ensemble = {}
            for name in ("SWDOWN", "GLW", "SWDNT", "LWUPT"):
                field = variables[name][1]
                values = field.reshape(-1)
                weights = area.reshape(-1)
                mean = float(np.sum(values * weights) / np.sum(weights))
                variance = float(np.sum(weights * (values - mean) ** 2) / np.sum(weights))
                n_eff = float(np.sum(weights) ** 2 / np.sum(weights ** 2))
                spatial_ensemble[name] = {
                    "first_positive_record_area_weighted_mean_w_m2": mean,
                    "population_variance_w2_m4": variance,
                    "population_stddev_w_m2": float(np.sqrt(max(variance, 0.0))),
                    "weighted_standard_error_w_m2": float(np.sqrt(max(variance, 0.0) / n_eff)),
                    "min_w_m2": float(values.min()), "max_w_m2": float(values.max()),
                    "sample_count": int(values.size),
                }
            if "CLDFRA" in ds.variables:
                cf = read_numeric(ds, "CLDFRA", case)[1]
                spatial_ensemble["cloud_fraction_first_positive_record"] = {
                    "min": float(cf.min()), "max": float(cf.max()),
                    "spatially_uniform": bool(np.allclose(cf, cf.reshape(-1)[0], rtol=0.0, atol=1.0e-7)),
                }
        time_strings = times
        return {"status": "PASS", "radiation_option": option,
                "history_files": [str(path) for path in files], "history_time_count": len(times),
                "times": time_strings, "validator": validation,
                "area_m2_min": float(area.min()), "area_m2_max": float(area.max()),
                "area_weighted_fluxes": spatial_flux, "accumulated_surface_energy": integrated,
                "first_call_grid_spatial_sample": spatial_ensemble}


def environment_record(wrf_exe: Path, ideal_exe: Path, env: dict[str, str]) -> dict[str, Any]:
    version = subprocess.run(["gfortran", "--version"], text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, check=False).stdout.splitlines()
    config_path = WRF_ROOT / "configure.wrf"
    compiler_settings: dict[str, str] = {}
    if config_path.exists():
        for line in config_path.read_text(errors="replace").splitlines():
            if re.match(r"^(SFC|SCC|DM_FC|DM_CC|FC|CC|NETCDF|WRFIO_NCD_LARGE_FILE_SUPPORT)\s*=", line):
                key, value = line.split("=", 1)
                compiler_settings[key.strip()] = value.strip()
    git_head = subprocess.run(["git", "-C", str(CHECKOUT_ROOT), "rev-parse", "HEAD"],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                              check=False).stdout.strip()
    git_status = subprocess.run(["git", "-C", str(CHECKOUT_ROOT), "status", "--short",
                                 "--untracked-files=no"],
                                text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                check=False).stdout.splitlines()
    runner = Path(__file__).resolve()
    analyzer = CHECKOUT_ROOT / "tools/analyze_radiation_comparison.py"
    return {"wrf_root": str(WRF_ROOT), "checkout_root": str(CHECKOUT_ROOT),
            "git_head": git_head or "unavailable", "git_status_short": git_status,
            "runner_sha256": sha256(runner),
            "analyzer_sha256": sha256(analyzer) if analyzer.is_file() else None,
            "wrf_executable": str(wrf_exe),
            "wrf_executable_sha256": sha256(wrf_exe), "wrf_executable_size": wrf_exe.stat().st_size,
            "ideal_executable": str(ideal_exe), "ideal_executable_sha256": sha256(ideal_exe),
            "gfortran_version": version[0] if version else "unavailable",
            "configure_wrf_settings": compiler_settings,
            "environment": {key: env.get(key) for key in ("NETCDF", "JASPERLIB", "JASPERINC", "LD_LIBRARY_PATH", "OMP_NUM_THREADS", "WRF_RRTMGP_CAPTURE_DIR", "WRF_RRTMGP_CAPTURE_CALL")}}


def scenarios() -> list[dict[str, Any]]:
    return [
        {"name": "mp2-control", "mp_physics": 2, "overlap": 2, "species": None},
        {"name": "mp2-clear-sky-overlap0", "mp_physics": 2, "overlap": 0, "species": None},
        {"name": "mp4-mixed", "mp_physics": 4, "overlap": 2, "species": "mixed"},
        {"name": "mp4-liquid-only", "mp_physics": 4, "overlap": 2, "species": "liquid-only"},
        {"name": "mp4-ice-only", "mp_physics": 4, "overlap": 2, "species": "ice-only"},
        {"name": "mp4-snow-only", "mp_physics": 4, "overlap": 2, "species": "snow-only"},
        {"name": "mp5-mixed", "mp_physics": 5, "overlap": 2, "species": "mixed"},
    ]


def run_scenario(root: Path, spec: dict[str, Any], minutes: int, ideal_exe: Path,
                 wrf_exe: Path, env: dict[str, str], first_call_grid: int | None = None) -> dict[str, Any]:
    base = root / spec["name"]
    init = base / "initial"
    run_minutes, run_seconds = (divmod(10, 60) if first_call_grid is not None else (minutes, 0))
    init_namelist = configured_namelist(spec["mp_physics"], 37, spec["overlap"],
                                        run_minutes, first_call_grid)
    if run_seconds:
        init_namelist = set_clock(init_namelist, run_minutes, run_seconds)
    create_case(init, init_namelist)
    ideal = run_logged(ideal_exe, init, "ideal.log", env)
    if ideal["returncode"] != 0 or not (init / "wrfinput_d01").is_file():
        fail(f"{init}: ideal.exe failed; see {ideal['log']}")
    fixture = apply_fixture(init / "wrfinput_d01", spec["mp_physics"], spec["species"])
    source_hashes = variable_hashes(init / "wrfinput_d01")
    source_file_hash = sha256(init / "wrfinput_d01")
    forcing_hashes = {name: sha256(init / name)
                      for name in ("input_sounding", "input_soil", "force_ideal.nc")}
    initial_homogeneity = check_initial_homogeneity(init / "wrfinput_d01")

    pair: dict[str, Any] = {**spec, "fixture": fixture,
                            "forcing_input_sha256": forcing_hashes,
                            "initialization": {"case": str(init), "case_dir_relative": str(init.relative_to(root)), "ideal": ideal,
                                               "wrfinput_file_sha256": source_file_hash,
                                               "variable_sha256": source_hashes,
                                               "horizontal_homogeneity": initial_homogeneity},
                            "cases": {}}
    for option in OPTIONS:
        case = base / f"ra{option}"
        create_case(case, configured_namelist(spec["mp_physics"], option,
                                              spec["overlap"], run_minutes, first_call_grid))
        if run_seconds:
            case_namelist = set_clock((case / "namelist.input").read_text(), run_minutes, run_seconds)
            (case / "namelist.input").write_text(case_namelist, encoding="utf-8")
        copy_initial_state(init / "wrfinput_d01", case / "wrfinput_d01", option)
        if {name: sha256(case / name) for name in forcing_hashes} != forcing_hashes:
            fail(f"{case}: sounding/soil/forcing files differ from shared initializer")
        shutil.copy2(init / "ideal.log", case / "ideal.log")
        case_hashes = variable_hashes(case / "wrfinput_d01")
        if case_hashes != source_hashes:
            fail(f"{case}: copied wrfinput variable arrays differ from shared initializer")
        wrf = run_logged(wrf_exe, case, "wrf.log", env)
        if wrf["returncode"] != 0:
            fail(f"{case}: wrf.exe returned {wrf['returncode']}; see {wrf['log']}")
        logs = check_log(case)
        duration_seconds = 10 if first_call_grid is not None else minutes * 60
        validation = summarize_history(case, option, duration_seconds, first_call_grid)
        pair["cases"][str(option)] = {
            "case": str(case), "case_dir_relative": str(case.relative_to(root)),
            "option": option, "namelist_sha256": sha256(case / "namelist.input"),
            "wrfinput_file_sha256": sha256(case / "wrfinput_d01"),
            "wrfinput_variable_sha256": case_hashes, "initial_arrays_equal": True,
            "wrf": wrf, "diagnostics": logs, "analysis": validation,
        }
    left, right = (pair["cases"][str(option)] for option in OPTIONS)
    if left["analysis"]["times"] != right["analysis"]["times"]:
        fail(f"{base}: 4/4 and 37/37 history timestamps differ")
    pair["paired_initial_arrays_equal"] = (left["wrfinput_variable_sha256"] == right["wrfinput_variable_sha256"])
    if not pair["paired_initial_arrays_equal"]:
        fail(f"{base}: initial variable arrays mismatch after copying")
    normalized = []
    for option in OPTIONS:
        text = (base / f"ra{option}" / "namelist.input").read_text(encoding="utf-8")
        for key in ("ra_lw_physics", "ra_sw_physics"):
            text = re.sub(rf"(?im)^(\s*{key}\s*=\s*)\d+\s*,", rf"\g<1>OPTION,", text)
        normalized.append(text)
    pair["namelist_equal_except_radiation_options"] = normalized[0] == normalized[1]
    if not pair["namelist_equal_except_radiation_options"]:
        fail(f"{base}: paired namelists differ outside ra_lw_physics/ra_sw_physics")
    if first_call_grid is not None:
        cldfra = []
        for option in OPTIONS:
            case = Path(pair["cases"][str(option)]["case"])
            output = sorted(case.glob("wrfout_d01_*"))[-1]
            with netCDF4.Dataset(output) as ds:
                cldfra.append(np.asarray(ds.variables["CLDFRA"][1], dtype=np.float64)
                              if "CLDFRA" in ds.variables else None)
        if cldfra[0] is not None and cldfra[1] is not None:
            pair["first_record_cloud_fraction"] = {
                "exactly_equal_between_options": bool(np.array_equal(cldfra[0], cldfra[1])),
                "max_abs_37_minus_4": float(np.max(np.abs(cldfra[1] - cldfra[0]))),
                "ra4_min": float(cldfra[0].min()), "ra4_max": float(cldfra[0].max()),
                "ra37_min": float(cldfra[1].min()), "ra37_max": float(cldfra[1].max()),
            }
        else:
            pair["first_record_cloud_fraction"] = {"available": False}
    pair["output_differences"] = {}
    for var in ("SWDOWN", "GLW", "SWDNT", "LWUPT"):
        a = left["analysis"]["area_weighted_fluxes"][var]
        b = right["analysis"]["area_weighted_fluxes"][var]
        pair["output_differences"][var] = {
            "endpoint_37_minus_4_w_m2": b["area_weighted_endpoint_w_m2"] - a["area_weighted_endpoint_w_m2"],
            "post_initial_mean_37_minus_4_w_m2": b["area_weighted_post_initial_sample_mean_w_m2"] - a["area_weighted_post_initial_sample_mean_w_m2"],
        }
    for variable in ("ACSWDNB", "ACLWDNB"):
        a = left["analysis"]["accumulated_surface_energy"][variable]["run_mean_w_m2"]
        b = right["analysis"]["accumulated_surface_energy"][variable]["run_mean_w_m2"]
        pair["output_differences"][variable + "_run_mean_w_m2"] = b - a
    return pair


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-directory", type=Path, required=True,
                        help="new nonexistent root directory for all paired SCM outputs")
    parser.add_argument("--run-minutes", type=int, default=5)
    parser.add_argument("--first-call-grid", type=int, default=None,
                        help="strict 10-second SCM diagnostic probe on an N by N grid (fails on non-finite state/tendencies)")
    parser.add_argument("--scenario", action="append", choices=[s["name"] for s in scenarios()],
                        help="run only named scenario(s); default runs all seven")
    args = parser.parse_args()
    if args.run_minutes < 1:
        parser.error("--run-minutes must be positive")
    if args.first_call_grid is not None and args.first_call_grid < 2:
        parser.error("--first-call-grid must be at least 2")
    root = args.output_directory.expanduser().resolve()
    if root.exists():
        parser.error(f"refusing existing output directory: {root}")
    if not root.parent.is_dir():
        parser.error(f"output parent directory must already exist: {root.parent}")
    ideal_exe, wrf_exe = WRF_ROOT / "main/ideal.exe", WRF_ROOT / "main/wrf.exe"
    for exe in (ideal_exe, wrf_exe):
        if not exe.is_file() or not exe.stat().st_mode & 0o111:
            parser.error(f"missing executable {exe}")
    for path in (TEMPLATE, VALIDATOR, SCM_DIR / "radiation_iofields.txt",
                 INPUT_DIR / "input_sounding", INPUT_DIR / "input_soil", INPUT_DIR / "force_ideal.nc"):
        if not path.is_file():
            parser.error(f"missing required SCM input {path}")
    # The WRF executable is linked to the workspace-local netCDF Fortran runtime.
    env = os.environ.copy()
    # Capture files are disabled for these forecast comparisons even if the
    # invoking shell happens to carry a replay/capture setting.
    env.pop("WRF_RRTMGP_CAPTURE_DIR", None)
    env.pop("WRF_RRTMGP_CAPTURE_CALL", None)
    local_netcdf = REPO_ROOT / "deps/netcdf/lib"
    if local_netcdf.is_dir():
        env["LD_LIBRARY_PATH"] = str(local_netcdf) + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
    root.mkdir(parents=True)
    ensemble_mode = args.first_call_grid is not None
    if ensemble_mode:
        env["OMP_NUM_THREADS"] = "1"
        env["OPENBLAS_NUM_THREADS"] = "1"
    duration_seconds = 10 if ensemble_mode else args.run_minutes * 60
    effective_minutes, effective_seconds = divmod(duration_seconds, 60)
    receipt = {"status": "RUNNING", "output_directory": str(root), "run_minutes": effective_minutes,
               "run_seconds": effective_seconds, "duration_seconds": duration_seconds,
               "history_interval_seconds": 10, "history_interval_minutes": 0,
               "ensemble_mode": ensemble_mode, "first_call_grid_width": args.first_call_grid,
               "first_call_grid_cells": (args.first_call_grid ** 2 if ensemble_mode else None),
               "ensemble_interpretation": ("one deterministic WRF grid-seeded spatial McICA realization; spatial columns are a diagnostic sample, not independent forecast ensemble members"
                                            if ensemble_mode else None),
               "weighting": {"spatial": "AREA2D area-weighted domain means",
                             "instantaneous": "post-initial history sample means; the t=0 zero-init record is excluded",
                             "integrated": "endpoint ACSWDNB/ACLWDNB area mean divided by run seconds"},
               "executable_environment": environment_record(wrf_exe, ideal_exe, env),
               "pairs": []}
    receipt_path = root / "receipt.json"
    try:
        selected_scenarios = set(args.scenario or [])
        for spec in scenarios():
            if selected_scenarios and spec["name"] not in selected_scenarios:
                continue
            print(f"Running {spec['name']} 4/4 and 37/37" +
                  (f" on {args.first_call_grid}x{args.first_call_grid} grid for 10 seconds" if ensemble_mode else ""), flush=True)
            pair = run_scenario(root, spec, args.run_minutes, ideal_exe, wrf_exe, env,
                                args.first_call_grid)
            receipt["pairs"].append(pair)
            receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        receipt["status"] = "PASS"
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path),
                          "pair_count": len(receipt["pairs"]),
                          "wrf_sha256": receipt["executable_environment"]["wrf_executable_sha256"]}, indent=2))
        return 0
    except (RuntimeError, OSError, subprocess.SubprocessError, AssertionError, ValueError, KeyError) as exc:
        receipt["status"] = "FAILED"
        receipt["failure"] = str(exc)
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"ERROR: {exc}; partial receipt: {receipt_path}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
