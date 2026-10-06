#!/usr/bin/env python3
"""Saved-array join only. Never calls the opacity reconstruction or a solver."""
from pathlib import Path
import hashlib, importlib.util, json, math, sys
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
BASE=Path(__file__).resolve().parent
PLAN_SHA="81b64b14eb6aa648e33b6f9e7e17262c1e8422f0a2aebdec7da34060d22d24f5"
def digest(p): return hashlib.sha256(p.read_bytes()).hexdigest()
def verify(r):
 p=ROOT/r['path']
 if p.is_symlink() or not p.is_file() or p.stat().st_size!=r['size_bytes'] or digest(p)!=r['sha256']:raise ValueError('pin mismatch '+str(p))
 return p
p=BASE/'plan.json'
if digest(p)!=PLAN_SHA:raise ValueError('plan changed')
plan=json.loads(p.read_text());files={k:verify(v) for k,v in plan['pins'].items()}
execution=json.loads(files['normal_execution'].read_text())
if execution['actual_child_return_code']!=0:raise ValueError('normal point did not complete')
capture=json.loads(files['production_execution'].read_text())
records=capture['arms']['OFF']['captures']
matching=[r for r in records if r['files']['input']['sha256']==plan['pins']['input']['sha256'] and r['files']['result']['sha256']==plan['pins']['production_result']['sha256']]
if len(matching)!=1 or matching[0]['step']!=721 or matching[0]['phase']!='LW':raise ValueError('actual same-call capture not unique')
construction=json.loads(files['construction'].read_text());cr=json.loads(files['construction_receipt'].read_text())
if cr['construction_sha256']!=plan['pins']['construction']['sha256'] or construction['source_pins']['input']['sha256']!=plan['pins']['input']['sha256']:raise ValueError('construction/input join mismatch')
case=construction['cases'][0]
if len(construction['cases'])!=1 or case['case_id']!='normal-n2-absent':raise ValueError('wrong carrier')
sys.dont_write_bytecode=True
spec=importlib.util.spec_from_file_location('saved_stats_only',files['statistics_helper']);stats=importlib.util.module_from_spec(spec);spec.loader.exec_module(stats)
sys.path.insert(0,str(files['comparator'].parent))
from compare_column_replay import read_result
actual=read_result(files['production_result'])
if (actual['phase'],actual['nc'],actual['nl'])!=('LW',1,45):raise ValueError('wrong WRF result shape')
d=np.asarray(case['dry_column_molecule_cm2'],dtype=np.float64);tau=np.asarray(case['tau_point'],dtype=np.float64)
sections=actual['sections'];dry=sections['GAS_COL_DRY']
if dry.shape!=(1,45,1):raise ValueError('wrong dry shape')
result={'schema':'UDM37_NORMAL_PRODUCTION_SAVED_JOIN_V1','status':'DIAGNOSTIC_COMPLETE_NO_NUMERICAL_VERDICT','plan_sha256':PLAN_SHA,'same_call_join_exact':True,'production_source_head':plan['context']['source_head'],'dry':stats.summarize_dry_column(d,dry[0,:,0]),'tau':{},'new_point_RTE_model_compile':0,'scope_limit':plan['scope_limit']}
for name in ['GAS_TAU_RAW','GAS_TAU']:
 target=sections[name]
 if target.shape!=(1,45,128):raise ValueError('wrong tau shape')
 full=stats.summarize_pair(tau,target[0]);result['tau'][name]={'all45':full}
 for label, span in [('native32',slice(0,32)),('extension13',slice(32,45))]:
  signed=np.asarray(full['signed_residual'])[span]; t=target[0,span]
  rel=np.divide(signed,t,out=np.zeros_like(signed),where=t!=0)
  ulps=np.asarray(full['signed_ordered_binary64_ulp_delta'],dtype=object)[span]
  result['tau'][name][label]={'summary':{'cells':int(signed.size),'max_absolute_residual':float(np.max(np.abs(signed))),'rms_residual':float(np.sqrt(np.mean(signed*signed))),'max_absolute_relative_residual_nonzero_target':float(np.max(np.abs(rel[t!=0]))) if np.any(t!=0) else None,'max_absolute_ordered_ulp_delta':max(abs(int(x)) for x in ulps.flat),'numerical_gate':'NONE_DIAGNOSTIC_ONLY'}}
for k,r in plan['pins'].items():verify(r)
with (BASE/'result.json').open('x') as f:json.dump(result,f,indent=2,allow_nan=False);f.write('\n')
print(json.dumps({'status':result['status'],'dry':result['dry']['summary'],'tau':{k:{a:b['summary'] for a,b in v.items()} for k,v in result['tau'].items()}}))
