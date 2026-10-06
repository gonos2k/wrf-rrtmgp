#!/usr/bin/env python3
"""Check saved metadata integrity only; never load raw traces or execute audit."""
from pathlib import Path
import hashlib
import json
import sys
sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
KNOWN = {
    'evidence/audit.py': 'a739a7b555488f4d013881481498a52d890018c9130b46dd6ae031d4349030ea',
    'evidence/plan.json': '073f9e9e4602d95bf81c6650d0346d86271a73ba26a10ac195243ba1aced55f6',
    'run/execution.json': '185560430e3ba82fbce0f6c9809119d471e57975afecccc26adeabea18f27bd1',
    'run/result.json': '855c495bf6024ead7cc22f716989bd84dcdba0fcc25d0818c9aa98cd81345472',
    'reviews/independent-source-review.json': '9db2804051ec8816e357e0fcf68db548725db2b8ccb9d192e43ed2df62e6facc',
    'reviews/independent-terminal-review.json': 'e0112732ac2a36916205e69c9bfdd732f63539d6a0ea281e86e3b7dbc54e4478',
    'reviews/broadener-marker-clarification.json': '0f6fcb5cf087e3370664d7083d857a87e3fbe94ad6ce607229cf765b465ca6dc',
}
FIELDS = {'YI', 'GI', 'PAVP0', 'PAVP2', 'SP_from_observed_corrected_SUI', 'SPPSP_from_observed_corrected_SUI', 'shifted_VNU', 'term_meta_VNU'}
def require(condition, label):
    if not condition:
        raise ValueError(label)
def sha(b):
    return hashlib.sha256(b).hexdigest()
def obj(rel):
    return json.loads((P / rel).read_text())
