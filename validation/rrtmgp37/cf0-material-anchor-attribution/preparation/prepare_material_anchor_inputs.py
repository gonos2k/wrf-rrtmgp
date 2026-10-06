#!/usr/bin/env python3
"""Prepare four exact CF0 audit sidecars; never invoke the reference engine."""
from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
VALIDATOR = ROOT / "build/udm37-cf0-retained-cu-eight-inputs-v1/validate_sidecar.py"
INVENTORY = ROOT / "build/udm37-cf0-next-anchor-inventory-v1/inventory.json"
BASELINE_EXECUTION = ROOT / "build/udm37-occurrence-clipping-baseline-replay-v1/runs-v1/execution.json"


def pin(path: Path) -> dict:
    path = Path(path)
    content = path.read_bytes()
    return {"path": str(path.relative_to(ROOT)), "bytes": len(content),
            "sha256": hashlib.sha256(content).hexdigest()}


def parse_records(path: Path) -> tuple[list[str], dict[str, np.ndarray]]:
    lines = path.read_text().splitlines()
    header, records, pos = lines[1].split(), {}, 2
    while pos < len(lines):
        fields = lines[pos].split()
        pos += 1
        if not fields:
            continue
        name = fields[0]
        if name in {"END", "RAW_END", "INPUT_END"}:
            break
        shape = ((int(fields[1]),) if len(fields) == 2
                 else tuple(map(int, fields[1:])))
        count = int(np.prod(shape))
        values: list[float] = []
        while len(values) < count:
            if pos >= len(lines):
                raise ValueError(f"truncated {name} section in {path}")
            values.extend(float(v.replace("D", "E").replace("d", "e"))
                          for v in lines[pos].split())
            pos += 1
        if len(values) != count:
            raise ValueError(f"bad {name} section count in {path}")
        records[name] = np.asarray(values).reshape(shape, order="F")
    return header, records


