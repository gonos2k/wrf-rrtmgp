#!/usr/bin/env python3
"""Freeze bounded actual witnesses and command journals; pin large histories."""
from pathlib import Path
import gzip,hashlib,io,json,struct,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;S=P/'saved';S.mkdir(exist_ok=True)
payload={}
def put(n,p):payload[n]=p.read_bytes()
put('analysis.json',B/'udm37-restart-first-analysis-v1/analysis.json')
for directory,key in [('udm37-restart-first-fix-build-v2','build'),('udm37-restart-first-fix-run-v2','fixed'),('udm37-restart-first-probe-build-v1','probe_build'),('udm37-restart-first-probe-run-v1','probe'),('udm37-restart-first-ww-v2','native'),('udm37-restart-first-nonzero-host-v1','nonzero')]:
 d=B/directory;put(key+'/receipt.json',d/'receipt.json')
 for pat in ['command-*.*','*/namelist.input','*/radiation_iofields.txt']:
  for p in sorted(d.glob(pat)):put(key+'/'+str(p.relative_to(d)),p)
for n in ['replay.f90','inputs.bin']:put('native/'+n,B/'udm37-restart-first-ww-v2'/n)
for key,name in [('build','udm37-restart-first-fix-build-v2'),('probe_build','udm37-restart-first-probe-build-v1')]:
 put(key+'/compiled_solve.F',B/name/('solve_em_public.F' if key=='build' else 'solve_em_probe.F'))
for arm in ['continuous','restart']:
 for stage in ['r0-a00-entry','r1-a00-rk_prep']:
  name='probe-021540-'+stage
  source=B/'udm37-restart-first-probe-run-v1'/arm/(name+'.bin');raw=source.read_bytes();pos=0;parts=[]
  # Retain only initialized consumed fields; entry scratch is not causal evidence.
  keep={'u_2','v_2','w_2','t_2','ph_2','mu_2','mub','p','al','alb','qv','qnc','qnr','qnn'} if 'entry' in stage else {'ww'}
  while pos<len(raw):
   key,*shape=struct.unpack_from('<32s3i',raw,pos);count=shape[0]*shape[1]*shape[2];end=pos+44+count*4
   if key.rstrip().decode() in keep:parts.append(raw[pos:end])
   pos=end
  payload['witness/'+arm+'/'+name+'.bin']=b''.join(parts)
  put('witness/'+arm+'/'+name+'.txt',source.with_suffix('.txt'))
# Preserve excluded attempts explicitly, without qualifying them as success.
for name in ['udm37-restart-first-ww-v1','udm37-restart-first-fix-build-v1','udm37-restart-first-fix-run-v1']:
 d=B/name
 for pat in ['command-*.*','development-status.json','receipt.json','solve_em_public.F','replay.f90']:
  for p in sorted(d.glob(pat)):put('development/'+name+'/'+p.name,p)
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
files={};buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
 for n,raw in sorted(payload.items()):
  item=tarfile.TarInfo(n);item.size=len(raw);item.mtime=0;tar.addfile(item,io.BytesIO(raw));files[n]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
(S/'evidence.tar.gz').write_bytes(gzip.compress(buf.getvalue(),mtime=0))
sources=['WRF/dyn_em/solve_em.F','WRF/share/module_bc.F','WRF/share/input_wrf.F','WRF/share/output_wrf.F','WRF/dyn_em/module_big_step_utilities_em.F','WRF/dyn_em/module_em.F','WRF/dyn_em/module_bc_em.F','WRF/phys/module_mp_udm.F','WRF/phys/module_ra_rrtmgp.F','WRF/test/rrtmgp/convert_udm_specified.py','WRF/Registry/Registry.EM_COMMON','validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc','validation/rrtmgp37/research-policy-contract/closure-conditions.json']
identity={'base_commit':'3ad2efd1c3ca73bd43f0470c456f826a61736cd2','base_tree':'55574e5f43f162a83bde389ab6dff2ac070679d7','current_sources':{n:pin(R/n) for n in sources},'files':files,'archive':pin(S/'evidence.tar.gz'),'large_histories':'Full NetCDF files are content-pinned in analysis.json. Saved stdlib replay checks inventories and bounded raw witnesses, not every NetCDF element.','production_accepted':False}
(P/'identity.json').write_text(json.dumps(identity,indent=2)+'\n');print('RESTART_EVIDENCE_DEPOSITED',len(files),'entries',len(buf.getvalue()),'raw bytes')
