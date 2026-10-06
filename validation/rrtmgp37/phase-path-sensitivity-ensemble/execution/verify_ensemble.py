#!/usr/bin/env python3
"""Independent post-run verifier and paired-summary derivation for ensemble receipt."""
import csv, hashlib, json, math
from pathlib import Path
import numpy as np
HERE=Path(__file__).resolve().parent
ROOT=Path(__file__).resolve().parents[4]
BASE=Path('build/udm-phase-path-sensitivity-work')
CAP=Path('build/udm-selected-real-audit/on-only-20261003-v1/audit-on/run/capture')
DATA=Path('build/pr-wrf-rrtmgp/WRF/run')
TABLE=Path('build/pr-wrf-rrtmgp/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc')
SC={'LW':BASE/'prepared-lw','SW':BASE/'prepared-v2'}
MODES=('cf0_uniform','grid_uniform','ice160','ice140')
TCRIT=2.039513446

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def parse(p):
 lines=Path(p).read_text('ascii').splitlines()
 assert lines[0]=='RRTMGP_RESULT_V1'
 phase,nc,nl=lines[1].split();i=2;d={}
 while i<len(lines):
  h=lines[i].split();i+=1;name=h[0];shape=tuple(map(int,h[1:]));n=math.prod(shape);v=[]
  while len(v)<n:
   v.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split());i+=1
  assert name not in d and len(v)==n
  a=np.asarray(v,dtype=np.float64).reshape(shape,order='F')
  assert np.isfinite(a).all(),f'nonfinite {p}:{name}'
  d[name]=a
 return phase,int(nc),int(nl),d
def stat(arr):
 a=np.asarray(arr,dtype=np.float64);n=a.shape[0]
 mu=a.mean(axis=0);sd=a.std(axis=0,ddof=1);se=sd/math.sqrt(n)
 def cv(x): return x.tolist() if np.ndim(x) else float(x)
 return {'n':n,'mean':cv(mu),'sample_sd':cv(sd),'mcse':cv(se),'ci95_low':cv(mu-TCRIT*se),'ci95_high':cv(mu+TCRIT*se)}
