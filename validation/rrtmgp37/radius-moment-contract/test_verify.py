#!/usr/bin/env python3
"""Standard-library regression controls for the historical and current source gates."""
import argparse
import fnmatch
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

PACKAGE = Path(__file__).resolve().parent
REPO = PACKAGE.parents[2]
HISTORICAL_ROOT = None


def workflow_contract(text, paths, historical_commit):
    for event in ('pull_request', 'push'):
        block = re.search(r'^  ' + event + r':\n(.*?)(?=^  \w|^permissions:)', text,
                          flags=re.MULTILINE | re.DOTALL)
        if block is None:
            raise ValueError(f'missing event: {event}')
        filters = re.search(r'^    paths:\n((?:      - .+\n)+)', block.group(1), re.MULTILINE)
        if filters is None:
            raise ValueError(f'missing paths: {event}')
        patterns = [line.strip()[2:].strip("'\"") for line in filters.group(1).splitlines()]
        for path in paths:
            if not any(fnmatch.fnmatchcase(path, pattern) for pattern in patterns):
                raise ValueError(f'uncovered source path: {event}: {path}')
    checkout = re.search(r'^          ref: (\w+)\n          path: (\S+)\n', text, re.MULTILINE)
    if checkout is None or checkout.group(1) != historical_commit:
        raise ValueError('historical checkout ref does not match source contract')
    root = checkout.group(2)
    if f'--source-root {root}' not in text or f'--historical-source-root {root}' not in text:
        raise ValueError('historical checkout not selected by verifier and regression runner')


