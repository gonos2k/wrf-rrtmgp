"""Deposit only completed actual runs and their original operands."""
from pathlib import Path
import gzip,hashlib,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;payload={}
DIRS=[('udm37-vapor-first-build-v1','original_build'),('udm37-vapor-first-host-v1','original'),('udm37-vapor-components-build-v1','components_build'),('udm37-vapor-components-host-v1','components'),('udm37-vapor-flux-build-v1','flux_build'),('udm37-vapor-flux-host-v1','flux'),('udm37-vapor-roundoff-build-v2','roundoff_build'),('udm37-vapor-roundoff-host-v1','roundoff'),('udm37-vapor-corrected-public-v2','public'),('udm37-vapor-corrected-observed-v2','observed_build'),('udm37-vapor-native-transport-v2','native_transport'),('udm37-vapor-corrected-short_public-v2','short_public'),('udm37-vapor-corrected-short_observed-v2','short_observed'),('udm37-vapor-corrected-day-v2','day'),('udm37-vapor-corrected-restart-v3','restart'),('udm37-vapor-corrected-public-v1','tile_copy_control_public'),('udm37-vapor-corrected-observed-v1','tile_copy_control_build'),('udm37-vapor-corrected-day-v1','tile_copy_control_day'),('udm37-vapor-corrected-short_public-v1','development/initial_copy_short_public'),('udm37-vapor-corrected-short_observed-v1','development/initial_copy_short_observed'),('udm37-vapor-corrected-restart-v2','development/initial_copy_restart')]
for directory,key in DIRS:
 D=B/directory;receipt=json.loads((D/'receipt.json').read_text());assert receipt.get('status','SUCCESS')=='SUCCESS',(key,receipt.get('status'))
 for pat in ['receipt.json','command-*.*','*.F','*.f90','history-comparison.json','host/namelist.input','host/namelist.output','host/radiation_iofields.txt','host/vapor-*.txt','host/real-budget.txt']:
  for p in sorted(D.glob(pat)):payload[key+'/'+str(p.relative_to(D))]=p.read_bytes()
# The first compile failed before any model process; keep the diagnostic log.
for p in sorted((B/'udm37-vapor-roundoff-build-v1').glob('command-*.*')):payload['development/failed_intrinsic_name_build/'+p.name]=p.read_bytes()
for n in ['history.json','copy-comparison.json','coefficients-during.json','coefficients-after.json']:payload[n]=(B/'udm37-vapor-corrected-analysis-v2'/n).read_bytes()
for n in ['candidate-plan.json','source-candidate-plan.json']:payload[n]=(P/n).read_bytes()
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
files={};buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
 for n,b in sorted(payload.items()):
  x=tarfile.TarInfo(n);x.size=len(b);x.mtime=0;tar.addfile(x,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
(P/'saved').mkdir(exist_ok=True);f=P/'saved/evidence.tar.gz';f.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
names=['WRF/dyn_em/solve_em.F','WRF/dyn_em/module_bc_em.F','WRF/dyn_em/module_advect_em.F','WRF/dyn_em/module_em.F','WRF/phys/module_physics_addtendc.F','validation/rrtmgp37/research-policy-contract/closure-conditions.json','validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc']
names += [str(p.relative_to(R)) for p in P.glob('*') if p.suffix in ['.py','.f90'] and p.name!='deposit.py']
(P/'identity.json').write_text(json.dumps({'original_base_commit':'4bb3f428931e871677f4cd8f47923878099471b0','KFETA_correction_PR':193,'vapor_correction_PR':194,'runtime_source_reference_commit':'16e4cb4c0d63929987f04e7c946397ac86ca67d9','producer_source_scope':'Incremental build from the pinned retained public archive and exact source files saved here; this is not a claim of a clean checkout build at that Git commit.','current_sources':{n:pin(R/n) for n in names},'files':files,'archive':pin(f),'large_history_scope':'Actual NetCDF arrays decoded locally and pinned per array and per file; saved CI replays retained inventories and reductions without reopening the large NetCDF.','scientific_approval':False},indent=2)+'\n')
print('VAPOR_CORRECTION_DEPOSITED',len(files),f.stat().st_size)
