#!/usr/bin/env python3
"""Authenticate a saved structural census; never open external raw inputs or run audit."""
import hashlib
import json
import math
from pathlib import Path
import sys
sys.dont_write_bytecode = True
P = Path(__file__).resolve().parent
KNOWN = {
    'evidence/audit.py': '2f7fee7188e013bdacfc30ff2c135392c98263e5277b7f6e6dd93c9c2bf3bcda',
    'evidence/plan.json': 'a509998be2235f8e764d8b3f5d2af0f5735665ff75437de0e99c2b16a6638abe',
    'run/execution.json': '8629c98619173633f1e67c262ec873a97c19f03399f2f96528e7d13f07defd5a',
    'run/result.json': 'eb8243244ff65d396c1c797195e7dcc36111dd7cce9a084c8873ec0aad109e22',
    'reviews/independent-terminal.json': '2167727f7ea663883b90b3862cafe11e6f8ff54d0e17589517481020d96e8ef0',
    'reviews/root-terminal.json': '079d1d33876246d6348fbecc5f54a3a73591d6d1ab7cca396ea874b8a06b7811',
}
def require(condition, message):
    if not condition:
        raise ValueError(message)
def sha(b):
    return hashlib.sha256(b).hexdigest()
def obj(rel):
    return json.loads((P / rel).read_text())
