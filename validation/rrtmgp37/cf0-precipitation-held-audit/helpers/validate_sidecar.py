#!/usr/bin/env python3
"""Offline validator/serializer for the proposed CF0 precipitation audit sidecar.

This module performs no RRTMGP calls. It pins a sidecar to the independently
captured native raw paths and CF. The Fortran source patch is not compiled here.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
import struct
import tempfile
import unittest

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

def decode(text):
    lines = text.splitlines()
    if len(lines) < 7 or lines[0].strip() != MAGIC:
        raise SidecarError("bad sidecar magic/length")
    h = lines[1].split()
    if len(h) != 5:
        raise SidecarError("bad sidecar header")
    phase, ncol, native_n, species = h[0], int(h[1]), int(h[2]), int(h[3])
    occurrence = float(h[4])
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

def validate_against_raw(sidecar_text, raw_path: Path, species_name: str, engine_n: int, input_path: Path | None = None):
    header, rec = parse_raw(raw_path)
    phase, i, j, native_n = header
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
    if rain[0] != expected_rain or snow[0] != expected_snow:
        raise SidecarError("sidecar values differ from captured omitted raw paths")
    if species == 2:
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
            "engine_layers": engine_n, "species": species_name,
            "positive_native_layers": sum(v > 0 for row in (rain if species == 1 else snow) for v in row),
            "omitted_path_sum_g_m2": sum(sum(row) for row in (rain if species == 1 else snow))}

class ValidatorTests(unittest.TestCase):
    def payload(self):
        cf = [[0.0, 0.5, 0.0]]
        rain = [[2.0, 0.0, 0.0]]
        snow = [[0.0, 0.0, 0.0]]
        return ["LW", 1, 3, 1, 1.0, rain, snow, cf, 5]
    def test_roundtrip_native_only(self):
        p = self.payload(); text = encode(*p); d = decode(text)
        self.assertEqual((d[0],d[1],d[2],d[3]), ("LW",1,3,1))
        self.assertEqual(d[5], [[2.0,0.0,0.0]])
        self.assertEqual(len(d[5][0]), 3)  # engine padding is added as zero by reader
    def test_reject_cf_positive(self):
        p = self.payload(); p[5] = [[2.0,1.0,0.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_shape(self):
        p = self.payload(); p[5] = [[2.0,0.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_multicolumn_scope(self):
        with self.assertRaises(SidecarError):
            validate_payload("LW",2,3,1,1.0,[[1.,0.,0.],[1.,0.,0.]],[[0.,0.,0.],[0.,0.,0.]],[[0.,0.,0.],[0.,0.,0.]])
    def test_reject_units(self):
        p = self.payload(); text = encode(*p).replace(UNITS,"PATH_UNITS_KG_M2")
        with self.assertRaises(SidecarError): decode(text)
    def test_reject_nonfinite(self):
        p = self.payload(); p[5] = [[float('nan'),0.0,0.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_negative(self):
        p = self.payload(); p[5] = [[-1.0,0.0,0.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_species_mix(self):
        p = self.payload(); p[6] = [[0.0,0.0,1.0]]
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_occurrence(self):
        p = self.payload(); p[4] = 0.5
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_phase(self):
        p = self.payload(); p[0] = "MIXED"
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_engine_extension(self):
        p = self.payload(); p[2] = 5; p[5] = [[2.0,0.0,0.0,0.0,0.0]]; p[6] = [[0.0]*5]; p[7] = [[0.0]*5]; p[8] = 4
        with self.assertRaises(SidecarError): encode(*p)
    def test_reject_trailing_data(self):
        text=encode(*self.payload())+"UNEXPECTED 1\n0\n"
        with self.assertRaises(SidecarError): decode(text)
    def raw_fixture(self, source_radius_m):
        sections={"HAS_REQS":[1.0],"CF":[0.0,0.0],"SOURCE_RE_SNOW":[source_radius_m,source_radius_m],
                  "RES":[source_radius_m*1e6,source_radius_m*1e6],
                  "RWP_OMITTED":[0.0,0.0],"SWP_OMITTED":[0.0,1.0]}
        lines=["RRTMGP_RAW_V1","LW 7 9 2"]
        for name,values in sections.items(): lines += [f"{name} {len(values)}", " ".join(str(v) for v in values)]
        return "\n".join(lines)+"\n"
    def test_input_matrix_section(self):
        with tempfile.TemporaryDirectory() as tmp:
            f=Path(tmp)/"input"; f.write_text("RRTMGP_REPLAY_V1\nRES 1 3\n1 2 3\n")
            self.assertEqual(parse_input_matrix(f,"RES"),(1,3,[1.0,2.0,3.0]))
    def test_snow_radius_source_eligibility(self):
        text=encode("LW",1,2,2,1.0,[[0.,0.]],[[0.,1.]],[[0.,0.]],3)
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/"valid.raw"; raw.write_text(self.raw_fixture(25e-6))
            inp=Path(tmp)/"valid.input"; inp.write_text("RRTMGP_REPLAY_V1\nRES 1 3\n2.5e1 2.5e1 2.5e1\n")
            validate_against_raw(text,raw,"snow",3,inp)
    def test_reject_input_radius_mismatch(self):
        text=encode("LW",1,2,2,1.0,[[0.,0.]],[[0.,1.]],[[0.,0.]],3)
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/"raw"; raw.write_text(self.raw_fixture(25e-6))
            inp=Path(tmp)/"input"; inp.write_text("RRTMGP_REPLAY_V1\nRES 1 3\n25 24 25\n")
            with self.assertRaises(SidecarError): validate_against_raw(text,raw,"snow",3,inp)
    def test_reject_background_snow_radius(self):
        text=encode("LW",1,2,2,1.0,[[0.,0.]],[[0.,1.]],[[0.,0.]],3)
        with tempfile.TemporaryDirectory() as tmp:
            raw=Path(tmp)/"background.raw"; raw.write_text(self.raw_fixture(9.99e-6))
            with self.assertRaises(SidecarError): validate_against_raw(text,raw,"snow",3)
    def test_reject_extension_shape(self):
        p = self.payload(); p[2] = 5; p[5] = [[2.0,0.0,0.0,0.0,0.0]]; p[6] = [[0.0]*5]; p[7] = [[0.0]*5]
        with self.assertRaises(SidecarError): encode(*p[:-1], engine_n=3)

if __name__ == "__main__":
    ap=argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--workspace", type=Path)
    ap.add_argument("--write-sidecars", action="store_true")
    ap.add_argument("--outdir", type=Path)
    args=ap.parse_args()
    if args.self_test:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(ValidatorTests)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        raise SystemExit(0 if result.wasSuccessful() else 1)
    if not args.write_sidecars or args.workspace is None or args.outdir is None:
        ap.error("use --self-test or --workspace PATH --write-sidecars --outdir NEW_DIRECTORY")
    if args.outdir.exists(): ap.error("outdir already exists; refusing overwrite")
    args.outdir.mkdir(parents=True)
    cases=[
      ("rain-lw","rain","build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy/replay-recovery-v2/capture/lw.raw","build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy/replay-recovery-v2/capture/lw.input",47),
      ("rain-sw","rain","build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy/replay-recovery-v3/capture/sw.raw","build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy/replay-recovery-v3/capture/sw.input",40),
      ("snow-lw","snow","build/udm-stratified-replacement-captures-v1/material_cf0_snow_daylight_proxy/capture/lw.raw","build/udm-stratified-replacement-captures-v1/material_cf0_snow_daylight_proxy/capture/lw.input",47),
      ("snow-sw","snow","build/udm-stratified-replacement-captures-v1/material_cf0_snow_daylight_proxy/capture/sw.raw","build/udm-stratified-replacement-captures-v1/material_cf0_snow_daylight_proxy/capture/sw.input",40),
    ]
    report=[]
    for name,species,rel,input_rel,engine_n in cases:
        path=args.workspace/rel; input_path=args.workspace/input_rel
        hdr, rec=parse_raw(path); n=hdr[3]; sp=1 if species=="rain" else 2
        source="RWP_OMITTED" if sp==1 else "SWP_OMITTED"
        active=[rec[source]]
        other=[[0.0]*n]
        rain=active if sp==1 else other; snow=active if sp==2 else other
        cf=[rec["CF"]]
        text=encode(hdr[0],1,n,sp,1.0,rain,snow,cf,engine_n)
        summary=validate_against_raw(text,path,species,engine_n,input_path)
        out=args.outdir/(name+".positive.sidecar")
        out.write_text(text)
        report.append({**summary,"mode":"positive-omitted-path","raw_path":rel,
                       "raw_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                       "input_path":input_rel,"input_sha256":hashlib.sha256(input_path.read_bytes()).hexdigest(),
                       "sidecar_path":out.name,"sidecar_sha256":hashlib.sha256(out.read_bytes()).hexdigest()})
        zero_rain=[[0.0]*n]; zero_snow=[[0.0]*n]
        zero_text=encode(hdr[0],1,n,sp,1.0,zero_rain,zero_snow,cf,engine_n)
        z=decode(zero_text)
        validate_payload(z[0],z[1],z[2],z[3],z[4],z[5],z[6],cf,engine_n)
        zout=args.outdir/(name+".zero.sidecar"); zout.write_text(zero_text)
        report.append({"phase":hdr[0],"anchor_ij":[hdr[1],hdr[2],],"native_layers":n,
                       "engine_layers":engine_n,"species":species,"mode":"all-zero-control",
                       "positive_native_layers":0,"omitted_path_sum_g_m2":0.0,"raw_path":rel,
                       "raw_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
                       "sidecar_path":zout.name,"sidecar_sha256":hashlib.sha256(zout.read_bytes()).hexdigest()})
    (args.outdir/"manifest.json").write_text(json.dumps({"schema":"cf0-sidecar-proposal-v1","solver_calls":0,"cases":report},indent=2)+"\n")
