#!/usr/bin/env python3
"""Prepare or execute a paired, same-state 32-seed sensitivity ensemble.

Default is plan-only. A real run requires --execute and a new output directory.
The runner invokes only the standalone independent column replay, never WRF.
"""
from __future__ import annotations
import argparse, hashlib, json, os, subprocess, sys, time
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]

NSEEDS=32
T95_DF31=2.039513446
MODES=('cf0_uniform','grid_uniform','ice160','ice140')
PHASES=('LW','SW')
FLUX_FIELDS=('UP','DN','HR')

def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for block in iter(lambda:f.read(1<<20),b''):h.update(block)
 return h.hexdigest()
def read_sections(path):
 lines=Path(path).read_text(encoding='ascii').splitlines()
 if lines[0]!='RRTMGP_RESULT_V1':raise ValueError('bad result magic')
 phase,nc,nl=lines[1].split();i=2;sections={}
 while i<len(lines):
  h=lines[i].split();i+=1;name=h[0];shape=tuple(map(int,h[1:]));n=int(np.prod(shape));values=[]
  while len(values)<n:
   values.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split());i+=1
  if name in sections or len(values)!=n:raise ValueError('bad result section '+name)
  a=np.asarray(values,dtype=np.float64).reshape(shape,order='F')
  if not np.isfinite(a).all():raise ValueError('nonfinite result section '+name)
  sections[name]=a
 return phase,int(nc),int(nl),sections
def stats(values):
 a=np.asarray(values,dtype=np.float64)
 if a.shape[0]<2:raise ValueError('statistics require at least two paired samples')
 mean=a.mean(axis=0);sd=a.std(axis=0,ddof=1);mcse=sd/np.sqrt(a.shape[0]);margin=T95_DF31*mcse
 def val(x):return x.tolist() if np.ndim(x) else float(x)
 return {'n':int(a.shape[0]),'mean':val(mean),'sample_sd':val(sd),'mcse':val(mcse),'mean_95pct_t_ci_low':val(mean-margin),'mean_95pct_t_ci_high':val(mean+margin),'ci_method':'mean +/- t(0.975,df=31) * sample_sd/sqrt(32); paired interpretation applies to variant-minus-baseline samples'}
def self_test():
 s=stats([1,2,3,4]);assert abs(s['mean']-2.5)<1e-15 and abs(s['sample_sd']-(5/3)**0.5)<1e-14
 # Pairing must preserve the algebraic sample differences exactly.
 base=np.array([3.,4.,5.,6.]);variant=base+np.array([1.,2.,3.,4.]);assert np.array_equal(variant-base,[1.,2.,3.,4.])
 return True
def command(exe,data,inp,out,seed=None,sidecar=None):
 return [str(exe),str(data),str(inp),str(out),'1','',str(sidecar) if sidecar is not None else '',
         str(seed) if seed is not None else '']
def run_one(args,env,logpath):
 t=time.time();p=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=180)
 logpath.write_text(p.stdout,encoding='utf-8')
 if p.returncode:raise RuntimeError(f'command failed ({p.returncode}); see {logpath}')
 return p.stdout,time.time()-t
