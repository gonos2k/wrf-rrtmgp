"""Replay retained operands; never rerun a model or approve physical accuracy."""
from pathlib import Path
import argparse,gzip,hashlib,importlib.util,io,json,re,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2]
# Replay the retained cloudy campaign against its exact pre-cloud-off sources.
# This does not certify the modified runtime; current wrappers have separate tests.
import runpy
R = runpy.run_path(str(P.parent/'historical-source/binding.py'))['SnapshotRoot'](
    R, 'snapshot-789188e2.json')
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
E=load('vapor_evaluation',P/'evaluate.py');I=load('vapor_observer',P/'instrument.py');H=load('vapor_historical',P.parent/'historical-source/binding.py');V=load('vapor_readonly',P.parent/'real-case-budget/verify_saved.py');require=E.require
def sha(b):return hashlib.sha256(b).hexdigest()
def data():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'],'archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as tar:
  require(set(tar.getnames())==set(ident['files']),'archive roster');d={n:tar.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(d[n])==p['sha256'] and len(d[n])==p['bytes'],'payload '+n)
 for n,p in ident['current_sources'].items():require(sha((R/n).read_bytes())==p['sha256'],'current source '+n)
 for n in ['candidate-plan.json','source-candidate-plan.json']:require(d[n]==(P/n).read_bytes(),'candidate declaration changed')
 public=json.loads(d['public/receipt.json']);observed=json.loads(d['observed_build/receipt.json'])
 for n,p in public['sources'].items():require(sha((R/n).read_bytes())==p['sha256'],'compiled public source '+n)
 for n,p in observed['public_sources'].items():require(sha((R/n).read_bytes())==p['sha256'],'observed public source '+n)
 # The preliminary full-copy prototype is a serial implementation control,
 # not another independent meteorological case or a parallel-support claim.
 proto=json.loads(d['tile_copy_control_public/receipt.json'])
 latest=d['public/module_bc_em.F'].decode()
 local_copy='           IF (positive_source) THEN\n             DO j=max(jts,jds),min(jte,jde-1)\n             DO k=kts,min(kte,kde-1)\n             DO i=max(its,ids),min(ite,ide-1)\n               tend_before(i,k,j) = scalar_tend(i,k,j)\n             END DO\n             END DO\n             END DO\n           END IF'
 require(latest.count(local_copy)==1,'tile-local source copy changed')
 require(latest.replace(local_copy,'           IF (positive_source) tend_before = scalar_tend').encode()==d['tile_copy_control_public/module_bc_em.F'],'serial control differs beyond source-copy scope')
 for n in ['module_advect_em.F','solve_em.F']:require(d['public/'+n]==d['tile_copy_control_public/'+n],'serial control numerical source differs')
 proto_build=json.loads(d['tile_copy_control_build/receipt.json']);proto_day=json.loads(d['tile_copy_control_day/receipt.json'])
 require(proto_build['base_public_library']['sha256']==proto['library']['sha256'],'serial control public library')
 require(proto_day['executable']['sha256']==proto_build['executable']['sha256'],'serial control executable')
 require(d['tile_copy_control_day/host/namelist.input']==d['day/host/namelist.input'],'serial control physics or duration changed')
 for command in proto['commands']+proto_build['commands']+proto_day['commands']:require(command['actual_returncode']==0 and not command['timed_out'],'serial control command failed')
 for n,p in proto['sources'].items():require(sha(d['tile_copy_control_public/'+Path(n).name])==p['sha256'],'serial control public source receipt')

 require(public['fixture']['sha256']==sha((P/'native_source.f90').read_bytes()),'native source fixture')
 nt=json.loads(d['native_transport/receipt.json']);require(nt['fixture']['sha256']==sha((P/'native_transport.f90').read_bytes()) and nt['public_library']['sha256']==public['library']['sha256'],'native shared-flux library/fixture')
 kf=load('vapor_retained_kf',P.parent/'kfeta-precipitation-lifetime/verify_saved.py').data();kfbuild=json.loads(kf['native/receipt.json']);require(public['base_KFETA_library']['sha256']==kfbuild['library']['sha256'],'KF correction not linked')
 require(observed['base_public_library']['sha256']==public['library']['sha256'],'observer numerical library differs')
 bud=load('vapor_budget_observer',P.parent/'convective-support/instrument.py');generated=bud.transform(R);generated['solve_em.F']=I.transform(R,generated['solve_em.F'])
 for n,source in generated.items():
  require(d['observed_build/'+n]==source.encode(),'generated corrected observer '+n)
  folder='WRF/dyn_em' if n in ['solve_em.F','module_em.F'] else 'WRF/phys';V.readonly((R/folder/n).read_text(),source)
 for n,p in observed['sources'].items():require(sha(d['observed_build/'+n])==p['sha256'],'compiled corrected observer '+n)
 require(d['observed_build/vapor_probe.f90']==(P/'probe.f90').read_bytes(),'compiled vapor helper')
 require(d['observed_build/budget_probe.f90']==(P.parent/'convective-support/probe.f90').read_bytes(),'compiled budget helper')
 # The original traces remain bound to original source bytes, not these fixes.
 old=load('vapor_retained_original_day',P.parent/'convective-support/verify_saved.py').data();oldident=json.loads((P.parent/'convective-support/identity.json').read_text());root=H.HistoricalRoot(R,oldident['current_sources'])
 require(I.transform(root).encode()==d['original_build/solve_em.F'],'original observer transformation')
 V.readonly((root/'WRF/dyn_em/solve_em.F').read_text(),d['original_build/solve_em.F'].decode())
 require(d['original_build/probe.f90']==(P/'probe.f90').read_bytes(),'original helper source')
 require(d['flux_build/probe.f90']==(P/'flux_probe.f90').read_bytes(),'compiled face helper')
 require(d['components_build/probe.f90']==(P/'component_probe.f90').read_bytes(),'compiled source-component helper')
 for key in ['components_build','flux_build']:
  receipt=json.loads(d[key+'/receipt.json'])
  for n,p in receipt['sources'].items():require(sha(d[key+'/'+n])==p['sha256'],'compiled original source receipt '+key+'/'+n)
  V.readonly((root/'WRF/dyn_em/solve_em.F').read_text(),d[key+'/solve_em.F'].decode())
 V.readonly((root/'WRF/phys/module_physics_addtendc.F').read_text(),d['components_build/module_physics_addtendc.F'].decode())
 oldadv=H.historical_bytes(R,'WRF/dyn_em/module_advect_em.F','58253bdbeb188dd47ed0579fcd2891086be1889b75c0c7d3696c9ad1d213559d')
 V.readonly(oldadv.decode(),d['flux_build/module_advect_em.F'].decode())
 original_history=json.loads(old['history.json'])['history']['sha256']
 c=json.loads(d['original/history-comparison.json']);require(c['original_history_sha256']==original_history,'original control history')
 c=json.loads(d['components/history-comparison.json']);require(c['files'][0]['sha256']==original_history,'source-component control history')
 base=json.loads(old['host/receipt.json'])
 for arm,buildkey in [('original','original_build'),('components','components_build'),('flux','flux_build'),('roundoff','roundoff_build'),('short_public','public'),('short_observed','observed_build'),('day','observed_build'),('restart','public')]:
  receipt=json.loads(d[arm+'/receipt.json']);build=json.loads(d[buildkey+'/receipt.json']);require(receipt['status']=='SUCCESS','qualified host incomplete '+arm)
  require(receipt['executable']['sha256']==build['executable']['sha256'],'runtime executable '+arm)
  require(receipt.get('forcing',receipt.get('original_forcing'))['sha256']==base['forcing']['sha256'],'real boundary forcing changed '+arm)
  for cmd in receipt['commands']+build['commands']:require(cmd['actual_returncode']==0 and not cmd['timed_out'],'qualified execution failed '+arm)
  log=d[arm+'/command-01.stdout'].decode(errors='replace');require('SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log,'host terminal '+arm)
 for arm in ['short_public','short_observed','day','original','flux','roundoff']:
  rr=json.loads(d[arm+'/receipt.json']);require(rr['initial']['sha256']==base['initial']['sha256'],'real initial state changed '+arm)
 # Only output/checkpoint scheduling differs from the original real-data day.
 expected=old['host/host/namelist.input'].decode();expected,n=re.subn(r'(?im)^(\s*restart_interval_s\s*=\s*)[^,\n]+',lambda m:m[1]+'21540',expected);require(n==1,'checkpoint schedule edit')
 require(expected.encode()==d['day/host/namelist.input'],'day input/policy/dt changed')
 for arm in ['short_public','short_observed']:
  require(json.loads(d[arm+'/receipt.json'])['namelist']['sha256']==sha(d[arm+'/host/namelist.input']),'short namelist receipt')
 require(d['short_public/host/namelist.input']==d['short_observed/host/namelist.input'],'observer input differs')
 for arm in ['day','restart']:
  rr=json.loads(d[arm+'/receipt.json']);require(rr['namelist']['sha256']==sha(d[arm+'/host/namelist.input']),'runtime namelist '+arm)
  nml=d[arm+'/host/namelist.input'].decode();require(re.search(r'(?im)^\s*time_step\s*=\s*60\s*,',nml),'original dt changed')
 first_restart_LW=re.search(r'd01 (2016-10-06_\d\d:\d\d:\d\d) LW RRTMGP_UDM_LUT_CLIP',d['restart/command-01.stdout'].decode())
 require(first_restart_LW and first_restart_LW[1]=='2016-10-06_06:00:00','restart radiation phase changed')
 before=json.loads(d['coefficients-during.json']);after=json.loads(d['coefficients-after.json'])
 prior_coefficients=json.loads(old['coefficients-after.json'])
 for n,p in before['files'].items():require(p['sha256']==after['files'][n]['sha256']==prior_coefficients['files'][n]['sha256'],'coefficient changed '+n)
 closure='validation/rrtmgp37/research-policy-contract/closure-conditions.json'
 require(ident['current_sources'][closure]['sha256']==oldident['current_sources'][closure]['sha256'],'original seven conditions changed')
 require(before['frozen_table']['sha256']==after['frozen_table']['sha256']==sha((P.parent/'frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc').read_bytes()),'frozen table changed')
 return d

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--write',action='store_true');args=ap.parse_args();r=E.evaluate(data())
 if args.write:(P/'result.json').write_text(json.dumps(R.summary(r),indent=2)+'\n')
 else:require(r==json.loads((P/'result.json').read_text()),'results differ from actual operands')
 print(json.dumps(R.summary({'status':r['status'],'model_steps':r['model_steps'],'vapor_final_nonnegative_criterion_passed':r['vapor_final_nonnegative_criterion_passed'],'expired_rate_criterion_passed':r['KFETA_expired_rate_criterion_passed'],'water_conservation_approved':False,'whole_energy_approved':False,'current_runtime_source_matches':True,'new_model_runs':0})))
if __name__=='__main__':main()
