#!/usr/bin/env python3
"""Read-only posthoc verifier for the preserved GNU dm+sm CCN build attempt.

This follows the actual WRF recipe: sed converts .F to .G, /lib/cpp applies
DM/OpenMP macros to .G and emits .bb, standard.exe plus CPP emits .f90, and
mpif90 compiles that generated source with -fopenmp. It never rebuilds or runs
WRF.
"""
from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import re
import subprocess
from typing import Any

ROOT = Path(__file__).resolve().parents[3]
TASK = ROOT / "build/udm37-ccn-tile-init-gnu-v1"
HERE = TASK / "posthoc-v3"
SPEC_PATH = TASK / "source-freeze-v1.json"
PREPARER_PATH = TASK / "prepare_ccn_source_v1.py"
GENERATED_VERIFIER_PATH = TASK / "verify_generated_ccn_v1.py"
SOURCE_RECEIPT_PATH = TASK / "source-preparation-v1.json"
MANIFEST_PATH = TASK / "source-manifest-v1.json"
BUILD_RECEIPT_PATH = TASK / "build-result-v1.json"
BUILD_LOG_PATH = TASK / "build-em_real-v1.log"
OUTPUT_PATH = HERE / "posthoc-attestation-v3.json"
EXPECTED_BUILD_RECEIPT_SHA = "ba3938fab7a16e8f2cd9f2e4d939f1c2fa95cee9cf392a7e403f6891fcb6a631"
EXPECTED_BUILD_LOG_SHA = "e7cde20caeb447ef496f774eae1172108766b9cf9a4162cf7d33dff1e1ba2faa"
EXPECTED_V1_HARNESS_ERROR = "AttributeError: module 'prepare_ccn_source_v1' has no attribute 'verify_compile_commands'"
MODULES = ("module_mp_udm", "module_microphysics_driver")


def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    p = path.resolve(strict=True)
    if not p.is_file():
        raise ValueError(f"not a regular file: {p}")
    return {"path": str(p), "size_bytes": p.stat().st_size, "sha256": sha(p)}


def import_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def verify_compile_phases(log_text: str, modules: tuple[str, ...] = MODULES) -> dict[str, Any]:
    """Check per-target CPP macros and the subsequent actual Fortran compile.

    In WRF's make rules, -DDM_PARALLEL and -D_OPENMP are passed to /lib/cpp
    for the .F source; -fopenmp is passed to mpif90 for generated .f90. The
    Fortran compiler command is not expected to repeat -DDM_PARALLEL.
    """
    lines = log_text.splitlines()
    result: dict[str, Any] = {}
    for module in modules:
        mod = re.escape(module.lower())
        sed = [(i, line) for i, line in enumerate(lines)
               if re.search(rf"\b{mod}\.f\s*>\s*{mod}\.g\b", line.lower())]
        cpp = [(i, line) for i, line in enumerate(lines)
               if "/lib/cpp" in line.lower()
               and re.search(rf"\b{mod}\.(?:g|f)\b", line.lower())]
        cpp_good = [x for x in cpp if "-ddm_parallel" in x[1].lower() and "-d_openmp" in x[1].lower()]
        generated = [(i, line) for i, line in enumerate(lines)
                     if "standard.exe" in line.lower()
                     and re.search(rf"\b{mod}\.bb\b", line.lower())
                     and re.search(rf">\s*{mod}\.f90\b", line.lower())]
        f90 = [(i, line) for i, line in enumerate(lines)
               if ("mpif90" in line.lower() and re.search(r"\s-c(?:\s|$)", line.lower())
                   and re.search(rf"\s-o\s+{mod}\.o\b", line.lower())
                   and re.search(rf"\b{mod}\.f90\b", line.lower()))]
        f90_good = [x for x in f90 if "-fopenmp" in x[1].lower()]
        ordered = bool(sed and cpp_good and generated and f90_good
                       and sed[0][0] < cpp_good[0][0] < generated[0][0] < f90_good[0][0])
        result[module] = {
            "sed_f_to_g_count": len(sed),
            "cpp_command_count": len(cpp),
            "cpp_dm_parallel_command_count": sum("-ddm_parallel" in x[1].lower() for x in cpp),
            "cpp_openmp_macro_command_count": sum("-d_openmp" in x[1].lower() for x in cpp),
            "standard_bb_to_f90_count": len(generated),
            "fortran_compile_command_count": len(f90),
            "fortran_openmp_compile_command_count": len(f90_good),
            "phase_lines": {"sed": sed[0][0] + 1 if sed else None,
                            "cpp": cpp_good[0][0] + 1 if cpp_good else None,
                            "standard_to_f90": generated[0][0] + 1 if generated else None,
                            "fortran_compile": f90_good[0][0] + 1 if f90_good else None},
            "cpp_command_lines": [x[0] + 1 for x in cpp_good],
            "fortran_command_lines": [x[0] + 1 for x in f90_good],
            "passed": ordered,
        }
        if not result[module]["passed"]:
            raise ValueError(f"CPP/Fortran flag phase check failed for {module}: {result[module]}")
    return {"status": "CPP_AND_FORTRAN_FLAGS_PASS", "modules": result}