def summary_vector(a):return stats(np.asarray(a))
def check_seed_metadata(sections,seed,phase):
 if int(sections['ACTIVE_SAMPLE_SEED'].item())!=seed:raise ValueError('active sample seed metadata mismatch')
 if int(sections['ACTIVE_MASK_CHECK_SKIPPED'].item())!=1:raise ValueError('missing explicit active-mask skip marker')
 expected_anchor=1 if phase=='SW' else 0
 if int(sections['RECORDED_ANCHOR_MASK_CHECK'].item())!=expected_anchor:raise ValueError('recorded anchor mask-check status mismatch')
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--exe',type=Path,required=True);ap.add_argument('--data-dir',type=Path,required=True)
 ap.add_argument('--capture-dir',type=Path,required=True);ap.add_argument('--sw-sidecars',type=Path,required=True);ap.add_argument('--lw-sidecars',type=Path,required=True)
 ap.add_argument('--table',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--execute',action='store_true')
 a=ap.parse_args();exe=a.exe.resolve();data=a.data_dir.resolve();cap=a.capture_dir.resolve();swsc=a.sw_sidecars.resolve();lwsc=a.lw_sidecars.resolve();table=a.table.resolve();out=a.out.resolve()
 if out.exists() and any(out.iterdir()):raise SystemExit(f'refusing nonempty output directory {out}')
 if not self_test():raise SystemExit('statistics self-test failed')
 # A deterministic 32-key sequence, in the supported 31-bit positive seed range.
 seeds=[100001+k*104729 for k in range(NSEEDS)]
 if len(set(seeds))!=NSEEDS or not all(1<=s<=2147483647 for s in seeds):raise SystemExit('bad seed plan')
 phases={ph:{'input':cap/f'{ph.lower()}.input','capture_result':cap/f'{ph.lower()}.result','sidecars':(lwsc if ph=='LW' else swsc)} for ph in PHASES}
 for ph,x in phases.items():
  if not all(p.is_file() for p in (x['input'],x['capture_result'])):raise SystemExit(f'missing {ph} anchor input/result')
  for mode in MODES:
   if not (x['sidecars']/f'{mode}.sidecar').is_file():raise SystemExit(f'missing {ph}/{mode} sidecar')
 env=os.environ.copy();env['WRF_RRTMGP_FROZEN_TABLE']=str(table)
 plan={'status':'PLAN_ONLY' if not a.execute else 'RUNNING','scope':'one opaque captured column, paired standalone radiative-transfer replay; no WRF/forecast/observation claims','seeds':seeds,'n_seeds':NSEEDS,'seed_formula':'100001 + k*104729, k=0..31','runs':{'strict_anchor_baselines':2,'seeded_baselines':NSEEDS*2,'seeded_variants':NSEEDS*2*len(MODES),'total_if_executed':2+NSEEDS*2*(1+len(MODES))},'phases':{},'hashes':{'executable':sha(exe),'table':sha(table),'data_coefficients':{p.name:sha(p) for p in sorted(data.glob('rrtmgp-*.nc'))},'capture':{},'sidecars':{}} ,'runner_sha256':sha(Path(__file__)),'seed_override_source_sha256':sha(Path(__file__).with_name('reference_column_seed_override.f90')),'statistics':{'paired_difference':'variant minus same-seed baseline','mean':'arithmetic sample mean across 32 paired differences','sample_sd':'ddof=1','mcse':'sample_sd/sqrt(32)','95pct_CI':'paired Student t interval, df=31, tcrit=2.039513446','interpretation':'Monte Carlo variability for this one captured state only; not an empirical-observation confidence interval or forecast uncertainty.'}}
 for ph,x in phases.items():
  plan['phases'][ph]={'input_sha256':sha(x['input']),'capture_result_sha256':sha(x['capture_result']),'seed_recorded_anchor':int(x['input'].read_text(encoding='ascii').splitlines()[1].split()[4])}
  plan['hashes']['capture'][ph]={'input':sha(x['input']),'result':sha(x['capture_result']),'raw':sha(cap/f'{ph.lower()}.raw')}
  plan['hashes']['sidecars'][ph]={m:sha(x['sidecars']/f'{m}.sidecar') for m in MODES}
 plan['self_test']={'sample_statistics_and_pairing':'PASS'}
 if not a.execute:
  out.parent.mkdir(parents=True,exist_ok=True);out.mkdir(parents=True,exist_ok=False);(out/'plan.json').write_text(json.dumps(plan,indent=2,sort_keys=True)+'\n')
  print(json.dumps({'status':'PLAN_ONLY','plan':str(out/'plan.json'),'runs_if_executed':plan['runs']['total_if_executed']},indent=2));return 0
 out.mkdir(parents=True,exist_ok=False)
 receipt={**plan,'status':'RUNNING','anchor_checks':{},'seed_results':{},'failures':[]}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 try:
  # Mandatory strict captured-seed anchor: defaults, no sensitivity sidecar or override.
  cmp_path=ROOT/'build/udm-selected-real-wrf/source/WRF/test/rrtmgp/compare_column_replay.py'
  for ph,x in phases.items():
   phase_dir=out/'anchor'/ph.lower();phase_dir.mkdir(parents=True)
   anchor_out=phase_dir/'anchor.result';log=phase_dir/'anchor.log'
   source_input_hash=sha(x['input'])
   stdout,_=run_one(command(exe,data,x['input'],anchor_out),env,log)
   if sha(x['input'])!=source_input_hash:raise RuntimeError(f'{ph} anchor input changed during run')
   cmp=subprocess.run([sys.executable,str(cmp_path),str(x['capture_result']),str(anchor_out)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
   (phase_dir/'compare.json').write_text(cmp.stdout,encoding='utf-8')
   report=json.loads(cmp.stdout)
   if cmp.returncode or not report.get('passed'):raise RuntimeError(f'{ph} strict captured-seed anchor failed')
   receipt['anchor_checks'][ph]={'status':'PASS','sections':report.get('sections_compared'),'compare_sha256':sha(phase_dir/'compare.json')}
   (out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
  for ph,x in phases.items():
   phase_data=[]
   for seed in seeds:
    sd=out/'samples'/ph.lower()/f'seed-{seed:010d}';sd.mkdir(parents=True)
    bpath=sd/'baseline.result';blog=sd/'baseline.log'
    source_input_hash=sha(x['input'])
    bstdout,_=run_one(command(exe,data,x['input'],bpath,seed),env,blog)
    if sha(x['input'])!=source_input_hash:raise RuntimeError(f'{ph} input changed during seeded baseline')
    bph,bnc,bnl,b=read_sections(bpath)
    check_seed_metadata(b,seed,ph)
    if f'ACTIVE_SEED={seed}' not in bstdout or 'ACTIVE_MASK_VS_RECORDED_MASK=SKIPPED:' not in bstdout:raise RuntimeError(f'{ph} baseline seed provenance absent for {seed}')
    if ph=='SW' and 'CAPTURE_ANCHOR_MASK_CHECK=PASS' not in bstdout:raise RuntimeError('SW recorded V9 anchor-mask validation not passed')
    per_variant={}
    for mode in MODES:
     vpath=sd/f'{mode}.result';vlog=sd/f'{mode}.log'
     vstdout,_=run_one(command(exe,data,x['input'],vpath,seed,x['sidecars']/f'{mode}.sidecar'),env,vlog)
     if sha(x['input'])!=source_input_hash:raise RuntimeError(f'{ph} input changed during {mode} run')
     if f'ACTIVE_SEED={seed}' not in vstdout or 'ACTIVE_MASK_VS_RECORDED_MASK=SKIPPED:' not in vstdout:raise RuntimeError(f'{ph}/{mode} seed provenance absent')
     if ph=='SW' and 'CAPTURE_ANCHOR_MASK_CHECK=PASS' not in vstdout:raise RuntimeError('SW V9 anchor mask check not passed')
     vph,vnc,vnl,v=read_sections(vpath)
     check_seed_metadata(v,seed,ph)
     if (vph,vnc,vnl)!=(bph,bnc,bnl):raise RuntimeError('paired result dimensions/phase differ')
     if not np.array_equal(v['MASK'],b['MASK']):raise RuntimeError(f'{ph}/{mode}/{seed}: paired masks differ')
     for field in ('GAS_COL_DRY','GAS_TAU','FROZEN_TAU','GRAUPEL_TAU_EXT','HAIL_TAU_EXT','GRAUPEL_TAU_ABS','HAIL_TAU_ABS'):
      if field in v and field in b and not np.array_equal(v[field],b[field]):raise RuntimeError(f'{ph}/{mode}/{seed}: changed non-target optics {field}')
     metrics={}
     for f in ('UP','DN','HR'):
      if f not in v or f not in b:continue
      metrics[f+'_baseline']=b[f]
      metrics[f+'_variant']=v[f]
      metrics[f+'_paired_delta']=v[f]-b[f]
      if f in ('UP','DN'):
       idx=0 if f=='DN' else -1
       metrics['surface_DN_paired_delta' if f=='DN' else 'TOA_UP_paired_delta']=float(v[f][0,idx,0]-b[f][0,idx,0])
     per_variant[mode]=metrics
    phase_data.append({'seed':seed,'baseline':{f:b[f] for f in ('UP','DN','HR') if f in b},'variants':per_variant})
    receipt['seed_results'].setdefault(ph,[]).append({'seed':seed,'paired_mask_pass':True,'active_seed_marker_pass':True,'variant_modes':list(per_variant)})
    (out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
   summaries={}
   for mode in MODES:
    summaries[mode]={}
    for f in ('UP','DN','HR'):
     vals=[sample['variants'][mode][f+'_paired_delta'] for sample in phase_data]
     summaries[mode][f+'_paired_delta']=summary_vector(vals)
     summaries[mode][f+'_baseline']=summary_vector([sample['baseline'][f] for sample in phase_data])
     summaries[mode][f+'_variant']=summary_vector([sample['variants'][mode][f+'_variant'] for sample in phase_data])
     if f=='DN': summaries[mode]['surface_DN_paired_delta']=summary_vector([sample['variants'][mode]['surface_DN_paired_delta'] for sample in phase_data])
     if f=='UP': summaries[mode]['TOA_UP_paired_delta']=summary_vector([sample['variants'][mode]['TOA_UP_paired_delta'] for sample in phase_data])
   (out/f'{ph.lower()}-summary.json').write_text(json.dumps(summaries,indent=2,sort_keys=True)+'\n')
  receipt['status']='PASS_32_SEED_PAIRED_REPLAY';(out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 except Exception as exc:
  receipt['status']='FAIL';receipt['failures'].append(str(exc));(out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n');raise
 print(json.dumps({'status':receipt['status'],'receipt':str(out/'receipt.json')},indent=2));return 0
if __name__=='__main__':raise SystemExit(main())
