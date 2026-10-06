#!/usr/bin/env python3
"""Offline integrity checks for the archived historical-source experiment."""
from __future__ import annotations
import argparse
import csv
import hashlib
import json
import math
from pathlib import Path


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def read_json(path: Path):
    return json.loads(path.read_text())


def verify(package: Path) -> dict:
    package = package.resolve()
    manifest = read_json(package / 'manifest.json')
    manifest_rows = manifest.get('files', [])
    rows = {row['path']: row for row in manifest_rows}
    if len(rows) != len(manifest_rows):
        raise ValueError('duplicate manifest path')
    actual = {p.relative_to(package).as_posix() for p in package.rglob('*')
              if p.is_file() and p.relative_to(package).as_posix() != 'manifest.json'}
    if actual != set(rows) or manifest.get('file_count') != len(rows):
        raise ValueError('closed package roster mismatch')
    for rel, row in rows.items():
        raw = (package / rel).read_bytes()
        if (len(raw), sha(raw)) != (row.get('size_bytes'), row.get('sha256')):
            raise ValueError('payload hash/size mismatch: ' + rel)
        if Path(rel).suffix.lower() in {'.nc', '.o', '.a', '.so'} or rel == 'rrtmgp_rfmip_sw_diag':
            raise ValueError('binary or NetCDF payload unexpectedly included: ' + rel)

    origins = read_json(package / 'receipts/origin-inventory.json').get('origins', [])
    origin_by_path = {row['package_path']: row for row in origins}
    authored = {'README.md', 'verify.py', 'receipts/origin-inventory.json'}
    expected_origins = set(rows) - authored
    if len(origin_by_path) != len(origins) or set(origin_by_path) != expected_origins:
        raise ValueError('origin inventory must cover every verbatim payload exactly once')
    for rel, origin in origin_by_path.items():
        row = rows[rel]
        if (origin.get('sha256'), origin.get('size_bytes')) != (row['sha256'], row['size_bytes']):
            raise ValueError('origin hash/size does not join package payload: ' + rel)

    plan = read_json(package / 'analysis/plan.json')
    execution = read_json(package / 'receipts/execution.json')
    launched = read_json(package / 'receipts/launched.json')
    build = read_json(package / 'receipts/build-receipt.json')
    analysis = read_json(package / 'analysis/result.json')
    residual = read_json(package / 'analysis/residual-details.json')
    loader = read_json(package / 'receipts/loader-equivalence.json')
    source_fetch = read_json(package / 'receipts/source-fetch.json')
    strict_inventory = read_json(package / 'receipts/strict-inventory.json')
    source_tree = read_json(package / 'source/v1.0-tree.json')
    pre = read_json(package / 'reviews/pre-run-review.json')
    post = read_json(package / 'reviews/post-run-review.json')
    residual_review = read_json(package / 'reviews/residual-review.json')
    source_review = read_json(package / 'reviews/source-math-review.json')

    def payload_pin(rel):
        row = rows[rel]
        return {'path': str((package / rel).resolve()), 'sha256': row['sha256'], 'size': row['size_bytes']}

    def matches_record(record, rel):
        pin = payload_pin(rel)
        return (record.get('sha256') == pin['sha256'] and
                record.get('bytes', record.get('size')) == pin['size'])

    if plan.get('schema') != 'udm37-historical-source-experiment-v1' or plan.get('source_commit') != 'ed5b0113109fcd23a010a90c61f21bad551146ef':
        raise ValueError('historical experiment plan/source identity mismatch')
    if sha((package / 'analysis/plan.json').read_bytes()) != build.get('plan_sha256'):
        raise ValueError('build receipt is not bound to archived plan')
    if source_fetch.get('source_pin') != plan.get('source_commit'):
        raise ValueError('source-fetch receipt does not match planned source revision')
    if source_fetch.get('model_build_solver_calls') != 0:
        raise ValueError('source-fetch record unexpectedly claims execution')
    if launched.get('source_commit') != plan.get('source_commit') or launched.get('argv') != execution.get('argv') or launched.get('started_epoch') != execution.get('started_epoch'):
        raise ValueError('launch and terminal execution receipts do not join')
    for key, rel in [('plan', 'analysis/plan.json'), ('build_receipt', 'receipts/build-receipt.json'),
                     ('pre_run_review', 'reviews/pre-run-review.json'), ('runner', 'scripts/run.py'),
                     ('loader_equivalence', 'receipts/loader-equivalence.json')]:
        if not matches_record(launched.get('pins', {}).get(key, {}), rel):
            raise ValueError('launch receipt pin mismatch: ' + key)
    if not matches_record(execution.get('pins', {}).get('plan', {}), 'analysis/plan.json'):
        raise ValueError('execution receipt plan pin mismatch')
    for key, rel in [('build_receipt', 'receipts/build-receipt.json'),
                     ('pre_run_review', 'reviews/pre-run-review.json'),
                     ('runner', 'scripts/run.py'),
                     ('loader_equivalence', 'receipts/loader-equivalence.json')]:
        if not matches_record(execution.get('pins', {}).get(key, {}), rel):
            raise ValueError('execution receipt pin mismatch: ' + key)
    pins = plan.get('pins', {})
    for key, rel in [('original_driver', 'source/rrtmgp_rfmip_sw.F90'),
                     ('diagnostic_driver', 'source/rrtmgp_rfmip_sw_diag.F90'),
                     ('observer_patch', 'source/observer.patch')]:
        if not matches_record(pins.get(key, {}), rel):
            raise ValueError('plan source pin mismatch: ' + key)
    for key, rel in [('profile_selector', 'analysis/profile-selector.txt'),
                     ('failure_selector', 'analysis/failure-selector.csv')]:
        if not matches_record(pins.get(key, {}), rel):
            raise ValueError('plan selector pin mismatch: ' + key)
    if source_tree.get('sha') != plan.get('source_commit'):
        raise ValueError('archived historical Git tree does not match source commit')
    tree_blobs = {row.get('path'): row.get('sha') for row in source_tree.get('tree', []) if row.get('type') == 'blob'}
    tracked = [row for row in plan.get('source_files', [])]
    expected_source_paths = {
        'examples/rfmip-clear-sky/rrtmgp_rfmip_sw.F90': 'source/rrtmgp_rfmip_sw.F90',
        'LICENSE': 'source/LICENSE',
    }
    for upstream, rel in expected_source_paths.items():
        source_row = next((row for row in tracked if row.get('path', '').endswith('/source/' + upstream)), None)
        if not source_row or tree_blobs.get(upstream) != source_row.get('git_blob_sha1'):
            raise ValueError('source tree blob does not join the experiment source inventory: ' + upstream)
        if not matches_record(source_row, rel):
            raise ValueError('archived source file does not match experiment source inventory: ' + upstream)
    for key, rel in [('analyzer', 'scripts/analyze.py'), ('execution', 'receipts/execution.json')]:
        if not matches_record(analysis.get('pins', {}).get(key, {}), rel):
            raise ValueError('analysis pin mismatch: ' + key)
    if not matches_record(residual.get('pins', {}).get('analyzer', {}), 'scripts/residual_details.py'):
        raise ValueError('residual analyzer pin mismatch')
    if not matches_record(residual.get('pins', {}).get('frozen_analysis', {}), 'analysis/result.json'):
        raise ValueError('residual analysis pin mismatch')
    if not matches_record(residual_review.get('pins', {}).get('residual-details.json', {}), 'analysis/residual-details.json'):
        raise ValueError('independent residual review pin mismatch')
    for key, rel in [('analysis.json', 'analysis/result.json'),
                     ('plan.json', 'analysis/plan.json'),
                     ('analyze.py', 'scripts/analyze.py'),
                     ('run.py', 'scripts/run.py'),
                     ('observer.patch', 'source/observer.patch'),
                     ('execution.json', 'receipts/execution.json'),
                     ('build-receipt.json', 'receipts/build-receipt.json'),
                     ('pre-run-review.json', 'reviews/pre-run-review.json')]:
        if not matches_record(post.get('pins', {}).get(key, {}), rel):
            raise ValueError('post-run review input pin mismatch: ' + key)
    for key, rel in [('analysis.json', 'analysis/result.json'),
                     ('analyze.py', 'scripts/analyze.py'),
                     ('post-run-review.json', 'reviews/post-run-review.json'),
                     ('residual-details.json', 'analysis/residual-details.json'),
                     ('residual_details.py', 'scripts/residual_details.py')]:
        if not matches_record(residual_review.get('pins', {}).get(key, {}), rel):
            raise ValueError('residual review input pin mismatch: ' + key)

    if execution.get('status') != 'COMPLETE_ONE_HISTORICAL_STANDALONE_NOT_ACCURACY_VERDICT' or execution.get('returncode') != 0:
        raise ValueError('historical standalone execution did not complete with its scoped status')
    if execution.get('new_SW_standalone_calls') != 1 or execution.get('new_WRF_REAL_or_forecast_calls') != 0:
        raise ValueError('historical execution call counts mismatch')
    if build.get('status') != 'PASS_BUILD_NO_SOLVER' or build.get('solver_invocations') != 0 or build.get('WRF_or_REAL_invocations') != 0:
        raise ValueError('historical build receipt scope mismatch')
    exe = build.get('executable', {})
    if len(exe.get('sha256', '')) != 64 or not isinstance(exe.get('size'), int) or exe['size'] <= 0:
        raise ValueError('build executable identity malformed')
    if not execution.get('argv') or execution['argv'][0] != exe.get('path'):
        raise ValueError('executed binary path does not match build receipt')
    if pre.get('status') != 'PASS_SCOPED_SOURCE_OBSERVER_STATIC' or pre.get('blockers_in_observer_source') != []:
        raise ValueError('pre-run source/observer review not passing')
    if post.get('status') != 'PASS_SCOPED_SAVED_EVIDENCE_REVIEW_STRICT_COMPARISON_FAILS' or post.get('material_blockers') != []:
        raise ValueError('post-run evidence review scope/status mismatch')
    if residual_review.get('status') != 'PASS_SCOPED_SAVED_RESIDUAL_DETAILS_STRICT_FAIL_PRESERVED' or residual_review.get('material_blockers') != []:
        raise ValueError('residual review scope/status mismatch')
    if source_review.get('status') != 'READ_ONLY_STATIC_AUDIT':
        raise ValueError('source-math review scope/status mismatch')
    metrics = source_review.get('observed_retained_metrics', {})
    optics = analysis.get('capture_comparison', {}).get('optics', {}).get('fields', {})
    if (metrics.get('tau_max_abs') != optics.get('tau', {}).get('max_abs') or
            metrics.get('ssa_max_abs') != optics.get('ssa', {}).get('max_abs') or
            metrics.get('asymmetry_g_max_abs') != optics.get('g', {}).get('max_abs')):
        raise ValueError('source-math review metrics do not match analysis')

    if analysis.get('status') != 'COMPLETE_DIAGNOSTIC_NOT_ACCURACY_VERDICT':
        raise ValueError('analysis status mismatch')
    if analysis.get('historical_full_strict_failures') != 21 or analysis.get('retained_current_old_solar_full_strict_failures') != 155:
        raise ValueError('full-array strict comparison counts mismatch')
    if analysis.get('raw_historical_source_exact_to_promoted_coefficient') is not True:
        raise ValueError('historical source/coefficient consumed-vector identity not recorded')
    if analysis.get('written_casts_exact_for_both_135_profile_captures') is not True:
        raise ValueError('captured output cast verification missing')
    if analysis.get('capture_comparison', {}).get('flux_solver', {}).get('metrics', {}).get('max_abs') != 8.128138233587379e-07:
        raise ValueError('selected double-flux maximum does not match frozen result')
    selector_rows = [line.split() for line in (package / 'analysis/profile-selector.txt').read_text().splitlines() if line.strip()]
    selected = [(int(row[0]), int(row[1])) for row in selector_rows if len(row) == 2]
    if len(selector_rows) != 135 or len(selected) != 135 or len(set(selected)) != 135 or any(not (1 <= e <= 18 and 1 <= s <= 100) for e, s in selected):
        raise ValueError('profile selector must contain 135 unique valid (experiment,site) pairs')
    with (package / 'analysis/failure-selector.csv').open(newline='') as stream:
        selector_csv = list(csv.DictReader(stream))
    if len(selector_csv) != 155 or sum(row.get('variable') == 'rsd' for row in selector_csv) != 116 or sum(row.get('variable') == 'rsu' for row in selector_csv) != 39:
        raise ValueError('failure selector roster/count mismatch')
    coord_rows = [(row['variable'], int(row['expt_index0']), int(row['site_index0']), int(row['level_index0'])) for row in selector_csv]
    if len(set(coord_rows)) != 155 or any(v not in ('rsd', 'rsu') or not (0 <= e < 18 and 0 <= s < 100 and 0 <= k < 61) for v, e, s, k in coord_rows):
        raise ValueError('failure selector coordinate validation failed')
    full = analysis.get('full_outputs', {})
    if (full.get('rsd', {}).get('historical_vs_reference_ULP_histogram') != {'0': 109784, '1': 16} or
            full.get('rsu', {}).get('historical_vs_reference_ULP_histogram') != {'0': 109688, '1': 112}):
        raise ValueError('stored float32 ULP histogram mismatch')
    if full.get('rsd', {}).get('historical_vs_reference', {}).get('max_abs') != 6.103515625e-05 or full.get('rsu', {}).get('historical_vs_reference', {}).get('max_abs') != 3.0517578125e-05:
        raise ValueError('full-array historical residual maxima mismatch')
    strict = strict_inventory.get('strict_gate', {}).get('failures', {})
    if (sum(strict.get(v, {}).get('failed_cells', -1) for v in ('rsd', 'rsu')) != 104071 or
            sum(strict.get(v, {}).get('failed_cells', -1) for v in ('rld', 'rlu')) != 0):
        raise ValueError('inherited current-reference strict count mismatch')
    if strict_inventory.get('v4_failure_selector_and_v5_diagnostic', {}).get('v4_selector', {}).get('selected_failure_counts') != {'rsd': 116, 'rsu': 39, 'total': 155}:
        raise ValueError('inherited old-solar selector count mismatch')
    for v in ('rsd', 'rsu'):
        experiment_output = execution.get('outputs', {}).get(v, {})
        analyzed_output = full.get(v, {}).get('historical_pin', {})
        if (experiment_output.get('sha256'), experiment_output.get('size')) != (analyzed_output.get('sha256'), analyzed_output.get('bytes')):
            raise ValueError('execution/output analysis pin mismatch: ' + v)
    counts = residual.get('counts', {})
    expected_counts = {'full_strict_failures': 21, 'selected_failures': 13,
                       'new_failures_outside_original_selector': 8,
                       'captured_failure_cells': 13, 'uncaptured_failure_cells': 8,
                       'captured_historical_prewrite_strict_failures': 8,
                       'captured_midpoint_ties': 0}
    if any(counts.get(k) != v for k, v in expected_counts.items()):
        raise ValueError('residual summary counts mismatch')
    residual_rows = residual.get('residual_cells', [])
    captured = [r for r in residual_rows if r.get('profile_captured')]
    uncaptured = [r for r in residual_rows if not r.get('profile_captured')]
    uncaptured_profiles = {tuple(r['index0_experiment_site_level'][:2]) for r in uncaptured}
    if len(residual_rows) != 21 or len(captured) != 13 or len(uncaptured) != 8 or len(uncaptured_profiles) != 8:
        raise ValueError('residual cell/capture profile roster mismatch')
    if any(not r.get('historical_rounding', {}).get('prewrite_outside_closed_reference_rounding_interval') for r in captured):
        raise ValueError('captured residual midpoint classification mismatch')
    distances = []
    for row in captured:
        detail = row['historical_rounding']
        lo, hi = detail['reference_float32_rounding_interval_W_m2']
        value = detail['prewrite_W_m2']
        distances.append(max(lo - value, value - hi, 0.0))
    if not (math.isclose(min(distances), 4.940261533192825e-10, rel_tol=1e-12, abs_tol=1e-21) and
            math.isclose(max(distances), 1.4248405477701453e-07, rel_tol=1e-12, abs_tol=1e-18)):
        raise ValueError('captured prewrite/reference quantization interval distance range mismatch')
    prewrite_failures = [row for row in captured if row['historical_rounding']['prewrite_strict_fail']]
    stored_only = [row for row in captured if abs(row['historical_stored_minus_reference_W_m2']) > 1e-5 and not row['historical_rounding']['prewrite_strict_fail']]
    if len(prewrite_failures) != 8 or len(stored_only) != 5 or any(row['variable'] != 'rsu' for row in stored_only):
        raise ValueError('prewrite versus float32 stored-threshold crossing counts mismatch')

    if loader.get('coefficient_consumption', {}).get('historical_vs_v5_counterfactual_common_non_solar_variable_count') != 29 or loader.get('coefficient_consumption', {}).get('common_non_solar_all_names_exact_dtype_shape_and_values') is not True:
        raise ValueError('loader-equivalence intersection receipt mismatch')
    if loader.get('reuse_decision', {}).get('current_code_old_effective_coefficients_arm') != 'REUSE_V5_OLD_SOLAR_ARM_NO_RERUN':
        raise ValueError('loader-equivalence reuse record mismatch')
    if (loader.get('historical_coefficients', {}).get('sha256') != pins.get('coefficient', {}).get('sha256') or
            loader.get('rfmip_input_and_boundaries', {}).get('input_sha256') != pins.get('input', {}).get('sha256')):
        raise ValueError('loader-equivalence source/input pins do not match experiment plan')
    for key in ('flux_solver', 'flux_written', 'optics', 'source_pre', 'source_post'):
        execution_pin = execution.get('captures', {}).get(key, {})
        analysis_pin = analysis.get('capture_comparison', {}).get(key, {}).get('historical_pin', {})
        if (execution_pin.get('sha256'), execution_pin.get('size')) != (analysis_pin.get('sha256'), analysis_pin.get('bytes')):
            raise ValueError('execution/analysis capture pin mismatch: ' + key)
    return {'status': 'PASS_SCOPED_HISTORICAL_SOURCE_EVIDENCE_ARCHIVE',
            'payload_files_checked': len(rows), 'historical_source_commit': plan['source_commit'],
            'historical_candidate_strict_failures': 21, 'inherited_old_solar_strict_failures': 155,
            'uncaptured_failure_profiles': len(uncaptured_profiles), 'solver_model_or_network_calls': False,
            'scope': 'One historical-source SW g224 candidate; no original CMIP6 generator identity or accuracy pass.'}


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--package', type=Path, default=Path(__file__).resolve().parent)
    args = ap.parse_args()
    print(json.dumps(verify(args.package), sort_keys=True))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
