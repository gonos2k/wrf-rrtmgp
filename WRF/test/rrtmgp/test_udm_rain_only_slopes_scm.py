#!/usr/bin/env python3
"""Six-case SCM contract for the rain-only UDM slope initialization fix.

This runs cold/warm 37/37 cases with the existing dry-DEND gate off/on and
ordinary 4/4 controls. It checks 37 off/on passivity, compares new 37 outputs
descriptively with archived parents, and strictly compares both 4/4 outputs
with archived controls. It also validates the existing opt-in DEND and native
radius captures. This is a scoped runtime contract, not precipitation
accuracy or general physical validation. A fresh candidate build receipt is
mandatory; the parent binary cannot stand in for it. No ideal.exe or standalone
RTE calls.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import struct
import subprocess
import sys
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

import test_surface_scm
import test_udm_scm


HERE = Path(__file__).resolve().parent
SUCCESS = "SUCCESS COMPLETE WRF"
ENTRY_GATE = "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY"
RADIUS_GATE = "WRF_RRTMGP_CAPTURE_UDM_RADII"
CAPTURE_DIR = "WRF_RRTMGP_CAPTURE_DIR"
CAPTURE_CALL = "WRF_RRTMGP_CAPTURE_CALL"
ENV_PREFIX = "WRF_RRTMGP_"


class CheckFailure(RuntimeError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise CheckFailure(message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    temp = Path(temp_name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            json.dump(value, stream, indent=2, sort_keys=True, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp.unlink(missing_ok=True)


def json_value(value: Any) -> Any:
    if isinstance(value, np.ndarray):
        return value.tolist()
    if isinstance(value, np.generic):
        return value.item()
    if isinstance(value, bytes):
        return {"bytes_hex": value.hex()}
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return str(value)


def file_pin(path: Path) -> dict[str, Any]:
    require(path.is_file(), f"required file is missing: {path}")
    return {"path": str(path.resolve()), "size_bytes": path.stat().st_size,
            "sha256": sha256(path)}


def tree_pins(root: Path) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for path in sorted(root.iterdir()):
        if path.is_file():
            item: dict[str, Any] = {"size_bytes": path.stat().st_size, "sha256": sha256(path)}
            if path.is_symlink():
                item["symlink_text"] = os.readlink(path)
            result[path.name] = item
    return result


def source_and_runtime_pins(wrf_root: Path, build_receipt: dict[str, Any]) -> dict[str, Any]:
    repo = wrf_root.parent
    authoring_wrf = HERE.parents[1]
    paired_sources = {
        "module_microphysics_driver.F": authoring_wrf / "phys/module_microphysics_driver.F",
        "module_mp_udm.F": authoring_wrf / "phys/module_mp_udm.F",
        "module_ra_rrtmgp_trace.F": authoring_wrf / "phys/module_ra_rrtmgp_trace.F",
    }
    runtime_sources = {name: wrf_root / "phys" / name for name in paired_sources}
    for name, author_path in paired_sources.items():
        require(sha256(author_path) == sha256(runtime_sources[name]),
                f"authoring/runtime source mismatch for compiled {name}")
    expected_candidate = {
        "module_mp_udm.F": ("18bac4328061b828c1a57fcbead77986eb71bf5b6a56985fbed0672647bc7d4d", 193968),
        "module_microphysics_driver.F": ("7e15f93341b1fa079136aa60b2f2061c6e7844f107446ae8e7951edff00820fb", 198427),
        "module_ra_rrtmgp_trace.F": ("c08a1cae7a93f85a08ed59042aa1b98dc1ef6b42d33c6f344b93a9eca9d652e9", 41541),
    }
    for name, (expected_sha, expected_size) in expected_candidate.items():
        candidate_source = runtime_sources[name]
        require(candidate_source.stat().st_size == expected_size and sha256(candidate_source) == expected_sha,
                f"candidate source pin mismatch for {name}")
    source_paths = [
        wrf_root / "phys/module_microphysics_driver.F",
        runtime_sources["module_ra_rrtmgp_trace.F"],
        wrf_root / "phys/module_mp_udm.F",
        wrf_root / "Registry/Registry.EM_COMMON",
        wrf_root / "configure.wrf",
        wrf_root / "test/rrtmgp/validate_scm.py",
    ]
    source_pins = {str(p.resolve()): file_pin(p) for p in source_paths}
    authoring_names = (
        "test_udm_scm.py", "test_surface_scm.py", "test_cloud_scm.py",
        "test_column_replay.py", "compare_column_replay.py",
        "test_udm_entry_density.py", "test_udm_radius_stage.py",
        "test_udm_rain_only_slopes_scm.py",
        "test_udm_sedimentation_density_scm.py",
    )
    authoring_tools = {str((HERE / name).resolve()): file_pin(HERE / name)
                       for name in authoring_names}
    authoring_tools.update({str(path.resolve()): file_pin(path)
                            for path in paired_sources.values()})
    executable_pins = {
        "wrf.exe": file_pin(wrf_root / "main/wrf.exe"),
        "ideal.exe": file_pin(wrf_root / "main/ideal.exe"),
    }
    libraries = build_receipt.get("executables", {}).get("wrf.exe", {}).get("ldd", {}).get("libraries")
    require(isinstance(libraries, list) and libraries,
            "successful build receipt lacks the WRF runtime library closure")
    library_pins = {}
    for item in libraries:
        libpath = Path(item.get("path", "")).resolve()
        require(libpath.is_file(), f"runtime library is missing: {libpath}")
        actual = file_pin(libpath)
        require(actual["sha256"] == item.get("sha256") and
                actual["size_bytes"] == item.get("size_bytes"),
                f"runtime library differs from build receipt: {libpath}")
        library_pins[str(libpath)] = actual
    needed_runtime = [wrf_root / "test/rrtmgp/radiation_iofields.txt",
                      wrf_root / "test/em_scm_xy/input_sounding",
                      wrf_root / "test/em_scm_xy/input_soil",
                      wrf_root / "test/em_scm_xy/force_ideal.nc"]
    runtime_pins = {str(p.resolve()): file_pin(p) for p in needed_runtime}
    run_tree = tree_pins(wrf_root / "run")
    return {"repo_root": str(repo.resolve()), "wrf_root": str(wrf_root.resolve()),
            "source_and_config": source_pins, "executables": executable_pins,
            "runtime_libraries": library_pins,
            "authoring_tools": authoring_tools,
            "authoring_runtime_compiled_sources_equal": True,
            "SCM_inputs": runtime_pins,
            "WRF_run_assets": run_tree}


def immutable_inputs(seed_dirs: dict[str, Path], baseline_root: Path) -> dict[str, Any]:
    result: dict[str, Any] = {"seeds": {}, "archived_baselines": {}}
    for label, path in seed_dirs.items():
        result["seeds"][label] = {
            "wrfinput_d01": file_pin(path / "wrfinput_d01"),
            "namelist.input": file_pin(path / "namelist.input"),
        }
    for label in ("cold", "warm"):
        result["archived_baselines"][label] = {}
        for flavor, case_name in (
            ("37_off", f"{label}-37-off"), ("37_on", f"{label}-37-on"),
            ("4", f"{label}-4"),
        ):
            case = baseline_root / case_name
            history = sorted(case.glob("wrfout_d01_*"))
            require(len(history) == 1, f"{case}: expected one archived history file")
            result["archived_baselines"][label][flavor] = {
                "wrfinput_d01": file_pin(case / "wrfinput_d01"),
                "namelist.input": file_pin(case / "namelist.input"),
                "history": file_pin(history[0]),
            }
    return result


def configure_helpers(wrf_root: Path) -> None:
    """Redirect helper staging/validation to the caller's freshly built WRF tree."""
    test_surface_scm.WRF_ROOT = wrf_root
    test_surface_scm.TEMPLATE = wrf_root / "test/rrtmgp/namelist.scm37"
    test_surface_scm.INPUT_DIR = wrf_root / "test/em_scm_xy"
    test_surface_scm.DATA_DIR = wrf_root / "run"
    test_udm_scm.WRF_ROOT = wrf_root
    test_udm_scm.DATA_DIR = wrf_root / "run"
    test_udm_scm.VALIDATOR = wrf_root / "test/rrtmgp/validate_scm.py"


