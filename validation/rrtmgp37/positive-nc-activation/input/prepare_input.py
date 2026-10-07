#!/usr/bin/env python3
"""Create one-element QVAPOR supersaturation intervention from frozen source data."""
from __future__ import annotations
import hashlib, json, math, shutil, struct
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[2]
WORK = ROOT / "build/udm37-activation-supersat-input-v1"
BASE = ROOT / "build/udm37-positive-nc-stage-runtime-2min-v2/stage/on/wrfinput_d01"
PACKET = ROOT / "build/udm37-positive-nc-stage-runtime-2min-v2/stage/on/number_capture/number_d1_tile1_i23_j2_step1_stage30_sub1.raw"
SOURCE_PATHS = {
    "module_mp_udm.F": ("build/udm37-positive-nc-stage-observer-source-v2/WRF/phys/module_mp_udm.F", "9f25a1aaebd0d29ba3ecdf86c9fe65065cf920fc187bdfd904e8b8192bc7e3c8", 208324),
    "module_microphysics_driver.F": ("build/udm37-positive-nc-stage-observer-source-v2/WRF/phys/module_microphysics_driver.F", "c2568eef1fe6223eab587c864ae104bbfaace5fde1266313ddc36ba89541d74d", 203985),
    "module_model_constants.F": ("build/udm37-positive-nc-stage-observer-source-v2/WRF/share/module_model_constants.F", "5b80377fecdc18a5f0ad38d3b6c15cfc86ad5d76701adbbbb08a08698d0f7062", 8280),
}
BASE_SHA = "849f340d8d74b8e252b40d41c2d660126ae7a7b755d2e2b9eb24e988c97efc03"
PACKET_SHA = "b7fdfb7c6130c0133ab13fd2740f272ec68bb98b5fd97eb0481cf50b94dd9454"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def f32(x: float) -> float:
    return struct.unpack("=f", struct.pack("=f", float(x)))[0]


def source_saturation_lookup(t: float, pressure: float) -> dict:
    # Reproduce module_mp_udm.F default-REAL constants, table construction,
    # linear interpolation, pressure cap, and mixing-ratio operation order.
    nx = 7501
    xmin, xmax = f32(180.0), f32(330.0)
    cliq, cvap, rv, ttp, psat, hvap = map(f32, (4190.0, 1870.0, 461.5, 273.16, 610.78, 2501000.0))
    dldt = f32(cvap - cliq)
    xa = f32(-dldt / rv)
    xb = f32(xa + f32(hvap / f32(rv * ttp)))
    xinc = f32(f32(xmax - xmin) / f32(nx - 1))
    c1 = f32(f32(1.0) - f32(xmin / xinc))
    c2 = f32(f32(1.0) / xinc)
    table = []
    for j in range(nx):
        x = f32(xmin + f32(f32(j) * xinc))
        tr = f32(ttp / x)
        pow_term = f32(math.pow(tr, xa))
        exp_arg = f32(xb * f32(f32(1.0) - tr))
        exp_term = f32(math.exp(exp_arg))
        table.append(f32(f32(psat * pow_term) * exp_term))
    t = f32(t)
    pressure = f32(pressure)
    xj = f32(c1 + f32(c2 * t))
    xj = min(max(xj, f32(1.0)), f32(nx))
    jx = min(int(xj), nx - 1)
    es = f32(table[jx - 1] + f32(f32(xj - f32(jx)) * f32(table[jx] - table[jx - 1])))
    es = min(es, f32(f32(0.99) * pressure))
    ep2 = f32(f32(287.0) / f32(461.6))
    qmin = f32(1.0e-15)
    qsat = f32(f32(ep2 * es) / f32(pressure - es))
    qsat = max(qsat, qmin)
    return {"svp_pa": es, "qsat_mixing_ratio": qsat, "ep2": ep2,
            "table_index_1based": jx, "table_fraction": f32(xj - f32(jx)),
            "default_real_bits": 32, "operation_order": "source-default-REAL table/formula/interpolation/ep2*es/(p-es)"}


def attr_value(v):
    x = v.getncattr(v.name) if False else None
    return x


def canonical_attr(x):
    if isinstance(x, np.ndarray): return {"dtype": str(x.dtype), "shape": list(x.shape), "values": x.tolist()}
    if isinstance(x, np.generic): return x.item()
    if isinstance(x, bytes): return {"bytes_hex": x.hex()}
    return x


def snapshot(path: Path) -> dict:
    info = {"dimensions": {}, "global_attrs": {}, "variables": {}}
    with Dataset(path, "r") as ds:
        for n, d in ds.dimensions.items(): info["dimensions"][n] = {"size": len(d), "isunlimited": d.isunlimited()}
        for a in ds.ncattrs(): info["global_attrs"][a] = canonical_attr(ds.getncattr(a))
        for n, v in ds.variables.items():
            info["variables"][n] = {
                "dims": list(v.dimensions), "shape": list(v.shape), "dtype": str(v.dtype),
                "attrs": {a: canonical_attr(v.getncattr(a)) for a in v.ncattrs()},
                "data_sha256": hashlib.sha256(np.ascontiguousarray(v[:]).tobytes()).hexdigest(),
            }
    return info


