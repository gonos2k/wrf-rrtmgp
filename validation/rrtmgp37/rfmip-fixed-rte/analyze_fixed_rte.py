#!/usr/bin/env python3
"""Read-only decomposition of saved fixed-RTE outputs and strict-cell references."""
from __future__ import annotations
import argparse, gzip, hashlib, json, math, struct
from pathlib import Path

HERE=Path(__file__).resolve().parent
BASE=HERE
NLEV=61
STRICT_ATOL=1.0e-5
EXEC=BASE/'execution-v4/execution.json'
EXPECTED_EXEC_SHA='de63e764cf2bb4649b54ad444d2662f8c3b7e2013aa7ba7c17019c2634e998fc'

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def f32(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def read_flux(path, keys, expected_sha, expected_size):
 p=Path(path)
 raw=p.read_bytes()
 if len(raw)!=expected_size or sha(p)!=expected_sha:raise RuntimeError(f'flux pin mismatch: {p}')
 recbytes=8+2*NLEV*8
 if len(raw)!=len(keys)*recbytes:raise RuntimeError(f'flux geometry mismatch: {p}')
 out={}
 for i,k in enumerate(keys):
  off=i*recbytes; got=struct.unpack_from('<ii',raw,off)
  if got!=k:raise RuntimeError(f'flux key mismatch: {got} != {k}')
  vals=struct.unpack_from('<'+('d'*(2*NLEV)),raw,off+8)
  if not all(math.isfinite(v) for v in vals):raise RuntimeError(f'nonfinite flux in {p} {k}')
  out[k]={'up':vals[:NLEV],'down':vals[NLEV:]}
 return out
def read_gzip_stream(path, expected_sha, expected_size):
 p=Path(path)
 if sha(p)!=expected_sha:raise RuntimeError(f'compressed stream hash mismatch {p}')
 raw=gzip.decompress(p.read_bytes())
 if len(raw)!=expected_size:raise RuntimeError(f'decompressed stream size mismatch {p}')
 return raw
def metrics(vals):
 vals=list(vals)
 return {'n':len(vals),'min':min(vals),'max':max(vals),'mean':sum(vals)/len(vals),'mean_abs':sum(abs(x) for x in vals)/len(vals),'max_abs':max(abs(x) for x in vals),'rms':math.sqrt(sum(x*x for x in vals)/len(vals))}
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--output',type=Path,default=BASE/'fixed-rte-component-analysis.json')
 args=ap.parse_args()
 if sha(EXEC)!=EXPECTED_EXEC_SHA:raise RuntimeError('fixed-RTE terminal receipt pin mismatch')
 ex=json.loads(EXEC.read_text())
 if ex.get('status')!='PASS_SCOPED_FIXED_RTE_BASELINE_REPRODUCTION':raise RuntimeError('unexpected fixed-RTE terminal status')
 if ex.get('gas_optics_calls')!=0 or ex.get('model_forecasts')!=0 or ex.get('rte_calls_expected')!=40:raise RuntimeError('unexpected solver/model scope')
 if ex.get('strict_rfmip_gate_changed') is not False or ex.get('physical_accuracy_claim') is not False:raise RuntimeError('strict/accuracy scope changed')
 children=ex.get('children',[])
 if len(children)!=5 or any(c.get('returncode')!=0 or c.get('timed_out') or not c.get('reaped') for c in children):raise RuntimeError('terminal child completion mismatch')
 streams=json.loads((BASE/'inputs/source-subset-manifest.json').read_text())['streams']
 # Validate all 8 portable gzip streams and exact decompressed hashes/sizes.
 gzip_meta={};decompressed={}
 for name,item in streams.items():
  z=BASE/'inputs/streams'/f'{name}.bin.gz'
  gz_sha=sha(z); payload=read_gzip_stream(z,gz_sha,item['size_bytes'])
  if hashlib.sha256(payload).hexdigest()!=item['sha256'] or len(payload)!=item['size_bytes']:raise RuntimeError(f'input stream payload mismatch: {name}')
  decompressed[name]=payload;gzip_meta[name]={'gzip_sha256':gz_sha,'gzip_size_bytes':z.stat().st_size,'raw_sha256':item['sha256'],'raw_size_bytes':item['size_bytes']}
 # Check same source_post record bytes between the arms.
 if decompressed['current_source_post']!=decompressed['historical_source_post']:raise RuntimeError('shared source_post streams differ')
 keys=[tuple(map(int,s.split())) for s in (BASE/'inputs/profiles20.txt').read_text().splitlines()]
 if len(keys)!=20 or keys!=sorted(keys) or len(set(keys))!=20:raise RuntimeError('invalid 20-key roster')
 # Verify key order/layout and finiteness of input optics/source streams.
 for name,nval in [('current_optics',60*224*3),('historical_optics',60*224*3),('current_source_post',224),('historical_source_post',224)]:
  raw=decompressed[name]; rec=8+8*nval
  if len(raw)!=rec*20:raise RuntimeError(f'input layout mismatch {name}')
  for i,key in enumerate(keys):
   off=i*rec
   if struct.unpack_from('<ii',raw,off)!=key:raise RuntimeError(f'input key mismatch {name}/{key}')
   for (x,) in struct.iter_unpack('<d',raw[off+8:off+rec]):
    if not math.isfinite(x):raise RuntimeError(f'nonfinite input {name}/{key}')
 # Load saved baseline and actual replay flux streams.
 ref_streams={n:read_flux(BASE/'references'/f'{n}.bin',keys,sha(BASE/'references'/f'{n}.bin'),(8+2*NLEV*8)*20) for n in ('current_solver','current_written','historical_solver','historical_written')}
 outputs={n:read_flux(BASE/'execution-v4'/f'replay_{n}.bin',keys,ex['outputs'][n]['sha256'],ex['outputs'][n]['size_bytes']) for n in ('current_solver','current_written','historical_solver','historical_written')}
 # Reconfirm identity gate and capture/written equivalence from actual bytes.
 identity=[]
 for k in keys:
  identity.append(outputs['current_solver'][k]==ref_streams['current_solver'][k] and outputs['current_written'][k]==ref_streams['current_written'][k])
 if not all(identity):raise RuntimeError('current-optics exact saved-baseline gate failed')
 same_written={arm:(outputs[f'{arm}_solver']==outputs[f'{arm}_written'] and ref_streams[f'{arm}_solver']==ref_streams[f'{arm}_written']) for arm in ('current','historical')}
 if not all(same_written.values()):raise RuntimeError('solver/written streams differ unexpectedly in this subset')
 # Component decomposition at each profile, output level, and flux direction.
 values={c:[] for c in ('optics','post_optics_residual','total','closure')}
 for k in keys:
  for direction in ('up','down'):
   for lev in range(NLEV):
    cur=outputs['current_solver'][k][direction][lev]
    curhist=outputs['historical_solver'][k][direction][lev]
    savedhist=ref_streams['historical_solver'][k][direction][lev]
    dopt=curhist-cur
    dpost=savedhist-curhist
    dtotal=savedhist-cur
    closure=dopt+dpost-dtotal
    values['optics'].append(dopt);values['post_optics_residual'].append(dpost);values['total'].append(dtotal);values['closure'].append(closure)
 # Validate 21 strict cells against source residual metadata, preserve the published f32 reference.
 residual=json.loads((BASE/'references/original-strict-residual-details.json').read_text())
 rows=[]; original_count=0; replay_cast_fail_count=0; replay_raw_fail_count=0
 for r in residual['residual_cells']:
  e0,s0,l0=r['index0_experiment_site_level']; key=(e0+1,s0+1)
  variable=r['variable'].lower(); direction={'rsd':'down','rsu':'up'}[variable]
  idx=int(l0)
  if key not in outputs['current_solver'] or not 0<=idx<NLEV:raise RuntimeError(f'strict key outside selected records: {r}')
  cur=outputs['current_solver'][key][direction][idx]
  histfix=outputs['historical_solver'][key][direction][idx]
  savhist=ref_streams['historical_solver'][key][direction][idx]
  ref=float(r['reference_stored_W_m2']); histstored=float(r['historical_stored_W_m2'])
  hround=r.get('historical_rounding',{})
  histpre=float(hround['prewrite_W_m2']) if 'prewrite_W_m2' in hround else savhist
  if 'prewrite_W_m2' in hround and savhist!=histpre:raise RuntimeError(f'saved historical solver row failed exact prewrite mapping {key}/{variable}/{idx}: {savhist} != {histpre}')
  if f32(savhist)!=histstored:raise RuntimeError(f'saved historical double does not cast to stored float32 at {key}/{variable}/{idx}')
  if histstored==ref or abs(histstored-ref)<=STRICT_ATOL:raise RuntimeError('original strict failure unexpectedly no longer fails')
  original_count+=1
  dopt=histfix-cur; dpost=savhist-histfix; dtotal=savhist-cur
  closure=dopt+dpost-dtotal
  curerr=cur-ref; histerr=histfix-ref
  curcast=f32(cur); histcast=f32(histfix)
  curcast_err=curcast-ref; histcast_err=histcast-ref
  if abs(curcast_err)>STRICT_ATOL: replay_cast_fail_count+=1
  if abs(histerr)>STRICT_ATOL: replay_raw_fail_count+=1
  interval=hround.get('reference_float32_rounding_interval_W_m2')
  rows.append({'variable':r['variable'].upper(),'profile_one_based':list(key),'level_index0':idx,
    'reference_published_float32_W_m2':ref,'original_historical_stored_float32_W_m2':histstored,
    'original_historical_stored_minus_reference_W_m2':histstored-ref,
    'original_historical_strict_margin_over_atol_W_m2':abs(histstored-ref)-STRICT_ATOL,
    'original_historical_prewrite_double_W_m2':histpre,
    'original_historical_prewrite_source':'saved_historical_rounding_record' if 'prewrite_W_m2' in hround else 'new_v3_saved_historical_capture',
    'original_historical_prewrite_minus_reference_W_m2':histpre-ref,
    'current_RTE_current_optics_W_m2':cur,'current_RTE_historical_optics_W_m2':histfix,
    'saved_historical_solver_W_m2':savhist,
    'delta_optics_historical_minus_current_RTE_W_m2':dopt,
    'delta_post_optics_residual_saved_historical_minus_current_RTE_W_m2':dpost,
    'delta_total_saved_historical_minus_current_RTE_current_optics_W_m2':dtotal,
    'component_sum_closure_W_m2':closure,
    'current_RTE_historical_optics_minus_reference_W_m2':histerr,
    'current_RTE_historical_optics_strict_margin_over_atol_W_m2':abs(histerr)-STRICT_ATOL,
    'current_RTE_historical_optics_cast_float32_W_m2':histcast,
    'current_RTE_historical_optics_cast_minus_reference_W_m2':histcast_err,
    'cast_inside_historical_reference_rounding_interval':(interval[0] <= histcast <= interval[1]) if interval else None,
    'current_RTE_current_optics_minus_reference_W_m2':curerr,
    'current_RTE_current_optics_cast_float32_W_m2':curcast,
    'current_RTE_current_optics_cast_minus_reference_W_m2':curcast_err})
 if len(rows)!=21:raise RuntimeError('strict residual cell count changed')
 summary={
  'schema':'RFMIP_FIXED_RTE_COMPONENT_ANALYSIS_V1','status':'PASS_SCOPED_DECOMPOSITION_NOT_STRICT_PASS',
  'scope':'Read-only arithmetic on terminal fixed-RTE outputs and saved capture streams. No solver/build/model executed by this analyzer.',
  'execution':{'path':'execution-v4/execution.json','sha256':sha(EXEC),'status':ex['status'],'compile_link_rte_children':[(c['label'],c['returncode'],c['reaped'],c['timed_out']) for c in children],'rte_calls':ex['rte_calls_expected'],'gas_optics_calls':ex['gas_optics_calls'],'forecast_calls':ex['model_forecasts'],'current_identity_gate':'20/20 current optics replay records bitwise equal saved current-old-solar solver and written streams','historical_arm_saved_comparison':'0/20 historical replay records bitwise equal saved historical solver and written stream; descriptive only'},
  'pins':{'subset_manifest':{'path':'inputs/source-subset-manifest.json','sha256':sha(BASE/'inputs/source-subset-manifest.json')},'profile_roster':{'path':'inputs/profiles20.txt','sha256':sha(BASE/'inputs/profiles20.txt')},'strict_reference_details':{'path':'references/original-strict-residual-details.json','sha256':sha(BASE/'references/original-strict-residual-details.json')},'subset_gzip_streams':gzip_meta,'replay_outputs':{n:{'sha256':sha(BASE/'execution-v4'/f'replay_{n}.bin'),'size_bytes':(BASE/'execution-v4'/f'replay_{n}.bin').stat().st_size} for n in outputs}},
  'profile_count':20,'flux_levels':NLEV,'directions':['up','down'],'solver_written_saved_streams_bitwise_equal':same_written,
  'component_definitions':{'delta_optics':'current-RTE(historical saved optics) minus current-RTE(current saved optics)','delta_post_optics_residual':'saved historical solver flux minus current-RTE(historical saved optics)','delta_total':'saved historical solver flux minus current-RTE(current saved optics)','closure':'delta_optics + delta_post_optics_residual - delta_total'},
  'all_level_component_metrics':{k:metrics(v) for k,v in values.items()},
  'strict_failure_cells':{'count':len(rows),'by_variable':{v:sum(r['variable']==v for r in rows) for v in ('RSD','RSU')},'original_historical_stored_failures':original_count,'threshold_atol_W_m2':STRICT_ATOL,'rtol':0,'threshold_changed':False,'rows':rows,'fixedRTE_historical_optics_cast_exceeding_threshold_diagnostic_only':replay_cast_fail_count,'fixedRTE_historical_optics_raw_double_exceeding_threshold_diagnostic_only':replay_raw_fail_count},
  'spectral_mapping_limit':'The three coefficient files share band-edge and gpoint-limit metadata; this does not establish per-gpoint physical equivalence across coefficient generations. The fixed-RTE result is an index-ordered optical-input counterfactual under the current RTE.',
  'interpretation_limits':['The historical-optics arm under the current RTE is a controlled replay, not the historical solver.','The post-optics residual includes solver-version/transport differences and any remaining capture-to-replay convention differences; it is not atmospheric transport.','The 21-cell published strict RFMIP failures remain preserved; this component analysis does not change the strict gate or establish physical accuracy.']}
 out=args.output;out.write_text(json.dumps(summary,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':summary['status'],'analysis_sha256':sha(out),'component_metrics':summary['all_level_component_metrics'],'strict_hist_replay_cast_over_threshold':replay_cast_fail_count,'strict_hist_replay_raw_over_threshold':replay_raw_fail_count},indent=2))
if __name__=='__main__':main()
