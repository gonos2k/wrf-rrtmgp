#!/usr/bin/env python3
"""Validate UDM call-entry density diagnostic packets and optional post-radius joins.

This checks writer format, identities, source equations and saved-state joins. It
is a diagnostic contract, not a physical-accuracy or equation-of-state authority.
Run self-tests with ``python -I -S test_udm_entry_density.py --self-test``.
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import hashlib
import importlib.util
import json
import math
from pathlib import Path
import re
import struct
import sys
import tempfile
import unittest

MAGIC = "RRTMGP_UDM_ENTRY_DENSITY_V1"
ENTRY_NAME = re.compile(r"udm_entry_density_d([0-9]+)_i([0-9]+)_j([0-9]+)_step([0-9]+)\.raw\Z")
FIELD_NAME = re.compile(r"[A-Z][A-Z0-9_]*\Z")
INTEGER = re.compile(r"[0-9]+\Z")
VECTOR_FIELDS = (
    "TH_K", "PII", "T_K", "P_PA", "QV_MIXING_RATIO_KG_KG", "DEN_PASSED_KG_M3",
    "DEND_REEVALUATED_PRECALL_KG_M3", "QC_RAW", "QI_RAW", "QR_RAW", "QS_RAW",
    "QG_RAW", "QH_RAW", "NN_RAW", "NC_RAW", "NR_RAW",
)
SCALAR_FIELDS = (
    "RD_J_KG_K", "RV_J_KG_K", "CPD_J_KG_K", "CPV_J_KG_K", "GRAVITY_M_S2",
    "DELT_SECONDS", "QMIN", "T0C_K", "RHO0_KG_M3", "RHO_WATER_KG_M3",
    "DEND_ORIGIN", "DEFAULT_REAL_BITS", "SOURCE_TIME_PRESENT",
)
OPTIONAL_SCALARS = ("SOURCE_TIME_SECONDS",)
EPS32 = 2.0 ** -23
SERIALIZATION_REL_TOL = 2.0e-16


class ContractError(ValueError):
    pass


def require(condition: bool, message: str) -> None:
    if not condition:
        raise ContractError(message)


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def f32(x: float) -> float:
    return struct.unpack("=f", struct.pack("=f", float(x)))[0]


def bits32(x: float) -> bytes:
    return struct.pack("=f", f32(x))


def ulp32(x: float) -> float:
    value = f32(x)
    require(math.isfinite(value), "ULP calculation requires a finite value")
    # IEEE binary32 spacing is symmetric at +x/-x; use the magnitude's next value.
    magnitude = abs(value)
    raw = struct.unpack("=I", struct.pack("=f", magnitude))[0]
    require(raw < 0x7f7fffff, "ULP calculation at max finite magnitude")
    nxt = struct.unpack("=f", struct.pack("=I", raw + 1))[0]
    return float(nxt) - float(magnitude)


def parse_int(token: str, name: str, minimum: int = 0) -> int:
    require(INTEGER.fullmatch(token) is not None, f"{name}: malformed integer")
    value = int(token)
    require(value >= minimum, f"{name}: integer below minimum")
    return value


@dataclass
class EntryPacket:
    path: Path
    header: tuple[int, int, int, int, int, int]
    fields: dict[str, tuple[float, ...]]
    sha256: str
    size_bytes: int

    def pin(self) -> dict:
        return {"path": str(self.path.resolve()), "sha256": self.sha256, "size_bytes": self.size_bytes}


def read_records(lines: list[str], label: str) -> dict[str, tuple[float, ...]]:
    fields = {}
    pos = 0
    while pos < len(lines):
        parts = lines[pos].split()
        pos += 1
        require(len(parts) == 2 and FIELD_NAME.fullmatch(parts[0]) is not None,
                f"{label}: malformed field header")
        name = parts[0]
        require(name not in fields, f"{label}: duplicate field {name}")
        count = parse_int(parts[1], f"{label}/{name} count", 1)
        require(count <= 1_000_000, f"{label}/{name}: excessive field count")
        values = []
        while len(values) < count:
            require(pos < len(lines), f"{label}/{name}: truncated values")
            tokens = lines[pos].split()
            pos += 1
            require(bool(tokens), f"{label}/{name}: empty value row")
            try:
                values.extend(float(t.replace("D", "E").replace("d", "e")) for t in tokens)
            except ValueError as exc:
                raise ContractError(f"{label}/{name}: malformed numeric value") from exc
            require(len(values) <= count, f"{label}/{name}: excess values")
            require(all(math.isfinite(x) for x in values), f"{label}/{name}: nonfinite value")
        fields[name] = tuple(values)
    return fields


def one(fields: dict[str, tuple[float, ...]], name: str) -> float:
    require(name in fields and len(fields[name]) == 1, f"missing/non-scalar {name}")
    return fields[name][0]


def integer_scalar(fields: dict[str, tuple[float, ...]], name: str) -> int:
    value = one(fields, name)
    require(value.is_integer(), f"{name}: expected integer-valued scalar")
    return int(value)


def source_density_checks(fields: dict[str, tuple[float, ...]], label: str, kts: int) -> list[dict]:
    n = len(fields["T_K"])
    rd, rv = one(fields, "RD_J_KG_K"), one(fields, "RV_J_KG_K")
    require(rd != rv, f"{label}: RD and RV must differ, matching writer guard")
    rows = []
    gamma8 = (8.0 * EPS32) / (1.0 - 8.0 * EPS32)
    for idx in range(n):
        th = fields["TH_K"][idx]
        pii = fields["PII"][idx]
        temp = fields["T_K"][idx]
        pressure = fields["P_PA"][idx]
        qv = fields["QV_MIXING_RATIO_KG_KG"][idx]
        rho = fields["DEN_PASSED_KG_M3"][idx]
        dend = fields["DEND_REEVALUATED_PRECALL_KG_M3"][idx]
        require(pressure > 0. and temp > 0. and rho > 0.,
                f"{label}: P/T/DEN must be positive at zero-based level {idx}")

        # This is the exact source default-REAL operation: temperature=th*pii.
        temp_native = f32(th * pii)
        require(abs(temp-temp_native) <= 0.5*ulp32(temp) + SERIALIZATION_REL_TOL*abs(temp),
                f"{label}: TH*PII source relation mismatch at level {idx}")

        # Reevaluate the exact source expression in binary64 and also simulate its
        # default-REAL operation sequence. The gamma bound is derived from the
        # expression's finite operation count and conditioning, not tuned to data.
        term_p = pressure / temp
        term_rv = rho * rv
        denom = rd - rv
        dend64 = (term_p - term_rv) / denom
        dend32 = f32(f32(f32(term_p) - f32(term_rv)) / f32(denom))
        round_bound = gamma8 * (abs(term_p) + abs(term_rv) + abs(dend64*denom)) / abs(denom)
        round_bound += 0.5*ulp32(dend) + SERIALIZATION_REL_TOL*abs(dend)
        require(abs(dend-dend64) <= round_bound,
                f"{label}: DEND source expression exceeds derived default-REAL bound at level {idx}")
        require(abs(dend-dend32) <= ulp32(dend) + SERIALIZATION_REL_TOL*abs(dend),
                f"{label}: DEND differs from default-REAL source-operation simulation at level {idx}")

        eos_dry = None
        eos_total = None
        eos_denominator = temp * (rd + rv*qv)
        if math.isfinite(eos_denominator) and eos_denominator != 0.:
            eos_dry = pressure / eos_denominator
            eos_total = eos_dry * (1. + qv)
            if not math.isfinite(eos_dry) or not math.isfinite(eos_total):
                eos_dry = eos_total = None
        rows.append({
            "native_level_index": idx,
            "native_k": kts + idx,
            "P_PA": pressure,
            "T_K": temp,
            "QV_MIXING_RATIO_KG_KG": qv,
            "DEN_PASSED_KG_M3": rho,
            "DEND_REEVALUATED_PRECALL_KG_M3": dend,
            "DEND_binary64_source_expression": dend64,
            "DEND_default_REAL_simulation": dend32,
            "DEND_source_expression_abs_residual": abs(dend-dend64),
            "DEND_source_expression_derived_bound": round_bound,
            "EOS_dry_density_conditional_kg_m3": eos_dry,
            "EOS_total_density_conditional_kg_m3": eos_total,
            "passed_DEN_minus_conditional_EOS_total_kg_m3": (rho-eos_total if eos_total is not None else None),
            "passed_DEN_minus_conditional_EOS_total_relative": ((rho-eos_total)/eos_total if eos_total not in (None,0.) else None),
            "passed_DEN_minus_conditional_EOS_dry_kg_m3": (rho-eos_dry if eos_dry is not None else None),
            "passed_DEN_minus_conditional_EOS_dry_relative": ((rho-eos_dry)/eos_dry if eos_dry not in (None,0.) else None),
            "DEND_minus_conditional_EOS_dry_kg_m3": (dend-eos_dry if eos_dry is not None else None),
            "DEND_minus_conditional_EOS_dry_relative": ((dend-eos_dry)/eos_dry if eos_dry not in (None,0.) else None),
            "interpretation": "diagnostic comparison only; EOS dry/gas-total convention is conditional, not a physical acceptance test",
        })
    return rows


def parse_entry(path: Path) -> EntryPacket:
    require(not path.is_symlink(), f"{path.name}: symlink packet rejected")
    data = path.read_bytes()
    try:
        lines = data.decode("ascii").splitlines()
    except UnicodeDecodeError as exc:
        raise ContractError(f"{path.name}: packet is not ASCII") from exc
    require(len(lines) >= 2, f"{path.name}: missing magic/header")
    require(lines[0] == MAGIC, f"{path.name}: wrong magic")
    name_match = ENTRY_NAME.fullmatch(path.name)
    require(name_match is not None, f"{path.name}: invalid packet filename")
    h = lines[1].split()
    require(len(h) == 6, f"{path.name}: expected six-integer header")
    domain, step, i, j, kts, kte = [parse_int(v, f"{path.name} header") for v in h]
    require(domain >= 1 and i >= 1 and j >= 1 and kts >= 1 and kte >= kts,
            f"{path.name}: invalid identity or vertical bounds")
    require((domain, i, j, step) == tuple(map(int, name_match.groups())),
            f"{path.name}: filename/header identity mismatch")
    fields = read_records(lines[2:], path.name)
    expected = set(VECTOR_FIELDS + SCALAR_FIELDS)
    present = integer_scalar(fields, "SOURCE_TIME_PRESENT") if "SOURCE_TIME_PRESENT" in fields else None
    require(present in (0, 1), f"{path.name}: SOURCE_TIME_PRESENT must be 0 or 1")
    expected_fields = expected | ({"SOURCE_TIME_SECONDS"} if present == 1 else set())
    require(set(fields) == expected_fields,
            f"{path.name}: field roster mismatch; missing={sorted(expected_fields-set(fields))}, extra={sorted(set(fields)-expected_fields)}")
    nlevels = kte-kts+1
    for key in VECTOR_FIELDS:
        require(len(fields[key]) == nlevels, f"{path.name}: {key} count does not equal kte-kts+1")
    for key in SCALAR_FIELDS + OPTIONAL_SCALARS:
        if key in fields:
            require(len(fields[key]) == 1, f"{path.name}: {key} must be scalar")
    require(one(fields, "DEND_ORIGIN") == 1.0,
            f"{path.name}: DEND_ORIGIN must be exactly 1 (explicit pre-call reevaluation)")
    require(integer_scalar(fields, "DEFAULT_REAL_BITS") == 32,
            f"{path.name}: DEFAULT_REAL_BITS must be exactly 32")
    if present:
        require(one(fields, "SOURCE_TIME_SECONDS") >= 0., f"{path.name}: negative source clock")
    return EntryPacket(path, (domain, step, i, j, kts, kte), fields, digest(data), len(data))


def load_radius_parser():
    parser_path = Path(__file__).with_name("test_udm_radius_stage.py")
    require(parser_path.is_file(), "sibling test_udm_radius_stage.py is required for post-radius joins")
    spec = importlib.util.spec_from_file_location("_udm_radius_stage_for_density_join", parser_path)
    require(spec is not None and spec.loader is not None, "cannot load sibling radius-stage parser")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


def family_raw_paths(directory: Path, prefix: str) -> list[Path]:
    # Captures share one directory across entry, post-radius and radiation packets.
    # Select this family only; any malformed name beginning with its prefix still
    # reaches the strict family parser and is rejected.
    return sorted(p for p in directory.glob("*.raw") if p.name.startswith(prefix))


def inspect(entry_dir: Path, producer_dir: Path | None = None) -> dict:
    require(entry_dir.is_dir(), f"entry directory missing: {entry_dir}")
    raw_paths = family_raw_paths(entry_dir, "udm_entry_density")
    require(raw_paths, "entry directory contains no UDM entry-density packets")
    packets = [parse_entry(p) for p in raw_paths]
    by_key = {}
    for p in packets:
        d,s,i,j,kts,kte=p.header
        key=(d,i,j,s)
        require(key not in by_key, f"duplicate entry-density identity {key}")
        by_key[key]=p

    source_root=Path(__file__).resolve().parents[3]
    trace_source=source_root/"WRF/phys/module_ra_rrtmgp_trace.F"
    report={"schema":"UDM_ENTRY_DENSITY_CONTRACT_V1","status":"ENTRY_DENSITY_DIAGNOSTIC_CONTRACT_CHECKED",
        "scope":"Validates the emitted call-entry packet, exact source-equation diagnostics and optional same-call post-radius identity/time/DEN join. No physical density or gas-mixture accuracy claim.",
        "source_pins":{"trace_writer":{"path":"WRF/phys/module_ra_rrtmgp_trace.F","sha256":digest(trace_source.read_bytes())},
                       "radius_stage_parser":{"path":"WRF/test/rrtmgp/test_udm_radius_stage.py","sha256":digest(Path(__file__).with_name("test_udm_radius_stage.py").read_bytes())}},
        "packet_count":len(packets),"entry_packets":[],"post_radius_joins":[],"model_build_solver_calls":0}
    for p in packets:
        _,step,i,j,kts,kte=p.header
        present=integer_scalar(p.fields,"SOURCE_TIME_PRESENT")
        rows=source_density_checks(p.fields,p.path.name,p.header[4])
        report["entry_packets"].append({"identity":{"domain":p.header[0],"step":step,"i":i,"j":j,"kts":kts,"kte":kte},
            "pin":p.pin(),"source_time_present":present,"source_time_seconds":one(p.fields,"SOURCE_TIME_SECONDS") if present else None,
            "DEND_origin":"explicit pre-call reevaluation; not direct observation of udm2d local DEND",
            "levels":rows})
    if producer_dir is not None:
        require(producer_dir.is_dir(),f"producer directory missing: {producer_dir}")
        radius_parser=load_radius_parser()
        radius_paths=family_raw_paths(producer_dir,"udm_radius_")
        producers={}
        for path in radius_paths:
            pp=radius_parser.parse_packet(path)
            require(len(pp.header)==6,f"{path.name}: expected post-radius producer packet")
            domain,step,i,j,kts,kte=pp.header
            key=(domain,i,j,step)
            require(key not in producers,f"duplicate post-radius producer identity {key}")
            producers[key]=pp
        require(set(producers)==set(by_key),f"entry/producer key roster mismatch; missing={sorted(set(by_key)-set(producers))}, extra={sorted(set(producers)-set(by_key))}")
        joins=[]
        for key in sorted(by_key):
            ep=by_key[key]; pp=producers[key]
            require(ep.header[4:6]==pp.header[4:6],f"{key}: entry/post-radius level bounds differ")
            require(integer_scalar(ep.fields,"SOURCE_TIME_PRESENT")==1,f"{key}: exact join requires entry clock")
            require(radius_parser.scalar(pp,"SOURCE_TIME_PRESENT",True)==1,f"{key}: exact join requires post-radius clock")
            entry_time=one(ep.fields,"SOURCE_TIME_SECONDS")
            producer_time=radius_parser.scalar(pp,"SOURCE_TIME_SECONDS")
            require(entry_time==producer_time,f"{key}: entry/post-radius time mismatch")
            entry_den=ep.fields["DEN_PASSED_KG_M3"]
            producer_den=pp.fields["SOURCE_RHO"]
            require(len(entry_den)==len(producer_den),f"{key}: DEN vector length mismatch")
            require(all(bits32(a)==bits32(b) for a,b in zip(entry_den,producer_den)),f"{key}: DEN changed across native UDM call")
            shared=(('T_K','SOURCE_T'),('QC_RAW','SOURCE_QC'),('QI_RAW','SOURCE_QI'),('QS_RAW','SOURCE_QS'),('NC_RAW','SOURCE_QNC'))
            changes={a:sum(bits32(x)!=bits32(y) for x,y in zip(ep.fields[a],pp.fields[b])) for a,b in shared}
            joins.append({"identity":{"domain":key[0],"i":key[1],"j":key[2],"step":key[3]},
                "entry_pin":ep.pin(),"post_radius_pin":{"path":str(pp.path.resolve()),"sha256":pp.sha256,"size_bytes":pp.size},
                "time_seconds_exact":entry_time,"same_call_key_exact":True,"DEN_unchanged_binary32":True,
                "post_update_shared_state_changed_layers_reported_not_required_equal":changes})
        report["post_radius_joins"]=joins
        report["join_count"]=len(joins)
        report["producer_parser_source_sha256"]=digest(Path(__file__).with_name("test_udm_radius_stage.py").read_bytes())
    # Reject concurrent edits between parsing and report generation.
    for p in packets:
        require(digest(p.path.read_bytes())==p.sha256,f"{p.path.name}: changed during inspection")
    require(sorted(x.name for x in family_raw_paths(entry_dir,"udm_entry_density"))==sorted(p.path.name for p in packets),"entry packet-family roster changed during inspection")
    return report


def format_packet(path: Path, magic: str, header: str, fields: dict[str,list[float]]) -> None:
    lines=[magic,header]
    for name,values in fields.items():
        lines.append(f"{name} {len(values)}")
        lines.extend(f"{x:.16E}" for x in values)
    path.write_text("\n".join(lines)+"\n",encoding="ascii")


def manufactured_entry(directory: Path, *, name="udm_entry_density_d1_i3_j4_step10.raw", magic=MAGIC,
                        qv=(0.01,-0.001), rho=(1.1,0.9), bad_t=False, bad_dend=False, origin=1.0, present=1, time=600.0):
    th=[1.0,1.1]; pii=[280.0,270.0]
    t=[f32(a*b) for a,b in zip(th,pii)]
    if bad_t: t[0]+=0.5
    p=[90000.0,80000.0]; rho=list(rho)
    rd,rv=f32(287.0),f32(461.0)
    dend=[]
    for pp,tt,rr in zip(p,t,rho):
        dend.append(f32((f32(f32(pp/tt)-f32(rr*rv)))/f32(rd-rv)))
    if bad_dend: dend[0]+=0.1
    fields={
      "TH_K":th,"PII":pii,"T_K":t,"P_PA":p,"QV_MIXING_RATIO_KG_KG":list(qv),
      "DEN_PASSED_KG_M3":rho,"DEND_REEVALUATED_PRECALL_KG_M3":dend,
      "QC_RAW":[-1.e-5,2.e-4],"QI_RAW":[0.,0.],"QR_RAW":[0.,0.],"QS_RAW":[0.,0.],
      "QG_RAW":[0.,0.],"QH_RAW":[0.,0.],"NN_RAW":[0.,0.],"NC_RAW":[1.e8,2.e8],"NR_RAW":[0.,0.],
      "RD_J_KG_K":[rd],"RV_J_KG_K":[rv],"CPD_J_KG_K":[1004.],"CPV_J_KG_K":[1850.],
      "GRAVITY_M_S2":[9.81],"DELT_SECONDS":[60.],"QMIN":[1.e-12],"T0C_K":[273.15],
      "RHO0_KG_M3":[1.2],"RHO_WATER_KG_M3":[1000.],"DEND_ORIGIN":[origin],
      "DEFAULT_REAL_BITS":[32.],"SOURCE_TIME_PRESENT":[float(present)]}
    if present: fields["SOURCE_TIME_SECONDS"]=[time]
    format_packet(directory/name,magic,"1 10 3 4 1 2",fields)
    return directory/name


def make_producer(directory: Path, *, step=10, time=600.0, rho=(1.1,0.9)) -> Path:
    from importlib.util import spec_from_file_location
    radius_path=Path(__file__).with_name("test_udm_radius_stage.py")
    spec=spec_from_file_location("_udm_radius_stage_fixture",radius_path)
    mod=importlib.util.module_from_spec(spec);sys.modules[spec.name]=mod;spec.loader.exec_module(mod)
    t=[280.,297.]
    fields={n:[0.,0.] for n in mod.PRODUCER_VECTORS}
    fields.update(SOURCE_T=t,SOURCE_QC=[1.e-4,2.e-4],SOURCE_QI=[0.,0.],SOURCE_QS=[0.,0.],
        SOURCE_QNC=[1.e8,2.e8],SOURCE_RHO=list(rho),SOURCE_RE_CLOUD=[8.e-6,9.e-6],
        SOURCE_RE_ICE=[2.e-5,3.e-5],SOURCE_RE_SNOW=[4.e-5,5.e-5],UDM_CF_USED=[0.,0.])
    fields.update({n:[v] for n,v in {"UDM_CF_STEP":step,"UDM_CF_TOP":2,"QMIN":1.e-12,"T0C":273.15,
      "RHO_WATER":1000.,"RHO_SNOW":100.,"SOURCE_TIME_PRESENT":1,"SOURCE_TIME_SECONDS":time}.items()})
    path=directory/f"udm_radius_d1_i3_j4_step{step}.raw"
    format_packet(path,"RRTMGP_UDM_RADIUS_V1",f"1 {step} 3 4 1 2",fields)
    return path


class EntryDensityControls(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(prefix="udm-entry-density-")
        self.root=Path(self.tmp.name);self.entries=self.root/"entry";self.producers=self.root/"producer"
        self.entries.mkdir();self.producers.mkdir()

    def tearDown(self): self.tmp.cleanup()

    def test_valid_moist_and_eos_metrics(self):
        manufactured_entry(self.entries)
        report=inspect(self.entries)
        self.assertEqual(report["packet_count"],1)
        self.assertIsNotNone(report["entry_packets"][0]["levels"][0]["EOS_dry_density_conditional_kg_m3"])

    def test_dry_and_negative_qv_are_diagnostic_inputs(self):
        manufactured_entry(self.entries,qv=(0.,-0.001))
        report=inspect(self.entries)
        self.assertEqual(report["packet_count"],1)
        self.assertLess(report["entry_packets"][0]["levels"][1]["QV_MIXING_RATIO_KG_KG"],0.)

    def test_valid_negative_dend_is_not_rejected(self):
        manufactured_entry(self.entries,rho=(0.5,0.9))
        report=inspect(self.entries)
        self.assertLess(report["entry_packets"][0]["levels"][0]["DEND_REEVALUATED_PRECALL_KG_M3"],0.)

    def test_malformed_entry_family_name_rejected(self):
        p=manufactured_entry(self.entries)
        (self.entries/"udm_entry_density_broken.raw").write_bytes(p.read_bytes())
        with self.assertRaisesRegex(ContractError,"invalid packet filename"): inspect(self.entries)

    def test_mixed_capture_directory_families_join(self):
        manufactured_entry(self.entries)
        make_producer(self.entries)
        (self.entries/"lw_2.raw").write_text("radiation placeholder\n",encoding="ascii")
        report=inspect(self.entries,self.entries)
        self.assertEqual(report["packet_count"],1)
        self.assertEqual(report["join_count"],1)

    def test_wrong_magic(self):
        manufactured_entry(self.entries,magic="WRONG")
        with self.assertRaisesRegex(ContractError,"wrong magic"): inspect(self.entries)

    def test_filename_header_identity(self):
        manufactured_entry(self.entries).write_text(manufactured_entry(self.entries).read_text().replace("1 10 3 4 1 2","1 11 3 4 1 2"))
        with self.assertRaisesRegex(ContractError,"identity mismatch"): inspect(self.entries)

    def test_vector_shape(self):
        p=manufactured_entry(self.entries)
        lines=p.read_text().splitlines()
        index=lines.index("QC_RAW 2")
        lines[index]="QC_RAW 1"
        del lines[index+2]
        p.write_text("\n".join(lines)+"\n")
        with self.assertRaisesRegex(ContractError,"kte-kts"): inspect(self.entries)

    def test_nonfinite_rejected(self):
        p=manufactured_entry(self.entries)
        lines=p.read_text().splitlines()
        index=lines.index("P_PA 2")
        lines[index+1]="NaN"
        p.write_text("\n".join(lines)+"\n")
        with self.assertRaisesRegex(ContractError,"nonfinite"): inspect(self.entries)

    def test_dend_origin_must_identify_reevaluation(self):
        manufactured_entry(self.entries,origin=0.)
        with self.assertRaisesRegex(ContractError,"DEND_ORIGIN"): inspect(self.entries)

    def test_default_real_bits_must_be_32(self):
        p=manufactured_entry(self.entries)
        lines=p.read_text().splitlines()
        index=lines.index("DEFAULT_REAL_BITS 1")
        lines[index+1]="6.4000000000000000E+01"
        p.write_text("\n".join(lines)+"\n")
        with self.assertRaisesRegex(ContractError,"DEFAULT_REAL_BITS"): inspect(self.entries)

    def test_th_pii_source_equation(self):
        manufactured_entry(self.entries,bad_t=True)
        with self.assertRaisesRegex(ContractError,r"TH\*PII"): inspect(self.entries)

    def test_dend_source_equation(self):
        manufactured_entry(self.entries,bad_dend=True)
        with self.assertRaisesRegex(ContractError,"DEND source expression"): inspect(self.entries)

    def test_clock_presence_metadata(self):
        p=manufactured_entry(self.entries,present=0)
        p.write_text(p.read_text()+"SOURCE_TIME_SECONDS 1\n6.0000000000000000E+002\n")
        with self.assertRaisesRegex(ContractError,"field roster mismatch"): inspect(self.entries)

    def test_same_call_join_exact_clock_and_den(self):
        manufactured_entry(self.entries);make_producer(self.producers)
        report=inspect(self.entries,self.producers)
        self.assertEqual(report["join_count"],1)
        self.assertTrue(report["post_radius_joins"][0]["DEN_unchanged_binary32"])

    def test_post_radius_den_change_rejected(self):
        manufactured_entry(self.entries);make_producer(self.producers,rho=(1.11,0.9))
        with self.assertRaisesRegex(ContractError,"DEN changed"): inspect(self.entries,self.producers)

    def test_post_radius_clock_change_rejected(self):
        manufactured_entry(self.entries);make_producer(self.producers,time=660.)
        with self.assertRaisesRegex(ContractError,"time mismatch"): inspect(self.entries,self.producers)

    def test_missing_post_radius_join_rejected(self):
        manufactured_entry(self.entries)
        with self.assertRaisesRegex(ContractError,"roster mismatch"): inspect(self.entries,self.producers)

    def test_duplicate_entry_identity_rejected(self):
        p=manufactured_entry(self.entries)
        dup=self.entries/"udm_entry_density_d1_i3_j4_step010.raw"
        dup.write_bytes(p.read_bytes())
        with self.assertRaisesRegex(ContractError,"duplicate entry-density identity"): inspect(self.entries)

    def test_duplicate_post_radius_identity_rejected(self):
        manufactured_entry(self.entries);p=make_producer(self.producers)
        dup=self.producers/"udm_radius_d1_i3_j4_step010.raw";dup.write_bytes(p.read_bytes())
        with self.assertRaisesRegex((ContractError,ValueError),"duplicate post-radius producer identity|filename/header identity mismatch"):
            inspect(self.entries,self.producers)


def main() -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--self-test",action="store_true",help="manufactured raw-packet checks only")
    ap.add_argument("--entry-dir",type=Path)
    ap.add_argument("--producer-dir",type=Path)
    ap.add_argument("--output",type=Path)
    args=ap.parse_args()
    if args.self_test:
        suite=unittest.defaultTestLoader.loadTestsFromTestCase(EntryDensityControls)
        result=unittest.TextTestRunner(verbosity=2).run(suite)
        return 0 if result.wasSuccessful() else 1
    if args.entry_dir is None: ap.error("--entry-dir required outside --self-test")
    try:
        report=inspect(args.entry_dir,args.producer_dir)
        payload=json.dumps(report,indent=2,sort_keys=True,allow_nan=False)+"\n"
        if args.output:
            with args.output.open("x",encoding="utf-8") as f: f.write(payload)
        else: print(payload,end="")
        return 0
    except (OSError,ValueError,OverflowError) as exc:
        print(f"UDM_ENTRY_DENSITY_ERROR: {exc}",file=sys.stderr)
        return 1


if __name__=="__main__":
    sys.dont_write_bytecode=True
    raise SystemExit(main())
