#!/usr/bin/env python3
"""Mutation controls for the saved-capsule verifier (stdlib only)."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run(package):
    return subprocess.run(
        [sys.executable, "-I", "-S", "-B", str(package / "verify_saved.py")],
        cwd="/tmp", capture_output=True, text=True, timeout=30,
    )


def copy_package(parent, name):
    target = parent / name
    shutil.copytree(HERE, target, ignore=shutil.ignore_patterns("__pycache__"))
    return target


def repin_manifest(package):
    integrity_path = package / "package-integrity.json"
    integrity = json.loads(integrity_path.read_text())
    integrity["files"]["manifest.json"] = digest(package / "manifest.json")
    integrity_path.write_text(json.dumps(integrity, sort_keys=True, indent=2) + "\n")


def main():
    with tempfile.TemporaryDirectory(prefix="lblrtm-pocket-mutations-") as td:
        root = Path(td)
        duplicate = copy_package(root, "duplicate-target")
        manifest_path = duplicate / "manifest.json"
        manifest = json.loads(manifest_path.read_text())
        manifest["selections"][-1] = dict(manifest["selections"][0])
        manifest_path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n")
        repin_manifest(duplicate)
        result = run(duplicate)
        assert result.returncode != 0 and "selection target roster" in result.stderr, result.stderr

        nested = copy_package(root, "nested-integrity")
        extra = nested / "unlisted" / "package-integrity.json"
        extra.parent.mkdir()
        extra.write_text("{}\n")
        result = run(nested)
        assert result.returncode != 0 and "closed package file roster" in result.stderr, result.stderr

    print("PASS_MUTATION_CONTROLS duplicate-target-and-nested-integrity-rejected")


if __name__ == "__main__":
    main()