def main():
    derived_dir = WORK / "derived"
    derived = derived_dir / "wrfinput_d01"
    report_path = WORK / "input-diff.json"
    if derived_dir.exists() or derived.exists() or report_path.exists():
        raise SystemExit(f"refusing overwrite: {derived_dir} or {report_path}")
    if sha(BASE) != BASE_SHA or sha(PACKET) != PACKET_SHA:
        raise SystemExit("frozen input or stage-30 packet hash mismatch")
    for _, (rel, expected, size) in SOURCE_PATHS.items():
        p = ROOT / rel
        if p.stat().st_size != size or sha(p) != expected:
            raise SystemExit(f"source pin mismatch: {rel}")
    # Packet schema: UDM37NUM1, 12-integer identity, 3 clocks, then 44 rows.
    lines = PACKET.read_text(encoding="ascii").splitlines()
    if lines[0] != "UDM37NUM1": raise SystemExit("wrong number packet magic")
    header = [int(x) for x in lines[1].split()]
    if header != [1, 1, 30, 1, 1, 23, 2, 1, 44, 32, 17, 1]: raise SystemExit(f"unexpected packet header: {header}")
    rows = {}
    for line in lines[3:]:
        p = line.split()
        if not p: continue
        k = int(p[0]); vals = [float(x.replace("D", "E")) for x in p[1:]]
        if len(vals) != 14 or k in rows: raise SystemExit("malformed/duplicate packet row")
        rows[k] = vals
    if len(rows) != 44 or set(rows) != set(range(1, 45)): raise SystemExit("incomplete packet levels")
    native_k = 7
    t_call, p_call, qv_call = rows[native_k][0:3]
    sat = source_saturation_lookup(t_call, p_call)
    q_target = f32(sat["qsat_mixing_ratio"] * f32(1.003))
    delta = f32(q_target - f32(qv_call))
    if not (delta > 0 and math.isfinite(delta)): raise SystemExit(f"invalid QV offset {delta}")
    derived_dir.mkdir()
    shutil.copy2(BASE, derived)
    with Dataset(derived, "r+") as ds:
        v = ds.variables["QVAPOR"]
        if tuple(v.dimensions) != ("Time", "bottom_top", "south_north", "west_east") or v.dtype != np.dtype("float32"):
            raise SystemExit("unexpected QVAPOR dimensions/dtype")
        index = (0, native_k - 1, 2 - 1, 23 - 1)
        before = np.float32(v[index])
        after = np.float32(before + np.float32(delta))
        if not np.isfinite(after) or after <= 0: raise SystemExit("resulting QVAPOR is not finite positive")
        v[index] = after
    before_snap = snapshot(BASE)
    after_snap = snapshot(derived)
    if before_snap["dimensions"] != after_snap["dimensions"] or before_snap["global_attrs"] != after_snap["global_attrs"]:
        raise SystemExit("dimension/global attribute change")
    if set(before_snap["variables"]) != set(after_snap["variables"]): raise SystemExit("variable roster changed")
    changed = []
    for name in before_snap["variables"]:
        b, a = before_snap["variables"][name], after_snap["variables"][name]
        if (b["dims"], b["shape"], b["dtype"], b["attrs"]) != (a["dims"], a["shape"], a["dtype"], a["attrs"]):
            raise SystemExit(f"metadata changed for {name}")
        if b["data_sha256"] != a["data_sha256"]: changed.append(name)
    if changed != ["QVAPOR"]: raise SystemExit(f"expected only QVAPOR data to differ; changed={changed}")
    # Verify the exact changed element and that every other value is preserved.
    with Dataset(BASE) as bds, Dataset(derived) as ads:
        bv, av = bds.variables["QVAPOR"][:], ads.variables["QVAPOR"][:]
        diff = np.argwhere(bv != av)
        if diff.tolist() != [[0, native_k - 1, 2 - 1, 23 - 1]]: raise SystemExit(f"QVAPOR changed indices {diff.tolist()}")
        if float(bv[0, native_k-1, 1, 22]) != float(before) or float(av[0,native_k-1,1,22]) != float(after):
            raise SystemExit("target QVAPOR element mismatch")
    report = {
        "schema": "UDM_ACTIVATION_SINGLE_QV_INPUT_INTERVENTION_V1",
        "status": "PREPARED_INPUT_ONLY_NOT_RUNTIME_AUTHORIZATION",
        "new_model_runs": 0,
        "baseline_input": {"path": str(BASE.relative_to(ROOT)), "sha256": BASE_SHA, "size_bytes": BASE.stat().st_size},
        "derived_input": {"path": str(derived.relative_to(ROOT)), "sha256": sha(derived), "size_bytes": derived.stat().st_size},
        "source_stage30_packet": {"path": str(PACKET.relative_to(ROOT)), "sha256": PACKET_SHA, "size_bytes": PACKET.stat().st_size},
        "location_fortran_1based": {"i": 23, "j": 2, "native_k": native_k},
        "python_index_0based": [0, native_k-1, 2-1, 23-1],
        "baseline_stage30_state": {"T_K": t_call, "P_Pa": p_call, "QV_kg_kg": qv_call,
            "NCCN_m3": rows[native_k][5], "NC_m3": rows[native_k][6]},
        "source_lookup": sat,
        "target_rh": 1.003,
        "target_call_boundary_qv": q_target,
        "additive_qv_offset": delta,
        "baseline_input_qvapor": float(before),
        "derived_input_qvapor": float(after),
        "changed_variable_data_arrays": changed,
        "changed_element_count": int(diff.shape[0]),
        "unchanged_dimensions_global_attrs_variable_roster_variable_metadata": True,
        "full_variable_comparison": "Every variable was independently read from baseline and derived inputs; only QVAPOR data digest differs, and exact changed-index scan has one element.",
        "interpretation": "The offset is computed from a saved UDM call-boundary state, then applied to the initial input QVAPOR element. Upstream dynamics and microphysics may change the resulting call-boundary state; future runtime must recompute RH and NC_ACT from packets. This is a deliberate single-state perturbation, not a physical validation.",
    }
    report_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": report["status"], "input_sha256": report["derived_input"]["sha256"], "changed": changed, "changed_element_count": int(diff.shape[0]), "qv_delta": delta, "target_rh": 1.003}, sort_keys=True))

if __name__ == "__main__": main()
