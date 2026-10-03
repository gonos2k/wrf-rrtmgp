#!/usr/bin/env python3
"""Read-only full shared-history/final-checkpoint comparison for delayed nest."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime
from pathlib import Path

import numpy as np
from netCDF4 import Dataset, default_fillvals

ROOT = Path(__file__).resolve().parents[3]
RUNROOT = ROOT / "build/udm37-ccn-delayed-nest-runtime-v1"
CONT = RUNROOT / "continuous"
RESTART = RUNROOT / "restart"
STAGE = RUNROOT / "stage.json"
CONT_RECEIPT = CONT / "execution.json"
RST_RECEIPT = RESTART / "execution.json"
HARNESS = ROOT / "build/udm-cu-current-nest-harness-v2/nested_runtime.py"
CONT_POSTHOC = RUNROOT / "posthoc-v1/continuous-posthoc-v4.json"
CONT_OMISSION_REPORT = RUNROOT / "posthoc-omission-audit-v1/report.json"
ANALYZER = Path(__file__).resolve()
NEGATIVE_CONTROL_SCRIPT = ANALYZER.parent / "test_contract.py"
NEGATIVE_CONTROL_RESULT = ANALYZER.parent / "negative-controls-v4.json"
RESTART_ADAPTER = RUNROOT / "posthoc-v1/restart_adapter.py"
POSTHOC_VALIDATOR = RUNROOT / "posthoc-v1/posthoc_validate.py"
BUILD = ROOT / "build/udm37-ccn-tile-init-gnu-v1/source/WRF"
INITIAL_DIAGS = {"UDM_CLDFRA", "UDM_CF_TOP", "UDM_CF_STEP"}
ALARM55 = "WRF_ALARM_SECS_TIL_NEXT_RING_55"
ALARM51 = "WRF_ALARM_SECS_TIL_NEXT_RING_51"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with p.open("rb") as f:
        for block in iter(lambda: f.read(1 << 20), b""): h.update(block)
    return h.hexdigest()


def pin(p: Path):
    return {"path": str(p), "size_bytes": p.stat().st_size, "sha256": sha(p)}


def canonical(x):
    if isinstance(x, np.ndarray):
        return {"dtype": x.dtype.str, "shape": list(x.shape), "hex": np.ascontiguousarray(x).tobytes().hex()}
    if isinstance(x, np.generic):
        a = np.asarray(x)
        return {"dtype": a.dtype.str, "shape": [], "hex": a.tobytes().hex()}
    if isinstance(x, bytes): return {"python_type": "bytes", "hex": x.hex()}
    if isinstance(x, str): return {"python_type": "str", "value": x}
    if isinstance(x, (int, float, bool)): return {"python_type": type(x).__name__, "value": x}
    return x


def raw(a): return np.ascontiguousarray(a).tobytes(order="C")


def attr_map(ds): return {n: canonical(ds.getncattr(n)) for n in ds.ncattrs()}


def read_times(ds):
    v = ds.variables["Times"]
    v.set_auto_maskandscale(False)
    return [bytes(row).decode("ascii").replace("\x00", "").strip() for row in v[:]]


def expected_alarm55(domain, is_restart, timestamp):
    t = datetime.strptime(timestamp, "%Y-%m-%d_%H:%M:%S")
    if is_restart:
        start = datetime(2010, 6, 11, 1, 10)
    else:
        # The child continuous start is 01:00; parent continuous starts at 00:00.
        start = datetime(2010, 6, 11, 0 if domain == 1 else 1, 0)
    return int((start - t).total_seconds())


def scalar_int(ds, name):
    v = np.asarray(ds.getncattr(name))
    if v.size != 1 or v.dtype.kind not in "iu": raise AssertionError(f"{name} must be an integer scalar")
    return int(v.reshape(-1)[0])


def check_disabled55(ds, domain, is_restart, timestamp):
    if scalar_int(ds, "WRF_ALARM_ISRINGING_55") != 0:
        raise AssertionError("alarm 55 is expected disabled for the elapsed-anchor exception")
    expected = expected_alarm55(domain, is_restart, timestamp)
    got = scalar_int(ds, ALARM55)
    if got != expected: raise AssertionError(f"alarm55 elapsed anchor mismatch: {got} != {expected}")
    return {"seconds": got, "expected_seconds": expected, "is_ringing": 0}


def check_expected_alarm51_final(c, r):
    cv, rv = scalar_int(c, ALARM51), scalar_int(r, ALARM51)
    ci, ri = scalar_int(c, "WRF_ALARM_ISRINGING_51"), scalar_int(r, "WRF_ALARM_ISRINGING_51")
    if (cv, rv, ci, ri) != (600, 3000, 1, 1):
        raise AssertionError(f"restart alarm51 final exception invalid: {(cv, rv, ci, ri)}")
    return {"continuous_seconds": cv, "restart_seconds": rv, "continuous_is_ringing": ci, "restart_is_ringing": ri}


def numeric_quality(v):
    dtype = np.dtype(v.dtype)
    if dtype.kind not in "iuf": return None
    v.set_auto_mask(True); v.set_auto_scale(False); rawv = v[:]
    v.set_auto_maskandscale(True); decoded = v[:]
    v.set_auto_maskandscale(False)
    a = np.asarray(np.ma.getdata(rawv)); b = np.asarray(np.ma.getdata(decoded))
    fills = []
    for name in ("_FillValue", "missing_value"):
        if name in v.ncattrs(): fills.extend(np.asarray(v.getncattr(name)).reshape(-1).tolist())
    key = dtype.kind + str(dtype.itemsize)
    if key in default_fillvals: fills.append(default_fillvals[key])
    nfill = 0
    for fill in fills:
        try: nfill += int(np.count_nonzero(a == np.asarray(fill, dtype=dtype)))
        except (TypeError, ValueError, OverflowError): pass
    return {"raw_masked": int(np.ma.getmaskarray(rawv).sum()),
            "decoded_masked": int(np.ma.getmaskarray(decoded).sum()),
            "raw_nonfinite": int(np.count_nonzero(~np.isfinite(a))),
            "decoded_nonfinite": int(np.count_nonzero(~np.isfinite(b))),
            "raw_or_default_fill": nfill}


def compare_datasets(cpath: Path, rpath: Path, domain: int, timestamp: str, *, checkpoint=False):
    is_initial = timestamp == "2010-06-11_01:10:00" and not checkpoint
    result = {"domain": domain, "timestamp": timestamp, "kind": "checkpoint" if checkpoint else "history",
              "continuous": pin(cpath), "restart": pin(rpath), "expected_initial_diagnostic_resets": [],
              "variable_count": None, "exact_variable_count": 0, "initial_reset_variable_count": 0,
              "variables": [], "global_attribute_differences": [], "alarm55_elapsed": None, "alarm51_final_interval": None}
    with Dataset(cpath) as c, Dataset(rpath) as r:
        c.set_auto_maskandscale(False); r.set_auto_maskandscale(False)
        if c.data_model != r.data_model: raise AssertionError(f"data model differs: {cpath.name}/{rpath.name}")
        if {k: len(v) for k, v in c.dimensions.items()} != {k: len(v) for k, v in r.dimensions.items()}:
            raise AssertionError(f"dimension sizes differ: {cpath.name}/{rpath.name}")
        if set(c.dimensions) != set(r.dimensions): raise AssertionError("dimension name sets differ")
        if set(c.variables) != set(r.variables):
            raise AssertionError(f"variable sets differ: only continuous={sorted(set(c.variables)-set(r.variables))}; only restart={sorted(set(r.variables)-set(c.variables))}")
        if not checkpoint:
            if read_times(c) != [timestamp] or read_times(r) != [timestamp]: raise AssertionError(f"history time coordinate mismatch at {timestamp}")
        else:
            if read_times(c) != [timestamp] or read_times(r) != [timestamp]: raise AssertionError(f"checkpoint time coordinate mismatch at {timestamp}")
        cdims = {k: (v.isunlimited(), len(v)) for k, v in c.dimensions.items()}
        rdims = {k: (v.isunlimited(), len(v)) for k, v in r.dimensions.items()}
        if cdims != rdims: raise AssertionError("dimension unlimited flags differ")
        cattrs, rattrs = attr_map(c), attr_map(r)
        result["continuous_global_attributes"] = cattrs
        result["restart_global_attributes"] = rattrs
        all_attrs = set(cattrs) | set(rattrs)
        differences = sorted(n for n in all_attrs if cattrs.get(n) != rattrs.get(n))
        allowed = {"START_DATE"}
        if checkpoint: allowed.update({ALARM51, ALARM55})
        if set(differences) - allowed: raise AssertionError(f"unexpected global attribute differences: {differences}")
        for name, cv in c.variables.items():
            rv = r.variables[name]
            if cv.dtype != rv.dtype or cv.dimensions != rv.dimensions or set(cv.ncattrs()) != set(rv.ncattrs()):
                raise AssertionError(f"variable metadata mismatch: {name}")
            for an in cv.ncattrs():
                if canonical(cv.getncattr(an)) != canonical(rv.getncattr(an)):
                    raise AssertionError(f"variable attribute mismatch: {name}.{an}")
            quality_c, quality_r = numeric_quality(cv), numeric_quality(rv)
            if quality_c is not None:
                for label, quality in (("continuous", quality_c), ("restart", quality_r)):
                    if any(quality[k] != 0 for k in quality):
                        raise AssertionError(f"numeric mask/nonfinite/fill in {label} {cpath.name} {name}: {quality}")
                    bucket = result.setdefault(f"{label}_numeric_quality", {k: 0 for k in quality})
                    for k, v in quality.items(): bucket[k] += v
            cv.set_auto_maskandscale(False); rv.set_auto_maskandscale(False)
            ca = np.asarray(cv[:]); ra = np.asarray(rv[:])
            equal = ca.dtype == ra.dtype and ca.shape == ra.shape and raw(ca) == raw(ra)
            classification = "exact"
            if equal:
                result["exact_variable_count"] += 1
            elif is_initial and name in INITIAL_DIAGS:
                if not np.all(ra == -1): raise AssertionError(f"initial restart diagnostic not reset to -1: {name}")
                result["initial_reset_variable_count"] += 1
                classification = "initial_restart_reset_to_minus_one"
                result["expected_initial_diagnostic_resets"].append({"field": name, "restart_value": -1,
                    "continuous_sha256": hashlib.sha256(raw(ca)).hexdigest(), "restart_sha256": hashlib.sha256(raw(ra)).hexdigest(),
                    "continuous_shape": list(ca.shape), "dtype": ca.dtype.str})
            else:
                raise AssertionError(f"unexpected raw field mismatch {cpath.name}/{rpath.name}: {name}")
            va = {an: canonical(cv.getncattr(an)) for an in cv.ncattrs()}
            vb = {an: canonical(rv.getncattr(an)) for an in rv.ncattrs()}
            attr_digest = hashlib.sha256(json.dumps(va, sort_keys=True, separators=(",", ":")).encode()).hexdigest()
            result["variables"].append({"name": name, "dtype": ca.dtype.str, "dimensions": list(cv.dimensions),
                "shape": list(ca.shape), "continuous_raw_sha256": hashlib.sha256(raw(ca)).hexdigest(),
                "restart_raw_sha256": hashlib.sha256(raw(ra)).hexdigest(), "raw_bytes_equal": bool(equal),
                "variable_attributes_equal": va == vb, "variable_attributes_sha256": attr_digest,
                "classification": classification})
        result["variable_count"] = len(c.variables)
        expected_resets = INITIAL_DIAGS if is_initial else set()
        if set(x["field"] for x in result["expected_initial_diagnostic_resets"]) != expected_resets:
            raise AssertionError(f"initial reset mismatch set at {timestamp}/d{domain}")
        if is_initial and result["initial_reset_variable_count"] != 3: raise AssertionError("expected 3 initial diagnostic reset differences")
        if differences:
            if "START_DATE" in differences:
                exp_c = "2010-06-11_00:00:00" if domain == 1 else "2010-06-11_01:00:00"
                exp_r = "2010-06-11_01:10:00"
                if c.getncattr("START_DATE") != exp_c or r.getncattr("START_DATE") != exp_r:
                    raise AssertionError(f"unexpected START_DATE pair at d{domain}/{timestamp}")
            if ALARM55 in differences and checkpoint:
                result["alarm55_elapsed"] = {"continuous": check_disabled55(c, domain, False, timestamp),
                                              "restart": check_disabled55(r, domain, True, timestamp)}
            elif checkpoint:
                # Still confirm both disabled alarm-55 anchors at every compared file.
                result["alarm55_elapsed"] = {"continuous": check_disabled55(c, domain, False, timestamp),
                                              "restart": check_disabled55(r, domain, True, timestamp)}
            elif not checkpoint and ALARM55 in c.ncattrs() and ALARM55 in r.ncattrs():
                # If the anchor metadata is present on histories, require its
                # source-defined value even when both sides happen to match.
                check_disabled55(c, domain, False, timestamp)
                check_disabled55(r, domain, True, timestamp)
            if ALARM51 in differences:
                if not checkpoint or timestamp != "2010-06-11_02:00:00":
                    raise AssertionError("alarm 51 difference is allowed only on the final checkpoint")
                result["alarm51_final_interval"] = check_expected_alarm51_final(c, r)
            elif checkpoint:
                # Ensure matching final interval values still describe the documented active alarm state.
                if scalar_int(c, "WRF_ALARM_ISRINGING_51") != scalar_int(r, "WRF_ALARM_ISRINGING_51"):
                    raise AssertionError("alarm51 ringing state differs")
        elif checkpoint:
            result["alarm55_elapsed"] = {"continuous": check_disabled55(c, domain, False, timestamp),
                                          "restart": check_disabled55(r, domain, True, timestamp)}
        elif ALARM55 in c.ncattrs() and ALARM55 in r.ncattrs():
            check_disabled55(c, domain, False, timestamp)
            check_disabled55(r, domain, True, timestamp)
        result["global_attribute_differences"] = [{"name": n, "continuous": cattrs.get(n), "restart": rattrs.get(n)} for n in differences]
        if checkpoint and timestamp == "2010-06-11_02:00:00":
            if ALARM51 not in differences: raise AssertionError("expected documented final restart-alarm interval metadata difference")
            result["alarm51_final_interval"] = check_expected_alarm51_final(c, r)
    return result


def source_pins():
    paths = {
        "registry": BUILD / "Registry/Registry.EM_COMMON",
        "udm_registry": BUILD / "Registry/registry.rrtmgp37",
        "streams_ids": BUILD / "frame/module_streams.F",
        "streams_ids_preprocessed": BUILD / "frame/module_streams.f90",
        "timekeeping_source": BUILD / "share/set_timekeeping.F",
        "timekeeping_preprocessed": BUILD / "share/set_timekeeping.f90",
        "restart_schedule_driver": BUILD / "share/mediation_integrate.F",
        "restart_schedule_driver_preprocessed": BUILD / "share/mediation_integrate.f90",
        "history_header": BUILD / "share/output_wrf.F",
        "udm_init": BUILD / "phys/module_physics_init.F",
        "configure": BUILD / "configure.wrf",
    }
    return {k: pin(v) for k, v in paths.items()}


def namelist_scalar(path: Path, name: str):
    text = path.read_text()
    matches = re.findall(rf"(?im)^\s*{re.escape(name)}\s*=\s*([^,\s]+)", text)
    if len(matches) != 1: raise AssertionError(f"expected one {name} in {path}, found {matches}")
    return matches[0].strip().lower()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--output", type=Path, required=True)
    args = ap.parse_args()
    out = args.output.resolve()
    if out.exists(): print(f"refusing to overwrite {out}", file=sys.stderr); return 2
    fixed_files = [STAGE, CONT_RECEIPT, RST_RECEIPT, HARNESS, RESTART_ADAPTER, POSTHOC_VALIDATOR, CONT_POSTHOC, CONT_OMISSION_REPORT,
                   CONT / "namelist.input", RESTART / "namelist.input", CONT / "cu_nest_iofields.txt", ANALYZER,
                   NEGATIVE_CONTROL_SCRIPT, NEGATIVE_CONTROL_RESULT]
    before = {str(p): pin(p) for p in fixed_files}
    stage = json.loads(STAGE.read_text()); cr = json.loads(CONT_RECEIPT.read_text()); rr = json.loads(RST_RECEIPT.read_text())
    if rr.get("status") != "FAIL_PRESERVED" or rr.get("returncode") != 0 or not rr.get("all_rank_success"):
        raise AssertionError("restart receipt does not match completed failure being attributed")
    if not rr.get("continuous_outputs_unchanged") or rr.get("continuous_status_remains") != "FAIL_PRESERVED":
        raise AssertionError("restart receipt does not attest preserved continuous output run")
    if cr.get("status") != "FAIL_PRESERVED" or cr.get("returncode") != 0 or not cr.get("all_rank_success"):
        raise AssertionError("continuous receipt differs from the known helper-failed, model-success state")
    if rr.get("stage", {}).get("sha256") != sha(STAGE) or stage.get("runner", {}).get("sha256") != sha(HARNESS):
        raise AssertionError("restart receipt/stage does not bind current stage/helper")
    if rr.get("adapter", {}).get("sha256") != sha(RESTART_ADAPTER):
        raise AssertionError("restart receipt does not bind its adapter")
    if rr.get("preserved_original_continuous_execution", {}).get("sha256") != sha(CONT_RECEIPT):
        raise AssertionError("restart receipt does not bind preserved continuous receipt")
    if rr.get("posthoc_ledger", {}).get("sha256") != sha(CONT_POSTHOC) or rr.get("posthoc_validator", {}).get("sha256") != sha(POSTHOC_VALIDATOR):
        raise AssertionError("restart receipt posthoc ledger/validator provenance mismatch")
    neg = json.loads(NEGATIVE_CONTROL_RESULT.read_text())
    if neg.get("status") != "PASS" or len(neg.get("cases", [])) != 13:
        raise AssertionError("comparator negative-control suite is not a passing 13-case receipt")
    if rr.get("before_runtime_identity") != rr.get("after_runtime_identity") or not rr.get("runtime_identity_unchanged"):
        raise AssertionError("runtime identity changed between restart run pre/post pins")
    if rr.get("resolved_libraries_before") != rr.get("resolved_libraries_after") or not rr.get("resolved_libraries_unchanged"):
        raise AssertionError("resolved runtime library pins changed around restart")
    if sha(CONT / "namelist.input") != stage["continuous_namelist_sha256"] or sha(RESTART / "namelist.input") != stage["restart_namelist_sha256"]:
        raise AssertionError("run namelist content does not match staged hash")
    restart_intervals = {"continuous_minutes": int(namelist_scalar(CONT / "namelist.input", "restart_interval")),
                         "restart_minutes": int(namelist_scalar(RESTART / "namelist.input", "restart_interval")),
                         "continuous_restart": namelist_scalar(CONT / "namelist.input", "restart"),
                         "restart_restart": namelist_scalar(RESTART / "namelist.input", "restart")}
    if restart_intervals != {"continuous_minutes": 10, "restart_minutes": 50,
                             "continuous_restart": ".false.", "restart_restart": ".true."}:
        raise AssertionError(f"restart-interval namelist inputs changed: {restart_intervals}")
    linked_inputs = []
    for d in (1, 2):
        linked = RESTART / f"wrfrst_d{d:02d}_2010-06-11_01:10:00"
        expected = CONT / linked.name
        if not linked.is_symlink() or linked.resolve(strict=True) != expected.resolve(strict=True) or sha(linked) != sha(expected):
            raise AssertionError(f"restart input is not its own pinned continuous checkpoint: {linked.name}")
        linked_inputs.append({"path": str(linked), "target": str(linked.resolve()), "sha256": sha(linked), "size_bytes": linked.stat().st_size})
    pairs = []
    for d in (1, 2):
        for minute in (10, 20, 30, 40, 50, 60):
            stamp = f"2010-06-11_{1 if minute < 60 else 2:02d}:{minute % 60:02d}:00"
            # Construct canonical hour rollover for 02:00.
            if minute == 60: stamp = "2010-06-11_02:00:00"
            cpath = CONT / f"wrfout_d{d:02d}_{stamp}"
            rpath = RESTART / f"wrfout_d{d:02d}_{stamp}"
            pairs.append(compare_datasets(cpath, rpath, d, stamp))
    checkpoint_pairs = []
    for d in (1, 2):
        stamp = "2010-06-11_02:00:00"
        cpath = CONT / f"wrfrst_d{d:02d}_{stamp}"
        rpath = RESTART / f"wrfrst_d{d:02d}_{stamp}"
        checkpoint_pairs.append(compare_datasets(cpath, rpath, d, stamp, checkpoint=True))
    if len(pairs) != 12 or len(checkpoint_pairs) != 2: raise AssertionError("incomplete comparison matrix")
    for entry in rr.get("continuous_output_pins_before", []):
        p = Path(entry["path"])
        if not p.is_file() or sha(p) != entry["sha256"]: raise AssertionError(f"continuous output changed since restart launch: {p}")
    if rr.get("continuous_output_pins_before") != rr.get("continuous_output_pins_after"):
        raise AssertionError("continuous output before/after pins differ")
    if {str(p): pin(p) for p in fixed_files} != before:
        raise AssertionError("source receipts, namelists, helper, or ledger changed during read-only comparison")
    source = source_pins()
    report = {
        "status": "PASS_SCOPED_RESTART_PARITY_WITH_INITIAL_DIAGNOSTIC_RESET_AND_FINAL_RESTART_ALARM_METADATA",
        "scope": "read-only stored-state comparison; strict original restart helper receipt remains FAIL_PRESERVED",
        "analyzer": pin(ANALYZER),
        "negative_controls": {"script": pin(NEGATIVE_CONTROL_SCRIPT), "result": pin(NEGATIVE_CONTROL_RESULT),
                              "status": neg["status"], "case_count": len(neg["cases"])},
        "strict_restart_receipt": pin(RST_RECEIPT), "strict_restart_status": rr["status"],
        "strict_restart_error": rr.get("error"), "continuous_receipt": pin(CONT_RECEIPT), "continuous_status": cr["status"],
        "stage": pin(STAGE), "helper": pin(HARNESS), "restart_adapter": pin(RESTART_ADAPTER),
        "posthoc_validator": pin(POSTHOC_VALIDATOR), "continuous_posthoc_ledger": pin(CONT_POSTHOC),
        "continuous_omission_report": pin(CONT_OMISSION_REPORT),
        "restart_input_checkpoint_links": linked_inputs,
        "input_namelists": {"continuous": pin(CONT / "namelist.input"), "restart": pin(RESTART / "namelist.input")},
        "restart_interval_configuration": restart_intervals,
        "runtime_integrity": {"before": rr.get("before_runtime_identity"), "after": rr.get("after_runtime_identity"),
                              "resolved_libraries_before": rr.get("resolved_libraries_before"),
                              "resolved_libraries_after": rr.get("resolved_libraries_after"),
                              "runtime_identity_unchanged": rr.get("runtime_identity_unchanged"),
                              "resolved_libraries_unchanged": rr.get("resolved_libraries_unchanged")},
        "counts": {"history_pairs": len(pairs), "history_variables_by_domain": {"d01": pairs[0]["variable_count"], "d02": pairs[6]["variable_count"]},
                   "history_exact_fields": sum(p["exact_variable_count"] for p in pairs),
                   "initial_diagnostic_resets": sum(p["initial_reset_variable_count"] for p in pairs),
                   "final_checkpoint_pairs": len(checkpoint_pairs),
                   "final_checkpoint_variables": {f"d{p['domain']:02d}": p["variable_count"] for p in checkpoint_pairs}},
        "history_pairs": pairs, "final_checkpoint_pairs": checkpoint_pairs,
        "alarm_interpretation": {
            "alarm51": "active RESTART_ALARM (index 51); only the final checkpoint differs because restart_interval is 10 minutes continuous and 50 minutes restarted. Both ISRINGING_51=1; exact countdowns are 600 and 3000 seconds.",
            "alarm55": "disabled COMPUTE_VORTEX_CENTER_ALARM (index 55; preprocessed set_timekeeping.f90:4385-4389); each final checkpoint's signed countdown is validated against its own run-start timestamp, and ISRINGING_55=0 on both sides.",
            "not_allowed": "No other field, variable metadata, global attribute, checkpoint, or history difference is accepted.",
        },
        "source_pins_and_citations": {"files": source, "citations": {
            "restart_alarm_id": "module_streams.F:19-23 (RESTART_ALARM index 51; BOUNDARY_ALARM is index 52); module_streams.f90:125-129 is the preprocessed counterpart; vortex-center alarm is index 55 at .F:27 / .f90:133",
            "restart_interval_controls_alarm": "set_timekeeping.F:393-412 (restart_interval in minutes, time interval creation and RESTART_ALARM setup)",
            "restart_alarm_output_only": "mediation_integrate.F:362-372 and 1122-1126 (RESTART_ALARM ringing triggers med_restart_out; no other alarm is used for restart output here); corresponding preprocessed file is source-pinned",
            "alarm51_values": "continuous/ restart namelist.input:23 (restart_interval 10/50); final checkpoint explicitly verifies active alarm and exact interval countdowns",
            "alarm55": "module_streams.F:133-135 and set_timekeeping.F: (vortex center alarm disabled in preprocessed build; receipt pins the exact preprocessed source/configure)",
            "initial_udm_reset": "registry.rrtmgp37:3-5 (history-only diagnostics); module_physics_init.F:1164-1177 initializes associated diagnostics to -1",
        }},
    }
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix(out.suffix + ".tmp")
    tmp.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n")
    tmp.replace(out)
    print(f"{report['status']}: {out}")
    return 0


if __name__ == "__main__": raise SystemExit(main())
