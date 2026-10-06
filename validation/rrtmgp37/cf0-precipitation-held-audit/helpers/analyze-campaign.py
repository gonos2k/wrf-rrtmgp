#!/usr/bin/env python3
"""Read-only analysis of the already completed eight-call CF0 campaign."""
from pathlib import Path
import hashlib, json, math
import numpy as np
ROOT=Path(__file__).resolve().parents[2]
CAM=ROOT/'build/udm37-cf0-precip-campaign-v5'
BASE=ROOT/'build/udm37-cf0-precip-original-baseline-v1/runs-v2'
PROP=ROOT/'build/udm37-cf0-precip-audit-patch-proposal-v2'
OUT=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(p):
 p=Path(p).resolve(strict=True);return {'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def read_result(path):
 lines=Path(path).read_text(encoding='ascii').splitlines()
 if len(lines)<2 or lines[0].strip()!='RRTMGP_RESULT_V1':raise ValueError(f'bad result header: {path}')
 h=lines[1].split(); phase,nc,nl=h[0],int(h[1]),int(h[2]); data={}; order=[];i=2
 while i<len(lines):
  if not lines[i].strip():i+=1;continue
  h=lines[i].split();i+=1; name=h[0];shape=tuple(map(int,h[1:]));n=math.prod(shape); vals=[]
  while len(vals)<n:
   vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split());i+=1
  if name in data or len(vals)!=n:raise ValueError(f'malformed section {name}: {path}')
  a=np.asarray(vals,dtype=np.float64).reshape(shape,order='F')
  if not np.isfinite(a).all():raise ValueError(f'nonfinite section {name}: {path}')
  data[name]=a;order.append(name)
 return phase,nc,nl,data,order
def arrstats(a):
 return {'shape':list(a.shape),'min':float(a.min()),'max':float(a.max()),'sum_across_all_layers_and_bands':float(a.sum()),'nonzero_elements':int(np.count_nonzero(a))}
def section_diff(old,new):
 d=new-old;ix=np.unravel_index(np.abs(d).argmax(),d.shape)
 return {'changed_elements':int(np.count_nonzero(d)),'max_abs':float(np.max(np.abs(d))),'max_abs_index_zero_based':list(map(int,ix)),'old_at_max':float(old[ix]),'new_at_max':float(new[ix])}
execj=json.loads((CAM/'execution.json').read_text()); plan=json.loads((CAM/'invocation-plan.json').read_text()); basej=json.loads((BASE/'execution.json').read_text())
if execj['status']!='PASS_ALL_EIGHT_CALLS' or execj['calls_completed']!=8 or execj['solver_invocations']!=8:raise ValueError('campaign receipt is not the recorded complete 8-call PASS')
base_by={(c['phase'],c['species']):c for c in basej['cases']}
calls={c['case_id']:c for c in execj['calls']}; planby={c['case_id']:c for c in plan['calls']}
zero=[];positive=[]
for ident in plan['order']:
 c=calls[ident]; pc=planby[ident]
 op=pin(c['output']);
 if op['sha256']!=c['generated_output_pin']['sha256'] or op['size_bytes']!=c['generated_output_pin']['size_bytes']:raise ValueError(f'output drift {ident}')
 if ident.endswith('.zero'):
  if c['validation']['status']!='ZERO_SIDECAR_EXACT_DOUBLE_ORACLE_BYTE_PASS' or op['sha256']!=c['validation']['baseline_sha256']:raise ValueError(f'zero-byte contract failed {ident}')
  zero.append({'case_id':ident,'output':op,'oracle_sha256':c['validation']['baseline_sha256'],'byte_identical':True})
  continue
 species,phase=ident.split('.')[0].split('-');phase=phase.upper()
 oldcase=base_by[(phase,species)]; baseline=oldcase['exact_double_zero_sidecar_oracle']['result']
 old=read_result(baseline['path']); cur=read_result(c['output'])
 if old[:3]!=cur[:3]:raise ValueError(f'positive output dimensions/phase differ {ident}')
 _,nc,nl,od,oo=old;_,_,_,nd,no=cur
 mut={'LW':{'TOTAL_TAU','UP','DN','HR'},'SW':{'TOTAL_TAU','TOTAL_SSA','TOTAL_G','UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF'}}[phase]
 unchanged=[]
 for name in oo:
  if name not in mut:
   if not np.array_equal(od[name],nd[name]):raise ValueError(f'undeclared result change {ident}/{name}')
   unchanged.append(name)
 d={name:section_diff(od[name],nd[name]) for name in mut}
 # Surface is interface 1; TOA is final interface, as asserted by the standalone fixture.
 if phase=='LW':
  boundary={'surface_down_flux_delta':float(nd['DN'][0,0,0]-od['DN'][0,0,0]),'toa_up_flux_delta':float(nd['UP'][0,-1,0]-od['UP'][0,-1,0]),'max_abs_native_heating_delta':float(np.max(np.abs((nd['HR']-od['HR'])[:,:39,:]))),'max_abs_extension_heating_delta':float(np.max(np.abs((nd['HR']-od['HR'])[:,39:,:])))}
  added={'AUDIT_EXTRA_PRECIP_TAU':arrstats(nd['AUDIT_EXTRA_PRECIP_TAU'])}
 else:
  boundary={'surface_down_flux_delta':float(nd['DN'][0,0,0]-od['DN'][0,0,0]),'surface_net_down_flux_delta':float((nd['DN'][0,0,0]-nd['UP'][0,0,0])-(od['DN'][0,0,0]-od['UP'][0,0,0])),'toa_up_flux_delta':float(nd['UP'][0,-1,0]-od['UP'][0,-1,0]),'max_abs_native_heating_delta':float(np.max(np.abs((nd['HR']-od['HR'])[:,:39,:]))),'max_abs_extension_heating_delta':float(np.max(np.abs((nd['HR']-od['HR'])[:,39:,:])))}
  added={k:arrstats(nd[k]) for k in ('AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA')}
 added['AUDIT_EXTRA_PRECIP_TAU']['native_layer_band_sum']=float(nd['AUDIT_EXTRA_PRECIP_TAU'][:,:39,:].sum())
 added['AUDIT_EXTRA_PRECIP_TAU']['extension_layer_band_sum']=float(nd['AUDIT_EXTRA_PRECIP_TAU'][:,39:,:].sum())
 positive.append({'case_id':ident,'phase':phase,'species':species,'output':op,'baseline_result':pin(baseline['path']),'output_validation':c['validation']['status'],'mutated_section_differences':d,'unchanged_original_sections':unchanged,'boundary_flux_and_heating_deltas':boundary,'added_audit_optics':added,'input_capture':pc['raw'],'sidecar':pc['sidecar'],'native_layers':pc['native_layers'],'engine_layers':pc['engine_layers'],'positive_native_layers':pc.get('positive_native_layers',0)})
