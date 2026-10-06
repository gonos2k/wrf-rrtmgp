#!/usr/bin/env python3
"""Round-trip synthetic LW/SW audit results through the audit-capable serialized reader."""
import json,tempfile
from pathlib import Path
import numpy as np
from continue_six import load_base,plan

def write_result(path,r):
 lines=['RRTMGP_RESULT_V1',f"{r['phase']} {r['nc']} {r['nl']}"]
 for name,a in r['sections'].items():
  lines.append(name+' '+' '.join(str(x) for x in a.shape))
  vals=np.asarray(a,dtype=np.float64).ravel(order='F')
  for i in range(0,len(vals),5): lines.append(' '.join(f'{x:.17e}' for x in vals[i:i+5]))
 Path(path).write_text('\n'.join(lines)+'\n')

def synthetic(m,c):
 oldplan=json.loads((m.HERE.parent/'udm37-cf0-material-anchor-runtime-v1/plan.json').read_text())
 original=next(x for x in oldplan['cases'] if x['call_id']==c['call_id'])
 base=m.read_result(original['historical_reference']['path']); _,phase,nc,nl,fields=m.read_input(c['input']['path']); nb,ng=(16,128) if phase=='LW' else (14,112)
 r={'phase':phase,'nc':nc,'nl':nl,'sections':{k:v.copy() for k,v in base['sections'].items()}}
 audit={'AUDIT_EXTRA_PRECIP_TAU'} if phase=='LW' else {'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA'}
 for key in audit:
  if key=='AUDIT_DIRECT_PREDELTA': r['sections'][key]=np.zeros((nc,nl+1,1))
  elif key.endswith('_SSA') or key.endswith('_G') or key.endswith('_TAU'): r['sections'][key]=np.zeros((nc,nl,nb))
  else: r['sections'][key]=np.zeros((nc,nl,nb))
 decoded=m.import_module(m.VALIDATOR,'continuation_test_sidecar').decode(Path(c['sidecar']['path']).read_text()); _,_,nn,_,_,rain,snow=decoded
 for k in range(nn):
  if rain[0][k]>0 or snow[0][k]>0:
   r['sections']['AUDIT_EXTRA_PRECIP_TAU'][0,k,0]=1.e-6
   if phase=='SW':
    r['sections']['AUDIT_EXTRA_PRECIP_TAU_RAW'][0,k,0]=1.e-6
    r['sections']['AUDIT_EXTRA_PRECIP_SSA'][0,k,0]=0.8
    r['sections']['AUDIT_EXTRA_PRECIP_G'][0,k,0]=0.15
 limits=m.band_gpoint_limits(phase,fields,nb,ng); et=m.expand_bands(r['sections']['AUDIT_EXTRA_PRECIP_TAU'],limits,ng); b=base['sections']
 r['sections']['TOTAL_TAU']=b['TOTAL_TAU']+et
 if phase=='SW':
  es=m.expand_bands(r['sections']['AUDIT_EXTRA_PRECIP_SSA'],limits,ng);eg=m.expand_bands(r['sections']['AUDIT_EXTRA_PRECIP_G'],limits,ng)
  scatter=b['TOTAL_TAU']*b['TOTAL_SSA']+et*es; gm=b['TOTAL_TAU']*b['TOTAL_SSA']*b['TOTAL_G']+et*es*eg
  r['sections']['TOTAL_SSA']=scatter/np.maximum(3*np.finfo(float).tiny,r['sections']['TOTAL_TAU'])
  r['sections']['TOTAL_G']=gm/np.maximum(3*np.finfo(float).tiny,scatter)
 return original,base,r
m=load_base(); old_plan=json.loads((m.HERE/'plan.json').read_text()); selected=[next(c for c in old_plan['cases'] if c['call_id']=='winter_native_cu-lw-rain-increment'),next(c for c in plan()['cases'] if c['call_id']=='material_cf0_snow_low_cloud-sw-snow-increment')]
count=0; rejected=0
with tempfile.TemporaryDirectory(prefix='cf0-reader-roundtrip-') as td:
 for c in selected:
  oc,base,syn=synthetic(m,c); path=Path(td)/(c['phase']+'.result');write_result(path,syn);parsed=m.read_result(path)
  assert set(parsed['sections'])==set(syn['sections']) and parsed['phase']==syn['phase'] and parsed['nl']==syn['nl']
  assert m.positive_validate(oc,parsed,base)['audit_tau_max']>0
  bad={**parsed,'sections':{k:a.copy() for k,a in parsed['sections'].items()}};bad['sections']['PREPARED_TAU'][0,0,0]+=1e-6
  try: m.positive_validate(oc,bad,base);raise AssertionError('held component mutation passed')
  except ValueError: rejected+=1
  bad={**parsed,'sections':{k:a.copy() for k,a in parsed['sections'].items()}};bad['sections']['TOTAL_TAU'][0,0,0]+=1e-5
  try: m.positive_validate(oc,bad,base);raise AssertionError('moment mutation passed')
  except ValueError: rejected+=1
  count+=1
obj={'schema':'cf0-material-anchor-serialized-reader-controls-v1','status':'PASS_NO_SOLVER','serialized_fixture_count':count,'mutation_rejections':rejected,'phases':['LW','SW'],'formats':['V10','V9'],'solver_invocations':0}
receipt=Path(__file__).resolve().parent/'serialized-reader-controls.json'
if receipt.exists(): raise RuntimeError('refusing to overwrite offline control receipt')
receipt.write_text(json.dumps(obj,sort_keys=True,indent=2)+'\n')
print(json.dumps(obj,sort_keys=True))
