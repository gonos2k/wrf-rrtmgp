#!/usr/bin/env python3
"""Replay and cross-check one selected WRF call-2 LW/V9-SW capture.

This is a post-run validator only. It never invokes WRF; it invokes the standalone
reference_column executable once per captured phase.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

import numpy as np


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def parse_raw(path: Path) -> tuple[str, list[str], dict[str, np.ndarray]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RAW_V1":
        raise ValueError(f"{path}: expected RRTMGP_RAW_V1")
    header = lines[1].split()
    if len(header) != 4:
        raise ValueError(f"{path}: malformed raw header")
    phase, i, j, nl = header[0].upper(), int(header[1]), int(header[2]), int(header[3])
    records: dict[str, np.ndarray] = {}
    p = 2
    while p < len(lines):
        fields = lines[p].split()
        p += 1
        if len(fields) != 2:
            raise ValueError(f"{path}:{p}: malformed raw record header")
        name, n = fields[0], int(fields[1])
        if n < 1 or name in records or p + n > len(lines):
            raise ValueError(f"{path}:{p}: invalid raw record {name}")
        values = np.asarray([float(x.replace("D", "E").replace("d", "e"))
                             for x in lines[p:p+n]], dtype=np.float64)
        p += n
        if not np.isfinite(values).all():
            raise ValueError(f"{path}: {name} contains nonfinite values")
        records[name] = values
    if nl < 1:
        raise ValueError(f"{path}: invalid layer count")
    return phase, [str(i), str(j), str(nl)], records


def read_activations(path: Path) -> list[tuple[int, float]]:
    grouped: dict[str, set[tuple[int, float]]] = {"LW": set(), "SW": set()}
    with path.open(newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            phase = row["phase"].strip().upper()
            if phase in grouped:
                grouped[phase].add((int(row["step"]), float(row["source_seconds"])))
    if grouped["LW"] != grouped["SW"] or len(grouped["LW"]) < 2:
        raise ValueError(f"{path}: expected at least two matching LW/SW source activations")
    return sorted(grouped["LW"])


def output_tolerance(expected: np.ndarray) -> np.ndarray:
    as32 = np.asarray(expected, dtype=np.float32)
    return 4.0 * np.abs(np.spacing(as32)).astype(np.float64) + 1.0e-6


def compare_host(actual: np.ndarray, expected: np.ndarray, label: str) -> dict:
    actual = np.asarray(actual, dtype=np.float64)
    expected = np.asarray(expected, dtype=np.float64)
    if actual.shape != expected.shape or not np.isfinite(actual).all() or not np.isfinite(expected).all():
        raise ValueError(f"{label}: shape/nonfinite mismatch {actual.shape} vs {expected.shape}")
    difference = np.abs(actual - expected)
    tolerance = output_tolerance(expected)
    passed = bool(np.all(difference <= tolerance))
    return {"passed": passed, "shape": list(actual.shape),
            "max_abs_difference": float(difference.max(initial=0.0)),
            "max_float32_tolerance": float(tolerance.max(initial=0.0)),
            "criterion": "4 float32 ULP + 1e-6"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("capture_dir", type=Path, help="ON run's capture directory")
    ap.add_argument("audit_csv", type=Path, help="same_state.csv from that ON run")
    ap.add_argument("reference_executable", type=Path)
    ap.add_argument("coefficient_directory", type=Path)
    ap.add_argument("frozen_table", type=Path)
    ap.add_argument("source_manifest", type=Path)
    ap.add_argument("source_root", type=Path)
    ap.add_argument("wrf_executable", type=Path)
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    capture = args.capture_dir.resolve()
    ref_exe = args.reference_executable.resolve()
    coeff = args.coefficient_directory.resolve()
    frozen = args.frozen_table.resolve()
    manifest = args.source_manifest.resolve()
    source_root = args.source_root.resolve()
    wrf_exe = args.wrf_executable.resolve()
    if not all(p.exists() for p in (capture, args.audit_csv, ref_exe, coeff, frozen, manifest, source_root, wrf_exe)):
        ap.error("capture, audit, executables, source manifest, coefficients, and frozen table must exist")
    output_path = args.output.resolve()
    if output_path.exists():
        ap.error(f"refusing to overwrite validation receipt: {output_path}")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    provenance_path = Path(__file__).resolve().with_name("reference-provenance.json")
    provenance = json.loads(provenance_path.read_text(encoding="utf-8"))
    pinned = provenance["build"]
    assets = provenance["data_assets"]
    if sha256(ref_exe) != pinned["reference_executable_sha256"]:
        raise ValueError("reference executable SHA differs from prepared provenance")
    if sha256(wrf_exe) != pinned["wrf_executable_sha256"]:
        raise ValueError("WRF executable SHA differs from prepared provenance")
    if sha256(manifest) != provenance["selected_source"]["source_manifest_sha256"]:
        raise ValueError("selected source-manifest SHA differs from prepared provenance")
    source_manifest = json.loads(manifest.read_text(encoding="utf-8"))
    if source_manifest.get("base_commit") != provenance["selected_source"]["reported_base_commit"]:
        raise ValueError("selected source-manifest base commit differs from prepared provenance")
    if source_manifest.get("source_tree") != "build/udm-selected-real-wrf/source":
        raise ValueError("selected source-manifest root differs from the staged source tree")
    for relative, expected in provenance["selected_source"]["key_source_sha256"].items():
        if sha256(source_root / relative) != expected:
            raise ValueError(f"selected source file SHA mismatch: {relative}")
    for filename, expected in assets["coefficient_sha256"].items():
        if sha256(coeff / filename) != expected:
            raise ValueError(f"coefficient SHA mismatch: {filename}")
    if sha256(frozen) != assets["frozen_table_sha256"]:
        raise ValueError("frozen table SHA differs from prepared provenance")

    # Import the exact schema parser/comparator from this selected source snapshot.
    test_dir = Path(__file__).resolve().parents[3] / "build/udm-selected-real-wrf/source/WRF/test/rrtmgp"
    if not (test_dir / "test_column_replay.py").is_file():
        # The default path above is workspace/build/udm-selected-real-audit/...; permit
        # an explicit source-root environment for relocatable evidence bundles.
        source_root = Path(os.environ.get("SELECTED_WRF_SOURCE", ""))
        test_dir = source_root / "WRF/test/rrtmgp"
    if not (test_dir / "test_column_replay.py").is_file():
        ap.error("cannot find selected source test_column_replay.py; set SELECTED_WRF_SOURCE")
    sys.path.insert(0, str(test_dir))
    from compare_column_replay import compare, read_result  # type: ignore
    from test_column_replay import read_input  # type: ignore

    activations = read_activations(args.audit_csv.resolve())
    second_step, second_source_seconds = activations[1]
    report: dict = {
        "schema": "UDM_SELECTED_POINT_INDEPENDENT_REPLAY_V1", "status": "FAIL",
        "scope": "one WRF point (169,80), one captured call (call 2), 39 native layers",
        "phase_results": {},
        "activation_mapping": {"second_observed_activation": {"step": second_step,
            "source_seconds": second_source_seconds}, "method": "paired LW/SW source step/time from ON same_state.csv"},
        "scope_limits": [
            "Standalone replay validates captured host-to-library inputs and independent wrapper reconstruction; it is not a forecast-accuracy test.",
            "The replay uses the same pinned RRTMGP/RTE library and frozen-table query component; it is independent of the WRF adapter and host preparation code.",
            "Frozen optics are recomputed from the hash-verified table by the reference's query interface; this is not an independent validation of the experimental frozen-optics physical model.",
            "This validator must be run only after the separately approved ON case completes; it does not execute WRF.",
        ],
    }
    env = os.environ.copy()
    env["WRF_RRTMGP_FROZEN_TABLE"] = str(frozen)
    all_pass = True
    reference_paths = []
    for phase in ("LW", "SW"):
        phase_lower = phase.lower()
        replay = capture / f"{phase_lower}.input"
        production_path = capture / f"{phase_lower}.result"
        raw_path = capture / f"{phase_lower}.raw"
        if not all(p.is_file() for p in (replay, production_path, raw_path)):
            raise ValueError(f"{phase}: missing .input/.result/.raw capture")
        magic = replay.read_text(encoding="ascii").splitlines()[0].strip()
        expected_magic = "RRTMGP_REPLAY_V8" if phase == "LW" else "RRTMGP_REPLAY_V9"
        if magic != expected_magic:
            raise ValueError(f"{phase}: expected {expected_magic}, found {magic}")
        parsed_phase, nc, nl, overlap, seed, iceflag, inputs = read_input(replay)
        if parsed_phase != phase or nc != 1:
            raise ValueError(f"{phase}: expected one-column capture, got {(parsed_phase,nc,nl)}")
        raw_phase, coord, raw = parse_raw(raw_path)
        native_nl = int(coord[2])
        if raw_phase != phase or coord[:2] != ["169", "80"] or native_nl != 39:
            raise ValueError(f"{phase}: expected point 169,80 and 39 native levels; found {raw_phase} {coord}")
        if nl < native_nl:
            raise ValueError(f"{phase}: replay has fewer engine layers ({nl}) than native layers ({native_nl})")
        if "PI" not in raw or raw["PI"].size != native_nl or np.any(raw["PI"] <= 0.0):
            raise ValueError(f"{phase}: raw PI must be positive with one value per native model layer")
        if int(round(raw.get("RADIATION_STEP", np.array([-1]))[0])) != second_step:
            raise ValueError(f"{phase}: raw call does not map to second activation step {second_step}")
        if abs(float(raw.get("SOURCE_TIME_SECONDS", np.array([float("nan")]))[0]) - second_source_seconds) > 1.e-3:
            raise ValueError(f"{phase}: raw source time does not map to second activation")
        if "NATIVE_DRY_LAYER_MASS_KG_M2" not in inputs:
            raise ValueError(f"{phase}: replay omitted native dry-layer mass")
        replay_dry_mass = inputs["NATIVE_DRY_LAYER_MASS_KG_M2"]
        if replay_dry_mass.shape != (1, native_nl):
            raise ValueError(f"{phase}: native dry mass shape {replay_dry_mass.shape} does not match raw model layers")
        if "DRY_LAYER_MASS_KG_M2" not in raw or not np.array_equal(
                replay_dry_mass, raw["DRY_LAYER_MASS_KG_M2"].reshape(1, native_nl)):
            raise ValueError(f"{phase}: native dry mass replay differs from the raw WRF layer-mass snapshot")
        if phase == "LW":
            for gas in ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4"):
                if gas not in inputs or inputs[gas].shape != (1, nl):
                    raise ValueError(f"LW: V8 replay missing {gas}")
                if gas not in raw or not np.array_equal(inputs[gas][:, :native_nl],
                                                         raw[gas].reshape(1, native_nl)):
                    raise ValueError(f"LW: replay {gas} differs from raw host VMR profile")
        else:
            for record in ("TOA_GPOINT", "RAW_GAS_TAU", "MCICA_MASK", "RAW_CLOUD_TAU",
                           "RAW_PRECIP_TAU", "RAW_GRAUPEL_TAU_EXT", "RAW_HAIL_TAU_EXT"):
                if record not in inputs:
                    raise ValueError(f"SW: V9 replay missing {record}")
        if inputs.get("FROZEN_MODE", np.zeros((1, 1))).item() != 1.0:
            raise ValueError(f"{phase}: selected experiment is expected to capture frozen mode 1")
        hash_bytes = inputs.get("FROZEN_TABLE_SHA256_BYTES")
        if hash_bytes is None:
            raise ValueError(f"{phase}: missing frozen table digest in replay input")
        recorded_frozen_sha = "".join(chr(int(v)) for v in hash_bytes[:, 0])
        if recorded_frozen_sha != sha256(frozen):
            raise ValueError(f"{phase}: capture frozen-table digest differs from selected asset")

        reference_path = output_path.with_name(output_path.stem + f".{phase_lower}.reference.result")
        if reference_path.exists():
            raise ValueError(f"refusing to overwrite reference output: {reference_path}")
        reference_paths.append(reference_path)
        run = subprocess.run([str(ref_exe), str(coeff), str(replay), str(reference_path)],
                             env=env, text=True, stdout=subprocess.PIPE,
                             stderr=subprocess.STDOUT, check=False)
        if run.returncode != 0:
            raise RuntimeError(f"{phase} independent reference failed ({run.returncode}): {run.stdout[-3000:]}")
        prod = read_result(production_path)
        ref = read_result(reference_path)
        section_diff = compare(prod, ref)
        psec = prod["sections"]
        rsec = ref["sections"]
        if "WRF_THETA_HR" not in psec or "HR" not in rsec:
            raise ValueError(f"{phase}: need host WRF_THETA_HR and RRTMGP HR for native heating check")
        # WRF stores potential-temperature tendency, while the standalone RTE
        # reference reports temperature heating in K/day.  PI maps theta-rate
        # back to temperature-rate: dT/dt = PI*dtheta/dt.
        host_theta = psec["WRF_THETA_HR"]
        if host_theta.shape != (1, native_nl, 1):
            raise ValueError(f"{phase}: WRF_THETA_HR should cover {native_nl} native levels, got {host_theta.shape}")
        if rsec["HR"].shape != (1, nl, 1):
            raise ValueError(f"{phase}: reference HR does not span the {nl} replay levels")
        pi = raw["PI"].reshape(1, native_nl, 1)
        host_temperature_hr = host_theta * pi * 86400.0
        host_checks = {"WRF_THETA_HR_times_PI_times_86400_vs_RTE_HR_K_day": compare_host(
            host_temperature_hr, rsec["HR"][:, :native_nl, :], f"{phase} theta-to-temperature heating")}
        if phase == "LW":
            host_checks["WRF_GLW_from_DN_surface"] = compare_host(
                psec["WRF_GLW"], rsec["DN"][:, :1, :], "LW surface down")
            host_checks["WRF_OLR_from_UP_TOA"] = compare_host(
                psec["WRF_OLR"], rsec["UP"][:, -1:, :], "LW TOA up")
        else:
            host_checks["WRF_GSW_from_surface_net"] = compare_host(
                psec["WRF_GSW"], rsec["DN"][:, :1, :] - rsec["UP"][:, :1, :], "SW surface net")
            host_checks["WRF_SWDDIR_from_DIRECT_surface"] = compare_host(
                psec["WRF_SWDDIR"], rsec["DIRECT"][:, :1, :], "SW surface direct horizontal")
            host_checks["WRF_SWDDIF_from_DIFFUSE_surface"] = compare_host(
                psec["WRF_SWDDIF"], rsec["DIFFUSE"][:, :1, :], "SW surface diffuse")
        phase_pass = section_diff.get("passed", False) and all(x["passed"] for x in host_checks.values())
        all_pass &= phase_pass
        report["phase_results"][phase] = {
            "pass": phase_pass, "schema": magic,
            "replay_header": {"overlap": overlap, "seed": seed, "iceflag": iceflag,
                              "nc": nc, "engine_nl": nl, "native_model_nl": native_nl,
                              "appended_upper_layers": nl-native_nl},
            "input_sha256": sha256(replay), "raw_sha256": sha256(raw_path),
            "production_result_sha256": sha256(production_path),
            "independent_reference_result_sha256": sha256(reference_path),
            "independent_replay": section_diff,
            "host_diagnostic_checks": host_checks,
            "native_contracts": {"native_dry_layer_mass_layers": int(inputs["NATIVE_DRY_LAYER_MASS_KG_M2"].shape[1]),
                                 "native_dry_mass_matches_raw_exactly": True,
                                 "frozen_table_sha256": recorded_frozen_sha,
                                 "call_step": second_step,
                                 "source_seconds": float(raw["SOURCE_TIME_SECONDS"][0]),
                                 "point_wrf_one_based": [169, 80]},
        }
    report["status"] = "PASS" if all_pass else "FAIL"
    output_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0 if all_pass else 1


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError, ValueError, subprocess.SubprocessError) as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        raise SystemExit(1)