class SourceControls(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='radius-archive-controls-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.package = self.root / 'package'
        shutil.copytree(PACKAGE, self.package)
        self.historical = self.root / 'historical'
        self.current = self.root / 'current'
        self.contract = json.loads((PACKAGE / 'current-source-contract.json').read_text())
        self.paths = [row['path'] for row in self.contract['files']]
        for origin, target in ((HISTORICAL_ROOT, self.historical), (REPO, self.current)):
            for rel in self.paths:
                dest = target / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(origin / rel, dest)

    def verify(self, historical=None, current=None):
        return subprocess.run([sys.executable, '-I', '-S', str(self.package / 'verify.py'),
                               '--source-root', str(historical or self.historical),
                               '--current-source-root', str(current or self.current)],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)

    def reject(self, proc, marker):
        self.assertNotEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(marker, proc.stdout)

    def test_historical_pass_and_current_difference_reported(self):
        proc = self.verify()
        self.assertEqual(proc.returncode, 0, proc.stdout)
        report = json.loads(proc.stdout)
        self.assertEqual(report['archive_source_checkout'], str(self.historical))
        self.assertEqual(report['current_source_checkout'], str(self.current))
        differences = [row['path'] for row in report['current_vs_archive'] if not row['matches_archived_pin']]
        self.assertEqual(differences, ['WRF/phys/module_microphysics_driver.F'])
        self.assertEqual(report['current_source_contract_status'], 'PASS_REVIEWED_SOURCE_IDENTITY_ONLY')
        self.assertFalse(report['physical_accuracy_claim'])

    def test_wrong_historical_root_rejected(self):
        self.reject(self.verify(historical=self.current), 'source-review hash mismatch')

    def test_default_current_checkout_cannot_pass_as_historical(self):
        proc = subprocess.run([sys.executable, '-I', '-S', str(PACKAGE / 'verify.py')],
                              text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.reject(proc, 'source-review hash mismatch WRF/phys/module_microphysics_driver.F')

    def test_historical_root_cannot_pass_as_reviewed_current(self):
        self.reject(self.verify(current=self.historical), 'current-source contract hash mismatch')

    def test_missing_current_root_rejected(self):
        self.reject(self.verify(current=self.root / 'missing-current'), 'missing current source file')

    def test_missing_historical_root_rejected(self):
        self.reject(self.verify(historical=self.root / 'missing'), 'missing source file')

    def test_historical_source_mutations_rejected(self):
        for rel in self.paths:
            with self.subTest(path=rel):
                source = self.historical / rel
                original = source.read_bytes()
                source.write_bytes(original + b'\n! mutation\n')
                self.reject(self.verify(), 'source-review hash mismatch ' + rel)
                source.write_bytes(original)

    def test_current_source_mutations_rejected(self):
        for rel in self.paths:
            with self.subTest(path=rel):
                source = self.current / rel
                original = source.read_bytes()
                source.write_bytes(original + b'\n! mutation\n')
                self.reject(self.verify(), 'current-source contract hash mismatch ' + rel)
                source.write_bytes(original)

    def test_payload_mutation_rejected(self):
        source = self.package / 'evidence/moment-result.json'
        source.write_bytes(source.read_bytes() + b'\n')
        self.reject(self.verify(), 'payload pin mismatch: evidence/moment-result.json')

    def test_contract_tamper_rejected_by_manifest(self):
        source = self.package / 'current-source-contract.json'
        source.write_bytes(source.read_bytes() + b'\n')
        self.reject(self.verify(), 'payload pin mismatch: current-source-contract.json')

    def test_contract_pin_drift_rejected_even_with_updated_manifest(self):
        source = self.package / 'current-source-contract.json'
        contract = json.loads(source.read_text())
        contract['files'][0]['sha256'] = '0' * 64
        source.write_text(json.dumps(contract))
        manifest_path = self.package / 'manifest.json'
        manifest = json.loads(manifest_path.read_text())
        for row in manifest['files']:
            if row['path'] == 'current-source-contract.json':
                row['bytes'] = source.stat().st_size
                row['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
        manifest_path.write_text(json.dumps(manifest))
        self.reject(self.verify(), 'current-source contract hash mismatch WRF/phys/module_mp_udm.F')

    def test_unsafe_manifest_paths_rejected(self):
        manifest_path = self.package / 'manifest.json'
        original = manifest_path.read_text()
        for rel in ('/tmp/outside', '../outside', 'evidence/../outside',
                    './README.md', 'evidence//moment-result.json', 'evidence\\outside'):
            with self.subTest(path=rel):
                manifest = json.loads(original)
                manifest['files'][0]['path'] = rel
                manifest_path.write_text(json.dumps(manifest))
                self.reject(self.verify(), 'unsafe relative path')
        manifest_path.write_text(original)

    def test_symlink_payload_escape_rejected(self):
        source = self.package / 'evidence/moment-result.json'
        outside = self.root / 'outside-payload.json'
        outside.write_bytes(source.read_bytes())
        source.unlink()
        source.symlink_to(outside)
        self.reject(self.verify(), 'path escapes root: evidence/moment-result.json')

    def test_manifest_payload_omission_rejected(self):
        source = self.package / 'manifest.json'
        manifest = json.loads(source.read_text())
        manifest['files'] = [row for row in manifest['files'] if row['path'] != 'evidence/moment-result.json']
        source.write_text(json.dumps(manifest))
        self.reject(self.verify(), 'closed roster mismatch')

    def test_unsafe_archived_source_paths_rejected(self):
        source = self.package / 'evidence/source-review.json'
        original = source.read_text()
        manifest_path = self.package / 'manifest.json'
        original_manifest = manifest_path.read_text()
        for rel in ('/tmp/outside-source', '../outside-source', 'WRF/../outside-source'):
            with self.subTest(path=rel):
                review = json.loads(original)
                review['source']['files'][0]['path'] = rel
                source.write_text(json.dumps(review))
                manifest = json.loads(original_manifest)
                for row in manifest['files']:
                    if row['path'] == 'evidence/source-review.json':
                        row['bytes'] = source.stat().st_size
                        row['sha256'] = hashlib.sha256(source.read_bytes()).hexdigest()
                manifest_path.write_text(json.dumps(manifest))
                self.reject(self.verify(), 'unsafe relative path')
        source.write_text(original)
        manifest_path.write_text(original_manifest)

    def test_source_symlink_escapes_rejected(self):
        rel = self.paths[0]
        for root in (self.historical, self.current):
            with self.subTest(root=root.name):
                source = root / rel
                original = source.read_bytes()
                outside = self.root / ('outside-' + root.name)
                outside.write_bytes(original)
                source.unlink()
                source.symlink_to(outside)
                self.reject(self.verify(), 'path escapes root: ' + rel)
                source.unlink()
                source.write_bytes(original)

    def test_extra_payload_rejected(self):
        (self.package / 'unregistered.txt').write_text('extra')
        self.reject(self.verify(), 'closed roster mismatch')

    def test_workflow_covers_both_events_and_historical_root(self):
        text = (REPO / '.github/workflows/validate-radius-moment-contract.yml').read_text()
        workflow_contract(text, self.paths, self.contract['historical_source_commit'])

    def test_workflow_missing_source_coverage_rejected(self):
        text = (REPO / '.github/workflows/validate-radius-moment-contract.yml').read_text()
        for event in ('pull_request', 'push'):
            for rel in self.paths:
                with self.subTest(event=event, path=rel):
                    start = text.index('  ' + event + ':')
                    end = text.index('permissions:') if event == 'push' else text.index('  push:')
                    altered = text[:start] + text[start:end].replace("      - '" + rel + "'\n", '') + text[end:]
                    with self.assertRaisesRegex(ValueError, 'uncovered source path: ' + event):
                        workflow_contract(altered, self.paths, self.contract['historical_source_commit'])

    def test_workflow_wrong_historical_ref_rejected(self):
        text = (REPO / '.github/workflows/validate-radius-moment-contract.yml').read_text()
        text = text.replace('ref: ' + self.contract['historical_source_commit'], 'ref: ' + '0' * 40)
        with self.assertRaisesRegex(ValueError, 'historical checkout ref'):
            workflow_contract(text, self.paths, self.contract['historical_source_commit'])


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--historical-source-root', required=True, type=Path)
    args = parser.parse_args()
    HISTORICAL_ROOT = args.historical_source_root.resolve()
    unittest.main(argv=[sys.argv[0]], verbosity=2)
