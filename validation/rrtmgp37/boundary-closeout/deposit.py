#!/usr/bin/env python3
from pathlib import Path
import gzip,hashlib,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;S=P/'saved';S.mkdir(exist_ok=False);payload={}
def put(n,p):payload[n]=p.read_bytes()
put('analysis.json',B/'udm37-boundary-closeout-analysis-v1/analysis.json')
for directory,key in [('udm37-boundary-closeout-probe-build-v1','build'),('udm37-boundary-closeout-host-v1','host'),('udm37-boundary-closeout-halo-v1','halo')]:
 d=B/directory;put(key+'/receipt.json',d/'receipt.json')
 for pat in ['command-*.*','*/namelist.input','*/radiation_iofields.txt']:
  for p in sorted(d.glob(pat)):put(key+'/'+str(p.relative_to(d)),p)
for n in ['module_bc_probe.F','solve_em_probe.F']:put('build/'+n,B/'udm37-boundary-closeout-probe-build-v1'/n)
put('build/probe.f90',P/'probe.f90');put('host/boundary-closeout.txt',B/'udm37-boundary-closeout-host-v1/host/boundary-closeout.txt');put('halo/common_halo.f90',P/'common_halo.f90')
buf=io.BytesIO();files={}
with tarfile.open(fileobj=buf,mode='w') as t:
 for n,raw in sorted(payload.items()):
  info=tarfile.TarInfo(n);info.size=len(raw);info.mtime=0;t.addfile(info,io.BytesIO(raw));files[n]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
p=S/'evidence.tar.gz';p.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
names=['WRF/dyn_em/solve_em.F','WRF/share/module_bc.F','WRF/dyn_em/module_bc_em.F','WRF/phys/module_mp_udm.F','WRF/phys/module_ra_rrtmgp.F','WRF/share/input_wrf.F','WRF/share/output_wrf.F','WRF/Registry/Registry.EM_COMMON','WRF/test/rrtmgp/convert_udm_specified.py','validation/rrtmgp37/restart-first-step/result.json','validation/rrtmgp37/research-policy-contract/closure-conditions.json','validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc']
identity={'base_commit':'553df58f4f0cb8c48f9cdb68843094bb9433d0c4','base_tree':'f6ffe201b3bd33479fa3a79155d2ef9d967d4d64','current_sources':{n:pin(R/n) for n in names},'archive':pin(p),'files':files,'raw_history_scope':'675 arrays decoded locally; saved replay verifies their hash inventory and bounded operands, not large raw NetCDF elements','production_accepted':False}
(P/'identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('CLOSEOUT_DEPOSITED',len(files),'entries',p.stat().st_size,'compressed bytes')