def preflight_seed_matches(seed: Path, baseline_root: Path, label: str) -> dict[str, Any]:
    seed_input = seed / "wrfinput_d01"
    seed_nml = (seed / "namelist.input").read_text(encoding="utf-8")
    checks = {}
    for flavor, opt, case_suffix in (("37_off", 37, "37-off"),
                                     ("37_on", 37, "37-on"), ("4", 4, "4")):
        case = baseline_root / f"{label}-{case_suffix}"
        require(sha256(seed_input) == sha256(case / "wrfinput_d01"),
                f"{label} seed wrfinput differs from archived {flavor} input")
        expected_nml = test_udm_scm.make_namelist(seed_nml, opt, opt, 1)
        baseline_text = (case / "namelist.input").read_text(encoding="utf-8")
        normalized_baseline = test_udm_scm.make_namelist(baseline_text, opt, opt, 1)
        require(expected_nml == normalized_baseline,
                f"{label} seed namelist differs from archived {flavor} settings after scoped normalization")
        checks[flavor] = {"input_sha256_equal": True, "normalized_namelist_equal": True,
                          "expected_option": opt}
    return checks


def canonical_attrs(attrs: dict[str, Any]) -> dict[str, Any]:
    return {name: json_value(value) for name, value in sorted(attrs.items())}


