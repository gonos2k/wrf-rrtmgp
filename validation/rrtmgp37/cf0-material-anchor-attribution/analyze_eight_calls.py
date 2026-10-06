#!/usr/bin/env python3
"""Recompute four paired response profiles from preserved material-anchor outputs.

Uses NumPy and the repository's audit-capable compare_column_replay parser.
No solver or build is invoked. Independent numerical validation is recorded
separately in continuation-v3/receipts/independent-terminal-review-v4.json.
"""
from __future__ import annotations
import gzip
import hashlib
import importlib.util
import json
import math
import tempfile
from pathlib import Path
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
READER_PATH = ROOT / "WRF/test/rrtmgp/compare_column_replay.py"
EXPECTED_READER_SHA256 = "6099a3819268d3ee17bbcbaf0610c03822c09247da6ac5bdfdef66c9190533a7"
PAIRS = [
    ("winter_native_cu", "LW", "winter_native_cu-lw-baseline", "winter_native_cu-lw-rain-increment", 32),
    ("winter_native_cu", "SW", "winter_native_cu-sw-baseline", "winter_native_cu-sw-rain-increment", 32),
    ("material_cf0_snow_low_cloud", "LW", "material_cf0_snow_low_cloud-lw-baseline", "material_cf0_snow_low_cloud-lw-snow-increment", 39),
    ("material_cf0_snow_low_cloud", "SW", "material_cf0_snow_low_cloud-sw-baseline", "material_cf0_snow_low_cloud-sw-snow-increment", 39),
]
RESPONSE = {"UP", "DN", "HR", "UPC", "DNC", "HRC", "DIRECT", "DIFFUSE", "VISDIR", "VISDIF", "NIRDIR", "NIRDIF", "TOTAL_TAU", "TOTAL_SSA", "TOTAL_G", "WRF_GLW", "WRF_OLR", "WRF_GSW", "WRF_SWDDIR", "WRF_SWDDIF"}
PROFILE = {"UP", "DN", "HR", "UPC", "DNC", "HRC", "DIRECT", "DIFFUSE", "VISDIR", "VISDIF", "NIRDIR", "NIRDIF", "WRF_GLW", "WRF_OLR", "WRF_GSW", "WRF_SWDDIR", "WRF_SWDDIF"}


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def parser():
    b = READER_PATH.read_bytes()
    if sha(b) != EXPECTED_READER_SHA256:
        raise RuntimeError(f"audit-capable reader pin mismatch: {READER_PATH}")
    spec = importlib.util.spec_from_file_location("cf0_material_result_reader", READER_PATH)
    if spec is None or spec.loader is None:
        raise RuntimeError("cannot load pinned result reader")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def package_result(call_id: str) -> Path:
    p = HERE / "partial-run-v1/results" / f"{call_id}.result.gz"
    if not p.exists():
        p = HERE / "continuation-v3/results" / f"{call_id}.result.gz"
    if not p.is_file():
        raise FileNotFoundError(call_id)
    return p


def parse_gzip(path: Path, scratch: Path, call_id: str, reader):
    raw = gzip.decompress(path.read_bytes())
    target = scratch / f"{call_id}.result"
    target.write_bytes(raw)
    parsed = reader.read_result(target)
    return raw, parsed


def be64(a: np.ndarray) -> bytes:
    return np.asarray(a, dtype=">f8").tobytes(order="F")


