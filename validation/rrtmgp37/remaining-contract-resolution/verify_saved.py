#!/usr/bin/env python3
"""Check included evidence bytes and scoped arithmetic; never approve physics.

External executables, coefficients, full NetCDF and LBL streams are not reopened.
An internally consistent manifest is not independent provenance authentication.
"""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct

BASE = Path(__file__).resolve().parent
REPO = BASE.parents[2]


def require(ok, message):
    if not ok:
        raise ValueError(message)


def read(name):
    return json.loads((BASE / name).read_text())


def flux_records(name):
    raw = (BASE / name).read_bytes()
    step = 8 + 122 * 8
    require(len(raw) > 0 and len(raw) % step == 0, 'prewrite record length')
    records = {}
    for offset in range(0, len(raw), step):
        expt, site = struct.unpack_from('<ii', raw, offset)
        key = (expt - 1, site - 1)
        require(key not in records and 0 <= key[0] < 18 and 0 <= key[1] < 100,
                'prewrite profile roster')
        records[key] = struct.unpack_from('<122d', raw, offset + 8)
    return records


def f32(value):
    return struct.pack('<f', value)


def rounding_cell(reference):
    require(reference > 0, 'this saved positive-flux analysis needs a positive reference')
    word = struct.unpack('<I', f32(reference))[0]
    lower = struct.unpack('<f', struct.pack('<I', word - 1))[0]
    upper = struct.unpack('<f', struct.pack('<I', word + 1))[0]
    return [(lower + reference) / 2, (upper + reference) / 2]