def verify():
    manifest = obj('manifest.json')
    require(manifest['schema'] == 'UDM37_CO2_TRANSFER_CLOSED_MANIFEST_V1', 'manifest schema')
    rows = manifest['files']
    names = [x['relative_path'] for x in rows]
    require(len(names) == len(set(names)) == manifest['payload_count'] == 17, 'closed payload count')
    require(all(not Path(s).is_absolute() and '..' not in Path(s).parts and s != 'manifest.json' for s in names), 'unsafe relative paths')
    require({str(f.relative_to(P)) for f in P.rglob('*') if f.is_file()} == set(names) | {'manifest.json'}, 'closed roster, including nested manifests')
    require(not any(f.is_symlink() for f in P.rglob('*')), 'symlink forbidden')
    for row in rows:
        b = (P / row['relative_path']).read_bytes()
        require(len(b) == row['bytes'] and sha(b) == row['sha256'], 'payload hash: ' + row['relative_path'])
    require(sum(x['bytes'] for x in rows) == manifest['payload_bytes'], 'payload byte accounting')
    for rel, expected in KNOWN.items():
        require(sha((P / rel).read_bytes()) == expected, 'immutable executed/review pin: ' + rel)
    origins = obj('origins.json')
    require(origins['copied_count'] == len(origins['files']) == 13, 'verbatim origin count')
    require(len({x['relative_path'] for x in origins['files']}) == 13, 'duplicate origins')
    for row in origins['files']:
        require(row['relative_path'] in names and row['encoding'] == 'verbatim', 'origin mapping')
        b = (P / row['relative_path']).read_bytes()
        require(len(b) == row['bytes'] and sha(b) == row['sha256'], 'origin bytes')
    refs = origins['inherited_references']
    require([x['relative_to_package'] for x in refs] == ['../stock-lblrtm-co2-companion-census/manifest.json', '../stock-lblrtm-co2-companion-census/run/result.json'], 'exact inherited reference paths')
    for row in refs:
        b = (P / row['relative_to_package']).read_bytes()
        require(len(b) == row['bytes'] and sha(b) == row['sha256'], 'unchanged inherited census')
    census = obj('../stock-lblrtm-co2-companion-census/run/result.json')
    require(sha((P / refs[1]['relative_to_package']).read_bytes()) == 'eb8243244ff65d396c1c797195e7dcc36111dd7cce9a084c8873ec0aad109e22', 'actual census result pin')
    plan, execution, result = obj('evidence/plan.json'), obj('run/execution.json'), obj('run/result.json')
    require(plan['script']['sha256'] == execution['script_sha256'] == KNOWN['evidence/audit.py'] and execution['plan_sha256'] == KNOWN['evidence/plan.json'], 'executed script/plan')
    require(execution['status'] == 'TERMINAL' and execution['actual_child_returncode'] == 0 and execution['pid'] == 2254879 and execution['reaped'] is True and execution['timed_out'] is False and execution['exception'] is None and execution['new_model_build_solver_calls'] == 0, 'actual reader terminal')
    require(result['status'] == 'PASS_SCOPED_801_CO2_INTERPOLATION_PRESSURE_AND_CENTER_TRANSFER', 'scoped result status')
    require(result['observed_CO2_identities'] == plan['target']['observed_CO2_identities'] == 801 and result['target_record_count'] == plan['target']['expected_CO2_target_terms'] == 5930, 'observed identity/write counts')
    require(result['all_target_records'] == plan['target']['all_target_terms'] == 6072, 'all target count')
    require(set(result['checks']) == FIELDS and result['differences_first20'] == [], 'field roster/differences')
    for field in FIELDS:
        require(result['checks'][field] == {'bit_differences': 0, 'checks': 5930, 'max_ULP': 0, 'max_abs': 0.0}, 'saved check summary: ' + field)
    require(sum(x['checks'] for x in result['checks'].values()) == result['total_compared_values'] == 47440, 'repeated field accounting')
    require(result['stage_counts'] == {'1': 2965, '2': 2965} and sum(result['bin_record_counts'].values()) == 5930, 'stage/bin counts')
    identities = result['identity_checks']
    require(len(identities) == 801, 'identity rows')
    keys = set()
    for row in identities:
        key = (row['block'], row['slot'], row['encoded_MOL'], row['flag'])
        require(key not in keys and row['pass'] == 21 and row['flag'] == 1 and row['encoded_MOL'] % 100 == 2 and row['isotope'] == row['encoded_MOL'] // 100, 'unique observed CO2 identity')
        keys.add(key)
        require(set(row['checks_bit_exact']) == FIELDS and all(v is True for v in row['checks_bit_exact'].values()), 'eight identity-field exact flags')
    require(keys == {(x['block'], x['slot'], x['mol'], x['iflg']) for x in census['record_matches']}, 'exact census membership')
    require(len(keys) * len(FIELDS) == 6408, 'unique identity-field count')
    ranges = result['TAPE3_selected_ranges']
    require(ranges['read_bytes'] == 509192 and ranges['fresh_whole_file_hash'] is False and ranges['stat_before_after_equal'] is True, 'bounded ranges/historical full hash')
    require(ranges['historical_whole_file_SHA256'] == census['range_read']['previously_authenticated_whole_file_sha256'], 'historical full pin')
    require(ranges['range_hashes'] == {x['range']: x['sha256'] for x in census['range_read']['selected_range_hashes']}, 'actual census selected-range SHA join')
    require(ranges['additional_pressure_shift_branch_first_predicate_false_count'] == 801 and ranges['broadener_flag_patterns'] == {'(-654321, 0, 0, 0, 0, 0, 0)': 6, '(0, 0, 0, 0, 0, 0, 0)': 795}, 'first branch predicate/source marker patterns')
    require(result['input_pins']['census']['sha256'] == 'eb8243244ff65d396c1c797195e7dcc36111dd7cce9a084c8873ec0aad109e22', 'input census pin')
    require(result['observed_strength_sign_counts'] == {x: {'positive': 801} for x in ('SP', 'SUI', 'strength_factor')}, 'observed strength sign counts')
    require(result['new_solver_build_model_calls'] == 0, 'scientific call scope')
    peer = obj('reviews/independent-terminal-review.json')
    require(peer['execution']['sha256'] == KNOWN['run/execution.json'] and peer['result']['sha256'] == KNOWN['run/result.json'] and peer['result']['checks'] == result['checks'] and peer['execution']['actual_child_returncode'] == 0, 'independent terminal pin/result join')
    source = obj('reviews/independent-source-review.json')
    require(source['reader']['sha256'] == KNOWN['evidence/audit.py'] and source['plan']['sha256'] == KNOWN['evidence/plan.json'], 'independent source review join')
    root = obj('reviews/root-terminal-review.json')
    for name, rel in [('audit.py', 'evidence/audit.py'), ('plan.json', 'evidence/plan.json'), ('run-v1/execution.json', 'run/execution.json'), ('run-v1/result.json', 'run/result.json')]:
        require(root['pins'][name]['sha256'] == KNOWN[rel], 'root terminal pin')
    require(root['all_write_field_comparisons'] == 47440 and root['unique_identity_field_combinations'] == 6408 and root['corrected_SUI_independent_proof_for_all801'] is False, 'root count/limitation')
    require(obj('reviews/broadener-marker-clarification.json')['status'] == 'SOURCE_CONFIRMED_STORAGE_LENGTH_MARKER', 'additive marker clarification')
    scope = obj('scope.json')
    require(scope['actual_calls'] == {'saved_record_reader': 1, 'model': 0, 'solver': 0, 'build': 0} and scope['corrected_SUI_is_observed_input'] is True and scope['all801_thermal_strength_proven'] is False and scope['negative_OD_FAIL_retained'] is True and scope['physical_normality_accepted'] is False, 'scope and open gates')
    print('PASS_SCOPED_SAVED_TRANSFER_INTEGRITY: 17 payloads, 13 verbatim origins, 801 identities / 5930 writes / 47440 repeated checks; no raw reader or physics execution')
if __name__ == '__main__':
    try:
        verify()
    except Exception as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
