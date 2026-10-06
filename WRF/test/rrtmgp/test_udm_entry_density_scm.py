#!/usr/bin/env python3
"""Run the six bounded SCM cases for the opt-in UDM entry-density trace.

This is a passivity check for a diagnostic gate, not a physical validation.
It launches four fresh 37/37 SCM forecasts (gate off/on for cold and warm
seeds) and two fresh ordinary 4/4 forecasts. It never launches ideal.exe or
the standalone radiation solver.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
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


def source_and_runtime_pins(wrf_root: Path) -> dict[str, Any]:
    repo = wrf_root.parent
    authoring_wrf = HERE.parents[1]
    authoring_trace = authoring_wrf / "phys/module_ra_rrtmgp_trace.F"
    runtime_trace = wrf_root / "phys/module_ra_rrtmgp_trace.F"
    require(sha256(authoring_trace) == sha256(runtime_trace),
            "authoring parser trace source differs from the compiled runtime trace source")
    source_paths = [
        wrf_root / "phys/module_microphysics_driver.F",
        runtime_trace,
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
        "test_udm_entry_density_scm.py",
    )
    authoring_tools = {str((HERE / name).resolve()): file_pin(HERE / name)
                       for name in authoring_names}
    authoring_tools[str(authoring_trace.resolve())] = file_pin(authoring_trace)
    executable_pins = {
        "wrf.exe": file_pin(wrf_root / "main/wrf.exe"),
        "ideal.exe": file_pin(wrf_root / "main/ideal.exe"),
    }
    needed_runtime = [wrf_root / "test/rrtmgp/radiation_iofields.txt",
                      wrf_root / "test/em_scm_xy/input_sounding",
                      wrf_root / "test/em_scm_xy/input_soil",
                      wrf_root / "test/em_scm_xy/force_ideal.nc"]
    runtime_pins = {str(p.resolve()): file_pin(p) for p in needed_runtime}
    run_tree = tree_pins(wrf_root / "run")
    return {"repo_root": str(repo.resolve()), "wrf_root": str(wrf_root.resolve()),
            "source_and_config": source_pins, "executables": executable_pins,
            "authoring_tools": authoring_tools,
            "authoring_runtime_trace_source_equal": True,
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
        for flavor, case_name in (("new37", f"{label}-new37"), ("new4", f"{label}-new4")):
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
    for flavor, opt in (("new37", 37), ("new4", 4)):
        case = baseline_root / f"{label}-{flavor}"
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
                      *, require_attributes: bool, require_file_bytes: bool) -> dict[str, Any]:
    # Keep using the established helper for its byte-level array contract, and
    # strengthen it here to reject missing/extra history fields and mask drift.
    helper = test_udm_scm.assert_history_bytes_equal(left, right, label)
    lp, rp = Path(left["history_path"]), Path(right["history_path"])
    la, ra = strict_history_arrays(lp), strict_history_arrays(rp)
    require(set(la) == set(ra), f"{label}: history variable roster changed")
    changed = []
    for name in sorted(la):
        if (la[name]["shape"] != ra[name]["shape"] or la[name]["dtype"] != ra[name]["dtype"]
                or la[name]["data"] != ra[name]["data"] or la[name]["mask"] != ra[name]["mask"]):
            changed.append(name)
    require(not changed, f"{label}: strict history bytes differ in {changed[:16]}")
    lm, rm = history_metadata(lp), history_metadata(rp)
    dim_equal = lm["data_model"] == rm["data_model"] and lm["dimensions"] == rm["dimensions"]
    require(dim_equal, f"{label}: data model or dimension metadata differs")
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
    return {"status": "PASS", "helper_array_comparison": helper,
            "strict_variable_roster_equal": True, "strict_all_array_data_and_masks_equal": True,
            "data_model_and_dimensions_equal": dim_equal,
            "all_metadata_equal": attrs_equal,
            "metadata_difference_names": metadata_differences,
            "left_history_sha256": sha256(lp), "right_history_sha256": sha256(rp),
            "whole_file_byte_identical": exact_file}


def capture_packet_headers(capture_dir: Path, kind: str) -> list[dict[str, Any]]:
    prefix = "udm_entry_density_" if kind == "entry" else "udm_radius_"
    magic = "RRTMGP_UDM_ENTRY_DENSITY_V1" if kind == "entry" else "RRTMGP_UDM_RADIUS_V1"
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
    magic = "RRTMGP_UDM_ENTRY_DENSITY_V1" if kind == "entry" else "RRTMGP_UDM_RADIUS_V1"
    for index, packet in enumerate(headers):
        values = packet_values(capture / packet["name"], magic)
        require("SOURCE_TIME_SECONDS" in values and len(values["SOURCE_TIME_SECONDS"]) == 1,
                f"{packet['name']}: missing source clock")
        expected_time = float(index * 10)
        require(values["SOURCE_TIME_SECONDS"][0] == expected_time,
                f"{packet['name']}: expected source clock {expected_time}s")
        require(values.get("SOURCE_TIME_PRESENT") == [1.0],
                f"{packet['name']}: source clock must be explicitly present")
    return headers


def clean_environment(case: Path, *, entry_enabled: bool) -> dict[str, str]:
    env = {key: value for key, value in os.environ.items() if not key.startswith(ENV_PREFIX)}
    env["OMP_NUM_THREADS"] = "1"
    env[CAPTURE_DIR] = str(case / "capture")
    env[CAPTURE_CALL] = "2"
    env[RADIUS_GATE] = "1"
    if entry_enabled:
        env[ENTRY_GATE] = "1"
    return env


def launch_arm(receipt: dict[str, Any], receipt_path: Path, label: str, seed: dict[str, Any],
               case: Path, option: int, entry_enabled: bool, wrf_root: Path,
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
    env = clean_environment(case, entry_enabled=entry_enabled) if option == 37 else {
        key: value for key, value in os.environ.items() if not key.startswith(ENV_PREFIX)}
    if option != 37:
        env["OMP_NUM_THREADS"] = "1"
    started = datetime.now().astimezone().isoformat()
    arm["start_time"] = started
    arm["executable"] = file_pin(executable)
    arm["environment_controls"] = {"OMP_NUM_THREADS": "1",
                                   "entry_gate": "1" if entry_enabled else "unset",
                                   "radius_capture": "1" if option == 37 else "unset",
                                   "capture_call": "2" if option == 37 else "unset"}
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
            arm["entry_packet_pins"] = entries
            arm["radius_packet_pins"] = radius_headers
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
                            baseline_root: Path) -> None:
    require(source_and_runtime_pins(wrf_root) == receipt["preflight_pins"],
            "source, executable, configuration, or runtime assets changed during run")
    after = immutable_inputs(seed_dirs, baseline_root)
    require(after == input_pins, "seed or archived baseline inputs/outputs changed during run")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wrf-root", required=True, type=Path, help="fresh-build WRF directory")
    ap.add_argument("--cold-seed", required=True, type=Path)
    ap.add_argument("--warm-seed", required=True, type=Path)
    ap.add_argument("--baseline-root", required=True, type=Path,
                    help="archived warm-ice-scm root; never written")
    ap.add_argument("--output-root", required=True, type=Path,
                    help="new nonexistent output directory")
    args = ap.parse_args()

    wrf_root = args.wrf_root.expanduser().resolve()
    cold_seed_dir = args.cold_seed.expanduser().resolve()
    warm_seed_dir = args.warm_seed.expanduser().resolve()
    baseline_root = args.baseline_root.expanduser().resolve()
    output_root = args.output_root.expanduser().resolve()
    require(not output_root.exists(), f"refusing existing output root: {output_root}")
    parser_path = HERE / "test_udm_entry_density.py"
    for path in (wrf_root / "main/wrf.exe", wrf_root / "test/rrtmgp/namelist.scm37",
                 wrf_root / "test/rrtmgp/radiation_iofields.txt",
                 wrf_root / "test/em_scm_xy/input_sounding",
                 wrf_root / "test/em_scm_xy/input_soil",
                 wrf_root / "test/em_scm_xy/force_ideal.nc",
                 wrf_root / "test/rrtmgp/validate_scm.py",
                 cold_seed_dir / "namelist.input", cold_seed_dir / "wrfinput_d01",
                 warm_seed_dir / "namelist.input", warm_seed_dir / "wrfinput_d01",
                 baseline_root / "cold-new37/wrfinput_d01",
                 baseline_root / "warm-new37/wrfinput_d01",
                 baseline_root / "cold-new4/wrfinput_d01",
                 baseline_root / "warm-new4/wrfinput_d01"):
        require(path.is_file(), f"required preflight file missing: {path}")
    require(parser_path.is_file(), f"entry parser is missing from authoring tree: {parser_path}")
    configure_helpers(wrf_root)

    seed_dirs = {"cold": cold_seed_dir, "warm": warm_seed_dir}
    seed_matches = {label: preflight_seed_matches(path, baseline_root, label)
                    for label, path in seed_dirs.items()}
    input_pins = immutable_inputs(seed_dirs, baseline_root)
    pins = source_and_runtime_pins(wrf_root)
    output_root.parent.mkdir(parents=True, exist_ok=True)
    output_root.mkdir()
    receipt_path = output_root / "execution.json"
    receipt: dict[str, Any] = {
        "schema": "udm37-entry-density-scm-passivity-v1",
        "status": "PREPARED",
        "scope": "Six fresh SCM forecasts only: cold/warm 37/37 with entry-density gate unset/set, then cold/warm ordinary 4/4. No ideal.exe or standalone RTE calls.",
        "created_utc": datetime.now().astimezone().isoformat(),
        "planned_forecast_invocations": 6,
        "actual_forecast_invocations": 0,
        "model_attempts_started": 0,
        "standalone_rte_invocations": 0,
        "preflight_pins": pins,
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
                             output_root / f"{label}-37-off", 37, False, wrf_root, parser_path)
            results[f"{label}-37-off"] = off
            atomic_json(receipt_path, receipt)
            on = launch_arm(receipt, receipt_path, f"{label}-37-on", seed,
                            output_root / f"{label}-37-on", 37, True, wrf_root, parser_path)
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
                archived_case = baseline_root / f"{label}-new37"
                old = test_udm_scm.validate_history(archived_case, 37)
                baseline = {"history_path": old["path"], "history_arrays": old["arrays"]}
                eqbase = compare_histories(run_data, baseline,
                    f"{label} new37 {arm_name} vs archived new37", require_attributes=False,
                    require_file_bytes=False)
                receipt["comparisons"][f"{label}_37_{arm_name}_vs_archive"] = eqbase
                atomic_json(receipt_path, receipt)

            plain = launch_arm(receipt, receipt_path, f"{label}-4", seed,
                               output_root / f"{label}-4", 4, False, wrf_root, None)
            results[f"{label}-4"] = plain
            atomic_json(receipt_path, receipt)
            archived_case = baseline_root / f"{label}-new4"
            old4 = test_udm_scm.validate_history(archived_case, 4)
            baseline4 = {"history_path": old4["path"], "history_arrays": old4["arrays"]}
            eq4 = compare_histories(plain, baseline4,
                f"{label} new4 vs archived new4", require_attributes=False,
                require_file_bytes=False)
            receipt["comparisons"][f"{label}_4_vs_archive"] = eq4
            atomic_json(receipt_path, receipt)

        require(receipt["actual_forecast_invocations"] == 6,
                "completed campaign did not use exactly six forecasts")
        verify_assets_unchanged(receipt, wrf_root, input_pins, seed_dirs, baseline_root)
        receipt["status"] = "PASS_SCOPED_PASSIVITY_AND_ARCHIVE_REGRESSION"
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
