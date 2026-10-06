#!/usr/bin/env python3
"""Check dynamic CAM CFC capture/replay from a real-data UDM radiation case.

This is a one-minute input-contract test. It does not establish long-forecast
stability or radiation-scheme accuracy.
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
from typing import Any

import numpy as np

import test_column_replay
import test_surface_scm
from compare_column_replay import compare, read_result

WRF_ROOT = test_surface_scm.WRF_ROOT
REPO_ROOT = WRF_ROOT.parent
DATA_DIR = test_surface_scm.DATA_DIR
STATIC_CFC = {"VMR_CFC11": 0.251e-9, "VMR_CFC12": 0.538e-9,
              "VMR_CFC22": 0.169e-9, "VMR_CCL4": 0.093e-9}
CFC_NAMES = tuple(STATIC_CFC)
N2_MAGICS = {"RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"}
TRACE_GAS_MAGICS = {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V10", *N2_MAGICS}
SUCCESS = "SUCCESS COMPLETE WRF"


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def source_hashes() -> dict[str, str]:
    names = (
        "WRF/Registry/Registry.EM_COMMON", "WRF/share/module_check_a_mundo.F",
        "WRF/phys/module_physics_init.F", "WRF/phys/module_ra_clWRF_support.F",
        "WRF/phys/module_ra_rrtmg_lw.F", "WRF/phys/module_ra_rrtmgp.F",
        "WRF/phys/module_ra_rrtmgp_trace.F", "WRF/test/rrtmgp/test_column_replay.py",
        "WRF/test/rrtmgp/compare_column_replay.py",
        "WRF/test/rrtmgp/test_lw_trace_gases_scm.py",
        "WRF/test/rrtmgp/test_lw_trace_gases_realcase.py",
    )
    return {n: sha256(REPO_ROOT / n) for n in names if (REPO_ROOT / n).is_file()}


def set_namelist_values(text: str, key: str, values: list[str]) -> str:
    pattern = re.compile(rf"(?im)^(\s*{re.escape(key)}\s*=\s*)([^\n!]*?)(\s*(?:!.*)?)$")
    matches = list(pattern.finditer(text))
    if len(matches) != 1:
        fail(f"expected one namelist assignment for {key}, found {len(matches)}")
    match = matches[0]
    rhs = match.group(2).strip()
    has_trailing_comma = rhs.endswith(",")
    items = [x.strip() for x in rhs.rstrip(",").split(",") if x.strip()]
    if not items:
        fail(f"empty namelist assignment for {key}")
    new_items = values if len(values) == len(items) else [values[0]] * len(items)
    rendered = ", ".join(new_items) + ("," if has_trailing_comma else "")
    return text[:match.start(2)] + rendered + text[match.end(2):]


def first_int(text: str, key: str) -> int:
    match = re.search(rf"(?im)^\s*{re.escape(key)}\s*=\s*(\d+)", text)
    if not match:
        fail(f"namelist lacks {key}")
    return int(match.group(1))


def assignment_text(text: str, key: str) -> str | None:
    match = re.search(rf"(?im)^\s*{re.escape(key)}\s*=\s*([^\n!]+)", text)
    return match.group(1).strip().rstrip(",").strip() if match else None


def ensure_ghg_input(text: str) -> tuple[str, bool]:
    start = re.search(r"(?im)^\s*&physics\b", text)
    if not start:
        fail("namelist has no physics group")
    end = re.search(r"(?im)^\s*/\s*$", text[start.end():])
    if not end:
        fail("could not find physics namelist group terminator")
    stop = start.end() + end.start()
    block = text[start.end():stop]
    if re.search(r"(?im)^\s*ghg_input\s*=", block):
        return text, False
    return text[:stop] + " ghg_input = 1,\n" + text[stop:], True


def prepare_case(source: Path, case: Path, table: Path) -> dict[str, str]:
    case.mkdir()
    for name in ("namelist.input", "wrfinput_d01", "wrfbdy_d01"):
        src = source / name
        if not src.is_file():
            fail(f"source case missing {name}: {source}")
        shutil.copy2(src, case / name)
    for src in source.iterdir():
        if src.is_symlink():
            target = src.resolve(strict=True)
            link = case / src.name
            if link.exists() or link.is_symlink():
                link.unlink()
            link.symlink_to(target)

    cam_path = case / "CAMtr_volume_mixing_ratio"
    if not cam_path.is_file():
        fail(f"case has no readable CAMtr_volume_mixing_ratio: {cam_path}")
    cam_hash = sha256(cam_path)
    text = (case / "namelist.input").read_text(encoding="utf-8")
    old_table_text = assignment_text(text, "rrtmgp_udm_frozen_table")
    if old_table_text is None:
        fail("source namelist lacks rrtmgp_udm_frozen_table")
    old_table = Path(old_table_text.strip("'\" ")).expanduser()
    if not old_table.is_file() or sha256(old_table) != sha256(table):
        fail("requested table bytes do not match the frozen case's configured table")
    text, ghg_default_materialized = ensure_ghg_input(text)
    source_debug_level = first_int(text, "debug_level")
    start = datetime(*(first_int(text, f"start_{field}") for field in
                       ("year", "month", "day", "hour", "minute", "second")))
    end = start + timedelta(minutes=1)
    text = set_namelist_values(text, "run_days", ["0"])
    text = set_namelist_values(text, "run_hours", ["0"])
    text = set_namelist_values(text, "run_minutes", ["1"])
    text = set_namelist_values(text, "run_seconds", ["0"])
    for field, value in (("year", end.year), ("month", end.month), ("day", end.day),
                         ("hour", end.hour), ("minute", end.minute), ("second", end.second)):
        text = set_namelist_values(text, f"end_{field}", [str(value)])
    text = set_namelist_values(text, "debug_level", ["1"])
    text = set_namelist_values(text, "rrtmgp_udm_frozen_table", ["'" + str(table) + "'"])
    (case / "namelist.input").write_text(text, encoding="utf-8")
    for key, expected in (("mp_physics", "27"), ("ra_lw_physics", "37"),
                          ("ra_sw_physics", "37"), ("use_mp_re", "1"), ("ghg_input", "1"),
                          ("rrtmgp_udm_frozen_optics", "1")):
        actual = first_int(text, key)
        if actual != int(expected):
            fail(f"expected {key}={expected}, found {actual}")
    return {"source_case": str(source), "source_wrfinput_sha256": sha256(source / "wrfinput_d01"),
            "source_wrfbdy_sha256": sha256(source / "wrfbdy_d01"),
            "working_wrfinput_sha256": sha256(case / "wrfinput_d01"),
            "working_wrfbdy_sha256": sha256(case / "wrfbdy_d01"),
            "cam_table_sha256": cam_hash, "cam_table_resolved": str(cam_path.resolve()),
            "frozen_table_sha256": sha256(table), "frozen_table": str(table),
            "source_namelist_frozen_table": str(old_table.resolve()),
            "ghg_input_default_materialized": ghg_default_materialized,
            "ghg_input_registry_default": 1,
            "source_debug_level": source_debug_level, "working_debug_level": 1,
            "debug_level_changed_for_wrapper_cfc_diagnostic": source_debug_level != 1,
            "namelist_sha256": sha256(case / "namelist.input"),
            "start_time": start.isoformat(), "end_time": end.isoformat()}


def clean_environment(capture_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("WRF_RRTMGP"):
            env.pop(name)
    env["OMP_NUM_THREADS"] = "1"
    env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture_dir)
    env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
    return env


def logged_annual_cam_value(log: str, name: str) -> float:
    match = re.search(rf"(?im)^\s*{name}\s*=\s*([+-]?[0-9.]+(?:[EeDd][+-]?\d+)?)\s+volume mixing ratio", log)
    if not match:
        fail(f"WRF log lacks parsed annual {name} value")
    return float(match.group(1).replace("D", "E").replace("d", "e"))


def logged_wrapper_cfc_values(log: str) -> tuple[float, float, str]:
    lines = log.splitlines()
    for index, line in enumerate(lines):
        if "RRTMG LW CLWRF interpolated GHG values year:" not in line:
            continue
        context = " ".join(lines[index:index + 5])
        match = re.search(
            r"(?i)cfc11vmr:\s*([+-]?[0-9.]+(?:[EeDd][+-]?\d+)?)\s+"
            r"cfc12vmr:\s*([+-]?[0-9.]+(?:[EeDd][+-]?\d+)?)", context)
        if not match:
            fail("first LW wrapper GHG debug record lacks both interpolated CFC values")
        parse = lambda value: float(value.replace("D", "E").replace("d", "e"))
        return parse(match.group(1)), parse(match.group(2)), line.strip()
    fail("WRF log lacks the first LW wrapper interpolated-GHG diagnostic")


def invoke_reference(reference: Path, input_path: Path, output_path: Path,
                     case: Path, table: Path) -> None:
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("WRF_RRTMGP"):
            env.pop(name)
    env["OMP_NUM_THREADS"] = "1"
    env["WRF_RRTMGP_FROZEN_TABLE"] = str(table)
    proc = subprocess.run([str(reference), str(DATA_DIR), str(input_path), str(output_path)],
                          cwd=case, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                          text=True, check=False)
    (case / (output_path.stem + ".log")).write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0 or not output_path.is_file():
        fail(f"reference replay failed: {proc.stdout[-3000:]}")


def decode_frozen_sha(records: dict[str, np.ndarray]) -> str:
    value = records.get("FROZEN_TABLE_SHA256_BYTES")
    if value is None or value.shape != (64, 1):
        fail("V8 replay input lacks frozen-table SHA-256 bytes")
    try:
        return "".join(chr(int(x)) for x in value[:, 0])
    except (ValueError, OverflowError):
        fail("invalid frozen table SHA bytes")


def validate_capture(case: Path, reference: Path, table: Path, log: str) -> dict[str, Any]:
    capture = case / "capture"
    input_path, result_path, raw_path = capture / "lw.input", capture / "lw.result", capture / "lw.raw"
    if not all(p.is_file() for p in (input_path, result_path, raw_path)):
        fail("real case did not produce a complete LW call-1 capture")
    if "Climate GHG input from file from year" not in log or "GHG annual values from CAM trace gas file" not in log:
        fail("WRF log does not prove CAM input was loaded and interpolated")
    annual_cfc11 = logged_annual_cam_value(log, "CFC11")
    annual_cfc12 = logged_annual_cam_value(log, "CFC12")
    wrapper_cfc11, wrapper_cfc12, wrapper_line = logged_wrapper_cfc_values(log)
    phase, nc, nl, overlap, seed, iceflag, records = test_column_replay.read_input(input_path)
    magic = input_path.read_text(encoding="ascii").splitlines()[0].strip()
    if phase != "LW" or nc != 1 or magic not in TRACE_GAS_MAGICS:
        fail(f"expected a single-column LW trace-gas capture, got {magic}")
    if magic in N2_MAGICS:
        n2 = records.get("VMR_N2")
        trace_flag = records.get("TRACE_GASES_PRESENT")
        if n2 is None or n2.shape != (nc, nl) or not np.isfinite(n2).all() or np.any((n2 < 0.0) | (n2 > 1.0)):
            fail(f"{magic} requires finite VMR_N2 with shape {(nc, nl)} and values in [0,1]")
        if trace_flag is None or trace_flag.shape != (1, 1) or not np.isfinite(trace_flag).all() or float(trace_flag.item()) != 1.0:
            fail("real-data CFC test requires TRACE_GASES_PRESENT=1")
    if decode_frozen_sha(records) != sha256(table):
        fail("captured frozen-optics table hash does not match requested table")
    raw_phase, i, j, raw = test_column_replay.read_raw(raw_path)
    if raw_phase != "LW" or (i, j) != (1, 1):
        fail(f"unexpected raw capture phase/location: {raw_phase} ({i},{j})")
    raw_nl = int(raw["DP_HPA"].size)
    if not 1 <= raw_nl <= nl:
        fail(f"invalid raw physical-layer count {raw_nl} for adapter nl={nl}")
    cfc_reports: dict[str, Any] = {}
    for name in CFC_NAMES:
        values = records.get(name)
        native = raw.get(name)
        if values is None or values.shape != (nc, nl) or native is None or native.shape != (raw_nl,):
            fail(f"missing or malformed captured {name}")
        if not np.isfinite(values).all() or np.any(values < 0.0):
            fail(f"{name} is nonfinite or negative")
        test_column_replay.assert_close(values[0, :raw_nl], native,
                                        f"{name}: exact native trace pass-through",
                                        rtol=0.0, atol=0.0)
        if nl > raw_nl:
            test_column_replay.assert_close(values[0, raw_nl:],
                                            np.full(nl - raw_nl, native[-1]),
                                            f"{name}: upper extension holds the model-top value",
                                            rtol=0.0, atol=0.0)
        cfc_reports[name] = {"min_vmr": float(values.min()), "max_vmr": float(values.max()),
                             "sha256": hashlib.sha256(values.tobytes(order="F")).hexdigest()}
    for name, log_value in (("VMR_CFC11", wrapper_cfc11), ("VMR_CFC12", wrapper_cfc12)):
        test_column_replay.assert_close(records[name][0], np.full(nl, log_value),
                                        f"{name}: equals first LW wrapper interpolated value",
                                        rtol=2.e-7, atol=1.e-18)
        if np.allclose(records[name], STATIC_CFC[name], rtol=2.e-7, atol=1.e-18):
            fail(f"{name} remains at its fallback constant despite CAM reader log")
    for name in ("VMR_CFC22", "VMR_CCL4"):
        test_column_replay.assert_close(records[name], np.full((nc, nl), STATIC_CFC[name]),
                                        f"{name}: fixed wrapper value", rtol=2.e-7, atol=1.e-18)

    production = read_result(result_path)
    if "GAS_TAU_RAW" not in production["sections"]:
        fail("production result lacks GAS_TAU_RAW")
    ref_out = capture / "lw.reference.result"
    invoke_reference(reference, input_path, ref_out, case, table)
    reference_result = read_result(ref_out)
    replay = compare(production, reference_result)
    if not replay.get("passed"):
        fail(f"independent {magic} reference replay failed: {replay.get('failed_sections')}")

    zero_records = {name: np.array(value, copy=True) for name, value in records.items()}
    if magic in N2_MAGICS:
        for name in CFC_NAMES:
            del zero_records[name]
        zero_records["TRACE_GASES_PRESENT"][:] = 0.0
    else:
        for name in CFC_NAMES:
            zero_records[name][:] = 0.0
    zero_input = capture / "lw.cfc-zero.input"
    # Re-serialize through the test helper, preserving all unchanged V8 fields.
    from test_lw_trace_gases_scm import render_input
    render_input(zero_input, (phase, nc, nl, overlap, seed, iceflag), zero_records, magic=magic)
    _, _, _, _, _, _, zero_reread = test_column_replay.read_input(zero_input)
    if magic in N2_MAGICS:
        if float(zero_reread["TRACE_GASES_PRESENT"].item()) != 0.0 or any(name in zero_reread for name in CFC_NAMES):
            fail("V12/V13 zero-CFC replay must clear the presence flag and omit all CFC records")
        if not np.array_equal(zero_reread["VMR_N2"], records["VMR_N2"]):
            fail("V12/V13 zero-CFC replay changed the captured N2 profile")
    zero_result = capture / "lw.cfc-zero.result"
    invoke_reference(reference, zero_input, zero_result, case, table)
    zero_sections = read_result(zero_result)["sections"]
    # Attribution compares reference engine to the same reference engine with
    # only CFC VMRs zeroed. Production REAL32 output remains an independent
    # replay-validation check above.
    actual_sections = reference_result["sections"]
    gas_delta = float(np.max(np.abs(actual_sections["GAS_TAU_RAW"] - zero_sections["GAS_TAU_RAW"])))
    flux_delta = {name: float(np.max(np.abs(actual_sections[name] - zero_sections[name])))
                  for name in ("UP", "DN", "HR")}
    if gas_delta <= 0.0 or max(flux_delta.values()) <= 0.0:
        fail("zero-CFC reference variant did not change gas optical depth and LW outputs")
    return {"raw_grid_i_j": [i, j], "input_magic": magic,
            "n2_profile": ({"shape": list(records["VMR_N2"].shape),
                            "min_vmr": float(records["VMR_N2"].min()),
                            "max_vmr": float(records["VMR_N2"].max()),
                            "preserved_in_zero_cfc_variant": True}
                           if magic in N2_MAGICS else None),
            "trace_gases_present": (int(records["TRACE_GASES_PRESENT"].item())
                                    if magic in N2_MAGICS else True),
            "input_header": {"nc": nc, "nl": nl,
            "overlap": overlap, "seed": seed, "iceflag": iceflag},
            "annual_initialization_cam_log_values_vmr": {"CFC11": annual_cfc11, "CFC12": annual_cfc12,
                "role": "CAM file-load/initial interpolation evidence only; time differs from LW call"},
            "first_lw_wrapper_interpolated_values_vmr": {"CFC11": wrapper_cfc11,
                "CFC12": wrapper_cfc12, "log_line": wrapper_line},
            "captured_cfc_vmr": cfc_reports,
            "reader_evidence": "PASS_CAM_file_read_and_annual_interpolation_logged",
            "reference_replay": {"status": "PASS", "sections_compared": replay["sections_compared"],
                                 "max_differences": replay["max_differences"]},
            "zero_cfc_counterfactual_reference_only": {"gas_tau_raw_max_abs_difference": gas_delta,
                "flux_heating_max_abs_difference": flux_delta,
                "zero_input_sha256": sha256(zero_input), "zero_result_sha256": sha256(zero_result)},
            "files": {"input_sha256": sha256(input_path), "raw_sha256": sha256(raw_path),
                      "production_result_sha256": sha256(result_path), "reference_result_sha256": sha256(ref_out)}}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrf", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--case", type=Path, required=True,
                        help="frozen real-data case containing namelist, wrfinput, wrfbdy, and runtime links")
    parser.add_argument("--table", type=Path, required=True,
                        help="frozen-optics table; its bytes must match the seed case table")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new output directory; must not already exist")
    args = parser.parse_args()
    wrf, reference, source, table, out = (p.expanduser().resolve() for p in
                                         (args.wrf, args.reference, args.case, args.table, args.output_dir))
    if out.exists() or not out.parent.is_dir():
        parser.error(f"output directory must be new and parent must exist: {out}")
    for executable in (wrf, reference):
        if not executable.is_file() or not executable.stat().st_mode & 0o111:
            parser.error(f"missing/non-executable executable: {executable}")
    if not table.is_file() or not (source / "namelist.input").is_file():
        parser.error("table or source case is missing")
    case = out / "real-udm27-ra37-ghg1"
    out.mkdir()
    sources_before = source_hashes()
    source_hashes_before = {name: sha256(source / name) for name in
                            ("namelist.input", "wrfinput_d01", "wrfbdy_d01",
                             "CAMtr_volume_mixing_ratio")}
    binary_hashes = {"wrf": sha256(wrf), "reference": sha256(reference), "table": sha256(table)}
    case_provenance = prepare_case(source, case, table)
    capture = case / "capture"
    capture.mkdir()
    initial_hashes = {name: sha256(case / name) for name in ("wrfinput_d01", "wrfbdy_d01")}
    proc = subprocess.run([str(wrf)], cwd=case, env=clean_environment(capture),
                          stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, check=False)
    log = proc.stdout
    (case / "wrf.log").write_text(log, encoding="utf-8")
    if proc.returncode != 0 or SUCCESS not in log:
        fail(f"real-data WRF failed (rc={proc.returncode}); log tail:\n{log[-4000:]}")
    if any(sha256(case / name) != value for name, value in initial_hashes.items()):
        fail("WRF modified its input or boundary file")
    capture_result = validate_capture(case, reference, table, log)
    sources_after = source_hashes()
    if sources_before != sources_after:
        fail("source changed during real-case check")
    if source_hashes_before != {name: sha256(source / name) for name in source_hashes_before}:
        fail("frozen source-case inputs changed")
    if binary_hashes != {"wrf": sha256(wrf), "reference": sha256(reference), "table": sha256(table)}:
        fail("an executable or frozen table changed during run")
    receipt = {"status": "PASS_REAL_CASE_DYNAMIC_CAM_CFC_CAPTURE_AND_REPLAY",
        "scope": {"real_data_forecast_minutes": 1, "microphysics": "UDM27",
                  "radiation": "RRTMGP37/37", "ghg_input": 1,
                  "frozen_optics_mode": 1, "accuracy_claimed": False,
                  "CFC11_CFC12_source": "CAM table loaded during real-run physics initialization and interpolation logged",
                  "CFC22_CCL4_source": "wrapper fixed constants; not supplied by the CAM reader"},
        "provenance": {"source_sha256_before_after": sources_before,
                       "executables_and_table_sha256": binary_hashes,
                       "source_case_input_sha256_before_after": source_hashes_before,
                       "case": case_provenance,
                       "active_CAM_table_target": case_provenance["cam_table_resolved"]},
        "run": {"returncode": proc.returncode, "success_marker": SUCCESS,
                "log_sha256": sha256(case / "wrf.log"), "log_path": str(case / "wrf.log"),
                "capture_call": 1, "capture_path": str(capture)},
        "capture_validation": capture_result}
    rendered = json.dumps(receipt, indent=2, sort_keys=True) + "\n"
    (out / "lw-trace-gases-realcase-result.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
