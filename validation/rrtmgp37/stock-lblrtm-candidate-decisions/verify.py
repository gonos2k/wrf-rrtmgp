#!/usr/bin/env python3
"""Draft integrity-only archive verifier. Never imports archived numerical code."""
import argparse
import gzip
import hashlib
import json
import os
from pathlib import Path
import sys

sys.dont_write_bytecode = True


def require(condition, message):
    if not condition:
        raise ValueError(message)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--output', type=Path, required=True)
    args = ap.parse_args()
    root = Path(__file__).resolve().parent
    out = args.output.resolve()
    require(root not in out.parents and out != root, 'output must be outside archive')
    require(not out.exists(), 'refuse existing output')
    manifest_bytes = (root / 'manifest.json').read_bytes()
    manifest = json.loads(manifest_bytes)
    require(manifest['schema'] == 'UDM37_CANDIDATE_DECISION_ARCHIVE_MANIFEST_V1', 'manifest schema')
    rows = manifest['files']
    names = [r['relative_path'] for r in rows]
    require(len(names) == len(set(names)) == manifest['payload_count'], 'duplicate/count mismatch')
    actual = []
    for path in root.rglob('*'):
        require(not path.is_symlink(), 'symlink not permitted')
        if path.is_file() and path != root / 'manifest.json':
            actual.append(path.relative_to(root).as_posix())
    require(sorted(names) == sorted(actual), 'closed archive roster mismatch')
    for row in rows:
        rel = Path(row['relative_path'])
        require(not rel.is_absolute() and '..' not in rel.parts, 'unsafe payload path')
        b = (root / rel).read_bytes()
        require(len(b) == row['bytes'] and hashlib.sha256(b).hexdigest() == row['sha256'], 'stored payload pin mismatch: ' + str(rel))
        if row.get('compression') == 'gzip':
            inflated = gzip.decompress(b)
            require(len(inflated) == row['origin_bytes'] and hashlib.sha256(inflated).hexdigest() == row['origin_sha256'], 'inflated origin pin mismatch')
    # Archive decisions/statuses are derived metadata. No raw linebank, events,
    # spectra, coefficient vectors or source replay is read by this verifier.
    scope = json.loads((root / 'scope.json').read_text())
    require(scope['physical_acceptance'] == 'FAIL_NEGATIVE_OD_RETAINED', 'physical FAIL was promoted')
    require(scope['new_production_changes'] == 0, 'wrong source scope')
    require(scope['candidate_build_invocations'] == scope['candidate_solver_invocations'] == 1, 'wrong compiled budget')
    require(scope['saved_reader_invocations'] == 2 and scope['reader_actual_RCs'] == [1, 0], 'reader chronology')
    correction = json.loads((root / 'reporting-correction.json').read_text())
    require(correction['literal_report_preserved'] is True, 'original report not retained')
    require(correction['supported_reason9_event_count'] == 7431 and correction['invalid_value'] == 7500,
            'counter correction not scoped')
    require(correction['left_censored_prefix_records'] == 69 and correction['new_raw_reader_model_build_solver_invocations'] == 0, 'metadata-only correction')
    require(correction['reason9_unique_identity_claim'] == 'NOT_USED_FROM_DEFECTIVE_AGGREGATE', 'unsupported unique reason9 claim')
    executed = gzip.decompress((root / 'reader/v2/report.json.gz').read_bytes())
    require(hashlib.sha256(executed).hexdigest() == correction['literal_report_sha256'], 'correction/literal-report join')
    result = json.loads(executed)
    require(result['phase_reason_counts']['2:9'] == correction['supported_reason9_event_count'], 'direct event count')
    require(result['join']['computed_reason9_invocations'] == correction['invalid_value'], 'preserved counter')
    require(result['join']['left_censored_ancestry_validated'] is False, 'censored ancestry promoted')
    require(result['spectra']['samples_bitwise_equal'] == 63838065 and len(result['spectra']['layers']) == 45, 'saved spectral scope')
    require(result['join']['target_term_updates_joined'] == 6072 and result['join']['target_full_invocation_identities'] == 837, 'saved join scope')
    for rel, expected_rc in [('runtime/build/execution.json', 0), ('runtime/solver/execution.json', 0),
                             ('reader/v1/execution.json', 1), ('reader/v2/execution.json', 0)]:
        receipt = json.loads((root / rel).read_text())
        rc = receipt.get('actual_child_returncode', receipt.get('actual_returncode'))
        require(type(rc) is int and rc == expected_rc and type(receipt.get('pid')) is int, 'executed receipt chronology')
    origins = json.loads((root / 'origins.json').read_text())
    copied = {r['relative_path']: r for r in origins['copies']}
    require(len(copied) == len(origins['copies']), 'duplicate origins')
    require(set(copied) | set(origins['authored_payloads']) == set(names), 'origin roster')
    for row in rows:
        if row['relative_path'] in copied:
            origin = copied[row['relative_path']]
            expected_sha = row.get('origin_sha256', row['sha256'])
            expected_bytes = row.get('origin_bytes', row['bytes'])
            require(origin['sha256'] == expected_sha and origin['size_bytes'] == expected_bytes, 'origin pin join')
    report = {'status': 'PASS_SCOPED_SAVED_ARCHIVE_INTEGRITY', 'payload_count': len(rows),
              'manifest_sha256': hashlib.sha256(manifest_bytes).hexdigest(),
              'physical_acceptance': scope['physical_acceptance'],
              'raw_numeric_reader_or_solver_invocations': 0,
              'limits': ['Stored/inflated archive integrity and declared chronology only.',
                         'Does not reopen unbundled raw data or reproduce line-routing/OD mathematics.']}
    out.parent.mkdir(parents=True, exist_ok=True)
    with out.open('x') as f:
        json.dump(report, f, indent=2)
        f.write('\n')
        f.flush()
        os.fsync(f.fileno())


if __name__ == '__main__':
    main()
