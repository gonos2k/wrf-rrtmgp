#!/usr/bin/env python3
"""Run isolated UDM/RRTMGP SCM pairs and exercise fail-closed UDM inputs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

import test_cloud_scm
import test_column_replay
import test_surface_scm
from compare_column_replay import compare, read_result

WRF_ROOT = test_surface_scm.WRF_ROOT
TEMPLATE = test_surface_scm.TEMPLATE
INPUT_DIR = test_surface_scm.INPUT_DIR
DATA_DIR = test_surface_scm.DATA_DIR
VALIDATOR = TEMPLATE.parent / "validate_scm.py"
SUCCESS = "SUCCESS COMPLETE WRF"
PHASES = {"L": (("QC", "SOURCE_QC"), "LWP"),
          "I": (("QI", "SOURCE_QI"), "IWP"),
          "R": (("QR", "SOURCE_QR"), "RWP"),
          "S": (("QS", "SOURCE_QS"), "SWP"),
          "G": (("QG", "SOURCE_QG"), None),
          "H": (("QH", "SOURCE_QH"), None)}
RAW_PHASE_NAMES = {"L": "LWP", "I": "IWP", "R": "RWP",
                   "S": "SWP", "G": "GWP", "H": "HWP"}
BACKGROUND_UM = {"REL": 2.49, "REI": 4.99, "RES": 9.99}
ACTIVE_OUTPUT_ROOT: Path | None = None


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def replace_assignment(text: str, key: str, value: str, *, required: bool = False,
                       group: str = "physics") -> str:
    pattern = rf"(?im)^(\s*{re.escape(key)}\s*=\s*)[^,\n]+,"
    text, count = re.subn(pattern, rf"\g<1>{value},", text, count=1)
    if count == 0 and required:
        fail(f"namelist template is missing {key}")
    if count == 0:
        start = text.lower().find(f"&{group.lower()}")
        end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", text[start:]) if start >= 0 else None
        if start < 0 or end_match is None:
            fail(f"could not locate &{group} namelist block")
        end = start + end_match.start()
        text = text[:end] + f"\n {key} = {value},\n" + text[end:]
    return text


def make_namelist(source: str, lw: int, sw: int, run_minutes: int,
                  use_mp_re: int = 1) -> str:
    text = test_column_replay.set_mp_physics(source, 27)
    text = replace_assignment(text, "ra_lw_physics", str(lw), required=True)
    text = replace_assignment(text, "ra_sw_physics", str(sw), required=True)
    text = replace_assignment(text, "use_mp_re", str(use_mp_re))
    text = test_column_replay.set_run_minutes(text, run_minutes)
    text = replace_assignment(text, "history_interval", "0", required=True)
    text = replace_assignment(text, "history_interval_s", "10", group="time_control")
    return text


def write_initial_udm_fixture(wrfinput: Path, mixed: bool) -> dict[str, Any]:
    """Seed explicit UDM species in one cold level of the generated SCM state."""
    with netCDF4.Dataset(wrfinput, "r+") as ds:
        for name in ("T", "P", "PB", "QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP", "QHAIL"):
            if name not in ds.variables:
                fail(f"{wrfinput}: missing UDM fixture variable {name}")
        theta = np.asarray(ds.variables["T"][0], dtype=np.float64)
        pressure = (np.asarray(ds.variables["P"][0], dtype=np.float64) +
                    np.asarray(ds.variables["PB"][0], dtype=np.float64))
        with np.errstate(invalid="ignore", divide="ignore", over="ignore"):
            temperature = (theta + 300.0) * np.power(pressure / 100000.0, 287.0 / 1004.0)
        candidates = [k for k in range(temperature.shape[0] - 1)
                      if np.isfinite(temperature[k]).all() and np.isfinite(pressure[k]).all()
                      and 240.0 <= float(np.mean(temperature[k])) < 260.0
                      and float(np.mean(pressure[k])) > 20000.0]
        if not candidates:
            fail(f"{wrfinput}: no cold interior level for UDM fixture")
        layer = min(candidates, key=lambda k: abs(float(np.mean(temperature[k])) - 250.0))
        amounts = ({"QCLOUD": 2.0e-5, "QRAIN": 1.0e-6, "QICE": 1.0e-5,
                    "QSNOW": 2.0e-5, "QGRAUP": 0.0, "QHAIL": 0.0} if mixed else
                   {name: 0.0 for name in ("QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP", "QHAIL")})
        for name, amount in amounts.items():
            values = np.asarray(ds.variables[name][:], dtype=np.float64)
            values[:] = 0.0
            values[0, layer, :, :] = amount
            ds.variables[name][:] = values
    return {"layer_index_zero_based": layer, "temperature_k_mean": float(np.mean(temperature[layer])),
            "pressure_pa_mean": float(np.mean(pressure[layer])),
            "species_kg_kg": amounts, "mixed": mixed}


def run_logged(exe: Path, case: Path, logfile: str,
               env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    if env is None:
        env = os.environ.copy()
        env.pop("WRF_RRTMGP_CAPTURE_DIR", None)
        env.pop("WRF_RRTMGP_CAPTURE_CALL", None)
    with (case / logfile).open("w", encoding="utf-8") as stream:
        return subprocess.run([str(exe)], cwd=case, env=env, stdout=stream,
                              stderr=subprocess.STDOUT, text=True, check=False)


def make_generated_seed(root: Path, tag: str, mixed: bool) -> tuple[Path, dict[str, Any]]:
    case = root / f"seed-{tag}"
    test_surface_scm.prepare_case(case, 0)
    base = test_cloud_scm.original_lsm2_namelist()
    (case / "namelist.input").write_text(make_namelist(base, 4, 4, 1))
    ideal = run_logged(WRF_ROOT / "main/ideal.exe", case, "ideal.log")
    if ideal.returncode != 0 or not (case / "wrfinput_d01").is_file():
        fail(f"{case}: ideal.exe failed; inspect ideal.log")
    fixture = write_initial_udm_fixture(case / "wrfinput_d01", mixed)
    return case, fixture


def seed_from_directory(path: Path, label: str) -> dict[str, Any]:
    if not (path / "wrfinput_d01").is_file():
        fail(f"{label} seed directory lacks wrfinput_d01: {path}")
    baseline_history = sorted(path.glob("wrfout_d01_*"))
    if baseline_history:
        with netCDF4.Dataset(baseline_history[-1]) as ds:
            if (int(ds.RA_LW_PHYSICS), int(ds.RA_SW_PHYSICS)) != (4, 4):
                fail(f"{path}: supplied historical baseline must be RRTMG4/4")
    return {"path": path, "wrfinput": path / "wrfinput_d01", "baseline_history": baseline_history}


def create_run_case(seed: dict[str, Any], case: Path, lw: int, sw: int,
                    run_minutes: int, capture_call: int | None) -> None:
    test_surface_scm.prepare_case(case, 0)
    source_namelist = (seed["path"] / "namelist.input").read_text()
    (case / "namelist.input").write_text(make_namelist(source_namelist, lw, sw, run_minutes))
    shutil.copy2(seed["wrfinput"], case / "wrfinput_d01")
    if capture_call is not None:
        (case / "capture").mkdir()


def history_files(case: Path) -> list[Path]:
    return sorted(case.glob("wrfout_d01_*"))


def validate_history(case: Path, expected_option: int) -> dict[str, Any]:
    log = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")
    if SUCCESS not in log:
        fail(f"{case}: WRF success marker missing")
    paths = history_files(case)
    if len(paths) != 1:
        fail(f"{case}: expected one history output, got {len(paths)}")
    run = subprocess.run([sys.executable, str(VALIDATOR), str(case), "--expected-options",
                          str(expected_option)], cwd=WRF_ROOT, stdout=subprocess.PIPE,
                         stderr=subprocess.STDOUT, text=True, check=False)
    if run.returncode != 0:
        fail(f"{case}: validate_scm failed ({run.returncode}): {run.stdout[-3000:]}")
    report = json.loads(run.stdout)[str(case)]
    with netCDF4.Dataset(paths[0]) as ds:
        times = np.asarray(ds.variables["Times"][:])
        rendered = [b"".join(row).decode("ascii") for row in times]
        parsed = [datetime.strptime(item, "%Y-%m-%d_%H:%M:%S") for item in rendered]
        if len(parsed) < 2:
            fail(f"{case}: expected at least two 10-second history records")
        deltas = [(right - left).total_seconds() for left, right in zip(parsed, parsed[1:])]
        if any(delta != 10.0 for delta in deltas):
            fail(f"{case}: history times are not 10 seconds apart: {deltas}")
        snapshot = {name: np.asarray(var[:]).copy() for name, var in ds.variables.items()}
    report["history_interval_seconds"] = 10
    report["time_deltas_seconds"] = deltas
    return {"report": report, "path": paths[0], "arrays": snapshot}


def assert_history_bytes_equal(left: dict[str, Any], right: dict[str, Any], label: str) -> dict[str, Any]:
    a = left.get("history_arrays", left.get("arrays"))
    b = right.get("history_arrays", right.get("arrays"))
    if a is None or b is None:
        fail(f"{label}: history arrays were not retained")
    common = sorted(a.keys() & b.keys())
    if not common:
        fail(f"{label}: no common history arrays")
    mismatches: list[str] = []
    for name in common:
        if a[name].shape != b[name].shape or a[name].dtype != b[name].dtype:
            mismatches.append(name)
        elif a[name].dtype.kind in "OUS":
            if not np.array_equal(a[name], b[name]):
                mismatches.append(name)
        elif a[name].tobytes() != b[name].tobytes():
            mismatches.append(name)
    if mismatches:
        fail(f"{label}: history arrays differ: {mismatches[:20]}")
    return {"identical_arrays": common, "count": len(common),
            "left_only": sorted(a.keys() - b.keys()), "right_only": sorted(b.keys() - a.keys())}


def validate_capture(case: Path, phase: str, call: int, reference_exe: Path,
                    expect_native_radius: bool = False) -> dict[str, Any]:
    capture = case / "capture"
    raw_phase, i, j, raw = test_column_replay.read_raw(capture / f"{phase.lower()}.raw")
    input_phase, nc, nl, overlap, seed, iceflag, inp = test_column_replay.read_input(
        capture / f"{phase.lower()}.input")
    if raw_phase != phase or input_phase != phase or nc != 1 or nl < 1:
        fail(f"{case}: invalid {phase} replay capture header")
    if "MP_PHYSICS" not in raw or int(round(float(raw["MP_PHYSICS"][0]))) != 27:
        fail(f"{case}: {phase} raw capture does not identify UDM mp_physics=27")
    for suffix in ("result",):
        if not (capture / f"{phase.lower()}.{suffix}").is_file():
            fail(f"{case}: missing captured {phase} {suffix}")
    nl_raw = len(raw.get("DP_HPA", []))
    if nl_raw == 0:
        fail(f"{case}: {phase} raw capture omitted DP_HPA")
    dry_mass, dry_mass_source = test_column_replay.dry_layer_mass_kg_m2(
        raw, nl_raw, require_native=True)
    adapter_nl = inp["PLAY"].shape[1]
    if adapter_nl > nl_raw:
        for path_name in ("LWP", "IWP", "SWP", "RWP"):
            if path_name in inp and np.any(inp[path_name][0, nl_raw:adapter_nl] != 0.0):
                fail(f"{case}: {phase} above-top {path_name} must be zero")
    phase_checks: dict[str, Any] = {}
    for phase_key, (q_names, radiation_name) in PHASES.items():
        raw_phase_name = RAW_PHASE_NAMES[phase_key]
        grid_name = f"{raw_phase_name}_GRID"
        rad_name = f"{raw_phase_name}_RADIATION"
        omitted_name = f"{raw_phase_name}_OMITTED"
        if grid_name not in raw or rad_name not in raw or omitted_name not in raw:
            fail(f"{case}: {phase} raw capture missing UDM phase records {grid_name}/{rad_name}/{omitted_name}")
        grid = raw[grid_name][:nl_raw]
        rad = raw[rad_name][:nl_raw]
        omitted = raw[omitted_name][:nl_raw]
        if not (np.isfinite(grid).all() and np.isfinite(rad).all() and np.isfinite(omitted).all()):
            fail(f"{case}: non-finite UDM {phase_key} path in {phase} capture")
        q_key = next((name for name in q_names if name in raw), None)
        mass_residual = None
        if q_key is not None and "GRAVITY" in raw:
            q = test_column_replay.corrected_hydrometeor(raw, q_key, raw_phase_name, nl_raw)
            cf = raw["CF"][:nl_raw]
            expected_grid = q * dry_mass * 1000.0
            test_column_replay.assert_close(grid, expected_grid,
                f"{case}: {phase} {phase_key} grid mass", rtol=3.e-6, atol=2.e-6)
            # Graupel is diagnosed in grid space and deliberately excluded from
            # RRTMGP cloud optics; unlike clear-CF omission, this applies at all CF.
            expected_omitted = (expected_grid if phase_key == "G" else
                                np.where(cf == 0.0, expected_grid, 0.0))
            test_column_replay.assert_close(omitted, expected_omitted,
                f"{case}: {phase} {phase_key} zero-CF omitted mass", rtol=3.e-6, atol=2.e-6)
            wet = cf > 0.0
            if phase_key == "G":
                test_column_replay.assert_close(rad, np.zeros_like(rad),
                    f"{case}: {phase} graupel excluded from radiation optics", rtol=0.0, atol=0.0)
            elif radiation_name is not None:
                if radiation_name not in inp:
                    fail(f"{case}: captured adapter input missing {radiation_name}")
                test_column_replay.assert_close(inp[radiation_name][0, :nl_raw][wet],
                    expected_grid[wet] / cf[wet], f"{case}: {phase} {phase_key} in-cloud path",
                    rtol=3.e-6, atol=2.e-6)
                test_column_replay.assert_close(rad, inp[radiation_name][0, :nl_raw],
                    f"{case}: {phase} {phase_key} prepared radiation path", rtol=0.0, atol=0.0)
            else:
                test_column_replay.assert_close(rad, np.where(wet, expected_grid / np.where(wet, cf, 1.), 0.),
                    f"{case}: {phase} {phase_key} diagnostic in-cloud path", rtol=3.e-6, atol=2.e-6)
            mass_residual = float(np.max(np.abs(grid - expected_grid), initial=0.0))
        phase_checks[phase_key] = {"grid_mass_max_abs_error": mass_residual,
                                   "grid_positive_layers": int(np.count_nonzero(grid > 0.0)),
                                   "omitted_positive_layers": int(np.count_nonzero(omitted > 0.0))}

    for name in ("REL", "REI", "RES"):
        if name not in inp:
            fail(f"{case}: {phase} adapter input missing {name}")
    radius_evidence: dict[str, Any] = {}
    if call == 2:
        for inp_name, source_names, q_names, bg in (
            ("REL", ("SOURCE_RE_CLOUD",), ("QC", "SOURCE_QC"), BACKGROUND_UM["REL"]),
            ("REI", ("SOURCE_RE_ICE",), ("QI", "SOURCE_QI"), BACKGROUND_UM["REI"]),
            ("RES", ("SOURCE_RE_SNOW",), ("QS", "SOURCE_QS"), BACKGROUND_UM["RES"]),
        ):
            source_name = next((name for name in source_names if name in raw), None)
            q_name = next((name for name in q_names if name in raw), None)
            if source_name is None or q_name is None:
                fail(f"{case}: second-call native radius evidence missing {source_names}/{q_names}")
            source_um = raw[source_name][:nl_raw] * 1.0e6
            active = raw[q_name][:nl_raw] > 0.0
            native = active & np.isfinite(source_um) & (np.abs(source_um - bg) > 1.e-5)
            if expect_native_radius and np.any(active) and not np.any(native):
                fail(f"{case}: second-call {inp_name} never contains a diagnosed native radius")
            if np.any(native):
                test_column_replay.assert_close(inp[inp_name][0, :nl_raw][native], source_um[native],
                    f"{case}: second-call native {inp_name} pass-through", rtol=5.e-7, atol=1.e-6)
            radius_evidence[inp_name] = {"diagnosed_layers": int(np.count_nonzero(native)),
                                         "max_um": float(np.max(source_um[native])) if np.any(native) else None}

    reference_output = capture / f"{phase.lower()}.reference.result"
    reference = subprocess.run([str(reference_exe), str(DATA_DIR),
                                str(capture / f"{phase.lower()}.input"), str(reference_output)],
                               cwd=case, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                               text=True, check=False)
    if reference.returncode != 0 or not reference_output.is_file():
        fail(f"{case}: independent {phase} reference failed: {reference.stdout[-2000:]}")
    replay = compare(read_result(capture / f"{phase.lower()}.result"), read_result(reference_output))
    if not replay.get("passed"):
        fail(f"{case}: independent {phase} replay mismatch {replay.get('failed_sections')}")
    return {"phase": phase, "call": call, "header": [nc, nl, overlap, seed, iceflag],
            "dry_layer_mass_source": dry_mass_source,
            "udm_paths": phase_checks, "native_radius_second_call": radius_evidence,
            "reference_sections_compared": replay["sections_compared"],
            "raw_column": {"i": i, "j": j}}


def run_capture_case(seed: dict[str, Any], case: Path, lw: int, sw: int,
                     run_minutes: int, call: int, reference_exe: Path,
                     expect_native_radius: bool) -> dict[str, Any]:
    create_run_case(seed, case, lw, sw, run_minutes, call)
    env = os.environ.copy()
    env["WRF_RRTMGP_CAPTURE_DIR"] = str(case / "capture")
    env["WRF_RRTMGP_CAPTURE_CALL"] = str(call)
    run = run_logged(WRF_ROOT / "main/wrf.exe", case, "wrf.log", env)
    if run.returncode != 0:
        fail(f"{case}: wrf.exe returned {run.returncode}; inspect wrf.log")
    history = validate_history(case, 37)
    capture = {phase: validate_capture(case, phase, call, reference_exe, expect_native_radius)
               for phase in ("LW", "SW")}
    return {"case": str(case), "history": history["report"], "history_arrays": history["arrays"],
            "history_path": history["path"], "capture": capture,
            "wrfinput_sha256": sha256(case / "wrfinput_d01")}


def run_plain_case(seed: dict[str, Any], case: Path, option: int,
                   run_minutes: int) -> dict[str, Any]:
    create_run_case(seed, case, option, option, run_minutes, None)
    run = run_logged(WRF_ROOT / "main/wrf.exe", case, "wrf.log")
    if run.returncode != 0:
        fail(f"{case}: wrf.exe returned {run.returncode}; inspect wrf.log")
    history = validate_history(case, option)
    return {"case": str(case), "history": history["report"],
            "wrfinput_sha256": sha256(case / "wrfinput_d01"), "history_arrays": history["arrays"],
            "history_path": history["path"]}


def run_gate(seed: dict[str, Any], root: Path, label: str, lw: int, sw: int,
             mp: int, use_mp_re: int, diagnostic: str) -> dict[str, Any]:
    case = root / f"gate-{label}"
    test_surface_scm.prepare_case(case, 0)
    text = make_namelist((seed["path"] / "namelist.input").read_text(), lw, sw, 1, use_mp_re)
    text = test_column_replay.set_mp_physics(text, mp)
    (case / "namelist.input").write_text(text)
    shutil.copy2(seed["wrfinput"], case / "wrfinput_d01")
    run = run_logged(WRF_ROOT / "main/wrf.exe", case, "wrf.log")
    log = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")
    if diagnostic not in log or SUCCESS in log:
        fail(f"{case}: expected fail-closed diagnostic {diagnostic!r}; return={run.returncode}")
    return {"case": str(case), "diagnostic": diagnostic, "returncode": run.returncode,
            "rejected": True}


def run_hail_case(seed: dict[str, Any], root: Path) -> dict[str, Any]:
    case = root / "hail-positive-rejected"
    test_surface_scm.prepare_case(case, 0)
    (case / "namelist.input").write_text(make_namelist((seed["path"] / "namelist.input").read_text(), 37, 37, 1))
    shutil.copy2(seed["wrfinput"], case / "wrfinput_d01")
    with netCDF4.Dataset(case / "wrfinput_d01", "r+") as ds:
        qh = ds.variables.get("QHAIL")
        qc = ds.variables.get("QCLOUD")
        if qh is None or qc is None:
            fail(f"{case}: QHAIL/QCLOUD fixture fields missing")
        qcv = np.asarray(qc[:], dtype=np.float64)
        active = np.argwhere(qcv[0] > 0.0)
        if active.size == 0:
            fail(f"{case}: mixed seed has no cloud cell for hail fixture")
        k, j, i = active[0]
        values = np.asarray(qh[:], dtype=np.float64)
        values[0, k, j, i] = 1.e-8
        qh[:] = values
    run = run_logged(WRF_ROOT / "main/wrf.exe", case, "wrf.log")
    log = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")
    expected = "RRTMGP_INPUT_UDM_HAIL_OPTICS_UNSUPPORTED"
    if expected not in log or SUCCESS in log:
        fail(f"{case}: positive hail did not fail closed with {expected}; return={run.returncode}")
    return {"case": str(case), "diagnostic": expected, "fixture": {"i": int(i), "j": int(j),
            "k_zero_based": int(k), "q_hail_kg_kg": 1.e-8}, "rejected": True}


def run_graupel_case(seed: dict[str, Any], root: Path) -> dict[str, Any]:
    case = root / "graupel-positive-diagnostic"
    test_surface_scm.prepare_case(case, 0)
    (case / "namelist.input").write_text(make_namelist((seed["path"] / "namelist.input").read_text(), 37, 37, 1))
    shutil.copy2(seed["wrfinput"], case / "wrfinput_d01")
    with netCDF4.Dataset(case / "wrfinput_d01", "r+") as ds:
        qg = ds.variables.get("QGRAUP")
        qc = ds.variables.get("QCLOUD")
        if qg is None or qc is None:
            fail(f"{case}: QGRAUP/QCLOUD fixture fields missing")
        qcv = np.asarray(qc[:], dtype=np.float64)
        active = np.argwhere(qcv[0] > 0.0)
        if active.size == 0:
            fail(f"{case}: mixed seed has no cloud cell for graupel fixture")
        k, j, i = active[0]
        values = np.asarray(qg[:], dtype=np.float64)
        values[0, k, j, i] = 1.e-8
        qg[:] = values
    run = run_logged(WRF_ROOT / "main/wrf.exe", case, "wrf.log")
    log = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")
    token = "RRTMGP_UDM_GRAUPEL_OPTICS_OMITTED"
    if run.returncode != 0 or SUCCESS not in log or token not in log:
        fail(f"{case}: positive graupel must warn and complete; return={run.returncode}")
    return {"case": str(case), "diagnostic": token,
            "fixture": {"i": int(i), "j": int(j), "k_zero_based": int(k),
                        "q_graupel_kg_kg": 1.e-8}, "warning_seen": True}


def run_negative_graupel_case(seed: dict[str, Any], root: Path) -> dict[str, Any]:
    """Require a negative registered QG value to reach the builder and abort WRF."""
    case = root / "negative-graupel-rejected"
    test_surface_scm.prepare_case(case, 0)
    (case / "namelist.input").write_text(
        make_namelist((seed["path"] / "namelist.input").read_text(), 37, 37, 1))
    shutil.copy2(seed["wrfinput"], case / "wrfinput_d01")
    with netCDF4.Dataset(case / "wrfinput_d01", "r+") as ds:
        qg = ds.variables.get("QGRAUP")
        qc = ds.variables.get("QCLOUD")
        if qg is None or qc is None:
            fail(f"{case}: QGRAUP/QCLOUD fixture fields missing")
        qcv = np.asarray(qc[:], dtype=np.float64)
        active = np.argwhere(qcv[0] > 0.0)
        if active.size == 0:
            fail(f"{case}: mixed seed has no cloud cell for negative-graupel fixture")
        k, j, i = active[0]
        values = np.asarray(qg[:], dtype=np.float64)
        values[0, k, j, i] = -1.e-8
        qg[:] = values
    run = run_logged(WRF_ROOT / "main/wrf.exe", case, "wrf.log")
    log = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")
    # This token is emitted by rrtmgp_build_udm_inputs' nonnegative-QG check.
    # Checking WRF's fatal banner prevents a merely logged warning passing;
    # checking for no normal completion marker ensures it aborted the run.
    diagnostic = "RRTMGP_INPUT_UDM_QG_NEGATIVE"
    if diagnostic not in log or "FATAL CALLED" not in log or SUCCESS in log:
        fail(f"{case}: negative QG was not rejected by the builder; return={run.returncode}")
    return {"case": str(case), "diagnostic": diagnostic, "returncode": run.returncode,
            "fixture": {"i": int(i), "j": int(j), "k_zero_based": int(k),
                        "q_graupel_kg_kg": -1.e-8}, "fatal_seen": True, "success_marker": False}


def compare_historical_baseline(run: dict[str, Any], baseline: dict[str, Any], label: str) -> dict[str, Any]:
    if not baseline["baseline_history"]:
        fail(f"{baseline['path']}: no historical 4/4 output to compare")
    seed_hash = sha256(baseline["wrfinput"])
    if run["wrfinput_sha256"] != seed_hash:
        fail(f"{label}: run wrfinput differs from supplied historical baseline")
    path = baseline["baseline_history"][-1]
    with netCDF4.Dataset(path) as ds:
        base = {name: np.asarray(var[:]).copy() for name, var in ds.variables.items()}
        if (int(ds.RA_LW_PHYSICS), int(ds.RA_SW_PHYSICS)) != (4, 4):
            fail(f"{path}: historical comparison baseline is not 4/4")
    current = run["history_arrays"]
    common = sorted(base.keys() & current.keys())
    diffs = []
    for name in common:
        if base[name].shape != current[name].shape or base[name].dtype != current[name].dtype:
            diffs.append(name)
        elif base[name].dtype.kind in "OUS":
            if not np.array_equal(base[name], current[name]):
                diffs.append(name)
        elif base[name].tobytes() != current[name].tobytes():
            diffs.append(name)
    if diffs:
        fail(f"{label}: RRTMG4 historical baseline differs in arrays {diffs[:20]}")
    return {"status": "PASS_BITWISE", "arrays_compared": len(common),
            "history_file": str(path), "wrfinput_sha256": seed_hash}


def main() -> int:
    global ACTIVE_OUTPUT_ROOT
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output_directory", type=Path, help="new isolated output directory")
    parser.add_argument("--reference-executable", type=Path, required=True,
                        help="independent reference_column built by the standalone CMake target")
    parser.add_argument("--baseline-control", type=Path,
                        help="optional pre-change 4/4 control SCM directory")
    parser.add_argument("--baseline-mixed", type=Path,
                        help="optional pre-change 4/4 mixed UDM SCM directory")
    parser.add_argument("--run-minutes", type=int, default=1)
    args = parser.parse_args()
    root = args.output_directory.expanduser().resolve()
    reference_exe = args.reference_executable.expanduser().resolve()
    if root.exists():
        parser.error(f"refusing existing output directory {root}")
    if not root.parent.is_dir():
        parser.error(f"output parent does not exist: {root.parent}")
    if args.run_minutes < 1:
        parser.error("--run-minutes must be positive")
    for exe in (WRF_ROOT / "main/ideal.exe", WRF_ROOT / "main/wrf.exe", reference_exe):
        if not exe.is_file() or not exe.stat().st_mode & 0o111:
            parser.error(f"missing executable {exe}")
    for required in (TEMPLATE, INPUT_DIR / "input_sounding", INPUT_DIR / "input_soil",
                     INPUT_DIR / "force_ideal.nc", WRF_ROOT / "test/rrtmgp/radiation_iofields.txt",
                     VALIDATOR, DATA_DIR / "rrtmgp-gas-lw-g128.nc",
                     DATA_DIR / "rrtmgp-gas-sw-g112.nc"):
        if not required.is_file():
            parser.error(f"missing SCM input {required}")
    root.mkdir()
    ACTIVE_OUTPUT_ROOT = root

    if args.baseline_control:
        control = seed_from_directory(args.baseline_control.expanduser().resolve(), "control")
        control_fixture: dict[str, Any] = {"source": "external-baseline"}
    else:
        control_path, control_fixture = make_generated_seed(root, "control", mixed=False)
        control = {"path": control_path, "wrfinput": control_path / "wrfinput_d01",
                   "baseline_history": []}
    if args.baseline_mixed:
        mixed = seed_from_directory(args.baseline_mixed.expanduser().resolve(), "mixed")
        mixed_fixture: dict[str, Any] = {"source": "external-baseline"}
    else:
        mixed_path, mixed_fixture = make_generated_seed(root, "mixed", mixed=True)
        mixed = {"path": mixed_path, "wrfinput": mixed_path / "wrfinput_d01",
                 "baseline_history": []}

    summary: dict[str, Any] = {"status": "FAIL", "duration_minutes": args.run_minutes,
        "source_states": {"control": {"wrfinput_sha256": sha256(control["wrfinput"]), "fixture": control_fixture},
                          "mixed": {"wrfinput_sha256": sha256(mixed["wrfinput"]), "fixture": mixed_fixture}},
        "pairs": {}, "gates": {}, "hail": {}, "graupel": {}, "negative_graupel": {}}

    for tag, seed in (("control", control), ("mixed", mixed)):
        pair_root = root / tag
        pair_root.mkdir()
        ra4 = run_plain_case(seed, pair_root / "ra4", 4, args.run_minutes)
        ra4_repeat = run_plain_case(seed, pair_root / "ra4-repeat", 4, args.run_minutes)
        deterministic = assert_history_bytes_equal(ra4, ra4_repeat, f"{tag} option4 repeat determinism")
        ra37_first = run_capture_case(seed, pair_root / "ra37-call1", 37, 37,
                                      args.run_minutes, 1, reference_exe, tag == "mixed")
        ra37_second = run_capture_case(seed, pair_root / "ra37-call2", 37, 37,
                                       args.run_minutes, 2, reference_exe, tag == "mixed")
        if ra4["wrfinput_sha256"] != ra37_first["wrfinput_sha256"] or \
           ra4["wrfinput_sha256"] != ra37_second["wrfinput_sha256"]:
            fail(f"{tag}: paired 4/37 runs did not use byte-identical initial states")
        ra37_repeat_equal = assert_history_bytes_equal(ra37_first, ra37_second,
                                                       f"{tag} RRTMGP capture-call repeat")
        baseline_arg = args.baseline_control if tag == "control" else args.baseline_mixed
        baseline_status = (compare_historical_baseline(ra4, seed, f"{tag} historical 4")
                           if baseline_arg else {"status": "NOT_CHECKED_NO_HISTORICAL_BASELINE"})
        summary["pairs"][tag] = {"initial_wrfinput_sha256": ra4["wrfinput_sha256"],
            "ra4": {"case": ra4["case"], "history": ra4["history"]},
            "ra4_repeat_arrays": deterministic, "ra37_call1": ra37_first,
            "ra37_call2": ra37_second, "ra37_capture_repeat_arrays": ra37_repeat_equal,
            "historical_option4_bitwise": baseline_status}

    summary["gates"] = {
        "wrong_microphysics": run_gate(mixed, root, "mp4-rejected", 37, 37, 4, 1,
                                        "RRTMGP37 requires mp_physics=27 (UDM)"),
        "mixed_radiation": run_gate(mixed, root, "mixed-radiation-rejected", 37, 4, 27, 1,
                                     "RRTMGP37 requires paired ra_lw_physics=37 and ra_sw_physics=37"),
        "native_radii_disabled": run_gate(mixed, root, "use-mp-re0-rejected", 37, 37, 27, 0,
                                           "RRTMGP37 UDM requires use_mp_re=1 for native effective radii"),
    }
    summary["hail"] = run_hail_case(mixed, root)
    summary["graupel"] = run_graupel_case(mixed, root)
    summary["negative_graupel"] = run_negative_graupel_case(mixed, root)
    summary["status"] = "PASS_RUNTIME; HISTORICAL_4_BASELINE_OPTIONAL"
    rendered = json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    (root / "udm-scm-result.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        if ACTIVE_OUTPUT_ROOT is not None and ACTIVE_OUTPUT_ROOT.is_dir():
            failure = {"status": "FAIL", "error": str(exc)}
            (ACTIVE_OUTPUT_ROOT / "udm-scm-result.json").write_text(
                json.dumps(failure, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
