"""Exercise documentary acceptance boundaries without running science."""
import copy
import json
import unittest
from pathlib import Path
from verify import verify

ROOT = Path(__file__).resolve().parents[3]
INDEX = json.loads(Path(__file__).with_name('checklist.json').read_text())


class AcceptanceBoundary(unittest.TestCase):
    def test_pinned_index_does_not_approve_production(self):
        result = verify(ROOT, INDEX)
        self.assertEqual(result['index_integrity'], 'PASS')
        self.assertFalse(result['production_accepted'])
        self.assertEqual(result['original_gates'], 19)

    def test_reject_missing_original_gate(self):
        index = copy.deepcopy(INDEX)
        index['original19'].pop()
        with self.assertRaisesRegex(ValueError, 'original19'):
            verify(ROOT, index)

    def test_reject_false_approval(self):
        index = copy.deepcopy(INDEX)
        index['production_accepted'] = True
        with self.assertRaisesRegex(ValueError, 'production acceptance'):
            verify(ROOT, index)

    def test_reject_changed_evidence_digest(self):
        index = copy.deepcopy(INDEX)
        index['evidence'][0]['sha256'] = '0' * 64
        with self.assertRaisesRegex(ValueError, 'evidence changed'):
            verify(ROOT, index)

    def test_reject_path_escape(self):
        index = copy.deepcopy(INDEX)
        index['evidence'][0]['path'] = '../foreign-repository'
        with self.assertRaisesRegex(ValueError, 'unexpected evidence paths'):
            verify(ROOT, index)

    def test_reject_missing_evidence(self):
        index = copy.deepcopy(INDEX)
        index['evidence'].pop()
        with self.assertRaisesRegex(ValueError, 'evidence paths'):
            verify(ROOT, index)

    def test_reject_empty_runtime_roster(self):
        index = copy.deepcopy(INDEX)
        index['startup_runtime_source_sha256'] = {}
        with self.assertRaisesRegex(ValueError, 'startup runtime paths'):
            verify(ROOT, index)

    def test_source_change_is_reported_without_retagging_evidence(self):
        index = copy.deepcopy(INDEX)
        name = next(iter(index['startup_runtime_source_sha256']))
        index['startup_runtime_source_sha256'][name] = '0' * 64
        result = verify(ROOT, index)
        self.assertEqual(result['index_integrity'], 'PASS')
        self.assertFalse(result['startup_source_subset_matches'])
        self.assertFalse(result['production_accepted'])


if __name__ == '__main__':
    unittest.main()
