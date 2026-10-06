#!/usr/bin/env python3
"""Verify retained historical packages against their exact archived reader source.

No compiler or numerical engine is invoked. Historical package verifiers are
imported unchanged; their REPO root is mapped to a temporary dependency tree in
which only reference_column.f90 is supplied by the verified SHA-addressed archive.
"""
import hashlib
import importlib.util
import json
import os
import sys
import tempfile
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parents[3]
BASE = ROOT / "validation/rrtmgp37"
ARCHIVED_SHA = "6e82effd7d25242656858a8242c7e6941fced6aec0ec4d906762ef3ccb1b4ff0"
SOURCE_REL = Path("WRF/test/rrtmgp/reference_column.f90")
INDEX = BASE / "reference-source-archive" / f"sha256-{ARCHIVED_SHA}" / "archive-index.json"
SOURCE = INDEX.parent / "reference_column.f90"
HISTORICAL_ADAPTER_SHA = "b3932fa4e88202d5fe0fb660764bec9a07d031c03b501c20ee6ef259828ffa69"
ADAPTER_REL = Path("WRF/phys/module_ra_rrtmgp.F")
ADAPTER_INDEX = BASE / "reference-source-archive" / f"sha256-{HISTORICAL_ADAPTER_SHA}" / "archive-index.json"
ADAPTER_SOURCE = ADAPTER_INDEX.parent / "module_ra_rrtmgp.F"
ARCHIVED_DEPENDENCIES = {
    (SOURCE_REL, ARCHIVED_SHA): (SOURCE, 87769),
    (ADAPTER_REL, HISTORICAL_ADAPTER_SHA): (ADAPTER_SOURCE, 73930),
}
PACKAGES = (
    "bon-night-independent-replay",
    "bon-night-dry-column-attribution",
    "bon-night-lw-transport",
)


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load verifier module: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def verify_archive():
    index = json.loads(INDEX.read_text())
    if index.get("sha256") != ARCHIVED_SHA or index.get("size_bytes") != 87769:
        raise ValueError("archive index does not describe the expected historical reader")
    if sha(SOURCE) != ARCHIVED_SHA or SOURCE.stat().st_size != 87769:
        raise ValueError("archived source bytes do not match SHA-addressed archive")
    adapter_index = json.loads(ADAPTER_INDEX.read_text())
    if adapter_index.get("sha256") != HISTORICAL_ADAPTER_SHA or adapter_index.get("size_bytes") != 73930:
        raise ValueError("adapter archive index does not describe the historical adapter source")
    if sha(ADAPTER_SOURCE) != HISTORICAL_ADAPTER_SHA or ADAPTER_SOURCE.stat().st_size != 73930:
        raise ValueError("archived adapter bytes do not match SHA-addressed archive")
    return {"reference_column": index, "module_ra_rrtmgp": adapter_index}


def package_dependencies(package):
    roster_package = package
    if package == "bon-night-dry-column-attribution":
        # This package deliberately inherits the independent-replay dependency
        # roster rather than copying another source roster.
        roster_package = "bon-night-independent-replay"
    roster = json.loads((BASE / roster_package / "original-payload-roster.json").read_text())
    deps = roster["repository_dependencies"]
    ref = deps.get("current_reference_source")
    if not ref or ref.get("sha256") != ARCHIVED_SHA or ref.get("repository_relative_path") != SOURCE_REL.as_posix():
        raise ValueError(f"{package}: historical source dependency is not the archived SHA")
    return deps


def build_repo_mapping(tmp_root, dependencies):
    """Build a temporary repo-shaped tree; never modify the checkout."""
    mapped = {}
    for package, deps in dependencies.items():
        for name, rec in deps.items():
            rel = Path(rec["repository_relative_path"])
            dst = tmp_root / rel
            archived = ARCHIVED_DEPENDENCIES.get((rel, rec.get("sha256")))
            if archived:
                source, expected_size = archived
                if rec.get("size_bytes") != expected_size:
                    raise ValueError(f"historical archive size mismatch: {package}:{name}:{rel}")
                expected_sha = rec["sha256"]
            else:
                source = ROOT / rel
                expected_sha = rec["sha256"]
            if sha(source) != expected_sha or source.stat().st_size != rec["size_bytes"]:
                raise ValueError(f"dependency pin mismatch: {package}:{name}:{rel}")
            previous = mapped.get(rel)
            if previous and previous != expected_sha:
                raise ValueError(f"conflicting dependency pins for {rel}")
            mapped[rel] = expected_sha
            if dst.exists() or dst.is_symlink():
                if dst.resolve() != source.resolve():
                    raise ValueError(f"conflicting temporary dependency target: {rel}")
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.symlink_to(source)
    return mapped


def verify_all():
    index = verify_archive()
    dep_sets = {name: package_dependencies(name) for name in PACKAGES}
    summaries = []
    with tempfile.TemporaryDirectory(prefix="rrtmgp37-historical-reader-") as td:
        temp_root = Path(td)
        mapping = build_repo_mapping(temp_root, dep_sets)
        for package in PACKAGES:
            verifier = BASE / package / "verify.py"
            module = load_module("historical_verify_" + package.replace("-", "_"), verifier)
            module.REPO = temp_root
            result = module.verify()
            summaries.append({
                "package": package,
                "verifier_sha256": sha(verifier),
                "status": result.get("status"),
                "manifest_sha256": result.get("manifest_sha256"),
                "verified_payload_count": result.get("payload_count"),
                "historical_reader_sha256": ARCHIVED_SHA,
            })
    return {
        "schema": "rrtmgp37_historical_reference_package_verification_v1",
        "status": "PASS_THREE_HISTORICAL_PACKAGES_WITH_ARCHIVED_SOURCE_MAPPING",
        "archive_indexes": {"reference_column": sha(INDEX), "module_ra_rrtmgp": sha(ADAPTER_INDEX)},
        "archive_sources": {"reference_column": sha(SOURCE), "module_ra_rrtmgp": sha(ADAPTER_SOURCE)},
        "archived_source_count": len(ARCHIVED_DEPENDENCIES),
        "archive_sizes_bytes": {"reference_column": SOURCE.stat().st_size, "module_ra_rrtmgp": ADAPTER_SOURCE.stat().st_size},
        "repository_checkout_modified": False,
        "builds": 0,
        "solver_calls": 0,
        "temporary_dependency_count": len(mapping),
        "temporary_mapping_archived_dependencies": [
            {"path": rel.as_posix(), "sha256": digest, "source": str(path)}
            for (rel, digest), (path, _size) in ARCHIVED_DEPENDENCIES.items()
        ],
        "packages": summaries,
        "scope": "Runs unchanged offline artifact verifiers against archived historical reference_column bytes and current hash-checked non-reader dependencies. It validates retained artifact integrity, not current V12 source behavior or physical accuracy.",
        "archive": index,
    }


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    result = verify_all()
    if args.output:
        out = args.output.absolute()
        if out.exists():
            raise FileExistsError(out)
        out.parent.mkdir(parents=True, exist_ok=True)
        tmp = out.with_name(out.name + ".tmp")
        with tmp.open("x") as f:
            json.dump(result, f, indent=2, sort_keys=True, allow_nan=False)
            f.write("\n"); f.flush(); os.fsync(f.fileno())
        os.replace(tmp, out)
    print(json.dumps(result, sort_keys=True, allow_nan=False))


if __name__ == "__main__":
    main()
