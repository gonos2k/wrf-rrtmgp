#!/usr/bin/env python3
"""Recheck saved selected-source records; no compiler/model or unit approval."""
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
import sys
sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parent

def require(condition,message):
    if not condition:raise ValueError(message)

def verify():
    manifest=json.loads((ROOT/'manifest.json').read_text())
    expected={r['path'] for r in manifest['payloads']}
    actual={p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*') if p.is_file() and p!=ROOT/'manifest.json'}
    require(actual==expected and len(expected)==len(manifest['payloads']),'payload roster differs')
    for record in manifest['payloads']:
        p=ROOT/record['path'];require(not p.is_symlink() and p.resolve().is_relative_to(ROOT),'unsafe payload')
        data=p.read_bytes()
        require(len(data)==record['size_bytes'] and hashlib.sha256(data).hexdigest()==record['sha256'],'payload bytes differ: '+record['path'])
    require(manifest['physical_acceptance'] is False and manifest['remaining_physical_gates']==7,'physical gates changed')
    spec=importlib.util.spec_from_file_location('saved_host_checker',ROOT/'scripts/test_udm_host_number_transport.py')
    checker=importlib.util.module_from_spec(spec);spec.loader.exec_module(checker)
    r=json.loads((ROOT/'receipt.json').read_text())
    require(r['status']=='PASS_SCOPED_NATIVE_SCALAR_TRANSPORT' and r['scientific_acceptance'] is False,'scope differs')
    require(r['source_pins_before']==r['source_pins_after'],'original inputs changed')
    for record in r['source_pins_before']:
        name=Path(record['path']).name;p=ROOT/'scripts'/name
        data=p.read_bytes() if p.exists() else gzip.decompress((ROOT/'source'/(name+'.gz')).read_bytes())
        require(hashlib.sha256(data).hexdigest()==record['sha256'] and len(data)==record['size_bytes'],'source binding differs')
    pieces=[]
    require([s['procedure'] for s in r['native_slices']]==['advect_scalar','rk_update_scalar','rk_update_scalar_pd','flow_dep_bdy_qnn'],'slice roster differs')
    for s in r['native_slices']:
        data=gzip.decompress((ROOT/'source'/(Path(s['source']['path']).name+'.gz')).read_bytes())
        piece='\n'.join(data.decode().splitlines()[s['first_line']-1:s['last_line']])+'\n'
        require(hashlib.sha256(piece.encode()).hexdigest()==s['slice_sha256'],'native slice differs')
        pieces.append(piece)
    generated=gzip.decompress((ROOT/'source/native-scalar-slices.f90.gz').read_bytes())
    require(generated==(checker.ADAPTER+'\n'.join(pieces)+'\nend module\n').encode(),'adapter/native source assembly differs')
    require(hashlib.sha256(generated).hexdigest()==r['generated_source']['sha256'],'compiled source pin differs')
    ps=r['processes'];require(len(ps)==5 and all(p['status']=='TERMINAL' and p['actual_returncode']==0 for p in ps),'process roster/RC differs')
    require([p['kind'] for p in ps]==['compiler_version','compile_link','native_scalar_fixture','compile_link','native_scalar_fixture'],'process scope differs')
    for number,opt in ((3,'O0'),(5,'O2')):
        data=checker.parse((ROOT/f'command-{number:02d}.stdout').read_text());budgets=checker.check(data)
        result=r['results'][opt]
        require(result['cell_records']==len(data['cells'])==768 and result['boundary_storage_records']==len(data['boundaries'])==720,'record counts differ')
        require(data['counts']==result['procedure_calls']==[32,32,32,6] and budgets==result['budgets'],'derived FV ledger differs')
        require(set(result['negative_controls_rejected'])=={'missing-cell','wrong-map','wrong-mass','wrong-number','uncleared-source','wrong-inflow'},'negative-control roster differs')
    require(all(r[k]==0 for k in ('full_WRF_builds','WRF_host_runs','full_module_builds','UDM_calls','RTE_runs')),'model claims changed')
    pr=json.loads((ROOT/'pr154-terminal.json').read_text())
    require(pr['state']=='MERGED' and pr['mergeCommit']['oid']==manifest['source_base_main'] and
            pr['headRefOid']=='74dcfb368212e8d6983004ff81804099c09ee444','PR154 identity differs')
    require(len(pr['statusCheckRollup'])==11 and all(c['status']=='COMPLETED' and c['conclusion']=='SUCCESS' for c in pr['statusCheckRollup']),'PR154 terminal differs')
    return {'status':'PASS_SCOPED_SAVED_NATIVE_SCALAR_TRANSPORT','payloads':len(expected),
            'rederived_cell_records':1536,'rederived_boundary_storage_records':1440,
            'new_compiler_or_model_runs':0,'physical_acceptance':False}

if __name__=='__main__':
    try:print(json.dumps(verify()))
    except (ValueError,KeyError,OSError,StopIteration) as error:
        print(json.dumps({'status':'FAIL_SAVED_HOST_TRANSPORT','error':str(error)}));sys.exit(1)