def history_metadata(path: Path) -> dict[str, Any]:
    with netCDF4.Dataset(path) as ds:
        dims = {name: {"size": len(dim), "unlimited": bool(dim.isunlimited())}
                for name, dim in sorted(ds.dimensions.items())}
        variables = {}
        for name, var in sorted(ds.variables.items()):
            variables[name] = {
                "dimensions": list(var.dimensions), "shape": list(var.shape),
                "dtype": str(var.dtype), "attributes": canonical_attrs(var.__dict__),
            }
        return {"data_model": ds.data_model, "dimensions": dims,
                "global_attributes": canonical_attrs(ds.__dict__), "variables": variables}


def strict_history_arrays(path: Path) -> dict[str, dict[str, Any]]:
    arrays: dict[str, dict[str, Any]] = {}
    with netCDF4.Dataset(path) as ds:
        for name, var in ds.variables.items():
            value = var[:]
            mask = np.ma.getmaskarray(value)
            data = np.asarray(np.ma.getdata(value))
            arrays[name] = {"shape": data.shape, "dtype": data.dtype.str,
                            "data": data.tobytes(), "mask": mask.tobytes()}
    return arrays


def compare_histories(left: dict[str, Any], right: dict[str, Any], label: str,
                      *, require_attributes: bool, require_file_bytes: bool,
                      require_arrays: bool = True) -> dict[str, Any]:
    # Keep using the established helper for its byte-level array contract, and
    # strengthen it here to reject missing/extra history fields and mask drift.
    helper = (test_udm_scm.assert_history_bytes_equal(left, right, label)
              if require_arrays else None)
    lp, rp = Path(left["history_path"]), Path(right["history_path"])
    la, ra = strict_history_arrays(lp), strict_history_arrays(rp)
    roster_equal = set(la) == set(ra)
    require(roster_equal, f"{label}: history variable roster changed")
    changed = []
    structure_changed = []
    mask_changed = []
    nonnumeric_changed = []
    for name in sorted(set(la) & set(ra)):
        a, b = la[name], ra[name]
        if a["shape"] != b["shape"] or a["dtype"] != b["dtype"]:
            structure_changed.append(name)
        if a["mask"] != b["mask"]:
            mask_changed.append(name)
        if a["data"] != b["data"]:
            changed.append(name)
            if np.dtype(a["dtype"]).kind not in "iuf":
                nonnumeric_changed.append(name)
    if require_arrays:
        require(not changed, f"{label}: strict history bytes differ in {changed[:16]}")
    lm, rm = history_metadata(lp), history_metadata(rp)
    dim_equal = lm["data_model"] == rm["data_model"] and lm["dimensions"] == rm["dimensions"]
    require(dim_equal, f"{label}: data model or dimension metadata differs")
    if not require_arrays:
        require(not structure_changed, f"{label}: numeric comparison schema changed in {structure_changed[:16]}")
        require(not mask_changed, f"{label}: masked-value pattern changed in {mask_changed[:16]}")
        require(not nonnumeric_changed,
                f"{label}: nonnumeric history data changed in {nonnumeric_changed[:16]}")
    attrs_equal = lm == rm
    metadata_differences = {
        "global_attributes": sorted(k for k in set(lm["global_attributes"]) | set(rm["global_attributes"])
                                     if lm["global_attributes"].get(k) != rm["global_attributes"].get(k)),
        "variables": sorted(k for k in set(lm["variables"]) | set(rm["variables"])
                            if lm["variables"].get(k) != rm["variables"].get(k)),
    }
    if require_attributes:
        require(attrs_equal, f"{label}: NetCDF attributes/schema differ")
    exact_file = sha256(lp) == sha256(rp)
    if require_file_bytes:
        require(exact_file, f"{label}: whole history file hashes differ")
    numeric_deltas = {}
    if not require_arrays:
        with netCDF4.Dataset(lp) as lds, netCDF4.Dataset(rp) as rds:
            for name in sorted(set(lds.variables) & set(rds.variables)):
                lv, rv = lds.variables[name], rds.variables[name]
                if lv.shape != rv.shape or lv.dtype != rv.dtype or lv.dtype.kind not in "iuf":
                    continue
                lraw, rraw = lv[:], rv[:]
                lmasks, rmasks = np.ma.getmaskarray(lraw), np.ma.getmaskarray(rraw)
                ldata = np.asarray(np.ma.getdata(lraw), dtype=np.float64)
                rdata = np.asarray(np.ma.getdata(rraw), dtype=np.float64)
                unmasked = ~(lmasks | rmasks)
                lfinite = np.isfinite(ldata) & unmasked
                rfinite = np.isfinite(rdata) & unmasked
                nonfinite_pattern_differences = int(np.count_nonzero(unmasked & (np.isfinite(ldata) != np.isfinite(rdata))))
                require(nonfinite_pattern_differences == 0,
                        f"{label}: finite/nonfinite pattern differs for {name}")
                valid = lfinite & rfinite
                nonfinite_left = int(np.count_nonzero(unmasked & ~np.isfinite(ldata)))
                nonfinite_right = int(np.count_nonzero(unmasked & ~np.isfinite(rdata)))
                delta = rdata[valid] - ldata[valid]
                if not delta.size:
                    numeric_deltas[name] = {
                        "compared_finite_count": 0, "different_finite_count": 0,
                        "nonfinite_left_count": nonfinite_left,
                        "nonfinite_right_count": nonfinite_right,
                        "nonfinite_pattern_difference_count": nonfinite_pattern_differences,
                        "mask_difference_count": int(np.count_nonzero(lmasks != rmasks)),
                        "max_abs": None, "rms": None, "q50_abs": None,
                        "q90_abs": None, "q99_abs": None,
                    }
                    continue
                absolute = np.abs(delta)
                numeric_deltas[name] = {
                    "compared_finite_count": int(delta.size),
                    "different_finite_count": int(np.count_nonzero(delta)),
                    "nonfinite_left_count": nonfinite_left,
                    "nonfinite_right_count": nonfinite_right,
                    "nonfinite_pattern_difference_count": nonfinite_pattern_differences,
                    "mask_difference_count": int(np.count_nonzero(lmasks != rmasks)),
                    "max_abs": float(np.max(absolute)),
                    "rms": float(np.sqrt(np.mean(delta * delta))),
                    "q50_abs": float(np.quantile(absolute, 0.50)),
                    "q90_abs": float(np.quantile(absolute, 0.90)),
                    "q99_abs": float(np.quantile(absolute, 0.99)),
                }
    return {"status": ("PASS_STRICT_IDENTITY" if require_arrays else
                        "RECORDED_DESCRIPTIVE_ARCHIVE_DIFFERENCES"),
            "helper_array_comparison": helper,
            "comparison_scope": "strict-byte-identity" if require_arrays else "descriptive-archive-difference",
            "strict_variable_roster_equal": roster_equal,
            "strict_all_array_data_and_masks_equal": not changed and roster_equal,
            "changed_variable_names": changed,
            "schema_changed_variable_names": structure_changed,
            "mask_changed_variable_names": mask_changed,
            "nonnumeric_changed_variable_names": nonnumeric_changed,
            "numeric_difference_summaries_right_minus_left": numeric_deltas,
            "data_model_and_dimensions_equal": dim_equal,
            "all_metadata_equal": attrs_equal,
            "metadata_difference_names": metadata_differences,
            "left_history_sha256": sha256(lp), "right_history_sha256": sha256(rp),
            "whole_file_byte_identical": exact_file}


