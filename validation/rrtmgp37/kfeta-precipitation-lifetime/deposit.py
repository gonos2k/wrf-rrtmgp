from pathlib import Path
import gzip,hashlib,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;payload={}
for directory,key in [('udm37-kfeta-expiry-build-v1','native'),('udm37-kfeta-expiry-probe-v1','probe'),('udm37-kfeta-expiry-host-v1','host')]:
 D=B/directory
 for pat in ['receipt.json','command-*.*','*.F','probe.f90','before/scheme-*.bin','after/scheme-*.bin','*/namelist.input','*/radiation_iofields.txt','*/kfeta-lifetime.txt','history-comparison.json']:
  for p in sorted(D.glob(pat)):payload[key+'/'+str(p.relative_to(D))]=p.read_bytes()
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
files={};buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
 for n,b in sorted(payload.items()):
  x=tarfile.TarInfo(n);x.size=len(b);x.mtime=0;tar.addfile(x,io.BytesIO(b));files[n]={'sha256':hashlib.sha256(b).hexdigest(),'bytes':len(b)}
(P/'saved').mkdir(exist_ok=True);f=P/'saved/evidence.tar.gz';f.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
names=['WRF/phys/module_physics_addtendc.F','WRF/phys/module_surface_driver.F','WRF/dyn_em/module_first_rk_step_part1.F','WRF/phys/module_cumulus_driver.F','WRF/phys/module_cu_kfeta.F','WRF/dyn_em/solve_em.F','validation/rrtmgp37/research-policy-contract/closure-conditions.json']
names += [str(p.relative_to(R)) for p in P.glob('*.py') if p.name!='deposit.py']+[str((P/'native.f90').relative_to(R)),str((P/'probe.f90').relative_to(R))]
(P/'identity.json').write_text(json.dumps({'base_commit':'4bb3f428931e871677f4cd8f47923878099471b0','current_sources':{n:pin(R/n) for n in names},'files':files,'archive':pin(f),'physical_accuracy_approved':False},indent=2)+'\n')
print('KFETA_FIX_DEPOSITED',len(files),f.stat().st_size)
