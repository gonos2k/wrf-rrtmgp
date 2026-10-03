#!/usr/bin/env python3
"""Read-only provenance gate for the fresh CCN-tile-init GNU WRF build.

This does not stage cases or launch WRF. It accepts the original build receipt
only when a separate posthoc attestation explains its harness-only failure.
"""
from __future__ import annotations
import argparse, hashlib, json, os, re, subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / "build/udm37-ccn-tile-init-gnu-v1"
FREEZE = BUILD / "source-freeze-v1.json"
BUILD_RESULT = BUILD / "build-result-v1.json"
SOURCE_MANIFEST = BUILD / "source-manifest-v1.json"
DEP_MANIFEST = BUILD / "shared-dependencies-before-v1.json"
LOG = BUILD / "build-em_real-v1.log"
WRF = BUILD / "source/WRF/main/wrf.exe"
ATTESTATION = BUILD / "posthoc-v3/posthoc-attestation-v3.json"
VERIFIER = BUILD / "posthoc-v3/verify_ccn_build_v3.py"
EXPECTED_ATTESTATION_SHA = "6cb009bdaf649ac1add2dc26acc73315746824b4c256c47cbaa87730fda7b081"
EXPECTED_WRF_SHA = "c694e0bb05b5fa5b20ea6d0a6a7b07573572ebc9c79f976499808eb820b12658"
EXPECTED_WRF_SIZE = 59010648
EXPECTED_SOURCE_MANIFEST_SHA = "da7f8daeb1a7a07be284f84d1a0252f1b41a31d7ee6d9ab029e3b8afd90feda1"
EXPECTED_DEP_MANIFEST_SHA = "e49061863c79e836747d21559950b90e2f6d40b798dbbc8d08895d1cf4a87290"
EXPECTED_LOG_SHA = "e7cde20caeb447ef496f774eae1172108766b9cf9a4162cf7d33dff1e1ba2faa"
EXPECTED_ATTESTATION_SHA = "6cb009bdaf649ac1add2dc26acc73315746824b4c256c47cbaa87730fda7b081"
COMPILED_PATHS = (
    "WRF/phys/module_microphysics_driver.F",
    "WRF/phys/module_mp_udm.F",
)

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for b in iter(lambda: f.read(1024 * 1024), b""):
            h.update(b)
    return h.hexdigest()

def pin(path: Path) -> dict:
    st = path.stat()
    return {"path": str(path.resolve()), "size_bytes": st.st_size, "sha256": sha(path)}

def require_pin(path: Path, expected_sha: str, expected_size: int | None = None):
    p = pin(path)
    if p["sha256"] != expected_sha or (expected_size is not None and p["size_bytes"] != expected_size):
        raise ValueError(f"pin mismatch: {path}")
    return p

def check_source_manifest(manifest: dict, root: Path):
    checked = 0
    for ent in manifest["files"]:
        p = root / ent["path"]
        if ent["type"] == "file":
            if not p.is_file() or p.stat().st_size != ent["size"] or sha(p) != ent["sha256"]:
                raise ValueError(f"source file changed: {ent['path']}")
        elif ent["type"] == "symlink":
            if not p.is_symlink() or os.readlink(p) != ent["target"]:
                raise ValueError(f"source symlink changed: {ent['path']}")
        else:
            raise ValueError(f"unknown source entry kind: {ent['type']}")
        checked += 1
    if checked != 6735 or manifest["entry_count"] != checked:
        raise ValueError(f"source roster count mismatch: {checked}")
    return checked

def check_dependencies(dep: dict):
    checked = 0
    for entry in dep["files"]:
        if entry["kind"] == "file":
            p = entry["file"]
            path = Path(p["path"])
            if not path.is_file() or path.stat().st_size != p["size_bytes"] or sha(path) != p["sha256"]:
                raise ValueError(f"shared dependency changed: {path}")
        elif entry["kind"] == "symlink":
            l = entry["link"]
            path = Path(entry["path"])
            if not path.is_symlink() or os.readlink(path) != l["link_text"]:
                raise ValueError(f"dependency symlink changed: {path}")
        else:
            raise ValueError(f"unknown dependency entry kind: {entry['kind']}")
        checked += 1
    if checked != 1582:
        raise ValueError(f"dependency roster count mismatch: {checked}")
    return checked

