#!/usr/bin/env python3
"""Saved metadata/integrity verification only; no raw readers or subprocesses."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def digest(data):
    return hashlib.sha256(data).hexdigest()


def load(name):
    return json.loads((ROOT / name).read_text())


def bind_bytes(name, pin):
    data = (ROOT / name).read_bytes()
    require(digest(data) == pin['sha256'] and len(data) == pin['size_bytes'],
            'saved pin mismatch: ' + name)


def verify():
    manifest = load('manifest.json')
    rows = manifest['files']
    names = [r['relative_path'] for r in rows]
    require(len(names) == len(set(names)) == manifest['payload_count'], 'duplicate/count roster')
    actual = set()
    for path in ROOT.rglob('*'):
        require(not path.is_symlink(), 'unexpected package symlink: ' + str(path))
        if path.is_file() and path != ROOT / 'manifest.json':
            actual.add(path.relative_to(ROOT).as_posix())
    require(actual == set(names), 'closed roster mismatch')
    by_name = {r['relative_path']: r for r in rows}
    for name, row in by_name.items():
        path = ROOT / name
        require(path.resolve().is_relative_to(ROOT) and '..' not in Path(name).parts,
                'unsafe payload path')
        data = path.read_bytes()
        require(digest(data) == row['sha256'] and len(data) == row['bytes'],
                'payload hash/size mismatch: ' + name)
    require(sum(r['bytes'] for r in rows) == manifest['payload_bytes'], 'payload byte total')

    origins = load('origins.json')
    copies = origins['copies']
    copy_names = [r['package_path'] for r in copies]
    require(len(copy_names) == len(set(copy_names)), 'duplicate origins')
    require(set(copy_names) | set(origins['authored_payloads']) == set(names), 'origin roster join')
    for row in copies:
        data = (ROOT / row['package_path']).read_bytes()
        require(digest(data) == row['stored_sha256'] and len(data) == row['stored_size_bytes'],
                'stored origin mismatch')
        if row['encoding'] == 'gzip_mtime0':
            require(data[4:8] == b'\0\0\0\0', 'nonzero gzip timestamp')
            original = gzip.decompress(data)
        else:
            require(row['encoding'] == 'verbatim', 'unknown origin encoding')
            original = data
        require(digest(original) == row['origin']['sha256'] and
                len(original) == row['origin']['size_bytes'], 'inflated/verbatim origin mismatch')

    parent = origins['parent_references']
    parent_path = (ROOT / parent['parent_manifest']['path']).resolve()
    data = parent_path.read_bytes()
    require(digest(data) == parent['parent_manifest']['sha256'] and
            len(data) == parent['parent_manifest']['size_bytes'], 'parent PR120 manifest pin')
    parent_rows = {r['relative_path']: r for r in json.loads(data)['files']}
    for row in parent['repository_paths_from_exact_parent']:
        require(parent_rows.get(row['relative_path']) == row, 'parent reference row mismatch')
        data = (parent_path.parent / row['relative_path']).read_bytes()
        require(digest(data) == row['sha256'] and len(data) == row['bytes'], 'parent reference bytes')

    scope = load('scope.json')
    summary = load('results/compact-summary.json')
    literal = summary['private_literal_report']
    require(literal == scope['private_report'] == origins['private_report_reference'],
            'private literal report pin joins')
    require(literal['sha256'] == 'f94476c8dcb2ae707fc04a07b6cc6f9afd4ff5d0af4bc19f876710887c491993'
            and literal['size_bytes'] == 1387853, 'wrong literal report')
    require(summary['report_not_redistributed'] and not scope['raw_report_distributed'],
            'private report distribution scope')
    require(summary['negative_OD_acceptance'] == 'FAIL_RETAINED_NO_CLIPPING', 'physical FAIL scope')

    source = load('source/plan.json')
    allow = load('source/allowlist.json')
    runtime = load('runtime/plan.json')
    stage = load('runtime/stage-receipt.json')
    case = load('runtime/case-stage.json')
    bind_bytes('runtime/stage-receipt.json', runtime['stage_receipt_pin'])
    bind_bytes('runtime/case-stage.json', runtime['case_stage_pin'])
    bind_bytes('runtime/run_once.py', {'sha256': runtime['runner_sha256'],
                                   'size_bytes': runtime['runner_size_bytes']})
    require(source['candidate']['sha256'] == runtime['candidate_source']['sha256'] ==
            stage['candidate_source']['sha256'] ==
            '63f6383c698e2e63e9dcde3956f0f936364b38aeffeb23f41284cdfb8e19bf65',
            'executed source72 identities')
    require(allow['identity_count'] == 72 and len(allow['identities']) == 72 and
            allow['groups'] == {'left_censored_prefix69': 69, 'dominant_negative3': 3},
            '72 identity groups')
    identities = [tuple(row[k] for k in allow['fields']) for row in allow['identities']]
    require(len(set(identities)) == 72, 'duplicate selected identities')
    require(case['inputs'] == runtime['held_case']['inputs'] and case['input_count'] == 38,
            'same38 input roster')
    require(len(runtime['protected_source_pins']) == 58 and len(runtime['runtime_library_pins']) == 47,
            'external source/library attestation counts')

    build = load('runtime/build-execution.json')
    built = load('runtime/build-postflight.json')
    solver = load('runtime/solver-execution.json')
    post = load('runtime/solver-postflight.json')
    for label, receipt in [('build', build), ('solver', solver)]:
        require(receipt['actual_child_returncode'] == 0 and receipt['status'] == 'TERMINAL' and
                receipt['reaped'] and not receipt['timed_out'] and receipt['exception'] is None,
                'actual child terminal outcome: ' + label)
    require(built['status'] == 'BUILD_RC0_INCREMENTAL_OPROP_ONLY' and
            built['changed_objects'] == [runtime['oprop_object_relative_path']], 'one-object build')
    before = {r['path']: r['sha256'] for r in runtime['prebuild_objects']}
    after = built['object_hashes_after']
    require(len(before) == len(after) == 21 and set(before) == set(after), '21 object roster')
    require([r for r in before if before[r] != after[r]] == built['changed_objects'],
            '20 held object identities')
    require(post['status'] == 'RC0_OUTPUT_SCOPE_OR_DIAGNOSTIC_HASH_FAILURE' and
            post['actual_child_returncode'] == 0, 'original strict wrapper failure')
    require(post['diagnostic_outputs_byte_exact'] == {
        'UDM37_CANDIDATE_DECISIONS': False, 'UDM37_PANEL_TRACE': True, 'UDM37_R3_TERM_TRACE': True},
        'retained raw-byte strict outcomes')
    require(post['input_bytes_unchanged'] and post['input_pins_before'] == post['input_pins_after']
            and len(post['input_pins_before']) == 38, 'actual38 unchanged input attestation')

    failed = load('reader/failed-v3/execution.json')
    passed = load('reader/executed-v5/execution.json')
    require(failed['pid'] == 2020164 and failed['actual_child_returncode'] == 1 and
            passed['pid'] == 2043083 and passed['actual_child_returncode'] == 0,
            'actual two-reader chronology')
    for receipt in [failed, passed]:
        require(receipt['status'] == 'TERMINAL' and receipt['reaped'] and
                not receipt['timed_out'] and receipt['exception'] is None, 'reader terminal metadata')
    require(load('reader/executed-v5/plan.json')['schema'] ==
            'UDM37_CANDIDATE_DECISION_ANCESTRY_SAVED_READER_PREPARATION_V4', 'v5/V4 history')
    require(summary['strict_original_contract']['wrapper_returncode'] == 3 and
            summary['strict_original_contract']['not_superseded'], 'strict FAIL not superseded')
    compare = summary['scoped_source_defined_comparison']
    require(not compare['byte_sha256_equal'] and compare['strict_byte_identity_failure_preserved']
            and compare['token_fields_equal_except_source_uninitialized_metadata'] and
            compare['allowed_token_differences'] == 25070 and
            compare['rows_with_allowed_metadata_difference'] == 14379, 'limited comparison')
    groups = summary['ancestry_records']['groups']
    require(summary['ancestry_records']['total'] == 72 and
            groups['left_censored_prefix69']['actual_prefilter_records'] == 69 and
            groups['dominant_negative3']['actual_prefilter_records'] == 3, 'event counts')
    require(summary['field_checks'] == {'total': 303, 'prefix_cross_stage': 276,
            'dominant_cross_stage': 12, 'dominant_same_call': 15, 'differences': 0,
            'unit': 'scalar field comparisons, not event or invocation counts'}, 'field counts')
    for name, count in [('left_censored_prefix69', 69), ('dominant_negative3', 3)]:
        for values in summary['strength_signs_and_finiteness'][name].values():
            require(values == {'finite': count, 'positive': count, 'negative': 0, 'zero': 0},
                    'sign/finite counts')
    require(summary['thermal']['count_corrected'] == 72 and
            summary['thermal']['max_abs_residual_combined_SUI_SP_SPPSP'] == 0,
            'saved thermal diagnostic')
    require(summary['spectra']['layers'] == 45 and
            summary['spectra']['samples_bitwise_equal'] == 63838065 and
            summary['spectra']['changed_header_words_only'] == [168], 'saved spectral scope')
    require(load('prospective/plan.json')['status'] ==
            'PROSPECTIVE_UNCOMPILED_UNRUN_DIAGNOSTIC_PATCH', 'prospective fix not executed')
    require(load('primary-audit/erratum-v1.json')['preserved_original']['sha256'] ==
            digest((ROOT / 'primary-audit/audit.json').read_bytes()), 'primary audit erratum ancestry')
    require(load('reviews/reader-terminal-review.json')['status'] ==
            'PASS_SCOPED_DERIVED_REPORT_REVIEW_OUTER_FAILURE_PRESERVED', 'terminal review scope')
    return {'status': 'PASS_SAVED_ARCHIVE_INTEGRITY_STRICT_RAW_FAIL_RETAINED',
            'payloads': len(rows), 'origin_copies': len(copies),
            'manifest_sha256': digest((ROOT / 'manifest.json').read_bytes()),
            'compiled_solver_raw_reader_invocations': 0,
            'physics_acceptance': 'NOT_ESTABLISHED_NEGATIVE_OD_FAIL_RETAINED'}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    if args.output:
        require(not args.output.resolve().is_relative_to(ROOT), 'output must be outside archive')
        require(not args.output.exists(), 'refuse receipt overwrite')
    result = verify()
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        with args.output.open('x') as f:
            json.dump(result, f, indent=2)
            f.write('\n')
    print(json.dumps(result, sort_keys=True))


if __name__ == '__main__':
    main()
