"""Deposit actual history extraction and link original observation/baseline bytes."""
from pathlib import Path
import json,hashlib,io,tarfile,gzip
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;D=B/'udm37-real-output-independent-v1'
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
payload={p.name:p.read_bytes() for p in D.glob('*') if p.is_file()};files={};buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
 for n,b in sorted(payload.items()):
  x=tarfile.TarInfo(n);x.size=len(b);x.mtime=0;tar.addfile(x,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
(P/'saved').mkdir(exist_ok=True);out=P/'saved/evidence.tar.gz';out.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
old=P.parent/'solrad-boundary-site-48h';observations=['raw/ste16280.dat','raw/ste16281.dat','sources/README_SOLRAD.txt','sources/dataset-ste-2016.html','download-manifest.json','station-selection.json','manifest.json']
deps=[]
for name in ['vapor-first-operation','native-sw-phase-closeout','frozen-important-state-reference']:
 deps += [str((P.parent/name/f).relative_to(R)) for f in ['identity.json','result.json']]
deps += ['validation/rrtmgp37/research-policy-contract/closure-conditions.json']
names=['WRF/phys/module_radiation_driver.F']+[str(p.relative_to(R)) for p in P.glob('*.py') if p.name!='deposit.py']
ident={'base_main':'001834648e80efc633562a17cba2b290f49b33b8','base_tree':'ae48354d312b0e98903525076d5e9309ecf75d50','archive':pin(out),'files':files,'existing_observation_evidence':{str((old/n).relative_to(R)):pin(old/n) for n in observations},'dependencies':{n:pin(R/n) for n in deps},'current_sources':{n:pin(R/n) for n in names},'outputs':{n:pin(P/n) for n in ['hourly-comparison.csv','sterling-corrected-day-sw.png']},'plan':pin(P/'plan.json'),'production_changes':False,'new_model_build_solver_processes':0,'original_seven_conditions_changed':False,'scope':'native corrected history decoded locally and matched to existing original NOAA observations; saved replay does not reopen the large NetCDF or rerun models','reference_download_scope':'original pinned NOAA download reused; no new raw download claimed'}
(P/'identity.json').write_text(json.dumps(ident,indent=2)+'\n');print('INDEPENDENT_OUTPUT_DEPOSITED',len(files),out.stat().st_size)
