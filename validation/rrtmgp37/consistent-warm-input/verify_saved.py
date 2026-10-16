"""Study replay; no physics gate or historical source is silently promoted."""
import gzip,hashlib,importlib.util,json,math
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def read(n):return gzip.decompress((B/'saved'/(n+'.gz')).read_bytes())
def sha(x):return hashlib.sha256(x).hexdigest()
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def verify():
 seal=json.loads((B/'manifest.json').read_text());require(not seal['production_accepted'],'false production promotion')
 roster={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts};require(roster==set(seal['files']),'sealed roster differs')
 for n,row in seal['files'].items():
  p=B/n;require(not p.is_symlink() and p.stat().st_size==row['bytes'] and sha(p.read_bytes())==row['sha256'],'sealed bytes differ '+n)
 ident=json.loads((B/'identity.json').read_text());require(ident['base_main']=='7fa7e594c34514fe995ba0321a3f84efa55f2aab' and not ident['production_source_changed'] and not ident['physics_gates_closed'],'study/source scope changed')
 for n,digest in ident['source_files'].items():require(sha(read('source/'+n))==digest,'retained studied source differs '+n)
 for tag,count in [('canonical',3),('theta_reference',3),('final',3)]:
  receipt=json.loads(read('host/'+tag+'/receipt.json'));require(len(receipt['processes'])==count,'actual host/producer scope')
  for idx,p in enumerate(receipt['processes'],1):
   require(p['status']=='TERMINAL' and p['actual_returncode']==0 and not p['timed_out'],'unqualified actual host process')
   text=read(f'host/{tag}/command-{idx:02d}.stdout');require(b'SUCCESS COMPLETE' in text and b'FATAL CALLED' not in text,'host did not succeed')
  if tag!='canonical':require(read('host/'+tag+'-on_dt10.bin')==read('host/'+tag+'-off_dt10.bin'),'observer changes whole history')
 for before,after,allowed in [('canonical','theta_reference',{'T_BASE'}),('theta_reference','final',{'P','AL','PH','Z_BASE','QNCCN','QNCLOUD','QNRAIN'})]:
  x=audit_before=json.loads(read('host/'+before+'-input.json'));y=json.loads(read('host/'+after+'-input.json'));x={z['variable']:z for z in x['records']};y={z['variable']:z for z in y['records']};require(set(x)==set(y),'input variable roster differs')
  require(all(x[n]['sha256']==y[n]['sha256'] for n in x if n not in allowed),'unrelated initial field modified')
 producer=json.loads(read('inputs/final-producer-receipt.json'));require(producer['seed_sha256']==sha(read('inputs/ideal-seed.nc')) and producer['output_sha256']==sha(read('inputs/final.nc')),'actual producer file binding')
 require(json.loads(read('host/final-input.json'))['source_NetCDF_sha256']==producer['output_sha256'],'executed final input not produced here')
 # Link unchanged production runtime to the prior archive/executable proof.
 prior=ROOT/'validation/rrtmgp37/policy2-budget-optics/saved'
 pr=json.loads(gzip.decompress((prior/'observer/receipt.json.gz').read_bytes()));final=json.loads(read('host/final/receipt.json'));require(final['executable']['sha256']==pr['executable']['sha256'],'unbound science executable')
 a=load(B/'analyze_saved.py','warm_a');result=a.analyze(read);require(result==json.loads((B/'result.json').read_text()),'raw replay differs')
 mie=json.loads(read('mie/result.json'));require(mie['engine']=='3.2.0' and mie['temperature_K']==298.15 and mie['reff_um']==12 and not mie['LUT_original_temperature_PSD_RI_weighting_known'],'optical temperature/scope changed')
 for name in ['Hale','Segelstein']:require(sha(read('mie/'+name+'.yml'))==mie['reference_sources'][name]['sha256'],'water RI data differs')
 original=json.loads(read('flux/LUT/coefficients.json'))['arrays'];lookup={n:n for n in ['extliq','ssaliq','asyliq']}
 for mode,case in [('Hale','baseline'),('Segelstein','RI_Segelstein_same_25C')]:
  tab=json.loads(read('flux/'+mode+'/coefficients.json'));require(sha(read('flux/'+mode+'/rrtmgp-clouds-sw-bnd.nc'))==tab['file_sha256'],'actual optical table bytes differ')
  for field in lookup:
   for band in range(14):
    for ri in range(20):
     x=original[field][band][ri];y=tab['arrays'][field][band][ri]
     if band in [5,7] and ri in [9,10]:
      row=next(z for z in mie['records'] if z['band']==band+1 and z['case']==case);o=row['calculations']['r2048s192']['Planck5780'];val=o[{'extliq':'ext','ssaliq':'ssa','asyliq':'g'}[field]];require(math.isclose(y,val,rel_tol=2e-7),'Mie query12 coefficient changed')
     else:require(x==y,'unrelated optical coefficient changed')
 flux=json.loads(read('flux/receipt.json'));require(len(flux['commands'])==3 and all(p['status']=='TERMINAL' and p['actual_returncode']==0 and not p['timed_out'] for p in flux['commands']),'actual RTE comparison failed')
 require(json.loads((B/'closure-conditions.json').read_text())==json.loads((ROOT/'validation/rrtmgp37/policy2-budget-optics/closure-conditions.json').read_text()),'seven closure conditions changed')
 require(not result['production_accepted'] and not result['physics_gates_closed'] and all(not x['full_energy_closed'] for x in result['host'].values()),'false physical approval')
 return {'status':'PASS_SCOPED_CONSISTENT_WARM_STUDY','qualified_WRF_processes':8,'qualified_ideal_processes':1,'independent_thin_RTE_columns':3,'fresh_model_runs_in_replay':0,'whole_host_budget_approved':False,'LUT_generation_certified':False,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
