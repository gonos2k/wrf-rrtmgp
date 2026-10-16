"""Verify retained normal-build evidence; launches no scientific executable."""
from pathlib import Path
import gzip,hashlib,importlib.util,json
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
    if not ok:raise ValueError(msg)
def sha(x):return hashlib.sha256(x).hexdigest()
def read(n):return gzip.decompress((B/'saved'/(n+'.gz')).read_bytes())
def load(p,n):
    s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def verify():
    seal=json.loads((B/'manifest.json').read_text())
    roster={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
    require(roster==set(seal['files']),'sealed roster differs')
    for n,z in seal['files'].items():
        p=B/n;require(not p.is_symlink() and p.stat().st_size==z['bytes'] and sha(p.read_bytes())==z['sha256'],'sealed file differs '+n)
    ident=json.loads((B/'identity.json').read_text());host=json.loads(read('host/receipt.json'))
    require(ident['production_source_changed'] and ident['defaults']==[0,0] and not ident['production_accepted'] and not ident['science_gates_closed'],'false approval or default change')
    require(ident['base_main']=='3485400c30b54c853787a4a4f9d54a3baea90424','wrong base')
    for n,h in ident['source_files'].items():require(sha(read('source/'+n))==h,'retained compiled source mismatch')
    require(ident['execution']==host['executable'] and host['status']=='PASS_SCOPED_INTEGRATED_RESEARCH','execution chain differs')
    require(len(host['processes'])==ident['qualified_WRF_processes']==14,'qualified process count differs')
    good={'cloud_00','cloud_01','cloud_10','cloud_11','capacity_previous','defaults_previous','held_11','resumed_11','audit_11'}
    refused={'mismatch_capacity','mismatch_size','missing_tag','bad_tag','unsupported_theta'}
    require({x['kind'] for x in host['processes']}==good|refused,'actual execution roster differs')
    for i,x in enumerate(host['processes'],1):
        require(x['status']=='TERMINAL' and not x['timed_out'] and x['actual_returncode']==0,'unreaped or failed process')
        require(x['argv']==[host['executable']['path']],'wrong executable in process')
        text=read(f'host/command-{i:02d}.stdout').decode(errors='replace')
        if x['kind'] in good:require('SUCCESS COMPLETE WRF' in text and 'FATAL CALLED' not in text,'incomplete normal execution')
        else:
            message='Malformed RRTMGP research metadata' if x['kind']=='bad_tag' else 'RRTMGP research polic'
            require(message in text and 'SUCCESS COMPLETE WRF' not in text,'missing actual rejection')
    ins=json.loads(read('input/identity.json'));base=ins['cloud_00']['physical_arrays']
    for n,z in ins.items():require(sha(read('input/'+n+'.nc'))==z['file_sha256']==ident['case_inputs'][n]['wrfinput_d01'],'actual input file identity differs')
    for n in ['cloud_01','cloud_10','cloud_11','held_11','resumed_11']:
        require(ins[n]['physical_arrays']==base,'four-way physical initial arrays differ')
    for c,s in [(0,0),(0,1),(1,0),(1,1)]:
        n=f'cloud_{c}{s}';require(ins[n]['attrs']=={'RRTMGP_CAPACITY_POLICY':c,'RRTMGP_LIQUID_SIZE_POLICY':s},'input policy tag differs')
    for n in good:
        idx=json.loads(read('host/'+n+'.json'));data=read('host/'+n+'.bin')
        require(sha(data)==idx['payload_sha256'],'history payload differs')
        for z in idx['records']:require(sha(data[z['offset']:z['offset']+z['bytes']])==z['sha256'],'history array differs')
        if n in ['held_11','resumed_11']:require(idx['attrs']['RRTMGP_CAPACITY_POLICY']==idx['attrs']['RRTMGP_LIQUID_SIZE_POLICY']==1,'lost history identity')
    # Retained PR179 outputs apply only where the normal integrated route reproduces arrays.
    prior=B.parent/'native-radiation-capacity/saved/host'
    for n,p in [('cloud_00','cloud_native'),('cloud_01','cloud_gamma8'),('capacity_previous','capacity'),('defaults_previous','legacy')]:
        require(read('host/'+n+'.bin')==gzip.decompress((prior/(p+'.bin.gz')).read_bytes()),'integrated default/standalone differs from PR179 '+n)
    require(read('host/audit_11.bin')==read('host/cloud_11.bin'),'diagnostic changes integrated forecast')
    require(host['audit_passivity_arrays_equal']==211,'diagnostic passivity missing')
    require((B/'closure-conditions.json').read_bytes()==(B.parent/'native-radiation-capacity/closure-conditions.json').read_bytes(),'seven conditions changed')
    a=load(B/'analyze_saved.py','integration_analysis');result=a.analyze(read)
    require(result==json.loads((B/'result.json').read_text()),'retained analysis differs')
    return {'status':result['status'],'qualified_WRF_processes':14,'new_science_runs_in_replay':0,
            'current_source_equals_retained':all((ROOT/n).is_file() and sha((ROOT/n).read_bytes())==h for n,h in ident['source_files'].items()),
            'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
