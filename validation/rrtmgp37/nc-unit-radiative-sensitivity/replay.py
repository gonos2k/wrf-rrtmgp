#!/usr/bin/env python3
"""Six fresh held-state RTE arms; never launch WRF or modify production sources."""
import argparse
import gzip
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]
sys.path.insert(0, str(REPO / "WRF/test/rrtmgp"))
from compare_column_replay import read_result
from test_column_replay import read_input
from test_udm_radius_stage import parse_packet

ARMS = ("A_native", "B_volume", "C_mass")
SUFFIX = ("SW_DIRECT_PREDELTA_POLICY", "TOA_GPOINT", "RAW_GAS_TAU", "MCICA_MASK",
          "RAW_CLOUD_TAU", "RAW_PRECIP_TAU", "RAW_GRAUPEL_TAU_EXT", "RAW_HAIL_TAU_EXT",
          "BAND_LIMS_GPOINT", "BAND_LIMS_WAVENUMBER", "VISIBLE_WEIGHT")
PREDELTA = {"DIRECT_PREDELTA", "DIRECTC_PREDELTA", "VISDIR_PREDELTA", "NIRDIR_PREDELTA"}
HELD = {"MASK", "GAS_COL_DRY", "GAS_TAU", "GAS_TAU_RAW", "GAS_SSA", "GAS_G", "VMR_N2",
        "PRECIP_TAU", "PRECIP_SSA", "PRECIP_G", "DI_USED", "DS_USED", "UPC", "DNC", "HRC", "DIRECTC"}


def require(condition, message):
    if not condition:
        raise ValueError(message)


def pin(path):
    data = path.read_bytes()
    return {"path": str(path.resolve()), "size_bytes": len(data),
            "sha256": hashlib.sha256(data).hexdigest()}


def blocks(path):
    lines = path.read_bytes().splitlines(keepends=True)
    pos = 2
    result = []
    while pos < len(lines):
        start = pos
        tokens = lines[pos].split()
        require(len(tokens) in (3, 4), "invalid record header")
        name = tokens[0].decode("ascii")
        shape = tuple(int(x) for x in tokens[1:])
        require(min(shape) > 0, "invalid shape")
        count = math.prod(shape)
        pos += 1
        found = 0
        while found < count and pos < len(lines):
            found += len(lines[pos].split())
            pos += 1
        require(found == count, "short or oversize record")
        result.append((name, shape, b"".join(lines[start:pos])))
    require(len(result) == len({row[0] for row in result}), "duplicate record")
    return lines[:2], result


def project_sw(source, dest):
    header, rows = blocks(source)
    require(header[0].strip() == b"RRTMGP_REPLAY_V9", "only this V9 projection is supported")
    require(tuple(row[0] for row in rows[-11:]) == SUFFIX, "unexpected SW oracle suffix")
    physical = rows[:-11]
    require(len(physical) == 33 and physical[-1][0] == "MOL_WEIGHT_DRY", "physical prefix")
    require(not {"FROZEN_MODE", "CU_POPULATION_POLICY"}.intersection(row[0] for row in physical),
            "CU/frozen projection is unsupported")
    header[0] = b"RRTMGP_REPLAY_V6\n"
    dest.write_bytes(b"".join(header) + b"".join(row[2] for row in physical))
    _, projected = blocks(dest)
    require(physical == projected, "projection changed physical bytes")


def replace_rel(source, dest, radii, active):
    header, rows = blocks(source)
    _, _, nl, _, _, _, records = read_input(source)
    rel = records["REL"].copy()
    require(rel.shape == (1, nl) and len(radii) <= nl, "REL shape")
    indexes = np.flatnonzero(active)
    rel[0, indexes] = radii[indexes]
    changed = []
    for name, shape, raw in rows:
        if name != "REL":
            changed.append(raw)
            continue
        lines = raw.splitlines(keepends=True)
        require(len(lines) == nl + 1 and shape == (1, nl), "REL line layout")
        for k in indexes:
            value = float(rel[0, k])
            old = float(lines[k + 1].replace(b"D", b"E"))
            if value != old:
                lines[k + 1] = f"  {value: .16E}\n".encode("ascii")
        changed.append(b"".join(lines))
    dest.write_bytes(b"".join(header) + b"".join(changed))
    new_header, new_rows = blocks(dest)
    require(header == new_header, "variant changed header")
    require([row for row in rows if row[0] != "REL"] ==
            [row for row in new_rows if row[0] != "REL"], "variant changed non-REL bytes")
    _, _, _, _, _, _, new_records = read_input(dest)
    require(np.array_equal(new_records["REL"], rel), "REL encoding mismatch")
    inactive = np.ones(nl, dtype=bool)
    inactive[indexes] = False
    require(np.array_equal(rel[:, inactive], records["REL"][:, inactive]), "inactive REL changed")


