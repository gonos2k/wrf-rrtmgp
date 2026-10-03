#!/usr/bin/env python3
"""Verify retained text/ledger relationships; never load external NC or models."""
import csv
import hashlib
import json
import math
from pathlib import Path
import struct


def need(c, message):
    if not c:
        raise ValueError(message)


def canonical(d):
    return hashlib.sha256(json.dumps(d, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def relative(root, name):
    p = Path(name)
    need(not p.is_absolute() and '..' not in p.parts, 'unsafe path')
    q = root / p
    need(q.is_file() and not q.is_symlink() and q.resolve().is_relative_to(root.resolve()), 'missing/escaping payload')
    return q


def load(root, name):
    return json.loads(relative(root, name).read_text())


def worker(q, expected_exe):
    need(q['status'] == 'PASS_ALL_RANKS_RADIATION_WORKERS' and q['verified_all_rank_radiation_workers'], 'worker proof')
    need(q['executable_sha256'] == expected_exe and q['expected_mpi_ranks'] == len(q['observed_pids']) == 4, 'worker exe/PIDs')
    need(q['pie'] and q['contains_lw_and_sw_calls'] and q['symbol'] == '__module_radiation_driver_MOD_radiation_driver._omp_fn.1', 'callback identity')
    for pid, p in q['observed_pids'].items():
        need(pid.isdigit() and p['workers'] == [0, 1] and p['teams'] == [2] and p['balanced'] and p['paired_callbacks'] == 36, 'per-PID pairs/workers')
        need(set(p['worker_cpu_ns']) == {'0', '1'} and all(n > 1000000 for n in p['worker_cpu_ns'].values()), 'per-PID CPU')
    need(q['radiation_records'] == 288 == 2 * sum(p['paired_callbacks'] for p in q['observed_pids'].values()), 'record accounting')


def pair(root, q):
    with relative(root, q['table']).open(newline='') as f:
        r = csv.DictReader(f)
        need(r.fieldnames == ['variable', 'dtype', 'shape_json', 'left_sha256', 'right_sha256', 'equal'], 'table schema')
        rows = list(r)
    need(len(rows) == q['field_count'] == len({x['variable'] for x in rows}), 'table completeness')
    recovered = []
    for row in rows:
        need(row['equal'] in ('true', 'false'), 'equality spelling')
        eq = row['equal'] == 'true'
        need(eq == (row['left_sha256'] == row['right_sha256']), 'raw equality/hash')
        need(all(len(row[k]) == 64 and all(c in '0123456789abcdef' for c in row[k]) for k in ('left_sha256', 'right_sha256')), 'SHA syntax')
        shape = json.loads(row['shape_json'])
        need(isinstance(shape, list) and all(isinstance(x, int) and x >= 0 for x in shape), 'shape')
        recovered.append({'name': row['variable'], 'dtype': row['dtype'], 'shape': shape, 'left_sha': row['left_sha256'], 'right_sha': row['right_sha256'], 'equal': eq})
    need(canonical(recovered) == q['original_ledger_canonical_sha256'], 'complete ledger identity')
    unequal = sum(not x['equal'] for x in recovered)
    need(unequal == q['unequal_fields'] and q['passed'] == (q['metadata_equal'] and unequal == 0), 'outcome/count')
    need(q['whole_file_equal'] == (q['left']['sha256'] == q['right']['sha256']), 'wholefile status')
    return {x['name']: x for x in recovered}


def verify(root):
    manifest = load(root, 'artifact-manifest.json')
    need(manifest['schema'] == 'retained-sha256-manifest-v1', 'manifest schema')
    entries = manifest['files']
    need(len(entries) == len({x['path'] for x in entries}), 'duplicate artifact')
    need({str(p.relative_to(root)) for p in root.rglob('*') if p.is_file()} == {x['path'] for x in entries} | {'artifact-manifest.json'}, 'extra/missing artifact')
    for q in entries:
        p = relative(root, q['path'])
        need(p.stat().st_size == q['size_bytes'] and hashlib.sha256(p.read_bytes()).hexdigest() == q['sha256'], 'retained SHA mismatch:' + q['path'])
        need(p.suffix.lower() not in ('.nc', '.exe', '.o', '.so'), 'binary/model payload')
    d = load(root, 'runtime-ledger.json')
    need(d['schema'] == 'udm37-ccn-portable-runtime-ledger-v1' and d['source_pr49_head'] == '199d0d9be07f9289ac60959e5cdd89c39e71a7dd' and d['runtime_tested_source_head'] == '4673f9d6e82fb2822fe225f33b585042f00d451e' and d['base_pr47_head'] == '4394845667db52c258dab62719abc87402dd731f', 'source scope')
    need(d['status'] == 'PASS_SCOPED_RUNTIME_AND_ATTRIBUTED_RESTART_STATE' and d['restart']['status'] == 'PASS_SCOPED_RESTART_STATE_WITH_INITIAL_DIAGNOSTIC_RESET' and not d['restart']['original_strict_comparison_passed'] and d['restart']['scoped_state_accepted'], 'restart scope/failure erased')
    need(d['original_build_status'] == 'BUILD_FAIL_PRESERVED' and d['posthoc_status'] == 'POSTHOC_BUILD_ATTESTED_ORIGINAL_RUNNER_FAILURE_PRESERVED', 'build failure erased')
    need(d['source_count'] == 6735 and d['dependency_inventory']['count'] == 1582 and d['evidence_writer_model_build_calls'] == 0, 'source/curation scope')
    models = d['models']
    need(len(models) == d['primary_model_count'] == 17 and len({(m['family'], m['arm']) for m in models}) == 17, 'model count/duplicate')
    expected = {'old-ra37': 3, 'old-ra4': 2, 'early-ra4': 2, 'official-ra4': 2, 'new-3h': 4, 'new-24h': 1, 'restart-attempt': 3}
    need({f: sum(m['family'] == f for m in models) for f in expected} == expected, 'experiment family count')
    counts = load(root, 'model-count-ledger.json')
    primary = {m['receipt']['path'] for m in models}
    candidate = {m['receipt']['path'] for m in models if m['family'] in ('new-3h', 'new-24h', 'restart-attempt')}
    need(len(primary) == 17 and len(candidate) == 8 and counts['primary_receipt_paths'] == sorted(primary) and counts['candidate_receipt_paths'] == sorted(candidate), 'unique primary/candidate identity')
    earlier = counts['earlier_source47_models']
    older = {q['receipt']['path'] for q in earlier}
    need(len(earlier) == len(older) == 4 and not older.intersection(primary) and counts['unique_model_total'] == 21 and counts['prechange_and_reference_count'] == 13 and counts['candidate_subset_of_primary'] and counts['candidate_count'] == 8, 'overlap/count scope')
    for q in earlier:
        m = q['model']
        need(q['actual_model_invocations'] == 1 and q['before_after_pins_passed'] and q['strict_outputs_passed'] and m['returncode'] == 0 and m['model_completed'] and not m['timed_out'] and len(m['rank_logs']) == 4 and all(z['success'] and not z['fatal'] for z in m['rank_logs']), 'earlier source47 completion')
    for m in models:
        need(m['actual_model_invocations'] == 1 and m['strict_outputs_passed'] and m['before_after_pins_passed'], 'model contract')
        run = m['model']
        need(run['returncode'] == 0 and run['model_completed'] and not run['timed_out'] and len(run['rank_logs']) == 4 and all(x['success'] and not x['fatal'] for x in run['rank_logs']), 'four rank completion')
        fields = m['fields']
        h = fields['history']
        radiation = 4 if m['family'] in ('old-ra4', 'early-ra4', 'official-ra4') or m['arm'] == 'ra4-omp1' else 37
        expected_count = 222 if radiation == 4 else 225
        for q in [h] + ([fields['checkpoint']] if 'checkpoint' in fields else fields['checkpoints']):
            count = expected_count if q is h else 664
            need(q['variable_count'] == count and q['numeric_variable_count'] == count - 1 and q['passed'] and q['raw_decoded_finite_unmasked'] and q['default_fill_hits'] == 0, 'numeric/count scope')
            need(q['ordered_times'] == q['expected_times'] and q['physics'] == {'MP_PHYSICS': 27, 'RA_LW_PHYSICS': radiation, 'RA_SW_PHYSICS': radiation} and q['geometry'] == {'bottom_top': 32, 'south_north': 60, 'west_east': 73}, 'state identity')
    need(len(d['comparison_pairs']) == d['pair_count'] == 23 and sum(x['field_count'] for x in d['comparison_pairs']) == d['raw_table_rows'] == 9986, 'all-pair accounting')
    normalized = {(q['family'], q['key']): pair(root, q) for q in d['comparison_pairs']}
    need(len(normalized) == 23, 'duplicate comparison')
    old37 = [q for q in d['comparison_pairs'] if q['family'] == 'old-ra37']
    need([q['unequal_fields'] for q in old37] == [0, 0, 92, 194], 'old37 failures erased')
    for family, unequal in [('old-ra4', [93, 195]), ('official-ra4', [93, 196])]:
        need([q['unequal_fields'] for q in d['comparison_pairs'] if q['family'] == family] == unequal, 'baseline discriminator mismatch')
    need(all(q['passed'] and q['whole_file_equal'] for q in d['comparison_pairs'] if q['family'] in ('new-3h', 'new-24h', 'restart-own-omp')), 'scoped candidate equality')
    for field in ('history', 'checkpoint'):
        official = normalized[('official-ra4', field)]
        a = normalized[('official-patched-ra4', 'omp1-' + field)]
        b = normalized[('official-patched-ra4', 'omp2-' + field)]
        need(set(official) == set(a) == set(b) and all(official[n]['left_sha'] == a[n]['left_sha'] and official[n]['right_sha'] == b[n]['left_sha'] for n in official), 'derived official hashes/source')
        for q in (a, b):
            need({n for n, z in q.items() if not z['equal']} == (set() if field == 'history' else {'QZ0', 'USTM'}), 'cross-source exceptions erased')
    w = load(root, d['candidate_worker']['proof'])
    worker(w, d['candidate_executable']['sha256'])
    command = load(root, d['candidate_worker']['command'])
    need(command['analyzer']['sha256'] == '36a36b8213da887dd69e36e81502c3f3180ecacfc9e18efe7122c33b43c2faaa' and command['result']['sha256'] == hashlib.sha256(relative(root, d['candidate_worker']['proof']).read_bytes()).hexdigest() and command['no_model_invocation'], 'worker command/source/result')
    need(command['argv'][3] == w['executable'] and command['argv'][5] == w['log'], 'observer argv identity')
    fail = load(root, d['restart']['derived_checks'])
    need(fail['original_status'] == 'FAIL_PRESERVED' and fail['attributed_final_outcome'] == d['restart']['status'] and fail['original'] == d['restart']['strict_original'] and fail['original']['sha256'] == '7e9682c25b1303bd71f22c1c0ac117bb4baa0b3fd62b14abe39cdcc2ba681dca', 'original restart failure erased')
    for q in fail['first_five_exact_check_results'][1:]:
        expected_fields = {'UDM_CLDFRA', 'UDM_CF_STEP', 'UDM_CF_TOP'} if q['kind'].startswith('restart-history') else set()
        need({n for n, r in q['variables'].items() if not r['raw_bytes_equal']} == expected_fields and not q['passed'], 'strict restart mismatch accounting')
        need(set(q['unexplained_global_differences']) == (set() if expected_fields else {'WRF_ALARM_SECS_TIL_NEXT_RING_55'}), 'unclassified metadata mismatch')
        need(len(q['variables']) == (225 if expected_fields else 664) and all(v['attributes_equal'] and isinstance(v['dtype'], str) and isinstance(v['shape'], list) for v in q['variables'].values()), 'strict restart variable metadata')
        need(all(v['dimensions_equal'] for v in q['variables'].values()) if expected_fields else q['dimensions_equal'] and q['data_model_equal'], 'strict restart dimensions/data model')
    post = load(root, d['restart']['attribution_report'])
    need(post['status'] == d['restart']['status'] and post['strict_comparison']['status'] == 'FAIL_PRESERVED' and post['strict_comparison']['sha256'] == fail['original']['sha256'], 'attribution status/pin')
    need(hashlib.sha256(relative(root, d['restart']['attribution_report']).read_bytes()).hexdigest() == '6e18a5fb8ac190508acdd756c2fba8a1d5c30b472b7b9d95942f904f92622534' == fail['posthoc_report']['sha256'], 'reviewed attribution identity')
    need(post['history_counts'] == {'final_16_exact': 225, 'initial_15_exact': 222, 'initial_15_reset_to_minus_one': 3, 'variables_per_history': 225} and post['checkpoint_counts'] == {'all_raw_variables_exact': 664}, 'attribution counts')
    resets = {'UDM_CLDFRA': ('<f4', [32, 60, 73]), 'UDM_CF_STEP': ('<i4', [60, 73]), 'UDM_CF_TOP': ('<i4', [60, 73])}
    need(set(post['history_expected_differences']) == set(resets) and set(post['arms']) == {'restart-omp1', 'restart-omp2'}, 'attributed fields/arms')
    for arm, a in post['arms'].items():
        h = a['history']; initial = h['initial_15']; final = h['final_16']
        need(len(initial) == len(final) == 225 and set(initial) == set(final) and all(v == 'exact' for v in final.values()), 'final restart state')
        need({n for n, v in initial.items() if v != 'exact'} == set(resets), 'initial reset scope')
        for name, (dtype, shape) in resets.items():
            q = initial[name]
            need(q['candidate_dtype'] == dtype and q['candidate_shape'] == shape and q['expected_reset'] == -1, 'diagnostic reset contract')
            raw = struct.pack('<f' if dtype == '<f4' else '<i', -1) * math.prod(shape)
            need(hashlib.sha256(raw).hexdigest() == q['candidate_raw_sha256'] and q['candidate_raw_sha256'] != q['continuous_raw_sha256'], 'reset raw hash')
        cp = a['checkpoint']
        need(cp['exact_variables'] == 664 and set(cp['global_attribute_differences']) == {'START_DATE', 'WRF_ALARM_SECS_TIL_NEXT_RING_55'}, 'checkpoint metadata scope')
        for side, seconds in [('candidate', -3600), ('continuous', -14400)]:
            need(cp[side + '_alarm_seconds'] == seconds and cp[side + '_alarm_raw'] == {'dtype': '<i4', 'hex': struct.pack('<i', seconds).hex()}, 'disabled alarm value')
        strict_h, strict_cp = [q for q in fail['first_five_exact_check_results'][1:] if q['arm'] == arm]
        need(strict_h['candidate'] == a['history_candidate'] and strict_h['continuous'] == a['history_continuous'] and strict_cp['candidate'] == a['checkpoint_candidate'] and strict_cp['continuous'] == a['checkpoint_continuous'], 'posthoc/original output identity')
    excerpts = load(root, 'receipts/restart-source-basis-excerpts.json')
    source_hashes = {'physics_init': '5d2f86eeeb07431d6e9784eef0106989d275cd8f5c37d0433c0d462087db356c', 'registry': '86ce17cb42f7f222164ea2a3f130b57b7d01f8d90045012bb01e1e0e0b5662c1', 'alarm_definition': '524d7e7460d4151f50c0b33a0b3d4d21038085831b526fe8a915dd48db6d3be5', 'alarm_disable': 'bc1c0b26c1354a578820abeb7ea34d7a8562e4fa0d975448f7237392d6e2eba2'}
    need(set(excerpts) == set(source_hashes), 'source basis completeness')
    for key, sha in source_hashes.items():
        e = excerpts[key]; s = post['source_basis']['files'][key]
        need(e['original']['path'] == s['path'] and e['original']['sha256'] == s['sha256'] == sha and e['citation'] == post['source_basis']['citations'][key] and e['exact_excerpt'], 'source basis identity')
    return {'status': 'PASS_RETAINED_EVIDENCE_INTEGRITY', 'payloads': len(entries), 'primary_model_processes': 17, 'candidate_model_processes_included_in_primary': 8, 'earlier_source47_processes': 4, 'unique_model_processes': 21, 'comparison_tables': 23, 'raw_rows': 9986, 'restart_status': d['restart']['status'], 'original_strict_restart_status': 'FAIL_PRESERVED', 'external_arrays_recomputed': False}


if __name__ == '__main__':
    import argparse
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--package', type=Path, default=Path(__file__).resolve().parent)
    a = p.parse_args()
    print(json.dumps(verify(a.package.resolve()), sort_keys=True))
