#!/usr/bin/env python3
"""Build state/phase-specific experiment sidecars from pinned captured raw inputs."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[3]
HERE = Path(__file__).resolve().parent
MANIFEST = HERE.parent / "candidate-manifest-v2.json"
MODES = ("cf0_uniform", "grid_uniform", "ice160", "ice140")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def parse_sections(path: Path, magic: str):
    lines = path.read_text(encoding="ascii").splitlines()
    if not lines or lines[0] != magic:
        raise ValueError(f"{path}: expected {magic}")
    header = lines[1].split()
    p = 2
    records = {}
    while p < len(lines):
        h = lines[p].split()
        p += 1
        if len(h) < 2:
            raise ValueError(f"{path}: malformed record header")
        name, dims = h[0], tuple(int(x) for x in h[1:])
        n = int(np.prod(dims))
        vals = []
        while len(vals) < n:
            if p >= len(lines):
                raise ValueError(f"{path}: truncated {name}")
            vals.extend(float(x.replace("D", "E").replace("d", "e")) for x in lines[p].split())
            p += 1
        if len(vals) != n or name in records:
            raise ValueError(f"{path}: malformed/duplicate {name}")
        a = np.asarray(vals, dtype=np.float64).reshape(dims, order="F")
        if not np.isfinite(a).all():
            raise ValueError(f"{path}: nonfinite {name}")
        records[name] = a
    return header, records


def write_array(f, name, values):
    a = np.asarray(values, dtype=np.float32).reshape(-1)
    f.write(f"{name} 1 {a.size}\n")
    for value in a:
        f.write(f" {float(value):.9E}\n")


def prepare(out_dir: Path):
    m = json.loads(MANIFEST.read_text())
    if m.get("status") != "PRODUCTION_CAPTURE_SET_VALIDATED_SEED_EXECUTABLE_ANCHORS_PENDING":
        raise ValueError("unexpected capture manifest state")
    if out_dir.exists() and any(out_dir.iterdir()):
        raise ValueError(f"sidecar output directory must be fresh: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=False)
    report = {"schema": "UDM_STRATIFIED_MATRIX_SIDECARS_V1", "status": "PASS_PREPARATION_ONLY",
              "manifest_sha256": sha(MANIFEST), "cases": [], "sidecars": {}}
    arm_count = 0
    for case in m["cases"]:
        item = {"alias": case["alias"], "coordinate": case["coordinate"], "phases": {}}
        case_modes = set()
        for phase in ("LW", "SW"):
            suff = phase.lower()
            raw_path = ROOT / case["files"][f"{suff}_raw"]["path"]
            inp_path = ROOT / case["files"][f"{suff}_input"]["path"]
            prod_path = ROOT / case["files"][f"{suff}_production_result"]["path"]
            ref_path = ROOT / case["files"][f"{suff}_reference_result"]["path"]
            raw_header, raw = parse_sections(raw_path, "RRTMGP_RAW_V1")
            in_lines = inp_path.read_text(encoding="ascii").splitlines()
            expected_magic = "RRTMGP_REPLAY_V8" if phase == "LW" else "RRTMGP_REPLAY_V9"
            if in_lines[0] != expected_magic:
                raise ValueError(f"{case['alias']}/{phase}: wrong input magic")
            input_header, inp = parse_sections(inp_path, expected_magic)
            if (raw_header[0], int(raw_header[1]), int(raw_header[2])) != (
                phase, case["coordinate"]["i"], case["coordinate"]["j"]
            ):
                raise ValueError(f"{case['alias']}/{phase}: raw coordinate mismatch")
            input_phase = input_header[0]
            nc, nl, overlap, recorded_seed, iceflag = map(int, input_header[1:6])
            if input_phase != phase or nc != 1 or nl != (47 if phase == "LW" else 40) or iceflag != 4:
                raise ValueError(f"{case['alias']}/{phase}: unexpected replay dimensions/ice size flag")
            n_native = int(raw_header[3])
            if n_native != 39 or raw["CF"].size != n_native:
                raise ValueError(f"{case['alias']}/{phase}: native layer count mismatch")
            cf = raw["CF"].reshape(-1)
            if not np.array_equal(inp["CF"].reshape(-1)[:n_native].astype(np.float32), cf.astype(np.float32)):
                raise ValueError(f"{case['alias']}/{phase}: CF differs from raw capture")
            rwp = raw["RWP_GRID"].reshape(-1).astype(np.float32)
            swp = raw["SWP_GRID"].reshape(-1).astype(np.float32)
            qi = raw["QI"].reshape(-1)
            iwp_grid = raw["IWP_GRID"].reshape(-1)
            iwp_adapter = inp["IWP"].reshape(-1)[:n_native]
            re_adapter = inp["REI"].reshape(-1)[:n_native]
            preclip_diameter_um = np.asarray(2.0 * re_adapter.astype(np.float64), dtype=np.float32).astype(np.float64)
            mask_native = ((cf > 0.0) & (iwp_adapter > 0.0) & (qi > 0.0) &
                           (iwp_grid > 0.0) & (preclip_diameter_um > 180.0))
            reference_mask = (iwp_adapter > 0.0) & (preclip_diameter_um > 180.0)
            if not np.array_equal(mask_native, reference_mask):
                raise ValueError(f"{case['alias']}/{phase}: reference ICE mode would change a layer excluded by native eligibility")
            profile = case["phases"][phase]["actual_profile"]
            profile_mask = np.asarray(profile["ice160_140_eligibility_mask_cf_positive_iwp_positive_preclip_gt180"], dtype=bool)
            if profile_mask.size != n_native or not np.array_equal(profile_mask, mask_native):
                raise ValueError(f"{case['alias']}/{phase}: native raw eligibility differs from validated manifest")
            total_precip = float(np.sum(rwp.astype(np.float64) + swp.astype(np.float64)))
            cf0_precip = float(np.sum((rwp.astype(np.float64) + swp.astype(np.float64))[cf == 0.0]))
            eligible = []
            if cf0_precip > 0.0:
                eligible.append("cf0_uniform")
            if total_precip > 0.0:
                eligible.append("grid_uniform")
            if np.any(mask_native):
                eligible.extend(("ice160", "ice140"))
            # The original capture analyzer's eligible-mode declaration must match these independent raw/input gates.
            declared = profile.get("eligible_seed_variants")
            if declared is not None and declared != eligible:
                raise ValueError(f"{case['alias']}/{phase}: declared variants {declared} differ from {eligible}")
            case_modes.update(eligible)
            padded_rwp = np.zeros(nl, dtype=np.float32)
            padded_swp = np.zeros(nl, dtype=np.float32)
            padded_rwp[:n_native] = rwp
            padded_swp[:n_native] = swp
            padded_mask = np.zeros(nl, dtype=np.float32)
            padded_mask[:n_native] = mask_native.astype(np.float32)
            arm_count += len(eligible)
            item["phases"][phase] = {
                "input": str(inp_path.relative_to(ROOT)), "input_sha256": sha(inp_path),
                "raw": str(raw_path.relative_to(ROOT)), "raw_sha256": sha(raw_path),
                "production_result": str(prod_path.relative_to(ROOT)), "production_result_sha256": sha(prod_path),
                "ordinary_reference_result": str(ref_path.relative_to(ROOT)), "ordinary_reference_result_sha256": sha(ref_path),
                "header": {"magic": expected_magic, "nc": nc, "nl": nl, "overlap": overlap,
                           "recorded_seed": recorded_seed, "microphysics_ice_size_flag": iceflag},
                "cf0_precip_path_g_m2": cf0_precip, "total_precip_path_g_m2": total_precip,
                "cf_zero_precip_layers_1based": (np.where((cf == 0.0) & ((rwp.astype(np.float64) + swp.astype(np.float64)) > 0.0))[0] + 1).tolist(),
                "ice_preclip_eligible_layers_1based": (np.where(mask_native)[0] + 1).tolist(),
                "reference_changed_mask_matches_native_gate": True,
                "preclip_diameter_um_native": preclip_diameter_um.tolist(),
                "eligible_modes": eligible, "sidecars": {}
            }
            for mode in eligible:
                sidecar_dir = out_dir / case["alias"] / phase.lower()
                sidecar_dir.mkdir(parents=True, exist_ok=True)
                dest = sidecar_dir / f"{mode}.sidecar"
                if dest.exists():
                    raise ValueError(f"refusing overwrite {dest}")
                mode_tag = mode.upper()
                with dest.open("x", encoding="ascii", newline="\n") as f:
                    f.write(f"UDM_SENSITIVITY_V1 {mode_tag} {case['coordinate']['i']} {case['coordinate']['j']}\n")
                    write_array(f, "RWP_GRID", padded_rwp)
                    write_array(f, "SWP_GRID", padded_swp)
                    if mode in ("ice160", "ice140"):
                        write_array(f, "ICE_EXPECTED_MASK", padded_mask)
                sideinfo = {"path": str(dest.relative_to(ROOT)), "sha256": sha(dest), "bytes": dest.stat().st_size}
                item["phases"][phase]["sidecars"][mode] = sideinfo
                report["sidecars"][f"{case['alias']}/{phase}/{mode}"] = sideinfo
        report["cases"].append(item)
    report["eligible_phase_variant_arms"] = arm_count
    report["expected_arms_each_phase"] = 12
    per_phase = {phase: sum(len(c["phases"][phase]["eligible_modes"]) for c in report["cases"])
                 for phase in ("LW", "SW")}
    if arm_count != 24 or per_phase != {"LW": 12, "SW": 12}:
        raise ValueError(f"expected 12 eligible arms per phase / 24 total, got {per_phase}")
    report["eligible_arms_by_phase"] = per_phase
    report_path = out_dir / "preparation.json"
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    return report


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out-dir", type=Path, required=True)
    args = ap.parse_args()
    report = prepare(args.out_dir.resolve())
    print(json.dumps({"status": report["status"], "sidecars": len(report["sidecars"]),
                      "eligible_phase_variant_arms": report["eligible_phase_variant_arms"]}, indent=2))


if __name__ == "__main__":
    main()
