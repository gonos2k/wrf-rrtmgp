#!/usr/bin/env python3
"""Run the approved captured-anchor + one-seed CF0 paired smoke only."""
from __future__ import annotations
import argparse,hashlib,json,os,subprocess,sys
from pathlib import Path
import numpy as np
ROOT=Path(__file__).resolve().parents[3]
PHASES=('LW','SW')

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def read_result(path):
 lines=Path(path).read_text(encoding='ascii').splitlines()
 if lines[0]!='RRTMGP_RESULT_V1':raise ValueError('bad result magic')
 phase,nc,nl=lines[1].split();i=2;sections={}
 while i<len(lines):
  h=lines[i].split();i+=1;name=h[0];shape=tuple(map(int,h[1:]));n=int(np.prod(shape));vals=[]
  while len(vals)<n:vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split());i+=1
  if name in sections or len(vals)!=n:raise ValueError('bad/duplicate '+name)
  arr=np.asarray(vals,dtype=np.float64).reshape(shape,order='F')
  if not np.isfinite(arr).all():raise ValueError('nonfinite '+name)
  sections[name]=arr
 return phase,int(nc),int(nl),sections
def run(exe,data,inp,out,env,log,seed=None,sidecar=None):
 args=[str(exe),str(data),str(inp),str(out),'1','',str(sidecar) if sidecar else '',str(seed) if seed is not None else '']
 p=subprocess.run(args,env=env,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
 log.write_text(p.stdout,encoding='utf-8')
 if p.returncode:raise RuntimeError(f'reference failed rc={p.returncode}, log={log}')
 return p.stdout
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--exe',type=Path,required=True);ap.add_argument('--capture',type=Path,required=True);ap.add_argument('--data',type=Path,required=True);ap.add_argument('--table',type=Path,required=True);ap.add_argument('--sw-sidecars',type=Path,required=True);ap.add_argument('--lw-sidecars',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
 if not a.execute:raise SystemExit('This runner requires --execute; only one approved seed is run.')
 exe=a.exe.resolve();cap=a.capture.resolve();data=a.data.resolve();table=a.table.resolve();out=a.out.resolve();swsc=a.sw_sidecars.resolve();lwsc=a.lw_sidecars.resolve();seed=100001
 if out.exists():raise SystemExit(f'refusing existing output path {out}')
 out.mkdir(parents=True)
 env=os.environ.copy();env['WRF_RRTMGP_FROZEN_TABLE']=str(table)
 receipt={'status':'RUNNING','scope':'single-seed same-state independent replay smoke; no WRF forecast','seed':seed,'phases':{},'hashes':{'source':sha(Path(__file__).with_name('reference_column_seed_override.f90')),'runner':sha(Path(__file__)),'executable':sha(exe),'table':sha(table),'coefficients':{p.name:sha(p) for p in sorted(data.glob('rrtmgp-*.nc'))},'captures':{},'sidecars':{}}}
 (out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 try:
  cmp=ROOT/'build/udm-selected-real-wrf/source/WRF/test/rrtmgp/compare_column_replay.py'
  # Strict unchanged captured-seed outputs must pass before any override invocation.
  for ph in PHASES:
   inp=cap/f'{ph.lower()}.input';raw=cap/f'{ph.lower()}.raw';captured=cap/f'{ph.lower()}.result';before={str(p):sha(p) for p in (inp,raw,captured)}
   phase_dir=out/'anchors'/ph.lower();phase_dir.mkdir(parents=True)
   anchor=phase_dir/'anchor.result';log=phase_dir/'anchor.log'
   run(exe,data,inp,anchor,env,log)
   cp=subprocess.run([sys.executable,str(cmp),str(captured),str(anchor)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True)
   (phase_dir/'compare.json').write_text(cp.stdout,encoding='utf-8');rep=json.loads(cp.stdout)
   if cp.returncode or not rep.get('passed'):raise ValueError(f'{ph} strict anchor failed')
   if before!={str(p):sha(p) for p in (inp,raw,captured)}:raise ValueError(f'{ph} captured assets changed')
   receipt['hashes']['captures'][ph]={'input':before[str(inp)],'raw':before[str(raw)],'captured_result':before[str(captured)]}
   receipt['phases'][ph]={'anchor_status':'PASS','anchor_sections':rep.get('sections_compared'),'anchor_compare_sha256':sha(phase_dir/'compare.json')}
   (out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
  for ph in PHASES:
   inp=cap/f'{ph.lower()}.input';capture_result=cap/f'{ph.lower()}.result';input_before=sha(inp)
   line=inp.read_text(encoding='ascii').splitlines()[1].split();captured_seed=int(line[4])
   phase_dir=out/'sample'/ph.lower();phase_dir.mkdir(parents=True)
   basepath=phase_dir/'seed-baseline.result';baselog=phase_dir/'seed-baseline.log'
   bstdout=run(exe,data,inp,basepath,env,baselog,seed)
   bphase,bnc,bnl,b=read_result(basepath)
   vpath=phase_dir/'cf0-uniform.result';vlog=phase_dir/'cf0-uniform.log';sidecars=lwsc if ph=='LW' else swsc;sidecar=sidecars/'cf0_uniform.sidecar'
   vstdout=run(exe,data,inp,vpath,env,vlog,seed,sidecar)
   vphase,vnc,vnl,v=read_result(vpath)
   if sha(inp)!=input_before:raise ValueError(f'{ph} replay input was mutated')
   expected_nl=47 if ph=='LW' else 40
   if (bphase,vphase,bnc,vnc,bnl,vnl)!=(ph,ph,1,1,expected_nl,expected_nl):raise ValueError(f'{ph} sample result identity mismatch')
   if seed==captured_seed:raise ValueError(f'{ph} override seed must differ from captured seed')
   for output,stdout in ((b,bstdout),(v,vstdout)):
    if int(output['ACTIVE_SAMPLE_SEED'].item())!=seed or int(output['CAPTURE_INPUT_SEED'].item())!=captured_seed:raise ValueError(f'{ph} sample seed metadata mismatch')
    if int(output['ACTIVE_MASK_CHECK_SKIPPED'].item())!=1:raise ValueError(f'{ph} missing explicit mask-skip metadata')
    if int(output['RECORDED_ANCHOR_MASK_CHECK'].item())!=(1 if ph=='SW' else 0):raise ValueError(f'{ph} anchor-mask status metadata wrong')
    if 'ACTIVE_MASK_VS_RECORDED_MASK=SKIPPED:' not in stdout:raise ValueError(f'{ph} missing skip reason in log')
    if f'ACTIVE_SEED={seed}' not in stdout:raise ValueError(f'{ph} active seed missing from log')
   if ph=='SW':
    if 'CAPTURE_ANCHOR_MASK_CHECK=PASS' not in bstdout or 'CAPTURE_ANCHOR_MASK_CHECK=PASS' not in vstdout:raise ValueError('SW captured V9 mask check did not pass before override')
    captured_mask=read_result(capture_result)[3]['MASK']
    if np.array_equal(b['MASK'],captured_mask):raise ValueError('chosen SW seed did not regenerate a distinct mask')
   elif 'CAPTURE_ANCHOR_MASK_CHECK=UNAVAILABLE: V8 LW input contains no recorded mask field' not in bstdout:
    raise ValueError('LW recorded-mask-unavailable reason absent')
   if not np.array_equal(b['MASK'],v['MASK']):raise ValueError(f'{ph} same-seed paired mask differs')
   for key in ('GAS_COL_DRY','GAS_TAU','GAS_TAU_RAW','FROZEN_TAU','GRAUPEL_TAU_EXT','HAIL_TAU_EXT','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','CLOUD_TAU','CLOUD_SSA','CLOUD_G','PREPARED_TAU','PREPARED_SSA','PREPARED_G'):
    if key in b and key in v and not np.array_equal(b[key],v[key]):raise ValueError(f'{ph} CF0 changed invariant {key}')
   for key in ('PRECIP_TAU','PRECIP_SSA','PRECIP_G'):
    if key in b and key in v and not np.array_equal(b[key],v[key]):raise ValueError(f'{ph} CF0 changed conditional precipitation {key}')
   receipt['hashes']['sidecars'][ph]={'cf0_uniform':sha(sidecar)}
   receipt['phases'][ph]['seed_override']={'status':'PASS','active_seed':seed,'captured_seed':captured_seed,'seed_differs':seed!=captured_seed,'same_seed_paired_mask_exact':True,'sw_capture_anchor_mask_passed_before_sample_skip':ph=='SW','lw_mask_record_unavailable_reason_recorded':ph=='LW','sample_mask_differs_captured_mask':bool(ph=='SW' and not np.array_equal(b['MASK'],read_result(capture_result)[3]['MASK'])),'baseline_result_sha256':sha(basepath),'baseline_log_sha256':sha(baselog),'variant_result_sha256':sha(vpath),'variant_log_sha256':sha(vlog)}
   receipt['phases'][ph]['signed_flux_deltas']={'surface_DN_W_m2':float(v['DN'][0,0,0]-b['DN'][0,0,0]),'TOA_UP_W_m2':float(v['UP'][0,-1,0]-b['UP'][0,-1,0]),'HR_max_abs_K_day':float(np.max(np.abs(v['HR']-b['HR'])))}
   (out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
  receipt['status']='PASS_ONE_SEED_PAIRED_SMOKE';(out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
 except Exception as exc:
  receipt['status']='FAIL';receipt['failure']=str(exc);(out/'receipt.json').write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n');raise
 print(json.dumps({'status':receipt['status'],'receipt':str(out/'receipt.json')},indent=2))
if __name__=='__main__':main()
