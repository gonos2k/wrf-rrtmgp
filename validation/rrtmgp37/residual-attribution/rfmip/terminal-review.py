#!/usr/bin/env python3
"""Read-only original arrays/streams and pinned helper preflight; no numerical executable calls."""
from pathlib import Path
import csv,hashlib,json,runpy,struct
from datetime import datetime,timezone
import numpy as np
from netCDF4 import Dataset
ROOT=Path(__file__).resolve().parents[2]
HERE=Path(__file__).resolve().parent
TASK=ROOT/'build/udm37-rfmip-residual-next-diagnostic-v5'
RUN=TASK/'execution-v5'
EXPECTED_RECEIPT='88d2975310338bbec6b72280592dd9c1fc70742fc389842c7d04385fb68bbe3d'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def pin(p):
 p=Path(p);return {'path':str(p.relative_to(ROOT)),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def readvar(p,v):
 with Dataset(p) as ds:
  x=ds.variables[v];assert tuple(x.dimensions)==('expt','site','level')
  decoded=x[:];assert not np.ma.getmaskarray(decoded).any()
  x.set_auto_maskandscale(False);a=np.asarray(x[:]);assert a.shape==(18,100,61) and a.dtype==np.float32 and np.isfinite(a).all()
  return a.copy()
def stream(p,n,keys):
 data=p.read_bytes(); stride=8+8*n;assert len(data)==len(keys)*stride
 values={}
 for ix,k in enumerate(keys):
  off=ix*stride;assert struct.unpack_from('<ii',data,off)==k
  a=np.frombuffer(data,dtype='<f8',count=n,offset=off+8).copy();assert np.isfinite(a).all();values[k]=a
 return values
def eq(a,b):return a.dtype==b.dtype and a.shape==b.shape and a.tobytes()==b.tobytes()
def main():
 out=HERE/'review.json';assert not out.exists()
 receiptpath=RUN/'execution.json';assert sha(receiptpath)==EXPECTED_RECEIPT
 r=json.loads(receiptpath.read_text());assert r['status']=='COMPLETE_DIAGNOSTIC_NOT_STRICT_PASS'
 h=runpy.run_path(str(TASK/'run_diagnostic_once_v5.py'),run_name='independent_review_import')
 live=h['verify_pins']();assert live==r['pins_before']==r['pins_after'] and len(live)==62
 closure=h['runtime_libraries'](RUN/'build/rrtmgp_rfmip_sw_diag');assert len(closure)==47
 assert closure==r['diagnostic_runtime_libraries']==r['frozen_baseline_runtime_closure']==h['runtime_libraries'](h['BASE_EXE'])
 assert sha(RUN/'build/rrtmgp_rfmip_sw_diag')==r['diagnostic_executable_sha256']
 assert (RUN/'build/rrtmgp_rfmip_sw_diag').read_bytes()[:4]==b'\x7fELF'
 approval=json.loads((TASK/'root-approval-v5.json').read_text());assert approval=={'approved':True,'plan_sha256':h['PLAN_SHA'],'runner_sha256':sha(TASK/'run_diagnostic_once_v5.py'),'run_root':str(RUN),'max_solver_calls':2}
 for phase in ('compile','link'):
  assert r[phase]['returncode']==0 and not r[phase]['timed_out'];assert sha(RUN/'build'/f'{phase}.log')==r[phase]['log_sha256']
 assert [x['arm'] for x in r['calls']]==['current','old_solar'] and len(r['calls'])==2 and r['model_invocations']==2
 assert r['calls'][0]['end_epoch']<=r['calls'][1]['start_epoch']
 keys=[tuple(map(int,x.split())) for x in (TASK/'selected_profiles.txt').read_text().splitlines()]
 assert len(keys)==135 and keys==sorted(set(keys))
 rows=list(csv.DictReader((TASK/'failed_points.csv').open()));assert len(rows)==155
 captures={}; results={}; outputpins=[]
 with Dataset(h['INPUT']) as ds:
  tsi=np.asarray(ds['total_solar_irradiance'][:],dtype=np.float64)
  sza=np.asarray(ds['solar_zenith_angle'][:],dtype=np.float64)
 for call in r['calls']:
  arm=call['arm'];p=RUN/arm;assert call['returncode']==0 and not call['timed_out'] and call['post_process_pins_match']
  assert sha(p/'run.log')==call['log_sha256']
  assert (p/'input.nc').resolve()==h['INPUT'].resolve(); assert (p/'coeff.nc').resolve()==(h['CURRENT_COEFF'] if arm=='current' else h['OLD_COEFF']).resolve()
  assert sha(p/'profiles.txt')==h['SELECTOR_SHA']
  cap={stage:stream(p/f'diag_{stage}.bin',n,keys) for stage,n in [('source_pre',224),('source_post',224),('optics',40320),('flux_solver',122),('flux_written',122)]}
  for f in p.glob('diag_*.bin'):assert sha(f)==call['capture_hashes'][f.name];outputpins.append(pin(f))
  arrays={}; casts=0
  for var,offset in [('rsu',0),('rsd',61)]:
   filename=f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc';a=readvar(p/filename,var)
   ref=h['STAGE']/('control' if arm=='current' else 'old-solar-counterfactual')/filename
   assert eq(a,readvar(ref,var)) and sha(p/filename)==sha(ref)==call['output_bitwise_gate'][var]['sha256']
   for k in keys:
    e,s=k[0]-1,k[1]-1;assert eq(cap['flux_written'][k][offset:offset+61].astype(np.float32),a[e,s,:]);casts+=61
   arrays[var]=a;outputpins.append(pin(p/filename))
  assert casts==16470
  norms=[];day=0;night=0
  for k in keys:
   src=cap['source_pre'][k];post=cap['source_post'][k];target=float(tsi[k[1]-1]);denom=float(src.sum());assert target>0 and denom>0
   error=abs(float(post.sum())-target);tol=32*np.finfo(np.float64).eps*224*max(1.,abs(target),float(np.abs(post).sum()));assert error<=tol;norms.append(error)
   usecol=float(sza[k[1]-1])<90.-2.*np.spacing(90.)
   if usecol:assert eq(cap['flux_solver'][k],cap['flux_written'][k]);day+=1
   else:assert not np.any(cap['flux_written'][k]);night+=1
  assert max(norms)==call['broadband_tsi_diagnostic']['max_abs_post_sum_error']
  residual=[];under=over=outside=ties=0;ulps=[]
  strict={}
  for var in ('rsd','rsu'):
   filename=f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc';pub=readvar(h['PUBLISHED']/filename,var)
   strict[var]=int(np.count_nonzero(np.abs(arrays[var].astype(np.float64)-pub.astype(np.float64))>1e-5))
  for row in rows:
   var=row['variable'];e,s,k=(int(row[q]) for q in ('expt_index0','site_index0','level_index0'));key=(e+1,s+1)
   target=float(readvar(h['PUBLISHED']/f'{var}_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc',var)[e,s,k]);stored=float(arrays[var][e,s,k]);wp=float(cap['flux_written'][key][k+(61 if var=='rsd' else 0)])
   assert target>=0 and stored>=0
   ulp=abs(int(np.float32(stored).view(np.uint32))-int(np.float32(target).view(np.uint32)));ulps.append(ulp)
   lo=(float(np.nextafter(np.float32(target),np.float32(-np.inf)))+target)/2;hi=(target+float(np.nextafter(np.float32(target),np.float32(np.inf))))/2
   outside+=int(wp<lo or wp>hi);ties+=int(wp==lo or wp==hi)
   over+=int(abs(wp-target)>1e-5);under+=int(abs(wp-target)<=1e-5)
   residual.append({'variable':var,'expt_index0':e,'site_index0':s,'level_index0':k,'stored_minus_published':stored-target,'prewrite_minus_published':wp-target,'ulp':ulp,'outside_rounding_interval':bool(wp<lo or wp>hi)})
  if arm=='old_solar':assert strict=={'rsd':116,'rsu':39} and set(ulps)=={1} and outside==155 and over==99 and under==56 and ties==0
  results[arm]={'returncode':0,'full_output_whole_file_and_float32_baseline_parity':True,'output_shape':[18,100,61],'profile_cast_values_compared':casts,'profile_cast_exact':True,'selected_residuals':residual,'strict_full_array_failures':strict,'selected_stored_ulp_values':sorted(set(ulps)),'selected_wp_outside_published_rounding_interval':outside,'selected_wp_exact_rounding_ties':ties,'selected_wp_abs_error_over1e-5':over,'selected_wp_abs_error_not_over1e-5':under,'max_tsi_sum_error':max(norms),'captured_daylight_profiles':day,'captured_night_profiles':night}
  captures[arm]=cap
 cross={}
 for stage in captures['current']:
  count=sum(eq(captures['current'][stage][k],captures['old_solar'][stage][k]) for k in keys)
  mx=max(float(np.max(np.abs(captures['current'][stage][k]-captures['old_solar'][stage][k]))) for k in keys)
  cross[stage]={'bitwise_equal_profiles':count,'profiles':135,'max_abs_delta':mx}
  assert count==r['diagnostic_summary']['cross_arm'][stage]['bitwise_equal_profiles'] and mx==r['diagnostic_summary']['cross_arm'][stage]['max_abs_delta']
 assert cross['optics']['bitwise_equal_profiles']==135 and cross['optics']['max_abs_delta']==0 and cross['source_post']['bitwise_equal_profiles']==0
 assert sha(receiptpath)==EXPECTED_RECEIPT and h['verify_pins']()==live
 report={'schema':'rfmip-residual-diagnostic-terminal-independent-review-v1','created_utc':datetime.now(timezone.utc).isoformat(),'status':'PASS_SCOPED_DIAGNOSTIC_RECOMPUTATION_STRICT_REFERENCE_FAIL_PRESERVED','original_execution':pin(receiptpath),'root_approval':pin(TASK/'root-approval-v5.json'),'runner':pin(TASK/'run_diagnostic_once_v5.py'),'prebuild':pin(TASK/'prebuild-manifest-v5.json'),'counts':{'actual_original_driver_builds':1,'actual_original_compile_and_link_children':2,'actual_original_SW_reference_calls':2,'original_misnamed_model_invocations':2,'WRF_forecasts_in_this_diagnostic':0,'REAL_in_this_diagnostic':0,'new_invocations_by_reviewer':0,'cumulative_WRF_forecasts_root_reported':86,'cumulative_count_scope':'86 is root-provided separate forecast ledger state; these2standalone calls add0WRF.'},'integrity':{'input_pins':62,'unchanged_before_after':True,'runtime_closure':47,'exact_baseline_closure':True,'generated_executable':pin(RUN/'build/rrtmgp_rfmip_sw_diag'),'compile_link_RC0':True,'calls_RC0':True,'captured_binary_keys_and_finite_values':True,'auth_exact_plan_runner_root_budget':True},'arms':results,'cross_arm':cross,'output_pins':outputpins,'scientific_interpretation':['Both ordinary arm outputs exactly reproduce their own stage-v7 baseline; this is diagnostic instrumentation parity, not published accuracy.','Old-solar155strict failures persist, every stored residual exactly1float32ULP and every wp prewrite value outside published rounding interval; none lies exactly at a midpoint.','For99selectedcells wp absolute residual exceeds1e-5; for56wp residual doesnot exceed1e-5 while storedfloat32 residual does. Storage rounding changes threshold classification for those56; it doesnot establish a strict published PASS.','All135gas tau/ssa/g records remain bitwise equal across solar-only change; post-normalization source and transported flux records differ. These are paired pathway differences, not independent proof of a unique historical producer.','No historic generator SHA or full historical coefficients authenticated; no WRF-port accuracy, observational skill, or all-sky claim.'],'original_receipt_unchanged':True}
 out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'status':report['status'],'receipt':pin(out),'new_calls':0,'old_solar_counts':{k:results['old_solar'][k] for k in ['strict_full_array_failures','selected_stored_ulp_values','selected_wp_outside_published_rounding_interval','selected_wp_abs_error_over1e-5','selected_wp_abs_error_not_over1e-5']}}))
if __name__=='__main__':main()
