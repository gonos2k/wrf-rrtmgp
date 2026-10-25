"""Retain actual operands/receipts and ready input files; launches no model."""
from pathlib import Path
import json,hashlib,tarfile,io,gzip
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;payload={}
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
def pack(d,file):
 buf=io.BytesIO();files={}
 with tarfile.open(fileobj=buf,mode='w') as t:
  for n,b in sorted(d.items()):
   x=tarfile.TarInfo(n);x.size=len(b);x.mtime=0;t.addfile(x,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
 file.write_bytes(gzip.compress(buf.getvalue(),mtime=0));return {'archive':pin(file),'files':files}
for directory,key in [('udm37-sterling-boundary-build-v3','build'),('udm37-sterling-boundary-run-v1','run'),('udm37-sterling-interior-wps-v3','wps'),('udm37-sterling-interior-real-v1','real'),('udm37-sterling-interior-preflight-v1','preflight'),('udm37-sterling-thermodynamics-v2','thermo')]:
 D=B/directory
 for pat in ['receipt.json','command-*.*','*.F','*.f90','input.txt','host/namelist.input','host/namelist.output','namelist.wps','geogrid.log','metgrid.log','forecast.namelist.input','host/rsl.*','encoded/producer.json']:
  for p in D.glob(pat):
   if p.is_file():payload[key+'/'+str(p.relative_to(D))]=p.read_bytes()
payload['native/sterling-boundary.txt']=(B/'udm37-sterling-boundary-run-v1/host/sterling-boundary.txt').read_bytes()
for src,key in [('udm37-sterling-provenance-v1/provenance.json','provenance.json'),('udm37-sterling-thermodynamics-v2/thermodynamics.json','thermodynamics.json'),('udm37-sterling-boundary-history-comparison.json','history-comparison.json'),('udm37-vapor-corrected-public-v2/receipt.json','baseline-public-receipt.json'),('udm37-vapor-corrected-day-v2/receipt.json','baseline-day-receipt.json'),('udm37-vapor-corrected-day-v2/host/namelist.input','baseline-day.namelist'),('udm37-matthew-real-v1/execution-receipt.json','original-real-receipt.json'),('udm37-matthew-real-v1/case/namelist.input','original-real.namelist'),('udm37-sterling-interior-inputs-v1/download-receipt.json','download-receipt.json'),('udm37-sterling-interior-inputs-v1/extraction-manifest.json','extraction-manifest.json')]:payload[key]=(B/src).read_bytes()
for n in ['udm37-sterling-boundary-build-v1.log','udm37-sterling-boundary-build-v2.log','udm37-sterling-boundary-build-v3.log','udm37-sterling-wps-configure.log','udm37-sterling-wps-geogrid-build.log','udm37-sterling-wps-geogrid-direct-build.log','udm37-sterling-wps-geogrid-link-v2.log','udm37-sterling-wps-metgrid-build-v1.log']:
 p=B/n
 if p.exists():payload['development/'+n]=p.read_bytes()
for directory in ['udm37-sterling-interior-wps-v1','udm37-sterling-interior-wps-v2','udm37-sterling-thermodynamics-v1']:
 for p in (B/directory).glob('*'):
  if p.is_file() and not p.is_symlink() and p.suffix in ['.json','.log','.stderr','.stdout','.wps','.f90','.txt']:payload['development/'+directory+'/'+p.name]=p.read_bytes()
# Identify standard tools/tables and the unchanged old REAL optional-input semantics.
W=B/'udm37-sterling-wps-source-v1'
for p in [W/'configure.wps',W/'geogrid/GEOGRID.TBL.ARW',W/'metgrid/METGRID.TBL.ARW',W/'ungrib/Variable_Tables/Vtable.GFS']:
 payload['wps-source/'+str(p.relative_to(W))]=p.read_bytes()
old=B/'udm37-pr60-active-cu-current-build-v1/source-v3/WRF';assert (old/'share/module_optional_input.F').read_bytes()==(R/'WRF/share/module_optional_input.F').read_bytes();payload['old-optional-input.F']=(old/'share/module_optional_input.F').read_bytes()
payload['plan.json']=(P/'plan.json').read_bytes();(P/'saved').mkdir(exist_ok=True);evidence=pack(payload,P/'saved/evidence.tar.gz')
D=B/'udm37-sterling-interior-real-v1';inp={n:(D/'encoded'/n).read_bytes() for n in ['wrfinput_d01','wrfbdy_d01','producer.json']};inp['namelist.input']=(D/'forecast.namelist.input').read_bytes();inp['input-use-decision.json']=(P/'input-use-decision.json').read_bytes();inputs=pack(inp,P/'saved/interior-input.tar.gz')
deps=['validation/rrtmgp37/'+n for n in ['sterling-cloud-radiation-attribution/result.json','sterling-cloud-radiation-attribution/identity.json','real-output-independent-comparison/result.json','real-output-independent-comparison/identity.json','vapor-first-operation/identity.json','research-policy-contract/closure-conditions.json','real-case-budget/instrument.py','clear-reference/zero_number_input.py']]
sources=['WRF/share/module_bc.F','WRF/dyn_em/module_bc_em.F','WRF/dyn_em/solve_em.F','WRF/dyn_em/module_em.F','WRF/share/module_optional_input.F','WRF/dyn_em/module_initialize_real.F','WRF/phys/module_mp_udm.F','WRF/phys/module_microphysics_driver.F','WRF/share/module_model_constants.F','WRF/test/rrtmgp/convert_udm_specified.py','WRF/test/rrtmgp/test_netcdf_zz.py']+[str(p.relative_to(R)) for p in P.glob('*') if p.suffix in ['.py','.f90'] and p.name!='deposit.py']
identity={'base_main':'1fcffbbeea099839cce83ba2b3725d3de4543f5a','base_tree':'3970b8b68656ad6f0d10c7ddd3bc5b288e53e77d','evidence':evidence,'interior_input':inputs,'dependencies':{n:pin(R/n) for n in deps},'current_sources':{n:pin(R/n) for n in sources},'outputs':{n:pin(P/n) for n in ['result.json','input-use-decision.json','boundary-summary.csv','hourly-state-transect.png']},'production_changes':False,'new_WRF_processes':2,'new_REAL_processes':1,'new_24h_forecast':False,'qualified_WPS_processes':{'geogrid':1,'metgrid':1},'development_not_qualified':['boundary v1 source-anchor failure before compile','boundary v2 five-command successful build unused; v3 final five commands','WPS compile script missing csh; direct geogrid link needed-fopenmp for retained I/O','geogrid v1 path exceeds upstream128-character field; v2 default geog lacks highres package; v3 relative path and official lowres selector succeeded','saturation v1 extracted empty parameter block compile failed; v2 extracted correct block succeeded'],'generality':'serial one tile only; no new24h/restart or standaloneMie/RTE campaign; complete new input files retained, large native history locally retained and actual1350-pair comparison archived','physical_accuracy_approved':False,'original_seven_conditions_changed':False}
(P/'identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('DEPOSITED',[(x,identity[x]['archive']['bytes']) for x in ['evidence','interior_input']])