def load_expected_artifacts() -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    spec = json.loads(SPEC_PATH.read_text())
    source_receipt = json.loads(SOURCE_RECEIPT_PATH.read_text())
    source_manifest = json.loads(MANIFEST_PATH.read_text())
    build_receipt = json.loads(BUILD_RECEIPT_PATH.read_text())
    if sha(BUILD_RECEIPT_PATH) != EXPECTED_BUILD_RECEIPT_SHA:
        raise ValueError("preserved v1 BUILD_FAIL receipt changed")
    if sha(BUILD_LOG_PATH) != EXPECTED_BUILD_LOG_SHA:
        raise ValueError("preserved v1 compiler log changed")
    if source_receipt.get("status") != "SOURCE_PREPARED_NOT_BUILT":
        raise ValueError("source preparation was not a clean ready snapshot")
    if source_receipt.get("compile_invocations") != 0 or source_receipt.get("model_invocations") != 0:
        raise ValueError("source prep should not run compiler or model")
    if len(source_manifest.get("files", [])) != 6735 or source_manifest.get("entry_count") != 6735:
        raise ValueError("source manifest is not the frozen 6735-entry roster")
    if source_manifest.get("symlink_count") != 17:
        raise ValueError("source manifest symlink roster changed")
    if build_receipt.get("status") != "BUILD_FAIL_PRESERVED" or build_receipt.get("error") != EXPECTED_V1_HARNESS_ERROR:
        raise ValueError("unexpected v1 build receipt; retain and investigate, do not rewrite")
    if build_receipt.get("process", {}).get("returncode") != 0 or build_receipt.get("process", {}).get("timed_out"):
        raise ValueError("underlying full compiler process did not complete successfully")
    if not build_receipt.get("source_unchanged") or not build_receipt.get("dependencies_unchanged"):
        raise ValueError("frozen build receipt reports source/dependency mutation")
    if spec.get("base_commit") != source_manifest.get("base_commit"):
        raise ValueError("source base differs from the frozen build spec")
    return spec, source_receipt, source_manifest, build_receipt


