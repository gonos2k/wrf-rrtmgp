#!/usr/bin/env python3
"""Exercise reference_column's compiled CF0 precipitation sidecar reader.

Fixtures are small synthetic adapter captures.  The SW V9 capture is projected
to its clear second column because the current reader deliberately supports
one column only; positive sidecar paths are synthetic reader inputs, not a
claim that the projected adapter column carried that precipitation.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
from typing import Any

import numpy as np

from cf0_precip_sidecar import encode
from compare_column_replay import read_result
from test_column_replay import read_input


GLOBAL_RECORDS = {
    "ICE_ROUGHNESS", "SW_BAND_PARTITION", "PRECIPITATION_OPTICS",
    "GRAVITY", "CP_DRY", "MOL_WEIGHT_DRY", "SOLAR",
    "FROZEN_MODE", "FROZEN_OCCURRENCE", "FROZEN_TABLE_SHA256_BYTES",
    "SW_DIRECT_PREDELTA_POLICY", "CU_POPULATION_POLICY", "CU_RADIUS_POLICY",
    "CU_OCCURRENCE_POLICY", "BAND_LIMS_GPOINT", "BAND_LIMS_WAVENUMBER",
    "VISIBLE_WEIGHT",
}
PROCESS_INVOCATIONS: list[dict[str, Any]] = []
MUTABLE_SECTIONS = {
    "LW": {"TOTAL_TAU", "UP", "DN", "HR"},
    "SW": {"TOTAL_TAU", "TOTAL_SSA", "TOTAL_G", "UP", "DN", "HR",
           "DIRECT", "DIFFUSE", "VISDIR", "VISDIF", "NIRDIR", "NIRDIF"},
}


def run_tracked(role: str, command: list[str], env: dict[str, str], timeout: int) -> subprocess.CompletedProcess[str]:
    record: dict[str, Any] = {"role": role, "argv": command, "timeout_seconds": timeout}
    try:
        proc = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                              stderr=subprocess.STDOUT, check=False, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        record.update({"returncode": None, "timed_out": True,
                       "output_path_created": False})
        PROCESS_INVOCATIONS.append(record)
        raise RuntimeError(f"{role} timed out after {timeout}s: {command}") from exc
    except OSError as exc:
        record.update({"returncode": None, "timed_out": False,
                       "launch_error": f"{type(exc).__name__}: {exc}"})
        PROCESS_INVOCATIONS.append(record)
        raise
    record.update({"returncode": proc.returncode, "timed_out": False})
    PROCESS_INVOCATIONS.append(record)
    return proc


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def clean_env(capture: Path | None = None) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith("WRF_RRTMGP_"):
            env.pop(key, None)
    env["OMP_NUM_THREADS"] = "1"
    env["OMP_DYNAMIC"] = "FALSE"
    env["LC_ALL"] = "C"
    if capture is not None:
        env["WRF_RRTMGP_CAPTURE_DIR"] = str(capture)
    return env


def run_capture(executable: Path, data_dir: Path, mode: str, capture: Path) -> str:
    capture.mkdir(parents=True, exist_ok=False)
    command = [str(executable), str(data_dir), mode]
    proc = run_tracked("fixture_adapter", command, clean_env(capture), timeout=180)
    if proc.returncode != 0:
        raise RuntimeError(f"fixture generator {executable.name} {mode} failed ({proc.returncode}):\n{proc.stdout[-3000:]}")
    return proc.stdout


def write_input(path: Path, magic: str, phase: str, nc: int, nl: int,
                overlap: int, seed: int, iceflag: int,
                records: dict[str, np.ndarray]) -> None:
    lines = [magic, f"{phase} {nc} {nl} {overlap} {seed} {iceflag}"]
    for name, values in records.items():
        array = np.asarray(values, dtype=np.float64)
        if array.ndim < 1 or any(size < 1 for size in array.shape):
            raise ValueError(f"cannot serialize empty/invalid section {name}: {array.shape}")
        lines.append(name + " " + " ".join(str(int(size)) for size in array.shape))
        flat = array.ravel(order="F")
        for offset in range(0, flat.size, 6):
            lines.append(" ".join(f"{float(v):.17e}" for v in flat[offset:offset + 6]))
    path.write_text("\n".join(lines) + "\n", encoding="ascii")


def project_clear_sw_column(source: Path, destination: Path) -> dict[str, Any]:
    magic, nc, nl, overlap, seed, iceflag, records = read_input(source)
    if (magic, nc, nl) != ("SW", 2, 3):
        raise RuntimeError(f"expected captured two-column three-layer SW replay, got {(magic, nc, nl)}")
    projected: dict[str, np.ndarray] = {}
    sliced: list[str] = []
    preserved: list[str] = []
    for name, values in records.items():
        array = np.asarray(values)
        if name not in GLOBAL_RECORDS and array.ndim >= 2 and array.shape[0] == nc:
            projected[name] = array[1:2, ...].copy()
            sliced.append(name)
        else:
            projected[name] = array.copy()
            preserved.append(name)
    if "CF" not in projected or projected["CF"].shape != (1, nl) or np.any(projected["CF"] != 0.0):
        raise RuntimeError("the selected SW fixture column is not an all-clear column")
    if "RES" not in projected or projected["RES"].shape != (1, nl) or np.any(projected["RES"] <= 10.0):
        raise RuntimeError("synthetic snow audit requires captured native RES above 10 um")
    write_input(destination, "RRTMGP_REPLAY_V9", "SW", 1, nl, overlap, seed, iceflag, projected)
    reread = read_input(destination)
    if reread[:3] != ("SW", 1, nl):
        raise RuntimeError("projected one-column V9 input failed its parser roundtrip")
    return {"source_capture_sha256": sha256(source), "projected_input_sha256": sha256(destination),
            "source_columns": nc, "selected_source_column_one_based": 2,
            "projected_columns": 1, "layers": nl,
            "sliced_per_column_records": sorted(sliced),
            "preserved_global_records": sorted(preserved),
            "projection_is_synthetic_fixture_only": True}


def write_sidecar(path: Path, phase: str, species: int, cf: np.ndarray,
                  positive_layer: int | None) -> None:
    nlay = int(cf.shape[1])
    rain = [[0.0] * nlay]
    snow = [[0.0] * nlay]
    if positive_layer is not None:
        target = rain if species == 1 else snow
        target[0][positive_layer] = 100.0
    text = encode(phase, 1, nlay, species, 1.0, rain, snow, cf.tolist(), engine_n=nlay)
    path.write_text(text, encoding="ascii")


def run_reference(reference: Path, data_dir: Path, input_path: Path,
                  output_path: Path, sidecar: Path | None = None) -> subprocess.CompletedProcess[str]:
    command = [str(reference), str(data_dir), str(input_path), str(output_path)]
    if sidecar is not None:
        # Arguments 4 and 5 are SW policy and override path; preserve defaults.
        command += ["1", "", str(sidecar)]
    try:
        proc = run_tracked("reference_column", command, clean_env(), timeout=180)
    finally:
        # Attach the output path even when the subprocess times out, so the
        # receipt can distinguish pre-output rejection from other failures.
        PROCESS_INVOCATIONS[-1]["output_path"] = str(output_path)
        PROCESS_INVOCATIONS[-1]["output_path_created"] = output_path.exists()
    return proc


def success_reference(reference: Path, data_dir: Path, input_path: Path,
                      output_path: Path, sidecar: Path | None = None) -> dict[str, Any]:
    proc = run_reference(reference, data_dir, input_path, output_path, sidecar)
    if proc.returncode != 0 or not output_path.is_file():
        raise RuntimeError(f"compiled reference failed ({proc.returncode}):\n{proc.stdout[-3000:]}")
    return read_result(output_path)


def reject_reference(reference: Path, data_dir: Path, input_path: Path,
                     sidecar: Path, output_path: Path, message: str) -> None:
    proc = run_reference(reference, data_dir, input_path, output_path, sidecar)
    if proc.returncode == 0 or message not in proc.stdout:
        raise AssertionError(f"compiled reader did not reject {sidecar.name} with {message!r}:\n{proc.stdout[-2500:]}")
    if output_path.exists():
        raise AssertionError(f"reader rejection unexpectedly reached reference output creation: {output_path}")


def run_phase(reference: Path, data_dir: Path, root: Path, phase: str,
              input_path: Path, baseline_name: str) -> dict[str, Any]:
    magic, nc, nl, *_rest = read_input(input_path)
    expected_magic = "RRTMGP_REPLAY_V8" if phase == "LW" else "RRTMGP_REPLAY_V9"
    if input_path.read_text(encoding="ascii").splitlines()[0].strip() != expected_magic:
        raise RuntimeError(f"{phase} fixture magic is not {expected_magic}")
    if phase == "LW" and (magic, nc, nl) != ("LW", 1, 3):
        raise RuntimeError("expected one-column three-layer LW V8 fixture")
    if phase == "SW" and (magic, nc, nl) != ("SW", 1, 3):
        raise RuntimeError("expected projected one-column three-layer SW V9 fixture")
    records = _rest[-1]
    cf = records.get("CF")
    if cf is None or cf.shape != (1, nl) or not np.isfinite(cf).all():
        raise RuntimeError(f"{phase} input lacks finite CF matrix")
    snow_radius = records.get("RES")
    if snow_radius is None or snow_radius.shape != (1, nl) or np.any(snow_radius <= 10.0):
        raise RuntimeError(f"{phase} fixture must retain snow RES > 10 um")

    baseline_path = root / f"{phase.lower()}-{baseline_name}.result"
    baseline = success_reference(reference, data_dir, input_path, baseline_path)
    results: dict[str, Any] = {
        "input_magic": f"RRTMGP_REPLAY_V{8 if phase == 'LW' else 9}",
        "dimensions": [1, nl],
        "baseline_sha256": sha256(baseline_path),
        "zero_controls": {},
        "positive_species": {},
    }

    for species, species_name in ((1, "rain"), (2, "snow")):
        zero_sidecar = root / f"{phase.lower()}-{species_name}-zero.sidecar"
        write_sidecar(zero_sidecar, phase, species, cf, None)
        zero_path = root / f"{phase.lower()}-{species_name}-zero.result"
        zero_result = success_reference(reference, data_dir, input_path, zero_path, zero_sidecar)
        if zero_path.read_bytes() != baseline_path.read_bytes():
            raise AssertionError(f"{phase} all-zero {species_name} sidecar changed reference output bytes")
        results["zero_controls"][species_name] = {
            "accepted": True, "output_byte_equal_to_no_sidecar": True,
            "sidecar_sha256": sha256(zero_sidecar), "output_sha256": sha256(zero_path),
            "section_count": len(zero_result["sections"]),
        }

        # Use an interior native layer where CF is exactly zero.  The SW
        # projection has all-clear CF; the LW V8 fixture is clear sky.
        allowed = np.flatnonzero(cf[0] == 0.0)
        if allowed.size == 0:
            raise RuntimeError(f"{phase} positive sidecar requires an input layer with CF=0")
        layer = int(allowed[len(allowed) // 2])
        positive_sidecar = root / f"{phase.lower()}-{species_name}-positive.sidecar"
        write_sidecar(positive_sidecar, phase, species, cf, layer)
        positive_path = root / f"{phase.lower()}-{species_name}-positive.result"
        positive = success_reference(reference, data_dir, input_path, positive_path, positive_sidecar)
        sections = positive["sections"]
        required = ("AUDIT_EXTRA_PRECIP_TAU",) if phase == "LW" else (
            "AUDIT_EXTRA_PRECIP_TAU", "AUDIT_EXTRA_PRECIP_TAU_RAW", "AUDIT_EXTRA_PRECIP_SSA",
            "AUDIT_EXTRA_PRECIP_G", "AUDIT_DIRECT_PREDELTA")
        missing = [name for name in required if name not in sections]
        if missing:
            raise AssertionError(f"{phase} positive {species_name} sidecar omitted outputs {missing}")
        expected_sections = set(baseline["sections"])
        if phase == "LW":
            expected_sections.add("AUDIT_EXTRA_PRECIP_TAU")
        else:
            expected_sections.update({"AUDIT_EXTRA_PRECIP_TAU", "AUDIT_EXTRA_PRECIP_TAU_RAW",
                                      "AUDIT_EXTRA_PRECIP_SSA", "AUDIT_EXTRA_PRECIP_G",
                                      "AUDIT_DIRECT_PREDELTA"})
        if set(sections) != expected_sections:
            raise AssertionError(f"{phase} positive {species_name} output section set changed: "
                                 f"missing={sorted(expected_sections-set(sections))}, "
                                 f"extra={sorted(set(sections)-expected_sections)}")
        for name in sorted(set(baseline["sections"]) - MUTABLE_SECTIONS[phase]):
            if (sections[name].shape != baseline["sections"][name].shape or
                    sections[name].tobytes(order="F") != baseline["sections"][name].tobytes(order="F")):
                raise AssertionError(f"{phase} positive {species_name} unexpectedly changed invariant {name}")
        for name in required:
            values = sections[name]
            if not np.isfinite(values).all():
                raise AssertionError(f"{phase} positive {species_name} output {name} is non-finite")
            expected_shape = (baseline["sections"]["DIRECT_PREDELTA"].shape
                              if name == "AUDIT_DIRECT_PREDELTA" else
                              baseline["sections"].get("PRECIP_TAU", baseline["sections"]["CLOUD_TAU"]).shape)
            if values.shape != expected_shape:
                raise AssertionError(f"{phase} positive {species_name} output {name} has wrong optical shape")
        if not np.any(sections["AUDIT_EXTRA_PRECIP_TAU"] > 0.0):
            raise AssertionError(f"{phase} positive {species_name} did not create nonzero audit optical depth")
        if np.any(sections["AUDIT_EXTRA_PRECIP_TAU"] < 0.0):
            raise AssertionError(f"{phase} positive {species_name} audit optical depth is negative")
        changed_fluxes = {}
        for name in ("UP", "DN", "HR"):
            if sections[name].shape != baseline["sections"][name].shape:
                raise AssertionError(f"{phase} positive {species_name} changed {name} shape")
            changed_fluxes[name] = float(np.max(np.abs(sections[name] - baseline["sections"][name])))
        if not any(value > 0.0 for value in changed_fluxes.values()):
            raise AssertionError(f"{phase} positive {species_name} optical depth did not affect UP/DN/HR")
        if phase == "SW":
            if not np.any(sections["AUDIT_EXTRA_PRECIP_TAU_RAW"] > 0.0):
                raise AssertionError(f"SW positive {species_name} did not create raw audit optical depth")
            direct_shape = sections["AUDIT_DIRECT_PREDELTA"].shape
            if direct_shape != (1, nl + 1, 1):
                raise AssertionError(f"SW audit direct shape {direct_shape} != {(1, nl + 1, 1)}")
            if np.any(sections["AUDIT_EXTRA_PRECIP_SSA"] < 0.0) or np.any(sections["AUDIT_EXTRA_PRECIP_SSA"] > 1.0):
                raise AssertionError("SW audit SSA is outside [0,1]")
            if np.any(sections["AUDIT_EXTRA_PRECIP_G"] < -1.0) or np.any(sections["AUDIT_EXTRA_PRECIP_G"] > 1.0):
                raise AssertionError("SW audit asymmetry factor is outside [-1,1]")
            direct_base = baseline["sections"]["DIRECT_PREDELTA"]
            audit_direct = sections["AUDIT_DIRECT_PREDELTA"]
            slack = 64.0 * np.finfo(np.float64).eps * max(1.0, float(np.max(direct_base)))
            if np.any(audit_direct < 0.0) or np.any(audit_direct > direct_base + slack):
                raise AssertionError("SW audit direct beam violates nonnegative attenuation bounds")
            if not np.any(audit_direct < direct_base - slack):
                raise AssertionError("SW positive sidecar did not attenuate audit direct beam")
        results["positive_species"][species_name] = {
            "accepted": True, "synthetic_audit_path_g_m2": 100.0,
            "positive_layer_zero_based": layer, "positive_native_layer_count": 1,
            "sidecar_sha256": sha256(positive_sidecar), "output_sha256": sha256(positive_path),
            "audit_sections": {name: list(sections[name].shape) for name in required},
            "max_audit_tau": float(np.max(sections["AUDIT_EXTRA_PRECIP_TAU"])),
            "max_abs_rte_response": changed_fluxes,
        }
    return results


def mutate_cf_input(source: Path, destination: Path, values: list[float]) -> None:
    magic, nc, nl, overlap, seed, iceflag, records = read_input(source)
    changed = {name: np.asarray(array).copy() for name, array in records.items()}
    if changed["CF"].shape != (1, nl) or len(values) != nl:
        raise RuntimeError("CF mutation requires a one-column input and one value per layer")
    changed["CF"][0, :] = np.asarray(values, dtype=np.float64)
    write_input(destination, "RRTMGP_REPLAY_V8" if magic == "LW" else "RRTMGP_REPLAY_V9",
                magic, nc, nl, overlap, seed, iceflag, changed)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", type=Path, required=True)
    parser.add_argument("--reference", type=Path, required=True)
    parser.add_argument("--lw-generator", type=Path, required=True)
    parser.add_argument("--sw-generator", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--work-root", type=Path, required=True)
    args = parser.parse_args()
    data_dir, reference, lw_generator, sw_generator = (p.resolve() for p in
        (args.data, args.reference, args.lw_generator, args.sw_generator))
    for path in (data_dir, reference, lw_generator, sw_generator):
        if not path.exists():
            parser.error(f"required path does not exist: {path}")
    work_parent = args.work_root.resolve()
    work_parent.mkdir(parents=True, exist_ok=True)
    work_root = Path(tempfile.mkdtemp(prefix="run-", dir=work_parent))
    output = args.output.resolve()
    output.parent.mkdir(parents=True, exist_ok=True)
    report: dict[str, Any] = {
        "status": "FAIL",
        "scope": "compiled current reference_column sidecar reader; synthetic fixture/projection only",
        "compiled_fortran_reader_exercised": True,
        "model_invocations": 0,
        "process_invocations": [],
        "executables": {
            "reference": {"path": str(reference), "sha256": sha256(reference)},
            "lw_fixture_generator": {"path": str(lw_generator), "sha256": sha256(lw_generator)},
            "sw_fixture_generator": {"path": str(sw_generator), "sha256": sha256(sw_generator)},
        },
        "phases": {},
        "reject_controls": {},
    }
    try:
        lw_capture = work_root / "lw-capture"
        run_capture(lw_generator, data_dir, "zero", lw_capture)
        lw_input = lw_capture / "lw.input"
        if not lw_input.is_file():
            raise RuntimeError("LW generator did not emit lw.input")
        lw_summary = run_phase(reference, data_dir, work_root, "LW", lw_input,
                               "without-sidecar")
        lw_summary["capture_sha256"] = sha256(lw_input)

        sw_capture = work_root / "sw-capture"
        run_capture(sw_generator, data_dir, "capture_precip", sw_capture)
        sw_input = sw_capture / "sw.input"
        if not sw_input.is_file():
            raise RuntimeError("SW generator did not emit sw.input")
        sw_projected = work_root / "sw-clear-column-v9.input"
        projection = project_clear_sw_column(sw_input, sw_projected)
        sw_summary = run_phase(reference, data_dir, work_root, "SW", sw_projected,
                               "without-sidecar")
        sw_summary["projection"] = projection

        # Exercise compiled-reader failures before reference output creation.
        phase_input = sw_projected
        bad_cf = work_root / "sw-cf-positive.input"
        mutate_cf_input(phase_input, bad_cf, [0.0, 0.5, 0.0])
        rain_sidecar = work_root / "sw-cf-positive.sidecar"
        _sw_phase, _sw_nc, sw_nl, *_tail = read_input(phase_input)
        cf_positive = np.zeros((1, sw_nl), dtype=np.float64)
        write_sidecar(rain_sidecar, "SW", 1, cf_positive, 1)
        reject_reference(reference, data_dir, bad_cf, rain_sidecar,
                         work_root / "reject-positive-cf.result",
                         "audit path is only permitted where CF is zero")
        report["reject_controls"]["positive_path_where_cf_positive"] = "PASS_REJECTED_BEFORE_OUTPUT"

        bad_nan_cf = work_root / "sw-cf-nan.input"
        mutate_cf_input(phase_input, bad_nan_cf, [0.0, float("nan"), 0.0])
        reject_reference(reference, data_dir, bad_nan_cf, rain_sidecar,
                         work_root / "reject-nan-cf.result",
                         "audit cloud fraction must be finite and in [0,1]")
        report["reject_controls"]["nan_cf"] = "PASS_REJECTED_BEFORE_OUTPUT"

        valid_sidecar = work_root / "sw-valid-units.sidecar"
        write_sidecar(valid_sidecar, "SW", 1, cf_positive, 1)
        bad_units = work_root / "sw-bad-units.sidecar"
        bad_units.write_text(valid_sidecar.read_text(encoding="ascii").replace(
            "PATH_UNITS_G_M2", "PATH_UNITS_KG_M2"), encoding="ascii")
        reject_reference(reference, data_dir, phase_input, bad_units,
                         work_root / "reject-units.result",
                         "audit sidecar path units must be g m-2")
        report["reject_controls"]["wrong_units"] = "PASS_REJECTED_BEFORE_OUTPUT"

        bad_count = work_root / "sw-bad-native-count.sidecar"
        bad_count.write_text(encode("SW", 1, sw_nl + 1, 1, 1.0,
                                    [[0.0] * (sw_nl + 1)], [[0.0] * (sw_nl + 1)],
                                    [[0.0] * (sw_nl + 1)]) + "", encoding="ascii")
        reject_reference(reference, data_dir, phase_input, bad_count,
                         work_root / "reject-native-count.result",
                         "audit sidecar native layer count out of bounds")
        report["reject_controls"]["native_count_out_of_bounds"] = "PASS_REJECTED_BEFORE_OUTPUT"

        report["phases"] = {"LW": lw_summary, "SW": sw_summary}
        report["status"] = "PASS_COMPILED_FORTRAN_CF0_SIDECAR_CONTRACT"
    except Exception as exc:
        report["error"] = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        report["process_invocations"] = PROCESS_INVOCATIONS
        report["process_counts"] = {
            "reference_column_attempts": sum(x["role"] == "reference_column" for x in PROCESS_INVOCATIONS),
            "reference_column_successes": sum(x["role"] == "reference_column" and x.get("returncode") == 0
                                              for x in PROCESS_INVOCATIONS),
            "reference_column_rejected_before_output": sum(
                x["role"] == "reference_column" and x.get("returncode") is not None
                and x.get("returncode") != 0
                and not x.get("output_path_created", False) for x in PROCESS_INVOCATIONS),
            "fixture_adapter_attempts": sum(x["role"] == "fixture_adapter" for x in PROCESS_INVOCATIONS),
            "model_forecasts": 0,
        }
        output.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "report": str(output),
                      "compiled_fortran_reader_exercised": True,
                      "process_counts": report["process_counts"],
                      "model_invocations": 0}, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
