#!/usr/bin/env python3
"""Freeze selected actual evidence; large real histories stay content-pinned in build storage."""
from pathlib import Path
import json,gzip,hashlib,tarfile,io,platform
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;S=P/'saved';S.mkdir(exist_ok=False);files={}
def put(n,p):
 raw=p.read_bytes();out=S/(n+'.gz');out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(gzip.compress(raw,mtime=0));files[n]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'gzip':str(out.relative_to(P))}
for n in ['analysis.json','selected.json','manufactured.json']:put(n,B/'udm37-specified-number-analysis-v1'/n)
for n in ['receipt.json','good/kernel.txt','good/endpoints.txt','manufactured.nc']:put('kernel/'+n,B/'udm37-specified-number-kernel-v4'/n)
for d,key in [('udm37-specified-number-run-v2','integration'),('udm37-specified-number-run-v1','mode0_attempt'),('udm37-specified-number-restart-probe-v1','restore_observer'),('udm37-specified-number-host-control-v1','number0_control'),('udm37-specified-number-refusals-v1','refusals'),('udm37-specified-number-legacy-v1','legacy_regression'),('udm37-specified-number-guard-v3','scope_probe'),('udm37-specified-number-build-v1','build')]:
 root=B/d;put(key+'/receipt.json',root/'receipt.json')
 for p in root.rglob('namelist.input'):put(key+'/'+str(p.relative_to(root)),p)
 for p in root.rglob('namelist.output'):put(key+'/'+str(p.relative_to(root)),p)
 for p in root.glob('command-*.*'):put(key+'/'+p.name,p)
put('producer.json',B/'udm37-specified-number-run-v2/encoded/producer.json')
# Retain bounded development command journals without inflating file count.
archive=io.BytesIO();commands=0
with tarfile.open(fileobj=archive,mode='w') as tar:
 for glob in ['udm37-specified-number-kernel-v*','udm37-specified-number-guard-v*']:
  for d in sorted(B.glob(glob)):
   for p in sorted(d.glob('command-*.*')):
    raw=p.read_bytes();info=tarfile.TarInfo(d.name+'/'+p.name);info.size=len(raw);info.mtime=0;tar.addfile(info,io.BytesIO(raw));commands+=p.suffix=='.json'
raw=archive.getvalue();(S/'development.tar.gz').write_bytes(gzip.compress(raw,mtime=0));files['development.tar']={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw),'gzip':'saved/development.tar.gz'}
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
source=['WRF/dyn_em/solve_em.F','WRF/share/input_wrf.F','WRF/share/output_wrf.F','WRF/share/module_bc.F','WRF/dyn_em/module_bc_em.F','WRF/dyn_em/module_em.F','WRF/dyn_em/module_big_step_utilities_em.F','WRF/phys/module_mp_udm.F','WRF/phys/module_microphysics_driver.F','WRF/phys/module_ra_rrtmgp.F','WRF/Registry/Registry.EM_COMMON','WRF/test/rrtmgp/convert_udm_specified.py','WRF/test/rrtmgp/test_udm_dry_number_boundary.py','validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc']
identity={'base_commit':'d0058087c8d6b27e9c2b7dde2c4030543cacdd83','base_tree':'90d140489b04ac0346f26137823e8a538c920250','current_sources':{n:pin(R/n) for n in source},'files':files,'development_kernel_guard_command_records':commands,'large_raw_histories':'content-pinned in saved analysis; not committed or reread by stdlib CI','production_accepted':False}
command_tar=io.BytesIO()
with tarfile.open(fileobj=command_tar,mode='w') as tar:
 for n,row in files.items():
  if '/command-' in n:
   path=P/row['gzip'];raw=gzip.decompress(path.read_bytes());item=tarfile.TarInfo(n);item.size=len(raw);item.mtime=0;tar.addfile(item,io.BytesIO(raw));path.unlink();row.pop('gzip');row.update(archive='saved/commands.tar.gz',member=n)
(S/'commands.tar.gz').write_bytes(gzip.compress(command_tar.getvalue(),mtime=0))
for d in sorted(S.rglob('*'),key=lambda p:len(p.parts),reverse=True):
 if d.is_dir() and not any(d.iterdir()):d.rmdir()
(P/'identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('DEPOSITED',len(files),'entries')