def capture_packet_headers(capture_dir: Path, kind: str) -> list[dict[str, Any]]:
    prefix = "udm_entry_density_" if kind == "entry" else "udm_radius_"
    magic = "RRTMGP_UDM_ENTRY_DENSITY_V2" if kind == "entry" else "RRTMGP_UDM_RADIUS_V1"
    paths = sorted(capture_dir.glob(prefix + "*.raw"))
    records = []
    for path in paths:
        lines = path.read_text(encoding="ascii").splitlines()
        require(len(lines) >= 2 and lines[0] == magic, f"{path}: invalid {kind} packet header")
        values = [int(x) for x in lines[1].split()]
        require(len(values) == 6, f"{path}: expected six integer packet-header fields")
        domain, step, i, j, kts, kte = values
        records.append({"name": path.name, "domain": domain, "step": step,
                        "i": i, "j": j, "kts": kts, "kte": kte,
                        "sha256": sha256(path), "size_bytes": path.stat().st_size})
    return records


def packet_values(path: Path, expected_magic: str) -> dict[str, list[float]]:
    lines = path.read_text(encoding="ascii").splitlines()
    require(len(lines) >= 3 and lines[0] == expected_magic, f"{path}: invalid packet magic")
    records: dict[str, list[float]] = {}
    cursor = 2
    while cursor < len(lines):
        fields = lines[cursor].split()
        require(len(fields) == 2, f"{path}: malformed record header at line {cursor + 1}")
        name, count_text = fields
        require(name not in records, f"{path}: duplicate record {name}")
        try:
            count = int(count_text)
        except ValueError as exc:
            raise CheckFailure(f"{path}: invalid record count for {name}") from exc
        require(count > 0 and cursor + count < len(lines), f"{path}: truncated record {name}")
        vals = []
        for line in lines[cursor + 1:cursor + 1 + count]:
            try:
                value = float(line.strip())
            except ValueError as exc:
                raise CheckFailure(f"{path}: invalid numeric value in {name}") from exc
            require(np.isfinite(value), f"{path}: non-finite value in {name}")
            vals.append(value)
        records[name] = vals
        cursor += count + 1
    return records