def main():
 rec=json.loads((HERE/'receipt.json').read_text())
 assert rec['status']=='PASS_32_SEED_PAIRED_REPLAY'
 seeds=rec['seeds'];assert len(seeds)==32 and len(set(seeds))==32
 assert all(1<=s<=2147483647 for s in seeds)
 all_metrics={}; rows=[]; checked=0; seed_sets={}
 for ph in ('LW','SW'):
  pmetrics={}; seed_seen=[]
  for seed in seeds:
   d=HERE/'samples'/ph.lower()/f'seed-{seed:010d}'
   bp,bnc,bnl,b=parse(d/'baseline.result')
   assert bp==ph and bnc==1 and bnl==(47 if ph=='LW' else 40)
   s=int(b['ACTIVE_SAMPLE_SEED'].item());assert s==seed;seed_seen.append(s)
   assert int(b['CAPTURE_INPUT_SEED'].item())==rec['phases'][ph]['seed_recorded_anchor']
   assert int(b['ACTIVE_MASK_CHECK_SKIPPED'].item())==1
   assert int(b['RECORDED_ANCHOR_MASK_CHECK'].item())==(1 if ph=='SW' else 0)
   log=(d/'baseline.log').read_text()
   assert f'ACTIVE_SEED={seed}' in log and 'ACTIVE_MASK_VS_RECORDED_MASK=SKIPPED:' in log
   if ph=='SW': assert 'CAPTURE_ANCHOR_MASK_CHECK=PASS' in log
   else: assert 'CAPTURE_ANCHOR_MASK_CHECK=UNAVAILABLE:' in log
   for mode in MODES:
    vp,vnc,vnl,v=parse(d/f'{mode}.result')
    assert (vp,vnc,vnl)==(bp,bnc,bnl)
    assert int(v['ACTIVE_SAMPLE_SEED'].item())==seed
    assert int(v['CAPTURE_INPUT_SEED'].item())==rec['phases'][ph]['seed_recorded_anchor']
    assert int(v['ACTIVE_MASK_CHECK_SKIPPED'].item())==1
    assert int(v['RECORDED_ANCHOR_MASK_CHECK'].item())==(1 if ph=='SW' else 0)
    vlog=(d/f'{mode}.log').read_text()
    assert f'ACTIVE_SEED={seed}' in vlog and 'ACTIVE_MASK_VS_RECORDED_MASK=SKIPPED:' in vlog
    if ph=='SW': assert 'CAPTURE_ANCHOR_MASK_CHECK=PASS' in vlog
    else: assert 'CAPTURE_ANCHOR_MASK_CHECK=UNAVAILABLE:' in vlog
    extras_cf={'SENSITIVITY_PRECIP_TAU'} | ({'SENSITIVITY_RAW_PRECIP_TAU','DIRECT_PREDELTA_SCALED_NEGATIVE_CONTROL','DIRECT_SCALED_CUMULATIVE_TAU_NEGATIVE_CONTROL','DIRECT_RAW_CUMULATIVE_TAU'} if ph=='SW' else set())
    extras_ice={'ICE_DIAMETER_CHANGED','SENSITIVITY_COLUMN_J','ICE_DIAMETER_USED','ICE_DIAMETER_RAW','SENSITIVITY_COLUMN_I'}
    expected_fields=set(b)|(extras_cf if mode in ('cf0_uniform','grid_uniform') else extras_ice)
    assert set(v)==expected_fields,f'{ph}/{seed}/{mode}: result field set changed (missing={expected_fields-set(v)}, unexpected={set(v)-expected_fields})'
    assert np.array_equal(v['MASK'],b['MASK']),f'{ph}/{seed}/{mode}: mask mismatch'
    invariant=('GAS_COL_DRY','GAS_TAU','GAS_SSA','GAS_G','GRAUPEL_TAU_EXT','GRAUPEL_TAU_SCA',
               'GRAUPEL_TAU_SCA_G','HAIL_TAU_EXT','HAIL_TAU_SCA','HAIL_TAU_SCA_G',
               'FROZEN_TAU','FROZEN_SSA','FROZEN_G')
    for f in invariant:
     if f in b: assert np.array_equal(v[f],b[f]),f'{ph}/{seed}/{mode}: non-target field changed {f}'
    if mode in ('cf0_uniform','grid_uniform'):
     assert np.array_equal(v['DI_USED'],b['DI_USED']),f'{ph}/{seed}/{mode}: cloud ice diameter changed'
    if mode=='cf0_uniform':
     for f in ('CLOUD_TAU','CLOUD_SSA','CLOUD_G','PRECIP_TAU','PRECIP_SSA','PRECIP_G'):
      if f in b: assert np.array_equal(v[f],b[f]),f'{ph}/{seed}/{mode}: unrelated optics changed {f}'
    if mode in ('ice160','ice140'):
     for f in ('PRECIP_TAU','PRECIP_SSA','PRECIP_G'):
      if f in b: assert np.array_equal(v[f],b[f]),f'{ph}/{seed}/{mode}: precipitation changed {f}'
     changed=np.any(v['DI_USED']!=b['DI_USED'],axis=(0,2))
     assert int(changed.sum())==4,f'{ph}/{seed}/{mode}: expected exactly four active ice levels'
     flagged=np.any(v['ICE_DIAMETER_CHANGED']!=0,axis=(0,2))
     assert np.array_equal(flagged,changed),f'{ph}/{seed}/{mode}: changed-level flags differ from applied diameters'
     expected_d=160.0 if mode=='ice160' else 140.0
     applied=v['DI_USED'][0,changed,0]
     assert np.all(applied==expected_d),f'{ph}/{seed}/{mode}: selected diameter mismatch'
    for f in ('UP','DN','HR'): assert f in b and f in v
    delta={f:v[f]-b[f] for f in ('UP','DN','HR')}
    pmetrics.setdefault(mode,{f:[] for f in ('UP','DN','HR')})
    for f in ('UP','DN','HR'):
     pmetrics[mode][f].append(delta[f])
    rows.append({'phase':ph,'seed':seed,'mode':mode,
                 'surface_DN_delta':float(delta['DN'][0,0,0]),
                 'toa_UP_delta':float(delta['UP'][0,-1,0]),
                 'max_abs_HR_delta_K_day':float(np.max(np.abs(delta['HR']))),
                 'max_abs_UP_delta_W_m2':float(np.max(np.abs(delta['UP']))),
                 'max_abs_DN_delta_W_m2':float(np.max(np.abs(delta['DN'])))})
    checked+=1
  assert seed_seen==seeds and len(set(seed_seen))==32
  seed_sets[ph]=seed_seen
  all_metrics[ph]={}
  for mode in MODES:
   all_metrics[ph][mode]={f:stat(pmetrics[mode][f]) for f in ('UP','DN','HR')}
   all_metrics[ph][mode]['surface_DN_delta']=stat([float(x[0,0,0]) for x in pmetrics[mode]['DN']])
   all_metrics[ph][mode]['toa_UP_delta']=stat([float(x[0,-1,0]) for x in pmetrics[mode]['UP']])
 # Strict captured-seed comparisons must have passed before the ensemble.
 for ph,n in (('lw',20),('sw',46)):
  cmp=json.loads((HERE/'anchor'/ph/'compare.json').read_text())
  assert cmp.get('passed') and cmp.get('sections_compared')==n
 # Immutable artifacts still match the pre-run plan/receipt.
 expected={'executable':BASE/'ensemble-build/reference_column','table':TABLE,
           'reviewed_runner':BASE/'ensemble/run_seed_ensemble.py',
           'bounded_runner':BASE/'ensemble/run_seed_ensemble_bounded.py',
           'seed_override_source':BASE/'ensemble/reference_column_seed_override.f90'}
 after={k:sha(p) for k,p in expected.items()}
 assert after['executable']==rec['hashes']['executable'] and after['table']==rec['hashes']['table']
 plan_v4=json.loads((BASE/'ensemble/plan-review-v4/plan.json').read_text())
 assert after['reviewed_runner']==plan_v4['runner_sha256']=='b593aef13c11cbc88fb1e8186228986787e7ed39adbb2d2f31620906e19b10bb'
 assert after['seed_override_source']==rec['seed_override_source_sha256']
 assert rec['runner_sha256']=='085f1c249c77c50f942de684c5b01ea03667649fd7db082c9000d3c3f0a6e7e0'
 assert after['bounded_runner']==rec['runner_sha256']
 capture_after={}; sidecars_after={}
 for ph in ('LW','SW'):
  capture_after[ph]={}
  for ext in ('input','raw','result'):
   q=CAP/f'{ph.lower()}.{ext}'; capture_after[ph][ext]=sha(q)
   assert capture_after[ph][ext]==rec['hashes']['capture'][ph][ext]
  sidecars_after[ph]={}
  for mode in MODES:
   sidecars_after[ph][mode]=sha(SC[ph]/f'{mode}.sidecar')
   assert sidecars_after[ph][mode]==rec['hashes']['sidecars'][ph][mode]
 coeff={p.name:sha(p) for p in sorted(DATA.glob('rrtmgp-*.nc'))}
 assert coeff==rec['hashes']['data_coefficients']
 # Save compact independently-derived outputs.
 with (HERE/'per-seed-paired-deltas.csv').open('w',newline='') as f:
  w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');w.writeheader();w.writerows(rows)
 out={'status':'INDEPENDENT_VERIFY_PASS','scope':'single captured opaque column; paired standalone replay only',
      'validated_result_pairs':checked,'unique_active_seeds_per_phase':{k:len(set(v)) for k,v in seed_sets.items()},
      'seed_lists':seed_sets,'paired_masks_exact':True,'non_target_optics_exact':True,
      'LW_recorded_mask':'UNAVAILABLE in V8; explicitly not evaluated',
      'SW_recorded_mask_anchor':'strict captured V9 anchor passed before manufactured-seed replay; generated per-seed masks checked paired-exact',
      'immutable_hashes_after':after,'capture_hashes_after':capture_after,'sidecar_hashes_after':sidecars_after,'coefficient_hashes_after':coeff,
      'plan_v4_sha256':sha(BASE/'ensemble/plan-review-v4/plan.json'),
      'reviewed_source_patch_sha256':sha(BASE/'ensemble/reference_column_seed_override.patch'),
      'bounded_runner_diff_sha256':sha(BASE/'ensemble/run_seed_ensemble_bounded.py'),
      'statistics':all_metrics,'csv_sha256':sha(HERE/'per-seed-paired-deltas.csv'),
      'ci_method':'paired variant-minus-baseline; mean, ddof=1 sample SD, MCSE=SD/sqrt(32), t(0.975,31)=2.039513446 approximate mean interval conditional on this fixed state and deterministic seed list',
      'distribution_diagnostics':{},
      'interpretation':'Monte Carlo sensitivity for this one state only, not forecast uncertainty or accuracy. Student-t bands are approximate Monte Carlo mean intervals conditional on this fixed state and deterministic seed list; seed-key determinism does not establish independence.',
      'result_file_count':sum(1 for _ in HERE.rglob('*.result')),
      'runner_timeout_seconds':180}
 for ph in ('LW','SW'):
  for mode in MODES:
   vals=[r for r in rows if r['phase']==ph and r['mode']==mode]
   for metric in ('surface_DN_delta','toa_UP_delta','max_abs_HR_delta_K_day'):
    x=np.asarray([r[metric] for r in vals],dtype=float)
    sd=float(x.std(ddof=1)); mcse=sd/math.sqrt(32); mean=float(x.mean())
    out['distribution_diagnostics'][f'{ph}/{mode}/{metric}']={'min':float(x.min()),'max':float(x.max()),'zero_count_exact':int(np.count_nonzero(x==0.0)),'mean':mean,'sample_sd':sd,'mcse':mcse,'approx_ci95_mean_low':mean-TCRIT*mcse,'approx_ci95_mean_high':mean+TCRIT*mcse}
 out['immutable_hashes_after']=after
 (HERE/'independent-verification.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n')
 print(json.dumps({'status':out['status'],'pairs':checked,'verification':str(HERE/'independent-verification.json')},indent=2))
if __name__=='__main__':main()
