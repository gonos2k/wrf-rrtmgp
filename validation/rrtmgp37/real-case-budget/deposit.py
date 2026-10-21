#!/usr/bin/env python3
"""Freeze raw reductions, generated read-only source, journals and decoded history pins."""
from pathlib import Path
import gzip,hashlib,io,json,tarfile
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;S=P/'saved';S.mkdir(exist_ok=True);payload={}
def put(n,p):payload[n]=p.read_bytes()
def pin(p):return {'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'bytes':p.stat().st_size}
for name in ['inventory.json','surface_domains.json']:put(name,B/'udm37-real-budget-analysis-v1'/name)
for directory,key in [('udm37-real-budget-build-v5','build'),('udm37-real-budget-host-v2','host')]:
 d=B/directory;put(key+'/receipt.json',d/'receipt.json')
 for pat in ['command-*.*','*/namelist.input','*/radiation_iofields.txt','*.F']:
  for p in sorted(d.glob(pat)):put(key+'/'+str(p.relative_to(d)),p)
put('build/probe.f90',B/'udm37-real-budget-build-v5/probe.f90');put('host/real-budget.txt',B/'udm37-real-budget-host-v2/host/real-budget.txt')
# Excluded development is retained separately. Only final v5/v2 contributes the final result.
for directory in ['udm37-real-budget-build-v1','udm37-real-budget-build-v2','udm37-real-budget-build-v3','udm37-real-budget-build-v4','udm37-real-budget-host-v1']:
 d=B/directory
 for pat in ['receipt.json','command-*.json','command-*.stderr']:
  for p in sorted(d.glob(pat)):put('development/'+directory+'/'+p.name,p)
files={};buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w') as tar:
 for n,raw in sorted(payload.items()):
  item=tarfile.TarInfo(n);item.size=len(raw);item.mtime=0;tar.addfile(item,io.BytesIO(raw));files[n]={'sha256':hashlib.sha256(raw).hexdigest(),'bytes':len(raw)}
f=S/'evidence.tar.gz';f.write_bytes(gzip.compress(buf.getvalue(),mtime=0))
names=['WRF/dyn_em/solve_em.F','WRF/dyn_em/module_em.F','WRF/dyn_em/module_big_step_utilities_em.F','WRF/phys/module_physics_addtendc.F','WRF/phys/module_surface_driver.F','WRF/share/module_model_constants.F','WRF/phys/module_ra_rrtmg_lw.F','WRF/phys/module_ra_rrtmg_sw.F','WRF/phys/module_ra_rrtmgp.F','WRF/phys/module_mp_udm.F','WRF/share/module_bc.F','WRF/dyn_em/module_first_rk_step_part2.F','validation/rrtmgp37/research-policy-contract/closure-conditions.json','validation/rrtmgp37/restart-first-step/result.json','validation/rrtmgp37/boundary-closeout/result.json','validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc']
i={'base_commit':'b9fff6ac543e5bd2ec1b6df9eedfabbe9d81f846','base_tree':'1c86c73bd21fb72030196e96348e3f13f507f73d','current_sources':{n:pin(R/n) for n in names},'files':files,'archive':pin(f),'large_history_scope':'NetCDF decoded locally; saved CI replay checks pinned inventories and actual reduced operands, not every raw NetCDF element','production_accepted':False}
(P/'identity.json').write_text(json.dumps(i,indent=2)+'\n');print('REAL_BUDGET_DEPOSITED',len(files),f.stat().st_size)
