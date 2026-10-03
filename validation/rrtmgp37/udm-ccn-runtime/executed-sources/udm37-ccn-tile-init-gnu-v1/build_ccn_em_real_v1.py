#!/usr/bin/env python3
"""Prepare-only by default; fresh GNU dm+sm WRF build requires --compile-go."""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve().parent
SPEC_PATH = HERE / "source-freeze-v1.json"
PREPARER = HERE / "prepare_ccn_source_v1.py"
SOURCE_RECEIPT = HERE / "source-preparation-v1.json"
MANIFEST_PATH = HERE / "source-manifest-v1.json"
RESULT_PATH = HERE / "build-result-v1.json"
LOG_PATH = HERE / "build-em_real-v1.log"
TIMEOUT_S = 1800


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def import_preparer():
    expected = json.loads(SPEC_PATH.read_text()).get("preparer_sha256")
    if expected and digest(PREPARER) != expected:
        raise ValueError("source preparer changed from frozen harness")
    spec = importlib.util.spec_from_file_location("prepare_ccn_source_v1", PREPARER)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def import_generated_verifier():
    path = HERE / "verify_generated_ccn_v1.py"
    expected = json.loads(SPEC_PATH.read_text()).get("generated_verifier_sha256")
    if expected and digest(path) != expected:
        raise ValueError("generated-source verifier changed from frozen harness")
    spec = importlib.util.spec_from_file_location("verify_generated_ccn_v1", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


def pin(path: Path) -> dict[str, Any]:
    p = path.resolve(strict=True)
    if not p.is_file():
        raise ValueError(f"not a regular file: {p}")
    return {"path": str(p), "size_bytes": p.stat().st_size, "sha256": digest(p)}


def require_fresh_source(source: Path, manifest: dict[str, Any]) -> None:
    for rel in (
        "WRF/phys/module_mp_udm.o", "WRF/phys/module_microphysics_driver.o",
        "WRF/phys/module_mp_udm.f90", "WRF/phys/module_microphysics_driver.f90",
        "WRF/main/wrf.exe", "WRF/main/real.exe", "WRF/main/ndown.exe", "WRF/main/tc.exe",
    ):
        p = source / rel
        if p.exists() or p.is_symlink():
            raise FileExistsError(f"fresh source tree already contains build artifact: {rel}")
    for p in (source / "WRF/external/rte_rrtmgp/build").glob("*.o"):
        raise FileExistsError(f"fresh source tree has a stale RRTMGP object: {p.name}")
    if manifest.get("entry_count") != 6735 or len(manifest.get("files", [])) != 6735:
        raise ValueError("source manifest has the wrong file count")


def load_inputs():
    p = import_preparer()
    spec = json.loads(SPEC_PATH.read_text())
    prep = json.loads(SOURCE_RECEIPT.read_text())
    manifest = json.loads(MANIFEST_PATH.read_text())
    if prep.get("status") != "SOURCE_PREPARED_NOT_BUILT":
        raise ValueError("source is not freshly prepared")
    if prep.get("compile_invocations") != 0 or prep.get("model_invocations") != 0:
        raise ValueError("source preparation receipt unexpectedly reports compilation/model runs")
    if prep.get("source_manifest", {}).get("sha256") != pin(MANIFEST_PATH)["sha256"]:
        raise ValueError("source manifest pin differs from preparation receipt")
    staged = p.verify_staged_source(manifest)
    source = Path(manifest["source_path"]).resolve(strict=True)
    require_fresh_source(source, manifest)
    configure = pin(source / "WRF/configure.wrf")
    if configure["sha256"] != spec["configure_template"]["sha256"]:
        raise ValueError("staged configure.wrf differs from pinned GNU dm+sm configure")
    dependencies = p.import_dependency_inventory(spec)
    if dependencies != json.loads(p.DEPS_PIN.read_text()):
        raise ValueError("GNU/MPICH/NetCDF dependency inventory changed")
    return p, spec, prep, manifest, source, staged, dependencies


def build(args: argparse.Namespace) -> dict[str, Any]:
    p, spec, prep, manifest, source, staged, dependencies = load_inputs()
    if RESULT_PATH.exists() or LOG_PATH.exists():
        raise FileExistsError("build receipt/log exists; use a new versioned build directory")
    wrf = source / "WRF"
    env = dict(spec["build_environment"])
    env.update({"LC_ALL": "C", "LANG": "C", "TMPDIR": str(HERE / "tmp")})
    for name in ("HOME", "USER", "LOGNAME"):
        if name in os.environ:
            env[name] = os.environ[name]
    command = ["csh", "-f", "./compile", "-j", "12", "em_real"]
    common = {
        "schema": "udm37-ccn-gnu-dm-sm-build-v1",
        "freeze_spec": pin(SPEC_PATH),
        "source_preparation": pin(SOURCE_RECEIPT),
        "source_manifest": pin(MANIFEST_PATH),
        "source_entry_count": staged["entries"],
        "source_overlay": prep["overlay"],
        "shared_dependencies": pin(p.DEPS_PIN),
        "dependency_count": len(dependencies["files"]),
        "configure": pin(source / "WRF/configure.wrf"),
        "external_rte_object_roster_expected": spec["external_rte_object_names"],
        "command": command,
        "working_directory": str(wrf),
        "environment": env,
        "compile_invocations": 0,
        "model_invocations": 0,
    }
    if not args.compile_go:
        return {**common, "status": "READY_COMPILE_NOT_RUN"}

    (HERE / "tmp").mkdir(exist_ok=True)
    runner_pin = pin(Path(__file__))
    preparer_pin = pin(PREPARER)
    result = {**common, "status": "RUNNING", "compile_invocations": 1,
              "runner": runner_pin, "preparer": preparer_pin}
    with RESULT_PATH.open("x") as stream:
        stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    try:
        helper = p.import_donor_modules()[0]
        result["process"] = helper.bounded_process(command, wrf, env, LOG_PATH, TIMEOUT_S)
        text = LOG_PATH.read_text(errors="replace")
        log_status = helper.classify_build_log(text, result["process"]["returncode"])
        result["log_classification"] = log_status
        result["production_compile_commands"] = p.verify_compile_commands(LOG_PATH)
        generated_verifier = import_generated_verifier()
        result["generated_ccn"] = generated_verifier.verify_generated_sources(wrf)
        result["compiled_ccn"] = generated_verifier.verify_compiled_objects(wrf)
        executables = {}
        for name in ("wrf.exe", "real.exe", "ndown.exe", "tc.exe"):
            executable = wrf / "main" / name
            valid = executable.is_file() and executable.stat().st_size > 0
            if valid:
                with executable.open("rb") as stream:
                    valid = stream.read(4) == b"\x7fELF"
            if not valid:
                raise ValueError(f"fresh {name} is missing or is not an ELF executable")
            executables[name] = pin(executable)
        result["executables"] = executables
        result["wrf_executable"] = executables["wrf.exe"]
        result["status"] = (
            "BUILD_PASS" if result["process"]["returncode"] == 0
            and not result["process"]["timed_out"]
            and log_status["successful_footer"]
            and not log_status["errors"]
            else "BUILD_FAIL_PRESERVED"
        )
        if result["status"] != "BUILD_PASS":
            raise ValueError("compiler/build log did not satisfy the complete PASS contract")
    except Exception as exc:
        result["status"] = "BUILD_FAIL_PRESERVED"
        result["error"] = f"{type(exc).__name__}: {exc}"
    finally:
        try:
            result["source_unchanged"] = p.verify_staged_source(manifest) == staged
            if not result["source_unchanged"]:
                result["status"] = "BUILD_FAIL_PRESERVED"
        except Exception as exc:
            result["source_unchanged"] = False
            result["source_error"] = str(exc)
            result["status"] = "BUILD_FAIL_PRESERVED"
        try:
            result["dependencies_unchanged"] = p.import_dependency_inventory(spec) == dependencies
            if not result["dependencies_unchanged"]:
                result["status"] = "BUILD_FAIL_PRESERVED"
        except Exception as exc:
            result["dependencies_unchanged"] = False
            result["dependency_error"] = str(exc)
            result["status"] = "BUILD_FAIL_PRESERVED"
        if pin(Path(__file__)) != runner_pin or pin(PREPARER) != preparer_pin:
            result["status"] = "BUILD_FAIL_PRESERVED"
            result["harness_files_unchanged"] = False
        else:
            result["harness_files_unchanged"] = True
        with RESULT_PATH.open("w") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compile-go", action="store_true", help="launch the fresh GNU dm+sm WRF build")
    args = parser.parse_args()
    try:
        result = build(args)
    except FileExistsError as exc:
        print(json.dumps({"status": "OUTPUT_COLLISION", "error": str(exc),
                          "compile_invocations": 0, "model_invocations": 0}))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "SETUP_FAILED", "error": f"{type(exc).__name__}: {exc}",
                          "compile_invocations": 0, "model_invocations": 0}))
        return 1
    print(json.dumps({k: result.get(k) for k in ("status", "compile_invocations", "model_invocations", "command")}))
    return 0 if result["status"] in ("BUILD_PASS", "READY_COMPILE_NOT_RUN") else 1


if __name__ == "__main__":
    raise SystemExit(main())
