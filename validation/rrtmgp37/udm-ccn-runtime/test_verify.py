#!/usr/bin/env python3
"""Offline adversarial checks of the retained-evidence verifier; no models."""
import argparse
import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tempfile


def js(root, name, change):
    p = root / name
    q = json.loads(p.read_text()); change(q)
    p.write_text(json.dumps(q, sort_keys=True, indent=2) + '\n')


def manifest(root):
    q = {'schema': 'retained-sha256-manifest-v1', 'files': [{'path': str(p.relative_to(root)), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size_bytes': p.stat().st_size} for p in sorted(root.rglob('*')) if p.is_file() and p.name != 'artifact-manifest.json']}
    (root / 'artifact-manifest.json').write_text(json.dumps(q, sort_keys=True, indent=2) + '\n')


def run(package):
    sys.dont_write_bytecode = True
    spec = importlib.util.spec_from_file_location('retained_verifier', package / 'verify.py')
    v = importlib.util.module_from_spec(spec); spec.loader.exec_module(v)
    positive = v.verify(package)
    worker = 'retained/udm37-ccn-current-runtime-v1/cases/stage-v3/worker-proof.json'
    attributed = 'retained/udm37-ccn-restart-runtime-v1/posthoc-attribution-v1/report-v2.json'
    tests = []
    def check(name, edit, refresh=True):
        with tempfile.TemporaryDirectory(prefix='ccn-evidence-negative-') as folder:
            root = Path(folder) / 'package'; shutil.copytree(package, root)
            edit(root)
            if refresh:
                manifest(root)
            try:
                v.verify(root)
            except (ValueError, KeyError, TypeError, AssertionError) as e:
                tests.append({'name': name, 'rejected': True, 'reason': str(e), 'manifest_refreshed': refresh})
            else:
                raise AssertionError('negative control accepted: ' + name)
    check('retained_sha_tamper', lambda r: (r / 'README.md').write_text('tampered\n'), False)
    check('erase_original_build_failure', lambda r: js(r, 'runtime-ledger.json', lambda q: q.update(original_build_status='BUILD_PASS')))
    check('promote_original_restart_failure', lambda r: js(r, 'runtime-ledger.json', lambda q: q['restart'].update(original_strict_comparison_passed=True)))
    check('wrong_source_head', lambda r: js(r, 'runtime-ledger.json', lambda q: q.update(source_pr49_head='0'*40)))
    check('missing_worker_per_rank', lambda r: js(r, worker, lambda q: q['observed_pids'][next(iter(q['observed_pids']))].update(workers=[0])))
    check('aggregate_workers_not_each_pid', lambda r: js(r, worker, lambda q: [p.update(workers=[i % 2]) for i, p in enumerate(q['observed_pids'].values())]))
    check('worker_cpu_zero', lambda r: js(r, worker, lambda q: q['observed_pids'][next(iter(q['observed_pids']))]['worker_cpu_ns'].update({'1': 0})))
    check('nonfinite_contract_false', lambda r: js(r, 'runtime-ledger.json', lambda q: q['models'][0]['fields']['history'].update(raw_decoded_finite_unmasked=False)))
    check('metadata_contract_removed', lambda r: js(r, 'runtime-ledger.json', lambda q: q['comparison_pairs'][-1].update(metadata_equal=False)))
    def missing_row(r):
        q = json.loads((r / 'runtime-ledger.json').read_text())['comparison_pairs'][0]
        p = r / q['table']; rows = p.read_text().splitlines(keepends=True); p.write_text(''.join(rows[:-1]))
    check('missing_raw_table_row', missing_row)
    check('wrong_reset_value', lambda r: js(r, attributed, lambda q: q['arms']['restart-omp1']['history']['initial_15']['UDM_CF_STEP'].update(expected_reset=0)))
    check('wrong_disabled_alarm', lambda r: js(r, attributed, lambda q: q['arms']['restart-omp1']['checkpoint'].update(candidate_alarm_seconds=0)))
    check('original_restart_failure_erased', lambda r: js(r, 'receipts/restart-strict-failure-derived.json', lambda q: q.update(original_status='PASS')))
    check('new_unallowed_metadata_exception', lambda r: js(r, 'receipts/restart-strict-failure-derived.json', lambda q: q['first_five_exact_check_results'][2]['unexplained_global_differences'].update(OTHER={})))
    check('extra_unindexed_payload', lambda r: (r / 'extra.txt').write_text('extra'), False)
    check('missing_source_basis', lambda r: js(r, 'receipts/restart-source-basis-excerpts.json', lambda q: q.pop('registry')))
    check('double_count_candidate_models', lambda r: js(r, 'model-count-ledger.json', lambda q: q.update(unique_model_total=25)))
    return {'schema': 'portable-verifier-offline-controls-v1', 'status': 'PASS', 'positive': positive, 'negative_controls': tests, 'negative_count': len(tests), 'all_rejected': all(x['rejected'] for x in tests), 'model_build_reference_calls': 0, 'external_arrays_opened': False, 'verifier_sha256': hashlib.sha256((package / 'verify.py').read_bytes()).hexdigest()}


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__); p.add_argument('--package', type=Path, required=True); p.add_argument('--receipt', type=Path, required=True); a = p.parse_args()
    if a.receipt.exists():
        p.error('receipt collision')
    result = run(a.package.resolve())
    a.receipt.write_text(json.dumps(result, sort_keys=True, indent=2) + '\n')
    print(json.dumps({'status': result['status'], 'negative_count': result['negative_count'], 'receipt': str(a.receipt)}, sort_keys=True))
