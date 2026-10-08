#!/usr/bin/env python3
"""Link retained local connected-host execution to current compiled source.

Current source hashes and retained bytes are verified, but this is not a new
forecast, final approved-policy identity, or an at-execution library-open trace.
"""
from pathlib import Path
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

sys.dont_write_bytecode=True
ROOT=Path(__file__).resolve().parents[2]
CURRENT=ROOT/'build/udm37-remaining-contracts-pr-work'
RUNROOT=ROOT/'build/udm37-connected-host-final-v2'


def require(ok,message):
    if not ok:raise ValueError(message)


def pin(p):
    p=Path(p);raw=p.read_bytes()
    return {'path':str(p.resolve()),'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}


def main():
    output=ROOT/'build/udm37-remaining-resolution-v1/scoped-execution-identity-v1.json'
    require(not output.exists(),'preserve prior audit')
    receiptpath=RUNROOT/'runtime-strengthened/receipt.json'
    receipt=json.loads(receiptpath.read_text());require(receipt['status']=='PASS','saved execution did not pass')
    cmdpath=RUNROOT/'runtime-strengthened/command-03.json';command=json.loads(cmdpath.read_text())
    require(command['actual_returncode']==0 and command['status']=='TERMINAL','saved process incomplete')
    executable=receipt['executables']['wrf'];exe=Path(executable['path'])
    require(pin(exe)['sha256']==executable['sha256'],'retained executable changed')
    arm=receipt['arms']['nonuniform-on']
    arm_pins={}
    for name in ('input','namelist','log','history'):
        got=pin(arm[name]['path'])
        require(got['sha256']==arm[name]['sha256'] and got['bytes']==arm[name]['size_bytes'],'retained '+name+' changed')
        arm_pins[name]=got
    require(command['argv']==[str(exe)] and command['cwd']==str(Path(arm['namelist']['path']).parent),
            'process does not join selected executable/arm')
    prep=CURRENT/'WRF/test/rrtmgp/prepare_udm_connected_host.py'
    spec=importlib.util.spec_from_file_location('source_reverse',prep)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    sourcepins=json.loads((RUNROOT/'source/observer-source-pins.json').read_text())
    for rel,rec in sourcepins.items():
        production=(CURRENT/'WRF'/rel).read_bytes();snap=(RUNROOT/'source/WRF'/rel).read_bytes()
        require(hashlib.sha256(production).hexdigest()==rec['production_sha256'],'production pin mismatch')
        require(hashlib.sha256(snap).hexdigest()==rec['snapshot_sha256'],'snapshot pin mismatch')
        stripped=re.sub(re.escape(module.BEGIN)+r'.*?'+re.escape(module.END),'',snap.decode(),flags=re.S).encode()
        require(stripped==production,'observer reversal does not join current production source')
    files=subprocess.check_output(['git','ls-files','-z','WRF'],cwd=CURRENT).decode().split('\0')
    differences=[];matched=[]
    for name in files:
        if not name:continue
        rel=name[4:];a=CURRENT/name;b=RUNROOT/'source'/name
        if a.is_symlink():ok=b.is_symlink() and os.readlink(a)==os.readlink(b)
        else:
            expected=sourcepins.get(rel,{}).get('snapshot_sha256') or pin(a)['sha256']
            ok=b.is_file() and pin(b)['sha256']==expected
        (matched if ok else differences).append(rel)
    expected=['test/rrtmgp/test_udm_connected_host.py','test/rrtmgp/test_udm_connected_host_build.py']
    require(sorted(differences)==expected,'unexpected snapshot source differences')
    cache={}
    for line in (RUNROOT/'producer/CMakeCache.txt').read_text().splitlines():
        if line.startswith(('CMAKE_Fortran_COMPILER:','CMAKE_Fortran_FLAGS:','USE_MPI:','USE_OPENMP:',
                            'USE_ALLOCATABLES:','USE_IPO:','WRF_CASE:','WRF_CORE:')):
            cache[line.split('=',1)[0]]=line.split('=',1)[1]
    libs=[]
    audit_env={**os.environ,'LD_LIBRARY_PATH':str(ROOT/'build/deps/netcdf/lib')}
    text=subprocess.check_output(['/usr/bin/ldd',str(exe)],text=True,env=audit_env)
    require('not found' not in text,'missing current resolved library')
    for line in text.splitlines():
        m=re.match(r'\s*(?:\S+\s+=>\s+)?(/\S+)\s+\(',line)
        if m:libs.append(pin(Path(m[1]).resolve()))
    offered=[]
    case=Path(command['cwd'])
    for p in sorted(case.iterdir()):
        if p.is_file() and (p.suffix=='.nc' or p.name.startswith(('RRTMG','rrtmgp'))):offered.append(pin(p))
    policy={'ccn_conc':1.e8,'cold_driver_reset':'legacy first-step constant',
            'native_bounds':'unchanged source; no unit authority assigned','scalar_adv_opt':0,
            'RK':3,'boundary':'periodic x/y','microphysics':27,'radiation_LW_SW':[37,37]}
    nml=case/'namelist.input';ntext=nml.read_text()
    for key,value in [('mp_physics','27'),('ra_lw_physics','37'),('ra_sw_physics','37'),('scalar_adv_opt','0')]:
        require(re.search(r'^\s*'+key+r'\s*=\s*'+value+r'\s*[,!\n]',ntext,re.M),'namelist policy differs: '+key)
    d={'schema':'UDM37_RETAINED_SCOPED_EXECUTION_IDENTITY_V1','status':'PASS_SCOPED_BYTE_BINDINGS_FINAL_IDENTITY_OPEN',
       'base_main':'0f6dd96c4ad588f974c2f89600c1b9aecbde7ccd','base_tree':'720e462503a36a1b1c79ec55bc04c6aab2f92b26',
       'kind':'retained reversible observer snapshot; actual model execution already occurred',
       'source_matches':len(matched),'source_snapshot_differences':differences,
       'difference_scope':'two test runners differ; no compiled WRF source difference beyond reversible observer blocks',
       'observer_source_pins':sourcepins,'source_observer_preparer':pin(prep),
       'executable':pin(exe),'build_receipt':pin(RUNROOT/'build-receipt.json'),
       'toolchain':pin(RUNROOT/'gnu-serial.cmake'),'selected_CMake_cache':cache,
       'runtime_receipt':pin(receiptpath),'process_receipt':pin(cmdpath),'arm':arm_pins,
       'offered_coefficient_files':offered,'coefficient_scope':'files provided in case; not actual OS file-open trace',
       'resolved_libraries_at_audit':libs,'audit_library_path':audit_env['LD_LIBRARY_PATH'],
       'libraries_at_original_execution_authenticated':False,
       'runtime_policy':policy,'production_accepted':False,'independent_physical_acceptance':'NOT_ACCEPTED',
       'final_identity':'OPEN: final accepted policy plus at-execution closure/coefficients and physical approval remain missing',
       'new_compiler_runs':0,'new_model_runs':0,'scientific_replay_runs':0}
    output.write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n')
    print(json.dumps({'status':d['status'],'source_matches':len(matched),'identity':pin(output)}))


if __name__=='__main__':main()
