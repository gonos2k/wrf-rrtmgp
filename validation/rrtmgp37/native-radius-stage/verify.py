#!/usr/bin/env python3
"""Verify archived UDM radius-stage packets and conditional Nc sensitivity."""
from __future__ import annotations

import hashlib
import importlib.util
import argparse
import json
import math
from pathlib import Path
import sys


PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]
MANIFEST_PATH = PACKAGE / "manifest.json"
PARSER_REL = "WRF/test/rrtmgp/test_udm_radius_stage.py"
NATIVE_REL = "WRF/phys/module_mp_udm.F"
PARSER_SHA = "4a0117959f3b716c52bb3e2fdc051715956299019cc5ff4aa84e8de63b9b4fe8"
NATIVE_SHA = "872737fe3a0cebf941d3ee45056fb60aadf465f0f72d72d1a2c7abac6709351d"
RADIUS_FIELDS = ("SOURCE_RE_CLOUD", "SOURCE_RE_ICE", "SOURCE_RE_SNOW")
RADIUS_BOUNDS_M = (2.51e-6, 50.0e-6)


def fail(message: str) -> None:
    raise ValueError(message)


def require(condition: bool, message: str) -> None:
    if not condition:
        fail(message)


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def close(actual: float, expected: float) -> bool:
    return math.isclose(actual, expected, rel_tol=1e-14, abs_tol=1e-20)


def without_paths(value):
    """Ignore only physical file paths; preserve hashes, sizes and all science fields."""
    if isinstance(value, dict):
        return {k: without_paths(v) for k, v in value.items() if k != "path"}
    if isinstance(value, list):
        return [without_paths(v) for v in value]
    return value


def read_json(rel: str) -> dict:
    return json.loads((PACKAGE / rel).read_text(encoding="utf-8"))


