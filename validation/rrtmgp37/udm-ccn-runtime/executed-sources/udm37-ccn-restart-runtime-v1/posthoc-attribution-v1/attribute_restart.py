#!/usr/bin/env python3
"""Read-only attribution of the preserved strict restart comparison failure."""
from __future__ import annotations

import argparse
import hashlib
import json
import struct
import sys
from pathlib import Path

import numpy as np
from netCDF4 import Dataset

ROOT = Path(__file__).resolve().parents[3]
CASES = ROOT / "build/udm37-ccn-restart-runtime-v1/cases-v1"
STRICT = CASES / "comparison.json"
BASE = ROOT / "build/udm37-ccn-tile-init-gnu-v1/source/WRF"
ALLOWED_DIAGNOSTICS = ("UDM_CLDFRA", "UDM_CF_STEP", "UDM_CF_TOP")
ALARM = "WRF_ALARM_SECS_TIL_NEXT_RING_55"


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for block in iter(lambda: f.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def raw(a) -> bytes:
    return np.ascontiguousarray(a).tobytes(order="C")


def atom(x):
    if isinstance(x, np.ndarray):
        return {"dtype": x.dtype.str, "shape": list(x.shape), "hex": raw(x).hex()}
    if isinstance(x, np.generic):
        return {"dtype": x.dtype.str, "hex": np.asarray(x).tobytes().hex()}
    if isinstance(x, bytes):
        return {"bytes_hex": x.hex()}
    return x


def attrs_equal(a, b) -> bool:
    return set(a.ncattrs()) == set(b.ncattrs()) and all(
        atom(a.getncattr(k)) == atom(b.getncattr(k)) for k in a.ncattrs()
    )


def dims_equal(a, b) -> bool:
    return tuple(a.dimensions) == tuple(b.dimensions)


def array_at(v, index=None):
    v.set_auto_maskandscale(False)
    if index is None:
        return np.asarray(v[:])
    return np.asarray(v[index])


def eq_at(a, b, ia=None, ib=None):
    av, bv = array_at(a, ia), array_at(b, ib)
    return av.dtype == bv.dtype and av.shape == bv.shape and raw(av) == raw(bv)


def file_pin(path: Path):
    return {"path": str(path), "sha256": sha(path), "size_bytes": path.stat().st_size}


def text_times(ds):
    v = ds.variables["Times"]
    v.set_auto_maskandscale(False)
    return [b"".join(row.tolist()).decode("ascii").rstrip("\x00 ") for row in v[:]]


def assert_same_var_contract(a, b, name):
    if a.dtype != b.dtype or not dims_equal(a, b) or not attrs_equal(a, b):
        raise AssertionError(f"variable contract differs: {name}")


def compare_history_pair(candidate: Path, continuous: Path):
    findings = {"initial_15": {}, "final_16": {}}
    with Dataset(candidate) as c, Dataset(continuous) as r:
        ct, rt = text_times(c), text_times(r)
        if ct != ["2000-01-24_15:00:00", "2000-01-24_16:00:00"]:
            raise AssertionError(f"restart history times unexpected: {ct}")
        if rt != ["2000-01-24_12:00:00", "2000-01-24_13:00:00", "2000-01-24_14:00:00", "2000-01-24_15:00:00", "2000-01-24_16:00:00"]:
            raise AssertionError(f"continuous history times unexpected: {rt}")
        if set(c.variables) != set(r.variables) or len(c.variables) != 225:
            raise AssertionError("history variable set/count mismatch")
        for name, cv in c.variables.items():
            rv = r.variables[name]
            assert_same_var_contract(cv, rv, name)
            # Restart record 0 is continuous record 3; record 1 is record 4.
            if eq_at(cv, rv, 1, 4):
                findings["final_16"][name] = "exact"
            else:
                raise AssertionError(f"non-exact 16:00 history field: {name}")
            if eq_at(cv, rv, 0, 3):
                findings["initial_15"][name] = "exact"
            elif name in ALLOWED_DIAGNOSTICS:
                cv0 = array_at(cv, 0)
                if not np.all(cv0 == -1):
                    raise AssertionError(f"restart reset value not -1: {name}")
                findings["initial_15"][name] = {
                    "expected_reset": -1,
                    "candidate_dtype": cv0.dtype.str,
                    "candidate_shape": list(cv0.shape),
                    "continuous_raw_sha256": hashlib.sha256(raw(array_at(rv, 3))).hexdigest(),
                    "candidate_raw_sha256": hashlib.sha256(raw(cv0)).hexdigest(),
                }
            else:
                raise AssertionError(f"unexpected 15:00 difference: {name}")
        if sum(v == "exact" for v in findings["initial_15"].values()) != 222:
            raise AssertionError("15:00 exact-variable count is not 222")
        if set(k for k, v in findings["initial_15"].items() if v != "exact") != set(ALLOWED_DIAGNOSTICS):
            raise AssertionError("15:00 reset-diagnostic set mismatch")
        if sum(v == "exact" for v in findings["final_16"].values()) != 225:
            raise AssertionError("16:00 exact-variable count is not 225")
        if not attrs_equal(c, r):
            # The strict report identifies START_DATE as the only history global difference.
            diffs = {k for k in set(c.ncattrs()) | set(r.ncattrs())
                     if k not in c.ncattrs() or k not in r.ncattrs()
                     or atom(c.getncattr(k)) != atom(r.getncattr(k))}
            if diffs != {"START_DATE"}:
                raise AssertionError(f"unexpected history global attributes: {sorted(diffs)}")
    return findings


def attr_alarm(ds):
    v = ds.getncattr(ALARM)
    a = np.asarray(v)
    if a.size != 1 or a.dtype.kind not in "iu":
        raise AssertionError(f"alarm attribute is not an integer scalar: {atom(v)}")
    return int(a.reshape(-1)[0]), atom(v)


def compare_checkpoint(candidate: Path, continuous: Path):
    with Dataset(candidate) as c, Dataset(continuous) as r:
        if c.data_model != r.data_model or set(c.dimensions) != set(r.dimensions):
            raise AssertionError("checkpoint data model/dimensions mismatch")
        if set(c.variables) != set(r.variables) or len(c.variables) != 664:
            raise AssertionError("checkpoint variable set/count mismatch")
        for name, cv in c.variables.items():
            rv = r.variables[name]
            assert_same_var_contract(cv, rv, name)
            if not eq_at(cv, rv):
                raise AssertionError(f"non-exact checkpoint variable: {name}")
        diff = {k for k in set(c.ncattrs()) | set(r.ncattrs())
                if k not in c.ncattrs() or k not in r.ncattrs()
                or atom(c.getncattr(k)) != atom(r.getncattr(k))}
        if diff != {"START_DATE", ALARM}:
            raise AssertionError(f"unexpected checkpoint global attribute differences: {sorted(diff)}")
        alarm_c, alarm_c_repr = attr_alarm(c)
        alarm_r, alarm_r_repr = attr_alarm(r)
        if (alarm_c, alarm_r) != (-3600, -14400):
            raise AssertionError(f"unexpected alarm countdown values: candidate={alarm_c}, continuous={alarm_r}")
        return {"exact_variables": 664, "global_attribute_differences": sorted(diff),
                "candidate_alarm_seconds": alarm_c, "continuous_alarm_seconds": alarm_r,
                "candidate_alarm_raw": alarm_c_repr, "continuous_alarm_raw": alarm_r_repr}


def source_evidence():
    files = {
        "registry": BASE / "Registry/registry.rrtmgp37",
        "physics_init": BASE / "phys/module_physics_init.F",
        "alarm_definition": BASE / "frame/module_streams.f90",
        "alarm_disable": BASE / "share/set_timekeeping.f90",
    }
    lines = {}
    for key, p in files.items():
        lines[key] = {"path": str(p), "sha256": sha(p)}
    return {
        "files": lines,
        "citations": {
            "registry": "registry.rrtmgp37:3-5 (h-only; no restart I/O flag)",
            "physics_init": "module_physics_init.F:1164-1177 (initializes associated UDM diagnostics to -1)",
            "alarm_definition": "module_streams.f90:133-135 (alarm index 55 is COMPUTE_VORTEX_CENTER_ALARM)",
            "alarm_disable": "set_timekeeping.f90:4387-4390 (WRFU_AlarmDisable on COMPUTE_VORTEX_CENTER_ALARM)",
        },
    }


def build_report():
    strict_before = sha(STRICT)
    strict = json.loads(STRICT.read_text())
    if strict.get("status") != "FAIL_PRESERVED":
        raise AssertionError("original strict comparison is absent or no longer preserved as FAIL")
    strict_pairs = strict.get("pairs", [])
    if len(strict_pairs) != 7:
        raise AssertionError("strict comparison pair ledger changed")
    arms = {}
    for arm in ("restart-omp1", "restart-omp2"):
        d = CASES / arm
        h = d / "wrfout_d01_2000-01-24_15:00:00"
        cp = d / "wrfrst_d01_2000-01-24_16:00:00"
        cont = CASES / "continuous-omp2"
        ch = cont / "wrfout_d01_2000-01-24_12:00:00"
        cr = cont / "wrfrst_d01_2000-01-24_16:00:00"
        # Continuous history is one multi-record file in this case; select directly.
        hist_file = cont / "wrfout_d01_2000-01-24_12:00:00"
        arms[arm] = {
            "history_candidate": file_pin(h),
            "history_continuous": file_pin(hist_file),
            "history": compare_history_pair(h, hist_file),
            "checkpoint_candidate": file_pin(cp),
            "checkpoint_continuous": file_pin(cr),
            "checkpoint": compare_checkpoint(cp, cr),
        }
        hp = [p for p in strict_pairs if p.get("kind") == "restart-history-vs-continuous-15-16" and p.get("arm") == arm]
        rp = [p for p in strict_pairs if p.get("kind") == "restart-checkpoint-vs-continuous-16" and p.get("arm") == arm]
        if len(hp) != 1 or len(rp) != 1:
            raise AssertionError(f"strict ledger lacks unique restart pair for {arm}")
        if hp[0]["candidate"]["sha256"] != arms[arm]["history_candidate"]["sha256"]:
            raise AssertionError(f"strict history candidate pin mismatch for {arm}")
        if hp[0]["continuous"]["sha256"] != arms[arm]["history_continuous"]["sha256"]:
            raise AssertionError(f"strict continuous history pin mismatch for {arm}")
        if rp[0]["candidate"]["sha256"] != arms[arm]["checkpoint_candidate"]["sha256"]:
            raise AssertionError(f"strict checkpoint candidate pin mismatch for {arm}")
        if rp[0]["continuous"]["sha256"] != arms[arm]["checkpoint_continuous"]["sha256"]:
            raise AssertionError(f"strict continuous checkpoint pin mismatch for {arm}")
        history_diffs = sorted(k for k, v in hp[0]["variables"].items() if not v["raw_bytes_equal"])
        if history_diffs != sorted(ALLOWED_DIAGNOSTICS):
            raise AssertionError(f"strict receipt history difference set changed: {history_diffs}")
        if not rp[0]["raw_all_variables_equal"]:
            raise AssertionError("strict receipt no longer reports exact checkpoint state")
    # Ensure provenance assets did not change while readback was underway.
    if sha(STRICT) != strict_before:
        raise AssertionError("strict comparison artifact changed during read-only attribution")
    return {
        "status": "PASS_SCOPED_RESTART_STATE_WITH_INITIAL_DIAGNOSTIC_RESET",
        "scope": "posthoc attribution only; original strict comparison remains FAIL_PRESERVED",
        "strict_comparison": {"path": str(STRICT), "sha256": strict_before, "status": strict["status"]},
        "history_expected_differences": list(ALLOWED_DIAGNOSTICS),
        "history_counts": {"initial_15_exact": 222, "initial_15_reset_to_minus_one": 3,
                           "final_16_exact": 225, "variables_per_history": 225},
        "checkpoint_counts": {"all_raw_variables_exact": 664},
        "arms": arms,
        "source_basis": source_evidence(),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    if out.exists():
        print(f"refusing to overwrite {out}", file=sys.stderr)
        return 2
    report = build_report()
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.replace(out)
    print(f"{report['status']}: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
