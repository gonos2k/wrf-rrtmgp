#!/usr/bin/env python3
"""Curate existing pinned evidence. No model/build/helper/Git imports or calls."""
import csv
import datetime
import hashlib
import json
from pathlib import Path
import shutil

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
OUT = HERE / 'package-v1'


def need(c, message):
    if not c:
        raise ValueError(message)


def pin(p):
    p = Path(p)
    p = (p if p.is_absolute() else ROOT / p).resolve(strict=True)
    h = hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda: f.read(1048576), b''):
            h.update(b)
    return {'path': str(p), 'sha256': h.hexdigest(), 'size_bytes': p.stat().st_size}


def canon(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


externals = {}
origins = []


def read(p):
    q = pin(p)
    externals[q['path']] = q
    return json.loads(Path(q['path']).read_text())


def write(name, obj):
    p = OUT / name
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open('x') as f:
        f.write(json.dumps(obj, sort_keys=True, indent=2) + '\n')


def copy(name, p):
    before = pin(p)
    q = OUT / name
    q.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(before['path'], q)
    need(pin(before['path']) == before and pin(q)['sha256'] == before['sha256'], 'copy changed')
    origins.append({'retained_path': name, 'original': before})


def field_summary(q):
    need(q['passed'] and len(q['numeric_variables']) == q['numeric_variable_count'], 'strict field/count')
    need(q['default_fill_check'] == {'hits': {}, 'passed': True}, 'default fill')
    need(all(x['passed'] and x['raw_nonfinite'] == x['decoded_nonfinite'] == x['mask_hits'] == 0 and not any(x['explicit_fill_or_missing_hits'].values()) for x in q['numeric_variables'].values()), 'numeric contract')
    need(pin(q['file']['path']) == q['file'], 'output pin changed')
    externals[q['file']['path']] = q['file']
    r = {k: q[k] for k in ('file', 'variable_count', 'numeric_variable_count', 'ordered_times', 'expected_times', 'physics', 'geometry', 'passed')}
    r.update(raw_decoded_finite_unmasked=True, default_fill_hits=0, metadata_canonical_sha256=canon(q['metadata']), numeric_checks_canonical_sha256=canon(q['numeric_variables']))
    for k in ('surface', 'cu_positive_cells', 'icloud_cu', 'sw_positive_cells'):
        if k in q:
            r[k] = q[k]
    return r


models = []


def model(family, arm, path):
    e = read(path)
    need(e['status'] in ('PASS', 'PASS_ARM', 'PASS_SCOPED_24H_NEW_CCN_SOURCE') and e['actual_model_invocations'] == 1 and e['after_pins_valid'] and e['outputs']['passed'], 'terminal model')
    before = e.get('before_pins_valid')
    if before is None:
        if family == 'restart-attempt':
            need(e['before_build_identity'] == e['after_build_identity'], 'restart before/after build identity')
        else:
            need(e['pre_run_pins'] == e['post_run_pins'], 'official pins')
    else:
        need(before, 'before pins')
    m = e['model']
    need(m['returncode'] == 0 and m['model_completed'] and not m['timed_out'] and len(m['rank_logs']) == 4 and all(x['success'] and not x['fatal'] for x in m['rank_logs']), 'model/ranks')
    outs = e['outputs']
    fields = {'history': field_summary(outs['history'])}
    if 'checkpoint' in outs:
        fields['checkpoint'] = field_summary(outs['checkpoint'])
    else:
        fields['checkpoints'] = [field_summary(q) for q in outs['checkpoints']]
    models.append({'family': family, 'arm': arm, 'original_status': e['status'], 'receipt': pin(path), 'actual_model_invocations': 1, 'strict_outputs_passed': True, 'before_after_pins_passed': True, 'model': m, 'runtime_env': e.get('runtime_env', e.get('runtime_environment')), 'runner': e.get('runner', {'sha256': e.get('runner_sha256')}), 'stage': e['stage'], 'fields': fields})
    return e


pairs = []


def table(family, key, q, original, derivation=None):
    rows = q['ledger']
    need(len(rows) == len({r['name'] for r in rows}), 'duplicate field')
    need(all(r['equal'] == (r['left_sha'] == r['right_sha']) for r in rows), 'hash/equality')
    need(q['passed'] == (q['metadata_equal'] and all(r['equal'] for r in rows)), 'pair status')
    need(q['whole_file_equal'] == (q['left']['sha256'] == q['right']['sha256']), 'whole-file status')
    name = 'tables/' + family + '-' + key + '.csv'
    (OUT / 'tables').mkdir(exist_ok=True)
    with (OUT / name).open('x', newline='') as f:
        w = csv.writer(f)
        w.writerow(['variable', 'dtype', 'shape_json', 'left_sha256', 'right_sha256', 'equal'])
        for r in rows:
            w.writerow([r['name'], r['dtype'], json.dumps(r['shape'], separators=(',', ':')), r['left_sha'], r['right_sha'], str(r['equal']).lower()])
    item = {k: v for k, v in q.items() if k != 'ledger'}
    item.update(family=family, key=key, table=name, field_count=len(rows), unequal_fields=sum(not r['equal'] for r in rows), original_comparison_receipt=pin(original), original_ledger_canonical_sha256=canon(rows))
    if derivation:
        item['derivation'] = derivation
    pairs.append(item)


def main():
    need(not OUT.exists() and not OUT.is_symlink(), 'package collision')
    # Freeze preparation inputs before mutations. No runtime helper is loaded.
    v5 = read('build/udm-cu-current-omp-evidence-plan-v5/inclusion-index-v5.json')
    need(v5['status'] == 'PREPARATION_ONLY_24H_PASS_RESTART_PENDING', 'v5 scope')
    need(pin('build/udm37-ccn-runtime-evidence-v1/verify.py')['size_bytes'] > 0, 'verifier missing')
    OUT.mkdir()
    for family, base, arms in [
        ('old-ra37', 'build/udm-cu-current-omp-runtime-v2/cases', ('omp1', 'omp2', 'omp2-probe')),
        ('old-ra4', 'build/udm-cu-current-omp-ra4-control-v1/cases', ('omp1', 'omp2')),
        ('early-ra4', 'build/udm-cu-current-omp-early-ra4-v1/cases', ('omp1', 'omp2')),
        ('new-3h', 'build/udm37-ccn-current-runtime-v1/cases/stage-v3', ('ra37-omp1', 'ra37-omp2', 'ra37-omp2-probe', 'ra4-omp1')),
    ]:
        for arm in arms:
            model(family, arm, base + '/' + arm + '/execution.json')
        p = base + '/comparison.json'
        d = read(p)
        if family == 'early-ra4':
            for field in ('history', 'checkpoint'):
                table(family, field, {'field': field, 'pair': ['omp1', 'omp2'], **d[field + '_file_comparison']}, p)
            write('receipts/early-minute-observations.json', {'original': pin(p), 'schema': d['schema'], 'scope': d['scope'], 'status': d['status'], 'frame_comparison': d['frame_comparison']})
        else:
            for i, q in enumerate(d['pairs']):
                q = dict(q)
                q.setdefault('pair', ['omp1', 'omp2'])
                table(family, str(i) + '-' + q['field'], q, p)
    for arm in ('omp1', 'omp2'):
        model('official-ra4', arm, 'build/pristine-current-omp-control-v2/' + arm + '-execution.json')
    official_path = 'build/pristine-current-omp-control-v2/comparison.json'
    official = read(official_path)
    cross_path = 'build/pristine-current-omp-control-v2/root-patched-ra4-cross-source-v1.json'
    cross = read(cross_path)
    for q in cross['pairs']:
        field = 'history' if q['field'].startswith('wrfout') else 'checkpoint'
        table('official-patched-ra4', q['arm'] + '-' + field, {**q, 'field': field, 'pair': ['official-' + q['arm'], 'patched-' + q['arm']]}, cross_path)
    # Official original comparator retains mismatch rows only. Complete hashes
    # are already measured in root cross-source ledgers; derive a complete
    # official pair from their official LEFT array hashes without new IO/replay.
    for field in ('history', 'checkpoint'):
        groups = {q['arm']: q for q in cross['pairs'] if q['field'].startswith('wrfout' if field == 'history' else 'wrfrst')}
        left = groups['omp1']; right = groups['omp2']
        by = {r['name']: r for r in right['ledger']}
        rows = []
        for a in left['ledger']:
            b = by[a['name']]
            need(a['dtype'] == b['dtype'] and a['shape'] == b['shape'], 'official raw layout')
            rows.append({'name': a['name'], 'dtype': a['dtype'], 'shape': a['shape'], 'left_sha': a['left_sha'], 'right_sha': b['left_sha'], 'equal': a['left_sha'] == b['left_sha']})
        mismatches = {r['name'] for r in rows if not r['equal']}
        check = official['omp1_vs_omp2_' + field]
        original_names = {r['variable'] for r in check['differences']} if field == 'history' else set(check['raw_mismatches'])
        need(mismatches == original_names and len(rows) == (222 if field == 'history' else 664), 'official mismatch reconstruction')
        table('official-ra4', field, {'field': field, 'pair': ['omp1', 'omp2'], 'ledger': rows, 'left': left['left'], 'right': right['left'], 'metadata_equal': True, 'passed': False, 'whole_file_equal': False}, official_path, {'kind': 'Derived complete per-variable hashes from already-measured official LEFT arrays in two root cross-source ledgers; no array/model process invoked.', 'cross_source_receipt': pin(cross_path), 'matches_all_original_mismatch_names': True})
    new24 = model('new-24h', 'ra37-omp2', 'build/udm37-ccn-winter24h-v1/execution.json')
    table('new-24h', 'historical-history', {'field': 'history', 'pair': ['new-ra37-omp2-tiles2', 'old-ra37-omp1-one-tile'], **new24['outputs']['old_one_tile_history_comparison']}, 'build/udm37-ccn-winter24h-v1/execution.json')
    need(len(models) == 14 and len(pairs) == 21 and sum(q['field_count'] for q in pairs) == 9097, 'curation count')
    restart_path = 'build/udm37-ccn-restart-runtime-v1/cases-v1/comparison.json'
    restart = read(restart_path)
    need(pin(restart_path)['sha256'] == '7e9682c25b1303bd71f22c1c0ac117bb4baa0b3fd62b14abe39cdcc2ba681dca' and restart['status'] == 'FAIL_PRESERVED', 'restart failure pin')
    for arm in ('continuous-omp2', 'restart-omp1', 'restart-omp2'):
        model('restart-attempt', arm, 'build/udm37-ccn-restart-runtime-v1/cases-v1/' + arm + '/execution.json')
    for q in restart['pairs'][5:]:
        table('restart-own-omp', q['field'], {**q, 'pair': ['restart-omp1', 'restart-omp2']}, restart_path)
    write('receipts/restart-strict-failure-derived.json', {'original': pin(restart_path), 'original_status': restart['status'], 'attributed_final_outcome': 'UNDER_ROOT_REVIEW', 'root_causal_interpretation': 'NOT_FINAL', 'first_five_exact_check_results': restart['pairs'][:5], 'own_thread_raw_equality_retained_separately': True})
    need(len(models) == 17 and len(pairs) == 23 and sum(q['field_count'] for q in pairs) == 9986, 'expanded curation count')
    # Exact small original receipts, all failure classes, executed sources.
    for p in [
        'build/udm37-ccn-tile-init-pr-work/validation/rrtmgp37/udm-ccn-tile-startup/pre-change-observations.json',
        'build/udm37-ccn-tile-init-pr-work/validation/rrtmgp37/udm-ccn-tile-startup/post-fix-observations.json',
        'build/udm37-ccn-tile-init-gnu-v1/build-result-v1.json',
        'build/udm37-ccn-tile-init-gnu-v1/posthoc-v3/posthoc-attestation-v3.json',
        'build/udm37-ccn-tile-init-root-freeze-v1.json',
        'build/udm37-ccn-tile-init-independent-review-v2.json',
        'build/pristine-current-omp-control-v2/root-functional-review-v1.json',
        'build/pristine-current-omp-control-v2/root-stage-review.json',
        'build/pristine-current-omp-control-v2/comparison.json',
        'build/udm-cu-current-omp-early-ra4-v1/root-first-step-qnccn-v1.json',
        'build/udm37-ccn-current-runtime-v1/cases/stage-v1/stage-failure.json',
        'build/udm37-ccn-current-runtime-v1/cases/stage-v3/worker-proof.json',
        'build/udm37-ccn-current-runtime-v1/cases/stage-v3/worker-proof-command-v1.json',
        'build/udm-cu-current-omp-runtime-v2/cases/worker-proof.json',
    ]:
        copy('retained/' + p.removeprefix('build/'), p)
    for folder, names in [
        ('udm37-ccn-current-runtime-v1', ('runtime.py', 'runtime_integrity.py', 'plan-v1.json')),
        ('udm37-ccn-winter24h-v1', ('run24h.py',)),
        ('udm37-ccn-restart-runtime-v1', ('restart_continuous_v1.py', 'plan-v1.json', 'root-freeze-v1.json')),
        ('udm37-ccn-tile-init-gnu-v1', ('prepare_ccn_source_v1.py', 'build_ccn_em_real_v1.py', 'verify_generated_ccn_v1.py', 'source-freeze-v1.json', 'harness-manifest-v1.json')),
        ('udm37-ccn-tile-init-gnu-v1/posthoc-v3', ('verify_ccn_build_v3.py', 'test_verify_ccn_build_v3.py')),
        ('udm-cu-current-omp-runtime-v2', ('runtime.py', 'test_runtime.py')),
        ('udm-cu-current-omp-ra4-control-v1', ('control.py',)),
        ('udm-cu-current-omp-early-ra4-v1', ('early.py', 'test_early.py')),
        ('udm-cu-current-omp-harness-v1', ('analyze_workers.py', 'test_analyze_workers.py')),
        ('udm-cmake-openmp-full/runtime-preflight-v3', ('gomp_probe.c',)),
        ('udm-seaice-winter-validation-v1', ('winter_validation_v1.py',)),
        ('udm-seaice-winter-validation-v3', ('posthoc_runtime_helper_v1.py', 'run_case_v1.py')),
        ('udm-seaice-fresh-gnu-dm-sm-v1', ('posthoc-build-verifier-v1.py',)),
        ('udm-cu-winter24h-v1', ('prepare_winter24h_ra4_v3.py',)),
    ]:
        for n in names:
            copy('executed-sources/' + folder + '/' + n, 'build/' + folder + '/' + n)
    copy('executed-sources/prepare-pristine-current-omp-control.py', 'build/prepare-pristine-current-omp-control.py')
    for n in ('test_udm_ccn_startup.py', 'ccn_startup_fixture.f90.in', 'UDM_CCN_STARTUP.md'):
        copy('source-test/' + n, 'build/udm37-ccn-tile-init-pr-work/WRF/test/rrtmgp/' + n)
    for p in ('build/pristine-current-omp-control-v1/stage.json', 'build/udm37-ccn-current-runtime-v1/cases/stage-v2/stage.json'):
        d = read(p)
        write('receipts/' + Path(p).parent.parent.name + '-' + Path(p).parent.name + '-unrun.json', {'original': pin(p), 'original_status': d['status'], 'original_model_invocations': d['model_invocations'], 'classification': 'UNRUN_INELIGIBLE_STALE_BINDING', 'runner_binding': d.get('runner'), 'full_original_payload_external': True})
    for family, path in [('old-ra37', 'build/udm-cu-current-omp-runtime-v2/cases/stage.json'), ('old-ra4', 'build/udm-cu-current-omp-ra4-control-v1/cases/stage.json'), ('new-3h', 'build/udm37-ccn-current-runtime-v1/cases/stage-v3/stage.json')]:
        s = read(path)
        write('assets/' + family + '-named-bindings.json', {'original_stage': pin(path), 'arms': s['arms'], 'scope': 'Original active bindings and namelist pins; original case paths remain external.'})
    build = read('build/udm37-ccn-tile-init-gnu-v1/build-result-v1.json')
    att = read('build/udm37-ccn-tile-init-gnu-v1/posthoc-v3/posthoc-attestation-v3.json')
    led = {'schema': 'udm37-ccn-portable-runtime-ledger-v1', 'status': 'PROVISIONAL_RESTART_FAIL_UNDER_REVIEW', 'derived_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(), 'source_pr49_head': '4673f9d6e82fb2822fe225f33b585042f00d451e', 'base_pr47_head': '4394845667db52c258dab62719abc87402dd731f', 'candidate_executable': att['full_build_executables']['wrf.exe'], 'source_manifest': att['source_manifest'], 'source_count': 6735, 'dependency_inventory': att['dependency_inventory'], 'original_build_status': build['status'], 'original_build_error': build['error'], 'posthoc_status': att['status'], 'source_freeze': pin('build/udm37-ccn-tile-init-root-freeze-v1.json'), 'models': models, 'primary_model_count': 17, 'comparison_pairs': pairs, 'pair_count': 23, 'raw_table_rows': 9986, 'restart': {'status': 'STRICT_FAIL_PRESERVED_UNDER_REVIEW', 'actual_restart_comparison_accepted': False, 'strict_original': pin(restart_path), 'derived_checks': 'receipts/restart-strict-failure-derived.json'}, 'candidate_worker': {'proof': 'retained/udm37-ccn-current-runtime-v1/cases/stage-v3/worker-proof.json', 'command': 'retained/udm37-ccn-current-runtime-v1/cases/stage-v3/worker-proof-command-v1.json'}, 'scope_limits': ['Current-source strict restart failure remains under review', 'LegacyRA4 CCN startup defect preserved', 'CombinedCCN/predicate change not separately isolated', 'Static callback does not prove activeCU or both LW/SW branches every call', 'No general nest/decomposition/forecastaccuracy claim'], 'evidence_writer_model_build_calls': 0}
    write('runtime-ledger.json', led)
    copy('verify.py', HERE / 'verify.py')
    for n in ('README.md', 'scope-report-ko-en.md', 'PR-description-draft.md'):
        copy(n, HERE / n)
    write('provenance-index.json', {'schema': 'runtime-package-provenance-v1', 'copied_originals': origins, 'external_hash_pins': sorted(externals.values(), key=lambda q: q['path']), 'portable_scope': 'Retained SHA/ledger verification only; missing external arrays are not recomputed. Absolute-context logical runners are provenance, not relocated launchers. No NetCDF/ELF/object/shared-library files are included.'})
    manifest = {'schema': 'retained-sha256-manifest-v1', 'files': [{'path': str(p.relative_to(OUT)), 'sha256': pin(p)['sha256'], 'size_bytes': p.stat().st_size} for p in sorted(OUT.rglob('*')) if p.is_file()]}
    write('artifact-manifest.json', manifest)
    print(json.dumps({'directory': str(OUT), 'files': len(manifest['files']) + 1, 'bytes': sum(p.stat().st_size for p in OUT.rglob('*') if p.is_file()), 'manifest': pin(OUT / 'artifact-manifest.json'), 'restart': 'STRICT_FAIL_PRESERVED_UNDER_REVIEW'}))


if __name__ == '__main__':
    main()
