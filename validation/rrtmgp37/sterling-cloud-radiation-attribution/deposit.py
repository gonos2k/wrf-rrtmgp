"""Retain bounded run/source/actual operands; never launch a model."""
from pathlib import Path
import json,hashlib,tarfile,io,gzip
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;payload={}
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
for name,key in [('udm37-sterling-cloud-build-v1','build'),('udm37-sterling-cloud-run-v1','run')]:
 D=B/name;r=json.loads((D/'receipt.json').read_text());assert r.get('status','SUCCESS')=='SUCCESS'
 for pat in ['receipt.json','command-*.*','*.F','*.f90','host/namelist.input','host/namelist.output']:
  for p in D.glob(pat):payload[key+'/'+str(p.relative_to(D))]=p.read_bytes()
payload['host/sterling-cloud.txt']=(B/'udm37-sterling-cloud-run-v1/host/sterling-cloud.txt').read_bytes()
for p in (B/'udm37-sterling-finish-v2').rglob('*'):
 if p.is_file():payload[str(p.relative_to(B/'udm37-sterling-finish-v2'))]=p.read_bytes()
for n in ['udm37-sterling-analysis-v1.py','udm37-sterling-finish-v1.py','udm37-sterling-finish-v1.log','udm37-sterling-finish-v2.log']:payload['development/'+n]=(B/n).read_bytes()
for src,name in [('udm37-vapor-corrected-public-v2/receipt.json','baseline-public-receipt.json'),('udm37-vapor-corrected-day-v2/receipt.json','baseline-day-receipt.json')]:payload[name]=(B/src).read_bytes()
payload['plan.json']=(P/'plan.json').read_bytes();buf=io.BytesIO();files={}
with tarfile.open(fileobj=buf,mode='w') as t:
 for n,b in sorted(payload.items()):
  x=tarfile.TarInfo(n);x.size=len(b);x.mtime=0;t.addfile(x,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
(P/'saved').mkdir(exist_ok=True);f=P/'saved/evidence.tar.gz';f.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
deps=['validation/rrtmgp37/real-output-independent-comparison/'+n for n in ['identity.json','result.json','analyze.py','hourly-comparison.csv','sterling-corrected-day-sw.png']]
deps += ['validation/rrtmgp37/solrad-boundary-site-48h/'+n for n in ['raw/ste16280.dat','raw/ste16281.dat']]
deps += ['validation/rrtmgp37/vapor-first-operation/identity.json','validation/rrtmgp37/research-policy-contract/closure-conditions.json']
source=['WRF/phys/module_ra_rrtmg_sw.F','WRF/dyn_em/module_first_rk_step_part1.F','WRF/phys/module_radiation_driver.F']+[str(p.relative_to(R)) for p in P.glob('*') if p.suffix in ['.py','.f90'] and p.name!='deposit.py']
ident={'base_main':'0aadad812e5fffdb99d3bf0c34ea5429e4b26487','base_tree':'b072c653b57a233df9f89426f14f4b6190ad45fc','archive':pin(f),'files':files,'dependencies':{n:pin(R/n) for n in deps},'current_sources':{n:pin(R/n) for n in source},'outputs':{n:pin(P/n) for n in ['transect.csv','sterling-components-transect.png']},'new_actual_WRF_processes':1,'compile_and_link_commands':5,'new_standalone_RTE_Mie_processes':0,'production_changes':False,'original_seven_conditions_changed':False,'scope':'one bounded read-only diagnostic restart, not a new24-hour or general restart campaign; actual1350 native array comparisons done locally, hashes replayed without opening large NetCDF','standalone_extraction_scope':'native history and boundary decoded locally by retained extraction source; standalone extraction Python PID not recorded','physical_accuracy_approved':False}
(P/'identity.json').write_text(json.dumps(ident,indent=2)+'\n');print('STERLING_ATTRIBUTION_DEPOSITED',len(files),f.stat().st_size)
