"""Preserve completed observations and decode inventories, without changing model data."""
from pathlib import Path
import gzip,hashlib,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;payload={}
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
for directory,key in [('udm37-native-sw-build-v4','build'),('udm37-native-sw-short-v2','short'),('udm37-native-sw-day-v2','day')]:
 D=B/directory;receipt=json.loads((D/'receipt.json').read_text());assert receipt.get('status','SUCCESS')=='SUCCESS',(key,receipt.get('status'))
 for pat in ['receipt.json','command-*.*','*.F','*.f90','history-comparison.json','host/namelist.input','host/namelist.output','host/radiation_iofields.txt','host/sw-phase.txt','host/real-budget.txt','host/vapor-first.txt']:
  for p in sorted(D.glob(pat)):payload[key+'/'+str(p.relative_to(D))]=p.read_bytes()
# A diagnostic assumption failure before the first completed step is not hidden.
for directory,key in [('udm37-native-sw-build-v1','development/unused_first_build'),('udm37-native-sw-build-v2','development/missing_optional_array_build'),('udm37-native-sw-build-v3','development/failed_diagnostic_compile'),('udm37-native-sw-short-v1','development/missing_optional_array_attempt')]:
 D=B/directory
 for pat in ['receipt.json','command-*.*','*.F','*.f90','host/sw-phase.txt']:
  for p in sorted(D.glob(pat)):payload[key+'/'+str(p.relative_to(D))]=p.read_bytes()
for n in ['coefficients-during.json','coefficients-after.json','baseline-pins.json','baseline-budget.json']:
 payload[n]=(B/'udm37-native-sw-analysis-v1'/n).read_bytes()
payload['plan.json']=(P/'plan.json').read_bytes()
files={};buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
 for n,b in sorted(payload.items()):
  x=tarfile.TarInfo(n);x.size=len(b);x.mtime=0;tar.addfile(x,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
(P/'saved').mkdir(exist_ok=True);archive=P/'saved/evidence.tar.gz';archive.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
names=['WRF/dyn_em/solve_em.F','WRF/dyn_em/module_bc_em.F','WRF/dyn_em/module_advect_em.F','WRF/dyn_em/module_em.F','WRF/dyn_em/module_first_rk_step_part1.F','WRF/phys/module_physics_addtendc.F','WRF/phys/module_ra_rrtmg_sw.F','WRF/phys/module_radiation_driver.F','validation/rrtmgp37/research-policy-contract/closure-conditions.json','validation/rrtmgp37/vapor-first-operation/result.json']
names += [str(p.relative_to(R)) for p in P.glob('*') if p.suffix in ['.py','.f90'] and p.name!='deposit.py']
identity={'baseline_main_commit':'e5aa8fd55c4752c9c2b23e359cb279c0438493a5','baseline_main_tree':'03aac2176bd869e1d50c4beba78f5c87ed78e2aa','production_changes':False,'source_scope':'Incremental private observation build from the pinned completed corrected-observer archive; not a clean-checkout full WRF build claim. Exact generated sources and actual compile/link/model receipts retained.','current_sources':{n:pin(R/n) for n in names},'files':files,'archive':pin(archive),'large_history_scope':'Actual NetCDF arrays compared locally; complete per-array hashes and whole-file hashes retained. Saved CI does not reopen those NetCDF files or run a model.','actual_new_WRF_processes':3,'eligible_completed_WRF_processes':2,'independent_meteorological_cases':1,'development_scope':'One unused preliminary build, one preliminary build used in the missing-optional-array stop, one failed private compile, and the final completed private build; no production fix resulted.','scientific_approval':False}
(P/'identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('NATIVE_SW_RETURN_DEPOSITED',len(files),archive.stat().st_size)
