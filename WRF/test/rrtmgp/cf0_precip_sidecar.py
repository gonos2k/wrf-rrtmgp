#!/usr/bin/env python3
"""Portable Python validation of held CF0 precipitation sidecars.

No solver is launched. These checks authenticate caller-provided raw/input files;
the caller must separately pin their provenance and the actual launch closure.
They do not exercise the compiled Fortran sidecar reader.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import struct

MAGIC = "RRTMGP_CF0_PRECIP_AUDIT_V1"
UNITS = "PATH_UNITS_G_M2"

class SidecarError(ValueError):
    pass

def parse_raw(path: Path):
    lines = path.read_text().splitlines()
    if len(lines) < 2 or lines[0].strip() != "RRTMGP_RAW_V1":
        raise SidecarError("bad raw magic")
    hdr = lines[1].split()
    if len(hdr) != 4 or hdr[0] not in ("LW", "SW"):
        raise SidecarError("bad raw header")
    phase, i, j, native_n = hdr[0], int(hdr[1]), int(hdr[2]), int(hdr[3])
    records = {}
    k = 2
    while k < len(lines):
        head = lines[k].split()
        k += 1
        if len(head) != 2:
            raise SidecarError(f"malformed raw section at line {k}")
        name, count = head[0], int(head[1])
        vals = []
        while len(vals) < count and k < len(lines):
            vals.extend(float(x) for x in lines[k].split())
            k += 1
        if len(vals) != count or name in records:
            raise SidecarError(f"bad count or duplicate raw section {name}")
        records[name] = vals
    return (phase, i, j, native_n), records

def validate_payload(phase, ncol, native_n, species, occurrence, rain, snow, cf,
                     engine_n=None):
    if phase not in ("LW", "SW") or ncol != 1 or native_n < 1:
        raise SidecarError("invalid phase or dimensions")
    if species not in (1, 2):
        raise SidecarError("species must be 1 (rain) or 2 (snow)")
    if not math.isfinite(float(occurrence)) or float(occurrence) != 1.0:
        raise SidecarError("occurrence must be exactly one")
    if engine_n is not None and (native_n > engine_n):
        raise SidecarError("native prefix exceeds engine depth")
    for name, arr in (("rain", rain), ("snow", snow), ("cf", cf)):
        if len(arr) != ncol or any(len(row) != native_n for row in arr):
            raise SidecarError(f"{name} must have shape (ncol,native_nl)")
        if any(not math.isfinite(float(v)) for row in arr for v in row):
            raise SidecarError(f"{name} must be finite")
    if any(v < 0 for row in rain for v in row) or any(v < 0 for row in snow for v in row):
        raise SidecarError("paths must be nonnegative")
    if species == 1 and any(v != 0 for row in snow for v in row):
        raise SidecarError("rain-only call requires zero snow sidecar")
    if species == 2 and any(v != 0 for row in rain for v in row):
        raise SidecarError("snow-only call requires zero rain sidecar")
    if any((rain[c][k] > 0 or snow[c][k] > 0) and cf[c][k] > 0
           for c in range(ncol) for k in range(native_n)):
        raise SidecarError("positive sidecar paths are restricted to CF==0")
    if any(v < 0 or v > 1 for row in cf for v in row):
        raise SidecarError("CF must be in [0,1]")
    return True

def encode(phase, ncol, native_n, species, occurrence, rain, snow, cf, engine_n=None):
    validate_payload(phase, ncol, native_n, species, occurrence, rain, snow, cf, engine_n)
    def section(name, values):
        rows = [f"{name} {ncol} {native_n}"]
        rows += [" ".join(f"{float(x):.17e}" for x in values[c]) for c in range(ncol)]
        return rows
    out = [MAGIC, f"{phase} {ncol} {native_n} {species} {float(occurrence):.1f}", UNITS]
    out += section("AUDIT_RWP_GRID", rain)
    out += section("AUDIT_SWP_GRID", snow)
    return "\n".join(out) + "\n"

def _decode(text):
    lines = text.splitlines()
    if len(lines) < 7 or lines[0].strip() != MAGIC:
        raise SidecarError("bad sidecar magic/length")
    h = lines[1].split()
    if len(h) != 5:
        raise SidecarError("bad sidecar header")
    phase, ncol, native_n, species = h[0], int(h[1]), int(h[2]), int(h[3])
    occurrence = float(h[4])
    if ncol != 1 or native_n < 1:
        raise SidecarError("invalid sidecar dimensions")
    if lines[2].strip() != UNITS:
        raise SidecarError("bad units token")
    pos = 3
    arrays = {}
    for expected in ("AUDIT_RWP_GRID", "AUDIT_SWP_GRID"):
        parts = lines[pos].split(); pos += 1
        if len(parts) != 3 or parts[0] != expected or int(parts[1]) != ncol or int(parts[2]) != native_n:
            raise SidecarError("sidecar section header/shape mismatch")
        vals = []
        for _ in range(ncol):
            row = [float(x) for x in lines[pos].split()]; pos += 1
            if len(row) != native_n:
                raise SidecarError("sidecar row length mismatch")
            vals.append(row)
        arrays[expected] = vals
    if pos != len(lines):
        raise SidecarError("trailing sidecar content")
    return phase, ncol, native_n, species, occurrence, arrays["AUDIT_RWP_GRID"], arrays["AUDIT_SWP_GRID"]

def decode(text):
    try:
        return _decode(text)
    except (IndexError, ValueError, OverflowError) as exc:
        raise SidecarError("malformed or truncated sidecar") from exc

def parse_input_matrix(path: Path, wanted: str):
    lines=path.read_text().splitlines()
    found=[]
    for i,line in enumerate(lines):
        head=line.split()
        if len(head)==3 and head[0]==wanted:
            try: rows,cols=int(head[1]),int(head[2])
            except ValueError: continue
            count=rows*cols; vals=[]; j=i+1
            while len(vals)<count and j<len(lines):
                try: vals.extend(float(x) for x in lines[j].split())
                except ValueError: break
                j+=1
            if len(vals)==count: found.append((rows,cols,vals))
    if len(found)!=1: raise SidecarError(f"input must contain exactly one complete {wanted} section")
    return found[0]

def validate_replay_context(input_path: Path, raw_header, raw_records, engine_n: int):
    """Validate the untouched replay context paired with an audit sidecar.

    V10/V11 CU policy and profile sections are required and hashed here so a
    sidecar validation cannot silently drop the held CU population. This
    validates the supplied input; it never rewrites it.
    """
    lines = input_path.read_text(encoding="ascii").splitlines()
    if len(lines) < 2:
        raise SidecarError("replay input is truncated")
    version = lines[0].strip()
    header = lines[1].split()
    if version not in {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V9", "RRTMGP_REPLAY_V10", "RRTMGP_REPLAY_V11", "RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"}:
        raise SidecarError("CF0 sidecar context requires replay V8-V13")
    if len(header) != 6:
        raise SidecarError("replay header must contain phase/nc/nl/overlap/seed/iceflag")
    records_text = "\n".join(lines[2:])
    if version not in {"RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"} and \
            any((name + " ") in records_text for name in ("VMR_N2", "TRACE_GASES_PRESENT")):
        raise SidecarError("N2 background fields require replay V12/V13")
    phase = header[0].upper()
    try:
        nc, nl = int(header[1]), int(header[2])
    except ValueError as exc:
        raise SidecarError("invalid replay dimensions") from exc
    if nc != 1 or nl != engine_n or phase != raw_header[0]:
        raise SidecarError("replay phase/shape does not match paired raw/engine")
    if (version in {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V10", "RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"} and phase != "LW") or \
       (version in {"RRTMGP_REPLAY_V9", "RRTMGP_REPLAY_V11"} and phase != "SW"):
        raise SidecarError("replay version is not valid for this phase")
    def matrix(name):
        rows, cols, values = parse_input_matrix(input_path, name)
        return (rows, cols), values
    cf_shape, cf_values = matrix("CF")
    if cf_shape != (1, engine_n) or len(raw_records.get("CF", [])) != raw_header[3]:
        raise SidecarError("replay CF shape differs from engine/native context")
    if cf_values[:raw_header[3]] != raw_records["CF"]:
        raise SidecarError("replay CF native prefix differs from paired raw capture")
    if version in {"RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"}:
        n2_shape, n2_values = matrix("VMR_N2")
        flag_shape, flag_values = matrix("TRACE_GASES_PRESENT")
        if n2_shape != (1, engine_n) or any(not math.isfinite(v) or v < 0.0 or v > 1.0 for v in n2_values):
            raise SidecarError(f"{version} VMR_N2 must be finite in [0,1] with shape (1,nl)")
        if flag_shape != (1, 1) or flag_values[0] not in (0.0, 1.0):
            raise SidecarError(f"{version} TRACE_GASES_PRESENT must be scalar zero or one")
        cfc_names = ("VMR_CFC11", "VMR_CFC12", "VMR_CFC22", "VMR_CCL4")
        cfc_present = [input_path.read_text(encoding="ascii").count(name + " ") == 1 for name in cfc_names]
        if flag_values[0] == 1.0:
            for name in cfc_names:
                shape, values = matrix(name)
                if shape != (1, engine_n) or any(not math.isfinite(v) or v < 0.0 for v in values):
                    raise SidecarError(f"{version} {name} must be finite/nonnegative with shape (1,nl)")
        elif any(cfc_present):
            raise SidecarError(f"{version} CFC records conflict with TRACE_GASES_PRESENT=0")
    if version in {"RRTMGP_REPLAY_V10", "RRTMGP_REPLAY_V11", "RRTMGP_REPLAY_V13"}:
        cu_arrays = {}
        for name in ("CU_POPULATION_POLICY", "CU_RADIUS_POLICY", "CU_OCCURRENCE_POLICY"):
            shape, values = matrix(name)
            if shape != (1, 1) or values != [1.0]:
                raise SidecarError(f"{version} requires preserved scalar {name}=1")
            raw_value = raw_records.get(name)
            if raw_value != [1.0]:
                raise SidecarError(f"paired raw capture disagrees with {name}")
            cu_arrays[name] = values
        for name in ("CU_LWP", "CU_IWP", "CU_REL", "CU_REI"):
            shape, values = matrix(name)
            if shape != (1, engine_n) or any(not math.isfinite(v) for v in values):
                raise SidecarError(f"{version} {name} must be finite with shape (1,nl)")
            if name in {"CU_LWP", "CU_IWP"} and any(v < 0.0 for v in values):
                raise SidecarError(f"{version} {name} must be nonnegative")
            if name in {"CU_REL", "CU_REI"} and any(v <= 0.0 for v in values):
                raise SidecarError(f"{version} {name} must be positive")
            cu_arrays[name] = values
        native_shape, native_values = matrix("NATIVE_DRY_LAYER_MASS_KG_M2")
        if native_shape != (1, raw_header[3]) or any(not math.isfinite(v) or v <= 0.0 for v in native_values):
            raise SidecarError(f"{version} native dry-mass prefix must match raw depth and be positive")
        if version == "RRTMGP_REPLAY_V11":
            required = ("SW_DIRECT_PREDELTA_POLICY", "TOA_GPOINT", "RAW_GAS_TAU", "MCICA_MASK",
                        "RAW_CLOUD_TAU", "RAW_NATIVE_CLOUD_TAU", "RAW_CU_CLOUD_TAU",
                        "RAW_PRECIP_TAU", "RAW_GRAUPEL_TAU_EXT", "RAW_HAIL_TAU_EXT",
                        "BAND_LIMS_GPOINT", "BAND_LIMS_WAVENUMBER", "VISIBLE_WEIGHT")
            names = {line.split()[0] for line in lines[2:] if len(line.split()) >= 3}
            missing = [name for name in required if name not in names]
            if missing:
                raise SidecarError("V11 direct/CU optical provenance missing: " + ", ".join(missing))
            shape, values = matrix("SW_DIRECT_PREDELTA_POLICY")
            if shape != (1, 1) or values != [1.0]:
                raise SidecarError("V11 SW_DIRECT_PREDELTA_POLICY must equal one")
        digest = hashlib.sha256()
        for name in ("CU_POPULATION_POLICY", "CU_RADIUS_POLICY", "CU_OCCURRENCE_POLICY",
                     "CU_LWP", "CU_IWP", "CU_REL", "CU_REI"):
            digest.update(name.encode("ascii") + b"\0")
            digest.update(struct.pack("!I", len(cu_arrays[name])))
            for value in cu_arrays[name]:
                digest.update(struct.pack("!d", value))
        return {"version": version, "phase": phase, "native_layers": raw_header[3],
                "engine_layers": engine_n, "cu_policy_profile_sha256": digest.hexdigest(),
                "cu_records_preserved": list(cu_arrays)}
    return {"version": version, "phase": phase, "native_layers": raw_header[3],
            "engine_layers": engine_n, "cu_records_preserved": []}


def validate_against_raw(sidecar_text, raw_path: Path, species_name: str, engine_n: int, input_path: Path | None = None, zero_control: bool = False):
    header, rec = parse_raw(raw_path)
    phase, i, j, native_n = header
    replay_context = None
    if input_path is not None:
        first = input_path.read_text(encoding="ascii").splitlines()[0].strip()
        if first in {"RRTMGP_REPLAY_V8", "RRTMGP_REPLAY_V9", "RRTMGP_REPLAY_V10", "RRTMGP_REPLAY_V11", "RRTMGP_REPLAY_V12", "RRTMGP_REPLAY_V13"}:
            replay_context = validate_replay_context(input_path, header, rec, engine_n)
    phase2, ncol, n2, species, occ, rain, snow = decode(sidecar_text)
    expected_species = {"rain": 1, "snow": 2}.get(species_name)
    if phase2 != phase or ncol != 1 or n2 != native_n or species != expected_species:
        raise SidecarError("sidecar does not match raw phase/shape/species")
    for key in ("CF", "RWP_OMITTED", "SWP_OMITTED"):
        if key not in rec or len(rec[key]) != native_n:
            raise SidecarError(f"raw capture lacks native {key}")
    cf = [rec["CF"]]
    validate_payload(phase, ncol, native_n, species, occ, rain, snow, cf, engine_n)
    expected_rain = rec["RWP_OMITTED"] if species == 1 else [0.0] * native_n
    expected_snow = rec["SWP_OMITTED"] if species == 2 else [0.0] * native_n
    if zero_control:
        expected_rain = [0.0] * native_n
        expected_snow = [0.0] * native_n
    if rain[0] != expected_rain or snow[0] != expected_snow:
        raise SidecarError("sidecar values differ from captured omitted raw paths")
    if species == 2:
        for key in ("RES", "SOURCE_RE_SNOW"):
            if key not in rec or len(rec[key]) != native_n or any(not math.isfinite(v) for v in rec[key]):
                raise SidecarError(f"raw capture lacks finite native {key}")
        if input_path is not None:
            rows,cols,input_res=parse_input_matrix(input_path,"RES")
            if rows!=ncol or cols!=engine_n or input_res[:native_n]!=rec["RES"]:
                raise SidecarError("replay input RES native prefix differs from paired raw capture")
        if "RES" not in rec or "SOURCE_RE_SNOW" not in rec or "HAS_REQS" not in rec:
            raise SidecarError("snow anchor lacks explicit source-radius capability/radius records")
        if rec["HAS_REQS"] != [1.0]:
            raise SidecarError("snow source-radius capability flag is not explicitly active")
        active = [k for k, v in enumerate(snow[0]) if v > 0]
        bg_snow = struct.unpack("f", struct.pack("f", 9.99e-6))[0]
        for k in active:
            source_m = rec["SOURCE_RE_SNOW"][k]
            source_um = source_m * 1.0e6
            if rec["RES"][k] <= 10.0:
                raise SidecarError("active snow audit radius is not above the pinned helper's 10um threshold")
            if struct.unpack("f", struct.pack("f", source_m))[0] == bg_snow:
                raise SidecarError("active CF0 snow radius is the RE_QS_BG placeholder, not eligible for this proposal")
            if not math.isclose(rec["RES"][k],source_um,rel_tol=5.0e-7,abs_tol=1.0e-6):
                raise SidecarError("active snow RES does not match raw source radius in metres")
    return {"phase": phase, "anchor_ij": [i, j], "native_layers": native_n,
            "engine_layers": engine_n, "replay_context": replay_context, "species": species_name,
            "control": "all-zero" if zero_control else "positive-omitted-path",
            "positive_native_layers": sum(v > 0 for row in (rain if species == 1 else snow) for v in row),
            "omitted_path_sum_g_m2": sum(sum(row) for row in (rain if species == 1 else snow))}

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--raw", type=Path, required=True)
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--sidecar", type=Path, required=True)
    parser.add_argument("--species", choices=("rain", "snow"), required=True)
    parser.add_argument("--engine-layers", type=int, required=True)
    parser.add_argument("--zero-control", action="store_true",
                        help="authenticate an all-zero sidecar, not omitted-path equality")
    args = parser.parse_args()
    try:
        report = validate_against_raw(args.sidecar.read_text(), args.raw, args.species,
                                      args.engine_layers, args.input, args.zero_control)
    except (SidecarError, OSError, ValueError) as exc:
        parser.error(str(exc))
    print(json.dumps({"status": "PASS_PYTHON_SIDECAR_RAW_CONTRACT", **report,
                      "solver_calls": 0, "compiled_fortran_reader_exercised": False}))

if __name__ == "__main__":
    main()