def validate_capture_roster(capture: Path, kind: str) -> list[dict[str, Any]]:
    headers = capture_packet_headers(capture, kind)
    require(len(headers) == 6, f"{capture}: expected six {kind} packets, got {len(headers)}")
    require([x["step"] for x in headers] == list(range(1, 7)),
            f"{capture}: {kind} packet steps must be 1..6")
    require(all(x["domain"] == 1 and x["i"] == 1 and x["j"] == 1 and
                x["kts"] == 1 and x["kte"] == 59 for x in headers),
            f"{capture}: unexpected {kind} packet coordinates or native levels")
    magic = "RRTMGP_UDM_ENTRY_DENSITY_V2" if kind == "entry" else "RRTMGP_UDM_RADIUS_V1"
    for index, packet in enumerate(headers):
        values = packet_values(capture / packet["name"], magic)
        require("SOURCE_TIME_SECONDS" in values and len(values["SOURCE_TIME_SECONDS"]) == 1,
                f"{packet['name']}: missing source clock")
        expected_time = float(index * 10)
        require(values["SOURCE_TIME_SECONDS"][0] == expected_time,
                f"{packet['name']}: expected source clock {expected_time}s")
        require(values.get("SOURCE_TIME_PRESENT") == [1.0],
                f"{packet['name']}: source clock must be explicitly present")
        if kind == "entry":
            require(values.get("INPUT_DENSITY_IS_DRY") == [1.0],
                    f"{packet['name']}: V2 dry-density policy was not selected")
            require("DEND_LEGACY_COUNTERFACTUAL_KG_M3" in values,
                    f"{packet['name']}: missing legacy DEND counterfactual")
            require(len(values.get("DEN_PASSED_KG_M3", [])) == packet["kte"] - packet["kts"] + 1,
                    f"{packet['name']}: DEN length does not match packet levels")
            selected = values.get("DEND_REEVALUATED_PRECALL_KG_M3", [])
            passed = values.get("DEN_PASSED_KG_M3", [])
            require(len(selected) == len(passed),
                    f"{packet['name']}: selected DEND length does not match DEN")
            require(all(struct.pack("=f", a) == struct.pack("=f", b)
                        for a, b in zip(selected, passed)),
                    f"{packet['name']}: selected DEND is not binary32-identical to passed DEN")
    return headers


def clean_environment(case: Path, build_receipt: dict[str, Any], *, radius_capture: bool) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(ENV_PREFIX)}
    env["OMP_NUM_THREADS"] = "1"
    build_env = build_receipt.get("environment", {})
    for name in ("LD_LIBRARY_PATH", "NETCDF", "NETCDF_classic"):
        value = build_env.get(name)
        if value is not None:
            env[name] = str(value)
    if radius_capture:
        env[CAPTURE_DIR] = str(case / "capture")
        env[CAPTURE_CALL] = "2"
        env[RADIUS_GATE] = "1"
    return env


