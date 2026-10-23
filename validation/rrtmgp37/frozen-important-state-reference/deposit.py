"""Retain actual bounded host, quadrature and column evidence; no model launch."""
from pathlib import Path
import gzip,hashlib,io,json,tarfile,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;payload={}
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
for directory,key in [('udm37-frozen-selected-build-v1','selection_build'),('udm37-frozen-selected-selection-v1','selection'),('udm37-frozen-selected-capture-v1','capture'),('udm37-frozen-reference-column-v2','column_build'),('udm37-frozen-important-rte-v2','rte')]:
 D=B/directory;rec=json.loads((D/'receipt.json').read_text());assert rec.get('status','SUCCESS')=='SUCCESS'
 for pat in ['receipt.json','command-*.*','*.F','*.f90','history-comparison.json','target.json','area.json','input.dat','host/namelist.input','host/namelist.output','host/radiation_iofields.txt','host/frozen-selection.txt','host/capture/lw.*','*/input.dat','*/coefficients.dat','*/capture/lw.*']:
  for p in sorted(D.glob(pat)):payload[key+'/'+str(p.relative_to(D))]=p.read_bytes()
for directory,key in [('udm37-frozen-important-reference-v2','reference'),('udm37-frozen-important-original-v1','original'),('udm37-frozen-important-context-v1','context')]:
 for p in sorted((B/directory).glob('*.json')):payload[key+'/'+p.name]=p.read_bytes()
for n in ['reference','original']:
 directory='udm37-frozen-important-reference-v2' if n=='reference' else 'udm37-frozen-important-original-v1';payload[n+'/stdout.txt']=(B/(directory+'.log')).read_bytes()
for name in ['core.py','mie_jit.py','mie_nojit.py','__init__.py']:payload['dependencies/miepython/'+name]=(B/'udm37-frozen-independent-deps-v1/miepython'/name).read_bytes()
for p in (B/'udm37-frozen-independent-deps-v1/miepython-3.0.2.dist-info/licenses').iterdir():payload['dependencies/licenses/'+p.name]=p.read_bytes()
payload['dependencies/install.log']=(B/'udm37-frozen-independent-deps-v1.log').read_bytes();payload['dependencies/requirements.txt']=(R/'tools/udm_frozen_optics/requirements-independent.txt').read_bytes()
for source,key in [('udm37-vapor-corrected-public-v2/receipt.json','base-public-receipt.json'),('udm37-vapor-corrected-day-v2/receipt.json','base-day-receipt.json')]:payload['context/'+key]=(B/source).read_bytes()
for f in ['udm37-frozen-important-reference-v1.log','udm37-frozen-important-rte-v1.log']:payload['development/'+f]=(B/f).read_bytes()
# Preserve the preflight caller that omitted CU; it was rejected before any RTE process.
for p in sorted((B/'udm37-frozen-reference-column-v1').glob('*')):
 if p.suffix in ['.f90','.F','.json'] or p.name.startswith('command-'):payload['development/initial_column_build/'+p.name]=p.read_bytes()
payload['plan.json']=(P/'plan.json').read_bytes()
files={};buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
 for name,data in sorted(payload.items()):
  t=tarfile.TarInfo(name);t.size=len(data);t.mtime=0;tar.addfile(t,io.BytesIO(data));files[name]={'sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data)}
(P/'saved').mkdir(exist_ok=True);f=P/'saved/evidence.tar.gz';f.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
sources=['WRF/dyn_em/solve_em.F','WRF/dyn_em/module_bc_em.F','WRF/dyn_em/module_advect_em.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_ra_rrtmgp_frozen.F','WRF/phys/module_ra_rrtmgp_trace.F','tools/udm_frozen_optics/generate.py','tools/udm_frozen_optics/laguerre.py','validation/rrtmgp37/research-policy-contract/closure-conditions.json','validation/rrtmgp37/frozen-optics-reference/checks/independent-mie.json','validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc']
sources += [str(p.relative_to(R)) for p in P.glob('*') if p.suffix in ['.py','.f90'] and p.name!='deposit.py']
ident={'base_main':'ce3d1e46503c0bee1f71005e7024e83add7ed1ed','base_tree':'3cd893040359e7e015a2f61d56206cdf69a9c6f6','production_changes':False,'files':files,'archive':pin(f),'current_sources':{n:pin(R/n) for n in sources},'new_actual_WRF_processes':2,'new_actual_column_processes':6,'new_actual_independent_band_integrations':48,'new_actual_original_method_band_integrations':16,'independent_weather_cases':1,'source_scope':'private incremental selection observer and isolated public/renamed-adapter clients use the retained corrected public archive; no clean-checkout full WRF build claim','large_history_scope':'actual NetCDF arrays compared locally; saved replay verifies retained per-array/file hashes without opening NetCDF or launching a model','python_receipt_scope':'standalone integration outputs and successful exec logs are retained; their Python PIDs were not recorded; actual WRF/column command receipts retain PIDs','material_scope':'source ice data hash/URL retained, raw compilation not redistributed','physical_accuracy_approved':False}
(P/'identity.json').write_text(json.dumps(ident,indent=2)+'\n');print('FROZEN_ACTUAL_STATE_DEPOSITED',len(files),f.stat().st_size)
