#!/usr/bin/env python3
"""One-minute SCM checks for UDM's first-call snow-radius fallback.

The default mode consumes already-built baseline and candidate SCM executables
and checks three arms. ``--runtime-only`` consumes one already-built candidate
tree for a seed plus the candidate37 first-call path only. Neither mode builds
WRF. Each mode records its own scope explicitly; runtime-only does not claim
engine4 preservation. ``--capture-pair`` adds one candidate37 OFF forecast to
the ON forecast and checks complete history bytes for observer passivity.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

import test_column_replay
from compare_column_replay import read_result

SUCCESS = "SUCCESS COMPLETE WRF"
HYDROMETEORS = ("QCLOUD", "QRAIN", "QICE", "QSNOW", "QGRAUP", "QHAIL")
TIMEOUT_SECONDS = 180
CHILD_CLEANUP_GRACE_SECONDS = 15
SW_PRECIP_TAU_FLOOR = 1.0e-12


def validate_precipitation_optics(phase: str, records: dict[str, np.ndarray],
                                  k: int, host_real_bits: int = 32) -> dict[str, Any]:
    """Check the selected snow-only layer independently of returned tau.

    These are the pinned module_ra_rrtmgp_precip source equations, with paths
    in g/m2 and radius in micrometers. They test integration of that contract,
    not the physical validity of its coefficients or the snow population.
    The error budgets below count binary64 arithmetic, not an adjustable
    physical tolerance. SW subtraction near unit SSA uses extinction as scale.
    """
    swp = float(records["SWP"][0, k])
    rwp = float(records["RWP"][0, k])
    radius = float(records["RES"][0, k])
    if phase not in ("LW", "SW") or not np.isfinite([swp, rwp, radius]).all():
        fail("invalid phase or non-finite snow optics inputs")
    bands = 16 if phase == "LW" else 14
    tau = np.asarray(records["RESULT_PRECIP_TAU"])
    if (tau.shape != (*np.asarray(records["SWP"]).shape, bands)
            or not np.isfinite(tau).all() or np.any(tau < 0.0)):
        fail(f"{phase}: invalid precipitation optical depth shape/values")
    if not (rwp == 0.0 and swp > 0.0 and radius > 10.0):
        fail(f"{phase}: analytic check requires positive snow and zero rain")
    selected = tau[0, k, :]
    threshold = 0.0 if phase == "LW" else SW_PRECIP_TAU_FLOOR
    if not np.all(selected > threshold):
        fail(f"{phase}: every fixture-layer precipitation band must exceed {threshold:g}")
    eps = np.finfo(np.float64).eps
    if phase == "LW":
        expected = 1.5 * 1.05756 * swp / radius
        error = np.abs(selected - expected)
        bound = 16.0 * eps * expected
        if np.any(error > bound):
            fail("LW: snow optical depth disagrees with independent analytic path/radius check")
        return {"independent_check": "1.5*1.05756*SWP/RES, g/m2 and micrometers",
                "expected_snow_tau": expected, "max_abs_error": float(error.max()),
                "binary64_roundoff_bound": bound, "checked_bands": bands}
    ssa = np.asarray(records.get("RESULT_PRECIP_SSA", []))
    if ssa.shape != tau.shape or not np.isfinite(ssa).all() or np.any((ssa < 0.) | (ssa > 1.)):
        fail("SW: missing or invalid PRECIP_SSA for absorption invariant")
    # Delta scaling preserves tau*(1-ssa). Account for the native module's
    # min(1-1e-6,ssa) cap: even its four conservative bands have that absorption.
    extinction = swp * 1.09087 * (1.5 / (1.0315 * radius))
    if host_real_bits not in (32, 64):
        fail("SW: host REAL storage must be32 or64 bits for coefficient literals")
    # B0S/B1S array literals have no _wp suffix in the source. They round to
    # the compiler's default REAL kind before assignment to REAL(wp) tables.
    literal_kind = np.float32 if host_real_bits == 32 else np.float64
    b0 = np.array([.460] * 8 + [0.] * 6, dtype=literal_kind).astype(np.float64)
    b1 = np.array([0.] * 8 + [1.62e-5] * 2 + [0.] * 4, dtype=literal_kind).astype(np.float64)
    expected_absorption = extinction * np.maximum(1.e-6, b0 + b1 * 1.0315 * radius)
    absorption = selected * (1.0 - ssa[0, k, :])
    error = np.abs(absorption - expected_absorption)
    bound = 64.0 * eps * extinction
    if np.any(error > bound):
        fail("SW: delta-scaled precipitation absorption disagrees with independent snow invariant")
    return {"independent_check": "tau_delta*(1-ssa_delta) = tau_unscaled*max(1e-6,B0S+B1S*1.0315*RES)",
            "unscaled_snow_extinction": extinction,
            "expected_absorption_by_band": expected_absorption.tolist(),
            "max_abs_error": float(error.max()), "binary64_roundoff_bound": bound,
            "checked_bands": bands, "native_ssa_cap": "1-1e-6",
            "coefficient_literal_default_real_bits": host_real_bits}


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def atomic_json(path: Path, value: dict[str, Any]) -> None:
    tmp = path.with_name(path.name + ".tmp")
    data = (json.dumps(value, sort_keys=True, indent=2) + "\n").encode()
    with tmp.open("xb") as stream:
        stream.write(data)
        stream.flush()
        os.fsync(stream.fileno())
    os.replace(tmp, path)
    fd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def set_assignment(text: str, key: str, value: str, *, group: str = "physics") -> str:
    pattern = rf"(?im)^(\s*{re.escape(key)}\s*=\s*)[^,\n]+,"
    updated, count = re.subn(pattern, rf"\g<1>{value},", text, count=1)
    if count == 1:
        return updated
    if count != 0:
        fail(f"duplicate {key} assignment")
    start = updated.lower().find(f"&{group.lower()}")
    if start < 0:
        fail(f"missing &{group} block while adding {key}")
    end_match = re.search(r"(?m)^\s*/\s*(?:!.*)?$", updated[start:])
    if end_match is None:
        fail(f"unterminated &{group} block while adding {key}")
    end = start + end_match.start()
    return updated[:end] + f"\n {key} = {value},\n" + updated[end:]


def make_namelist(root: Path, lw: int, sw: int) -> str:
    text = (root / "test/rrtmgp/namelist.scm37").read_text()
    if re.search(r"(?im)^\s*debug_level\s*=", text):
        text, count = re.subn(
            r"(?im)^(\s*debug_level\s*=\s*)[^,\n]+,",
            r"\g<1>100,", text, count=1)
    else:
        text, count = re.subn(
            r"(?im)^(\s*&time_control\s*)$",
            r"\g<1>\n debug_level = 100,", text, count=1)
    if count != 1 or not re.search(r"(?im)^\s*sf_surface_physics\s*=\s*2\s*,", text):
        fail("SCM namelist must retain LSM2 and permit debug_level=100")
    text = test_column_replay.set_mp_physics(text, 27)
    text = set_assignment(text, "ra_lw_physics", str(lw))
    text = set_assignment(text, "ra_sw_physics", str(sw))
    text = test_column_replay.set_run_minutes(text, 1)
    text = set_assignment(text, "history_interval", "0", group="time_control")
    text = set_assignment(text, "history_interval_s", "60", group="time_control")
    # Keep initial and 60-second output records in one history file.
    text = set_assignment(text, "frames_per_outfile", "10000", group="time_control")
    return text


def prepare_case(root: Path, case: Path, namelist: str) -> None:
    case.mkdir(parents=True, exist_ok=False)
    (case / "namelist.input").write_text(namelist)
    shutil.copy2(root / "test/rrtmgp/radiation_iofields.txt", case)
    for name in ("input_sounding", "input_soil", "force_ideal.nc"):
        shutil.copy2(root / "test/em_scm_xy" / name, case / name)
    # SCM data are linked from the exact source tree selected for each arm.
    for source in (root / "run").iterdir():
        if source.is_file():
            target = case / source.name
            if not target.exists():
                target.symlink_to(source.resolve())


def run_once(exe: Path, case: Path, logname: str, capture: bool,
             kind: str, expected_executable_sha256: str | None = None) -> dict[str, Any]:
    if not exe.is_file() or not os.access(exe, os.X_OK):
        fail(f"missing executable: {exe}")
    exe_sha_before = sha256(exe)
    exe_size = exe.stat().st_size
    if expected_executable_sha256 is not None and exe_sha_before != expected_executable_sha256:
        fail(f"{kind}: executable hash differs from the preflight pin")
    env = os.environ.copy()
    for name in list(env):
        if name.startswith(("WRF_RRTMGP_", "OMP_", "GOMP_", "KMP_")) or name in {
            "MKL_NUM_THREADS", "OPENBLAS_NUM_THREADS"
        }:
            env.pop(name, None)
    env.pop("LD_PRELOAD", None)
    env["OMP_NUM_THREADS"] = "1"
    env["OMP_DYNAMIC"] = "FALSE"
    env["OMP_MAX_ACTIVE_LEVELS"] = "1"
    if capture:
        cap = case / "capture"
        cap.mkdir(exist_ok=False)
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(cap)
        env["WRF_RRTMGP_CAPTURE_CALL"] = "1"
    command = ["/usr/bin/timeout", "--signal=TERM", "--kill-after=15s",
               f"{TIMEOUT_SECONDS}s", str(exe)]
    result_path = case / "process-result.json"
    record: dict[str, Any] = {
        "kind": kind, "status": "STARTING", "launched": False,
        "executable": str(exe), "executable_sha256": exe_sha_before,
        "executable_size_bytes": exe_size, "command": command,
        "cwd": str(case), "timeout_seconds": TIMEOUT_SECONDS,
        "environment": {"OMP_NUM_THREADS": env["OMP_NUM_THREADS"],
                         "OMP_DYNAMIC": env["OMP_DYNAMIC"],
                         "OMP_MAX_ACTIVE_LEVELS": env["OMP_MAX_ACTIVE_LEVELS"],
                         "capture_enabled": capture,
                         "column_selection": "default (1,1)"},
        "log": logname,
    }
    atomic_json(result_path, record)
    with (case / logname).open("xb") as log:
        try:
            child = subprocess.Popen(command, cwd=case, env=env, stdout=log,
                                     stderr=subprocess.STDOUT, start_new_session=True)
        except BaseException as exc:
            record.update({"status": "FAILED_TO_SPAWN", "spawn_error": f"{type(exc).__name__}: {exc}"})
            atomic_json(result_path, record)
            raise
        record.update({"status": "RUNNING", "launched": True,
                       "pid": child.pid, "process_group": child.pid,
                       "started_unix": time.time()})
        lifecycle_stage = "RUNNING_RECORD"
        try:
            # The RUNNING write is part of the child lifecycle. If persistence
            # fails here, the process group must still be stopped and reaped.
            atomic_json(result_path, record)
            lifecycle_stage = "WAITING"
            returncode = child.wait()
        except BaseException as exc:
            cleanup_error = None
            try:
                # The group can outlive its session leader (for example when
                # the executable forks and exits during a receipt failure),
                # so signal/check the whole group even if poll() has an RC.
                try:
                    os.killpg(child.pid, signal.SIGTERM)
                except ProcessLookupError:
                    pass
                deadline = time.monotonic() + CHILD_CLEANUP_GRACE_SECONDS
                group_alive = True
                while time.monotonic() < deadline:
                    try:
                        os.killpg(child.pid, 0)
                    except ProcessLookupError:
                        group_alive = False
                        break
                    if child.poll() is None:
                        try:
                            child.wait(timeout=min(0.1, max(0.01, deadline - time.monotonic())))
                        except subprocess.TimeoutExpired:
                            pass
                    else:
                        time.sleep(0.02)
                if group_alive:
                    try:
                        os.killpg(child.pid, signal.SIGKILL)
                    except ProcessLookupError:
                        pass
                if child.poll() is None:
                    child.wait(timeout=15)
            except BaseException as cleanup_exc:
                cleanup_error = f"{type(cleanup_exc).__name__}: {cleanup_exc}"
            returncode = child.poll()
            running_write_failed = lifecycle_stage == "RUNNING_RECORD"
            record.update({"status": ("RUNNING_RECORD_FAILED_CHILD_REAPED" if returncode is not None
                                       else "RUNNING_RECORD_FAILED_REAP_PENDING")
                           if running_write_failed else
                           ("INTERRUPTED_CHILD_REAPED" if returncode is not None
                            else "INTERRUPTED_REAP_PENDING"),
                           "ended_unix": time.time(), "reaped": returncode is not None,
                           "cleanup_error": cleanup_error})
            record["running_record_error" if running_write_failed else "interrupted_error"] = \
                f"{type(exc).__name__}: {exc}"
            if returncode is not None:
                record.update({"returncode": returncode,
                               "timed_out": returncode == 124 or returncode == 137})
            try:
                atomic_json(result_path, record)
            except BaseException as receipt_exc:
                # Keep the original lifecycle failure primary. When the store
                # itself remains unavailable, the actual RC is still retained
                # in this raised exception and the child has already been reaped.
                if hasattr(exc, "add_note"):
                    exc.add_note(f"terminal process receipt could not be persisted: "
                                 f"{type(receipt_exc).__name__}: {receipt_exc}; "
                                 f"child_returncode={returncode!r}")
            raise
        # Persist the actual child RC immediately after wait, before any file
        # hashing, NetCDF inspection, or other postflight operation can fail.
        record.update({"status": "CHILD_REAPED", "returncode": returncode,
                       "ended_unix": time.time(), "reaped": True,
                       "timed_out": returncode == 124 or returncode == 137})
        try:
            atomic_json(result_path, record)
        except BaseException as exc:
            record.update({"status": "CHILD_REAPED_RECORD_FAILED",
                           "record_write_error": f"{type(exc).__name__}: {exc}"})
            try:
                atomic_json(result_path, record)
            except BaseException as receipt_exc:
                if hasattr(exc, "add_note"):
                    exc.add_note(f"terminal process receipt could not be persisted: "
                                 f"{type(receipt_exc).__name__}: {receipt_exc}; "
                                 f"child_returncode={returncode}")
            raise
        log.flush()
        os.fsync(log.fileno())
    try:
        exe_sha_after = sha256(exe)
        exe_size_after = exe.stat().st_size
        log_sha = sha256(case / logname)
        record.update({"executable_sha256_after": exe_sha_after,
                       "executable_size_bytes_after": exe_size_after,
                       "log_sha256": log_sha})
        if exe_sha_after != exe_sha_before or exe_size_after != exe_size:
            raise RuntimeError(f"{kind}: executable changed while the process was running")
        atomic_json(result_path, record)
    except BaseException as exc:
        record.update({"status": "POSTFLIGHT_ERROR",
                       "postflight_error": f"{type(exc).__name__}: {exc}"})
        atomic_json(result_path, record)
        raise
    record["status"] = "COMPLETE"
    atomic_json(result_path, record)
    return record


def one_history(case: Path) -> tuple[Path, dict[str, np.ndarray]]:
    paths = sorted(case.glob("wrfout_d01_*"))
    if len(paths) != 1:
        fail(f"{case}: expected exactly one hourly history file, found {len(paths)}")
    with netCDF4.Dataset(paths[0]) as ds:
        if (int(ds.RA_LW_PHYSICS), int(ds.RA_SW_PHYSICS), int(ds.MP_PHYSICS)) == (0, 0, 0):
            fail(f"{case}: history physics identifiers are unset")
        arrays: dict[str, np.ndarray] = {}
        ds.set_auto_maskandscale(False)
        for name, var in ds.variables.items():
            arrays[name] = np.asarray(var[:]).copy()
        times = np.asarray(ds.variables["Times"][:])
        rendered = [b"".join(row).decode("ascii") for row in times]
        if len(rendered) != 2:
            fail(f"{case}: expected exactly initial and 60-second history Times, got {rendered}")
        parsed = [datetime.strptime(value, "%Y-%m-%d_%H:%M:%S") for value in rendered]
        if (parsed[1] - parsed[0]).total_seconds() != 60.0:
            fail(f"{case}: one-minute integration did not produce a 60-second endpoint")
    return paths[0], arrays


def compare_shared_history(a: dict[str, np.ndarray], b: dict[str, np.ndarray]) -> dict[str, Any]:
    common = sorted(a.keys() & b.keys())
    if not common:
        fail("baseline4/candidate4 histories have no common variables")
    differences = []
    for name in common:
        x, y = a[name], b[name]
        if x.shape != y.shape or x.dtype != y.dtype:
            differences.append(name)
        elif x.dtype.kind in "OUS":
            if not np.array_equal(x, y):
                differences.append(name)
        elif x.tobytes(order="A") != y.tobytes(order="A"):
            differences.append(name)
    if differences:
        fail(f"engine4 baseline/candidate common history arrays differ: {differences[:30]}")
    return {"count": len(common), "identical_common_variables": common,
            "baseline_only": sorted(a.keys() - b.keys()),
            "candidate_only": sorted(b.keys() - a.keys())}


def read_capture(path: Path, phase: str) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    got_phase, i, j, raw = test_column_replay.read_raw(path / f"{phase.lower()}.raw")
    inp_phase, nc, nl, _, _, _, inp = test_column_replay.read_input(path / f"{phase.lower()}.input")
    if got_phase != phase or inp_phase != phase or (i, j) != (1, 1) or nc != 1 or nl < 1:
        fail(f"{phase}: invalid capture phase/shape")
    result = read_result(path / f"{phase.lower()}.result")
    sections = result.get("sections", {})
    if "PRECIP_TAU" not in sections:
        fail(f"{phase}: solver result omitted PRECIP_TAU")
    return raw, {**inp, **{f"RESULT_{k}": v for k, v in sections.items()}}


def validate_startup_capture(case: Path, seed: dict[str, Any]) -> dict[str, Any]:
    root = case / "capture"
    evidence = {}
    for phase in ("LW", "SW"):
        raw, combined = read_capture(root, phase)
        required = ("CF", "SOURCE_QS", "SOURCE_RE_SNOW", "SOURCE_DRY_RHO",
                    "STARTUP_SNOW_BOOTSTRAP", "STARTUP_SNOW_RADIUS_M",
                    "HOST_REAL_BITS", "RES", "HAS_REQS", "ICLOUD", "MP_PHYSICS",
                    "RESULT_PRECIP_TAU")
        missing = [name for name in required if name not in raw and name not in combined]
        if missing:
            fail(f"{phase}: missing startup-snow proof fields {missing}")
        cf = raw["CF"]
        qs = raw["SOURCE_QS"]
        source_res = raw["SOURCE_RE_SNOW"]
        dry_rho = raw["SOURCE_DRY_RHO"]
        bootstrap = raw["STARTUP_SNOW_BOOTSTRAP"]
        native_m = raw["STARTUP_SNOW_RADIUS_M"]
        # The prepared native paths are adapter records; these are the values
        # consumed by the current optical builder, not an inferred history field.
        if "RWP" not in combined or "SWP" not in combined:
            fail(f"{phase}: adapter input omitted rain/snow paths")
        rwp = np.asarray(combined["RWP"]).reshape(-1)
        swp = np.asarray(combined["SWP"]).reshape(-1)
        tau = combined["RESULT_PRECIP_TAU"]
        adapter_cf = np.asarray(combined["CF"]).reshape(-1)
        adapter_res = np.asarray(combined["RES"]).reshape(-1)
        k = int(seed["level_zero_based"])
        for name, arr in (("CF", cf), ("QS", qs), ("source radius", source_res),
                          ("dry density", dry_rho), ("bootstrap", bootstrap),
                          ("native snow radius", native_m), ("RWP", rwp),
                          ("SWP", swp), ("PRECIP_TAU", tau)):
            if not np.isfinite(arr).all():
                fail(f"{phase}: {name} contains non-finite values")
        if not (0 <= k < len(cf)):
            fail(f"{phase}: fixture level {k} outside captured layer count {len(cf)}")
        # The RAW callback records native WRF kts:kte layers (59 here), while
        # the RRTMGP adapter may append an upper extension. Source order is
        # bottom-first: the native kts:kte slice is copied into the adapter's
        # leading layers by rrtmgp_build_udm_inputs; gas_dry_column documents
        # the same ordering when copying native_mass. Therefore k remains the
        # same zero-based layer in the adapter prefix.
        if len(rwp) != len(swp) or len(adapter_cf) != len(rwp) or len(adapter_res) != len(rwp):
            fail(f"{phase}: adapter RWP/SWP/CF/RES layer shapes disagree")
        if len(cf) > len(adapter_cf) or k >= len(adapter_cf):
            fail(f"{phase}: native RAW layers do not fit the bottom-first adapter prefix")
        if (not np.array_equal(adapter_cf[:len(cf)], cf)
                or not np.array_equal(adapter_res[:len(cf)], np.asarray(raw["RES"]).reshape(-1))):
            fail(f"{phase}: native RAW CF/RES do not match the adapter's bottom-first prefix")
        if cf[k] != 1.0 or qs[k] <= 0.0 or dry_rho[k] <= 0.0:
            fail(f"{phase}: snow fixture did not reach saturated cloudy source state")
        if np.any(rwp != 0.0) or rwp[k] != 0.0:
            fail(f"{phase}: rain path is not zero")
        if swp[k] <= 0.0:
            fail(f"{phase}: snow grid path is not positive")
        mapping = test_column_replay.startup_snow_radius_mapping(raw, len(cf), phase)
        if mapping is None or not bool(mapping[1][k]):
            fail(f"{phase}: startup snow mapping did not select the fixture layer")
        res_um = float(np.asarray(raw["RES"]).reshape(-1)[k])
        if not (25.0 <= res_um <= 999.0):
            fail(f"{phase}: prepared RES outside native snow size range")
        if bootstrap[k] != 1.0 or native_m[k] <= 0.0:
            fail(f"{phase}: startup snow bootstrap marker/radius missing")
        # SOURCE_RE_SNOW is the unchanged pre-microphysics background sentinel;
        # the startup helper returns the separate radius used in RES.
        if abs(float(source_res[k]) - float(seed["background_re_snow_m"])) > 1.e-12:
            fail(f"{phase}: source re_snow state changed before the radiation fallback")
        if (tau.ndim != 3 or tau.shape[:2] != np.asarray(combined["SWP"]).shape
                or tau.shape[0] != 1 or tau.shape[2] < 1):
            fail(f"{phase}: PRECIP_TAU must be (column,adapter layers,bands) matching SWP, got {tau.shape}")
        if tau.shape[2] != (16 if phase == "LW" else 14):
            fail(f"{phase}: PRECIP_TAU band count {tau.shape[2]} differs from the pinned adapter contract")
        if phase == "SW":
            # module_ra_rrtmgp_precip.F applies MAX(1.0E-12_wp, tau_rain+tau_snow)
            # before delta scaling; requiring the final value above that floor
            # prevents the floor alone from satisfying this integration check.
            threshold = SW_PRECIP_TAU_FLOOR
            floor_source = "WRF/phys/module_ra_rrtmgp_precip.F:194, pre-delta tau_prec floor"
        else:
            threshold = 0.0
            floor_source = None
        optics = validate_precipitation_optics(phase, combined, k, int(raw["HOST_REAL_BITS"][0]))
        evidence[phase] = {"native_layers": int(len(cf)), "adapter_layers": int(len(adapter_cf)),
                           "fixture_level_native_and_adapter_zero_based": k,
                           "optical_dimension_label": "spectral bands",
                           "optical_band_count": int(tau.shape[2]),
                           "cf": float(cf[k]), "qs": float(qs[k]),
                           "source_re_snow_m": float(source_res[k]),
                           "startup_radius_m": float(native_m[k]),
                           "prepared_res_um": res_um,
                           "rwp_grid": float(rwp[k]), "swp_grid": float(swp[k]),
                           "precip_tau_threshold": threshold,
                           "precip_tau_floor_source": floor_source,
                           "precip_tau_above_threshold_count": int(np.count_nonzero(tau[0, k, :] > threshold)),
                           "independent_optics": optics}
    return evidence


def create_seed(baseline_root: Path, root: Path, ideal_sha256: str) -> dict[str, Any]:
    seed_dir = root / "shared-seed"
    prepare_case(baseline_root, seed_dir, make_namelist(baseline_root, 4, 4))
    ideal = run_once(baseline_root / "main/ideal.exe", seed_dir, "ideal.log", False, "ideal",
                     expected_executable_sha256=ideal_sha256)
    if ideal["returncode"] != 0 or not (seed_dir / "wrfinput_d01").is_file():
        fail("baseline ideal.exe failed to create wrfinput_d01")
    ideal_log = (seed_dir / "ideal.log").read_text(errors="replace")
    if "SUCCESS COMPLETE IDEAL INIT" not in ideal_log:
        fail("baseline ideal.exe did not report normal completion")
    wrfinput = seed_dir / "wrfinput_d01"
    with netCDF4.Dataset(wrfinput, "r+") as ds:
        required = (*HYDROMETEORS, "QVAPOR", "T", "P", "PB")
        missing = [name for name in required if name not in ds.variables]
        if missing:
            fail(f"generated seed lacks fixture variables: {missing}")
        theta = np.asarray(ds.variables["T"][0], dtype=np.float64)
        p = np.asarray(ds.variables["P"][0], dtype=np.float64) + np.asarray(ds.variables["PB"][0], dtype=np.float64)
        temperature = (theta + 300.0) * np.power(p / 100000.0, 287.0 / 1004.0)
        candidates = [k for k in range(1, temperature.shape[0] - 1)
                      if np.isfinite(temperature[k, 0, 0]) and np.isfinite(p[k, 0, 0])
                      and 240.0 <= temperature[k, 0, 0] <= 260.0 and p[k, 0, 0] > 20000.0]
        if not candidates:
            fail("generated seed has no cold interior level in the first column")
        k = min(candidates, key=lambda idx: abs(float(temperature[idx, 0, 0]) - 250.0))
        temp = float(temperature[k, 0, 0])
        pressure = float(p[k, 0, 0])
        # Source-equivalent saturation-over-ice branch of cal_cldfra1 for
        # F_QC/F_QI/F_QS true and snow-only QCLD>QCLDMIN.
        tc = temp - 273.15
        esi = 610.78 * np.exp(21.8745584 * tc / (temp - 7.66))
        qvsi = (287.0 / 461.6) * esi / (pressure - esi)
        if not np.isfinite(qvsi) or qvsi <= 0.0:
            fail("source-derived saturation mixing ratio is invalid")
        for name in HYDROMETEORS:
            values = np.asarray(ds.variables[name][:]).copy()
            values[:] = 0.0
            ds.variables[name][:] = values
        snow = np.asarray(ds.variables["QSNOW"][:]).copy()
        snow[0, k, 0, 0] = 1.0e-4
        ds.variables["QSNOW"][:] = snow
        qv = np.asarray(ds.variables["QVAPOR"][:]).copy()
        qv[:] = 0.0
        qv[0, k, 0, 0] = 1.02 * qvsi
        ds.variables["QVAPOR"][:] = qv
    return {"path": seed_dir, "wrfinput": wrfinput, "level_zero_based": int(k),
            "temperature_k": temp, "pressure_pa": pressure,
            "source_cal_cldfra1_qvsi": float(qvsi), "fixture_qv": float(1.02 * qvsi),
            "snow_kg_kg": 1.0e-4, "background_re_snow_m": 9.99e-6,
            "wrfinput_sha256": sha256(wrfinput), "ideal_invocations": 1}


def forecast(seed: dict[str, Any], root: Path, arm: str, wrf_root: Path,
             option: int, capture: bool, expected_executable_sha256: str) -> dict[str, Any]:
    case = root / arm
    prepare_case(wrf_root, case, make_namelist(wrf_root, option, option))
    shutil.copy2(seed["wrfinput"], case / "wrfinput_d01")
    if sha256(case / "wrfinput_d01") != seed["wrfinput_sha256"]:
        fail(f"{arm}: copied initial wrfinput does not match shared seed")
    process = run_once(wrf_root / "main/wrf.exe", case, "wrf.log", capture, "forecast",
                       expected_executable_sha256=expected_executable_sha256)
    if process["returncode"] != 0:
        fail(f"{arm}: wrf.exe returned {process['returncode']}; inspect preserved process-result.json/log")
    log = (case / "wrf.log").read_text(errors="replace")
    if SUCCESS not in log:
        fail(f"{arm}: WRF success marker missing")
    path, arrays = one_history(case)
    expected = (option, option, 27)
    with netCDF4.Dataset(path) as ds:
        got = (int(ds.RA_LW_PHYSICS), int(ds.RA_SW_PHYSICS), int(ds.MP_PHYSICS))
        if got != expected:
            fail(f"{arm}: history physics {got}, expected {expected}")
    return {"arm": arm, "case": str(case), "process": process,
            "radiation_option": option, "capture_enabled": capture,
            "namelist_sha256": sha256(case / "namelist.input"),
            "wrfinput_sha256": sha256(case / "wrfinput_d01"),
            "history_path": str(path), "history_sha256": sha256(path),
            "history_arrays": arrays,
            "startup_capture": validate_startup_capture(case, seed) if capture else None}


def compare_capture_pair(off: dict[str, Any], on: dict[str, Any]) -> dict[str, Any]:
    """Require entire same-input candidate37 OFF/ON history files to agree."""
    if (off["radiation_option"] != 37 or on["radiation_option"] != 37
            or off["capture_enabled"] or not on["capture_enabled"]
            or off["wrfinput_sha256"] != on["wrfinput_sha256"]
            or off["namelist_sha256"] != on["namelist_sha256"]
            or off["process"]["executable_sha256"] != on["process"]["executable_sha256"]):
        fail("capture pair must be same-input candidate37 OFF then ON")
    left, right = Path(off["history_path"]), Path(on["history_path"])
    if sha256(left) != off["history_sha256"] or sha256(right) != on["history_sha256"]:
        fail("capture-pair history changed after its forecast receipt")
    if off["history_sha256"] != on["history_sha256"]:
        fail("candidate37 capture OFF/ON complete NetCDF history bytes differ")
    a, b = _read_history_arrays(left), _read_history_arrays(right)
    if set(a) != set(b):
        fail("candidate37 capture OFF/ON history variable rosters differ")
    comparison = compare_shared_history(a, b)
    return {"status": "PASS_SCOPED_CAPTURE_PASSIVITY", "complete_history_bytes_identical": True,
            "history_sha256": off["history_sha256"], "common_arrays": comparison,
            "scope": "Same candidate37 input and executable; capture OFF/ON passivity only"}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    parser.add_argument("--baseline-wrf-root", type=Path,
                        help="fresh base38 WRF tree with main/ideal.exe and main/wrf.exe")
    parser.add_argument("--candidate-wrf-root", type=Path, required=True,
                        help="candidate WRF tree with main/wrf.exe")
    parser.add_argument("--runtime-only", action="store_true",
                        help="run one candidate37 first-call capture using candidate ideal.exe; no engine4 preservation claim")
    parser.add_argument("--capture-pair", action="store_true",
                        help="add same-input candidate37 capture OFF arm and require complete OFF/ON history byte identity")
    args = parser.parse_args()
    output = args.output.resolve()
    candidate = args.candidate_wrf_root.resolve()
    baseline = args.baseline_wrf_root.resolve() if args.baseline_wrf_root else None
    if output.exists():
        fail(f"refusing to overwrite output directory: {output}")
    if baseline is None and not args.runtime_only:
        fail("--baseline-wrf-root is required in the default three-arm mode")
    seed_root = candidate if args.runtime_only else baseline
    required_exes = [seed_root / "main/ideal.exe", candidate / "main/wrf.exe"]
    if not args.runtime_only:
        required_exes.append(baseline / "main/wrf.exe")
    for path in required_exes:
        if not path.is_file() or not os.access(path, os.X_OK):
            fail(f"required executable not found/executable: {path}")
    input_paths = ("test/rrtmgp/namelist.scm37", "test/rrtmgp/radiation_iofields.txt",
                   "test/em_scm_xy/input_sounding", "test/em_scm_xy/input_soil",
                   "test/em_scm_xy/force_ideal.nc")
    if baseline is not None:
        for rel in input_paths:
            left, right = baseline / rel, candidate / rel
            if not left.is_file() or not right.is_file() or sha256(left) != sha256(right):
                fail(f"baseline/candidate SCM input mismatch: {rel}")
    else:
        for rel in input_paths:
            if not (candidate / rel).is_file():
                fail(f"candidate SCM input missing: {rel}")
    coefficient_names = ("rrtmgp-gas-lw-g128.nc", "rrtmgp-gas-sw-g112.nc",
                         "rrtmgp-clouds-lw-bnd.nc", "rrtmgp-clouds-sw-bnd.nc")
    coefficient_hashes = {}
    for name in coefficient_names:
        candidate_path = candidate / "run" / name
        if not candidate_path.is_file():
            fail(f"candidate coefficient missing: {name}")
        candidate_hash = sha256(candidate_path)
        if baseline is not None:
            left = baseline / "run" / name
            if not left.is_file() or sha256(left) != candidate_hash:
                fail(f"baseline/candidate coefficient mismatch: {name}")
        coefficient_hashes[name] = candidate_hash
    output.mkdir(parents=True, exist_ok=False)
    executable_pins = {str(p): {"sha256": sha256(p), "size_bytes": p.stat().st_size}
                       for p in required_exes}
    mode = "candidate37-runtime-only" if args.runtime_only else "three-arm-engine4-and-startup-snow"
    forecast_limit = (1 if args.runtime_only else 3) + int(args.capture_pair)
    state: dict[str, Any] = {"schema": "udm37-startup-snow-scm-v2", "status": "RUNNING",
                             "scope": mode, "models_invoked": 0, "forecast_limit": forecast_limit,
                             "ideal_invocations": 0,
                             "executable_pins": executable_pins,
                             "coefficient_sha256": coefficient_hashes,
                             "baseline_root": str(baseline) if baseline is not None else None,
                             "seed_root": str(seed_root), "candidate_root": str(candidate)}
    if args.runtime_only:
        state["claims"] = ["candidate37 first-call startup-snow capture and selected-layer precipitation optics"]
        state["nonclaims"] = ["no baseline or engine4 preservation comparison"]
    else:
        state["claims"] = ["candidate37 first-call startup-snow capture and selected-layer precipitation optics",
                           "baseline38/candidate38 engine4 common-history bitwise identity"]
    state["capture_pair_requested"] = args.capture_pair
    if args.capture_pair:
        state["claims"].append("candidate37 capture OFF/ON complete-history byte identity")
    atomic_json(output / "execution.json", state)
    try:
        # Record the planned ideal invocation durably before entering it; the
        # exception handler later replaces this with the observed process count.
        state["ideal_invocations_planned"] = 1
        state["ideal_invocations_started"] = 1
        state["ideal_invocation_state"] = "STARTING"
        atomic_json(output / "execution.json", state)
        seed = create_seed(seed_root, output, executable_pins[str(seed_root / "main/ideal.exe")]["sha256"])
        state["seed"] = {k: v for k, v in seed.items() if k not in {"path", "wrfinput"}}
        state["ideal_invocations"] = 1
        state["ideal_invocation_state"] = "COMPLETE"
        atomic_json(output / "execution.json", state)
        arms = []
        if args.runtime_only:
            run_arms = (("candidate38-udm37-runtime-only", candidate, 37, True),)
        else:
            run_arms = (("baseline38-rttmg4", baseline, 4, False),
                        ("candidate38-rttmg4", candidate, 4, False),
                        ("candidate38-udm37", candidate, 37, True))
        if args.capture_pair:
            # Add the observational control immediately before the candidate37
            # ON arm. The original engine4 arms and run_once remain unchanged.
            run_arms = (*run_arms[:-1], ("candidate38-udm37-capture-off", candidate, 37, False),
                        run_arms[-1])
        for arm, wrf_root, option, capture in run_arms:
            state["forecast_attempts"] = len(arms) + 1
            state["arm_in_progress"] = arm
            atomic_json(output / "execution.json", state)
            result = forecast(seed, output, arm, wrf_root, option, capture,
                              executable_pins[str(wrf_root / "main/wrf.exe")]["sha256"])
            state["models_invoked"] += int(bool(result["process"].get("launched")))
            arms.append({k: v for k, v in result.items() if k != "history_arrays"})
            state["arms_completed"] = arms
            state.pop("arm_in_progress", None)
            atomic_json(output / "execution.json", state)
        if args.capture_pair:
            state["candidate37_capture_pair"] = compare_capture_pair(arms[-2], arms[-1])
        if args.runtime_only:
            state["status"] = "PASS_SCOPED_STARTUP_SNOW_RUNTIME_ONLY"
            state["engine4_common_history_comparison"] = None
        else:
            # Exact common-variable raw array comparison on the two unchanged engine4 arms.
            comparison = compare_shared_history(
                _read_history_arrays(Path(arms[0]["history_path"])),
                _read_history_arrays(Path(arms[1]["history_path"])))
            state.pop("histories", None)
            state["engine4_common_history_comparison"] = comparison
            state["status"] = "PASS_SCOPED_STARTUP_SNOW_RADIUS_AND_ENGINE4_PRESERVATION"
        state["forecast_attempts"] = forecast_limit
        atomic_json(output / "execution.json", state)
        return 0
    except BaseException as exc:
        saved = list(output.glob("*/process-result.json"))
        records = []
        for path in saved:
            try:
                records.append(json.loads(path.read_text()))
            except Exception:
                continue
        state["ideal_invocations"] = sum(
            record.get("kind") == "ideal" and record.get("launched") for record in records)
        if records:
            state["ideal_invocation_state"] = "COMPLETE" if state["ideal_invocations"] else "NOT_STARTED"
        state["models_invoked"] = max(
            int(state.get("models_invoked", 0)),
            sum(record.get("kind") == "forecast" and record.get("launched") for record in records))
        state["status"] = "FAIL_PRESERVED"
        state["failure"] = f"{type(exc).__name__}: {exc}"
        atomic_json(output / "execution.json", state)
        raise


def _read_history_arrays(path: Path) -> dict[str, np.ndarray]:
    with netCDF4.Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        return {name: np.asarray(var[:]).copy() for name, var in ds.variables.items()}


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
