#!/usr/bin/env python3
"""Offline archive resolution and tamper controls; no builds or solvers."""
import importlib.util
import hashlib
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
spec = importlib.util.spec_from_file_location("historical_package_verifier", P / "verify_historical_packages.py")
v = importlib.util.module_from_spec(spec); sys.modules[spec.name] = v; spec.loader.exec_module(v)

class ArchiveControls(unittest.TestCase):
    def test_payload_manifest_hashes(self):
        manifest = json.loads((P / "artifact-manifest.json").read_text())
        expected = {"README.md", "historical-verification.json", "test_verify_historical_packages.py",
                    "verify_historical_packages.py",
                    "sha256-6e82effd7d25242656858a8242c7e6941fced6aec0ec4d906762ef3ccb1b4ff0/archive-index.json",
                    "sha256-6e82effd7d25242656858a8242c7e6941fced6aec0ec4d906762ef3ccb1b4ff0/reference_column.f90",
                    "sha256-b3932fa4e88202d5fe0fb660764bec9a07d031c03b501c20ee6ef259828ffa69/archive-index.json",
                    "sha256-b3932fa4e88202d5fe0fb660764bec9a07d031c03b501c20ee6ef259828ffa69/module_ra_rrtmgp.F"}
        self.assertEqual({x["path"] for x in manifest["files"]}, expected)
        for row in manifest["files"]:
            path = P / row["path"]
            self.assertEqual(hashlib.sha256(path.read_bytes()).hexdigest(), row["sha256"])
            self.assertEqual(path.stat().st_size, row["size_bytes"])

    def test_archived_source_matches_historical_sha(self):
        indexes = v.verify_archive()
        self.assertEqual(indexes["reference_column"]["sha256"], v.ARCHIVED_SHA)
        self.assertEqual(indexes["module_ra_rrtmgp"]["sha256"], v.HISTORICAL_ADAPTER_SHA)

    def test_every_target_verifier_depends_on_same_archived_source(self):
        for package in v.PACKAGES:
            deps = v.package_dependencies(package)
            self.assertEqual(deps["current_reference_source"]["sha256"], v.ARCHIVED_SHA)

    def test_mapping_uses_archive_for_source_dependency(self):
        with tempfile.TemporaryDirectory() as td:
            deps = {p: v.package_dependencies(p) for p in v.PACKAGES}
            v.build_repo_mapping(Path(td), deps)
            mapped = Path(td) / v.SOURCE_REL
            self.assertTrue(mapped.is_symlink())
            self.assertEqual(v.sha(mapped), v.ARCHIVED_SHA)
            self.assertEqual(mapped.resolve(), v.SOURCE.resolve())
            adapter = Path(td) / v.ADAPTER_REL
            self.assertTrue(adapter.is_symlink())
            self.assertEqual(v.sha(adapter), v.HISTORICAL_ADAPTER_SHA)
            self.assertEqual(adapter.resolve(), v.ADAPTER_SOURCE.resolve())

    def test_mutated_archive_copy_rejected_by_sha(self):
        with tempfile.TemporaryDirectory() as td:
            bad = Path(td) / "reference_column.f90"
            bad.write_bytes(v.SOURCE.read_bytes() + b"!tamper\n")
            self.assertNotEqual(v.sha(bad), v.ARCHIVED_SHA)

    def test_unknown_historical_hash_not_silently_selected(self):
        deps = {p: v.package_dependencies(p) for p in v.PACKAGES}
        deps["bon-night-independent-replay"]["current_reference_source"]["sha256"] = "0" * 64
        with self.assertRaises(ValueError):
            # A package with a different source identity cannot use the old archive.
            with tempfile.TemporaryDirectory() as td:
                v.build_repo_mapping(Path(td), deps)

if __name__ == "__main__":
    unittest.main(verbosity=2)
