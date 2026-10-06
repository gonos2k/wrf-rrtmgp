#!/usr/bin/env python3
"""Retain Python-only validator tests and immutable production/capture pin proof."""
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys

sys.dont_write_bytecode = True
ROOT = Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE = Path(__file__).resolve().parent
WORK = ROOT/'build/udm-frozen-replay-validator-work'
TESTS = WORK/'WRF/test/rrtmgp'
PLAN = ROOT/'build/udm-stratified-capture-plan-v3/plan.json'
PLAN_SHA = '4f9e642fad9b648f352805ac6f9d71363945df0388c1e0acc608b3740f374279'
FIRST = ROOT/'build/udm-stratified-captures-v3/cf0_rain_low_cloud_proxy'


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024*1024), b''):
            h.update(chunk)
    return h.hexdigest()


def preserved_pins():
    assert sha(PLAN) == PLAN_SHA
    plan = json.loads(PLAN.read_text())
    expected = {str(PLAN): PLAN_SHA}
    for item in (plan['executable'], plan['state_identity']['checkpoint'],
                 plan['source_manifest'], plan['strict_reference_source'],
                 plan['strict_reference']):
        expected[item['path']] = item['sha256']
    for item in plan['executor_support_scripts'].values():
        expected[item['path']] = item['sha256']
    expected.update(plan['external_asset_sha256'])
    recovery = json.loads((FIRST/'replay-recovery-v1/recovery-receipt.json').read_text())
    for item in recovery['dependency_import_pins'].values():
        expected[item['path']] = item['sha256']
    for location, entries in ((FIRST/'capture', recovery['original_capture_sha256']),
                               (FIRST/'replay-recovery-v1/capture', recovery['copied_capture_sha256'])):
        expected.update({str(location/name): digest for name, digest in entries.items()})
    expected[str(FIRST/'receipt.json')] = '2bc9b28a9ac828372a8093541707383bc74d5dc117e8512f08196f1d5d9965a0'
    expected[str(FIRST/'replay-recovery-v1/recovery-receipt.json')] = '7de947c5d32ddc92827e24561f2ed141f25d3f392407f775dc7ab731470d1e95'
    expected[str(ROOT/'build/udm-stratified-captures-v2/cf0_rain_low_cloud_proxy/receipt.json')] = '4cfe00f838c1200cc5c18765a88a299632c8a46f314d99ba4a0dd54705a64826'
    for path, digest in expected.items():
        assert sha(path) == digest, path
    manifest = json.loads(Path(plan['source_manifest']['path']).read_text())
    source_root = Path(manifest['source_tree'])
    for entry in manifest['files']:
        path = source_root/entry['path']
        if entry['kind'] == 'symlink':
            assert path.is_symlink() and os.readlink(path) == entry['target'], str(path)
            digest = hashlib.sha256(os.readlink(path).encode()).hexdigest()
        else:
            digest = sha(path)
        assert digest == entry['sha256'], str(path)
    return {'explicit_pins': expected, 'source_manifest_entries_verified': len(manifest['files'])}


def main():
    receipt = {'status': 'PYTHON_PROOF_RUNNING', 'executed_script_sha256': sha(__file__),
               'no_wrf_or_reference_execution': True}
    try:
        receipt['before'] = preserved_pins()
        env = os.environ.copy()
        env['PYTHONDONTWRITEBYTECODE'] = '1'
        command = [sys.executable, str(TESTS/'test_frozen_raw_replay_contract.py')]
        result = subprocess.run(command, env=env, text=True, stdout=subprocess.PIPE,
                                stderr=subprocess.STDOUT, check=False)
        (HERE/'python-tests.log').write_text(result.stdout)
        receipt['tests'] = {'command': command, 'returncode': result.returncode,
                            'log_sha256': sha(HERE/'python-tests.log')}
        assert result.returncode == 0, result.stdout
        sys.path.insert(0, str(TESTS))
        from test_frozen_raw_replay_contract import fixture
        from test_udm_negative_policy import check_raw_record_validation
        check_raw_record_validation()  # Python function only, no Fortran compile/main.
        receipt['existing_negative_raw_checks'] = 'PASS'
        old_file = ROOT/'build/udm-phase-path-statistics-real-wrf/source/WRF/test/rrtmgp/test_column_replay.py'
        spec = importlib.util.spec_from_file_location('original_pinned_validator', old_file)
        old = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(old)
        original_failures = {}
        for phase in ('LW', 'SW'):
            raw, inp = fixture(True)
            try:
                old.compare_input_to_raw(phase, raw, inp, 3)
            except old.ReplayError as exc:
                assert 'GWP_OMITTED diagnostic-only mass contract' in str(exc)
                original_failures[phase] = str(exc)
            else:
                raise AssertionError('original validator unexpectedly accepted material mode1 G/H')
        receipt['original_bug_reproduced_with_synthetic_records'] = original_failures
        files = ['WRF/test/rrtmgp/test_column_replay.py',
                 'WRF/test/rrtmgp/test_frozen_raw_replay_contract.py',
                 'WRF/test/rrtmgp/CMakeLists.txt', 'config/registration37.json']
        receipt['modified_files_sha256'] = {name: sha(WORK/name) for name in files}
        registration = json.loads((WORK/'config/registration37.json').read_text())
        for name in files[:3]:
            key = name.removeprefix('WRF/')
            blob = subprocess.check_output(['git', '-C', str(WORK), 'hash-object', name], text=True).strip()
            assert registration['patched_blobs'][key] == blob
        subprocess.run(['git', '-C', str(WORK), 'diff', '--check'], check=True)
        receipt['registration_and_diff_check'] = 'PASS'
        diff = subprocess.check_output(['git', '-C', str(WORK), 'diff', '--binary'], text=True)
        new_diff = subprocess.run(['git', 'diff', '--no-index', '--', '/dev/null',
                                  str(TESTS/'test_frozen_raw_replay_contract.py')],
                                 text=True, stdout=subprocess.PIPE, check=False)
        assert new_diff.returncode == 1
        (HERE/'review.diff').write_text(diff+new_diff.stdout)
        receipt['review_diff_sha256'] = sha(HERE/'review.diff')
        receipt['after'] = preserved_pins()
        assert receipt['after'] == receipt['before']
        receipt['status'] = 'PYTHON_PROOF_PASS'
    except BaseException as exc:
        receipt['status'] = 'PYTHON_PROOF_FAIL_PRESERVED'
        receipt['error'] = repr(exc)
        raise
    finally:
        (HERE/'test-receipt.json').write_text(json.dumps(receipt, indent=2, sort_keys=True)+'\n')
    print(json.dumps({key: receipt[key] for key in ('status', 'modified_files_sha256', 'review_diff_sha256')}, indent=2))


if __name__ == '__main__':
    main()
