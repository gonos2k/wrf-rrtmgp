#!/usr/bin/env python3
"""Verify sealed historical kernel records; no compiler or physical approval."""
import copy
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent

def require(condition,message):
    if not condition:
        raise ValueError(message)

def verify():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    expected={r['path'] for r in manifest['payloads']}
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=ROOT/'manifest.json'}
    require(actual==expected and len(expected)==len(manifest['payloads']),'payload roster differs')
    for record in manifest['payloads']:
        p=ROOT/record['path']; require(not p.is_symlink() and p.resolve().is_relative_to(ROOT),'unsafe payload')
        data=p.read_bytes()
        require(len(data)==record['size_bytes'] and hashlib.sha256(data).hexdigest()==record['sha256'],
                'payload bytes differ: '+record['path'])
    require(manifest['physical_acceptance'] is False and manifest['remaining_physical_gates']==7,'physical gates changed')
    spec=importlib.util.spec_from_file_location('saved_kernel_checker',ROOT/'scripts/test_udm_thompson_radius.py')
    checker=importlib.util.module_from_spec(spec); spec.loader.exec_module(checker)
    receipt=json.loads((ROOT/'receipt.json').read_text())
    require(receipt['status']=='PASS_SCOPED_ACTUAL_CLOUD_RADIUS_KERNELS' and
            receipt['scientific_acceptance'] is False and receipt['thompson_init_calls']==0,'scope changed')
    require(receipt['source_pins_before']==receipt['source_pins_after'],'original inputs changed')
    for record in receipt['source_pins_before']:
        name=Path(record['path']).name
        p=ROOT/'scripts'/name
        data=p.read_bytes() if p.exists() else gzip.decompress((ROOT/'source'/(name+'.gz')).read_bytes())
        require(hashlib.sha256(data).hexdigest()==record['sha256'] and len(data)==record['size_bytes'],'source binding differs')
    for scheme,source in (('udm','module_mp_udm.F'),('thompson','module_mp_thompson.F')):
        native=gzip.decompress((ROOT/'source'/(source+'.gz')).read_bytes())
        for variant,observed in (('bridge',False),('observed',True)):
            data=gzip.decompress((ROOT/'source'/f'{scheme}-{variant}.F.gz').read_bytes())
            require(checker.snapshot(native,scheme,observed)==data,'test bridge/observer differs')
    processes=receipt['processes']
    require(len(processes)==29 and all(p['status']=='TERMINAL' and p['actual_returncode']==0 for p in processes),'process roster/RC differs')
    variants={'O0':{},'O2':{}}
    for i,p in enumerate(processes,1):
        if p['kind']!='actual_radius_fixture':continue
        exe,enabled=p['argv']; opt,variant=Path(exe).parts[-2:]
        key=variant+'-'+enabled
        require(opt in variants and key not in variants[opt],'duplicate fixture identity')
        variants[opt][key]=checker.parse((ROOT/f'command-{i:02d}.stdout').read_text())
    for opt,cases in variants.items():
        require(set(cases)=={'bridge-off','observed-off','observed-on'},'kernel variant roster differs')
        baseline=cases['bridge-off']['cases']
        require(all(v['cases']==baseline for v in cases.values()),'observer changed returns')
        require(not cases['bridge-off']['observations'] and not cases['observed-off']['observations'],'OFF emitted observation')
        rows=checker.check(cases['observed-on'])
        require(rows==receipt['results'][opt]['rows'],'derived radius results differ')
    require(receipt['counts']=={'compiler_or_link_processes':22,'fixture_processes':6,'compiler_version_queries':1,
                              'actual_helper_calls':72,'observed_cloud_cells':24},'execution counts differ')
    pr=json.loads((ROOT/'pr153-terminal.json').read_text())
    require(pr['state']=='MERGED' and pr['mergeCommit']['oid']==manifest['source_base_main'] and
            pr['headRefOid']=='f5be994cf738d23336f6d9b88c000252091d5edd','PR153 identity differs')
    checks=pr['statusCheckRollup']
    require(len(checks)==11 and all(c['status']=='COMPLETED' and c['conclusion']=='SUCCESS' for c in checks),'PR153 terminal checks differ')
    return {'status':'PASS_SCOPED_SAVED_CLOUD_RADIUS_KERNELS','payloads':len(expected),
            'rederived_observed_cloud_cells':24,'new_compiler_or_model_runs':0,'physical_acceptance':False}

if __name__=='__main__':
    try: print(json.dumps(verify()))
    except (ValueError,KeyError,OSError,StopIteration) as error:
        print(json.dumps({'status':'FAIL_SAVED_RADIUS_KERNELS','error':str(error)})); sys.exit(1)
