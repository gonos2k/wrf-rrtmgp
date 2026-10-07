#!/usr/bin/env python3
"""Exact saved-byte and state checks; no compiler, model, or physical PASS."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent


def require(condition, message):
    if not condition:
        raise ValueError(message)


def verify():
    manifest = json.loads((ROOT/'manifest.json').read_text())
    roster = {p['path'] for p in manifest['payloads']}
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
              if p.is_file() and p != ROOT/'manifest.json'}
    require(len(roster) == len(manifest['payloads']) and actual == roster, 'payload roster differs')
    for record in manifest['payloads']:
        p = ROOT/record['path']
        require(p.is_file() and not p.is_symlink(), 'payload absent or symlinked')
        data = p.read_bytes()
        require(len(data) == record['size_bytes'] and hashlib.sha256(data).hexdigest() == record['sha256'],
                'payload bytes differ: '+record['path'])
    require(manifest['physical_acceptance'] is False, 'saved observations cannot approve physics')
    spec = importlib.util.spec_from_file_location('historical_partial_checker',ROOT/'scripts/test_udm_partial_activation.py')
    checker = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(checker)
    receipt = json.loads((ROOT/'receipt.json').read_text())
    require(receipt['status'] == 'PASS_SCOPED_ACTUAL_UDM_PARTIAL_ACTIVATION', 'fixture receipt failed')
    require(receipt['scientific_acceptance'] is False and receipt['remaining_physical_gates'] == 7,
            'physical acceptance was relabeled')
    native = gzip.decompress((ROOT/'source/native_udm.F.gz').read_bytes())
    observed = gzip.decompress((ROOT/'source/observed_udm.F.gz').read_bytes())
    reconstructed, anchors = checker.observer_snapshot(native)
    require(reconstructed == observed and anchors == receipt['observer_anchors'], 'observer snapshot differs')
    require(hashlib.sha256(native).hexdigest() == receipt['source_pins_before'][0]['sha256'], 'native pin differs')
    require(receipt['source_pins_before'] == receipt['source_pins_after'], 'original source mutated')
    for before in receipt['source_pins_before'][3:]:
        p = ROOT/'scripts'/Path(before['path']).name
        require(hashlib.sha256(p.read_bytes()).hexdigest() == before['sha256'], 'historical checker/source pin differs')
    variants = {'O0':{},'O2':{}}
    processes = receipt['processes']
    require(len(processes)==23 and all(p['actual_returncode']==0 and p['status']=='TERMINAL' for p in processes),
            'actual process roster/returncode differs')
    for number,process in enumerate(processes,1):
        if process['kind'] != 'actual_udm_fixture':
            continue
        exe,mode = process['argv']
        opt,variant = Path(exe).parts[-2:]
        require(variant+'-'+mode not in variants[opt], 'duplicate fixture')
        variants[opt][variant+'-'+mode] = checker.parse((ROOT/f'command-{number:02d}.stdout').read_text())
    for opt,cases in variants.items():
        require(set(cases)=={'native-off','observed-off','observed-on'}, 'fixture variant roster differs')
        baseline = cases['native-off']
        for case in cases.values():
            for field in ('inputs','outputs','tags'):
                require(case[field] == baseline[field], 'pristine/OFF/ON state differs')
        require(not baseline['observations'] and not cases['observed-off']['observations'], 'OFF observations')
        rows = checker.check(cases['observed-on'])
        require(rows == receipt['results'][opt]['rows'], 'derived active observation rows differ')
    require(all(x['before']==x['after'] for x in receipt['executable_pins_before_and_after']), 'executable changed')
    return {'status':'PASS_SCOPED_SAVED_PARTIAL_ACTIVATION','payloads':len(roster),
            'rederived_active_cells':24,'new_compiler_or_model_runs':0,'physical_acceptance':False}


if __name__=='__main__':
    try:
        print(json.dumps(verify()))
    except Exception as error:
        print(json.dumps({'status':'FAIL_SAVED_PARTIAL_ACTIVATION','error':str(error)}))
        sys.exit(1)
