#!/usr/bin/env python3
"""Portable integrity/provenance verifier for the current default-RRTMG4 package.

Uses only Python's standard library. It verifies packaged bytes and recorded
comparison receipts, but does not re-open or numerically compare NetCDF arrays.
"""
from __future__ import annotations
import gzip, hashlib, json, sys
from pathlib import Path, PurePosixPath

ROOT = Path(__file__).resolve().parent
MANIFEST = ROOT / 'evidence_manifest.json'

def fail(message: str) -> None:
    raise SystemExit('FAIL: ' + message)

def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for block in iter(lambda: f.read(1 << 20), b''):
            h.update(block)
    return h.hexdigest()

def read_json(rel: str):
    return json.loads((ROOT / rel).read_text())

def main() -> int:
    if len(sys.argv) != 1:
        fail('this verifier accepts no arguments')
    if not MANIFEST.is_file():
        fail('evidence_manifest.json is missing')
    manifest = json.loads(MANIFEST.read_text())
    if manifest.get('schema') != 'current-default4-evidence-package-v1':
        fail('unexpected manifest schema')
    records = manifest.get('files')
    if not isinstance(records, list) or not records:
        fail('manifest files must be a nonempty list')
    expected = {}
    for row in records:
        rel = row.get('path')
        if not isinstance(rel, str) or not rel:
            fail('invalid manifest path')
        path = PurePosixPath(rel)
        if path.is_absolute() or '..' in path.parts or rel in expected:
            fail(f'unsafe or duplicate path: {rel}')
        expected[rel] = row
    actual = set()
    for p in ROOT.rglob('*'):
        if p.is_symlink():
            fail(f'symlink not allowed in package: {p.relative_to(ROOT)}')
        if p.is_file() and p != MANIFEST:
            actual.add(p.relative_to(ROOT).as_posix())
    if actual != set(expected):
        fail(f'package roster differs: unlisted={sorted(actual-set(expected))}, missing={sorted(set(expected)-actual)}')
    for rel, row in expected.items():
        p = ROOT / rel
        if not p.is_file() or p.stat().st_size != row.get('bytes') or digest(p) != row.get('sha256'):
            fail(f'file integrity mismatch: {rel}')

    pins = read_json('external-source-pins.json')
    if pins.get('schema') != 'current-default4-external-source-pins-v1':
        fail('external pin schema mismatch')
    official = pins['official_pristine']; current = pins['current']; source54 = pins['source54']
    auth = read_json('receipts/root-execution-authorization-v1.json')
    runner_sha = expected['runner/run_current_cases.py']['sha256']
    if auth['runner']['sha256'] != runner_sha:
        fail('authorized runner hash does not match packaged runner')
    pre_sha = expected['reviews/current-prelaunch-review.json']['sha256']
    term_sha = expected['reviews/current-terminal-review.json']['sha256']
    if auth['independent_prelaunch_review']['sha256'] != pre_sha:
        fail('authorization does not bind packaged prelaunch review')
    if current.get('prelaunch_review_sha256') != pre_sha or current.get('terminal_review_sha256') != term_sha:
        fail('external source pins do not bind both independent reviews')
    if current.get('source_head') != '5f3034e9c43209a352977da4885a3fc15b46c532' or current.get('compiled_source_commit') != 'b7b5f6f9cd657408e3bde3018d7e882ab3e4bce3':
        fail('current source identity mismatch')
    if current.get('wrf_tree_equal_between_compiled_and_head') is not True:
        fail('compiled/head WRF tree equality is not established')
    if source54['build_receipt_sha256'] != expected['receipts/source54-build-receipt.json']['sha256']:
        fail('source54 build receipt pin mismatch')
    for key, rel in (('control_receipt_sha256','receipts/source54-control-receipt.json'),('mixed_receipt_sha256','receipts/source54-mixed-receipt.json'),('independent_review_sha256','receipts/source54-independent-review.json')):
        if source54.get(key) != expected[rel]['sha256']:
            fail(f'source54 external receipt pin mismatch: {key}')
    if official.get('comparison_receipt_sha256') != expected['receipts/official-pristine-comparison.json']['sha256']:
        fail('official comparison receipt pin mismatch')
    build = read_json('receipts/current-build-receipt.json')
    if build.get('status') != 'BUILD_PASS' or build.get('returncode') != 0:
        fail('current build receipt is not a successful build')
    if digest(ROOT / 'receipts/current-build-receipt.json') != current['build_receipt_sha256']:
        fail('current build receipt external hash mismatch')
    if official.get('source_commit') != '06d4240ae989cc3e50af412bb472df3d9048783c':
        fail('official pristine source identity mismatch')

    preflight = read_json('receipts/current-preflight.json')
    stage = read_json('receipts/stage-manifest-final.json')
    runtime = read_json('receipts/runtime-comparison.json')
    if preflight.get('status') != 'READY_NOT_RUN' or preflight.get('models_invoked') != 0:
        fail('preflight is not a zero-run preflight record')
    if preflight.get('target_source_commit') != current['source_head'] or preflight.get('build_commit') != current['compiled_source_commit']:
        fail('preflight source/build commit identity mismatch')
    if preflight.get('binary_sha256') != current['binary_sha256'] or preflight.get('configure_sha256') != current['configure_sha256']:
        fail('preflight binary/configuration pins mismatch')
    if current.get('input_stage_sha256') != expected['receipts/input-stage.json']['sha256'] or current.get('preflight_sha256') != expected['receipts/current-preflight.json']['sha256'] or current.get('stage_manifest_sha256') != expected['receipts/stage-manifest-final.json']['sha256']:
        fail('external pin set does not bind the staged inputs and preflight')
    if preflight.get('runner_sha256') != runner_sha or preflight.get('build_receipt_sha256') != current['build_receipt_sha256'] or preflight.get('source_manifest_sha256') != current['source_manifest_sha256']:
        fail('preflight does not bind runner/build/source manifest')
    if stage.get('status') != 'READY_NOT_RUN' or stage.get('planned_runs') != 2:
        fail('stage manifest scope/status mismatch')
    if stage.get('runner', {}).get('sha256') != runner_sha:
        fail('stage manifest does not pin the packaged runner')
    terminal = read_json('reviews/current-terminal-review.json')
    pre_review = read_json('reviews/current-prelaunch-review.json')
    if terminal.get('status') != 'PASS_SCOPED_TWO_CURRENT_SOURCE_SCM_CASES' or terminal.get('source_head') != current['source_head'] or terminal.get('executable_sha256') != current['binary_sha256']:
        fail('independent terminal review identity/status mismatch')
    if terminal.get('executed_model_count') != 2 or terminal.get('reviewer_model_invocations') != 0 or terminal.get('reviewer_build_invocations') != 0:
        fail('terminal review invocation accounting mismatch')
    if pre_review.get('status') != 'PASS_SCOPED_PRELAUNCH_ONLY':
        fail('independent prelaunch review is not a scoped pass')
    # The original summary may omit executed_model_count; the two durable
    # per-case records remain authoritative. An explicit wrong count is invalid.
    if runtime.get('schema') != 'current-source-pristine-serial-ra4-regression-v1' or runtime.get('executed_model_count') not in (None, 2):
        fail('runtime comparison schema or invocation count mismatch')
    expected_times = [f'1999-10-22_19:00:{s:02d}' for s in range(0, 60, 10)] + ['1999-10-22_19:01:00']
    for case in ('control', 'mixed'):
        receipt = read_json(f'receipts/{case}-receipt.json')
        execution = read_json(f'receipts/{case}-execution.json')
        source54_receipt = read_json(f'receipts/source54-{case}-receipt.json')
        if receipt.get('status') != 'PASS' or receipt.get('case') != case:
            fail(f'{case} current case receipt is not PASS')
        if execution.get('returncode') != 0 or execution.get('case') != case:
            fail(f'{case} durable execution result is not RC 0')
        checks = receipt.get('runtime_checks', {})
        if receipt.get('process', {}).get('returncode') != 0 or not checks.get('success_complete_marker'):
            fail(f'{case} case receipt does not record successful process/log completion')
        for gate in ('static_pins_unchanged','runtime_assets_unchanged','staged_inputs_unchanged','official_baseline_assets_unchanged','source54_assets_unchanged','official_baseline_history_unchanged'):
            if checks.get(gate) is not True:
                fail(f'{case} immutability gate did not pass: {gate}')
        if source54_receipt.get('status') != 'PASS' or source54_receipt.get('case') != case:
            fail(f'{case} source54 receipt is not PASS')
        for key in ('comparison', 'source54_comparison'):
            comp = receipt.get(key)
            if not isinstance(comp, dict) or comp.get('status') != 'PASS':
                fail(f'{case} {key} did not pass')
            if comp.get('common_variable_count') != 208 or len(comp.get('equal_variables', [])) != 208:
                fail(f'{case} {key} does not record all 208 equal variables')
            names=comp.get('equal_variables', [])
            if len(set(names)) != 208:
                fail(f'{case} {key} equal-variable list contains duplicates')
            if comp.get('different_variables') or comp.get('missing_variables') or comp.get('extra_variables'):
                fail(f'{case} {key} records variable differences')
            if comp.get('whole_file_sha256_equal') is not True or comp.get('whole_file_sha256_actual') != comp.get('whole_file_sha256_reference'):
                fail(f'{case} {key} full NetCDF file hashes are not equal')
            if comp.get('issues') or comp.get('dimension_differences') or comp.get('global_attribute_differences'):
                fail(f'{case} {key} schema/attribute issues are recorded')
        actual_hash = receipt['comparison']['whole_file_sha256_actual']
        if receipt['comparison']['equal_variables'] != receipt['source54_comparison']['equal_variables']:
            fail(f'{case} official/source54 variable rosters differ')
        official_hash = official['history_sha256'][case]
        if actual_hash != official_hash or source54['history_sha256'][case] != official_hash:
            fail(f'{case} actual, official, and source54 history hashes differ')

        gzrel = manifest['history_outputs'][case]['package_path']
        gzpath = ROOT / gzrel
        expected_hash = official['history_sha256'][case]
        h = hashlib.sha256(); total = 0
        with gzip.open(gzpath, 'rb') as f:
            for block in iter(lambda: f.read(1 << 20), b''):
                h.update(block); total += len(block)
        if h.hexdigest() != expected_hash or total != manifest['history_outputs'][case]['uncompressed_bytes']:
            fail(f'{case} compressed history does not decompress to pinned official bytes')
        if manifest['history_outputs'][case]['uncompressed_sha256'] != expected_hash:
            fail(f'{case} compressed-history manifest provenance mismatch')

    rows = terminal.get('cases', [])
    if [r.get('case') for r in rows] != ['control', 'mixed']:
        fail('runtime summary case order/content mismatch')
    for row in rows:
        case = row['case']
        if row.get('process_RC') != 0 or row.get('variable_count') != 208 or row.get('numeric_variables') != 207:
            fail(f'{case} aggregate runtime result is not the expected successful 208-variable run')
        if row.get('data_model') != 'NETCDF4' or row.get('Times') != expected_times:
            fail(f'{case} runtime model or Times record mismatch')
        if row.get('history_sha256') != official['history_sha256'][case]:
            fail(f'{case} aggregate history SHA mismatch')
        if row.get('case_receipt_sha256') != expected[f'receipts/{case}-receipt.json']['sha256']:
            fail(f'{case} independent review does not bind the packaged case receipt')
        if row.get('durable_execution_receipt_sha256') != expected[f'receipts/{case}-execution.json']['sha256']:
            fail(f'{case} independent review does not bind the packaged execution receipt')
        if not row.get('numeric_decoded_finite_unmasked_default_fill_checked'):
            fail(f'{case} numeric quality gate is not recorded')
        comps = row.get('comparisons', [])
        if len(comps) != 2 or any(not c.get('wholefile_equal') or not c.get('all208_raw_schema_data_model_attributes_equal') for c in comps):
            fail(f'{case} aggregate comparison contract did not pass')
        if any(c.get('reference_sha256') != official['history_sha256'][case] for c in comps):
            fail(f'{case} terminal review references do not match pinned official history')
    print('PASS: closed roster, package hashes, provenance joins, process receipts, 208-variable comparison records, seven Times, and compressed history hashes verified.')
    print('LIMIT: this portable verifier does not reopen NetCDF arrays; use the documented optional netCDF4 check for direct array inspection.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
