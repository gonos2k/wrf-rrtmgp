#!/usr/bin/env python3
"""Verify the packaged PR68 guard-build/restart evidence; no model invocation."""
from __future__ import annotations
import argparse, base64, hashlib, json, sys
from pathlib import Path
HERE = Path(__file__).resolve().parent

def sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--external', action='store_true', help='also check absolute external file pins if present')
    args = parser.parse_args()
    manifest = json.loads((HERE / 'manifest.json').read_text())
    problems = []
    for record in manifest['files']:
        path = HERE / record['path']
        if not path.is_file():
            problems.append(f"missing packaged file: {record['path']}")
            continue
        if path.stat().st_size != record['size_bytes'] or sha(path) != record['sha256']:
            problems.append(f"packaged file hash/size mismatch: {record['path']}")
    for encoded, original in manifest.get('encoded_exact_files', {}).items():
        try:
            decoded = base64.b64decode((HERE / encoded).read_bytes().strip(), validate=True)
            if len(decoded) != original['original_size_bytes'] or hashlib.sha256(decoded).hexdigest() != original['original_sha256']:
                problems.append(f'encoded exact-source bytes mismatch: {encoded}')
        except Exception as exc:
            problems.append(f'cannot decode exact-source snapshot {encoded}: {exc}')
    if args.external:
        for label, record in manifest['external_pins'].items():
            path = Path(record['path'])
            if not path.is_file():
                problems.append(f'external pin unavailable: {label}: {path}')
            elif path.stat().st_size != record['size_bytes'] or sha(path) != record['sha256']:
                problems.append(f'external pin mismatch: {label}: {path}')
    plan = json.loads((HERE / 'evidence/plan-v3.json').read_text())
    stage = json.loads((HERE / 'evidence/stage-manifest-v3.json').read_text())
    readback = json.loads((HERE / 'evidence/stage-readback-v3.json').read_text())
    auth = json.loads((HERE / 'evidence/root-authorization-v3.json').read_text())
    run = json.loads((HERE / 'evidence/execution-receipt-v3.json').read_text())
    post = json.loads((HERE / 'evidence/candidate-build-postflight.json').read_text())
    independent = json.loads((HERE / 'evidence/independent-output-postflight-v2.json').read_text())
    local = lambda name: sha(HERE / name)
    chain = {
        'manifest_binds_plan': stage.get('plan_sha256') == local('evidence/plan-v3.json'),
        'readback_binds_plan_manifest': readback.get('plan_sha256') == local('evidence/plan-v3.json') and readback.get('manifest_sha256') == local('evidence/stage-manifest-v3.json'),
        'authorization_binds_stage': auth.get('plan_sha256') == local('evidence/plan-v3.json') and auth.get('manifest_sha256') == local('evidence/stage-manifest-v3.json') and auth.get('readback_sha256') == local('evidence/stage-readback-v3.json'),
        'runtime_binds_stage_authorization': run.get('plan_sha256') == local('evidence/plan-v3.json') and run.get('manifest_sha256') == local('evidence/stage-manifest-v3.json') and run.get('readback_sha256') == local('evidence/stage-readback-v3.json') and run.get('authorization_sha256') == local('evidence/root-authorization-v3.json'),
        'runtime_pair_status': run.get('status') == 'PASS_GUARD_PAIR_EXACT' and run.get('model_invocations') == 2,
        'build_postflight': post.get('status') == 'BUILD_PASS_SCOPED_POSTFLIGHT_RECONCILED' and not post.get('failed_checks'),
        'independent_output_postflight': independent.get('status') == 'PASS_GUARD_PAIR_EXACT_INDEPENDENT_READBACK' and not independent.get('failed_checks') and independent.get('execution_receipt_sha256') == local('evidence/execution-receipt-v3.json'),
    }
    for name, ok in chain.items():
        if not ok:
            problems.append(f'receipt chain failed: {name}')
    print(json.dumps({'status': 'FAIL' if problems else 'PASS', 'packaged_files_checked': len(manifest['files']), 'external_checked': bool(args.external), 'problems': problems}, indent=2))
    return 1 if problems else 0

if __name__ == '__main__':
    sys.exit(main())
