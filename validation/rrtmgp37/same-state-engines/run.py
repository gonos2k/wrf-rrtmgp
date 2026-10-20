#!/usr/bin/env python3
"""Execute unchanged engine calls on one declared common diagnostic state."""
from pathlib import Path
import os,sys,gzip,json,importlib.util,hashlib
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;OUT=B/'udm37-same-state-run-v1';OUT.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=R/'validation/rrtmgp37/liquid-endpoint-optics/saved';sources={}
for ph in ['lw','sw']:
 p=prior/f'day_peak_{ph}_B/input.dat.gz';sources[ph]={'path':str(p.relative_to(R)),'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
base=gzip.decompress((R/sources['lw']['path']).read_bytes()).decode().splitlines();sw=gzip.decompress((R/sources['sw']['path']).read_bytes()).decode().splitlines();nl,nn=map(int,base[0].split()[1:3]);assert(nl,nn)==(121,59)
values=lambda i:list(map(float,base[i].split()))
# Same pressure/temperature/VMR and host Cstar, explicit clear or liquid diagnostics.
runner=h.Runner(OUT,120,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},6)
receipt={'sources':sources,'plan_sha256':hashlib.sha256((P/'plan.json').read_bytes()).hexdigest(),'executable':h.pin(B/'udm37-same-state-build-v1/compare'),'runs':[],'new_WRF_runs':0,'production_accepted':False}
(OUT/'plan.json').write_bytes((P/'plan.json').read_bytes())
for ph,arm,seed in [('LW','clear',17),('SW','clear',17),('LW','liquid',17),('SW','liquid',17),('LW','liquid',98765),('SW','liquid',98765)]:
 name=ph.lower()+'_'+arm+('_seed_control' if seed!=17 else '');d=OUT/name;d.mkdir();(d/'capture').mkdir();(d/'export4').mkdir()
 for f in ['RRTMG_LW_DATA','RRTMG_SW_DATA']:(d/f).symlink_to((R/'WRF/run'/f).resolve())
 cf=[0.]*nl;lwp=[0.]*nl;rel=[21.5]*nl
 if arm=='liquid':cf[29]=1.;lwp[29]=10.
 const=base[1].split();const[3]=sw[1].split()[3]
 arrays=[values(i) for i in range(2,14)]+[cf,lwp,rel,values(26),values(29)]+[list(map(float,sw[i].split())) for i in range(30,35)]
 text=f'{ph} {nl} {nn} {seed}\n'+' '.join(const)+'\n'+'\n'.join(' '.join(format(v,'.17e') for v in a) for a in arrays)+'\n';(d/'input.dat').write_text(text)
 before=h.pin(d/'input.dat');runner.environment.update(WRF_RRTMGP_CAPTURE_DIR=str(d/'capture'),WRF_RRTMGP_CAPTURE_CALL='1',WRF_RRTMGP_RRTMG4_EXPORT_DIR=str(d/'export4'),WRF_RRTMGP_RRTMG4_EXPORT_DOMAIN='1',WRF_RRTMGP_RRTMG4_EXPORT_I='1',WRF_RRTMGP_RRTMG4_EXPORT_J='2',WRF_RRTMGP_RRTMG4_EXPORT_STEP='6511',WRF_RRTMGP_RRTMG4_EXPORT_SECONDS='65100')
 log=runner.run([B/'udm37-same-state-build-v1/compare',R/'WRF/run',d/'input.dat'],d,name).read_text()
 assert 'SAME_STATE_BOTH_ENGINES_COMPLETE' in log and 'FATAL' not in log.upper()
 assert before==h.pin(d/'input.dat')
 assert (d/'before.bin').read_bytes()==(d/'after4.bin').read_bytes()==(d/'after37.bin').read_bytes()
 receipt['runs'].append({'name':name,'phase':ph.lower(),'arm':arm,'seed':seed,'input':before,'native4':h.pin(d/'native4.txt'),'result37':h.pin(d/'capture'/(ph.lower()+'.result')),'snapshot':h.pin(d/'before.bin'),'export4':h.pin(next((d/'export4').glob('*.txt')))});receipt['commands']=runner.commands;h.write_json(OUT/'receipt.json',receipt)
 print('PAIRED_ENGINES_COMPLETE',name,flush=True)