def verify():
    manifest = obj('manifest.json')
    require(manifest['schema'] == 'UDM37_CO2_CENSUS_CLOSED_MANIFEST_V1', 'manifest schema')
    rows = manifest['files']
    names = [row['relative_path'] for row in rows]
    require(len(names) == len(set(names)) == manifest['payload_count'] == 15, 'payload roster count/duplicates')
    require(all(not Path(s).is_absolute() and '..' not in Path(s).parts and s != 'manifest.json' for s in names), 'unsafe path')
    actual = {str(f.relative_to(P)) for f in P.rglob('*') if f.is_file()}
    require(actual == set(names) | {'manifest.json'}, 'closed roster including nested manifest')
    require(not any(f.is_symlink() for f in P.rglob('*')), 'symlink forbidden')
    for row in rows:
        b = (P / row['relative_path']).read_bytes()
        require(len(b) == row['bytes'] and sha(b) == row['sha256'], 'payload hash: ' + row['relative_path'])
    require(sum(row['bytes'] for row in rows) == manifest['payload_bytes'], 'payload bytes')
    for rel, expected in KNOWN.items():
        require(sha((P / rel).read_bytes()) == expected, 'immutable executed/review pin: ' + rel)
    origins = obj('origins.json')
    copied = origins['files']
    require(origins['copied_count'] == len(copied) == 11, 'origin count')
    require(len({x['relative_path'] for x in copied}) == len(copied), 'duplicate origin')
    for row in copied:
        require(row['encoding'] == 'verbatim' and row['relative_path'] in names, 'origin encoding/path')
        b = (P / row['relative_path']).read_bytes()
        require(len(b) == row['bytes'] and sha(b) == row['sha256'], 'origin byte binding')
    plan, execution, result = obj('evidence/plan.json'), obj('run/execution.json'), obj('run/result.json')
    require(execution['status'] == 'TERMINAL' and execution['actual_child_returncode'] == 0 and execution['pid'] == 2169675 and execution['reaped'] is True and execution['timed_out'] is False and execution['exception'] is None, 'actual terminal RC')
    require(execution['script_sha256'] == KNOWN['evidence/audit.py'] and execution['plan_sha256'] == KNOWN['evidence/plan.json'], 'executed source/plan binding')
    require(result['status'] == 'PASS_SCOPED_801_OBSERVED_CO2_TARGET_MAIN_COMPANION_ASSOCIATIONS', 'saved scoped status')
    require(result['source_report_sha256'] == plan['scope']['candidate_report_sha256'] == plan['inputs']['derived_target_report']['sha256'], 'derived roster source binding')
    require(result['observed_target_identity_count'] == result['matched_main_count'] == plan['expected_summary']['target_identities'] == 801, 'observed count')
    for count, details in [('missing_identity_count', 'missing_identities'), ('duplicate_identity_count', 'duplicate_identities'), ('identity_mismatch_count', 'identity_mismatches'), ('open_group_count', 'open_groups')]:
        require(result[count] == 0 and result[details] == [], 'retained no-' + count)
    require(result['companion_cardinality_counts'] == {'1': 801}, 'cardinality summary')
    rr = result['range_read']
    require(rr['blocks_read'] == [484, 496] and rr['bytes_read'] == 509192 and rr['whole_file_sha_recomputed'] is False, 'bounded range/whole-file provenance')
    require(rr['stat_before'] == rr['stat_after'] and rr['stat_before']['size_bytes'] == plan['inputs']['tape3']['size_bytes'], 'stat identity')
    require(rr['previously_authenticated_whole_file_sha256'] == plan['inputs']['tape3']['historical_whole_file_sha256'], 'historical whole-file pin')
    panels = rr['panel_metadata']
    require([x['block'] for x in panels] == list(range(484, 497)), '13 panels')
    require(all(1 <= x['nlines'] <= 250 and math.isfinite(x['vlo']) and math.isfinite(x['vhi']) and x['vlo'] <= x['vhi'] for x in panels), 'panel metadata')
    hashes = rr['selected_range_hashes']
    require([x['range'] for x in hashes] == ['header'] + ['block-' + str(i) for i in range(484, 497)], 'range hashes')
    require([x['bytes'] for x in hashes] == [1672] + [39040] * 13 and sum(x['bytes'] for x in hashes) == rr['bytes_read'], 'range byte accounting')
    require(all(len(x['sha256']) == 64 and all(c in '0123456789abcdef' for c in x['sha256']) for x in hashes), 'range SHA syntax')
    nlines = {x['block']: x['nlines'] for x in panels}
    records = result['record_matches']
    require(len(records) == 801, 'record row count')
    identities, counts = set(), {}
    for row in records:
        key = (row['block'], row['slot'], row['mol'], row['iflg'])
        require(key not in identities, 'duplicate identity row')
        identities.add(key)
        require(row['block'] in nlines and 1 <= row['slot'] <= nlines[row['block']] and row['iflg'] == 1 and row['mol'] % 100 == 2 and row['isotope'] == row['mol'] // 100, 'main identity')
        require(row['companion_count'] == len(row['companion_slots']) == 1, 'saved complete companion group')
        companion = row['companion_slots'][0]
        expected = (row['block'], row['slot'] + 1) if row['slot'] < nlines[row['block']] else (row['block'] + 1, 1)
        require((companion['block'], companion['slot']) == expected and companion['iflg'] == -1, 'saved companion adjacency')
        counts[str(row['block'])] = counts.get(str(row['block']), 0) + 1
    require(counts == result['matched_by_block'] and sum(counts.values()) == 801, 'per-panel record counts')
    review = obj('reviews/independent-terminal.json')
    for role, rel in [('audit', 'evidence/audit.py'), ('plan', 'evidence/plan.json'), ('execution', 'run/execution.json'), ('result', 'run/result.json')]:
        require(review['pins'][role]['sha256'] == KNOWN[rel] and review['pins'][role]['size_bytes'] == (P / rel).stat().st_size, 'terminal review pin')
    require(review['result_review']['matched_main_count'] == 801 and review['terminal']['actual_child_rc'] == 0, 'terminal review summary')
    scope = obj('scope.json')
    require(scope['actual_calls'] == {'saved_record_reader': 1, 'model': 0, 'solver': 0, 'build': 0} and scope['physical_normality_accepted'] is False and scope['whole_file_hash_freshly_computed'] is False and scope['prior_strict_negative_OD_FAIL_retained'] is True, 'scope/counter limits')
    print('PASS_SCOPED_SAVED_CENSUS_INTEGRITY: 15 payloads, 11 verbatim origins, 801 main/companion rows; no raw reader/model/solver/build execution')
if __name__ == '__main__':
    try:
        verify()
    except Exception as exc:
        print('FAIL: ' + str(exc), file=sys.stderr)
        raise SystemExit(1)