def current_ldd(binary: Path):
    out = subprocess.run(["ldd", str(binary)], check=True, text=True, capture_output=True).stdout
    libs = {}
    for line in out.splitlines():
        m = re.match(r"\s*(\S+)\s+=>\s+(\S+)", line)
        if m:
            if m.group(2) == "not":
                raise ValueError("unresolved runtime dependency: " + line.strip())
            p = Path(m.group(2))
            if not p.is_file():
                raise ValueError("missing runtime dependency: " + str(p))
            libs[m.group(1)] = pin(p)
    return libs

def verify_build(attestation_path: Path = ATTESTATION):
    freeze = json.loads(FREEZE.read_text())
    result = json.loads(BUILD_RESULT.read_text())
    if freeze["base_commit"] != "4394845667db52c258dab62719abc87402dd731f":
        raise ValueError("unexpected physical-source base")
    source_pin = require_pin(SOURCE_MANIFEST, EXPECTED_SOURCE_MANIFEST_SHA)
    dep_pin = require_pin(DEP_MANIFEST, EXPECTED_DEP_MANIFEST_SHA)
    log_pin = require_pin(LOG, EXPECTED_LOG_SHA)
    if result["status"] != "BUILD_FAIL_PRESERVED" or result["process"]["returncode"] != 0:
        raise ValueError("original build receipt no longer matches reviewed harness-failure case")
    if not result["log_classification"]["passed"] or not result["log_classification"]["successful_footer"]:
        raise ValueError("compiler log is not classified successful")
    if not attestation_path.is_file():
        raise ValueError("posthoc build attestation not yet available")
    att = json.loads(attestation_path.read_text())
    if att.get("schema") != "udm37-ccn-gnu-dm-sm-posthoc-attestation-v3" or att.get("status") != "POSTHOC_BUILD_ATTESTED_ORIGINAL_RUNNER_FAILURE_PRESERVED":
        raise ValueError("posthoc attestation is not the accepted harness-only classification")
    if sha(attestation_path) != EXPECTED_ATTESTATION_SHA:
        raise ValueError("posthoc attestation pin differs")
    att_bin = att.get("full_build_executables", {}).get("wrf.exe", {})
    if att_bin.get("sha256") != EXPECTED_WRF_SHA or att.get("original_v1_harness_failure") != "AttributeError: module 'prepare_ccn_source_v1' has no attribute 'verify_compile_commands'":
        raise ValueError("attestation binary identity differs")
    if att.get("original_v1_receipt", {}).get("sha256") != sha(BUILD_RESULT):
        raise ValueError("attestation does not bind the preserved original build receipt")
    if att.get("source_manifest", {}).get("sha256") != EXPECTED_SOURCE_MANIFEST_SHA:
        raise ValueError("attested source manifest differs")
    if att.get("dependency_inventory", {}).get("sha256") != EXPECTED_DEP_MANIFEST_SHA or not att["dependency_inventory"].get("matches_frozen_before_after"):
        raise ValueError("attested dependency inventory differs")
    binary_pin = require_pin(WRF, EXPECTED_WRF_SHA, EXPECTED_WRF_SIZE)
    root = Path(json.loads(SOURCE_MANIFEST.read_text())["source_path"])
    source_doc = json.loads(SOURCE_MANIFEST.read_text())
    source_count = check_source_manifest(source_doc, root)
    overlays = freeze["source_overlays"]
    for rel in COMPILED_PATHS:
        expected = overlays[rel]
        if pin(root / rel)["sha256"] != expected["sha256"]:
            raise ValueError("compiled production overlay mismatch: " + rel)
    configure = freeze["configure_template"]
    configure_pin = require_pin(Path(configure["path"]), configure["sha256"], configure["size_bytes"])
    dep_count = check_dependencies(json.loads(DEP_MANIFEST.read_text()))
    import importlib.util
    base_path = ROOT / "build/udm-cu-current-omp-runtime-v2/runtime.py"
    if sha(base_path) != "126775590ee39f9c9170024f1b498ce2df86eee19654950b89e4ba92fdedb52a":
        raise ValueError("shared runtime helper changed")
    spec = importlib.util.spec_from_file_location("pinned_ccn_runtime", base_path)
    base = importlib.util.module_from_spec(spec); spec.loader.exec_module(base)
    _, _, runargs = base.parent()
    libs = base.m.library_pins(WRF, runargs.ld_library_path)
    # Revalidate every artifact the posthoc verifier actually compiled/linked,
    # not only the selected WRF executable.
    for item in att["generated_ccn_source"]["driver"], att["generated_ccn_source"]["udm"]:
        if pin(Path(item["path"])) != item:
            raise ValueError("generated Fortran source changed: " + item["path"])
    objects = att["compiled_ccn_objects"]
    if objects["external_rte_object_count"] != 25 or len(objects["external_rte_objects"]) != 25:
        raise ValueError("unexpected external RRTMGP object roster")
    object_pins = [objects["driver_object"], objects["udm_object"]]
    object_pins.extend({**item, "path": str(root / "WRF/external/rte_rrtmgp/build" / item["name"])} for item in objects["external_rte_objects"])
    for item in object_pins:
        path = Path(item["path"])
        if pin(path)["sha256"] != item["sha256"] or path.stat().st_size != item["size_bytes"]:
            raise ValueError("compiled object changed: " + str(path))
    executables = {}
    for name, item in att["full_build_executables"].items():
        current = pin(Path(item["path"]))
        if current != item:
            raise ValueError("full-build executable changed: " + name)
        executables[name] = current
    if executables.get("wrf.exe") != binary_pin:
        raise ValueError("selected executable differs from attested full-build executable")
    return {
        "status": "PASS_POSTHOC_BUILD_IDENTITY",
        "attestation": pin(attestation_path), "attestation_verifier": pin(VERIFIER), "original_build_result": pin(BUILD_RESULT),
        "binary": binary_pin, "source_manifest": source_pin, "source_entries_checked": source_count,
        "dependencies": dep_pin, "dependency_entries_checked": dep_count,
        "configure": configure_pin, "build_log": log_pin, "ldd_libraries": libs,
        "generated_ccn_source": att["generated_ccn_source"], "compiled_object_pins": object_pins,
        "full_build_executables": executables,
        "excluded_current_metadata": freeze["test_only_exclusions"],
    }

