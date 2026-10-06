#!/usr/bin/env python3
"""Exercise LW CFC VMR capture, replay, and isolated gas-off reference variants.

This is an implementation contract test for short UDM27/37 SCM states. It does
not compare RRTMGP against a different radiation scheme as a CFC-effect estimate.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import numpy as np

import test_cloud_scm
import test_column_replay
import test_frozen_scm
import test_surface_scm
import test_udm_scm
from compare_column_replay import compare, read_result

WRF_ROOT = test_surface_scm.WRF_ROOT
DATA_DIR = test_surface_scm.DATA_DIR
SUCCESS = "SUCCESS COMPLETE WRF"
CFC_NAMES = ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4")
N2_MAGICS = {"RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"}
TRACE_GAS_MAGICS = {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V10", *N2_MAGICS}
STATIC_CFC = {"VMR_CFC11": 0.251e-9, "VMR_CFC12": 0.538e-9,
              "VMR_CFC22": 0.169e-9, "VMR_CCL4": 0.093e-9}


def fail(message: str) -> None:
    raise RuntimeError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def source_hashes() -> dict[str, str]:
    repo = WRF_ROOT.parent
    names = (
        "WRF/Registry/Registry.EM_COMMON", "WRF/share/module_check_a_mundo.F",
        "WRF/phys/module_physics_init.F", "WRF/phys/module_ra_rrtmg_lw.F",
        "WRF/phys/module_ra_rrtmgp.F", "WRF/phys/module_ra_rrtmgp_trace.F",
        "WRF/run/CAMtr_volume_mixing_ratio",
        "WRF/test/rrtmgp/test_column_replay.py", "WRF/test/rrtmgp/compare_column_replay.py",
        "WRF/test/rrtmgp/reference_column.f90", "WRF/test/rrtmgp/test_frozen_scm.py",
        "WRF/test/rrtmgp/test_lw_trace_gases_scm.py",
    )
    return {name: sha256(repo / name) for name in names if (repo / name).is_file()}


def clean_environment(*, capture_dir: Path | None = None,
                      capture_call: int | None = None) -> dict[str, str]:
    env = os.environ.copy()
    for name in list(env):
        if name.startswith("WRF_RRTMGP"):
            env.pop(name)
    env["OMP_NUM_THREADS"] = "1"
    if capture_dir is not None:
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture_dir)
        env["WRF_RRTMGP_CAPTURE_CALL"] = str(capture_call)
    return env


def prepare_mode_case(seed: dict[str, Any], case: Path, *, ghg_input: int) -> None:
    test_frozen_scm.make_case(seed, case, 37, 37)
    text = (case / "namelist.input").read_text(encoding="utf-8")
    text = test_udm_scm.replace_assignment(text, "ghg_input", str(ghg_input))
    (case / "namelist.input").write_text(text, encoding="utf-8")
    if "rrtmgp_udm_frozen_optics" in text.lower() or "rrtmgp_udm_frozen_table" in text.lower():
        fail(f"{case}: trace-gas run must use mode 0 and omit experimental frozen-table options")


def render_input(path: Path, header: tuple[str, int, int, int, int, int],
                 records: dict[str, np.ndarray], *, magic: str = "RRTMGP_REPLAY_V8") -> None:
    phase, nc, nl, overlap, seed, iceflag = header
    with path.open("w", encoding="ascii") as stream:
        if magic not in {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V10", *N2_MAGICS}:
            fail(f"cannot render unsupported LW replay magic {magic}")
        stream.write(magic + "\n")
        stream.write(f"{phase} {nc} {nl} {overlap} {seed} {iceflag}\n")
        for name, array in records.items():
            values = np.asarray(array, dtype=np.float64)
            if values.ndim != 2:
                fail(f"cannot render V8 {name}: expected rank 2, got {values.ndim}")
            stream.write(f"{name} {values.shape[0]} {values.shape[1]}\n")
            flat = values.ravel(order="F")
            for offset in range(0, flat.size, 5):
                stream.write(" ".join(f"{float(v):.17e}" for v in flat[offset:offset + 5]) + "\n")


def invoke_reference(reference: Path, input_path: Path, output_path: Path, case: Path) -> None:
    env = clean_environment()
    proc = subprocess.run([str(reference), str(DATA_DIR), str(input_path), str(output_path)],
                          cwd=case, env=env, stdout=subprocess.PIPE,
                          stderr=subprocess.STDOUT, text=True, check=False)
    (case / (output_path.stem + ".log")).write_text(proc.stdout, encoding="utf-8")
    if proc.returncode != 0 or not output_path.is_file():
        fail(f"independent reference failed for {input_path.name}: {proc.stdout[-3000:]}")


def validate_lw_capture(case: Path, phase: str, call: int, reference: Path,
                        expected_ghg: int) -> dict[str, Any]:
    capture = case / "capture"
    input_path = capture / "lw.input"
    result_path = capture / "lw.result"
    if not all(p.is_file() for p in (capture / "lw.raw", input_path, result_path)):
        fail(f"{case}: missing complete LW capture for call {call}")
    input_phase, nc, nl, overlap, seed, iceflag, records = test_column_replay.read_input(input_path)
    if input_phase != "LW" or nc != 1:
        fail(f"{case}: unexpected LW replay header phase={input_phase} nc={nc}")
    magic = input_path.read_text(encoding="ascii").splitlines()[0].strip()
    if magic not in TRACE_GAS_MAGICS:
        fail(f"{case}: expected a trace-gas replay (V8/V10/V12/V13), got {magic}")
    trace_present = True
    n2_report = None
    if magic in N2_MAGICS:
        n2 = records.get("VMR_N2")
        flag = records.get("TRACE_GASES_PRESENT")
        if n2 is None or n2.shape != (nc, nl) or not np.isfinite(n2).all() or np.any((n2 < 0.0) | (n2 > 1.0)):
            fail(f"{case}: {magic} requires finite VMR_N2 with shape {(nc, nl)} and values in [0,1]")
        if flag is None or flag.shape != (1, 1) or not np.isfinite(flag).all() or float(flag.item()) not in (0.0, 1.0):
            fail(f"{case}: {magic} requires scalar TRACE_GASES_PRESENT=0 or 1")
        trace_present = bool(flag.item())
        if trace_present != all(name in records for name in CFC_NAMES):
            fail(f"{case}: {magic} CFC sections disagree with TRACE_GASES_PRESENT={int(trace_present)}")
        n2_report = {"shape": list(n2.shape), "min_vmr": float(n2.min()), "max_vmr": float(n2.max()),
                     "preserved_in_reference_variants": True}
    raw_phase, raw_i, raw_j, raw = test_column_replay.read_raw(capture / "lw.raw")
    if raw_phase != "LW":
        fail(f"{case}: raw capture has phase {raw_phase}, expected LW")
    raw_nl = int(raw["DP_HPA"].size)
    raw_fields = {"VMR_CFC11": "VMR_CFC11", "VMR_CFC12": "VMR_CFC12",
                  "VMR_CFC22": "VMR_CFC22", "VMR_CCL4": "VMR_CCL4"}
    cfc_values: dict[str, dict[str, Any]] = {}
    if trace_present:
        for name in CFC_NAMES:
            values = records.get(name)
            if values is None or values.shape != (nc, nl):
                fail(f"{case}: {name} must be present with native adapter shape {(nc, nl)}")
            if not np.isfinite(values).all() or np.any(values < 0.0):
                fail(f"{case}: {name} must be finite and nonnegative")
            cfc_values[name] = {"shape": list(values.shape), "min_vmr": float(values.min()),
                                "max_vmr": float(values.max()),
                                "sha256_f64_fortran": hashlib.sha256(values.tobytes(order="F")).hexdigest()}
            raw_values = raw.get(raw_fields[name])
            if raw_values is not None:
                if raw_values.shape != (raw_nl,):
                    fail(f"{case}: raw {name} has unexpected shape")
                test_column_replay.assert_close(values[0, :raw_nl], raw_values,
                                                f"{case}: {magic} {name} equals native wrapper capture",
                                                rtol=0.0, atol=0.0)
            elif magic in {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V10"}:
                fail(f"{case}: raw native capture lacks {name} with {raw_nl} layers")
            if expected_ghg in (0, 1):
                expected = np.full(values.shape, STATIC_CFC[name], dtype=np.float64)
                test_column_replay.assert_close(values, expected,
                                                f"{case}: ideal-run CAM-reader fallback {name}",
                                                rtol=2.e-7, atol=1.e-18)
    production = read_result(result_path)
    if production["phase"] != "LW" or production["nc"] != nc or production["nl"] != nl:
        fail(f"{case}: production result dimensions disagree with V8 input")
    if "GAS_TAU_RAW" not in production["sections"]:
        fail(f"{case}: production result lacks GAS_TAU_RAW")

    reference_path = capture / "lw.reference.result"
    invoke_reference(reference, input_path, reference_path, case)
    reference_result = read_result(reference_path)
    replay = compare(production, reference_result)
    if not replay.get("passed"):
        fail(f"{case}: V8 LW reference replay failed: {replay.get('failed_sections')}")

    # For legacy schemas, zero the four captured arrays. V12/V13 use an
    # explicit presence bit: remove the CFC records and set it to zero while
    # retaining VMR_N2 and every other section byte-for-byte in value.
    zero_counterfactual = {"applicable": False, "reason": "trace-gas profiles are absent"}
    if trace_present:
        zero_records = {name: np.array(value, copy=True) for name, value in records.items()}
        for name in CFC_NAMES:
            if magic in N2_MAGICS:
                del zero_records[name]
            else:
                zero_records[name][:] = 0.0
        if magic in N2_MAGICS:
            zero_records["TRACE_GASES_PRESENT"][:] = 0.0
        zero_input = capture / "lw.cfc-zero.input"
        render_input(zero_input, (input_phase, nc, nl, overlap, seed, iceflag), zero_records, magic=magic)
        # Ensure the exact serialized variant is still valid under the same
        # schema; no conversion to an older replay format is allowed.
        zero_phase, zero_nc, zero_nl, _, _, _, reread = test_column_replay.read_input(zero_input)
        if (zero_phase, zero_nc, zero_nl) != ("LW", nc, nl):
            fail(f"{case}: malformed {magic} zero-CFC variant")
        if magic in N2_MAGICS:
            if float(reread["TRACE_GASES_PRESENT"].item()) != 0.0 or any(name in reread for name in CFC_NAMES):
                fail(f"{case}: V12/V13 zero-CFC variant must preserve N2 and omit all CFC records")
            if not np.array_equal(reread["VMR_N2"], records["VMR_N2"]):
                fail(f"{case}: V12/V13 zero-CFC variant changed the N2 profile")
        else:
            for name in CFC_NAMES:
                if np.any(reread[name] != 0.0):
                    fail(f"{case}: CFC-zero variant retained nonzero {name}")
        zero_result = capture / "lw.cfc-zero.result"
        invoke_reference(reference, zero_input, zero_result, case)
        zero_sections = read_result(zero_result)["sections"]
        # The production REAL32 result is independently replay-checked above;
        # this delta compares the reference engine against itself.
        actual_sections = reference_result["sections"]
        gas_diff = float(np.max(np.abs(actual_sections["GAS_TAU_RAW"] - zero_sections["GAS_TAU_RAW"])))
        if gas_diff <= 0.0:
            fail(f"{case}: captured CFC VMRs produce no GAS_TAU_RAW difference against zero-CFC replay")
        response = {}
        for name in ("UP", "DN", "HR"):
            if name not in zero_sections or name not in actual_sections:
                fail(f"{case}: missing {name} section in CFC attribution result")
            response[name] = float(np.max(np.abs(actual_sections[name] - zero_sections[name])))
        if max(response.values()) <= 0.0:
            fail(f"{case}: CFC VMRs changed GAS_TAU_RAW but no LW flux/heating output")
        zero_counterfactual = {"applicable": True, "reference_only": True,
            "gas_tau_raw_max_abs_difference": gas_diff,
            "flux_heating_max_abs_difference": response,
            "input_sha256": sha256(zero_input), "result_sha256": sha256(zero_result)}
    return {"phase": phase, "capture_call": call, "header": {"nc": nc, "nl": nl,
            "overlap": overlap, "seed": seed, "iceflag": iceflag},
            "replay_magic": magic, "n2_profile": n2_report,
            "trace_gases_present": trace_present,
            "cfc_vmr_records": cfc_values, "native_raw_cfc_equality": "PASS_EXACT",
            "raw_column_i_j": [raw_i, raw_j], "native_raw_layers": raw_nl,
            "ghg_input_setting": expected_ghg,
            "cfc_source_assessment": {
                "kind": ("ideal.exe initialization fallback" if trace_present else "trace gases absent by explicit V12/V13 flag"),
                "cam_reader_loaded_file": False,
                "explanation": (("physics_init skips read_CAMgases(READtrFILE=true) for ideal runs; "
                                 "these captured values are fallback constants, not evidence that "
                                 "the CAM tracer table was consumed") if trace_present else
                                "TRACE_GASES_PRESENT=0 and the V12/V13 format omits the CFC records"),
                "captured_cfc11_cfc12_cfc22_ccl4_are_fallback_constants": trace_present,
            },
            "reference_replay": {"status": "PASS", "sections_compared": replay["sections_compared"],
                                 "max_differences": replay["max_differences"]},
            "zero_cfc_counterfactual": zero_counterfactual,
            "files": {"input_sha256": sha256(input_path), "production_result_sha256": sha256(result_path),
                      "reference_result_sha256": sha256(reference_path),
                      "raw_sha256": sha256(capture / "lw.raw")}}


def run_capture(seed: dict[str, Any], root: Path, tag: str, call: int, wrf: Path,
                reference: Path, ghg_input: int) -> dict[str, Any]:
    case = root / f"{tag}-ra37-ghg{ghg_input}-call{call}"
    prepare_mode_case(seed, case, ghg_input=ghg_input)
    capture = case / "capture"
    capture.mkdir()
    initial_hash = sha256(case / "wrfinput_d01")
    log = test_frozen_scm.run_logged(wrf, case, "wrf.log",
                                     clean_environment(capture_dir=capture, capture_call=call))
    log_text = (case / "wrf.log").read_text(encoding="utf-8", errors="replace")
    if log.returncode != 0 or SUCCESS not in log_text:
        fail(f"{case}: WRF did not complete successfully (rc={log.returncode}); log tail:\n{log_text[-3000:]}")
    history = test_frozen_scm.validate_history(case, 37)
    if sha256(case / "wrfinput_d01") != initial_hash:
        fail(f"{case}: WRF changed its initial input")
    capture_report = validate_lw_capture(case, "LW", call, reference, ghg_input)
    return {"case": str(case), "ghg_input": ghg_input, "capture_call": call,
            "wrfinput_sha256": initial_hash, "namelist_sha256": sha256(case / "namelist.input"),
            "history_path": str(history["path"]), "history_report": history["report"],
            "log_sha256": sha256(case / "wrf.log"), "capture": capture_report}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--wrf", type=Path, required=True)
    parser.add_argument("--ideal", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--baseline-wrf", type=Path,
                        help="optional parent WRF executable for bitwise RRTMG4 preservation checks")
    parser.add_argument("--output-dir", type=Path, required=True,
                        help="new, absent directory for all generated SCM cases and receipts")
    args = parser.parse_args()
    wrf, ideal, reference = (p.expanduser().resolve() for p in
                             (args.wrf, args.ideal, args.reference))
    baseline = args.baseline_wrf.expanduser().resolve() if args.baseline_wrf else None
    root = args.output_dir.expanduser().resolve()
    if root.exists():
        parser.error(f"refusing existing output directory: {root}")
    if not root.parent.is_dir():
        parser.error(f"output parent must exist: {root.parent}")
    for executable in (wrf, ideal, reference, baseline):
        if executable is None:
            continue
        if not executable.is_file() or not executable.stat().st_mode & 0o111:
            parser.error(f"missing/non-executable executable: {executable}")
    for required in (test_surface_scm.TEMPLATE, test_surface_scm.INPUT_DIR / "input_sounding",
                     test_surface_scm.INPUT_DIR / "input_soil", test_surface_scm.INPUT_DIR / "force_ideal.nc",
                     DATA_DIR / "rrtmgp-gas-lw-g128.nc", DATA_DIR / "rrtmgp-gas-sw-g112.nc"):
        if not required.is_file():
            parser.error(f"missing required input: {required}")
    root.mkdir()
    sources_before = source_hashes()
    binaries_before = {"wrf": sha256(wrf), "ideal": sha256(ideal), "reference": sha256(reference),
                       "baseline_wrf": sha256(baseline) if baseline is not None else None}
    data_hashes = {p.name: sha256(p) for p in
                   (DATA_DIR / "rrtmgp-gas-lw-g128.nc", DATA_DIR / "rrtmgp-gas-sw-g112.nc",
                    DATA_DIR / "CAMtr_volume_mixing_ratio")}

    seeds: dict[str, dict[str, Any]] = {}
    fixtures: dict[str, Any] = {}
    for tag, mixed in (("control", False), ("mixed", True)):
        seed, fixture = test_frozen_scm.create_seed(root, tag, mixed, ideal)
        seeds[tag] = seed
        fixtures[tag] = fixture
        seed_hash = sha256(seed["wrfinput"])
        fixtures[tag]["generated_wrfinput_sha256"] = seed_hash

    current_cases: dict[str, Any] = {}
    for tag, seed in seeds.items():
        current_cases[tag] = {
            "ghg_input_1": {f"call{call}": run_capture(seed, root, tag, call, wrf, reference, 1)
                            for call in (1, 2)},
        }
    # One explicit static-source case anchors the wrapper's GHG_INPUT=0 defaults.
    current_cases["explicit_static_control"] = {
        "ghg_input_0": {"call1": run_capture(seeds["control"], root, "explicit-static-control", 1, wrf, reference, 0)}
    }

    # Radiation option 4 must remain bitwise identical to the parent executable;
    # these comparisons are separate from, and not an estimate of, a CFC effect.
    baseline_checks: dict[str, Any] = {}
    for tag, seed in seeds.items():
        current = test_frozen_scm.run_mode0_case(seed, root / f"ra4-{tag}-current", 4, wrf)
        if baseline is None:
            baseline_checks[tag] = {"status": "NOT_RUN_NO_BASELINE_EXECUTABLE",
                                    "current_case": current["case"],
                                    "wrfinput_sha256": current["wrfinput_sha256"]}
            continue
        previous = test_frozen_scm.run_parent_mode0(seed, root / f"ra4-{tag}-baseline", 4, baseline)
        if current["wrfinput_sha256"] != previous["wrfinput_sha256"]:
            fail(f"{tag}: current/baseline RRTMG4 inputs differ")
        check = test_frozen_scm.compare_history_bytes(current, previous, f"{tag} RRTMG4 baseline")
        baseline_checks[tag] = {"status": check["status"],
            "arrays_compared": check["arrays_compared"], "current_case": current["case"],
            "baseline_case": previous["case"], "wrfinput_sha256": current["wrfinput_sha256"]}

    sources_after = source_hashes()
    binaries_after = {name: sha256(path) for name, path in
                      (("wrf", wrf), ("ideal", ideal), ("reference", reference))}
    binaries_after["baseline_wrf"] = sha256(baseline) if baseline is not None else None
    if sources_before != sources_after:
        fail("source files changed during the CFC SCM validation")
    if binaries_before != binaries_after:
        fail("an executable changed during the CFC SCM validation")
    if data_hashes != {p.name: sha256(p) for p in
                       (DATA_DIR / "rrtmgp-gas-lw-g128.nc", DATA_DIR / "rrtmgp-gas-sw-g112.nc",
                        DATA_DIR / "CAMtr_volume_mixing_ratio")}:
        fail("pinned gas coefficient bytes changed during validation")

    summary = {
        "status": "PASS_LW_TRACE_GAS_INPUT_AND_REPLAY",
        "scope": {"scm_duration_minutes": 1, "microphysics": "UDM27",
                  "radiation": "RRTMGP37 LW/SW", "captures": "LW calls 1 and 2 for control/mixed; explicit GHG_INPUT=0 control call 1",
                  "gas_source_limit": "ideal.exe skips CAM-file initialization; GHG_INPUT=1 cases exercise the fallback path, not dynamic CAM table values",
                  "accuracy_claimed": False, "rrtmg4_role": "bitwise unchanged baseline only; not part of CFC attribution"},
        "provenance": {"executables_sha256_before_after": binaries_before,
                       "source_sha256_before_after": sources_before,
                       "gas_coefficient_sha256": data_hashes,
                       "git_head": subprocess.run(["git", "rev-parse", "HEAD"], cwd=WRF_ROOT.parent,
                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False).stdout.strip()},
        "fixtures": fixtures,
        "ghg_input_1_runs": {tag: result["ghg_input_1"] for tag, result in current_cases.items()
                             if tag in seeds},
        "explicit_ghg_input_0": current_cases["explicit_static_control"],
        "rrtmg4_parent_bitwise": baseline_checks,
    }
    rendered = json.dumps(summary, indent=2, sort_keys=True, default=str) + "\n"
    (root / "lw-trace-gases-scm-result.json").write_text(rendered, encoding="utf-8")
    print(rendered, end="")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
