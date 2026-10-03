#!/usr/bin/env python3
"""Complete unreviewed local package metadata; no external source writes/processes."""
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'package-v4'


def pin(p):
    p = p.resolve(strict=True)
    return {'path': str(p), 'sha256': hashlib.sha256(p.read_bytes()).hexdigest(), 'size_bytes': p.stat().st_size}


def write(name, q):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        f.write(json.dumps(q, sort_keys=True, indent=2) + '\n')


def main():
    old = HERE / 'artifact-manifest-initial-v4.json'
    if old.exists() or (OUT / 'model-count-ledger.json').exists():
        raise ValueError('finalization collision')
    shutil.copy2(OUT / 'artifact-manifest.json', old)
    ledger = json.loads((OUT / 'runtime-ledger.json').read_text())
    origins = json.loads((OUT / 'provenance-index.json').read_text())
    rows = []
    for arm, name in [('ra4-24h-v1', 'execution-receipt-v1.json'), ('ra37-24h-v1', 'execution-receipt-v1.json'), ('ra4-own12-to13h-v1', 'restart-execution-v1.json'), ('ra37-own12-to13h-v1', 'restart-execution-v1.json')]:
        p = ROOT / 'build/udm-seaice-winter-validation-v3' / arm / name
        before = pin(p); e = json.loads(p.read_text())
        assert e['actual_model_invocations'] == 1 and e['before_pins_valid'] and e['after_pins_valid']
        passed = e['outputs']['passed'] if 'outputs' in e else e['strict_history']['passed'] and e['own_continuous_comparison']['passed']
        assert passed and pin(p) == before
        rows.append({'arm': arm, 'receipt': before, 'status': e['status'], 'actual_model_invocations': 1, 'model': e['model'], 'before_after_pins_passed': True, 'strict_outputs_passed': True})
        origins['external_hash_pins'].append(before)
    primary = sorted(q['receipt']['path'] for q in ledger['models'])
    candidate = sorted(q['receipt']['path'] for q in ledger['models'] if q['family'] in ('new-3h', 'new-24h', 'restart-attempt'))
    assert len(set(primary)) == 17 and len(set(candidate)) == 8 and not set(primary).intersection(q['receipt']['path'] for q in rows)
    write('model-count-ledger.json', {'schema': 'unique-model-receipt-count-v1', 'primary_receipt_paths': primary, 'candidate_receipt_paths': candidate, 'earlier_source47_models': rows, 'candidate_subset_of_primary': True, 'unique_model_total': 21, 'prechange_and_reference_count': 13, 'candidate_count': 8, 'scope': '17 primary already includes8 candidate; add4 disjoint source47 winter/restart references. Never17+8.'})
    for n in ('verify.py', 'test_verify.py'):
        before = pin(HERE / n); shutil.copy2(HERE / n, OUT / n)
        assert pin(OUT / n)['sha256'] == before['sha256']
        origins['copied_originals'] = [q for q in origins['copied_originals'] if q['retained_path'] != n] + [{'retained_path': n, 'original': before}]
    origins['external_hash_pins'] = sorted({q['path']: q for q in origins['external_hash_pins']}.values(), key=lambda q: q['path'])
    origins['finalization'] = {'initial_manifest': pin(old), 'script': pin(Path(__file__)), 'scope': 'Unique receipt-path count clarification and final offline verifier code before review; no original artifacts changed.'}
    (OUT / 'provenance-index.json').write_text(json.dumps(origins, sort_keys=True, indent=2) + '\n')
    shutil.copy2(Path(__file__), OUT / 'curation/finalize_v1.py')
    refresh()
    print(json.dumps({'status': 'LOCAL_PACKAGE_METADATA_FINALIZED', 'unique_models': 21, 'candidate_included_in_primary': 8}))


def refresh():
    manifest = {'schema': 'retained-sha256-manifest-v1', 'files': [{'path': str(p.relative_to(OUT)), 'sha256': pin(p)['sha256'], 'size_bytes': p.stat().st_size} for p in sorted(OUT.rglob('*')) if p.is_file() and p.name != 'artifact-manifest.json']}
    (OUT / 'artifact-manifest.json').write_text(json.dumps(manifest, sort_keys=True, indent=2) + '\n')


if __name__ == '__main__':
    main()