def main():
    manifest = read('manifest.json')
    require(manifest['production_accepted'] is False, 'manifest promoted physics')
    expected = {r['path'] for r in manifest['files']}
    require(len(expected) == len(manifest['files']), 'duplicate manifest paths')
    actual = {str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file()
              and p != BASE / 'manifest.json' and '__pycache__' not in p.parts}
    require(actual == expected, 'package file roster changed')
    for row in manifest['files']:
        p = (BASE / row['path']).resolve()
        require(p.is_relative_to(BASE) and not Path(row['path']).is_absolute(), 'unsafe package path')
        raw = p.read_bytes()
        require(len(raw) == row['bytes'] and hashlib.sha256(raw).hexdigest() == row['sha256'],
                'included bytes changed: ' + row['path'])
    script = REPO / 'WRF/test/rrtmgp/test_udm_native_ccn_bounds.py'
    require(hashlib.sha256(script.read_bytes()).hexdigest() == manifest['current_bounds_script_sha256'],
            'saved and current bounds scripts differ')
    checklist = read('checklist.json')
    ids = {'PHY-NC', 'PHY-SIZE', 'PHY-OCCURRENCE', 'REF-RFMIP', 'REF-LBL',
           'FINAL-IDENTITY', 'FINAL-FORECAST'}
    require(len(checklist['items']) == 7 and {r['id'] for r in checklist['items']} == ids,
            'seven parent gate roster differs')
    require(checklist['production_accepted'] is False and checklist['parent_completed_scoped'] == 15
            and checklist['parent_remaining'] == 7 and checklist['original_gate_count'] == 19
            and checklist['current_gate_count'] == 12, 'acceptance roster promoted')
    for row in checklist['items']:
        require(row['physical_gate_closed'] is False and row['status'] in ('OPEN', 'FAIL', 'NOT_RUN'),
                'physical gate promoted')
        for name in row['evidence']:
            require(name in expected, 'broken checklist evidence: ' + name)
    failed = read('evidence/native-bounds-v1/receipt.json')
    require(failed['status'] == 'FAIL_PRESERVED_STOPPED', 'first checker failure erased')
    bounds = read('evidence/native-bounds-v3/receipt.json')
    require(bounds['status'] == 'PASS_SCOPED_NATIVE_ENTRY_BOUNDS_AND_DRY_EXPORT', 'bounds scope')
    require(bounds['counts'] == {'manufactured_configurations': 20, 'fixture_processes': 6,
                                'actual_outer_udm_calls': 120, 'compiler_link_processes': 16}, 'bounds counts')
    spec = importlib.util.spec_from_file_location('saved_bounds', script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    for opt in ('O0', 'O2'):
        commands = [r for r in bounds['processes'] if r['kind'] == 'actual_udm_bounds_fixture'
                    and Path(r['cwd']).name == opt]
        require(len(commands) == 3, 'bounds process roster')
        parsed = []
        for r in commands:
            require(r['status'] == 'TERMINAL' and r['actual_returncode'] == 0 and not r['timed_out'],
                    'bounds process did not succeed')
            # The separate per-command receipt and the summary must agree.
            matching = [p for p in (BASE / 'evidence/native-bounds-v3').glob('command-*.json')
                        if json.loads(p.read_text()) == r]
            require(len(matching) == 1, 'process summary/receipt join')
            parsed.append(module.parse(matching[0].with_suffix('.stdout').read_text()))
        require(all(p['inputs'] == parsed[0]['inputs'] and p['returns'] == parsed[0]['returns']
                    and p['tags'] == parsed[0]['tags'] for p in parsed), 'observer passivity')
        require(not parsed[0]['observations'] and not parsed[1]['observations'], 'OFF observer output')
        require(module.verify(parsed[2]) == bounds['results'][opt]['rows'], 'saved active-cell arithmetic')
    old = read('evidence/rfmip-previous/residual-details.json')
    new = read('evidence/rfmip-eight/result.json')
    require(new['strict_failure_counts'] == {'rsd': 13, 'rsu': 8}
            and new['candidate_all_flux_bits_unchanged'] is True, 'strict FAIL was not preserved')
    previous = flux_records('evidence/rfmip-previous/diag_flux_written.bin')
    added = flux_records('evidence/rfmip-eight/diag_flux_written.bin')
    require(len(previous) == 135 and len(added) == 8, 'prewrite capture counts')
    require(set(added) == {tuple(v) for v in new['profiles']}, 'new profile selector join')
    roster = {(r['variable'], *r['index0_experiment_site_level']): r for r in old['residual_cells']}
    require(len(roster) == 21, 'original strict cell roster')
    newrows = {(r['variable'], *r['index0_experiment_site_level']): r for r in new['rows']}
    missing = {k for k, r in roster.items() if not r['profile_captured']}
    require(len(newrows) == 8 and set(newrows) == missing, 'missing-cell replacement roster')
    precast_fail = outside = 0
    for key, original in roster.items():
        var, e, s, level = key
        if original['profile_captured']:
            value = previous[(e, s)][level + (61 if var == 'rsd' else 0)]
            require(value == original['historical_rounding']['prewrite_W_m2'], 'old prewrite join')
        else:
            value = added[(e, s)][level + (61 if var == 'rsd' else 0)]
            require(value == newrows[key]['prewrite_W_m2'], 'new prewrite join')
        ref = original['reference_stored_W_m2']
        stored = original['historical_stored_W_m2']
        require(f32(value) == f32(stored), 'candidate binary32 cast')
        require(abs(stored - ref) > 1e-5, 'stored strict failure changed')
        low, high = rounding_cell(ref)
        outside += not low <= value <= high
        precast_fail += abs(value - ref) > 1e-5
    require((precast_fail, outside) == (14, 21), 'prewrite classification differs')
    identity = read('evidence/scoped-execution-identity-v1.json')
    require(identity['status'] == 'PASS_SCOPED_BYTE_BINDINGS_FINAL_IDENTITY_OPEN'
            and identity['production_accepted'] is False, 'identity scope promoted')
    print(json.dumps({'status': 'PASS_SCOPED_INCLUDED_EVIDENCE', 'production_accepted': False,
                      'parent_completed_scoped': 15, 'parent_remaining': 7,
                      'candidate_prewrite_coverage': 21, 'candidate_precast_strict_fail': 14,
                      'serialization_threshold_crossings': 7,
                      'RFMIP_stored_strict_fail': 21, 'external_payloads_reopened': False}))


if __name__ == '__main__':
    main()