def load_saved(compressed, output_dir):
    target = output_dir / (compressed.name.removesuffix(".gz"))
    require(not target.exists(), "saved-result extraction would overwrite a file")
    target.write_bytes(gzip.decompress(compressed.read_bytes()))
    return read_result(target)


def numeric_match(actual, saved, omitted=frozenset(), exact=False):
    a, b = actual["sections"], saved["sections"]
    require(set(a) == set(b) - set(omitted), "saved result section roster")
    require((actual["phase"], actual["nc"], actual["nl"]) ==
            (saved["phase"], saved["nc"], saved["nl"]), "saved result dimensions")
    for name, values in a.items():
        require(values.shape == b[name].shape, f"saved {name} shape")
        require(np.isfinite(values).all(), f"nonfinite {name}")
        same = np.array_equal(values, b[name]) if name == "MASK" or exact else np.allclose(
            values, b[name], rtol=1e-12, atol=1e-10, equal_nan=False)
        require(same, f"fresh vs saved numerical mismatch in {name}")


def delta_metrics(variant, control, native_n):
    a, b = variant["sections"], control["sections"]
    hr = a["HR"][0, :, 0] - b["HR"][0, :, 0]
    result = {
        "surface_down_W_m2": float(a["DN"][0, 0, 0] - b["DN"][0, 0, 0]),
        "TOA_up_W_m2": float(a["UP"][0, -1, 0] - b["UP"][0, -1, 0]),
        "surface_net_down_W_m2": float((a["DN"] - a["UP"])[0, 0, 0] -
                                        (b["DN"] - b["UP"])[0, 0, 0]),
        "max_abs_native_heating_K_day": float(np.abs(hr[:native_n]).max()),
        "max_abs_full_heating_K_day": float(np.abs(hr).max()),
        "heating_profile_K_day": hr.tolist(),
    }
    for name in ("DIRECT", "DIFFUSE"):
        if name in a:
            result[name.lower() + "_surface_W_m2"] = float(a[name][0, 0, 0] - b[name][0, 0, 0])
    return result


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--capture-dir", type=Path, required=True)
    ap.add_argument("--reference-exe", type=Path, required=True)
    ap.add_argument("--data-dir", type=Path, required=True)
    ap.add_argument("--expected-result-dir", type=Path)
    ap.add_argument("--baseline-mode", choices=("exact", "numeric"), default="exact",
                    help="numeric is an explicitly labeled cross-toolchain stored-baseline comparison")
    ap.add_argument("--output-dir", type=Path, required=True)
    args = ap.parse_args()
    for name in ("capture_dir", "reference_exe", "data_dir", "output_dir", "expected_result_dir"):
        if getattr(args, name) is not None:
            setattr(args, name, getattr(args, name).resolve())
    args.output_dir.mkdir(parents=True, exist_ok=False)
    saved_dir = args.output_dir / "saved"
    saved_dir.mkdir()
    producer = parse_packet(args.capture_dir / "udm_radius_d1_i1_j1_step1.raw")
    qc, nc, rho = (np.array(producer.fields[name]) for name in ("SOURCE_QC", "SOURCE_QNC", "SOURCE_RHO"))
    native_n = len(qc)
    require(native_n == 59, "native layer count")
    active = (qc * rho > 1e-12) & (nc * rho > 1e-6) & (nc > 0) & (rho > 0)
    require(int(active.sum()) == 33, "active layer count")
    water = producer.fields["RHO_WATER"][0]
    require(water == 1000, "water density")
    radii = {}
    for arm, factor in (("B_volume", rho), ("C_mass", np.ones_like(rho))):
        values = np.array(producer.fields["SOURCE_RE_CLOUD"]) * 1e6
        values[active] = np.cbrt(3 * qc[active] * factor[active] /
                                (4 * math.pi * water * nc[active])) * 1e6
        require(np.all((values[active] >= 2.51) & (values[active] <= 50)), "native radius bound")
        require(np.all((values[active] >= 2.5) & (values[active] <= 21.5)), "liquid LUT clipping")
        radii[arm] = values
    pin_paths = [args.reference_exe, args.capture_dir / "udm_radius_d1_i1_j1_step1.raw"]
    pin_paths += [args.capture_dir / (phase + ".input") for phase in ("lw", "sw")]
    pin_paths += sorted(args.data_dir.glob("rrtmgp-*.nc"))
    pins_before = [pin(p) for p in pin_paths]
    report = {"schema": "UDM_NC_CONDITIONAL_FRESH_REPLAY_V1", "status": "RUNNING",
              "RTE_attempts": [], "native_layers": native_n, "active_liquid_layers": int(active.sum()),
              "builds_launched": 0, "WRF_forecasts_launched": 0, "pins_before": pins_before, "deltas": {},
              "baseline_mode": args.baseline_mode}
    env = {key: value for key, value in os.environ.items() if not key.startswith("WRF_RRTMGP")}
    env.update(OMP_NUM_THREADS="1", OMP_DYNAMIC="FALSE")
    results = {}
    try:
        for phase in ("lw", "sw"):
            original = args.capture_dir / (phase + ".input")
            base = args.output_dir / (phase + "_A_native.input")
            if phase == "sw":
                project_sw(original, base)
            else:
                base.write_bytes(original.read_bytes())
            _, _, _, _, _, _, base_records = read_input(base)
            require(base_records["PLEV"][0, 0] > base_records["PLEV"][0, -1], "surface ordering")
            results[phase] = {}
            for arm in ARMS:
                inp = base if arm == "A_native" else args.output_dir / f"{phase}_{arm}.input"
                if arm != "A_native":
                    replace_rel(base, inp, radii[arm], active)
                out = args.output_dir / f"{phase}_{arm}.result"
                log = args.output_dir / f"{phase}_{arm}.log"
                attempt = {"phase": phase, "arm": arm, "input": pin(inp), "returncode": None}
                report["RTE_attempts"].append(attempt)
                (args.output_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n")
                with log.open("wb") as stream:
                    proc = subprocess.run([str(args.reference_exe), str(args.data_dir), str(inp), str(out)],
                                          env=env, stdout=stream, stderr=subprocess.STDOUT, timeout=120)
                attempt["returncode"] = proc.returncode
                (args.output_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n")
                attempt["log"] = pin(log)
                require(proc.returncode == 0 and out.is_file(), f"{phase}/{arm} solver failed")
                attempt["output"] = pin(out)
                result = read_result(out)
                results[phase][arm] = result
                if arm == "A_native":
                    saved = load_saved(args.capture_dir / f"{phase}.reference.result.gz", saved_dir)
                    numeric_match(result, saved, PREDELTA if phase == "sw" else frozenset(),
                                  exact=args.baseline_mode == "exact")
                    attempt["baseline_saved_" + args.baseline_mode + "_match"] = True
                else:
                    baseline = results[phase]["A_native"]["sections"]
                    fields = HELD.intersection(baseline)
                    require(fields.issubset(result["sections"]), "missing held field")
                    for name in fields:
                        require(np.array_equal(result["sections"][name], baseline[name]), f"held {name} changed")
                    attempt["exact_held_sections"] = sorted(fields)
                _, _, _, _, _, _, arm_records = read_input(inp)
                require(result["sections"]["RL_USED"].shape == (1, result["nl"], 1), "RL_USED shape")
                require(np.array_equal(result["sections"]["RL_USED"][:, :, 0], arm_records["REL"]),
                        "liquid radius clipped or altered")
                if args.expected_result_dir:
                    expected = load_saved(args.expected_result_dir / f"{phase}_{arm}.result.gz", saved_dir)
                    numeric_match(result, expected)
                    attempt["saved_arm_numeric_match"] = True
            report["deltas"][phase] = {"B_minus_A": delta_metrics(results[phase]["B_volume"], results[phase]["A_native"], native_n),
                                       "C_minus_B": delta_metrics(results[phase]["C_mass"], results[phase]["B_volume"], native_n)}
        require(len(report["RTE_attempts"]) == 6, "attempt count")
        report["pins_after"] = [pin(p) for p in pin_paths]
        require(report["pins_after"] == pins_before, "immutable input changed")
        report["status"] = "PASS_SCOPED_CONDITIONAL_RADIATIVE_SENSITIVITY"
    except Exception as exc:
        report.update(status="FAIL_PRESERVED", failure=repr(exc))
        raise
    finally:
        (args.output_dir / "result.json").write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps({"status": report["status"], "RTE_attempts": len(report["RTE_attempts"]),
                      "WRF_forecasts": 0, "result": str(args.output_dir / "result.json")}))


if __name__ == "__main__":
    main()
