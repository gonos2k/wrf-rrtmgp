#!/usr/bin/env python3
"""Hold captured gas/state/mask/RTE fixed and replace only prepared ice optics.

This restricted ice-only experiment diagnoses model differences. It is not an
accuracy test or an exact reproduction of RRTMG's gas grid and two-stream RTE.
"""
from __future__ import annotations

import argparse
import csv
import json
import subprocess
from pathlib import Path

import numpy as np

from compare_column_replay import read_result
from test_column_replay import read_input
from test_udm_cf_replay import metric_values


def run(command: list[str], logfile: Path) -> None:
    proc = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
    logfile.write_text(proc.stdout)
    if proc.returncode:
        raise RuntimeError(f"command failed ({proc.returncode}), inspect {logfile}: {command}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data-dir", type=Path, required=True)
    parser.add_argument("--reference-executable", type=Path, required=True)
    parser.add_argument("--bridge-executable", type=Path, required=True)
    parser.add_argument("--captures", type=Path, nargs="+", required=True)
    parser.add_argument("--audit-csv", type=Path)
    parser.add_argument("--output-dir", type=Path, required=True)
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    audit = []
    if args.audit_csv:
        with args.audit_csv.open() as f:
            audit = list(csv.DictReader(f))
    reports = []
    for source in args.captures:
        source = source.resolve()
        phase, nc, nl, _, _, _, records = read_input(source)
        if phase != "SW" or nc != 1:
            raise RuntimeError("experiment requires one SW column")
        if any(np.any(records.get(name, 0) != 0) for name in ("LWP", "SWP", "RWP")):
            raise RuntimeError("ice-only attribution rejects liquid and precipitation paths")
        active = records["IWP"] > 0
        if np.any(records["CF"][active] != 1):
            raise RuntimeError("initial optical attribution requires overcast ice (no McICA variance)")
        case_dir = output / source.stem
        case_dir.mkdir(exist_ok=True)
        baseline_path = case_dir / "baseline.result"
        reference = [str(args.reference_executable.resolve()), str(args.data_dir.resolve()), str(source)]
        run(reference + [str(baseline_path), "1"], case_dir / "baseline.log")
        baseline = read_result(baseline_path)
        base_metrics = metric_values(baseline)
        variants = {}
        for mode in ("native_wrapper", "native_physical_fu", "generic_rrtmg"):
            # Native wrapper uses UDM re_ice numerically as Fu generalized size;
            # matched physical Fu converts r_ec to d_ge=1.0315*r_ec. Generic
            # follows actual WRF reicalc(T) and the default iceflag3 conversion.
            ri = records["REI"][0].copy()
            if mode == "native_physical_fu":
                ri *= 1.0315
            rows = np.column_stack([
                records["LWP"][0], records["IWP"][0], records["SWP"][0],
                np.clip(records["REL"][0], 1.5, 60), np.clip(ri, 5, 140),
                np.clip(records["RES"][0], 5, 130), records["TLAY"][0]])
            bridge_input = case_dir / f"{mode}.input"
            optics = case_dir / f"{mode}.optics"
            result_path = case_dir / f"{mode}.result"
            with bridge_input.open("w") as f:
                f.write(f"WRF_RRTMG_SW_CLOUD_INPUT_V1\n{nl} 3 {int(mode == 'generic_rrtmg')}\n")
                np.savetxt(f, rows, fmt="%.16e")
            run([str(args.bridge_executable.resolve()), str(bridge_input), str(optics)],
                case_dir / f"{mode}-bridge.log")
            run(reference + [str(result_path), "1", str(optics)], case_dir / f"{mode}-reference.log")
            result = read_result(result_path)
            invariants = {}
            for name in ("GAS_TAU", "GAS_SSA", "GAS_G", "MASK", "UPC", "DNC", "HRC", "DIRECTC"):
                delta = float(np.max(np.abs(baseline["sections"][name] - result["sections"][name])))
                invariants[name] = delta
                if delta != 0:
                    raise RuntimeError(f"optics-only experiment changed {name}: {delta}")
            metrics = metric_values(result)
            variants[mode] = {"metrics": metrics,
                              "delta_from_rrtmgp": {name: metrics[name] - base_metrics[name] for name in metrics},
                              "held_fixed_max_difference": invariants}
        call = int(source.stem.rsplit("_", 1)[1])
        actual = [row for row in audit if row["phase"] == "sw" and int(row["step"]) == call
                  and int(row["i"]) == 1 and int(row["j"]) == 1 and row["metric"] == "SURFACE_DOWN"]
        actual_values = [{key: float(row[key]) for key in ("value37", "value4", "mean37", "mean4", "sd_delta")}
                         | {"radius_mode": int(row["radius_mode"])} for row in actual]
        reports.append({"capture": str(source), "baseline": base_metrics,
                        "variants": variants, "same_state_wrf_comparison": actual_values})
    report = {"scope": "overcast ice-only cloud-optics swap; gas/mask/clear-sky/RTE held fixed",
              "spectral_caveat": "RRTMG 2600 and pinned RRTMGP 2680 cm-1 shared edge differ; approximate ordered-band correspondence",
              "accuracy_claim": False, "captures": reports}
    (output / "summary.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