def attest() -> dict[str, Any]:
    spec, source_receipt, manifest, build = load_expected_artifacts()
    prepare = import_module("prepare_ccn_source_v1_posthoc", PREPARER_PATH)
    generated = import_module("verify_generated_ccn_v1_posthoc", GENERATED_VERIFIER_PATH)
    source = Path(manifest["source_path"]).resolve(strict=True)
    wrf = source / "WRF"
    staged_check = prepare.verify_staged_source(manifest)
    if staged_check != {"files": 6718, "symlinks": 17, "entries": 6735}:
        raise ValueError(f"source manifest readback failed: {staged_check}")
    overlay_checks = {}
    for rel, expected in spec["source_overlays"].items():
        path = source / rel
        actual = pin(path)
        if actual["sha256"] != expected["sha256"] or actual["size_bytes"] != expected["size_bytes"]:
            raise ValueError(f"production overlay changed after build: {rel}")
        overlay_checks[rel] = actual

    dependency_data = json.loads((TASK / "shared-dependencies-before-v1.json").read_text())
    _, donor_prep = prepare.import_donor_modules()
    current_dependencies = donor_prep.dependencies(spec)
    if len(current_dependencies["files"]) != 1582 or current_dependencies != dependency_data:
        raise ValueError("shared compiler/NetCDF/MPI dependency inventory changed")

    log = BUILD_LOG_PATH.read_text(errors="replace")
    phase_checks = verify_compile_phases(log)
    helper, _ = prepare.import_donor_modules()
    log_status = helper.classify_build_log(log, build["process"]["returncode"])
    if not log_status.get("successful_footer") or log_status.get("errors"):
        raise ValueError(f"build log lacks successful clean completion: {log_status}")
    generated_source = generated.verify_generated_sources(wrf)
    compiled_objects = generated.verify_compiled_objects(wrf)
    executables = {}
    for name in ("wrf.exe", "real.exe", "ndown.exe", "tc.exe"):
        path = wrf / "main" / name
        if not path.is_file() or path.stat().st_size == 0:
            raise ValueError(f"missing full-build executable: {name}")
        with path.open("rb") as stream:
            if stream.read(4) != b"\x7fELF":
                raise ValueError(f"non-ELF executable: {name}")
        executables[name] = pin(path)

    return {
        "schema": "udm37-ccn-gnu-dm-sm-posthoc-attestation-v3",
        "status": "POSTHOC_BUILD_ATTESTED_ORIGINAL_RUNNER_FAILURE_PRESERVED",
        "original_v1_receipt": pin(BUILD_RECEIPT_PATH),
        "original_v1_log": pin(BUILD_LOG_PATH),
        "original_v1_harness_failure": EXPECTED_V1_HARNESS_ERROR,
        "underlying_compile_process": build["process"],
        "source_preparation": pin(SOURCE_RECEIPT_PATH),
        "source_manifest": pin(MANIFEST_PATH),
        "source_manifest_readback": staged_check,
        "source_overlays_unchanged": overlay_checks,
        "dependency_inventory": {"count": len(current_dependencies["files"]),
                                  "path": str(TASK / "shared-dependencies-before-v1.json"),
                                  "sha256": sha(TASK / "shared-dependencies-before-v1.json"),
                                  "matches_frozen_before_after": True},
        "compile_log": {"classification": log_status, "flag_phase_validation": phase_checks},
        "generated_ccn_source": generated_source,
        "compiled_ccn_objects": compiled_objects,
        "full_build_executables": executables,
        "new_compile_invocations": 0,
        "new_model_invocations": 0,
        "v1_receipt_mutations": 0,
    }


def main() -> int:
    import argparse
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--attest-go", action="store_true", help="run read-only posthoc attestation and write a new v3 receipt")
    args = parser.parse_args()
    if not args.attest_go:
        print(json.dumps({"status": "READY_POSTHOC_NOT_RUN", "compile_invocations": 0,
                          "model_invocations": 0, "v1_receipt_unchanged": pin(BUILD_RECEIPT_PATH)}))
        return 0
    if OUTPUT_PATH.exists():
        print(json.dumps({"status": "OUTPUT_COLLISION", "path": str(OUTPUT_PATH)}))
        return 2
    try:
        result = attest()
    except Exception as exc:
        result = {"schema": "udm37-ccn-gnu-dm-sm-posthoc-attestation-v3",
                  "status": "POSTHOC_ATTESTATION_FAILED_PRESERVED",
                  "error": f"{type(exc).__name__}: {exc}",
                  "original_v1_receipt": pin(BUILD_RECEIPT_PATH),
                  "original_v1_log": pin(BUILD_LOG_PATH),
                  "new_compile_invocations": 0, "new_model_invocations": 0}
    OUTPUT_PATH.write_text(json.dumps(result, indent=2, sort_keys=True) + "\n")
    print(json.dumps({"status": result["status"], "receipt": str(OUTPUT_PATH),
                      "new_compile_invocations": 0, "new_model_invocations": 0}))
    return 0 if result["status"] == "POSTHOC_BUILD_ATTESTED_ORIGINAL_RUNNER_FAILURE_PRESERVED" else 1


if __name__ == "__main__":
    raise SystemExit(main())
