#!/usr/bin/env python3
"""Prepare-only GNU dm+sm WRF source harness for the option-37 CCN init fix.

Default operation validates the frozen donor/source/dependency inputs only.
Copying a fresh source tree requires the explicit --prepare-source-go flag.
This script never compiles WRF and never launches a model.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
WORKTREE = ROOT / "build/udm37-ccn-tile-init-work"
BASE = "4394845667db52c258dab62719abc87402dd731f"
ROOT_FREEZE = ROOT / "build/udm37-ccn-tile-init-root-freeze-v1.json"
ROOT_FREEZE_SHA = "58debad0e6b7642122b2739ac60c2490eaf94114d7d90822eba2832dd9968281"
OLD = ROOT / "build/udm-seaice-fresh-gnu-dm-sm-v1"
SPEC_PATH = HERE / "source-freeze-v1.json"
DONOR_MANIFEST = HERE / "donor-source-manifest-v1.json"
DONOR_ROOT = OLD / "source"
DEPS_PIN = HERE / "shared-dependencies-before-v1.json"
CONFIGURE = HERE / "configure-template.wrf"
DONOR_EQUIVALENCE = HERE / "donor-base-equivalence-v1.json"
OUTPUT_SOURCE = HERE / "source"
MANIFEST_PATH = HERE / "source-manifest-v1.json"
RECEIPT_PATH = HERE / "source-preparation-v1.json"
TARGET_PATHS = (
    "WRF/phys/module_microphysics_driver.F",
    "WRF/phys/module_mp_udm.F",
)
TEST_ONLY_TRACKED = "WRF/test/rrtmgp/CMakeLists.txt"
TEST_ONLY_UNTRACKED = (
    "WRF/test/rrtmgp/UDM_CCN_STARTUP.md",
    "WRF/test/rrtmgp/ccn_startup_fixture.f90.in",
    "WRF/test/rrtmgp/test_udm_ccn_startup.py",
)
DONOR_SPEC = OLD / "runner-source-freeze-spec-v2.json"
DONOR_PREP = OLD / "prepare_source_v1.py"
DONOR_HELPER = ROOT / "build/udm-seaice-winter-validation-v1/winter_validation_v1.py"
DONOR_BUILD = OLD / "source/WRF/external/rte_rrtmgp/build"


def digest_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def digest_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pin(path: Path) -> dict[str, Any]:
    resolved = path.resolve(strict=True)
    if not resolved.is_file():
        raise ValueError(f"not a regular file: {resolved}")
    return {"path": str(resolved), "size_bytes": resolved.stat().st_size,
            "sha256": digest_file(resolved)}


def run_git(*args: str) -> str:
    return subprocess.check_output(["git", "-C", str(WORKTREE), *args], text=True).strip()


def import_donor_modules():
    for path, expected in ((DONOR_HELPER, "6f66046e785fc5ef69f317daa3ca63a09a4cfab0839a67bea9703ce21691a4e8"),
                           (DONOR_PREP, "9062a5e8e21ce1b5efc3750101ef5e4ae4588c389a7f250e36d3e5703f533bde")):
        if digest_file(path) != expected:
            raise ValueError(f"pinned prior harness changed: {path}")
    hs = importlib.util.spec_from_file_location("winter_validation_v1", DONOR_HELPER)
    helper = importlib.util.module_from_spec(hs)
    assert hs.loader
    hs.loader.exec_module(helper)
    ps = importlib.util.spec_from_file_location("donor_prepare_source_v1", DONOR_PREP)
    preparer = importlib.util.module_from_spec(ps)
    assert ps.loader
    ps.loader.exec_module(preparer)
    return helper, preparer


def load_spec() -> tuple[dict[str, Any], dict[str, Any]]:
    spec_pin = pin(SPEC_PATH)
    spec = json.loads(SPEC_PATH.read_text())
    if spec.get("schema") != "udm37-ccn-gnu-dm-sm-source-freeze-v1":
        raise ValueError("unexpected source freeze schema")
    if spec.get("base_commit") != BASE:
        raise ValueError("wrong pinned parent commit")
    for key, path in (("donor_base_equivalence_pin", DONOR_EQUIVALENCE),
                      ("root_freeze_pin", ROOT_FREEZE)):
        expected = spec.get(key, {})
        actual = pin(path)
        if {k: actual[k] for k in ("path", "size_bytes", "sha256")} != expected:
            raise ValueError(f"frozen input changed: {path}")
    return spec, spec_pin


def validate_donor_equivalence() -> dict[str, Any]:
    record = json.loads(DONOR_EQUIVALENCE.read_text())
    if (record.get("status") != "PASS" or record.get("base_commit") != BASE
            or record.get("donor_entry_count") != 6735
            or record.get("matched_content_entries") != 6734
            or record.get("matched_base_entries") != 6735
            or record.get("base_commit_extra_count") != 11):
        raise ValueError("donor/base equivalence audit is incomplete or failed")
    if len(record.get("entries", [])) != 6734:
        raise ValueError("donor/base equivalence audit lacks its per-entry records")
    return {"path": str(DONOR_EQUIVALENCE), "sha256": digest_file(DONOR_EQUIVALENCE),
            "matched_content_entries": len(record["entries"]),
            "base_commit_extra_paths": record["base_commit_extra_paths_excluded"]}


def validate_patch(worktree: Path = WORKTREE) -> dict[str, Any]:
    if worktree.resolve(strict=True) != WORKTREE.resolve(strict=True):
        raise ValueError("source worktree path differs from frozen input")
    head = subprocess.check_output(["git", "-C", str(worktree), "rev-parse", "HEAD"], text=True).strip()
    if head != BASE:
        raise ValueError(f"source base moved: {head}")
    unstaged = subprocess.check_output(
        ["git", "-C", str(worktree), "diff", "--name-only", "HEAD"], text=True
    ).splitlines()
    staged = subprocess.check_output(
        ["git", "-C", str(worktree), "diff", "--cached", "--name-only"], text=True
    ).splitlines()
    if set(unstaged) != set(TARGET_PATHS) | {TEST_ONLY_TRACKED} or len(unstaged) != len(TARGET_PATHS) + 1:
        raise ValueError(f"expected two CCN production files and one test-only registration change, got {unstaged}")
    if staged:
        raise ValueError(f"staged changes are not part of this preparation: {staged}")
    root_freeze = json.loads(ROOT_FREEZE.read_text())
    if digest_file(ROOT_FREEZE) != ROOT_FREEZE_SHA or root_freeze.get("status") != "ROOT_PRODUCTION_FROZEN":
        raise ValueError("root production freeze changed or is not final")
    if root_freeze.get("base_commit") != BASE or Path(root_freeze.get("worktree", "")).resolve() != WORKTREE.resolve():
        raise ValueError("source tree differs from root production freeze")
    status = subprocess.check_output(
        ["git", "-C", str(worktree), "status", "--porcelain", "--untracked-files=all"], text=True
    ).splitlines()
    expected_status = {" M " + x for x in (*TARGET_PATHS, TEST_ONLY_TRACKED)}
    expected_status.update("?? " + x for x in TEST_ONLY_UNTRACKED)
    if set(status) != expected_status:
        raise ValueError(f"unexpected source status: {status}")
    test_registration = subprocess.check_output(
        ["git", "-C", str(worktree), "diff", "--unified=0", "HEAD", "--", TEST_ONLY_TRACKED],
        text=True,
    )
    if (test_registration.count("+add_test(NAME udm_ccn_tile_startup") != 1
            or "test_udm_ccn_startup.py" not in test_registration
            or re.search(r"^\+[^+].*[^\s]$", test_registration, re.M) is None):
        raise ValueError("unexpected CMake test-only diff; expected the single udm_ccn_tile_startup registration")

    driver = (worktree / TARGET_PATHS[0]).read_text(errors="strict")
    udm = (worktree / TARGET_PATHS[1]).read_text(errors="strict")
    checks = {
        "driver_sets_full_domain_before_openmp_loop": (
            "QNN_CURR(ims:ime,kms:kme,jms:jme) = ccn_conc" in driver
            and driver.index("QNN_CURR(ims:ime,kms:kme,jms:jme) = ccn_conc")
            < driver.index("!$OMP PARALLEL DO")
        ),
        "option37_call_passes_preinitialized_keyword": ",ccn_preinitialized=.true." in driver,
        "udm_optional_argument_declared": "logical, optional, intent(in) :: ccn_preinitialized" in udm,
        "legacy_default_kept_when_argument_absent": (
            "initialize_ccn = .true." in udm
            and "if (present(ccn_preinitialized)) initialize_ccn = .not. ccn_preinitialized" in udm
            and "if (itimestep==1 .and. initialize_ccn) then" in udm
        ),
    }
    if not all(checks.values()):
        raise ValueError(f"CCN patch source contract failed: {checks}")
    diff = subprocess.check_output(
        ["git", "-C", str(worktree), "diff", "--binary", "HEAD", "--", *TARGET_PATHS]
    )
    current_files = [pin(worktree / x) for x in TARGET_PATHS]
    for p in current_files:
        rel = str(Path(p["path"]).relative_to(worktree))
        expected = root_freeze.get("overlays", {}).get(rel, {})
        if p["sha256"] != expected.get("sha256") or p["size_bytes"] != expected.get("size_bytes"):
            raise ValueError(f"source file differs from root frozen overlay: {rel}")
    return {
        "head": head,
        "status": status,
        "root_freeze": pin(ROOT_FREEZE),
        "files": current_files,
        "patch_sha256": digest_bytes(diff),
        "patch_size_bytes": len(diff),
        "checks": checks,
        "excluded_test_only_worktree_changes": {
            "tracked_cmake_registration": TEST_ONLY_TRACKED,
            "untracked_test_files": list(TEST_ONLY_UNTRACKED),
            "reason": "CMake/Python fixture additions are not inputs to the classic GNU ./compile em_real build; the 6735-entry donor roster is retained unchanged apart from the two production overlays.",
        },
    }


def load_donor_manifest() -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_pin = pin(DONOR_MANIFEST)
    data = json.loads(DONOR_MANIFEST.read_text())
    if data.get("entry_count") != 6735 or len(data.get("files", [])) != 6735:
        raise ValueError("donor source manifest must contain exactly 6735 entries")
    if data.get("symlink_count") != 17:
        raise ValueError("donor source manifest symlink roster changed")
    paths = [x["path"] for x in data["files"]]
    if len(paths) != len(set(paths)):
        raise ValueError("duplicate donor paths")
    for rel in paths:
        p = Path(rel)
        if p.is_absolute() or ".." in p.parts or not rel:
            raise ValueError(f"unsafe donor relative path: {rel}")
    if "WRF/configure.wrf" not in paths:
        raise ValueError("donor manifest lacks the frozen configure.wrf")
    for rel in TARGET_PATHS:
        if rel not in paths:
            raise ValueError(f"CCN overlay path missing from donor manifest: {rel}")
    return data, manifest_pin


def verify_donor_files(data: dict[str, Any], check_content: bool = True) -> dict[str, Any]:
    file_count = symlink_count = 0
    for entry in data["files"]:
        path = DONOR_ROOT / entry["path"]
        if entry["type"] == "file":
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"donor file missing or replaced: {entry['path']}")
            if path.stat().st_size != entry["size"]:
                raise ValueError(f"donor size mismatch: {entry['path']}")
            if check_content and digest_file(path) != entry["sha256"]:
                raise ValueError(f"donor hash mismatch: {entry['path']}")
            file_count += 1
        elif entry["type"] == "symlink":
            if not path.is_symlink() or os.readlink(path) != entry["target"]:
                raise ValueError(f"donor symlink mismatch: {entry['path']}")
            symlink_count += 1
        else:
            raise ValueError(f"unsupported donor entry type: {entry['type']}")
    return {"files": file_count, "symlinks": symlink_count,
            "entries": file_count + symlink_count}


def canonical_manifest(data: dict[str, Any], overlay: dict[str, Any], source_path: Path) -> dict[str, Any]:
    files = []
    overlay_by_path = {x["relative_path"]: x for x in overlay["files"]}
    for entry in data["files"]:
        out = dict(entry)
        if entry["path"] in overlay_by_path:
            pin_entry = overlay_by_path[entry["path"]]["current_worktree_file"]
            out["size"] = pin_entry["size_bytes"]
            out["sha256"] = pin_entry["sha256"]
            out["provenance"] = "CCN option-37 patch overlay"
        else:
            out["provenance"] = "authenticated 6735-entry donor manifest"
        files.append(out)
    return {
        "schema": "udm37-ccn-source-manifest-v1",
        "base_commit": BASE,
        "source_path": str(source_path),
        "entry_count": len(files),
        "symlink_count": data["symlink_count"],
        "donor_manifest": pin(DONOR_MANIFEST),
        "excluded_current_commit_paths": [
            "validation/rrtmgp37/fractional-seaice-state/* (11 evidence-only files absent from frozen compiler donor roster)"
        ],
        "overlay_paths": sorted(overlay_by_path),
        "files": files,
    }


def import_dependency_inventory(spec: dict[str, Any]) -> dict[str, Any]:
    _, preparer = import_donor_modules()
    computed = preparer.dependencies(spec)
    saved = json.loads(DEPS_PIN.read_text())
    if computed != saved:
        raise ValueError("GNU/MPICH/NetCDF dependency inventory differs from the frozen 1582-entry baseline")
    if len(computed["files"]) != 1582:
        raise ValueError("dependency inventory count is not 1582")
    return computed


def validate_configure() -> dict[str, Any]:
    spec = json.loads(SPEC_PATH.read_text())
    current = pin(CONFIGURE)
    if current != spec["configure_template"]:
        raise ValueError("GNU dm+sm configure.wrf changed")
    active_lines = [line.split("#", 1)[0] for line in CONFIGURE.read_text().splitlines()]
    active = "\n".join(active_lines)
    required = ("-DDM_PARALLEL", "-fopenmp", "NETCDF", "mpif90", "gfortran")
    missing = [token for token in required if token not in active]
    if missing:
        raise ValueError(f"configure is not the expected GNU dm+sm build: missing {missing}")
    return {"pin": current, "required_markers": list(required), "markers_pass": True}


def current_overlay() -> dict[str, Any]:
    validated = validate_patch()
    files = []
    for p in validated["files"]:
        files.append({"relative_path": str(Path(p["path"]).relative_to(WORKTREE)),
                      "current_worktree_file": p})
    return {"files": files, "patch_sha256": validated["patch_sha256"],
            "patch_size_bytes": validated["patch_size_bytes"], "checks": validated["checks"]}


def validate_inputs(full_hash: bool = True) -> dict[str, Any]:
    spec, spec_pin = load_spec()
    overlay = current_overlay()
    donor, donor_pin = load_donor_manifest()
    donor_check = verify_donor_files(donor, check_content=full_hash)
    configure = validate_configure()
    dependencies = import_dependency_inventory(spec)
    canonical = canonical_manifest(donor, overlay, OUTPUT_SOURCE)
    return {
        "status": "READY_SOURCE_INPUTS_NOT_STAGED",
        "freeze_spec": spec_pin,
        "parent_commit": BASE,
        "root_production_freeze": pin(ROOT_FREEZE),
        "source_worktree": str(WORKTREE),
        "source_overlay": overlay,
        "donor_source_manifest": donor_pin,
        "donor_source_content_check": donor_check,
        "donor_base_equivalence": validate_donor_equivalence(),
        "canonical_source_manifest_preview": {
            "entry_count": canonical["entry_count"],
            "symlink_count": canonical["symlink_count"],
            "overlay_paths": canonical["overlay_paths"],
            "planned_manifest_sha256": digest_bytes(json.dumps(canonical, sort_keys=True).encode()),
        },
        "configure": configure,
        "shared_dependencies": pin(DEPS_PIN),
        "dependency_count": len(dependencies["files"]),
        "dependency_inventory_sha256": digest_file(DEPS_PIN),
        "external_rte_objects_expected": spec["external_rte_object_names"],
        "external_rte_object_count_expected": len(spec["external_rte_object_names"]),
        "compile_invocations": 0,
        "model_invocations": 0,
        "source_staged": False,
    }


def copy_donor_tree(data: dict[str, Any], dest: Path) -> None:
    if dest.exists() or dest.is_symlink():
        raise FileExistsError(f"fresh source destination already exists: {dest}")
    dest.mkdir(parents=True)
    for entry in data["files"]:
        rel = entry["path"]
        src = DONOR_ROOT / rel
        out = dest / rel
        out.parent.mkdir(parents=True, exist_ok=True)
        if entry["type"] == "symlink":
            out.symlink_to(entry["target"])
        else:
            shutil.copy2(src, out)
            if out.stat().st_size != entry["size"] or digest_file(out) != entry["sha256"]:
                raise ValueError(f"donor changed during source copy: {rel}")
    for rel in TARGET_PATHS:
        target = dest / rel
        shutil.copy2(WORKTREE / rel, target)
        overlay = next(x for x in current_overlay()["files"] if x["relative_path"] == rel)
        if pin(target)["sha256"] != overlay["current_worktree_file"]["sha256"]:
            raise ValueError(f"CCN source overlay changed during copy: {rel}")


def verify_staged_source(manifest: dict[str, Any]) -> dict[str, Any]:
    source = Path(manifest["source_path"])
    files = symlinks = 0
    for entry in manifest["files"]:
        path = source / entry["path"]
        if entry["type"] == "symlink":
            if not path.is_symlink() or os.readlink(path) != entry["target"]:
                raise ValueError(f"staged symlink mismatch: {entry['path']}")
            symlinks += 1
        else:
            if path.is_symlink() or not path.is_file():
                raise ValueError(f"staged source file missing: {entry['path']}")
            if path.stat().st_size != entry["size"] or digest_file(path) != entry["sha256"]:
                raise ValueError(f"staged source hash mismatch: {entry['path']}")
            files += 1
    if files + symlinks != manifest["entry_count"] or symlinks != manifest["symlink_count"]:
        raise ValueError("staged source manifest counts mismatch")
    return {"files": files, "symlinks": symlinks, "entries": files + symlinks}


def assert_no_preexisting_build_outputs(source: Path) -> None:
    roots = (source / "WRF/phys", source / "WRF/main", source / "WRF/external/rte_rrtmgp/build")
    for rel in ("WRF/phys/module_mp_udm.o", "WRF/phys/module_microphysics_driver.o",
                "WRF/phys/module_mp_udm.f90", "WRF/phys/module_microphysics_driver.f90",
                "WRF/main/wrf.exe", "WRF/main/real.exe", "WRF/main/ndown.exe", "WRF/main/tc.exe"):
        if (source / rel).exists():
            raise ValueError(f"staged source contains a preexisting build output: {rel}")
    for root in roots:
        if root.exists():
            stale = next((p for p in root.glob("*.o") if p.is_file()), None)
            if stale:
                raise ValueError(f"staged source contains stale object file: {stale.relative_to(source)}")


def prepare_source(args: argparse.Namespace) -> dict[str, Any]:
    preflight = validate_inputs(full_hash=True)
    if not args.prepare_source_go:
        return preflight
    if OUTPUT_SOURCE.exists() or OUTPUT_SOURCE.is_symlink() or MANIFEST_PATH.exists() or RECEIPT_PATH.exists():
        raise FileExistsError("source/manifest/receipt collision; use a new versioned output directory")
    donor, _ = load_donor_manifest()
    start = __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat()
    try:
        copy_donor_tree(donor, OUTPUT_SOURCE)
        overlay = current_overlay()
        manifest = canonical_manifest(donor, overlay, OUTPUT_SOURCE)
        manifest["donor_content_verified"] = preflight["donor_source_content_check"]
        manifest["configure_template"] = preflight["configure"]["pin"]
        with MANIFEST_PATH.open("x") as stream:
            stream.write(json.dumps(manifest, indent=2, sort_keys=True) + "\n")
        staged = verify_staged_source(manifest)
        assert_no_preexisting_build_outputs(OUTPUT_SOURCE)
        dependencies_after = import_dependency_inventory(json.loads(SPEC_PATH.read_text()))
        if dependencies_after != json.loads(DEPS_PIN.read_text()):
            raise ValueError("shared dependencies changed during source preparation")
        result = {
            "status": "SOURCE_PREPARED_NOT_BUILT",
            "started_utc": start,
            "ended_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "freeze_spec": pin(SPEC_PATH),
            "source_manifest": pin(MANIFEST_PATH),
            "source_manifest_counts": staged,
            "donor_source_manifest": preflight["donor_source_manifest"],
            "overlay": preflight["source_overlay"],
            "configure": preflight["configure"],
            "shared_dependencies": preflight["shared_dependencies"],
            "external_rte_objects_expected": preflight["external_rte_objects_expected"],
            "compile_command_for_later_review": ["csh", "-f", "./compile", "-j", "12", "em_real"],
            "compile_invocations": 0,
            "model_invocations": 0,
        }
        with RECEIPT_PATH.open("x") as stream:
            stream.write(json.dumps(result, indent=2, sort_keys=True) + "\n")
        return result
    except Exception as exc:
        failure = {
            "status": "SOURCE_PREPARATION_FAILED_PRESERVED",
            "started_utc": start,
            "ended_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
            "error": f"{type(exc).__name__}: {exc}",
            "compile_invocations": 0,
            "model_invocations": 0,
        }
        if not RECEIPT_PATH.exists():
            with RECEIPT_PATH.open("x") as stream:
                stream.write(json.dumps(failure, indent=2, sort_keys=True) + "\n")
        raise


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prepare-source-go", action="store_true",
                        help="copy exactly the authenticated donor manifest plus the two pinned source overlays")
    args = parser.parse_args()
    try:
        result = prepare_source(args)
    except FileExistsError as exc:
        print(json.dumps({"status": "OUTPUT_COLLISION", "error": str(exc), "compile_invocations": 0,
                          "model_invocations": 0}))
        return 2
    except Exception as exc:
        print(json.dumps({"status": "SETUP_FAILED", "error": f"{type(exc).__name__}: {exc}",
                          "compile_invocations": 0, "model_invocations": 0}))
        return 1
    print(json.dumps({k: result.get(k) for k in ("status", "source_staged", "compile_invocations", "model_invocations", "canonical_source_manifest_preview")}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