def load_parser(path: Path):
    spec = importlib.util.spec_from_file_location("udm_radius_stage_parser", path)
    if spec is None or spec.loader is None:
        fail("cannot load pinned stage parser")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def validate_manifest() -> dict:
    manifest = read_json("manifest.json")
    require(manifest.get("schema") == "UDM_NATIVE_RADIUS_STAGE_ARCHIVE_V1", "manifest schema")
    payload = manifest.get("payload")
    require(isinstance(payload, list), "manifest payload must be a list")
    payload_paths = []
    for row in payload:
        require(isinstance(row, dict) and set(row) == {"path", "sha256", "size_bytes"},
                "malformed payload row")
        rel = row["path"]
        require(isinstance(rel, str) and rel and not Path(rel).is_absolute() and ".." not in Path(rel).parts,
                f"unsafe payload path {rel!r}")
        payload_paths.append(rel)
    require(len(payload_paths) == len(set(payload_paths)), "duplicate payload path")
    actual = {p.relative_to(PACKAGE).as_posix() for p in PACKAGE.rglob("*")
              if p.is_file() and p != MANIFEST_PATH}
    require(set(payload_paths) == actual,
            f"payload roster mismatch: missing={sorted(set(payload_paths)-actual)}, "
            f"unlisted={sorted(actual-set(payload_paths))}")
    for row in payload:
        p = PACKAGE / row["path"]
        require(not p.is_symlink(), f"payload symlink is not allowed: {row['path']}")
        raw = p.read_bytes()
        require(len(raw) == row["size_bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],
                f"payload hash/size mismatch: {row['path']}")

    pins = manifest.get("source_pins")
    require(isinstance(pins, list) and pins, "manifest source_pins missing")
    pin_map = {}
    for row in pins:
        require(isinstance(row, dict) and set(row) == {"path", "sha256", "size_bytes"},
                "malformed source pin")
        rel = row["path"]
        require(isinstance(rel, str) and bool(rel.strip()) and not Path(rel).is_absolute() and ".." not in Path(rel).parts,
                f"unsafe source path {rel!r}")
        require(rel not in pin_map, f"duplicate source pin {rel}")
        p = REPO / rel
        require(not p.is_symlink(), f"source symlink is not allowed: {rel}")
        require(p.is_file(), f"missing pinned source {rel}")
        raw = p.read_bytes()
        require(len(raw) == row["size_bytes"] and hashlib.sha256(raw).hexdigest() == row["sha256"],
                f"source hash/size mismatch: {rel}")
        pin_map[rel] = row
    require(PARSER_REL in pin_map and pin_map[PARSER_REL]["sha256"] == PARSER_SHA,
            "parser source pin mismatch")
    require(NATIVE_REL in pin_map and pin_map[NATIVE_REL]["sha256"] == NATIVE_SHA,
            "native source pin mismatch")
    return {"payload_count": len(payload), "source_pins": pin_map}


def validate_join(source_pins: dict) -> dict:
    parser_path = REPO / PARSER_REL
    require(sha256(parser_path) == PARSER_SHA, "parser changed after manifest validation")
    parser = load_parser(parser_path)
    capture = PACKAGE / "capture"
    raw_files = sorted(p.name for p in capture.glob("*.raw"))
    expected = ["lw.raw", "sw.raw"] + [f"udm_radius_d1_i1_j1_step{k}.raw" for k in range(1, 7)]
    require(raw_files == sorted(expected), f"capture raw roster mismatch: {raw_files}")
    # Compare the saved state-transfer contract alone. Formula diagnostics are
    # recomputed independently from raw records in validate_sensitivity below.
    fresh = parser.inspect(capture, require_matched=True, include_liquid_formula=False)
    saved = read_json("evidence/stage-join.json")
    require(without_paths(fresh) == without_paths(saved), "saved stage join differs from fresh parser output")
    require(fresh["producer_packets"] == 6 and fresh["radiation_packets"] == 2,
            "capture packet counts")
    require(fresh["matched_consumers"] == 2 and fresh["bootstrap_consumers"] == 0,
            "stage-join counts")
    require({row["phase"] for row in fresh["joins"]} == {"LW", "SW"}, "both radiation phases required")
    for row in fresh["joins"]:
        require(row["status"] == "MATCHED_RADIUS_TRANSFER" and row["producer_step"] == 1 and
                row["radiation_step"] == 2 and row["all_three_radius_arrays_binary64_exact"],
                "expected same-column step-1 producer to step-2 phase transfer")
    return {"parser": parser, "fresh": fresh}


def validate_sensitivity(parser, fresh_join: dict) -> dict:
    data = read_json("evidence/nc-sensitivity.json")
    require(data.get("schema") == "UDM_NC_UNIT_CONDITIONAL_HELD_STATE_V1", "Nc sensitivity schema")
    require(data.get("status") == "CONDITIONAL_UNIT_SENSITIVITY_NOT_UNIT_VALIDATION", "Nc status")
    require(data.get("parser_sha256") == PARSER_SHA and data.get("native_source_sha256") == NATIVE_SHA,
            "Nc sensitivity source joins")
    require(data.get("runtime_counts") == {"WRF": 0, "REAL": 0, "build": 0, "RTE": 0,
                                            "compiled_replay": 0}, "Nc runtime counters")
    rows = data.get("rows")
    require(isinstance(rows, list) and len(rows) == 198, "expected 198 sensitivity rows")

    producers = {}
    for file_pin in fresh_join["fresh"]["producer_pins"]:
        packet = parser.parse_packet(Path(file_pin["path"]))
        producers[packet.header[1]] = packet
    require(sorted(producers) == list(range(1, 7)), "six unique producer states required")
    expected_active = set()
    for step, packet in producers.items():
        kts, kte = packet.header[4:6]
        for offset, (qc, nc, rho) in enumerate(zip(packet.fields["SOURCE_QC"],
                                                    packet.fields["SOURCE_QNC"],
                                                    packet.fields["SOURCE_RHO"])):
            if qc * rho > 1.e-12 and nc * rho > 1.e-6:
                expected_active.add((step, kts + offset))
    seen = set()
    vol_values, mass_values, densities, ratios = [], [], [], []
    volume_bounds = mass_bounds = 0
    for row in rows:
        step, k = row.get("producer_step"), row.get("native_k")
        key = (step, k)
        require(key not in seen, f"duplicate sensitivity row {key}")
        seen.add(key)
        require(step in producers, f"unknown producer step {step}")
        packet = producers[step]
        offset = k - packet.header[4]
        require(0 <= offset < packet.header[5] - packet.header[4] + 1, f"native level out of bounds {key}")
        qc = packet.fields["SOURCE_QC"][offset]
        nc = packet.fields["SOURCE_QNC"][offset]
        rho = packet.fields["SOURCE_RHO"][offset]
        captured = packet.fields["SOURCE_RE_CLOUD"][offset]
        water = parser.scalar(packet, "RHO_WATER")
        require(all(row[name] == val for name, val in (("qc_raw", qc), ("nc_raw", nc),
                                                         ("rho_kg_m3", rho), ("captured_radius_m", captured))),
                f"sensitivity row values do not join to producer packet {key}")
        require(qc > 0 and nc > 0 and rho > 0 and water > 0, f"nonpositive active row inputs {key}")
        require(qc * rho > 1.e-12 and nc * rho > 1.e-6, f"saved sensitivity row fails source guards {key}")
        r_volume = (0.75 * qc * rho / (math.pi * water * nc)) ** (1.0 / 3.0)
        r_mass = (0.75 * qc / (math.pi * water * nc)) ** (1.0 / 3.0)
        r_volume_bounded = min(RADIUS_BOUNDS_M[1], max(RADIUS_BOUNDS_M[0], r_volume))
        r_mass_bounded = min(RADIUS_BOUNDS_M[1], max(RADIUS_BOUNDS_M[0], r_mass))
        expected = {
            "if_Nc_per_m3_radius_unbounded_m": r_volume,
            "if_Nc_per_kg_radius_unbounded_m": r_mass,
            "if_Nc_per_m3_radius_bounded_m": r_volume_bounded,
            "if_Nc_per_kg_radius_bounded_m": r_mass_bounded,
            "unit_interpretation_ratio_unbounded": r_volume / r_mass,
            "ratio_density_prediction": rho ** (1.0 / 3.0),
            "if_Nc_per_m3_captured_difference_m": captured - r_volume_bounded,
            "if_Nc_per_kg_captured_difference_m": captured - r_mass_bounded,
        }
        for name, value in expected.items():
            require(close(row[name], value), f"formula mismatch {key}/{name}: {row[name]} vs {value}")
        for name, value in (("volume_bound_active", r_volume != r_volume_bounded),
                            ("mass_bound_active", r_mass != r_mass_bounded)):
            require(row[name] is value, f"bound flag mismatch {key}/{name}")
        volume_bounds += r_volume != r_volume_bounded
        mass_bounds += r_mass != r_mass_bounded
        densities.append(rho)
        ratios.append(r_volume / r_mass)
        vol_values.append(abs(captured - r_volume_bounded))
        mass_values.append(abs(captured - r_mass_bounded))
    require(seen == expected_active, "saved rows do not exactly cover raw-packet QC/Nc-guarded levels")
    require(len(seen) == 198, "expected 198 active sensitivity rows")
    require(volume_bounds == 0 and mass_bounds == 0, "unexpected radius bound activation")
    require(data["active_rows"] == 198, "active row summary")
    for key, values in (("density_min_max", densities), ("unit_ratio_min_max", ratios)):
        saved = data[key]
        require(len(saved) == 2 and close(saved[0], min(values)) and close(saved[1], max(values)),
                f"sensitivity summary mismatch: {key}")
    require(close(data["max_abs_captured_minus_volume_interpretation_m"], max(vol_values)),
            "volume interpretation max-difference summary")
    require(close(data["max_abs_captured_minus_mass_interpretation_m"], max(mass_values)),
            "mass interpretation max-difference summary")
    return {"rows": len(rows), "volume_bounds_active": volume_bounds,
            "mass_bounds_active": mass_bounds, "density_range": [min(densities), max(densities)],
            "conditional_ratio_range": [min(ratios), max(ratios)]}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--output", type=Path, help="write one JSON summary to a new file (never overwrite)")
    args = ap.parse_args()
    manifest = validate_manifest()
    joined = validate_join(manifest["source_pins"])
    sensitivity = validate_sensitivity(joined["parser"], joined)
    result = {"status": "PASS_SAVED_RADIUS_STAGE_AND_CONDITIONAL_NC_SENSITIVITY",
              "payload_files_checked": manifest["payload_count"],
              "source_pin_count": len(manifest["source_pins"]),
              "producer_packets": joined["fresh"]["producer_packets"],
              "matched_lw_sw_stage_transfers": joined["fresh"]["matched_consumers"],
              "sensitivity": sensitivity,
              "model_invocations": 0, "build_invocations": 0,
              "RTE_invocations": 0, "solver_invocations": 0,
              "physical_units_resolved": False,
              "radiation_psd_validated": False,
              "physical_accuracy_claim": False}
    rendered = json.dumps(result, sort_keys=True, allow_nan=False)
    if args.output is None:
        print(rendered)
    else:
        with args.output.open("x", encoding="utf-8") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True, allow_nan=False) + "\n")
        print(rendered)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        sys.exit(1)