def verify_donor_inputs():
    """Authenticate accepted parent runs without trusting their old executable as candidate."""
    base = ROOT / "build/udm-seaice-winter-validation-v3"
    specs = {
        "ra37": (base / "ra37-24h-v1/execution-receipt-v1.json", "150313d70a2a9e3274aed66703e671a22b40338cb5439bb32fb4770324eeabef", "PASS_RA37_24H"),
        "ra4": (base / "ra4-24h-v1/execution-receipt-v1.json", "4073ad6101c06b0f81ac9e2dd4f2dd94b095dac642a79e1e1fab49133bfa8647", "PASS_RA4_24H"),
    }
    out = {}
    for name, (path, expected_sha, expected_status) in specs.items():
        if not path.is_file():
            # RA4's receipt location may be named differently; do not silently pass.
            raise ValueError(f"donor receipt not found for {name}: {path}")
        doc = json.loads(path.read_text())
        if doc.get("status") != expected_status:
            raise ValueError(f"donor run not accepted: {name}")
        if expected_sha and sha(path) != expected_sha:
            raise ValueError(f"donor receipt hash mismatch: {name}")
        if doc.get("actual_model_invocations") != 1 or not doc.get("before_pins_valid") or not doc.get("after_pins_valid"):
            raise ValueError(f"donor receipt lacks accepted before/after integrity: {name}")
        if pin(Path(doc["runner"]["path"])) != doc["runner"]:
            raise ValueError(f"donor runner changed: {name}")
        if pin(Path(doc["stage_receipt"]["path"])) != doc["stage_receipt"]:
            raise ValueError(f"donor stage receipt changed: {name}")
        if doc.get("outputs", {}).get("history", {}).get("file"):
            x = doc["outputs"]["history"]["file"]
            if pin(Path(x["path"])) != x:
                raise ValueError(f"donor history changed: {name}")
        out[name] = {"receipt": pin(path), "status": doc["status"], "stage_receipt": doc["stage_receipt"], "runner": doc["runner"]}
    return out

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--attestation", type=Path, default=ATTESTATION)
    p.add_argument("--output", type=Path)
    a = p.parse_args()
    r = {"build": verify_build(a.attestation)}
    if a.output:
        a.output.write_text(json.dumps(r, indent=2) + "\n")
    print(json.dumps({"status": r["build"]["status"], "binary": r["build"]["binary"]}, indent=2))

if __name__ == "__main__":
    main()
