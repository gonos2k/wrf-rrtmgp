#!/usr/bin/env python3
"""Offline write-path and pin-preflight tests; executes no WRF/reference engines."""
import ast
import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent.parent
V4 = ROOT/'build/udm-stratified-capture-plan-v4/capture_runner.py'
V5 = HERE/'capture_runner.py'
V4_SHA = '182f8822e5094501e9f5e14bfd185463ce082d17b1292152f2aa6493ec0c9eee'
SNOW_RECEIPT = ROOT/'build/udm-stratified-captures-v4/cf0_snow_high_cloud_proxy/receipt.json'
SNOW_RECEIPT_SHA = '6afb79b5d4f73281eb8f5f0ec97f33f870e0ec6f82af7039ebf0b169050a4540'
CASES = ('ice_clip_low_cloud_proxy', 'ice_clip_high_cloud_proxy', 'clear_control', 'unclipped_cloud_control')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def all_write_paths(source):
    return [node.args[0] for node in ast.walk(ast.parse(source))
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name)
            and node.func.id == 'write']


def evaluate_paths(source, phase, root):
    results = []
    for expression in all_write_paths(source):
        # Evaluate filename expressions only; do not call write or execute the runner.
        for node in ast.walk(expression):
            if isinstance(node, ast.Name):
                assert node.id in {'out', 'phase', 'preflight_path'}, node.id
            if isinstance(node, ast.Call):
                assert isinstance(node.func, ast.Attribute) and node.func.attr == 'lower'
                assert isinstance(node.func.value, ast.Name) and node.func.value.id == 'phase'
                assert not node.args and not node.keywords
        value = eval(compile(ast.Expression(expression), '<offline-write-path>', 'eval'),
                     {'__builtins__': {}}, {'out': root, 'phase': phase, 'preflight_path': root/'preflight.json'})
        assert isinstance(value, Path) and value.is_relative_to(root)
        results.append(value.name)
    return results


class OfflineRunnerChecks(unittest.TestCase):
    def test_every_write_path_both_phases(self):
        source = V5.read_text()
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            for phase in ('LW', 'SW'):
                names = evaluate_paths(source, phase, root)
                self.assertIn('strict-'+phase.lower()+'.json', names)
                self.assertGreater(len(names), 8)
                self.assertFalse(list(root.iterdir()), 'offline filename test must not write files')

    def test_original_bug_is_detected_before_any_engine(self):
        self.assertEqual(sha(V4), V4_SHA)
        with tempfile.TemporaryDirectory() as temporary:
            for phase in ('LW', 'SW'):
                with self.subTest(phase=phase), self.assertRaisesRegex(TypeError, 'PosixPath.*str'):
                    evaluate_paths(V4.read_text(), phase, Path(temporary))

    def test_fixed_fresh_directory_guard_preserves_snow_failure(self):
        self.assertEqual(sha(SNOW_RECEIPT), SNOW_RECEIPT_SHA)
        source = V5.read_text()
        self.assertIn("if out.exists():raise RuntimeError('fresh fixed case directory required; no retry or overwrite')", source)
        self.assertIn("OUTPUT_ROOT=ROOT/'build/udm-stratified-captures-v4'", source)
        self.assertTrue(SNOW_RECEIPT.parent.exists())
        self.assertNotIn('shutil.rmtree', source)

    def test_remaining_four_preflights_and_repeat_are_stable(self):
        results = []
        for case in CASES+(CASES[0],):
            self.assertFalse((ROOT/'build/udm-stratified-captures-v4'/case).exists())
            command = [sys.executable, str(V5), '--case', case]
            run = subprocess.run(command, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            self.assertEqual(run.returncode, 0, run.stdout)
            preflight = HERE/'preflight'/(case+'.json')
            data = json.loads(preflight.read_text())
            self.assertEqual(data['status'], 'PIN_PREFLIGHT_PASS_NO_RUNTIME')
            self.assertEqual(data['runner_sha256'], sha(V5))
            self.assertFalse(Path(data['fixed_output_dir']).exists())
            results.append({'case': case, 'command': command, 'stdout': run.stdout,
                            'preflight_sha256': sha(preflight)})
        self.assertEqual(results[0]['preflight_sha256'], results[-1]['preflight_sha256'])
        (HERE/'offline-preflight-results.json').write_text(json.dumps({
            'status': 'FOUR_PREFLIGHTS_AND_REPEAT_PASS_NO_RUNTIME', 'results': results,
            'wrf_calls': 0, 'reference_calls': 0, 'runner_sha256': sha(V5)}, indent=2, sort_keys=True)+'\n')
        self.assertEqual(sha(SNOW_RECEIPT), SNOW_RECEIPT_SHA)


if __name__ == '__main__':
    unittest.main(verbosity=2)
