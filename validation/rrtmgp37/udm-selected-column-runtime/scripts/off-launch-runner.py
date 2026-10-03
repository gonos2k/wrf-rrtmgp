#!/usr/bin/env python3
"""Prepare or run the bounded serial selected-column restart audit.

Default mode is preparation only. Execution requires explicit approved binary
and source-tree SHA-256 values; each invocation requires a new output directory.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
from typing import Any

import numpy as np
from netCDF4 import Dataset


PLAN_REL = Path("build/udm-selected-column-work/build/real12h-selected-audit-plan/plan-v2.json")
SOURCE_REL = Path("build/udm-selected-real-wrf/source")
EXE_REL = SOURCE_REL / "WRF/main/wrf.exe"
SOURCE_MANIFEST_REL = Path("build/udm-selected-real-wrf/source-manifest.json")
BUILD_RECEIPT_REL = Path("build/udm-selected-real-wrf/build-receipt-v2.json")
ASSET_SHA = {
    "rrtmgp-gas-lw-g128.nc": "70ad65d116531122660318e5da2a2af9db74b425916202860e9527ef2375b8f6",
    "rrtmgp-gas-sw-g112.nc": "361ed541324068ded28a275a4dd757bcaa0a845aebefa630f43a04678668fe62",
    "rrtmgp-clouds-lw-bnd.nc": "09d6704c5b863b4c3ceb417d20bb3076ec492e6bf2dfbcc9f3c5996a3706f0b0",
    "rrtmgp-clouds-sw-bnd.nc": "7671835992a45afe66244b591a02c0b3df73d7d59ecb746bbffd9763497651cd",
    "frozen-ice-psd-moments.nc": "8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583",
}
SUCCESS_TEXT = "SUCCESS COMPLETE WRF"
MUTABLE_RE = re.compile(r"^(wrfout_|wrfrst_|rsl\.|namelist\.output$|.*\.log$)")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def json_write(path: Path, obj: Any) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n")


def json_value(value: Any) -> Any:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="replace")
    if isinstance(value, np.ndarray):
        return [json_value(item) for item in value.tolist()]
    if isinstance(value, np.generic):
        return json_value(value.item())
    if isinstance(value, (list, tuple)):
        return [json_value(item) for item in value]
    return value


def verify_build_manifest(workspace: Path, source: Path, exe: Path) -> tuple[str, dict[str, Any]]:
    manifest_path = workspace / SOURCE_MANIFEST_REL
    receipt_path = workspace / BUILD_RECEIPT_REL
    if not manifest_path.is_file() or not receipt_path.is_file():
        raise RuntimeError("fresh-build source manifest/receipt is required")
    build_receipt = json.loads(receipt_path.read_text())
    manifest_sha = sha256(manifest_path)
    if build_receipt.get("status") != "BUILD_PASS" or manifest_sha != build_receipt.get("source_manifest_sha256"):
        raise RuntimeError("build receipt does not authenticate the staged source manifest")
    if build_receipt.get("source_files_modified_or_missing_during_build"):
        raise RuntimeError("build receipt reports source files changed/missing during compilation")
    manifest = json.loads(manifest_path.read_text())
    checked = 0
    for entry in manifest.get("files", []):
        path = source / entry["path"]
        if entry["kind"] == "file":
            if not path.is_file() or sha256(path) != entry["sha256"]:
                raise RuntimeError(f"staged source mismatch: {entry['path']}")
            checked += 1
        elif entry["kind"] == "symlink":
            if not path.is_symlink() or os.readlink(path) != entry["target"]:
                raise RuntimeError(f"staged symlink mismatch: {entry['path']}")
            if hashlib.sha256(entry["target"].encode()).hexdigest() != entry["sha256"]:
                raise RuntimeError(f"bad source-manifest symlink digest: {entry['path']}")
            checked += 1
        else:
            raise RuntimeError(f"unsupported manifest entry kind: {entry.get('kind')}")
    expected_exe = build_receipt["executables"]["wrf.exe"]["sha256"]
    actual_exe = sha256(exe) if exe.is_file() else None
    if actual_exe != expected_exe:
        raise RuntimeError(f"built executable does not match build receipt: {actual_exe} != {expected_exe}")
    return manifest_sha, {"manifest_path": str(manifest_path), "manifest_sha256": manifest_sha,
                          "build_receipt_sha256": sha256(receipt_path), "checked_entries": checked,
                          "base_commit": manifest.get("base_commit"),
                          "build_compiler": build_receipt.get("compiler"),
                          "configure_choice": build_receipt.get("configure_choice"),
                          "build_executable_sha256": actual_exe}


def verify_source_shape(root: Path) -> None:
    trace = root / "WRF/phys/module_ra_rrtmgp_trace.F"
    driver = root / "WRF/phys/module_radiation_driver.F"
    physics = root / "WRF/phys/module_physics_init.F"
    for path in (trace, driver, physics):
        if not path.is_file():
            raise RuntimeError(f"merged selected-column source missing: {path}")
    checks = [
        (trace, "WRF_RRTMGP_COLUMN_I"), (trace, "trace_column_selection"),
        (trace, "WRF_RRTMGP_CAPTURE_CALL"), (driver, "selected_column"),
        (driver, "audit_step=itimestep"), (physics, "rrtmgp_udm_frozen_optics"),
    ]
    for path, marker in checks:
        if marker not in path.read_text(errors="replace"):
            raise RuntimeError(f"source does not contain expected merged feature {marker}: {path}")
    driver_text = driver.read_text()
    if "MOD(itimestep,stepra)" not in driver_text or "1+ra_call_offset" not in driver_text:
        raise RuntimeError("source radiation schedule expression changed; review call-2 mapping")
    physics_text = physics.read_text()
    if "STEPRA = nint(RADT*60./DT)" not in physics_text:
        raise RuntimeError("source STEPRA derivation changed; review predicted activation steps")


def verify_netcdf_restart(path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    with Dataset(path) as ds:
        dims = {name: len(dim) for name, dim in ds.dimensions.items()}
        expected_dims = plan["restart"]["dimensions"]
        for key, value in expected_dims.items():
            if dims.get(key) != value:
                raise RuntimeError(f"restart dimension {key}: expected {value}, got {dims.get(key)}")
        text = b"".join(ds.variables["Times"][0]).decode("ascii")
        expected_time = plan["restart"]["clock"]
        if text != expected_time:
            raise RuntimeError(f"restart timestamp mismatch: {text} != {expected_time}")
        i = int(plan["point_wrf_one_based"]["i"]) - 1
        j = int(plan["point_wrf_one_based"]["j"]) - 1
        k = int(plan["point_wrf_one_based"]["k_checkpoint"]) - 1
        values = {}
        for var, key in (("QGRAUP", "qg_kg_kg"), ("QHAIL", "qh_kg_kg")):
            actual = float(ds.variables[var][0, k, j, i])
            expected = float(plan["checkpoint_state"][key])
            if not np.isclose(actual, expected, rtol=0., atol=1.e-12):
                raise RuntimeError(f"restart checkpoint {var} mismatch: {actual} vs {expected}")
            values[var] = actual
        cf = float(ds.variables["CLDFRA"][0, k, j, i])
        if not np.isclose(cf, plan["checkpoint_state"]["cloud_fraction"], rtol=0., atol=1.e-7):
            raise RuntimeError(f"checkpoint CF mismatch: {cf}")
        dry_mass = -float(ds["DNW"][0, k]) * (
            float(ds["C1H"][0, k]) * (float(ds["MU_2"][0, j, i]) + float(ds["MUB"][0, j, i]))
            + float(ds["C2H"][0, k])) / 9.81
        if not np.isclose(dry_mass, plan["checkpoint_state"]["native_dry_layer_mass_kg_m2"], rtol=0., atol=1.e-8):
            raise RuntimeError(f"checkpoint dry-layer mass mismatch: {dry_mass}")
        if not np.isclose(values["QGRAUP"] * dry_mass * 1000., plan["checkpoint_state"]["gwp_g_m2"], rtol=0., atol=1.e-6):
            raise RuntimeError("checkpoint graupel path mismatch")
        if not np.isclose(values["QHAIL"] * dry_mass * 1000., plan["checkpoint_state"]["hwp_g_m2"], rtol=0., atol=1.e-6):
            raise RuntimeError("checkpoint hail path mismatch")
        return {"dimensions": dims, "time": text, "k_wrf_one_based": k + 1,
                "i_wrf_one_based": i + 1, "j_wrf_one_based": j + 1,
                "QGRAUP": values["QGRAUP"], "QHAIL": values["QHAIL"],
                "CLDFRA": cf, "native_dry_mass_kg_m2": dry_mass,
                "QGRAUP_path_g_m2": values["QGRAUP"] * dry_mass * 1000.,
                "QHAIL_path_g_m2": values["QHAIL"] * dry_mass * 1000.}


def set_nml(text: str, group: str, key: str, value: str) -> str:
    match = re.search(rf"(?ims)^([ \t]*&{re.escape(group)}\b[^\n]*\n)(.*?)(^[ \t]*/)", text)
    if not match:
        raise RuntimeError(f"namelist group &{group} missing")
    header, body, closer = match.groups()
    assignment = re.compile(rf"(?im)^([ \t]*){re.escape(key)}[ \t]*=.*$")
    if assignment.search(body):
        body = assignment.sub(lambda m: f"{m.group(1)}{key} = {value}", body, count=1)
    else:
        body = body.rstrip("\n") + f"\n {key} = {value}\n"
    return text[:match.start()] + header + body + closer + text[match.end():]


def make_namelist(template: Path, data_path: Path, lut: Path) -> str:
    text = template.read_text()
    values = {
        "run_days": "0", "run_hours": "0", "run_minutes": "11", "run_seconds": "0",
        "start_year": "2010, 2010, 2010", "start_month": "6, 6, 6",
        "start_day": "11, 11, 11", "start_hour": "12, 12, 12",
        "start_minute": "0, 0, 0", "start_second": "0, 0, 0",
        "end_year": "2010, 2010, 2010", "end_month": "6, 6, 6",
        "end_day": "11, 11, 11", "end_hour": "12, 12, 12",
        "end_minute": "11, 11, 11", "end_second": "0, 0, 0",
        "restart": ".true.", "override_restart_timers": ".true.",
        "history_interval": "1, 1, 1", "frames_per_outfile": "1, 1, 1",
        "iofields_filename": "'selected_audit_iofields.txt'",
        "ignore_iofields_warning": ".false.",
    }
    for key, value in values.items():
        text = set_nml(text, "time_control", key, value)
    physics = {
        "max_dom": "1", "time_step": "60", "use_mp_re": "1",
        "mp_physics": "27", "ra_lw_physics": "37", "ra_sw_physics": "37",
        "radt": "10", "ra_call_offset": "0", "aer_opt": "0", "cldovrlp": "2",
        "rrtmgp_data_path": f"'{data_path.resolve()}'",
        "rrtmgp_udm_frozen_optics": "1",
        "rrtmgp_udm_frozen_table": f"'{lut.resolve()}'",
    }
    # max_dom and time_step are in &domains; physics options are in &physics.
    text = set_nml(text, "domains", "max_dom", physics.pop("max_dom"))
    text = set_nml(text, "domains", "time_step", physics.pop("time_step"))
    for key, value in physics.items():
        text = set_nml(text, "physics", key, value)
    return text


def ignored_run_asset(_directory: str, names: list[str]) -> set[str]:
    ignored = set()
    for name in names:
        if MUTABLE_RE.match(name) or name in {"wrf.exe", "real.exe", "wrfinput_d01", "wrfbdy_d01"}:
            ignored.add(name)
    return ignored


def immutable_tree_hashes(run_dir: Path) -> dict[str, str]:
    hashes = {}
    for p in sorted(run_dir.rglob("*")):
        if p.relative_to(run_dir).parts[0] in {"audit", "capture"}:
            continue
        if not p.is_file() or MUTABLE_RE.match(p.name) or p.name in {"wrf.exe", "real.exe"}:
            continue
        hashes[p.relative_to(run_dir).as_posix()] = sha256(p)
    return hashes


def stage_cases(work: Path, workspace: Path, source: Path, plan: dict[str, Any], exe: Path | None) -> dict[str, Any]:
    template = workspace / "build/udm-frozen-restart-plan/trial-mode1-0to12/namelist.input"
    source_run = source / "WRF/run"
    restart_src = workspace / plan["restart"]["path"]
    wrfinput_src = workspace / plan["inputs"]["wrfinput"]["path"]
    wrfbdy_src = workspace / plan["inputs"]["wrfbdy"]["path"]
    lut = workspace / plan["inputs"]["frozen_mode1_table"]["path"]
    cases = {}
    for name in ("audit-off", "audit-on"):
        case = work / name
        run_dir = case / "run"
        case.mkdir()
        shutil.copytree(source_run, run_dir, ignore=ignored_run_asset)
        for src, dest in ((restart_src, run_dir / "wrfrst_d01_2010-06-11_12:00:00"),
                          (wrfinput_src, run_dir / "wrfinput_d01"),
                          (wrfbdy_src, run_dir / "wrfbdy_d01")):
            shutil.copy2(src, dest)
        nml = make_namelist(template, source_run, lut)
        (run_dir / "namelist.input").write_text(nml)
        shutil.copy2(source / "WRF/test/rrtmgp/radiation_iofields.txt",
                     run_dir / "selected_audit_iofields.txt")
        (run_dir / "audit").mkdir()
        (run_dir / "capture").mkdir()
        if exe is not None and exe.is_file():
            shutil.copy2(exe, run_dir / "wrf.exe")
        cases[name] = {
            "run_dir": str(run_dir), "namelist_sha256": sha256(run_dir / "namelist.input"),
            "immutable_assets": immutable_tree_hashes(run_dir),
            "wrfinput_sha256": sha256(run_dir / "wrfinput_d01"),
            "wrfbdy_sha256": sha256(run_dir / "wrfbdy_d01"),
            "restart_sha256": sha256(run_dir / "wrfrst_d01_2010-06-11_12:00:00"),
            "executable_copied": (run_dir / "wrf.exe").is_file(),
        }
    if cases["audit-off"]["namelist_sha256"] != cases["audit-on"]["namelist_sha256"]:
        raise RuntimeError("OFF/ON namelists differ")
    for field in ("immutable_assets", "wrfinput_sha256", "wrfbdy_sha256", "restart_sha256"):
        if cases["audit-off"][field] != cases["audit-on"][field]:
            raise RuntimeError(f"OFF/ON staged inputs differ: {field}")
    return cases


def parse_audit(path: Path) -> dict[str, Any]:
    with path.open(newline="") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        raise RuntimeError("same_state.csv has no rows")
    byphase: dict[str, set[tuple[int, float]]] = {"LW": set(), "SW": set()}
    for row in rows:
        phase = row["phase"].strip()
        if phase not in byphase:
            raise RuntimeError(f"unexpected audit phase {phase}")
        byphase[phase].add((int(row["step"]), float(row["source_seconds"])))
    for phase, activations in byphase.items():
        if len(activations) != 2:
            raise RuntimeError(f"expected 2 {phase} activations, got {sorted(activations)}")
    if byphase["LW"] != byphase["SW"]:
        raise RuntimeError("LW and SW activation step/time differ")
    activations = sorted(byphase["LW"])
    expected_steps = [721, 731]
    if [step for step, _ in activations] != expected_steps:
        raise RuntimeError(f"radiation schedule mismatch: expected steps {expected_steps}, got {activations}")
    groups: dict[tuple[str, int, float], list[dict[str, str]]] = {}
    for row in rows:
        key = (row["phase"].strip(), int(row["step"]), float(row["source_seconds"]))
        groups.setdefault(key, []).append(row)
    for key, group in groups.items():
        expected_metrics = (2 + 39) if key[0] == "LW" else (4 + 39)
        for metric in {r["metric"] for r in group}:
            match = [r for r in group if r["metric"] == metric]
            coordinates = {(int(r["i"]), int(r["j"])) for r in match}
            if len(match) != 2 or coordinates != {(169, 80), (0, 0)}:
                raise RuntimeError(f"audit rows not selected-column cell+aggregate for {key}/{metric}")
            if any(int(r["sample_count"]) != 32 for r in match):
                raise RuntimeError(f"audit seed sample count !=32 for {key}/{metric}")
        if len({r["metric"] for r in group}) != expected_metrics:
            raise RuntimeError(f"unexpected metrics in {key}")
    return {"activations": [{"step": s, "source_seconds": t} for s, t in activations],
            "rows": len(rows), "groups": len(groups), "metrics_per_phase": {"LW": 41, "SW": 43},
            "scope_checked": "selected_column cell plus one-cell (0,0) aggregate"}


def parse_raw_records(path: Path) -> tuple[dict[str, list[float]], list[str]]:
    lines = path.read_text().splitlines()
    if len(lines) < 3 or not lines[0].startswith("RRTMGP_RAW_V"):
        raise RuntimeError(f"invalid raw capture format: {path}")
    records: dict[str, list[float]] = {}
    i = 2
    while i < len(lines):
        parts = lines[i].split()
        i += 1
        if len(parts) != 2:
            continue
        try:
            n = int(parts[1])
        except ValueError:
            continue
        values = []
        for _ in range(n):
            if i >= len(lines):
                raise RuntimeError(f"truncated raw capture record {parts[0]}")
            values.append(float(lines[i].strip()))
            i += 1
        records[parts[0]] = values
    return records, lines[:2]


def parse_result_records(path: Path) -> tuple[dict[str, list[float]], list[int], list[str]]:
    lines = path.read_text().splitlines()
    if len(lines) < 2 or not lines[0].startswith("RRTMGP_RESULT_V"):
        raise RuntimeError(f"invalid result capture format: {path}")
    header = lines[1].split()
    if len(header) != 3:
        raise RuntimeError(f"invalid result dimensions: {path}")
    dims = [int(x) for x in header[1:]]
    records: dict[str, list[float]] = {}
    i = 2
    while i < len(lines):
        parts = lines[i].split()
        i += 1
        if len(parts) != 4:
            continue
        try:
            n = int(parts[1]) * int(parts[2]) * int(parts[3])
        except ValueError:
            continue
        if n < 0 or i + n > len(lines):
            raise RuntimeError(f"truncated result record {parts[0]}")
        records[parts[0]] = [float(x.strip()) for x in lines[i:i + n]]
        i += n
    return records, dims, lines[:2]


def compare_history(off_run: Path, on_run: Path, audit_rows: list[dict[str, str]], start: dt.datetime,
                    raw_capture: dict[str, dict[str, list[float]]]) -> dict[str, Any]:
    off_files = sorted(off_run.glob("wrfout_d01_*"))
    on_files = sorted(on_run.glob("wrfout_d01_*"))
    if not off_files or len(off_files) != len(on_files):
        raise RuntimeError(f"history file count differs/empty: OFF={len(off_files)} ON={len(on_files)}")
    fields_checked = 0
    timestamps_off: list[dt.datetime] = []
    mapping = {
        ("LW", "SURFACE_DOWN"): ("GLW", None), ("LW", "TOA_UP"): ("OLR", None),
        ("SW", "SURFACE_DOWN"): ("SWDNB", None), ("SW", "TOA_UP"): ("SWUPT", None),
        ("SW", "SW_NET"): ("GSW", None), ("SW", "SW_DIRECT"): ("SWDDIR", None),
    }
    all_history: list[tuple[dt.datetime, dict[str, np.ndarray]]] = []
    nctimes = []
    xtime_alignment = []
    for file in off_files:
        with Dataset(file) as ds:
            ds.set_auto_maskandscale(False)
            times = [b"".join(row).decode("ascii").strip() for row in ds.variables["Times"][:]]
            for record_index, text in enumerate(times):
                stamp = dt.datetime.strptime(text, "%Y-%m-%d_%H:%M:%S")
                timestamps_off.append(stamp)
                xtime = float(np.asarray(ds.variables["XTIME"][record_index]))
                delta = abs((stamp - start).total_seconds() - xtime * 60.)
                if delta > 1.e-2:
                    raise RuntimeError(f"absolute Times and XTIME disagree by {delta}s at {text}")
                xtime_alignment.append({"time": text, "xtime_minutes": xtime, "delta_seconds": delta})
            nctimes.extend(times)
            names = {n for n, v in ds.variables.items() if np.issubdtype(v.dtype, np.number)}
            for idx, text in enumerate(times):
                values = {n: np.array(ds.variables[n][idx]) for n in names}
                all_history.append((dt.datetime.strptime(text, "%Y-%m-%d_%H:%M:%S"), values))
    on_times = []
    for file in on_files:
        with Dataset(file) as ds:
            on_times.extend([b"".join(row).decode("ascii").strip() for row in ds.variables["Times"][:]])
    if nctimes != on_times:
        raise RuntimeError("OFF/ON absolute Times differ")
    if len(set(nctimes)) != len(nctimes) or not nctimes:
        raise RuntimeError("history Times must be nonempty and unique")
    if sorted(timestamps_off) != timestamps_off:
        raise RuntimeError("history Times are not ordered")
    metadata_differences = []
    global_metadata_differences = []
    dimension_differences = []
    fill_counts: dict[str, int] = {}
    for foff, fon in zip(off_files, on_files):
        with Dataset(foff) as a, Dataset(fon) as b:
            a.set_auto_maskandscale(False)
            b.set_auto_maskandscale(False)
            if a.variables["Times"][:].tobytes() != b.variables["Times"][:].tobytes():
                raise RuntimeError(f"Times bytes differ: {foff.name}")
            dims_a = {n: (len(d), d.isunlimited()) for n, d in a.dimensions.items()}
            dims_b = {n: (len(d), d.isunlimited()) for n, d in b.dimensions.items()}
            if dims_a != dims_b:
                dimension_differences.append({"file": foff.name, "off": dims_a, "on": dims_b})
                raise RuntimeError(f"history dimensions differ: {foff.name}")
            global_a = {k: json_value(a.getncattr(k)) for k in a.ncattrs()}
            global_b = {k: json_value(b.getncattr(k)) for k in b.ncattrs()}
            if global_a != global_b:
                global_metadata_differences.append({"file": foff.name, "off": global_a, "on": global_b})
            nums_a = {n for n, v in a.variables.items() if np.issubdtype(v.dtype, np.number)}
            nums_b = {n for n, v in b.variables.items() if np.issubdtype(v.dtype, np.number)}
            if nums_a != nums_b:
                raise RuntimeError(f"numeric history variable set differs: {nums_a ^ nums_b}")
            vars_a, vars_b = set(a.variables), set(b.variables)
            if vars_a != vars_b:
                raise RuntimeError(f"history variable set differs: {foff.name}")
            for name in sorted(vars_a):
                va, vb = a[name], b[name]
                if va.dimensions != vb.dimensions or va.dtype != vb.dtype:
                    raise RuntimeError(f"history variable dimensions/dtype differ: {foff.name}/{name}")
                attrs_a, attrs_b = va.ncattrs(), vb.ncattrs()
                attr_values_a = {k: json_value(va.getncattr(k)) for k in attrs_a}
                attr_values_b = {k: json_value(vb.getncattr(k)) for k in attrs_b}
                if attrs_a != attrs_b or attr_values_a != attr_values_b:
                    metadata_differences.append({"file": foff.name, "variable": name,
                                                 "off_dimensions": va.dimensions,
                                                 "on_dimensions": vb.dimensions,
                                                 "off_attrs": attr_values_a, "on_attrs": attr_values_b})
            for name in sorted(nums_a):
                av, bv = np.asarray(a[name][:]), np.asarray(b[name][:])
                if av.shape != bv.shape or av.dtype != bv.dtype or av.tobytes() != bv.tobytes():
                    raise RuntimeError(f"history variable not bitwise identical: {foff.name}/{name}")
                attrs_a = a[name].ncattrs()
                for attr in ("_FillValue", "missing_value", "scale_factor", "add_offset"):
                    va = a[name].getncattr(attr) if attr in attrs_a else None
                    vb = b[name].getncattr(attr) if attr in attrs_b else None
                    if (va is None) != (vb is None) or (va is not None and not np.array_equal(np.asarray(va), np.asarray(vb))):
                        raise RuntimeError(f"fill/scale metadata differs for {foff.name}/{name}:{attr}")
                fill_mask = np.zeros(av.shape, dtype=bool)
                for attr in ("_FillValue", "missing_value"):
                    if attr in attrs_a:
                        for fv in np.asarray(a[name].getncattr(attr)).reshape(-1):
                            fill_mask |= av == fv
                fill_counts[name] = fill_counts.get(name, 0) + int(np.count_nonzero(fill_mask))
                if not np.isfinite(av[~fill_mask]).all():
                    raise RuntimeError(f"non-finite unmasked values in {foff.name}/{name}")
                fields_checked += 1
    run_window_start = dt.datetime(2010, 6, 11, 12, 0)
    run_window_end = dt.datetime(2010, 6, 11, 12, 11)
    if timestamps_off[0] > run_window_start or timestamps_off[-1] < run_window_end:
        raise RuntimeError(f"history does not span requested restart window: {nctimes[0]}..{nctimes[-1]}")
    expected_times = [run_window_start + dt.timedelta(minutes=m) for m in range(0, 12)]
    if timestamps_off not in (expected_times, expected_times[1:]):
        raise RuntimeError(f"history must contain 1-minute timestamps through 12:11: {nctimes}")
    history_required = {"GLW", "OLR", "SWDNB", "SWUPT", "GSW", "SWDDIR", "SWDDIF", "RTHRATLW", "RTHRATSW"}
    final_names = set()
    with Dataset(off_files[-1]) as ds:
        ds.set_auto_maskandscale(False)
        final_names = set(ds.variables)
    if not history_required.issubset(final_names):
        raise RuntimeError(f"history missing requested radiation variables: {sorted(history_required-final_names)}")
    # The exact history offset is established from source time plus output data,
    # not assumed from an SCM convention. Only surface/TOA fluxes are compared.
    match_rows = []
    for row in audit_rows:
        phase, metric = row["phase"].strip(), row["metric"].strip()
        if (int(row["i"]), int(row["j"])) != (169, 80):
            continue
        field_info = mapping.get((phase, metric))
        if field_info is None and metric.startswith("HEAT_"):
            # Only call 2 is captured, so exact PI for the first activation is
            # unavailable. Keep its flux comparisons but do not infer heating.
            if int(row["step"]) != 731:
                continue
            try:
                k = int(metric.split("_", 1)[1]) - 1
            except ValueError:
                continue
            field_info = ("RTHRATLW" if phase == "LW" else "RTHRATSW", k)
        if field_info is None:
            continue
        field, k_index = field_info
        source_sec = float(row["source_seconds"])
        target = float(row["value37"])
        matches = []
        for stamp, vals in all_history:
            elapsed = (stamp - start).total_seconds()
            offset = elapsed - source_sec
            if abs(offset - 60.) > 1.e-4:
                continue
            if field not in vals:
                continue
            if field in {"RTHRATLW", "RTHRATSW"}:
                pi_values = raw_capture[phase].get("PI")
                if pi_values is None or k_index >= len(pi_values):
                    continue
                val = float(vals[field][k_index, 79, 168]) * pi_values[k_index] * 86400.0
            else:
                val = float(vals[field][79, 168])
            if np.isclose(val, target, rtol=5.e-7, atol=2.e-5):
                matches.append({"offset_seconds": int(offset), "time": stamp.strftime("%Y-%m-%d_%H:%M:%S"),
                                "history_value": val, "audit_value": target})
        if not matches:
            raise RuntimeError(f"history flux {phase}/{metric} did not match at audit source time + actual dt (60s)")
        match_rows.append({"phase": phase, "metric": metric, "step": int(row["step"]), "matches": matches})
    return {"history_files_off": [p.name for p in off_files], "history_files_on": [p.name for p in on_files],
            "times": nctimes, "numeric_fields_checked_per_file": fields_checked // len(off_files),
            "numeric_fields_bitwise_equal": True, "requested_direct_heating_fields_present": sorted(history_required),
            "xtime_absolute_time_alignment": xtime_alignment, "fill_value_counts": fill_counts,
            "metadata_differences": metadata_differences,
            "global_metadata_differences": global_metadata_differences,
            "dimension_differences": dimension_differences,
            "history_time_mapping": "absolute Times and XTIME*60 agree; audit source time + actual dt=60s",
            "audit_flux_matches": match_rows}


def run_case(case: Path, env: dict[str, str], timeout: int) -> dict[str, Any]:
    run_dir = case / "run"
    log = run_dir / "wrf.stdout.log"
    started = time.time()
    rc = None
    timed_out = False
    with log.open("wb") as stream:
        try:
            proc = subprocess.run([str(run_dir / "wrf.exe")], cwd=run_dir, env=env,
                                  stdout=stream, stderr=subprocess.STDOUT, timeout=timeout, check=False)
            rc = proc.returncode
        except subprocess.TimeoutExpired:
            timed_out = True
    log_text = log.read_text(errors="replace") if log.exists() else ""
    success = SUCCESS_TEXT in log_text or any(SUCCESS_TEXT in p.read_text(errors="replace")
                                               for p in run_dir.glob("rsl.error.*"))
    return {"returncode": rc, "timed_out": timed_out, "success_marker": success,
            "elapsed_seconds": time.time() - started, "log": log.name,
            "log_sha256": sha256(log) if log.exists() else None,
            "tail": log_text[-4000:]}


def clean_env(base: dict[str, str]) -> dict[str, str]:
    env = {k: v for k, v in base.items()
           if not k.startswith(("WRF_RRTMGP_", "WRF_UDM_BOUNDARY_CAPTURE"))}
    env["OMP_NUM_THREADS"] = "1"
    env["OMP_DYNAMIC"] = "FALSE"
    env["OMP_STACKSIZE"] = "512M"
    env["OPENBLAS_NUM_THREADS"] = "1"
    return env


def run_and_validate(work: Path, cases: dict[str, Any], base_env: dict[str, str], timeout: int,
                     assets_before: dict[str, Any], source: Path, exe: Path,
                     workspace: Path, phase_selection: str, off_run_dir: Path | None) -> dict[str, Any]:
    lock_path = work.parent / ".selected-column-audit.lock"
    with lock_path.open("a+") as lock:
        try:
            fcntl.flock(lock.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError as exc:
            raise RuntimeError(f"another selected-column audit is running (lock {lock_path})") from exc
        results = {}
        progress_path = work / "run-progress.json"
        if phase_selection == "on":
            if off_run_dir is None or not off_run_dir.resolve().is_dir():
                raise RuntimeError("phase=on requires --off-run-dir from a successful audit-off run")
            candidate = work / "audit-on/run"
            off_candidate = off_run_dir.resolve()
            off_receipt_path = off_candidate.parent.parent / "receipt.json"
            if not off_receipt_path.is_file():
                raise RuntimeError("audit-off run receipt missing beside --off-run-dir")
            off_receipt = json.loads(off_receipt_path.read_text())
            if off_receipt.get("status") != "OFF_COMPLETE_AWAITING_ON" or off_receipt.get("phase") != "off":
                raise RuntimeError("--off-run-dir receipt is not a successful OFF-only completion")
            if off_receipt.get("executable_sha256") != sha256(exe) or off_receipt.get("source_tree_sha256") != assets_before["source_tree_sha256"]:
                raise RuntimeError("OFF run executable/source provenance differs from current ON build")
            for filename in ("namelist.input", "wrfinput_d01", "wrfbdy_d01",
                             "wrfrst_d01_2010-06-11_12:00:00", "selected_audit_iofields.txt"):
                if not (off_candidate / filename).is_file() or sha256(off_candidate / filename) != sha256(candidate / filename):
                    raise RuntimeError(f"provided audit-off run has different immutable input {filename}")
        common = clean_env(base_env)
        selected_names = {"off": ["audit-off"], "on": ["audit-on"], "both": ["audit-off", "audit-on"]}[phase_selection]
        for name in selected_names:
            case = work / name
            env = dict(common)
            if name == "audit-on":
                env.update({
                    "WRF_RRTMGP_AUDIT_DIR": str(case / "run/audit"),
                    "WRF_RRTMGP_AUDIT_SEEDS": "32",
                    "WRF_RRTMGP_COLUMN_I": "169", "WRF_RRTMGP_COLUMN_J": "80",
                    "WRF_RRTMGP_CAPTURE_DIR": str(case / "run/capture"),
                    "WRF_RRTMGP_CAPTURE_CALL": "2",
                })
            results[name] = run_case(case, env, timeout)
            json_write(progress_path, {"case_runs": results, "completed_case_count": len(results)})
            if results[name]["returncode"] != 0 or results[name]["timed_out"] or not results[name]["success_marker"]:
                raise RuntimeError(f"WRF case failed: {name}")
        if phase_selection == "off":
            post_source_sha, post_source_info = verify_build_manifest(workspace, source, exe)
            post_shared = snapshot_shared_assets(source, workspace)
            if post_source_sha != assets_before["source_tree_sha256"] or post_shared != assets_before["shared_assets"]:
                raise RuntimeError("immutable source/data changed during OFF run")
            if immutable_tree_hashes(work / "audit-off/run") != cases["audit-off"]["immutable_assets"]:
                raise RuntimeError("staged immutable inputs changed during OFF run")
            return {"status": "OFF_COMPLETE_AWAITING_ON", "case_runs": results,
                    "phase": "off",
                    "executable_sha256": sha256(exe),
                    "source_tree_sha256": assets_before["source_tree_sha256"],
                    "off_run_directory": str(work / "audit-off/run"),
                    "no_audit_env": True, "native4_selector_set": False,
                    "source_manifest_after": post_source_info, "shared_assets_unchanged": True}
        off = (off_run_dir.resolve() if phase_selection == "on" and off_run_dir else work / "audit-off/run")
        on = work / "audit-on/run"
        audit = parse_audit(on / "audit/same_state.csv")
        audit_rows = list(csv.DictReader((on / "audit/same_state.csv").open(newline="")))
        raw_check = {}
        raw_capture = {}
        for phase in ("LW", "SW"):
            records, headers = parse_raw_records(on / f"capture/{phase}.input")
            raw_capture[phase] = records
            raw_header = headers[1].split()
            if raw_header != [phase, "169", "80", "39"]:
                raise RuntimeError(f"{phase} capture coordinates/levels are wrong: {raw_header}")
            if "RADIATION_STEP" not in records or "SOURCE_TIME_SECONDS" not in records:
                raise RuntimeError(f"{phase} second-call raw capture missing time/step metadata")
            if "PI" not in records or len(records["PI"]) != 39 or not np.isfinite(records["PI"]).all():
                raise RuntimeError(f"{phase} raw capture has invalid layer PI")
            if "FROZEN_TABLE_SHA256_BYTES" not in records:
                raise RuntimeError(f"{phase} raw capture is missing frozen LUT digest metadata")
            frozen_sha = "".join(chr(int(round(x))) for x in records["FROZEN_TABLE_SHA256_BYTES"])
            if frozen_sha != ASSET_SHA["frozen-ice-psd-moments.nc"]:
                raise RuntimeError(f"{phase} raw capture frozen-table hash mismatch: {frozen_sha}")
            result_records, result_dims, result_headers = parse_result_records(on / f"capture/{phase}.result")
            if result_dims != [1, 39] or "WRF_THETA_HR" not in result_records or len(result_records["WRF_THETA_HR"]) != len(records["PI"]):
                raise RuntimeError(f"{phase} result lacks layer-resolved WRF_THETA_HR")
            if not np.isfinite(result_records["WRF_THETA_HR"]).all():
                raise RuntimeError(f"{phase} WRF_THETA_HR contains nonfinite values")
            step = int(round(records["RADIATION_STEP"][0]))
            source_seconds = records["SOURCE_TIME_SECONDS"][0]
            actual = audit["activations"][1]
            if step != actual["step"] or abs(source_seconds - actual["source_seconds"]) > 1.e-3:
                raise RuntimeError(f"{phase} capture call 2 does not match second observed activation")
            raw_check[phase] = {"version_header": headers, "step": step, "source_seconds": source_seconds,
                                "matched_second_observed_activation": True,
                                "PI_layers": len(records["PI"]), "WRF_THETA_HR_layers": len(result_records["WRF_THETA_HR"]),
                                "frozen_table_sha256": frozen_sha,
                                "theta_to_temperature_heating_K_day": [float(t * pi * 86400.) for t, pi in zip(result_records["WRF_THETA_HR"], records["PI"])],
                                "result_header": result_headers,
                                "input_sha256": sha256(on / f"capture/{phase}.input"),
                                "result_sha256": sha256(on / f"capture/{phase}.result")}
            json_write(progress_path, {"case_runs": results, "audit": audit, "captures": raw_check,
                                       "completed_case_count": len(results)})
        history = compare_history(off, on, audit_rows, dt.datetime(2010, 6, 11, 0, 0), raw_capture)
        json_write(progress_path, {"case_runs": results, "audit": audit, "captures": raw_check,
                                   "history": history, "completed_case_count": len(results)})
        after_source_sha, after_source_info = verify_build_manifest(workspace, source, exe)
        after_assets = snapshot_shared_assets(source, workspace_from_plan=workspace)
        if after_source_sha != assets_before["source_tree_sha256"]:
            raise RuntimeError("source tree changed during audit")
        if after_assets != assets_before["shared_assets"]:
            raise RuntimeError("shared immutable input/coefficient assets changed during audit")
        for name in ("audit-off", "audit-on"):
            after_case = immutable_tree_hashes(work / name / "run")
            if after_case != cases[name]["immutable_assets"]:
                raise RuntimeError(f"staged immutable files changed during run: {name}")
        return {"case_runs": results, "audit": audit, "captures": raw_check,
                "history": history, "source_tree_sha256_after": after_source_sha,
                "source_manifest_after": after_source_info, "shared_assets_unchanged": True,
                "phase_selection": phase_selection}


def snapshot_shared_assets(source: Path, workspace_from_plan: Path) -> dict[str, str]:
    # workspace_from_plan is the workspace root passed in via caller.
    wrf_run = source / "WRF/run"
    paths = {f"coeff:{name}": wrf_run / name for name in ASSET_SHA if name.startswith("rrtmgp-")}
    # The LUT is rooted in the authoritative frozen source tree, not the run directory.
    lut = source / "validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc"
    paths["frozen_lut"] = lut
    case_inputs = {
        "restart": workspace_from_plan / "build/udm-frozen-restart-plan/trial-mode1-0to12/wrfrst_d01_2010-06-11_12:00:00",
        "wrfinput": workspace_from_plan / "build/udm-frozen-runtime-mpi/case-mode1/wrfinput_d01",
        "wrfbdy": workspace_from_plan / "build/udm-frozen-runtime-mpi/case-mode1/wrfbdy_d01",
    }
    paths.update(case_inputs)
    result = {}
    for name, path in paths.items():
        if not path.is_file():
            raise RuntimeError(f"immutable asset missing: {path}")
        result[name] = sha256(path)
    for name, expected in ASSET_SHA.items():
        asset_key = "frozen_lut" if name.startswith("frozen-") else f"coeff:{name}"
        if result[asset_key] != expected:
            raise RuntimeError(f"immutable asset SHA mismatch {name}: {result[asset_key]}")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, required=True)
    parser.add_argument("--source-root", type=Path)
    parser.add_argument("--wrf-exe", type=Path)
    parser.add_argument("--output-root", type=Path, required=True)
    parser.add_argument("--mode", choices=("prepare", "run"), default="prepare")
    parser.add_argument("--phase", choices=("off", "on", "both"), default="both")
    parser.add_argument("--off-run-dir", type=Path,
                        help="completed prior audit-off run directory required with --phase on")
    parser.add_argument("--approved-exe-sha256")
    parser.add_argument("--approved-source-tree-sha256")
    parser.add_argument("--timeout-seconds", type=int, default=3600)
    args = parser.parse_args()
    workspace = args.workspace.resolve()
    plan_path = workspace / PLAN_REL
    source = (args.source_root or (workspace / SOURCE_REL)).resolve()
    exe = (args.wrf_exe or (source / "WRF/main/wrf.exe")).resolve()
    work = args.output_root.resolve()
    if work.exists():
        parser.error(f"refusing existing output root (evidence is immutable): {work}")
    if args.timeout_seconds <= 0:
        parser.error("timeout must be positive")
    if args.mode == "run" and (not args.approved_exe_sha256 or not args.approved_source_tree_sha256):
        parser.error("run mode requires root-approved --approved-exe-sha256 and --approved-source-tree-sha256")
    work.mkdir(parents=True)
    receipt_path = work / "receipt.json"
    receipt: dict[str, Any] = {"schema": "UDM_SELECTED_REAL_AUDIT_V1", "status": "PREPARING",
                               "mode": args.mode, "executed": False, "failure": None,
                               "phase": args.phase,
                               "workspace": str(workspace), "source_root": str(source),
                               "binary_path": str(exe), "timeout_seconds_per_case": args.timeout_seconds}
    try:
        plan = json.loads(plan_path.read_text())
        if plan["status"] != "prepared_not_executed":
            raise RuntimeError(f"unexpected approved-plan status: {plan['status']}")
        verify_source_shape(source)
        source_sha, source_info = verify_build_manifest(workspace, source, exe)
        for key, expected in (("driver", plan["source_review"]["driver_sha256_at_plan_creation"]),
                              ("audit_config", plan["source_review"]["audit_config_sha256_at_plan_creation"])):
            src_file = workspace / plan["source_review"][key]
            if sha256(src_file) != expected:
                raise RuntimeError(f"source review hash mismatch for {key}: {sha256(src_file)}")
        shared_before = snapshot_shared_assets(source, workspace)
        restart_info = verify_netcdf_restart(workspace / plan["restart"]["path"], plan)
        actual_input_hashes = {
            "restart": sha256(workspace / plan["restart"]["path"]),
            "wrfinput": sha256(workspace / plan["inputs"]["wrfinput"]["path"]),
            "wrfbdy": sha256(workspace / plan["inputs"]["wrfbdy"]["path"]),
        }
        for key, path_info in (("restart", plan["restart"]), ("wrfinput", plan["inputs"]["wrfinput"]),
                               ("wrfbdy", plan["inputs"]["wrfbdy"])):
            if actual_input_hashes[key] != path_info["sha256"]:
                raise RuntimeError(f"input asset SHA mismatch: {key}")
        exe_sha = sha256(exe) if exe.is_file() else None
        if args.mode == "run":
            if exe_sha != args.approved_exe_sha256:
                raise RuntimeError(f"approved executable SHA does not match actual: {exe_sha}")
            if source_sha != args.approved_source_tree_sha256:
                raise RuntimeError(f"approved source-tree SHA does not match actual: {source_sha}")
        cases = stage_cases(work, workspace, source, plan, exe if args.mode == "run" else None)
        # OFF/ON setup is byte-identical; environment is the only switch.
        plan_derived = {
            "source_verified_activation_formula": "itimestep==1 or MOD(itimestep,STEPRA)==1+ra_call_offset",
            "restart_step": 720, "stepra": 10, "ra_call_offset": 0,
            "predicted_activation_steps": [721, 731],
            "source_time_is_observed": True,
            "capture_call": 2,
            "capture_selection_counts_per_phase_only_at_selected_column": True,
            "audit_calls_per_phase_per_activation": 65,
            "audit_shadow_calls_total": 260,
            "production_calls_total_two_activations": 4,
            "combined_shadow_plus_production_evaluations": 264,
            "prior_plan_shadow_count_correction": "The earlier plan counted 66 shadows/phase/activation. Driver skips engine 37 at m=0: m=0..32 yields 1 + 32*2 = 65 shadows per phase/activation.",
        }
        receipt.update({"plan_sha256": sha256(plan_path), "source_tree_sha256": source_sha,
                        "source_manifest": source_info, "executable_sha256": exe_sha,
                        "restart_validation": restart_info, "source_asset_hashes": shared_before,
                        "input_hashes": actual_input_hashes, "cases": cases,
                        "derived_schedule": plan_derived,
                        "status": "PREPARED_PENDING_APPROVED_EXECUTABLE" if args.mode == "prepare" else "RUNNING"})
        json_write(work / "derived-plan.json", {"plan": plan_derived, "restart": restart_info,
                                                 "point": plan["point_wrf_one_based"],
                                                 "run_window": {"start": plan["run"]["start"], "end": plan["run"]["end"]}})
        if args.mode == "run":
            receipt["executed"] = True
            run_result = run_and_validate(work, cases, os.environ.copy(), args.timeout_seconds,
                                          {"source_tree_sha256": source_sha, "shared_assets": shared_before},
                                          source, exe, workspace, args.phase, args.off_run_dir)
            receipt["run_validation"] = run_result
            receipt["status"] = run_result.get("status", "PASS")
        else:
            receipt["status"] = "PREPARED_PENDING_APPROVED_EXECUTABLE" if exe_sha is None else "PREPARED_NOT_EXECUTED"
    except Exception as exc:
        receipt["status"] = "FAIL"
        receipt["failure"] = {"type": type(exc).__name__, "message": str(exc)}
        progress_path = work / "run-progress.json"
        if progress_path.is_file():
            receipt["partial_run_progress"] = json.loads(progress_path.read_text())
        json_write(receipt_path, receipt)
        raise
    json_write(receipt_path, receipt)
    print(f"{receipt['status']}: {receipt_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