def launch_arm(receipt: dict[str, Any], receipt_path: Path, label: str, seed: dict[str, Any],
               case: Path, option: int, entry_enabled: bool, wrf_root: Path,
               build_receipt: dict[str, Any],
               parser_path: Path | None) -> dict[str, Any]:
    test_udm_scm.create_run_case(seed, case, option, option, 1,
                                 2 if option == 37 else None)
    before_input = sha256(case / "wrfinput_d01")
    require(before_input == seed["input_sha256"], f"{label}: staged wrfinput differs from seed")
    expected_text = test_udm_scm.make_namelist(seed["namelist_text"], option, option, 1)
    actual_text = (case / "namelist.input").read_text(encoding="utf-8")
    require(actual_text == expected_text, f"{label}: staged namelist differs from intended configuration")
    arm = {"case": str(case.resolve()), "option": option,
           "entry_density_enabled": entry_enabled,
           "staged_wrfinput_sha256": before_input,
           "staged_namelist_sha256": sha256(case / "namelist.input"),
           "log": str((case / "wrf.log").resolve()),
           "status": "LAUNCHING", "returncode": None}
    receipt["arms"][label] = arm
    receipt["model_attempts_started"] += 1
    atomic_json(receipt_path, receipt)

    executable = wrf_root / "main/wrf.exe"
    env = clean_environment(case, build_receipt, radius_capture=(option == 37))
    if entry_enabled:
        env[ENTRY_GATE] = "1"
    started = datetime.now().astimezone().isoformat()
    arm["start_time"] = started
    arm["executable"] = file_pin(executable)
    arm["environment_controls"] = {"OMP_NUM_THREADS": "1",
                                   "LD_LIBRARY_PATH": env.get("LD_LIBRARY_PATH"),
                                   "NETCDF": env.get("NETCDF"),
                                   "entry_gate": env.get(ENTRY_GATE, "unset"),
                                   "radius_capture": env.get(RADIUS_GATE, "unset"),
                                   "capture_call": env.get(CAPTURE_CALL, "unset")}
    atomic_json(receipt_path, receipt)
    run = test_udm_scm.run_logged(executable, case, "wrf.log", env)
    # Persist the actual return code and log hash before any validation/parsing.
    receipt["actual_forecast_invocations"] += 1
    arm["returncode"] = int(run.returncode)
    arm["end_time"] = datetime.now().astimezone().isoformat()
    arm["log_pin"] = file_pin(case / "wrf.log")
    arm["status"] = "PROCESS_COMPLETE"
    atomic_json(receipt_path, receipt)
    require(run.returncode == 0, f"{label}: wrf.exe failed with {run.returncode}; see preserved log")
    log_text = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")
    require(SUCCESS in log_text, f"{label}: WRF success marker missing")

    history = test_udm_scm.validate_history(case, option)
    history_path = Path(history["path"])
    expected_history_variables = 211 if option == 37 else 208
    require(len(history["arrays"]) == expected_history_variables,
            f"{label}: expected {expected_history_variables} history variables, got {len(history['arrays'])}")
    arm["history_pin"] = file_pin(history_path)
    arm["history_metadata"] = history_metadata(history_path)
    arm["history_time_count"] = len(history["report"].get("time_deltas_seconds", [])) + 1
    atomic_json(receipt_path, receipt)

    if option == 37:
        capture = case / "capture"
        radius_headers = validate_capture_roster(capture, "radius")
        entries = validate_capture_roster(capture, "entry") if entry_enabled else \
                  capture_packet_headers(capture, "entry")
        if entry_enabled:
            require(parser_path is not None and parser_path.is_file(),
                    "entry parser is missing; no entry capture can be accepted")
            report_path = case / "entry-density-report.json"
            command = [sys.executable, "-B", str(parser_path), "--entry-dir", str(capture),
                       "--producer-dir", str(capture), "--output", str(report_path)]
            parsed = subprocess.run(command, cwd=wrf_root, text=True, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, check=False)
            arm["parser_command"] = command
            arm["parser_returncode"] = int(parsed.returncode)
            arm["parser_stdout"] = parsed.stdout[-3000:]
            arm["entry_report_pin"] = file_pin(report_path) if report_path.is_file() else None
            atomic_json(receipt_path, receipt)
            require(parsed.returncode == 0 and report_path.is_file(),
                    f"{label}: entry-density parser failed ({parsed.returncode})")
            parsed_report = json.loads(report_path.read_text(encoding="utf-8"))
            require(parsed_report.get("schema") == "UDM_ENTRY_DENSITY_CONTRACT_V2",
                    f"{label}: parser did not validate V2 dry-policy packets")
            packet_rows = parsed_report.get("entry_packets", [])
            require(len(packet_rows) == 6 and all(
                row.get("version") == 2 and row.get("input_density_is_dry") == 1 and
                row.get("selected_DEND_policy") == "passed DEN"
                for row in packet_rows),
                f"{label}: parser report does not confirm six selected dry-DEND packets")
            arm["entry_packet_pins"] = entries
            arm["radius_packet_pins"] = radius_headers
            arm["entry_parser_report"] = {
                "schema": parsed_report.get("schema"),
                "packet_count": parsed_report.get("packet_count"),
                "join_count": parsed_report.get("join_count", 0),
                "selected_policy": "passed DEN for all six V2 packets",
                "legacy_counterfactual_present": True,
            }
        else:
            require(not entries, f"{label}: entry-density packets appeared with gate unset")
            arm["entry_packets_absent"] = True
            arm["radius_packet_pins"] = radius_headers
    else:
        require(not (case / "capture").exists(), f"{label}: plain 4/4 case unexpectedly staged capture")

    arm["status"] = "PASS_OUTPUTS_VALIDATED"
    atomic_json(receipt_path, receipt)
    return {"case": case, "history_path": history_path,
            "history_arrays": history["arrays"], "history_report": history["report"]}