def main() -> None:
    output_names = ["roster.json", "winter-rain-lw.sidecar", "winter-rain-sw.sidecar",
                    "low-cloud-snow-lw.sidecar", "low-cloud-snow-sw.sidecar"]
    if any((HERE / name).exists() for name in output_names):
        raise SystemExit("roster already exists; preserve it and prepare in a new directory")
    sys.path.insert(0, str(VALIDATOR.parent))
    import validate_sidecar as validator

    specs = [
        {"anchor": "winter_native_cu", "folder": "winter-native-cu",
         "coordinate": [17, 58], "species": "rain", "key": "RWP_OMITTED",
         "q_key": "SOURCE_QR", "sidecar_prefix": "winter-rain",
         "cu_policy": 1, "formats": {"LW": "V10", "SW": "V11"}},
        {"anchor": "material_cf0_snow_low_cloud", "folder": "ice_clip_low_cloud_proxy",
         "coordinate": [132, 35], "species": "snow", "key": "SWP_OMITTED",
         "q_key": "SOURCE_QS", "sidecar_prefix": "low-cloud-snow",
         "cu_policy": 0, "formats": {"LW": "V8", "SW": "V9"}},
    ]
    baseline_receipt = json.loads(BASELINE_EXECUTION.read_text())
    inherited_assets = baseline_receipt["pinned_files_before"]
    for asset in inherited_assets:
        path = Path(asset["path"])
        if not path.is_absolute():
            path = ROOT / path
        actual = pin(path)
        assert actual["bytes"] == asset["bytes"] and actual["sha256"] == asset["sha256"], actual
    inventory = json.loads(INVENTORY.read_text())
    inventory_pins = [entry for anchor in inventory["anchors"]
                      for row in anchor["phases"].values()
                      for entry in row["same_call_input_raw_result"]]
    for item in inventory_pins:
        actual = pin(ROOT / item["path"])
        assert actual["bytes"] == item["bytes"] and actual["sha256"] == item["sha256"]

    planned, sidecar_rows = [], []
    sidecar_paths = []
    for spec in specs:
        for phase in ("LW", "SW"):
            cap = ROOT / "build/udm37-occurrence-clipping-baseline-replay-v1/runs-v1" / \
                  f"{spec['folder']}-{phase.lower()}" / "capture"
            input_path, raw_path, result_path = (cap / f"{phase.lower()}.{suffix}"
                                                 for suffix in ("input", "raw", "result"))
            ih, input_data = parse_records(input_path)
            raw_header, raw_data = validator.parse_raw(raw_path)
            format_id = input_path.read_text().splitlines()[0]
            phase_in, ncol, engine_n, overlap, seed, iceflag = ih[0], *map(int, ih[1:])
            raw_phase, i, j, native_n = raw_header
            assert phase_in == raw_phase == phase and [i, j] == spec["coordinate"]
            assert ncol == 1 and len(raw_data["CF"]) == native_n <= engine_n
            assert format_id.endswith(spec["formats"][phase])
            cu_policy = int(input_data.get("CU_POPULATION_POLICY", np.zeros(1)).item())
            assert cu_policy == spec["cu_policy"]

            source_path = np.asarray(raw_data[spec["key"]], dtype=np.float64)
            cf = np.asarray(raw_data["CF"], dtype=np.float64)
            other = np.zeros(native_n, dtype=np.float64)
            if spec["species"] == "rain":
                rain, snow, species_code = source_path.tolist(), other.tolist(), 1
            else:
                rain, snow, species_code = other.tolist(), source_path.tolist(), 2
            text = validator.encode(phase, 1, native_n, species_code, 1.0,
                                    [rain], [snow], [cf.tolist()], engine_n)
            sidecar = HERE / f"{spec['sidecar_prefix']}-{phase.lower()}.sidecar"
            sidecar.write_text(text)
            validation = validator.validate_against_raw(
                text, raw_path, spec["species"], engine_n, input_path)
            assert validation["omitted_path_sum_g_m2"] == sum(float(v) for v in source_path.tolist())
            assert validation["positive_native_layers"] == int(np.count_nonzero(source_path > 0))

            drymass = np.asarray(raw_data["DRY_LAYER_MASS_KG_M2"], dtype=np.float64)
            normalized = source_path / (drymass * 1000.0)
            source_q = np.asarray(raw_data[spec["q_key"]], dtype=np.float64)
            active_cf0 = (cf == 0.0) & (source_path > 0.0)
            assert np.all(source_path[~active_cf0] == 0.0)
            if np.any(active_cf0):
                assert np.all(np.isfinite(normalized[active_cf0]))
                assert np.all(np.isfinite(source_q[active_cf0]))
            normalized_info = {
                "native_path_kg_kg_by_dry_layer_mass": normalized.tolist(),
                "source_q_kg_kg": source_q.tolist(),
                "active_CF0_max_abs_path_normalization_minus_source_q_kg_kg":
                    float(np.max(np.abs(normalized[active_cf0] - source_q[active_cf0])))
                    if np.any(active_cf0) else 0.0,
                "formula": "path_g_m2 / (DRY_LAYER_MASS_KG_M2 * 1000); derived check only, sidecar remains PATH_UNITS_G_M2",
            }
            radii = {}
            if spec["species"] == "snow":
                radii = {
                    "HAS_REQS": raw_data["HAS_REQS"],
                    "positive_CF0_native_k_1based": [int(k + 1) for k in np.where(active_cf0)[0]],
                    "SOURCE_RE_SNOW_m_by_native_k": [float(v) for v in raw_data["SOURCE_RE_SNOW"]],
                    "RES_um_by_native_k": [float(v) for v in raw_data["RES"]],
                    "FALLBACK_RES_um_by_native_k": [float(v) for v in raw_data["FALLBACK_RES"]],
                    "radius_used_by_sidecar": False,
                }
            else:
                radii = {
                    "HAS_REQC": raw_data.get("HAS_REQC"),
                    "SOURCE_RE_CLOUD_m_by_native_k": [float(v) for v in raw_data.get("SOURCE_RE_CLOUD", [])],
                    "REL_um_by_native_k": [float(v) for v in raw_data.get("REL", [])],
                    "radius_used_by_sidecar": False,
                }

            path_pin = pin(sidecar)
            sidecar_paths.append(path_pin)
            row = {
                "anchor": spec["anchor"], "phase": phase, "species": spec["species"],
                "occurrence": 1.0, "sidecar": path_pin,
                "raw_capture": pin(raw_path), "replay_input": pin(input_path),
                "saved_adapter_result_context": pin(result_path),
                "capture_format": format_id, "coordinate_domain_1_ij": [i, j],
                "input_engine_levels": engine_n, "raw_native_levels": native_n,
                "solver_level_map": {
                    "sidecar_stores_native_prefix_only": True,
                    "native_to_solver_levels": f"native k=1..{native_n} maps directly to solver levels 1..{native_n}",
                    "remaining_solver_levels": engine_n-native_n,
                    "remaining_solver_path_values": "reader pads with zeros; no padding values are serialized in sidecar",
                },
                "grid_path": {
                    "unit": "g m-2", "raw_record": spec["key"],
                    "values_exactly_copied_without_threshold": True,
                    "positive_native_layers": validation["positive_native_layers"],
                    "sum_g_m2": validation["omitted_path_sum_g_m2"],
                    "values_by_native_k": source_path.tolist(),
                },
                "normalized_path_check": normalized_info,
                "recorded_radii": radii,
                "validator_result": validation,
                "cu_population_policy": cu_policy,
                "seed": seed, "overlap": overlap, "microphysics_ice_size_flag": iceflag,
            }
            sidecar_rows.append(row)
            rootbase = ROOT / "build/udm37-cf0-material-anchor-inputs-v1"
            common = {"anchor": spec["anchor"], "phase": phase,
                      "capture_format": format_id, "input_pin": pin(input_path),
                      "raw_pin": pin(raw_path), "result_context_pin": pin(result_path),
                      "CU_POPULATION_POLICY": cu_policy, "seed": seed, "overlap": overlap}
            planned.extend([
                {**common, "call_id": f"{spec['anchor']}-{phase.lower()}-baseline",
                 "call_role": "unchanged captured baseline", "sidecar": None,
                 "expected_runtime_argument": "omit sidecar argument"},
                {**common, "call_id": f"{spec['anchor']}-{phase.lower()}-{spec['species']}-increment",
                 "call_role": "experimental occurrence-one single-species increment",
                 "sidecar": path_pin, "expected_runtime_argument": str(sidecar.relative_to(ROOT))},
            ])

    # Keep a full, hash-verified copy of the previous exact baseline closure in the roster.
    inherited = []
    for entry in inherited_assets:
        path = Path(entry["path"])
        if not path.is_absolute():
            path = ROOT / path
        inherited.append(pin(path))
    roster = {
        "schema": "udm37-cf0-material-anchor-input-roster-v1",
        "status": "PREPARED_NO_SOLVER_OR_BUILD",
        "scope": "Four exact CF0 sidecars and an eight-call baseline/increment roster; execution is not authorized by this preparation.",
        "inventory_receipt": pin(INVENTORY),
        "baseline_receipt": pin(BASELINE_EXECUTION),
        "validator": pin(VALIDATOR),
        "preparation_script": pin(Path(__file__)),
        "calls_planned": 8,
        "solver_calls_performed": 0,
        "new_builds": 0,
        "new_forecasts": 0,
        "counterfactual_contract": {
            "sidecar_occurrence": "exactly one, per existing validator contract",
            "sidecar_path_units": "PATH_UNITS_G_M2",
            "species_paths": "selected native omitted raw path only; other species zero",
            "CF_rule": "positive paths only at raw CF==0; exact raw CF/RWP_OMITTED/SWP_OMITTED values, no cutoffs",
            "production_policy": "experimental diagnostic input only; does not alter WRF defaults or production precipitation policy",
            "radius_policy": "all input radii remain captured values; sidecar optics helper receives recorded snow RES where relevant; no synthetic size added",
        },
        "sidecars": sidecar_rows,
        "planned_calls": planned,
        "inherited_historical_baseline_asset_closure": {
            "receipt_status": baseline_receipt["status"],
            "asset_count": len(inherited),
            "pins": inherited,
            "role_note": "These pins reproduce the prior unmodified baseline environment only. The former reference executable is not identified as the future sidecar-capable target; that target remains to be built/reviewed separately.",
        },
        "captured_input_raw_result_pins": inventory_pins,
        "limitations": [
            "The baseline-plus-increment roster is a proposed paired replay, not a completed result.",
            "An occurrence-one sidecar is experimental and not a production occurrence policy.",
            "Single-column replay does not estimate domain or forecast impact.",
            "No executable/build approval is included in this preparation.",
        ],
    }
    (HERE / "roster.json").write_text(json.dumps(roster, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": roster["status"], "sidecars": len(sidecar_rows),
                      "planned_calls": len(planned), "roster": pin(HERE / "roster.json")}, sort_keys=True))


if __name__ == "__main__":
    main()