layer=json.loads((PROP/'captured-layer-audit.json').read_text())
rawpaths={}
for row in layer['captures']:
 rawpaths[f"{row['species']}-{row['phase']}"]={'raw_capture_path':row['capture_path'],'raw_capture_sha256':row['capture_sha256'],'anchor_ij':[row['i'],row['j']],'positive_native_layers':row['raw_path_exact_positive_layers'],'raw_precip_path_sum_g_m2':row['raw_path_sum_g_m2'],'radius_fallback_runs_at_cf_zero':False}
result={'analysis_script':pin(__file__),'schema':'udm-cf0-precip-campaign-analysis-v1','scope':'Read-only posthoc analysis; exactly the eight already recorded standalone reference calls, zero additional solver invocations.','campaign_status':execj['status'],'campaign_solver_invocations':execj['solver_invocations'],'postflight':{'immutable_pin_count':execj['postflight']['immutable_pin_count'],'immutable_pins_unchanged':execj['postflight']['immutable_pins_unchanged'],'generated_outputs_unchanged':execj['postflight']['generated_outputs_unchanged'],'runtime_library_count':execj['postflight']['runtime_closure']['count'],'runtime_closure_pins_sha256':hashlib.sha256(json.dumps(execj['postflight']['runtime_closure']['resolved_libraries'],sort_keys=True,separators=(',',':')).encode()).hexdigest()},'execution_receipt':pin(CAM/'execution.json'),'invocation_plan':pin(CAM/'invocation-plan.json'),'build_receipt':pin(ROOT/'build/udm37-cf0-precip-patch-build-v1/build-receipt.json'),'proposal_status':pin(PROP/'proposal-status.json'),'original_baseline_receipt':pin(BASE/'execution.json'),'zero_controls':zero,'positive_cases':positive,'raw_capture_path_context':rawpaths,'interpretation_limits':['The four zero-sidecar result files are byte-identical to the saved exact double-precision sidecar-free oracle for the corresponding held column and phase. This is a narrow compatibility control, not a forecast result.','Positive calls are prescribed conditional-occurrence-one radiative sensitivities using selected held columns and saved precipitation path proxies; they do not establish cloud occurrence, independent optical truth, or forecast error.','Reported optical-depth sums are unweighted sums over layer-band elements, not a vertically integrated physical path or a mass budget.','Flux and heating deltas are differences versus each exact saved double-reference output. Surface is interface 1 and TOA the final interface. These changes are not accuracy judgments.','The experiment isolates rain/snow precipitation additions at held cloud-fraction-zero points. It does not establish a domain-wide correction, all hydrometeor species, or operational benefit.']}
# Pin the source script itself after its contents are stable (receipt gets script hash on final invocation).
outpath=OUT/'analysis.json'; outpath.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
print(outpath)