def verify_assets_unchanged(receipt: dict[str, Any], wrf_root: Path,
                            input_pins: dict[str, Any], seed_dirs: dict[str, Path],
                            baseline_root: Path, build_receipt_path: Path) -> None:
    build_receipt = json.loads(build_receipt_path.read_text(encoding="utf-8"))
    require(source_and_runtime_pins(wrf_root, build_receipt) == receipt["preflight_pins"],
            "source, executable, configuration, or runtime assets changed during run")
    require(file_pin(build_receipt_path) == receipt["candidate_build_receipt"],
            "candidate build receipt changed during run")
    after = immutable_inputs(seed_dirs, baseline_root)
    require(after == input_pins, "seed or archived baseline inputs/outputs changed during run")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wrf-root", required=True, type=Path, help="fresh-build WRF directory")
    ap.add_argument("--cold-seed", required=True, type=Path)
    ap.add_argument("--warm-seed", required=True, type=Path)
    ap.add_argument("--baseline-root", required=True, type=Path,
                    help="read-only PR107 archive root (cold/warm-37-off/on and cold/warm-4)")
    ap.add_argument("--build-receipt", required=True, type=Path,
                    help="fresh successful candidate-build execution receipt")
    ap.add_argument("--output-root", required=True, type=Path,
                    help="new nonexistent output directory")
    args = ap.parse_args()

    wrf_root = args.wrf_root.expanduser().resolve()
    cold_seed_dir = args.cold_seed.expanduser().resolve()
    warm_seed_dir = args.warm_seed.expanduser().resolve()
    baseline_root = args.baseline_root.expanduser().resolve()
    build_receipt_path = args.build_receipt.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    require(not output_root.exists(), f"refusing existing output root: {output_root}")
    require(build_receipt_path.is_file(), f"candidate build receipt missing: {build_receipt_path}")
    build_receipt = json.loads(build_receipt_path.read_text(encoding="utf-8"))
    require(build_receipt.get("status") in {"BUILD_PASS_SCOPED", "BUILD_PASS"},
            "candidate build receipt is not a successful fresh build")
    require(build_receipt.get("base_head") == "e3b9e52c2a20811830a27d34420721ca89b62e59",
            "candidate build does not use the reviewed e3b9e52 source base")
    expected_sources = {
        "WRF/phys/module_mp_udm.F": ("18bac4328061b828c1a57fcbead77986eb71bf5b6a56985fbed0672647bc7d4d", 193968),
        "WRF/phys/module_microphysics_driver.F": ("7e15f93341b1fa079136aa60b2f2061c6e7844f107446ae8e7951edff00820fb", 198427),
        "WRF/phys/module_ra_rrtmgp_trace.F": ("c08a1cae7a93f85a08ed59042aa1b98dc1ef6b42d33c6f344b93a9eca9d652e9", 41541),
    }
    overlay = build_receipt.get("overlay", {})
    require(set(overlay) == {"WRF/phys/module_mp_udm.F"},
            "candidate build receipt must contain only the UDM source overlay")
    udm_overlay = overlay["WRF/phys/module_mp_udm.F"]
    require(udm_overlay.get("sha256") == expected_sources["WRF/phys/module_mp_udm.F"][0] and
            udm_overlay.get("size_bytes") == expected_sources["WRF/phys/module_mp_udm.F"][1],
            "candidate build receipt does not bind the rain-only slope source")
    for manifest_name in ("source_manifest_before", "source_manifest_after"):
        manifest = build_receipt.get(manifest_name, {})
        require(manifest, f"candidate build receipt lacks {manifest_name}")
        for source_name, (expected_sha, expected_size) in expected_sources.items():
            row = manifest.get(source_name, {})
            require(row.get("kind") == "file" and row.get("sha256") == expected_sha and
                    row.get("size_bytes") == expected_size,
                    f"candidate {manifest_name} does not bind source {source_name}")
    built_exe = build_receipt.get("executables", {}).get("wrf.exe", {})
    require(built_exe.get("sha256") == sha256(args.wrf_root / "main/wrf.exe") and
            Path(built_exe.get("path", "")).resolve() == (args.wrf_root / "main/wrf.exe").resolve(),
            "candidate executable does not match successful build receipt")
    parser_path = HERE / "test_udm_entry_density.py"
    for path in (wrf_root / "main/wrf.exe", wrf_root / "test/rrtmgp/namelist.scm37",
                 wrf_root / "test/rrtmgp/radiation_iofields.txt",
                 wrf_root / "test/em_scm_xy/input_sounding",
                 wrf_root / "test/em_scm_xy/input_soil",
                 wrf_root / "test/em_scm_xy/force_ideal.nc",
                 wrf_root / "test/rrtmgp/validate_scm.py",
                 cold_seed_dir / "namelist.input", cold_seed_dir / "wrfinput_d01",
                 warm_seed_dir / "namelist.input", warm_seed_dir / "wrfinput_d01",
                 baseline_root / "cold-37-off/wrfinput_d01",
                 baseline_root / "cold-37-on/wrfinput_d01",
                 baseline_root / "warm-37-off/wrfinput_d01",
                 baseline_root / "warm-37-on/wrfinput_d01",
                 baseline_root / "cold-4/wrfinput_d01",
                 baseline_root / "warm-4/wrfinput_d01"):
        require(path.is_file(), f"required preflight file missing: {path}")
    require(parser_path.is_file(), f"entry parser is missing from authoring tree: {parser_path}")
    configure_helpers(wrf_root)

    seed_dirs = {"cold": cold_seed_dir, "warm": warm_seed_dir}
    seed_matches = {label: preflight_seed_matches(path, baseline_root, label)
                    for label, path in seed_dirs.items()}
    input_pins = immutable_inputs(seed_dirs, baseline_root)
    pins = source_and_runtime_pins(wrf_root, build_receipt)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    output_root.mkdir()
    receipt_path = output_root / "execution.json"
    receipt: dict[str, Any] = {
        "schema": "udm37-rain-only-slopes-scm-v1",
        "status": "PREPARED",
        "scope": "Six fresh SCM forecasts only: cold/warm 37/37 with the existing entry-density diagnostic gate unset/set, then cold/warm ordinary 4/4. This exercises the rain-only cloud-slope initialization source together with the existing opt-in DEND contract. Captured V2 packets must show the selected dry DEND policy and legacy counterfactual; 37 gate off/on must be strictly identical; 4/4 archive outputs must match arrays, metadata, and whole-file bytes exactly. New 37/archive differences are descriptive. No ideal.exe or standalone RTE calls.",
        "created_utc": datetime.now().astimezone().isoformat(),
        "planned_forecast_invocations": 6,
        "actual_forecast_invocations": 0,
        "model_attempts_started": 0,
        "standalone_rte_invocations": 0,
        "preflight_pins": pins,
        "candidate_build_receipt": file_pin(build_receipt_path),
        "candidate_build_receipt_status": build_receipt.get("status"),
        "immutable_seed_and_archive_pins": input_pins,
        "seed_baseline_checks": seed_matches,
        "arms": {}, "comparisons": {},
    }
    atomic_json(receipt_path, receipt)
    results: dict[str, dict[str, Any]] = {}
    failed: str | None = None
    try:
        for label, seed_dir in (("cold", cold_seed_dir), ("warm", warm_seed_dir)):
            seed = {"path": seed_dir, "wrfinput": seed_dir / "wrfinput_d01",
                    "input_sha256": sha256(seed_dir / "wrfinput_d01"),
                    "namelist_text": (seed_dir / "namelist.input").read_text(encoding="utf-8")}
            off = launch_arm(receipt, receipt_path, f"{label}-37-off", seed,
                             output_root / f"{label}-37-off", 37, False, wrf_root,
                             build_receipt, parser_path)
            results[f"{label}-37-off"] = off
            atomic_json(receipt_path, receipt)
            on = launch_arm(receipt, receipt_path, f"{label}-37-on", seed,
                            output_root / f"{label}-37-on", 37, True, wrf_root,
                            build_receipt, parser_path)
            results[f"{label}-37-on"] = on
            atomic_json(receipt_path, receipt)
            require(sha256(off["case"] / "namelist.input") == sha256(on["case"] / "namelist.input"),
                    f"{label}: entry gate changed the staged namelist")
            require(sha256(off["case"] / "wrfinput_d01") == sha256(on["case"] / "wrfinput_d01"),
                    f"{label}: entry gate changed staged initial conditions")
            eq = compare_histories(off, on, f"{label} gate off/on", require_attributes=True,
                                   require_file_bytes=True)
            receipt["comparisons"][f"{label}_37_off_vs_on"] = eq
            atomic_json(receipt_path, receipt)

            for arm_name, run_data in (("off", off), ("on", on)):
                archived_case = baseline_root / f"{label}-37-{arm_name}"
                old = test_udm_scm.validate_history(archived_case, 37)
                baseline = {"history_path": old["path"], "history_arrays": old["arrays"]}
                eqbase = compare_histories(run_data, baseline,
                    f"{label} new37 {arm_name} vs archived PR106 {arm_name}", require_attributes=True,
                    require_file_bytes=False, require_arrays=False)
                receipt["comparisons"][f"{label}_37_{arm_name}_vs_archive"] = eqbase
                atomic_json(receipt_path, receipt)

            plain = launch_arm(receipt, receipt_path, f"{label}-4", seed,
                               output_root / f"{label}-4", 4, False, wrf_root,
                               build_receipt, None)
            results[f"{label}-4"] = plain
            atomic_json(receipt_path, receipt)
            archived_case = baseline_root / f"{label}-4"
            old4 = test_udm_scm.validate_history(archived_case, 4)
            baseline4 = {"history_path": old4["path"], "history_arrays": old4["arrays"]}
            eq4 = compare_histories(plain, baseline4,
                f"{label} new4 vs archived new4", require_attributes=True,
                require_file_bytes=True)
            receipt["comparisons"][f"{label}_4_vs_archive"] = eq4
            atomic_json(receipt_path, receipt)

        require(receipt["actual_forecast_invocations"] == 6,
                "completed campaign did not use exactly six forecasts")
        verify_assets_unchanged(receipt, wrf_root, input_pins, seed_dirs, baseline_root,
                                build_receipt_path)
        receipt["status"] = "PASS_SCOPED_RAIN_ONLY_SLOPES_SCM_CONTRACT"
        receipt["assets_stable_postflight"] = True
        receipt["finished_utc"] = datetime.now().astimezone().isoformat()
        atomic_json(receipt_path, receipt)
    except BaseException as exc:
        failed = f"{type(exc).__name__}: {exc}"
        receipt["status"] = "FAIL_PRESERVED"
        receipt["failure"] = failed
        receipt["finished_utc"] = datetime.now().astimezone().isoformat()
        # Keep every already-recorded child return code and artifact pin.
        try:
            atomic_json(receipt_path, receipt)
        except Exception:
            pass
    print(json.dumps({"status": receipt["status"], "receipt": str(receipt_path),
                      "actual_forecast_invocations": receipt["actual_forecast_invocations"],
                      "model_attempts_started": receipt["model_attempts_started"],
                      "failure": failed}, indent=2))
    return 1 if failed else 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (CheckFailure, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
