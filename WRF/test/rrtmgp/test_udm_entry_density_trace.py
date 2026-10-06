#!/usr/bin/env python3
"""Standalone compile/run contract for the opt-in UDM entry-density packet."""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import time


ENV_KEYS = ("WRF_RRTMGP_CAPTURE_DIR", "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY",
            "WRF_RRTMGP_CAPTURE_UDM_RADII", "WRF_RRTMGP_CAPTURE_ALL",
            "WRF_RRTMGP_CAPTURE_CALL", "WRF_RRTMGP_COLUMN_I", "WRF_RRTMGP_COLUMN_J")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def durable_json(path: Path, obj: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(obj, f, indent=2, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, path)
    dfd = os.open(path.parent, os.O_RDONLY)
    try:
        os.fsync(dfd)
    finally:
        os.close(dfd)


def clean_env(updates: dict[str, str] | None = None, *, threads: str = "1") -> dict[str, str]:
    env = {k: v for k, v in os.environ.items() if k not in ENV_KEYS}
    env["OMP_NUM_THREADS"] = threads
    env["OMP_DYNAMIC"] = "FALSE"
    if updates:
        env.update(updates)
    return env


def run(cmd: list[str], cwd: Path, env: dict[str, str], record: Path) -> subprocess.CompletedProcess[str]:
    started = time.time()
    p = subprocess.run(cmd, cwd=cwd, env=env, text=True, stdout=subprocess.PIPE,
                       stderr=subprocess.STDOUT, check=False)
    # Save the process return code and complete output before inspecting either.
    durable_json(record, {"argv": cmd, "cwd": str(cwd), "started_unix": started,
                          "finished_unix": time.time(), "returncode": p.returncode,
                          "output": p.stdout})
    return p


def expect_failure(exe: Path, cwd: Path, env: dict[str, str], mode: str,
                   marker: str, receipt: Path) -> None:
    p = run([str(exe), mode], cwd, env, receipt)
    if p.returncode == 0 or marker not in p.stdout:
        raise AssertionError(f"{mode}: wanted {marker!r}; rc={p.returncode}\n{p.stdout}")


def parse_packet(path: Path) -> tuple[list[int], dict[str, list[float]]]:
    lines = path.read_text(encoding="ascii").splitlines()
    if len(lines) < 3 or lines[0] != "RRTMGP_UDM_ENTRY_DENSITY_V2":
        raise AssertionError("packet magic or minimum length is wrong")
    header = [int(x) for x in lines[1].split()]
    if len(header) != 6:
        raise AssertionError("packet header must contain six integers")
    records: dict[str, list[float]] = {}
    cursor = 2
    while cursor < len(lines):
        fields = lines[cursor].split()
        if len(fields) != 2:
            raise AssertionError(f"malformed record header at line {cursor + 1}")
        name, count_s = fields
        count = int(count_s)
        cursor += 1
        if count < 1 or cursor + count > len(lines) or name in records:
            raise AssertionError(f"bad/duplicate record {name}")
        values = [float(lines[cursor + k]) for k in range(count)]
        cursor += count
        if not all(map(math.isfinite, values)):
            raise AssertionError(f"nonfinite packet values in {name}")
        records[name] = values
    return header, records


def validate_packet(path: Path, expected_dry: bool) -> None:
    header, r = parse_packet(path)
    if header != [1, 23, 2, 3, 4, 6]:
        raise AssertionError(f"unexpected packet header {header}")
    vectors = ("TH_K", "PII", "T_K", "P_PA", "QV_MIXING_RATIO_KG_KG",
               "DEN_PASSED_KG_M3", "DEND_REEVALUATED_PRECALL_KG_M3",
               "DEND_LEGACY_COUNTERFACTUAL_KG_M3", "QC_RAW", "QI_RAW",
               "QR_RAW", "QS_RAW", "QG_RAW", "QH_RAW", "NN_RAW", "NC_RAW", "NR_RAW")
    scalars = ("RD_J_KG_K", "RV_J_KG_K", "CPD_J_KG_K", "CPV_J_KG_K", "GRAVITY_M_S2",
               "DELT_SECONDS", "QMIN", "T0C_K", "RHO0_KG_M3", "RHO_WATER_KG_M3",
               "DEND_ORIGIN", "DEFAULT_REAL_BITS", "SOURCE_TIME_PRESENT", "SOURCE_TIME_SECONDS",
               "INPUT_DENSITY_IS_DRY")
    if tuple(r) != vectors + scalars:
        raise AssertionError(f"unexpected packet record order/names: {tuple(r)}")
    if any(len(r[n]) != 3 for n in vectors) or any(len(r[n]) != 1 for n in scalars):
        raise AssertionError("record vector/scalar dimensions do not match header")
    close_vec = lambda actual, expected: all(abs(a-b) <= max(1.e-7, abs(b)*2.e-7)
                                              for a, b in zip(actual, expected))
    if not close_vec(r["TH_K"], [250., 251., 252.]) or not close_vec(r["PII"], [1., .99, .98]):
        raise AssertionError(f"input vectors changed during capture: TH={r['TH_K']} PII={r['PII']}")
    if not close_vec(r["P_PA"], [90000., 80000., 70000.]) or not close_vec(r["DEN_PASSED_KG_M3"], [1.1, 1., .3]):
        raise AssertionError("pressure or passed-density vectors changed")
    if r["QC_RAW"][1] >= 0 or r["QH_RAW"][1] >= 0 or r["NN_RAW"][2] >= 0:
        raise AssertionError("raw negative diagnostic values were clipped or lost")
    # Validate products and DEND at default-REAL precision without claiming that
    # this re-evaluation observes the microphysics routine's private local DEND.
    for got, a, b in zip(r["T_K"], r["TH_K"], r["PII"]):
        if abs(got - a * b) > 2.e-5:
            raise AssertionError("temperature is not TH*PII within default-REAL rounding")
    rd, rv = r["RD_J_KG_K"][0], r["RV_J_KG_K"][0]
    for got, pressure, temp, density in zip(r["DEND_LEGACY_COUNTERFACTUAL_KG_M3"], r["P_PA"],
                                             r["T_K"], r["DEN_PASSED_KG_M3"]):
        expected = (pressure / temp - density * rv) / (rd - rv)
        if abs(got - expected) > max(2.e-7, abs(expected) * 2.e-6):
            raise AssertionError("pre-call DEND re-evaluation mismatch")
    if r["DEND_ORIGIN"] != [1.] or r["DEFAULT_REAL_BITS"] != [32.]:
        raise AssertionError("DEND provenance or default-REAL bit width mismatch")
    if r["INPUT_DENSITY_IS_DRY"] != [1. if expected_dry else 0.]:
        raise AssertionError("input density policy flag mismatch")
    if expected_dry:
        if not close_vec(r["DEND_REEVALUATED_PRECALL_KG_M3"], r["DEN_PASSED_KG_M3"]):
            raise AssertionError("dry-input selected density must equal passed density")
        if r["DEND_LEGACY_COUNTERFACTUAL_KG_M3"][2] >= 0.:
            raise AssertionError("negative legacy counterfactual DEND was clipped")
    else:
        if not close_vec(r["DEND_REEVALUATED_PRECALL_KG_M3"],
                         r["DEND_LEGACY_COUNTERFACTUAL_KG_M3"]):
            raise AssertionError("legacy selected density differs from its counterfactual field")
        if r["DEND_REEVALUATED_PRECALL_KG_M3"][2] >= 0.:
            raise AssertionError("negative re-evaluated DEND was clipped")
    if r["SOURCE_TIME_PRESENT"] != [1.] or r["SOURCE_TIME_SECONDS"] != [3600.]:
        raise AssertionError("optional source time metadata mismatch")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--wrf-root", type=Path, required=True)
    ap.add_argument("--receipt-dir", type=Path, required=True)
    ap.add_argument("--compiler", default=shutil.which("gfortran") or "gfortran")
    args = ap.parse_args()
    wrf = args.wrf_root.resolve()
    receipt_dir = args.receipt_dir.resolve()
    src = wrf / "phys/module_ra_rrtmgp_trace.F"
    driver = wrf / "test/rrtmgp/test_udm_entry_density_trace.F90"
    stub = wrf / "test/rrtmgp/standalone_wrf_error.f90"
    if not all(p.is_file() for p in (src, driver, stub)):
        raise FileNotFoundError("missing trace source, fixture, or fatal stub")
    receipt_dir.mkdir(parents=True, exist_ok=True)
    compiler = str(Path(args.compiler).resolve()) if Path(args.compiler).exists() else args.compiler
    source_pins = {str(p): {"sha256": sha(p), "size_bytes": p.stat().st_size}
                   for p in (src, driver, stub)}
    compiler_version = subprocess.run([compiler, "--version"], text=True, stdout=subprocess.PIPE,
                                      stderr=subprocess.STDOUT, check=False).stdout.splitlines()[0]
    root_receipt: dict[str, object] = {"schema": "udm-entry-density-trace-test-v1",
        "compiler": compiler, "compiler_version": compiler_version, "source_pins": source_pins,
        "runs": [], "model_invocations": 0}
    durable_json(receipt_dir / "test-running.json", root_receipt)

    # Keep executable fixtures under the pinned workspace filesystem; some
    # systems mount /tmp noexec, which would make a successful link un-runnable.
    with tempfile.TemporaryDirectory(prefix="udm-entry-density-trace-", dir=receipt_dir) as td_s:
        td = Path(td_s)
        run_results = []
        for opt in ("-O0", "-O2"):
            od = td / opt[1:]
            od.mkdir()
            capture = td / f"capture-{opt[1:]}"
            capture.mkdir()
            flags = ["-cpp", "-ffree-form", "-ffree-line-length-none", "-fopenmp", opt]
            inc = ["-I", str(od), "-J", str(od)]
            for label, source, obj in (("stub", stub, od / "error.o"), ("trace", src, od / "trace.o")):
                proc = run([compiler, *flags, *inc, "-c", str(source), "-o", str(obj)], td,
                           clean_env(), receipt_dir / f"{opt[1:]}-{label}-compile.json")
                if proc.returncode:
                    raise RuntimeError(f"{opt} compile failed for {label}; see durable receipt")
            exe = od / "density-trace-test"
            proc = run([compiler, "-fopenmp", opt, *inc, str(driver), str(od / "trace.o"),
                        str(od / "error.o"), "-o", str(exe)], td, clean_env(),
                       receipt_dir / f"{opt[1:]}-link.json")
            if proc.returncode:
                raise RuntimeError(f"{opt} link failed; see durable receipt")
            base = {"WRF_RRTMGP_CAPTURE_DIR": str(capture)}

            # Disabled mode must be a true no-op, including malformed shapes and
            # the absence of an output directory environment variable.
            no_capture = clean_env()
            proc = run([str(exe), "disabled"], td, no_capture, receipt_dir / f"{opt[1:]}-disabled.json")
            if proc.returncode:
                raise AssertionError(f"disabled default failed: {proc.stdout}")
            if list(capture.iterdir()):
                raise AssertionError("disabled gate wrote a file")
            proc = run([str(exe), "disabled"], td,
                       clean_env({**base, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": ""}),
                       receipt_dir / f"{opt[1:]}-empty-gate.json")
            if proc.returncode or list(capture.iterdir()):
                raise AssertionError(f"explicit empty gate must remain disabled: {proc.stdout}")
            enabled = {**base, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1",
                       "WRF_RRTMGP_COLUMN_I": "2", "WRF_RRTMGP_COLUMN_J": "3"}
            p = run([str(exe), "selection"], td, clean_env(enabled), receipt_dir / f"{opt[1:]}-selection.json")
            if p.returncode:
                raise AssertionError(f"valid selected packet failed: {p.stdout}")
            packet = capture / "udm_entry_density_d1_i2_j3_step23.raw"
            if sorted(x.name for x in capture.iterdir()) != [packet.name]:
                raise AssertionError("column filter must write exactly one selected packet")
            saved_packet = receipt_dir / f"{opt[1:]}-packet.raw"
            shutil.copyfile(packet, saved_packet)
            validate_packet(packet, expected_dry=False)
            packet_pin = {"path": str(saved_packet), "sha256": sha(saved_packet),
                          "size_bytes": saved_packet.stat().st_size}

            policy_packets = []
            for mode, expected_dry in (("falsepacket", False), ("drypacket", True)):
                policy_capture = td / f"capture-{opt[1:]}-{mode}"
                policy_capture.mkdir()
                policy_env = clean_env({**enabled, "WRF_RRTMGP_CAPTURE_DIR": str(policy_capture),
                                        "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1"})
                p = run([str(exe), mode], td, policy_env,
                        receipt_dir / f"{opt[1:]}-{mode}.json")
                if p.returncode:
                    raise AssertionError(f"density policy {mode} failed: {p.stdout}")
                policy_packet = policy_capture / "udm_entry_density_d1_i2_j3_step23.raw"
                validate_packet(policy_packet, expected_dry=expected_dry)
                saved_policy_packet = receipt_dir / f"{opt[1:]}-{mode}.raw"
                shutil.copyfile(policy_packet, saved_policy_packet)
                policy_packets.append({"mode": mode, "input_density_is_dry": expected_dry,
                                       "packet": {"path": str(saved_policy_packet),
                                                  "sha256": sha(saved_policy_packet),
                                                  "size_bytes": saved_policy_packet.stat().st_size}})

            missing_j = dict(enabled)
            missing_j.pop("WRF_RRTMGP_COLUMN_J")
            expect_failure(exe, td, clean_env(missing_j),
                           "packet", "RRTMGP_COLUMN_SELECTION_PAIR_REQUIRED",
                           receipt_dir / f"{opt[1:]}-missing-selector-partner.json")
            expect_failure(exe, td, clean_env({**enabled, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "0"}),
                           "packet", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_INVALID",
                           receipt_dir / f"{opt[1:]}-gate-zero-invalid.json")
            expect_failure(exe, td, clean_env({**enabled, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "OFF"}),
                           "packet", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_INVALID",
                           receipt_dir / f"{opt[1:]}-gate-off-invalid.json")
            expect_failure(exe, td, clean_env({**enabled, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1" * 48}),
                           "packet", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_INVALID",
                           receipt_dir / f"{opt[1:]}-gate-long-invalid.json")
            expect_failure(exe, td, clean_env({"WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1"}),
                           "packet", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_REQUIRES_CAPTURE_DIR",
                           receipt_dir / f"{opt[1:]}-missing-dir.json")
            expect_failure(exe, td, clean_env({**enabled, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1"}),
                           "badshape", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_SHAPE",
                           receipt_dir / f"{opt[1:]}-shape-invalid.json")
            expect_failure(exe, td, clean_env({**enabled, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1"}),
                           "nan", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_NONFINITE_TH_OR_PII",
                           receipt_dir / f"{opt[1:]}-nan-invalid.json")
            expect_failure(exe, td, clean_env({**enabled, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1"}),
                           "rawnan", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_NONFINITE_RAW_STATE",
                           receipt_dir / f"{opt[1:]}-rawnan-invalid.json")
            expect_failure(exe, td, clean_env({**enabled, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1"}),
                           "badclock", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_INVALID_SOURCE_TIME",
                           receipt_dir / f"{opt[1:]}-clock-invalid.json")
            expect_failure(exe, td, clean_env({**enabled, "WRF_RRTMGP_CAPTURE_UDM_ENTRY_DENSITY": "1"}),
                           "duplicate", "RRTMGP_TRACE_UDM_ENTRY_DENSITY_IO_ERROR",
                           receipt_dir / f"{opt[1:]}-duplicate-invalid.json")
            expect_failure(exe, td, clean_env(enabled, threads="2"), "packet",
                           "RRTMGP_TRACE_SERIAL_ONLY", receipt_dir / f"{opt[1:]}-omp-guard.json")
            run_results.append({"optimization": opt, "executable_sha256": sha(exe),
                                "packet": packet_pin, "policy_packets": policy_packets,
                                "compiled": True})
        root_receipt["runs"] = run_results

    after = {str(p): {"sha256": sha(p), "size_bytes": p.stat().st_size} for p in (src, driver, stub)}
    root_receipt["source_pins_after"] = after
    root_receipt["source_unchanged"] = source_pins == after
    if source_pins != after:
        durable_json(receipt_dir / "test-failed.json", root_receipt)
        raise AssertionError("test sources changed during fixture run")
    root_receipt["status"] = "PASS"
    durable_json(receipt_dir / "test-result.json", root_receipt)
    print("PASS: disabled no-op, exact opt-in packet, selected-column filter, malformed input/time, duplicate, and OMP guard at -O0/-O2")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
