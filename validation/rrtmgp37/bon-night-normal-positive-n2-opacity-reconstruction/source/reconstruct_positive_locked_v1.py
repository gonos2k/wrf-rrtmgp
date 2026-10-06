#!/usr/bin/env python3
"""Locked source-order point reconstruction draft for captured positive-N2 LW input.

The numerical function is deliberately not wired to the command line. Review
must approve this adaptation and a separate diagnostic plan before any call
constructs opacity. This draft never opens a saved result target.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import re

import numpy as np
from netCDF4 import Dataset, chartostring

SCHEMA = "udm37-normal-positive-n2-opacity-adaptation-v1"
INPUT_SECTIONS = {
    "h2o": "H2O", "co2": "CO2", "o3": "O3", "n2o": "N2O",
    "ch4": "CH4", "o2": "O2", "cfc11": "VMR_CFC11",
    "cfc12": "VMR_CFC12", "cfc22": "VMR_CFC22", "ccl4": "VMR_CCL4",
    "n2": "VMR_N2",
}
CALL_GAS_ORDER = ["h2o", "co2", "o3", "n2o", "ch4", "o2",
                  "cfc11", "cfc12", "cfc22", "ccl4", "n2"]


def file_sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def pinned_file(root: Path, rec: dict, name: str) -> Path:
    p = Path(rec["path"])
    if not p.is_absolute():
        p = root / p
    if p.is_symlink() or not p.is_file():
        raise ValueError(f"{name}: not a regular file: {p}")
    if p.stat().st_size != int(rec["size_bytes"]) or file_sha(p) != rec["sha256"]:
        raise ValueError(f"{name}: pinned bytes changed: {p}")
    return p


def read_packet(path: Path, phase: str) -> dict[str, np.ndarray]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 3 or lines[0].strip() != "RRTMGP_REPLAY_V13":
        raise ValueError(f"{path}: expected the pinned V13 packet")
    dims = lines[1].split()
    if len(dims) < 3 or dims[0] != phase or tuple(map(int, dims[1:3])) != (1, 45):
        raise ValueError(f"{path}: unexpected phase/shape")
    result: dict[str, np.ndarray] = {}
    i = 2
    while i < len(lines):
        if not lines[i].strip():
            i += 1
            continue
        fields = lines[i].split()
        if len(fields) < 2:
            raise ValueError(f"{path}:{i+1}: invalid section header")
        name, shape = fields[0], tuple(int(x) for x in fields[1:])
        if name in result or not shape or any(x <= 0 for x in shape):
            raise ValueError(f"{path}:{i+1}: duplicate/invalid section {name}")
        n, values = math.prod(shape), []
        i += 1
        while i < len(lines) and len(values) < n:
            if lines[i].strip():
                values.extend(float(x.replace("D", "E").replace("d", "e")) for x in lines[i].split())
            i += 1
        if len(values) != n:
            raise ValueError(f"{path}: truncated {name}")
        a = np.asarray(values, dtype=np.float64).reshape(shape, order="F")
        if not np.isfinite(a).all():
            raise ValueError(f"{path}: nonfinite {name}")
        result[name] = a
    return result


def _strings(a: np.ndarray) -> list[str]:
    return [str(x).strip().lower() for x in chartostring(a).reshape(-1)]


def read_table(path: Path) -> dict[str, np.ndarray | list[str]]:
    required = {
        "kmajor": ("temperature", "pressure_interp", "mixing_fraction", "gpt"),
        "kminor_lower": ("temperature", "mixing_fraction", "contributors_lower"),
        "kminor_upper": ("temperature", "mixing_fraction", "contributors_upper"),
        "key_species": ("bnd", "atmos_layer", "pair"),
        "vmr_ref": ("temperature", "absorber_ext", "atmos_layer"),
    }
    names = ["kmajor", "kminor_lower", "kminor_upper", "key_species", "vmr_ref",
             "gas_names", "gas_minor", "identifier_minor", "minor_gases_lower",
             "minor_gases_upper", "minor_limits_gpt_lower", "minor_limits_gpt_upper",
             "minor_scales_with_density_lower", "minor_scales_with_density_upper",
             "scaling_gas_lower", "scaling_gas_upper", "scale_by_complement_lower",
             "scale_by_complement_upper", "kminor_start_lower", "kminor_start_upper",
             "press_ref", "press_ref_trop", "temp_ref", "bnd_limits_gpt"]
    out: dict[str, np.ndarray | list[str]] = {}
    with Dataset(path, "r") as ds:
        for name, dims in required.items():
            if name not in ds.variables or tuple(ds[name].dimensions) != dims:
                raise ValueError(f"unexpected named dimensions for {name}")
        for name in names:
            if name not in ds.variables:
                raise ValueError(f"table lacks {name}")
            raw = ds[name][:]
            if np.ma.isMaskedArray(raw) and np.any(np.ma.getmaskarray(raw)):
                raise ValueError(f"masked table array {name}")
            a = np.asarray(raw)
            if a.dtype.kind == "f" and not np.isfinite(a).all():
                raise ValueError(f"nonfinite table variable {name}")
            if name in {"gas_names", "gas_minor", "identifier_minor", "minor_gases_lower",
                        "minor_gases_upper", "scaling_gas_lower", "scaling_gas_upper"}:
                out[name] = _strings(a)
            else:
                out[name] = a
    expected = {"kmajor": (14,60,9,128), "kminor_lower": (14,9,485),
                "kminor_upper": (14,9,308), "key_species": (16,2,2),
                "vmr_ref": (14,20,2), "bnd_limits_gpt": (16,2)}
    for name, shape in expected.items():
        if np.shape(out[name]) != shape:
            raise ValueError(f"unexpected {name} shape {np.shape(out[name])}")
    return out


def read_avogadro(path: Path) -> float:
    text = path.read_text(encoding="ascii")
    m = re.search(r"avogad\s*=\s*([0-9.]+(?:[Ee][+-]?\d+)?)_wp", text, re.I)
    if not m:
        raise ValueError("pinned source has no recognized avogad literal")
    return float(m.group(1))


def mapped_flavors(key_raw: np.ndarray, table_gases: list[str], available: list[str]):
    # Mirrors create_key_species_reduce, then create_flavor's band-major/atm-minor
    # insertion order and rewrite_key_species_pair((0,0)) -> (2,2).
    red = {gas: i + 1 for i, gas in enumerate(available)}
    key = np.zeros_like(key_raw, dtype=np.int64)
    for b, atm, q in np.ndindex(key_raw.shape):
        raw = int(key_raw[b, atm, q])
        if raw == 0:
            key[b, atm, q] = 0
        else:
            if raw < 1 or raw > len(table_gases):
                raise ValueError("key species table index out of bounds")
            gas = table_gases[raw - 1]
            if gas not in red:
                raise ValueError(f"missing required key species {gas}")
            key[b, atm, q] = red[gas]
    pairs = []
    for b in range(key.shape[0]):
        for atm in range(2):
            pair = tuple(int(x) for x in key[b, atm])
            if pair == (0, 0):
                pair = (2, 2)
                key[b, atm] = pair
            if pair not in pairs:
                pairs.append(pair)
    if any(x < 0 or x > len(available) for x in key.flat):
        raise ValueError("reduced key species index invalid")
    return key, pairs


def _interval_rows(v: dict, suffix: str, available: list[str]):
    gas_by_id = {}
    for ident, gas in zip(v["identifier_minor"], v["gas_minor"]):
        if ident in gas_by_id and gas_by_id[ident] != gas:
            raise ValueError("ambiguous minor identifier-to-gas mapping")
        gas_by_id[ident] = gas
    rows = []
    removed = 0
    for i, ident in enumerate(v[f"minor_gases_{suffix}"]):
        if ident not in gas_by_id:
            raise ValueError(f"unknown minor interval identifier {ident}")
        lo, hi = map(int, v[f"minor_limits_gpt_{suffix}"][i])
        width = hi - lo + 1
        if lo < 1 or hi > 128 or width < 1:
            raise ValueError("invalid minor interval bounds")
        gas = gas_by_id[ident]
        keep = gas in available
        start = int(v[f"kminor_start_{suffix}"][i])
        rows.append({"id": ident, "gas": gas, "lo": lo, "hi": hi, "width": width,
                     "raw_start": start, "packed_start": start - removed if keep else None,
                     "density": bool(v[f"minor_scales_with_density_{suffix}"][i]),
                     "scale_gas": v[f"scaling_gas_{suffix}"][i],
                     "complement": bool(v[f"scale_by_complement_{suffix}"][i]),
                     "keep": keep})
        if not keep:
            removed += width
    return rows


def _pack_minor(raw: np.ndarray, rows: list[dict]) -> np.ndarray:
    slices = []
    expected_start = 1
    for row in rows:
        if not row["keep"]:
            continue
        if row["packed_start"] != expected_start:
            raise ValueError("source packed-start offset does not match retained interval order")
        lo = row["raw_start"] - 1
        hi = lo + row["width"]
        slices.append(raw[:, :, lo:hi])
        expected_start += row["width"]
    return np.concatenate(slices, axis=2) if slices else raw[:, :, :0]


def reconstruct_point(plan: dict, root: Path) -> dict:
    """Build one normal-carrier 45x128 point array without opening saved targets."""
    pins = plan["pinned_artifacts"]
    input_path = pinned_file(root, pins["normal_input"], "normal input")
    coeff_path = pinned_file(root, pins["lw_coefficients"], "coefficient table")
    const_path = pinned_file(root, pins["gas_constants"], "constants")
    kernel_path = pinned_file(root, pins["gas_kernel"], "kernel")
    frontend_path = pinned_file(root, pins["gas_frontend"], "frontend")
    loader_path = pinned_file(root, pins["coefficient_loader"], "loader")
    # Source pins are returned before any optical-depth target is opened.
    source_pins = {n: {"path": str(p.relative_to(root)), "size_bytes": p.stat().st_size,
                       "sha256": file_sha(p)} for n, p in {
        "input": input_path, "coefficients": coeff_path, "constants": const_path,
        "kernel": kernel_path, "frontend": frontend_path, "loader": loader_path}.items()}
    inp = read_packet(input_path, "LW")
    for section, shape in {"PLAY": (1,45), "PLEV": (1,46), "TLAY": (1,45),
                           "NATIVE_DRY_LAYER_MASS_KG_M2": (1,32), "MOL_WEIGHT_DRY": (1,1), "GRAVITY": (1,1)}.items():
        if section not in inp or inp[section].shape != shape:
            raise ValueError(f"input section {section} has wrong/missing shape")
    v = read_table(coeff_path)
    table_gases = list(v["gas_names"])
    avog = read_avogadro(const_path)
    # Normal captured carrier: target reference has 32 supplied native masses.
    # Its 13 upper extensions retain get_col_dry pressure-derived amounts.
    mass = inp["NATIVE_DRY_LAYER_MASS_KG_M2"][0]
    if mass.shape != (32,) or np.any(mass <= 0.0):
        raise ValueError("normal carrier must supply exactly 32 positive native masses")
    mdry = float(inp["MOL_WEIGHT_DRY"].item())
    gravity = float(inp["GRAVITY"].item())
    if mdry <= 0.0 or gravity <= 0.0:
        raise ValueError("nonpositive host dry molecular weight or gravity")
    const_text = const_path.read_text(encoding="ascii")
    m = re.search(r"m_h2o\s*=\s*([0-9.]+(?:[Ee][+-]?\d+)?)_wp", const_text, re.I)
    if not m:
        raise ValueError("pinned source has no recognized water molecular weight")
    mh2o = float(m.group(1))
    h2o = np.asarray(inp["H2O"], dtype=np.float64)
    if h2o.shape != (1,45) or np.any(h2o < 0.0):
        raise ValueError("H2O must contain 45 nonnegative dry-air VMR values")
    pressure_edges = np.asarray(inp["PLEV"][0], dtype=np.float64) * 100.0
    dry = np.empty(45, dtype=np.float64)
    dry_terms = []
    for k in range(45):
        delta_plev = abs(float(pressure_edges[k]) - float(pressure_edges[k+1]))
        vmr = float(h2o[0,k])
        fact = 1.0 / (1.0 + vmr)
        m_air = (mdry + mh2o * vmr) * fact
        pressure_dry = 10.0 * delta_plev * avog * fact / (1000.0 * m_air * 100.0 * gravity)
        # Match the source-grouped native expression in the captured campaign
        # implementation. This is source-order modeling, not bitwise emulation
        # of the production Fortran kind/evaluation.
        selected = float(mass[k]) * (avog / (mdry * 10000.0)) if k < 32 else pressure_dry
        dry[k] = selected
        dry_terms.append({"layer_fortran": k+1, "source": "native_mass_prefix" if k < 32 else "pressure_extension",
                          "vmr_h2o": vmr, "delta_pressure_pa": delta_plev,
                          "dry_fraction": fact, "moist_molar_mass_kg_mol": m_air,
                          "pressure_derived_molecule_cm2": pressure_dry,
                          "native_mass_kg_m2": float(mass[k]) if k < 32 else None,
                          "selected_molecule_cm2": selected})
    if not np.isfinite(dry).all() or np.any(dry <= 0):
        raise ValueError("invalid independently derived normal dry column")
    tref = np.asarray(v["temp_ref"], dtype=np.float64)
    pref = np.asarray(v["press_ref"], dtype=np.float64)
    p_trop = float(np.asarray(v["press_ref_trop"]).reshape(-1)[0])
    if (not np.isfinite(tref).all() or not np.isfinite(pref).all() or
            not math.isfinite(p_trop) or np.any(tref <= 0.0) or np.any(pref <= 0.0) or
            p_trop <= 0.0 or np.any(np.diff(tref) <= 0.0) or np.any(np.diff(pref) >= 0.0)):
        raise ValueError("reference temperature/pressure grids or tropopause pressure violate source ordering/range")
    dtemp = (float(tref[-1]) - float(tref[0])) / (len(tref) - 1)
    pref_log = np.log(pref)
    pdelta = (math.log(float(pref[-1])) - math.log(float(pref[0]))) / (len(pref) - 1)
    trop_log = math.log(p_trop)
    if dtemp <= 0 or pdelta == 0 or not np.isfinite(pref_log).all():
        raise ValueError("invalid coefficient interpolation coordinates")
    play = np.asarray(inp["PLAY"][0], dtype=np.float64) * 100.0
    tlay = np.asarray(inp["TLAY"][0], dtype=np.float64)
    plev = np.asarray(inp["PLEV"][0], dtype=np.float64) * 100.0
    if (not np.isfinite(play).all() or not np.isfinite(tlay).all() or
            not np.isfinite(plev).all() or np.any(play <= 0.0) or
            np.any(tlay <= 0.0) or np.any(plev < 0.0)):
        raise ValueError("PLAY/TLAY must be positive finite and PLEV nonnegative finite")
    pref_min, pref_max = float(np.min(pref)), float(np.max(pref))
    tref_min, tref_max = float(np.min(tref)), float(np.max(tref))
    if np.any(play < pref_min) or np.any(play > pref_max):
        raise ValueError("PLAY outside pinned pressure-reference range")
    if np.any(tlay < tref_min) or np.any(tlay > tref_max):
        raise ValueError("TLAY outside pinned temperature-reference range")
    case_ids = ("normal-positive-n2-captured-input",)
    output_cases = []
    for case_id in case_ids:
        # `available_gases` is the caller membership set, but the frontend
        # constructs this%gas_names by PACK(gas_names, mask=membership): the
        # resulting reduced runtime order is therefore coefficient-table order.
        caller_membership = set(CALL_GAS_ORDER)
        available = [gas for gas in table_gases if gas in caller_membership]
        if not available or not caller_membership.issubset(set(table_gases)):
            raise ValueError("caller gas membership cannot be represented by the pinned table")
        key, flavors = mapped_flavors(np.asarray(v["key_species"]), table_gases, available)
        # col_gas(0,:) is dry; positive slots follow coefficient-table order
        # filtered by caller membership, matching frontend PACK(gas_names,...).
        colgas = np.zeros((len(available) + 1, 45), dtype=np.float64)
        colgas[0] = dry
        for ig, gas in enumerate(available, start=1):
            sec = INPUT_SECTIONS[gas]
            if sec not in inp or inp[sec].shape != (1, 45):
                raise ValueError(f"missing 45-level VMR section {sec}")
            vmr = inp[sec][0]
            if not np.isfinite(vmr).all() or np.any(vmr < 0):
                raise ValueError(f"invalid VMR {gas}")
            colgas[ig] = vmr * dry
        # Recreate interpolation state exactly as the pinned kernel computes it.
        nt, npres, neta = len(tref), len(pref), int(np.shape(v["kmajor"])[2])
        jt, jp, ft, fp, trop = [], [], [], [], []
        for k in range(45):
            jt0 = int((tlay[k] - (float(tref[0]) - dtemp)) / dtemp)
            jt0 = min(nt - 1, max(1, jt0))
            ft0 = (tlay[k] - float(tref[jt0 - 1])) / dtemp
            locp = 1.0 + (math.log(float(play[k])) - float(pref_log[0])) / pdelta
            jp0 = min(npres - 1, max(1, int(locp)))
            fp0 = locp - float(jp0)
            jt.append(jt0); jp.append(jp0); ft.append(ft0); fp.append(fp0)
            trop.append(math.log(float(play[k])) > trop_log)
        state = {}
        vmr_ref = np.asarray(v["vmr_ref"], dtype=np.float64)
        for k in range(45):
            atm = 0 if trop[k] else 1
            layer = {}
            for fid, pair in enumerate(flavors):
                planes = []
                for ipt in range(2):
                    tr = jt[k] - 1 + ipt
                    raw_a = 0 if pair[0] == 0 else table_gases.index(available[pair[0] - 1]) + 1
                    raw_b = 0 if pair[1] == 0 else table_gases.index(available[pair[1] - 1]) + 1
                    numerator = float(vmr_ref[tr, raw_a, atm])
                    denominator = float(vmr_ref[tr, raw_b, atm])
                    if denominator <= 0.0:
                        raise ValueError("nonpositive reference VMR denominator")
                    ratio = numerator / denominator
                    if not math.isfinite(ratio):
                        raise ValueError("nonfinite reference VMR ratio")
                    cmix = colgas[pair[0], k] + ratio * colgas[pair[1], k]
                    if cmix > 2.0 * np.finfo(np.float64).tiny:
                        eta = colgas[pair[0], k] / cmix
                    else:
                        eta = 0.5
                    loceta = eta * float(neta - 1)
                    je = min(int(loceta) + 1, neta - 1)
                    if je < 1 or je >= neta:
                        raise ValueError("eta interpolation index outside coefficient table")
                    fe = math.fmod(loceta, 1.0)
                    fm_temp = (1.0 - ft[k]) if ipt == 0 else ft[k]
                    fm = ((1.0 - fe) * fm_temp, fe * fm_temp)
                    fpress = fp[k]
                    major_weights = ((1.0-fpress)*fm[0], (1.0-fpress)*fm[1],
                                     fpress*fm[0], fpress*fm[1])
                    planes.append({"cmix": float(cmix), "eta": float(eta), "jeta": je,
                                   "feta": float(fe), "fminor": fm,
                                   "fmajor": major_weights})
                layer[fid] = planes
            state[k] = layer
        # Exact source minor interval pruning/repack: build kept raw slices in table order.
        minor_rows = {suffix: _interval_rows(v, suffix, available) for suffix in ("lower", "upper")}
        packed = {suffix: _pack_minor(np.asarray(v[f"kminor_{suffix}"]), minor_rows[suffix])
                  for suffix in ("lower", "upper")}
        bands = np.asarray(v["bnd_limits_gpt"], dtype=np.int64)
        if (bands.shape != (16,2) or int(bands[0,0]) != 1 or int(bands[-1,1]) != 128 or
                np.any(bands[:,0] > bands[:,1]) or
                any(int(bands[i+1,0]) != int(bands[i,1])+1 for i in range(15))):
            raise ValueError("band/g-point map is not a contiguous 1..128 partition")
        tau = np.zeros((45, 128), dtype=np.float64)
        kmajor = np.asarray(v["kmajor"], dtype=np.float64)
        # Kernel call adds each band in source order; interpolation3D groups four corners
        # by temperature plane, applies col_mix after that plane sum, then adds planes.
        major_terms = []
        for band, (gstart, gstop) in enumerate(bands):
            for k in range(45):
                atm = 0 if trop[k] else 1
                pair = tuple(int(x) for x in key[band, atm])
                fid = flavors.index(pair)
                planes = state[k][fid]
                itropo = 1 if trop[k] else 2
                for gfor in range(int(gstart), int(gstop) + 1):
                    plane_terms = []
                    plane_ledgers = []
                    for ipt, ps in enumerate(planes):
                        tindex = jt[k] - 1 + ipt
                        pbase = jp[k] + itropo - 2
                        ebase = ps["jeta"] - 1
                        # The interpolation index is based on npress reference
                        # coordinates, but the raw kmajor pressure axis has its
                        # own (60-slot) extent. Validate the two accessed table
                        # slots against that raw axis, not len(press_ref).
                        if not (0 <= pbase < np.shape(kmajor)[1]-1 and 0 <= ebase < neta-1):
                            raise ValueError("pressure/eta interpolation corner outside coefficient table")
                        wm = ps["fmajor"]
                        # Fortran expression: four weighted corners, left-associated.
                        # NetCDF raw axes are (temperature,pressure,eta,gpt).
                        coeffs = [
                            float(kmajor[tindex, pbase,   ebase,   gfor-1]),
                            float(kmajor[tindex, pbase,   ebase+1, gfor-1]),
                            float(kmajor[tindex, pbase+1, ebase,   gfor-1]),
                            float(kmajor[tindex, pbase+1, ebase+1, gfor-1]),
                        ]
                        terms = [wm[i] * coeffs[i] for i in range(4)]
                        s = terms[0] + terms[1]
                        s = s + terms[2]
                        s = s + terms[3]
                        plane_terms.append(ps["cmix"] * s)
                        plane_ledgers.append({
                            "temperature_index_fortran": jt[k] + ipt,
                            "eta_index_fortran": ps["jeta"],
                            "pressure_low_index_fortran": pbase + 1,
                            "coefficient_indices_fortran_raw_netCDF_T_P_eta_gpt": [
                                [tindex+1, pbase+1, ebase+1, gfor],
                                [tindex+1, pbase+1, ebase+2, gfor],
                                [tindex+1, pbase+2, ebase+1, gfor],
                                [tindex+1, pbase+2, ebase+2, gfor],
                            ],
                            "weights_eta_low_pressure_low__eta_high_pressure_low__eta_low_pressure_high__eta_high_pressure_high": wm,
                            "corner_coefficients_same_order": coeffs,
                            "weighted_corner_terms_same_order": terms,
                            "weighted_corner_sum_left_associated": s,
                            "col_mix": ps["cmix"],
                            "scaled_plane_value": plane_terms[-1],
                        })
                    major = plane_terms[0] + plane_terms[1]
                    tau[k, gfor-1] = tau[k, gfor-1] + major
                    major_terms.append({"band_fortran": band+1, "layer_fortran": k+1,
                                        "gpoint_fortran": gfor, "atmosphere_fortran": itropo,
                                        "flavor_fortran": fid+1, "key_pair_reduced_ids": list(pair),
                                        "planes": plane_ledgers,
                                        "two_scaled_plane_sum": major,
                                        "tau_after_major_add": float(tau[k, gfor-1])})
        # Lower then upper interval arrays; each retained interval applies only to its
        # atmosphere class, with source scaling and four source-ordered minor corners.
        gas_index = {gas: i + 1 for i, gas in enumerate(available)}
        minor_terms = []
        for atm, suffix in ((0, "lower"), (1, "upper")):
            km = packed[suffix]
            for row in minor_rows[suffix]:
                if not row["keep"]:
                    continue
                g0, g1 = row["lo"] - 1, row["hi"]
                band = int(np.searchsorted(bands[:, 1], row["lo"], side="left"))
                end_band = int(np.searchsorted(bands[:, 1], row["hi"], side="left"))
                if band >= len(bands) or end_band != band:
                    raise ValueError("minor interval is not contained in exactly one band")
                pair = tuple(int(x) for x in key[band, atm])
                fid = flavors.index(pair)
                pstart = int(row["packed_start"]) - 1
                for k in range(45):
                    if (0 if trop[k] else 1) != atm:
                        continue
                    scaling = float(colgas[gas_index[row["gas"]], k])
                    if row["density"]:
                        density_factor = 0.01 * float(play[k]) / float(tlay[k])
                        scaling = scaling * density_factor
                    else:
                        density_factor = None
                    scaling_gas_factor = None
                    if row["density"]:
                        sg = row["scale_gas"]
                        if sg in gas_index:
                            vmr_fact = 1.0 / float(colgas[0, k])
                            dry_fact = 1.0 / (1.0 + float(colgas[gas_index["h2o"], k]) * vmr_fact)
                            gas_fact = float(colgas[gas_index[sg], k]) * vmr_fact * dry_fact
                            scaling_gas_factor = gas_fact
                            if row["complement"]:
                                scaling = scaling * (1.0 - gas_fact)
                            else:
                                scaling = scaling * gas_fact
                    planes = state[k][fid]
                    for goff, g in enumerate(range(g0, g1)):
                        # interpolate2D_byflav source order: eta lower/upper at T0,
                        # then eta lower/upper at T1.
                        ps0, ps1 = planes
                        start = pstart + goff
                        a = ps0["fminor"][0] * float(km[jt[k]-1, ps0["jeta"]-1, start])
                        b = ps0["fminor"][1] * float(km[jt[k]-1, ps0["jeta"], start])
                        c = ps1["fminor"][0] * float(km[jt[k], ps1["jeta"]-1, start])
                        d = ps1["fminor"][1] * float(km[jt[k], ps1["jeta"], start])
                        interp = ((a + b) + c) + d
                        added = scaling * interp
                        tau[k, g] = tau[k, g] + added
                        minor_terms.append({
                            "atmosphere_lower_upper": suffix, "interval_id": row["id"],
                            "absorber": row["gas"], "layer_fortran": k+1,
                            "gpoint_fortran": g+1, "packed_contributor_index_fortran": start+1,
                            "raw_contributor_index_fortran": int(row["raw_start"])+goff,
                            "coefficient_indices_fortran_packed_temp_eta_contributor": [
                                [jt[k], ps0["jeta"], start+1],
                                [jt[k], ps0["jeta"]+1, start+1],
                                [jt[k]+1, ps1["jeta"], start+1],
                                [jt[k]+1, ps1["jeta"]+1, start+1],
                            ],
                            "coefficient_indices_fortran_raw_table_temp_eta_contributor": [
                                [jt[k], ps0["jeta"], int(row["raw_start"])+goff],
                                [jt[k], ps0["jeta"]+1, int(row["raw_start"])+goff],
                                [jt[k]+1, ps1["jeta"], int(row["raw_start"])+goff],
                                [jt[k]+1, ps1["jeta"]+1, int(row["raw_start"])+goff],
                            ],
                            "scaling_before_density": float(colgas[gas_index[row["gas"]], k]),
                            "density_factor": density_factor,
                            "scaling_gas_factor": scaling_gas_factor,
                            "complement": row["complement"], "scaling_final": scaling,
                            "minor_corner_terms_source_order": [a,b,c,d],
                            "interpolated_minor_coefficient_left_associated": interp,
                            "scaled_minor_tau": added,
                            "tau_after_minor_add": float(tau[k,g]),
                        })
        if tau.shape != (45, 128) or not np.isfinite(tau).all():
            raise ValueError(f"invalid constructed tau for {case_id}")
        output_cases.append({
            "case_id": case_id, "available_gases": available,
            "n2_source": "captured VMR_N2 input section; no scalar override or averaging",
            "n2_vmr_values": inp["VMR_N2"][0].tolist(),
            "gas_column_records": [
                {"gas": gas, "input_section": INPUT_SECTIONS[gas],
                 "vmr_values": inp[INPUT_SECTIONS[gas]][0].tolist(),
                 "column_molecule_cm2": colgas[gas_index, :].tolist()}
                for gas_index, gas in enumerate(available, start=1)],
            "dry_column_molecule_cm2": dry.tolist(), "tau_point": tau.tolist(),
            "discrete_context": {"jtemp_fortran": jt, "jpress_fortran": jp,
                                 "tropopause_lower": trop,
                                 "flavors_reduced_ids": [list(x) for x in flavors],
                                 "key_species_reduced_ids": key.tolist(),
                                 "minor_intervals": minor_rows,
                                 "layer_flavor_state": [
                                     {"layer_fortran": k+1, "jtemp_fortran": jt[k],
                                      "ftemp": ft[k], "jpress_fortran": jp[k],
                                      "fpress": fp[k], "tropopause_lower": trop[k],
                                      "flavors": [{"flavor_fortran": fid+1,
                                                   "reduced_pair": list(pair),
                                                   "reference_planes": state[k][fid]}
                                                  for fid,pair in enumerate(flavors)]}
                                     for k in range(45)]},
            "major_terms_source_order": major_terms,
            "minor_terms_source_order": minor_terms,
            "target_policy": "no saved opacity/result target is opened or read by this draft",
        })
    return {"status": "POINT_ARRAYS_CONSTRUCTED_TARGETS_NOT_OPENED",
            "source_pins": source_pins, "normal_carrier_scope": "32 native mass values plus 13 pressure-derived extensions",
            "dry_column_source_order_terms": dry_terms,
            "cases": output_cases,
            "limitations": [
                "Same-table mechanics only; this is not coefficient-generation or physical-accuracy validation.",
                "This point implementation has no strict arithmetic/log enclosure; residual agreement, when separately authorized, can only be diagnostic.",
            "The captured positive VMR_N2 is an input to this reconstruction, not evidence that its declared unit is physically correct.",
            "No saved GAS_TAU or other result target is opened or read by this draft."]}


def main() -> int:
    raise SystemExit("LOCKED: root must review point implementation and issue a separate diagnostic plan before reconstruction execution")


if __name__ == "__main__":
    main()
