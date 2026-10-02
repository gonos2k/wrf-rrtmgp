#!/usr/bin/env python3
"""Validate opt-in experimental UDM graupel/hail optics in short SCM runs.

This checks adapter input contracts and independent table replay for one-minute
finite-initial-state fixtures. It is not a long-forecast or physical-accuracy
validation.
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
from pathlib import Path
from typing import Any

import netCDF4
import numpy as np

import test_cloud_scm
import test_column_replay
import test_surface_scm
import test_udm_scm
from compare_column_replay import compare, read_result

WRF_ROOT = test_surface_scm.WRF_ROOT
INPUT_DIR = test_surface_scm.INPUT_DIR
DATA_DIR = test_surface_scm.DATA_DIR
SUCCESS = "SUCCESS COMPLETE WRF"
HERE = Path(__file__).resolve().parent
REPO_ROOT = WRF_ROOT.parent
sys.path.insert(0, str(REPO_ROOT / "tools/udm_frozen_optics"))
import lookup  # noqa: E402


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def hash_sources() -> dict[str, str]:
    names = (
        "WRF/Registry/Registry.EM_COMMON", "WRF/share/module_check_a_mundo.F",
        "WRF/phys/module_physics_init.F", "WRF/phys/module_ra_rrtmgp.F",
        "WRF/phys/module_ra_rrtmgp_input.F", "WRF/phys/module_ra_rrtmgp_frozen.F",
        "WRF/phys/module_ra_rrtmgp_trace.F", "WRF/phys/module_ra_rrtmg_lw.F",
        "WRF/phys/module_ra_rrtmg_sw.F", "WRF/test/rrtmgp/reference_column.f90",
        "WRF/test/rrtmgp/test_column_replay.py", "WRF/test/rrtmgp/test_frozen_scm.py",
    )
    return {name: sha256(REPO_ROOT / name) for name in names if (REPO_ROOT / name).is_file()}


def clean_environment(*, capture_dir: Path | None = None, capture_call: int | None = None,
                      table: Path | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("WRF_RRTMGP"):
            env.pop(name)
    env["OMP_NUM_THREADS"] = "1"
    if capture_dir is not None:
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture_dir)
        env["WRF_RRTMGP_CAPTURE_CALL"] = str(capture_call)
    if table is not None:
        env["WRF_RRTMGP_FROZEN_TABLE"] = str(table)
    return env


def run_logged(executable: Path, case: Path, logfile: str,
               env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    with (case / logfile).open("w", encoding="utf-8") as stream:
        return subprocess.run([str(executable)], cwd=case, env=env, stdout=stream,
                              stderr=subprocess.STDOUT, text=True, check=False)


def create_seed(root: Path, tag: str, mixed: bool, ideal_exe: Path) -> tuple[dict[str, Any], dict[str, Any]]:
    seed_dir = root / f"seed-{tag}"
    test_surface_scm.prepare_case(seed_dir, 0)
    base = test_cloud_scm.original_lsm2_namelist()
    (seed_dir / "namelist.input").write_text(test_udm_scm.make_namelist(base, 4, 4, 1), encoding="utf-8")
    ideal = run_logged(ideal_exe, seed_dir, "ideal.log", clean_environment())
    if ideal.returncode != 0 or not (seed_dir / "wrfinput_d01").is_file():
        fail(f"{seed_dir}: ideal.exe failed; inspect ideal.log")
    fixture = test_udm_scm.write_initial_udm_fixture(seed_dir / "wrfinput_d01", mixed)
    seed = {"path": seed_dir, "wrfinput": seed_dir / "wrfinput_d01",
            "namelist": seed_dir / "namelist.input", "fixture": fixture}
    return seed, fixture


def frozen_seed_copy(seed: dict[str, Any], root: Path, tag: str) -> tuple[dict[str, Any], dict[str, Any]]:
    target = root / f"frozen-seed-{tag}"
    test_surface_scm.prepare_case(target, 0)
    shutil.copy2(seed["namelist"], target / "namelist.input")
    shutil.copy2(seed["wrfinput"], target / "wrfinput_d01")
    layer = int(seed["fixture"]["layer_index_zero_based"])
    with netCDF4.Dataset(target / "wrfinput_d01", "r+") as ds:
        for name in ("QGRAUP", "QHAIL"):
            if name not in ds.variables:
                fail(f"{target}: missing {name} frozen fixture variable")
            values = np.asarray(ds.variables[name][:], dtype=np.float64)
            values[:] = 0.0
            values[0, layer, :, :] = 1.0e-6
            ds.variables[name][:] = values
    frozen = {"path": target, "wrfinput": target / "wrfinput_d01",
              "namelist": target / "namelist.input", "fixture": seed["fixture"]}
    with netCDF4.Dataset(frozen["wrfinput"]) as ds:
        expected_shape = ds.variables["QGRAUP"].shape
        if not np.all(np.asarray(ds.variables["QGRAUP"][0, layer]) == np.float32(1.0e-6)) or \
           not np.all(np.asarray(ds.variables["QHAIL"][0, layer]) == np.float32(1.0e-6)):
            fail(f"{target}: positive initial G/H fixture did not persist")
    return frozen, {"layer_zero_based": layer, "qgraupel_kg_kg": 1.e-6,
                    "qhail_kg_kg": 1.e-6, "array_shape": list(expected_shape)}


def make_case(seed: dict[str, Any], case: Path, lw: int, sw: int,
              table: Path | None = None) -> None:
    test_surface_scm.prepare_case(case, 0)
    source = seed["namelist"].read_text(encoding="utf-8")
    text = test_udm_scm.make_namelist(source, lw, sw, 1)
    if table is not None:
        text = test_udm_scm.replace_assignment(text, "rrtmgp_udm_frozen_optics", "1")
        text = test_udm_scm.replace_assignment(
            text, "rrtmgp_udm_frozen_table", "'" + str(table).replace("'", "''") + "'")
    (case / "namelist.input").write_text(text, encoding="utf-8")
    shutil.copy2(seed["wrfinput"], case / "wrfinput_d01")
    if table is None and re.search(r"(?im)^\s*rrtmgp_udm_frozen_(?:optics|table)\s*=", text):
        fail(f"{case}: mode-zero namelist must omit frozen options")
    if table is not None and ("rrtmgp_udm_frozen_optics = 1" not in text or
                              str(table) not in text):
        fail(f"{case}: frozen namelist options were not written")


def validate_history(case: Path, option: int) -> dict[str, Any]:
    return test_udm_scm.validate_history(case, option)


def compare_history_bytes(left: dict[str, Any], right: dict[str, Any], label: str) -> dict[str, Any]:
    a = left.get("history_arrays", left.get("arrays"))
    b = right.get("history_arrays", right.get("arrays"))
    if a is None or b is None:
        fail(f"{label}: history arrays are missing")
    common = sorted(a.keys() & b.keys())
    left_only, right_only = sorted(a.keys() - b.keys()), sorted(b.keys() - a.keys())
    numeric_kinds = set("iufc")
    left_numeric = {name for name, value in a.items() if value.dtype.kind in numeric_kinds}
    right_numeric = {name for name, value in b.items() if value.dtype.kind in numeric_kinds}
    if left_numeric != right_numeric:
        fail(f"{label}: numeric variable sets differ: left-only={sorted(left_numeric-right_numeric)}, "
             f"right-only={sorted(right_numeric-left_numeric)}")
    mismatches: list[str] = []
    compared: list[str] = []
    for name in common:
        if a[name].shape != b[name].shape or a[name].dtype != b[name].dtype:
            mismatches.append(name)
        elif a[name].dtype.kind in "OUS":
            if not np.array_equal(a[name], b[name]):
                mismatches.append(name)
        elif a[name].dtype.kind in "iufc":
            compared.append(name)
            if a[name].tobytes() != b[name].tobytes():
                mismatches.append(name)
    if not compared:
        fail(f"{label}: no common numeric history arrays")
    if mismatches:
        fail(f"{label}: numeric/history arrays differ: {mismatches[:30]}")
    return {"status": "PASS_BITWISE", "arrays_compared": compared,
            "left_only": left_only, "right_only": right_only}


def run_mode0_case(seed: dict[str, Any], case: Path, option: int,
                   executable: Path) -> dict[str, Any]:
    make_case(seed, case, option, option)
    input_hash = sha256(case / "wrfinput_d01")
    run = run_logged(executable, case, "wrf.log", clean_environment())
    if run.returncode != 0:
        fail(f"{case}: WRF returned {run.returncode}; inspect wrf.log")
    history = validate_history(case, option)
    if sha256(case / "wrfinput_d01") != input_hash:
        fail(f"{case}: WRF changed its initial input")
    return {"case": str(case), "option": option, "wrfinput_sha256": input_hash,
            "history_path": str(history["path"]), "history_arrays": history["arrays"],
            "history_report": history["report"], "namelist_sha256": sha256(case / "namelist.input")}


def run_parent_mode0(seed: dict[str, Any], case: Path, option: int,
                     executable: Path) -> dict[str, Any]:
    result = run_mode0_case(seed, case, option, executable)
    if re.search(r"(?im)^\s*rrtmgp_udm_frozen_(?:optics|table)\s*=", (case / "namelist.input").read_text()):
        fail(f"{case}: parent namelist must not contain new frozen flags")
    return result


def validate_frozen_capture(case: Path, phase: str, call: int, reference_exe: Path,
                            table: Path, table_model: Any, fixture_layer: int) -> dict[str, Any]:
    capture = case / "capture"
    raw_path, input_path = capture / f"{phase.lower()}.raw", capture / f"{phase.lower()}.input"
    raw_phase, i, j, raw = test_column_replay.read_raw(raw_path)
    input_phase, nc, nl, overlap, seed, iceflag, inp = test_column_replay.read_input(input_path)
    if (raw_phase, input_phase, nc) != (phase, phase, 1) or (i, j) != (1, 1):
        fail(f"{case}: unexpected {phase} raw/input header {raw_phase}/{input_phase}, nc={nc}, i/j={i}/{j}")
    if len(raw["DP_HPA"]) < 1:
        fail(f"{case}: no physical WRF layers in raw snapshot")
    raw_nl = len(raw["DP_HPA"])
    if raw.get("MP_PHYSICS", np.array([-1.])).shape != (1,) or int(raw["MP_PHYSICS"][0]) != 27:
        fail(f"{case}: capture does not identify UDM27")
    if raw.get("RHO", np.empty(0)).shape != (raw_nl,) or not np.isfinite(raw["RHO"]).all() or np.any(raw["RHO"] <= 0.):
        fail(f"{case}: raw moist density must be finite positive for all physical layers")
    if not (raw_nl <= nl and inp["PLAY"].shape == (1, nl)):
        fail(f"{case}: V7 input does not contain raw physical layers plus optional extension")
    if not (input_path.is_file() and (capture / f"{phase.lower()}.result").is_file()):
        fail(f"{case}: incomplete V7 capture")
    if inp.get("FROZEN_MODE", np.zeros((0, 0))).shape != (1, 1) or inp["FROZEN_MODE"].item() != 1.0:
        fail(f"{case}: V7 frozen mode metadata is not one")
    if inp.get("FROZEN_OCCURRENCE", np.zeros((0, 0))).shape != (1, 1) or inp["FROZEN_OCCURRENCE"].item() != 1.0:
        fail(f"{case}: frozen precip occurrence must be explicit uniform one")
    recorded_hash = "".join(chr(int(value)) for value in inp["FROZEN_TABLE_SHA256_BYTES"][:, 0])
    actual_table_hash = sha256(table)
    if recorded_hash != actual_table_hash:
        fail(f"{case}: V7 table identity {recorded_hash} != supplied table SHA256 {actual_table_hash}")

    dry_mass, mass_source = test_column_replay.dry_layer_mass_kg_m2(raw, raw_nl, require_native=True)
    phase_report: dict[str, Any] = {}
    q_corrected: dict[str, np.ndarray] = {}
    for species, q_name, short in (("graupel", "QG", "GWP"), ("hail", "QH", "HWP")):
        q = test_column_replay.corrected_hydrometeor(raw, q_name, short, raw_nl)
        if q.shape != (raw_nl,):
            fail(f"{case}: {q_name} does not match raw physical layers")
        q_corrected[species] = q
        expected_grid = q * dry_mass * 1000.0
        for suffix, expected in (("GRID", expected_grid), ("RADIATION", expected_grid),
                                 ("OMITTED", np.zeros(raw_nl, dtype=np.float64))):
            name = f"{short}_{suffix}"
            if name not in raw:
                fail(f"{case}: raw snapshot lacks {name}")
            test_column_replay.assert_close(raw[name], expected,
                f"{case}: {name} = sanitized q times native dry mass, uniform occurrence",
                rtol=3.e-6, atol=2.e-6)
        if not np.any(q > 0.0) or not np.any(expected_grid > 0.0):
            fail(f"{case}: positive {species} fixture disappeared before {phase} capture")
        path_record, lambda_record = inp[short], inp["LAMBDA_G" if species == "graupel" else "LAMBDA_H"]
        if path_record.shape != (1, nl) or lambda_record.shape != (1, nl):
            fail(f"{case}: V7 {short}/lambda shapes must span the complete adapter column")
        test_column_replay.assert_close(path_record[0, :raw_nl], expected_grid,
            f"{case}: V7 {short} native layers", rtol=3.e-6, atol=2.e-6)
        test_column_replay.assert_close(path_record[0, raw_nl:], np.zeros(nl-raw_nl),
            f"{case}: above-top {short} optical extension is zero", rtol=0., atol=0.)
        expected_lambda = lookup.reconstructed_udm_slope(q, raw["RHO"], species)
        test_column_replay.assert_close(raw[f"FROZEN_LAMBDA_{species[0].upper()}_M-1"], expected_lambda,
            f"{case}: raw diagnostic {species} lambda from sanitized q and moist RHO", rtol=5.e-7, atol=1.e-5)
        test_column_replay.assert_close(lambda_record[0, :raw_nl], expected_lambda,
            f"{case}: V7 native {species} lambda independently reconstructed", rtol=5.e-7, atol=1.e-5)
        test_column_replay.assert_close(lambda_record[0, raw_nl:], np.full(nl-raw_nl, 20000.),
            f"{case}: above-top {species} lambda sentinel", rtol=0., atol=0.)
        active_clear = (q > 0.0) & (raw["CF"][:raw_nl] == 0.0)
        active_cloudy = (q > 0.0) & (raw["CF"][:raw_nl] > 0.0)
        phase_report[species] = {"positive_layers": int(np.count_nonzero(q > 0.0),),
                                 "clear_cf_positive_layers": int(np.count_nonzero(active_clear)),
                                 "cloudy_cf_positive_layers": int(np.count_nonzero(active_cloudy)),
                                 "max_grid_path_g_m2": float(np.max(expected_grid, initial=0.0))}
    # The clear fixture proves frozen precip is not silently gated by cloud CF.
    cf = raw["CF"][:raw_nl]
    if fixture_layer >= raw_nl:
        fail(f"{case}: initial cold-level fixture lies outside the captured physical column")
    if case.name.startswith("frozen-control-"):
        for species, q in q_corrected.items():
            if q[fixture_layer] <= 0.0 or cf[fixture_layer] != 0.0:
                fail(f"{case}: clear fixture layer must retain positive {species} with CF=0")
    elif case.name.startswith("frozen-mixed-"):
        for species, q in q_corrected.items():
            if q[fixture_layer] <= 0.0 or cf[fixture_layer] <= 0.0:
                fail(f"{case}: mixed fixture layer must retain positive {species} with CF>0")

    result_path = capture / f"{phase.lower()}.result"
    production = read_result(result_path)
    for name in (("GRAUPEL_TAU_ABS", "HAIL_TAU_ABS") if phase == "LW" else
                 ("GRAUPEL_TAU_EXT", "HAIL_TAU_EXT")):
        values = production["sections"].get(name)
        if values is None or values.shape[1] < raw_nl:
            fail(f"{case}: production result lacks native {name} optical response")
        species = "graupel" if name.startswith("GRAUPEL") else "hail"
        active = q_corrected[species] > 0.0
        if not np.any(values[0, :raw_nl][active] > 0.0):
            fail(f"{case}: positive {species} path produced no positive {name}")
    frozen_tau = production["sections"].get("FROZEN_TAU")
    if frozen_tau is None or frozen_tau.shape[1] < raw_nl or not np.any(frozen_tau[0, :raw_nl] > 0.):
        fail(f"{case}: positive G/H inputs produced no frozen optical-depth contribution")

    reference_path = capture / f"{phase.lower()}.reference.result"
    env = clean_environment(table=table)
    run = subprocess.run([str(reference_exe), str(DATA_DIR), str(input_path), str(reference_path)],
                         cwd=case, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                         text=True, check=False)
    if run.returncode != 0 or not reference_path.is_file():
        fail(f"{case}: independent V7 {phase} reference failed: {run.stdout[-2500:]}")
    replay = compare(production, read_result(reference_path))
    if not replay.get("passed"):
        fail(f"{case}: independent V7 {phase} replay mismatch: {replay.get('failed_sections')}")
    return {"phase": phase, "call": call, "raw_column_i_j": [i, j],
            "replay_passed": True, "replay_sections_compared": replay["sections_compared"],
            "native_dry_mass_source": mass_source, "frozen_paths": phase_report,
            "result_sha256": sha256(result_path), "input_sha256": sha256(input_path),
            "raw_sha256": sha256(raw_path), "reference_sha256": sha256(reference_path)}


def run_frozen_capture(seed: dict[str, Any], case: Path, wrf_exe: Path,
                       reference_exe: Path, table: Path, table_model: Any,
                       call: int) -> dict[str, Any]:
    make_case(seed, case, 37, 37, table)
    capture = case / "capture"
    capture.mkdir()
    before_input = sha256(case / "wrfinput_d01")
    before_table = sha256(table)
    env = clean_environment(capture_dir=capture, capture_call=call)
    run = run_logged(wrf_exe, case, "wrf.log", env)
    if run.returncode != 0:
        tail = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")[-3000:]
        fail(f"{case}: WRF returned {run.returncode}; log tail:\n{tail}")
    history = validate_history(case, 37)
    if sha256(case / "wrfinput_d01") != before_input or sha256(table) != before_table:
        fail(f"{case}: initial input or frozen table changed during runtime")
    captures = {phase: validate_frozen_capture(case, phase, call, reference_exe,
                     table, table_model, int(seed["fixture"]["layer_index_zero_based"]))
                for phase in ("LW", "SW")}
    return {"case": str(case), "call": call, "history_path": str(history["path"]),
            "history_report": history["report"], "wrfinput_sha256": before_input,
            "namelist_sha256": sha256(case / "namelist.input"),
            "capture": captures, "log_sha256": sha256(case / "wrf.log")}


def run_mode0_parent_comparisons(seed_map: dict[str, dict[str, Any]], root: Path,
                                 wrf: Path, baseline: Path | None) -> dict[str, Any]:
    results: dict[str, Any] = {}
    for tag, seed in seed_map.items():
        results[tag] = {}
        for option in (37, 4):
            current = run_mode0_case(seed, root / f"mode0-{tag}-ra{option}-current", option, wrf)
            entry: dict[str, Any] = {"current": {"case": current["case"],
                "wrfinput_sha256": current["wrfinput_sha256"], "history_path": current["history_path"]}}
            if baseline is not None:
                parent = run_parent_mode0(seed, root / f"mode0-{tag}-ra{option}-parent", option, baseline)
                if current["wrfinput_sha256"] != parent["wrfinput_sha256"]:
                    fail(f"{tag} RA{option}: current and parent did not use byte-identical wrfinput")
                comparison = compare_history_bytes(current, parent, f"{tag} mode0 RA{option} parent comparison")
                entry["parent"] = {"case": parent["case"], "history_path": parent["history_path"]}
                entry["comparison"] = comparison
            else:
                entry["comparison"] = {"status": "NOT_RUN_NO_BASELINE_EXECUTABLE"}
            results[tag][f"ra{option}"] = entry
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrf", type=Path, required=True, help="current WRF executable")
    parser.add_argument("--ideal", type=Path, required=True, help="ideal.exe used to generate inputs")
    parser.add_argument("--reference", type=Path, required=True, help="independent V7 reference_column executable")
    parser.add_argument("--baseline-wrf", type=Path, help="optional parent WRF executable for mode-zero bitwise comparisons")
    parser.add_argument("--table", type=Path, required=True, help="frozen-optics generation directory or its NetCDF file")
    parser.add_argument("--output-dir", type=Path, required=True, help="new isolated output root")
    args = parser.parse_args()
    wrf, ideal, reference = (p.expanduser().resolve() for p in (args.wrf, args.ideal, args.reference))
    baseline = args.baseline_wrf.expanduser().resolve() if args.baseline_wrf else None
    table_arg = args.table.expanduser().resolve()
    table = table_arg / "frozen-ice-psd-moments.nc" if table_arg.is_dir() else table_arg
    table_root = table.parent
    root = args.output_dir.expanduser().resolve()
    if root.exists():
        parser.error(f"refusing existing output directory: {root}")
    if not root.parent.is_dir():
        parser.error(f"output parent must exist: {root.parent}")
    for executable in (wrf, ideal, reference, *((baseline,) if baseline else ())):
        if not executable.is_file() or not executable.stat().st_mode & 0o111:
            parser.error(f"missing/non-executable program: {executable}")
    for needed in (table, table_root / "result.json", test_surface_scm.TEMPLATE,
                   INPUT_DIR / "input_sounding", INPUT_DIR / "input_soil", INPUT_DIR / "force_ideal.nc",
                   WRF_ROOT / "test/rrtmgp/radiation_iofields.txt", DATA_DIR / "rrtmgp-gas-lw-g128.nc",
                   DATA_DIR / "rrtmgp-gas-sw-g112.nc", test_udm_scm.VALIDATOR):
        if not needed.is_file():
            parser.error(f"missing required file: {needed}")
    table_model = lookup.FrozenTable(table_root)
    table_hash = sha256(table)
    if table_model.table_sha256 != table_hash:
        parser.error("lookup artifact table identity differs from supplied table file")
    root.mkdir()
    source_hashes_before = hash_sources()
    binaries = {"wrf": sha256(wrf), "ideal": sha256(ideal), "reference": sha256(reference),
                "baseline_wrf": sha256(baseline) if baseline else None}
    seeds: dict[str, dict[str, Any]] = {}
    frozen_seeds: dict[str, dict[str, Any]] = {}
    fixtures: dict[str, Any] = {}
    for tag, mixed in (("control", False), ("mixed", True)):
        seed, fixture = create_seed(root, tag, mixed, ideal)
        seeds[tag] = seed
        frozen_seeds[tag], frozen_fixture = frozen_seed_copy(seed, root, tag)
        fixtures[tag] = {"initial_udm_fixture": fixture, "frozen_g_h_fixture": frozen_fixture,
                         "baseline_wrfinput_sha256": sha256(seed["wrfinput"]),
                         "frozen_wrfinput_sha256": sha256(frozen_seeds[tag]["wrfinput"])}

    frozen_runs: dict[str, Any] = {}
    for tag, seed in frozen_seeds.items():
        frozen_runs[tag] = {}
        for call in (1, 2):
            case = root / f"frozen-{tag}-call{call}"
            frozen_runs[tag][f"call{call}"] = run_frozen_capture(
                seed, case, wrf, reference, table, table_model, call)
    mode0 = run_mode0_parent_comparisons(seeds, root, wrf, baseline)
    source_hashes_after = hash_sources()
    if source_hashes_before != source_hashes_after:
        fail("tracked WRF/reference source bytes changed during SCM validation")
    if sha256(table) != table_hash:
        fail("frozen table changed during SCM validation")
    binary_hashes_after = {"wrf": sha256(wrf), "ideal": sha256(ideal), "reference": sha256(reference),
                           "baseline_wrf": sha256(baseline) if baseline else None}
    if binaries != binary_hashes_after:
        fail("one or more executable bytes changed during SCM validation")

    summary = {
        "status": "PASS_RUNTIME_EXPERIMENTAL_ONLY",
        "scope": {"runtime_minutes": 1, "initial_fixture_only": True,
                  "forecast_readiness_claimed": False, "scientific_accuracy_claimed": False,
                  "cases": ["clear-CF positive G/H", "mixed cloud plus positive G/H"],
                  "mode1_captures": "LW/SW calls 1 and 2 independently captured and replayed"},
        "provenance": {"executables_sha256_before": binaries, "executables_sha256_after": binary_hashes_after,
                       "table_path": str(table), "table_sha256_before_after": table_hash,
                       "table_generation_receipt": str(table_root / "result.json"),
                       "source_revision": subprocess.run(["git", "rev-parse", "HEAD"], cwd=REPO_ROOT,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False).stdout.strip(),
                       "source_file_sha256_before_after": source_hashes_before},
        "fixtures": fixtures,
        "frozen_mode1_runs": frozen_runs,
        "mode0_parent_bitwise": mode0,
    }
    rendered = json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    (root / "frozen-scm-result.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
