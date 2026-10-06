#!/usr/bin/env python3
"""Two-call, fail-closed RFMIP SW counterfactual runner; not executed at staging."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import signal
import subprocess
import time
from pathlib import Path

import netCDF4
import numpy as np

INPUT = Path("build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/inputs/multiple_input4MIPs_radiation_RFMIP_UColorado-RFMIP-1-2_none.nc")
CURRENT = Path("build/official-rrtmgp-reference/data/rrtmgp-gas-sw-g224.nc")
EXE = Path("build/official-rrtmgp-reference/source/examples/rfmip-clear-sky/rrtmgp_rfmip_sw")
UPSTREAM = Path("build/official-rrtmgp-reference/run-upstream")
OLD_SW = Path("build/udm37-rfmip-reference-provenance-v1/rrtmgp-data-sw-g224-2018-12-04.nc")
PUBLISHED = Path("build/official-rrtmgp-reference/data/examples/rfmip-clear-sky/reference")
NETCDF_LIB = Path("build/deps/root/usr/lib/x86_64-linux-gnu")
EXPECTED = {
    INPUT.as_posix(): "b8dc05d7cd2e0e6354b4a6198771ddf3bc09f18d72b49f20a41e2024e2fd51f4",
    CURRENT.as_posix(): "584f1dd41ea9fc07d4ee3754eb1dafbd46ad3161cd6fd20fa06b6922b6f0702e",
    EXE.as_posix(): "fcebb76288fec0fceba4d720f61001f495819489a975769eec7de57ca8daa74f",
    OLD_SW.as_posix(): "b9f4b15796d132880fffb49ac45c29753c1ee70a8ee3fed733899cb315c75e9b",
}
FILES = {
    "rsd": "rsd_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc",
    "rsu": "rsu_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc",
}


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def read_flux(path: Path, varname: str):
    with netCDF4.Dataset(path) as ds:
        if varname not in ds.variables:
            raise ValueError(f"missing {varname}: {path}")
        var = ds[varname]
        var.set_auto_maskandscale(False)
        raw = var[:]
        if np.ma.isMaskedArray(raw) and np.any(np.ma.getmaskarray(raw)):
            raise ValueError(f"masked {varname} values: {path}")
        values = np.asarray(raw.data if np.ma.isMaskedArray(raw) else raw)
        if not np.all(np.isfinite(values)):
            raise ValueError(f"non-finite {varname}: {path}")
        for attr in ("_FillValue", "missing_value"):
            if attr in var.ncattrs():
                marker = np.asarray(var.getncattr(attr), dtype=values.dtype)
                if np.any(np.isin(values, marker)):
                    raise ValueError(f"contains {attr} marker for {varname}: {path}")
        return values.copy()


def compare(path: Path, reference: Path, varname: str):
    got, ref = read_flux(path, varname), read_flux(reference, varname)
    if got.shape != ref.shape or got.dtype != ref.dtype:
        raise ValueError(f"shape/dtype mismatch for {varname}: {got.shape}/{got.dtype} vs {ref.shape}/{ref.dtype}")
    delta = np.abs(got.astype(np.float64) - ref.astype(np.float64))
    return {"shape": list(got.shape), "dtype": str(got.dtype),
            "max_abs": float(np.max(delta)), "mean_abs": float(np.mean(delta)),
            "count_gt_1e-5": int(np.count_nonzero(delta > 1e-5)),
            "within_published_atol_1e-5_rtol_0": bool(np.all(delta <= 1e-5)),
            "bitwise_value_equal": bool(got.tobytes(order="C") == ref.tobytes(order="C"))}


def verify_external_pins(workspace: Path):
    result = {}
    for rel, expected in EXPECTED.items():
        p = workspace / rel
        if not p.is_file():
            raise FileNotFoundError(p)
        got = sha(p)
        if got != expected:
            raise ValueError(f"immutable upstream pin changed: {rel} got {got}")
        result[rel] = got
    return result


def verify_output_reference_pins(workspace: Path, templates: dict):
    actual = {}
    for name, record in templates.items():
        pub = workspace / PUBLISHED / name
        baseline = workspace / UPSTREAM / name
        if sha(pub) != record["published_reference_sha256"]:
            raise ValueError(f"published reference output changed: {pub}")
        if sha(baseline) != record["current_upstream_output_sha256"]:
            raise ValueError(f"current upstream control output changed: {baseline}")
        actual[name] = {"published_reference_sha256": sha(pub),
                        "current_upstream_output_sha256": sha(baseline)}
    return actual


def execute(workspace: Path, stage: Path, approved_manifest_sha: str):
    workspace = workspace.resolve()
    stage = stage.resolve()
    manifest_path = stage / "stage-manifest.json"
    if not manifest_path.is_file():
        raise FileNotFoundError(manifest_path)
    manifest_sha = sha(manifest_path)
    if manifest_sha != approved_manifest_sha:
        raise ValueError(f"manifest review pin mismatch: {manifest_sha}")
    manifest = json.loads(manifest_path.read_text())
    if manifest.get("status") != "STAGED_NOT_RUN":
        raise ValueError("stage is not in STAGED_NOT_RUN state")
    if int(manifest["run_plan"]["max_invocations"]) != 2:
        raise ValueError("unexpected invocation cap")
    before = verify_external_pins(workspace)
    runner_sha256 = sha(Path(__file__).resolve())
    if before != manifest["pinned_inputs_sha256_before_after"]:
        raise ValueError("external pins differ from staged manifest")
    output_refs_before = verify_output_reference_pins(workspace, manifest["output_templates"])
    cf_coeff = stage / manifest["counterfactual_coeff_path"]
    if sha(cf_coeff) != manifest["counterfactual_coeff_sha256"]:
        raise ValueError("staged counterfactual coefficient file changed")

    # Fail closed on stale output directories: each is expected to contain only
    # pristine published templates when this exact stage is first executed.
    arm_spec = [
        ("control", workspace / CURRENT, "current_upstream_output_sha256"),
        ("old-solar-counterfactual", cf_coeff, None),
    ]
    templates = manifest["output_templates"]
    for arm, _, _ in arm_spec:
        run_dir = stage / arm
        if not run_dir.is_dir():
            raise FileNotFoundError(run_dir)
        expected_names = set(FILES.values())
        if {p.name for p in run_dir.iterdir()} != expected_names:
            raise ValueError(f"run directory has unexpected contents: {run_dir}")
        for name in expected_names:
            if sha(run_dir / name) != templates[name]["staged_template_sha256"]:
                raise ValueError(f"output template was already modified: {run_dir / name}")

    receipt_path = stage / "execution.json"
    if receipt_path.exists():
        raise FileExistsError(f"preserving prior execution receipt: {receipt_path}")
    receipt = {"schema": "rfmip-sw-solar-counterfactual-execution-v1", "status": "RUNNING",
               "stage_manifest_sha256": manifest_sha, "executable_and_data_pins_before": before,
               "reference_output_pins_before": output_refs_before,
               "runner_sha256": runner_sha256, "calls": [], "published_tolerance": {"atol": 1e-5, "rtol": 0}}

    def save():
        receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True) + "\n")

    env = {"LD_LIBRARY_PATH": str(workspace / NETCDF_LIB), "LC_ALL": "C", "TZ": "UTC"}
    receipt["runtime_environment"] = env.copy()
    try:
        for index, (arm, coeff, _) in enumerate(arm_spec):
            arm_dir = stage / arm
            coeff_path = coeff if coeff.is_absolute() else workspace / coeff
            input_arg = os.path.relpath(workspace / INPUT, arm_dir)
            coeff_arg = os.path.relpath(coeff_path, arm_dir)
            # Pinned upstream driver declares rfmip_file(256), kdist_file(132).
            # Use short relative paths and reject truncation before launch.
            if len(os.fsencode(input_arg)) > 256 or len(os.fsencode(coeff_arg)) > 132:
                raise ValueError("upstream Fortran command-argument buffer would truncate a path")
            if (arm_dir / input_arg).resolve() != (workspace / INPUT).resolve() or (arm_dir / coeff_arg).resolve() != coeff_path.resolve():
                raise ValueError("relative driver paths do not resolve to pinned input files")
            cmd = [str(workspace / EXE), "8", input_arg, coeff_arg, "1"]
            call = {"arm": arm, "command": cmd, "cwd": str(arm_dir), "status": "LAUNCHING"}
            receipt["calls"].append(call)
            save()  # durable intent before process creation
            start = time.time()
            launch_ns = time.time_ns()
            proc = subprocess.Popen(cmd, cwd=arm_dir, env=env, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, start_new_session=True)
            call["pid"] = proc.pid
            call["status"] = "RUNNING"
            save()
            try:
                stdout, _ = proc.communicate(timeout=120)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                stdout, _ = proc.communicate()
                call.update(status="TIMEOUT", returncode=proc.returncode,
                            elapsed_seconds=time.time() - start, stdout=stdout)
                receipt["status"] = "FAIL_PRESERVED"
                save()
                return 1
            call.update(returncode=proc.returncode, elapsed_seconds=time.time() - start,
                        stdout=stdout, status="PASS" if proc.returncode == 0 else "NONZERO_EXIT")
            save()
            if proc.returncode != 0:
                receipt["status"] = "FAIL_PRESERVED"
                save()
                return 1
            if ("Calculation uses RFMIP gases:" not in stdout or
                    re.search(r"STOP|ERROR|FATAL|segmentation fault|floating-point exception", stdout, re.I)):
                call["status"] = "DRIVER_COMPLETION_GUARD_FAILED"
                receipt["status"] = "FAIL_PRESERVED"
                save()
                return 1
            for output_name in FILES.values():
                output_path = arm_dir / output_name
                if not output_path.is_file() or output_path.stat().st_mtime_ns <= launch_ns:
                    call["status"] = "OUTPUT_NOT_FRESHLY_WRITTEN"
                    receipt["status"] = "FAIL_PRESERVED"
                    save()
                    return 1
            call["fresh_write_checks"] = {
                name: {"launch_ns": launch_ns, "output_mtime_ns": (arm_dir/name).stat().st_mtime_ns}
                for name in FILES.values()}

            got_paths = {name: arm_dir / filename for name, filename in FILES.items()}
            if any(not path.is_file() for path in got_paths.values()):
                receipt["status"] = "FAIL_PRESERVED"
                call["status"] = "MISSING_OUTPUT"
                save()
                return 1
            call["outputs"] = {name: {"path": str(path), "sha256": sha(path)} for name, path in got_paths.items()}
            if arm == "control":
                # This is the prerequisite that distinguishes a valid
                # counterfactual from a changed control setup.
                for name, path in got_paths.items():
                    current_reference = workspace / UPSTREAM / FILES[name]
                    current = compare(path, current_reference, name)
                    call.setdefault("current_upstream_bitwise_control", {})[name] = current
                    if not current["bitwise_value_equal"]:
                        call["status"] = "CONTROL_NOT_BITWISE_TO_PINNED_UPSTREAM"
                        receipt["status"] = "FAIL_PRESERVED"
                        save()
                        return 1
                if index != 0:
                    raise AssertionError("control must be first")
                # Do not require the known-residual control to pass publication
                # tolerance. Record it as the pre-registered control state.
                for name, path in got_paths.items():
                    call.setdefault("published_reference", {})[name] = compare(
                        path, workspace / PUBLISHED / FILES[name], name)
            else:
                for name, path in got_paths.items():
                    result = compare(path,
                        workspace / PUBLISHED / FILES[name], name)
                    call.setdefault("published_reference", {})[name] = result
                call["published_tolerance_pass"] = all(v["within_published_atol_1e-5_rtol_0"]
                                                         for v in call["published_reference"].values())
            call["status"] = "PASS"
            save()
            # Recheck after each process, especially between the control and
            # counterfactual, so drift prevents the second invocation.
            now = verify_external_pins(workspace)
            now_refs = verify_output_reference_pins(workspace, manifest["output_templates"])
            if now != before or now_refs != output_refs_before:
                call["status"] = "INPUT_OR_REFERENCE_DRIFT"
                receipt["status"] = "FAIL_PRESERVED"
                receipt["drift_detected_after_call"] = index + 1
                save()
                return 1
        if sha(cf_coeff) != manifest["counterfactual_coeff_sha256"] or sha(Path(__file__).resolve()) != runner_sha256:
            raise ValueError("counterfactual coefficient or runner drift")
        after = verify_external_pins(workspace)
        receipt["executable_and_data_pins_after"] = after
        output_refs_after = verify_output_reference_pins(workspace, manifest["output_templates"])
        receipt["reference_output_pins_after"] = output_refs_after
        if before != after or output_refs_before != output_refs_after:
            receipt["status"] = "FAIL_PRESERVED"
            receipt["reason"] = "upstream input/executable pins changed during execution"
            save()
            return 1
        receipt["status"] = "COMPLETE_TWO_SW_CALLS"
        receipt["counterfactual_published_tolerance_pass"] = receipt["calls"][1].get("published_tolerance_pass")
        save()
        return 0
    except Exception as exc:
        receipt["status"] = "FAIL_PRESERVED"
        receipt["exception"] = f"{type(exc).__name__}: {exc}"
        save()
        raise


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", type=Path, default=Path("."))
    ap.add_argument("--stage", type=Path, required=True)
    ap.add_argument("--execute", action="store_true", help="explicitly authorize the two SW subprocesses")
    ap.add_argument("--approved-manifest-sha256")
    args = ap.parse_args()
    if not args.execute:
        ap.error("staged only: pass --execute and the reviewed --approved-manifest-sha256 to launch")
    if not args.approved_manifest_sha256:
        ap.error("--approved-manifest-sha256 is required with --execute")
    raise SystemExit(execute(args.workspace, args.stage, args.approved_manifest_sha256))


if __name__ == "__main__":
    main()