def main() -> None:
    reader = parser()
    profiles = []
    summaries = []
    expected_calls = {x[2] for x in PAIRS} | {x[3] for x in PAIRS}
    with tempfile.TemporaryDirectory(prefix="cf0-material-analyze-") as td:
        scratch = Path(td)
        for anchor, phase, base_id, inc_id, native_nl in PAIRS:
            bp, ip = package_result(base_id), package_result(inc_id)
            b_raw, b = parse_gzip(bp, scratch, base_id, reader)
            i_raw, inc = parse_gzip(ip, scratch, inc_id, reader)
            if (b["phase"], inc["phase"]) != (phase, phase) or (b["nc"], inc["nc"]) != (1, 1) or b["nl"] != inc["nl"]:
                raise ValueError(f"header mismatch for {anchor}/{phase}")
            if native_nl > b["nl"]:
                raise ValueError(f"native prefix exceeds engine levels for {anchor}/{phase}")
            names_b, names_i = set(b["sections"]), set(inc["sections"])
            if phase == "LW":
                expected_added = {"AUDIT_EXTRA_PRECIP_TAU"}
            else:
                expected_added = {"AUDIT_EXTRA_PRECIP_TAU", "AUDIT_EXTRA_PRECIP_TAU_RAW", "AUDIT_EXTRA_PRECIP_SSA", "AUDIT_EXTRA_PRECIP_G", "AUDIT_DIRECT_PREDELTA"}
            if names_i - names_b != expected_added or names_b - names_i:
                raise ValueError(f"unexpected section roster change {anchor}/{phase}: +{names_i-names_b}, -{names_b-names_i}")
            if not expected_added.issubset(names_i):
                raise ValueError(f"missing audit sections for {anchor}/{phase}")
            # All source/component inputs and clear-sky post-clear outputs are held exactly.
            held = names_b - RESPONSE
            for name in held:
                if name not in inc["sections"] or be64(b["sections"][name]) != be64(inc["sections"][name]):
                    raise ValueError(f"held section changed: {anchor}/{phase}/{name}")
            # Clear-sky outputs are explicitly retained bit-for-bit after the audit insertion.
            for name in ("UPC", "DNC", "HRC", "DIRECTC"):
                if name in b["sections"] and be64(b["sections"][name]) != be64(inc["sections"][name]):
                    raise ValueError(f"clear-sky output changed: {anchor}/{phase}/{name}")
            tau = inc["sections"]["AUDIT_EXTRA_PRECIP_TAU"]
            if not np.isfinite(tau).all() or np.min(tau) < 0 or np.max(tau) <= 0:
                raise ValueError(f"audit tau is not finite/nonnegative/positive: {anchor}/{phase}")
            response_sections = sorted((names_b & names_i) & RESPONSE)
            delta_metrics = {}
            for name in response_sections:
                a = np.asarray(b["sections"][name], dtype=np.float64)
                z = np.asarray(inc["sections"][name], dtype=np.float64)
                if a.shape != z.shape or not np.isfinite(a).all() or not np.isfinite(z).all():
                    raise ValueError(f"response shape/finite mismatch {anchor}/{phase}/{name}")
                d = z - a
                flat = d.reshape(-1, order="F")
                mx = float(np.max(np.abs(flat))) if flat.size else 0.0
                arg = int(np.argmax(np.abs(flat))) if flat.size else 0
                delta_metrics[name] = {"shape":list(a.shape),"max_abs_delta":mx,"max_abs_flat_index_F":arg}
                if name not in PROFILE:
                    continue
                level_axis = (name in {"HR", "HRC"}) or name.startswith("WRF_") and name not in {"WRF_GLW", "WRF_OLR", "WRF_GSW", "WRF_SWDDIR", "WRF_SWDDIF"}
                for idx in np.ndindex(a.shape):
                    axis = idx[1] if len(idx) > 1 else 0
                    region = "native_prefix" if axis < native_nl or (name not in {"HR","HRC"} and axis <= native_nl) else "engine_extension"
                    profiles.append({"anchor":anchor,"phase":phase,"native_levels":native_nl,"engine_levels":b["nl"],"section":name,"index_0based":list(idx),"region":region,"baseline":float(a[idx]),"increment":float(z[idx]),"delta":float(d[idx])})
            def scalar_delta(name, index):
                a=b["sections"][name];z=inc["sections"][name]
                return float(z[index]-a[index])
            hr=b["sections"]["HR"]; hid=inc["sections"]["HR"]
            hdelta=hid-hr
            summary={"anchor":anchor,"phase":phase,"baseline_call_id":base_id,"increment_call_id":inc_id,
              "baseline_result_sha256_uncompressed":sha(b_raw),"increment_result_sha256_uncompressed":sha(i_raw),
              "baseline_result_gzip_sha256":sha(bp.read_bytes()),"increment_result_gzip_sha256":sha(ip.read_bytes()),
              "nc":b["nc"],"engine_levels":b["nl"],"native_levels":native_nl,"section_roster_change_added":sorted(expected_added),
              "held_section_names":sorted(held),"held_sections_bitwise_equal":True,
              "audit_tau_max":float(np.max(tau)),"audit_tau_sum":float(np.sum(tau)),
              "metrics":{"surface_DN_delta_W_m2":scalar_delta("DN",(0,0,0)),"surface_UP_delta_W_m2":scalar_delta("UP",(0,0,0)),"TOA_UP_delta_W_m2":scalar_delta("UP",(0,b["nl"],0)),
                "HR_Linf_engine_K_day":float(np.max(np.abs(hdelta))),"HR_Linf_native_prefix_K_day":float(np.max(np.abs(hdelta[:,:native_nl,:]))),
                "HR_Linf_extension_K_day":float(np.max(np.abs(hdelta[:,native_nl:,:]))) if b["nl"]>native_nl else 0.0},
              "response_sections":delta_metrics}
            if phase=="SW":
                summary["metrics"].update({"surface_DIRECT_delta_W_m2":scalar_delta("DIRECT",(0,0,0)),"surface_DIFFUSE_delta_W_m2":scalar_delta("DIFFUSE",(0,0,0))})
            summaries.append(summary)
    summaries.sort(key=lambda x:(x['anchor'],x['phase']))
    out={"schema":"CF0_MATERIAL_ANCHOR_FOUR_PAIR_RESPONSE_SUMMARY_V1","status":"RECOMPUTED_FROM_PRESERVED_OUTPUTS; INDEPENDENT_REVIEW_PASS_SCOPED",
      "new_solver_calls_for_analysis":0,"reader":{"path":"WRF/test/rrtmgp/compare_column_replay.py","sha256":EXPECTED_READER_SHA256},
      "interpretation_scope":"Descriptive within-anchor same-phase baseline/increment response only; does not establish physical accuracy, production policy, or domain/forecast impact. Independent oracle review is separately pinned.","pairs":summaries}
    (HERE/"results").mkdir(exist_ok=True)
    (HERE/"results/pair-response-summary-v1.json").write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
    import csv
    fields=["anchor","phase","native_levels","engine_levels","section","index_0based","region","baseline","increment","delta"]
    with (HERE/"results/pair-response-profiles-v1.csv").open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(profiles)
    print(f"Recomputed {len(summaries)} paired responses and {len(profiles)} profile values from preserved outputs")

if __name__ == "__main__":
    main()
