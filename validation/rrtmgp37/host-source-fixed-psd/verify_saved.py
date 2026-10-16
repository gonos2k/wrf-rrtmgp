"""Integrity/replay checks for one scoped source and PSD investigation."""
import gzip,hashlib,importlib.util,json,math,re
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def read(n):return gzip.decompress((B/'saved'/(n+'.gz')).read_bytes())
def sha(x):return hashlib.sha256(x).hexdigest()
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def verify():
 seal=json.loads((B/'manifest.json').read_text());require(not seal['production_accepted'],'false approval');files={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts};require(files==set(seal['files']),'sealed roster differs')
 for n,z in seal['files'].items():
  p=B/n;require(not p.is_symlink() and p.stat().st_size==z['bytes'] and sha(p.read_bytes())==z['sha256'],'sealed file changed '+n)
 ident=json.loads((B/'identity.json').read_text());require(ident['base_main']=='819e48db62eeb4c1d07d576fe5676a9964ff63ed' and not ident['production_source_changed'] and not ident['physics_gates_closed'],'source scope retagged')
 for n,digest in ident['source_files'].items():require(sha(read('source/'+n))==digest,'studied science source differs')
 require(re.sub(rb'! BUDGET_OBSERVER_BEGIN\n.*?! BUDGET_OBSERVER_END\n',b'',read('observer/solve_em.F'),flags=re.S)==read('source/WRF/dyn_em/solve_em.F'),'observer not reversible')
 archive=json.loads(read('observer/archive.json'));require(len(archive['original'])==len(archive['diagnostic']),'archive roster differs');changed=[x['name'] for x,z in zip(archive['original'],archive['diagnostic']) if x!=z];require(set(changed)=={'/','solve_em.F.o/'} and changed==archive['changed_members'],'unrelated compiled member changed')
 host=json.loads(read('host/receipt.json'));obs=json.loads(read('observer/receipt.json'));require(host['executable']==obs['executable'] and len(host['commands'])==3 and host['initial_input']['sha256']==ident['actual_input_sha256'],'actual executable/input chain')
 prior=ROOT/'validation/rrtmgp37/consistent-warm-input/saved';base=json.loads(gzip.decompress((prior/'host/final-input.json.gz').read_bytes()));require(ident['actual_input_sha256']==base['source_NetCDF_sha256'],'original final input was changed')
 for i,z in enumerate(host['commands'],1):
  require(z['status']=='TERMINAL' and z['actual_returncode']==0 and not z['timed_out'],'actual host failed/unreaped');require(b'SUCCESS COMPLETE WRF' in read(f'host/command-{i:02d}.stdout'),'host completion missing')
 for name in ['on_dt10','off_dt10','on_dt5']:
  idx=json.loads(read('host/'+name+'.json'));require(len(idx['records'])==211 and idx['attrs']['UDM_NUMBER_POLICY']==1 and idx['attrs']['UDM_POPULATION_POLICY']==2,'host source policy differs')
 require(read('host/on_dt10.bin')==read('host/off_dt10.bin')==gzip.decompress((prior/'host/final-on_dt10.bin.gz').read_bytes()),'source observer/capture changes history bytes')
 require(read('host/on_dt5.bin')==gzip.decompress((prior/'host/final-on_dt5.bin.gz').read_bytes()),'dt5 same input science differs')
 positive=json.loads(read('positive/result.json'));require(positive['actual_UDM_calls']==1 and positive['source_sha256']==sha(read('positive/production.F'))==ident['source_files']['WRF/phys/module_mp_udm.F'],'positive state compiled source binding')
 for z in positive['commands']:require(z['status']=='TERMINAL' and z['actual_returncode']==0 and not z['timed_out'],'positive module run failed')
 psd=json.loads(read('psd/moments-optics.json'));require(psd['material_temperature_K']==298.15 and sha(read('psd/Segelstein.yml'))==psd['water_sha256'],'RI/temperature changed')
 original=json.loads(read('psd/original-coefficients.json'))['arrays']
 for shape in [8,16]:
  row=next(x for x in psd['PSDs'] if x['shape']==shape);idx=math.ceil(row['reff_um']-2.5);tab=json.loads(read(f'psd/s{shape}-coefficients.json'));require(sha(read(f'psd/s{shape}-table.nc'))==tab['file_sha256'],'actual diagnostic table differs')
  for field,n in [('extliq','ext'),('ssaliq','ssa'),('asyliq','g')]:
   for band in range(14):
    for ri in range(20):
     x=original[field][band][ri];y=tab['arrays'][field][band][ri]
     if band in [5,7] and ri in [idx-1,idx]:require(math.isclose(y,row['bands'][str(band+1)]['r2048s192'][n],rel_tol=2e-7),'fixed mass-number Mie table changed')
     else:require(x==y,'unrelated band or radius changed')
 receipt=json.loads(read('psd/receipt.json'));require(len(receipt['commands'])==6 and receipt['current_host_liquid_absent'] is True,'optical actual scope changed')
 for z in receipt['commands']:require(z['status']=='TERMINAL' and z['actual_returncode']==0 and not z['timed_out'],'actual PSD RTE failed')
 a=load(B/'analyze_saved.py','source_psd_analysis');result=a.analyze(read);require(result==json.loads((B/'result.json').read_text()),'raw source/PSD replay differs');require(not result['production_accepted'] and not result['physics_gates_closed'],'false physical promotion')
 require(json.loads((B/'closure-conditions.json').read_text())==json.loads((ROOT/'validation/rrtmgp37/consistent-warm-input/closure-conditions.json').read_text()),'seven physical conditions changed')
 return {'status':'PASS_SCOPED_SOURCE_LOCALIZATION_AND_FIXED_M0M3_PSD','WRF_processes':3,'positive_UDM_calls':1,'RTE_columns':6,'fresh_model_runs_in_replay':0,'full_host_water_approved':False,'PSD_observationally_approved':False,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
