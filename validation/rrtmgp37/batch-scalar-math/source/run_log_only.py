#!/usr/bin/env python3
"""Run exactly batch32 and scalar32 once with the local scalar-log shim; retain failures."""
from pathlib import Path
import hashlib, json, os, re, struct, subprocess, sys, time, math
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
P=ROOT/'build/udm-lw-batch-wp-probe'; S=P/'scalar-log'
SRC=ROOT/'build/pr-wrf-rrtmgp/build/udm-lw-batch-diag-pr32-build-v4-source/WRF'
EXE=S/'build/wp_probe_scalar_log.exe'; FIX=P/'fixtures-v2/lw32-fortran-order.bin'
TABLE=ROOT/'build/pr-wrf-rrtmgp/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
DATADIR=SRC/'run'; LIB=ROOT/'build/deps/netcdf/lib'; TOUT=180
EXPECTED={
 'exe':'0643ac4f2bbcb749ab7f17748160e4f47d1e813876c165c3c715b83f4ab1feee',
 'shim':'13d2ed551d1f0f71df76b408a2c64c236fce04d2b1439a6b7ef88257d08c6414',
 'driver_obj':'f695a2d79685b966241bbcc6936d9a8b66127f408d9fb90c2ed04b8c1c066e45',
 'adapter_obj':'bcbb6b437a2157cfd1f31e6b643fb3d37abb0e514abcf140a80bac01fafb0e96',
 'fixture':'644ddb36f5f883b8e9a5ed75d53f426ec47176c83a5c24d7e49a40b6f62620da',
 'table':'8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583',
 'gas':'70ad65d116531122660318e5da2a2af9db74b425916202860e9527ef2375b8f6',
 'cloud':'09d6704c5b863b4c3ceb417d20bb3076ec492e6bf2dfbcc9f3c5996a3706f0b0',
}
LIB_SORTED_SHA='31921bf9067ad5b1b5567a12284008e2bd596fd7fe22d37acffb21ff9cdd880d'
EXPECTED_SHAPES={'GAS_COL_DRY':(32,47),'GAS_TAU':(32,47,128),'SOURCE_LAY':(32,47,128),'SOURCE_LEV':(32,48,128),'SOURCE_SFC':(32,128),'CLEAR_FU':(32,48),'CLEAR_FD':(32,48),'CLEAR_HEAT':(32,47),'TOTAL_TAU':(32,47,128),'ALL_FU':(32,48),'ALL_FD':(32,48),'ALL_HEAT':(32,47)}
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''): h.update(b)
 return h.hexdigest()
def pin(path,key): return {'path':str(path),'sha256':sha(path),'expected_sha256':EXPECTED[key],'ok':sha(path)==EXPECTED[key]}
def libs():
 env={'PATH':'/usr/bin:/bin','LC_ALL':'C','LD_LIBRARY_PATH':str(LIB)}
 cp=subprocess.run(['/usr/bin/ldd',str(EXE)],env=env,text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT,check=False)
 if cp.returncode: raise RuntimeError('ldd failed: '+cp.stdout)
 found={}
 for ln in cp.stdout.splitlines():
  if 'not found' in ln: raise RuntimeError('unresolved library: '+ln)
  s=ln.strip()
  if ' => ' in s:
   son,rest=s.split(' => ',1); path=rest.split(' (',1)[0]
  elif s.startswith('/'):
   path=s.split(' (',1)[0]; son=Path(path).name
  else: continue
  if path.startswith('/'):
   real=Path(path).resolve(strict=True)
   found[son]={'real_path':str(real),'sha256':sha(real)}
 expected=json.loads((P/'runtime-libraries.json').read_text())['libraries']
 expected={k:{'real_path':v['real_path'],'sha256':v['sha256']} for k,v in expected.items()}
 ok=found==expected
 return {'returncode':cp.returncode,'libraries':found,'expected_manifest_sha256':sha(P/'runtime-libraries.json'),'ok':ok,'output':cp.stdout}
def parse_wp(p):
 lines=Path(p).read_text().splitlines(); chunks={}; i=0
 while i<len(lines):
  head=lines[i].split(); i+=1
  if len(head) not in (3,4): raise ValueError(f'bad section header {head}')
  name=head[0]; shape=tuple(map(int,head[1:])); n=math.prod(shape)
  vals=lines[i:i+n]; i+=n
  if len(vals)!=n or any(len(x)!=16 for x in vals): raise ValueError(f'truncated/malformed section {name}')
  chunks.setdefault(name,[]).append((shape,vals))
 out={}
 for name,parts in chunks.items():
  tail=parts[0][0][1:]
  if any(sh[1:]!=tail for sh,_ in parts): raise ValueError(f'inconsistent scalar chunks {name}')
  arrays=[np.array(v,dtype='U16').reshape(sh,order='F') for sh,v in parts]
  arr=np.concatenate(arrays,axis=0)
  out[name]={'shape':arr.shape,'tokens':arr.flatten(order='F').tolist(),'chunks':len(parts)}
 return out
def val(tok): return struct.unpack('>d',int(tok,16).to_bytes(8,'big'))[0]
def ordered(tok):
 b=int(tok,16); return (~b & ((1<<64)-1)) if b>>63 else (b | (1<<63))
def main():
 if len(sys.argv)!=2: raise SystemExit('usage: run_counterfactual_pair.py FRESH_OUTPUT_DIRECTORY')
 out=Path(sys.argv[1]).absolute()
 if out.exists(): raise SystemExit(f'refusing existing output root {out}')
 out.mkdir(parents=True)
 receipt={'status':'RUNNING','output_root':str(out),'timeout_seconds_each':TOUT,'planned_engine_processes':['batch32','scalar32'],
   'executable':pin(EXE,'exe'),'shim_object':pin(S/'build/scalar_log_shim.o','shim'),
   'driver_object':pin(P/'build/wp_probe_driver.o','driver_obj'),'adapter_object':pin(P/'build/module_ra_rrtmgp.o','adapter_obj'),
   'fixture':pin(FIX,'fixture'),'gas_coeff':pin(DATADIR/'rrtmgp-gas-lw-g128.nc','gas'),
   'cloud_coeff':pin(DATADIR/'rrtmgp-clouds-lw-bnd.nc','cloud'),'frozen_table':pin(TABLE,'table'),
   'runtime_pre':None,'runtime_post':None,'runs':{},'wp_comparison':None,'f32_oracles':{},'exceptions':[]}
 try:
  receipt['runtime_pre']=libs()
  if not all(receipt[k]['ok'] for k in ['executable','shim_object','driver_object','adapter_object','fixture','gas_coeff','cloud_coeff','frozen_table']) or not receipt['runtime_pre']['ok']:
   raise RuntimeError('preflight pin/runtime mismatch; no model process launched')
  envbase={'PATH':'/usr/bin:/bin','LC_ALL':'C','LD_LIBRARY_PATH':str(LIB)}
  for mode,bs in [('batch32','32'),('scalar32','1')]:
   d=out/mode; d.mkdir()
   env={**envbase,'WRF_RRTMGP_BATCH_SIZE':bs,'RRTMGP_WP_CAPTURE_FILE':str(d/'wp.hex')}
   argv=[str(EXE),str(FIX),str(DATADIR),str(TABLE),mode,str(d/'actual-f32.bin')]
   start=time.time(); timed=False
   with (d/'stdout.log').open('wb') as log:
    try: cp=subprocess.run(argv,cwd=ROOT,env=env,stdout=log,stderr=subprocess.STDOUT,timeout=TOUT,check=False); rc=cp.returncode
    except subprocess.TimeoutExpired: rc=124; timed=True
   row={'argv':argv,'env':env,'elapsed_s':time.time()-start,'returncode':rc,'timed_out':timed,
      'stdout_sha256':sha(d/'stdout.log'),'wp_present':(d/'wp.hex').exists(),'f32_present':(d/'actual-f32.bin').exists()}
   if row['wp_present']: row['wp_sha256']=sha(d/'wp.hex')
   if row['f32_present']:
    actual=(d/'actual-f32.bin').read_bytes(); expected=(P/'fixtures-v2'/f'expected-{mode}.bin').read_bytes()
    row['f32_oracle']={'bytes_equal':actual==expected,'actual_sha256':hashlib.sha256(actual).hexdigest(),'expected_sha256':hashlib.sha256(expected).hexdigest(),'bytes':len(actual),'different_bytes':sum(x!=y for x,y in zip(actual,expected)) if len(actual)==len(expected) else None}
   receipt['runs'][mode]=row
  if set(receipt['runs'])=={'batch32','scalar32'} and all(x['wp_present'] and x['returncode']==0 and not x['timed_out'] for x in receipt['runs'].values()):
   ba=parse_wp(out/'batch32/wp.hex'); sc=parse_wp(out/'scalar32/wp.hex')
   if set(ba)!=set(EXPECTED_SHAPES) or set(sc)!=set(EXPECTED_SHAPES): raise ValueError('unexpected WP section set')
   cmp={}
   for name,shape in EXPECTED_SHAPES.items():
    b=ba[name]; s=sc[name]
    if tuple(b['shape'])!=shape or tuple(s['shape'])!=shape: raise ValueError(f'shape mismatch {name}: {b["shape"]}/{s["shape"]}')
    ids=[i for i,(x,y) in enumerate(zip(b['tokens'],s['tokens'])) if x!=y]
    diffs=[(val(b['tokens'][i]),val(s['tokens'][i]),b['tokens'][i],s['tokens'][i]) for i in ids]
    cmp[name]={'batch_chunks':b['chunks'],'scalar_chunks':s['chunks'],'shape':shape,'different_values':len(ids),'total_values':len(b['tokens']),
      'max_abs':max((abs(x-y) for x,y,_,_ in diffs),default=0.0),
      'max_ulp':max((abs(ordered(xh)-ordered(yh)) for _,_,xh,yh in diffs),default=0)}
   first=next((n for n in EXPECTED_SHAPES if cmp[n]['different_values']),None)
   receipt['wp_comparison']={'status':'COMPARED','first_differing_stage':first,'sections':cmp,'primary_gas_tau_equal':cmp['GAS_TAU']['different_values']==0,'source_functions_equal':all(cmp[n]['different_values']==0 for n in ['SOURCE_LAY','SOURCE_LEV','SOURCE_SFC'])}
  else: receipt['wp_comparison']={'status':'UNAVAILABLE','reason':'one or both engine processes failed, timed out, or omitted WP output'}
 except Exception as e: receipt['exceptions'].append(type(e).__name__+': '+str(e))
 finally:
  try: receipt['runtime_post']=libs()
  except Exception as e: receipt['exceptions'].append('runtime_post: '+type(e).__name__+': '+str(e))
  post={
   'executable':sha(EXE) if EXE.exists() else None,'shim_object':sha(S/'build/scalar_log_shim.o') if (S/'build/scalar_log_shim.o').exists() else None,
   'driver_object':sha(P/'build/wp_probe_driver.o') if (P/'build/wp_probe_driver.o').exists() else None,'adapter_object':sha(P/'build/module_ra_rrtmgp.o') if (P/'build/module_ra_rrtmgp.o').exists() else None,
   'fixture':sha(FIX) if FIX.exists() else None,'gas_coeff':sha(DATADIR/'rrtmgp-gas-lw-g128.nc') if (DATADIR/'rrtmgp-gas-lw-g128.nc').exists() else None,
   'cloud_coeff':sha(DATADIR/'rrtmgp-clouds-lw-bnd.nc') if (DATADIR/'rrtmgp-clouds-lw-bnd.nc').exists() else None,'frozen_table':sha(TABLE) if TABLE.exists() else None}
  receipt['post_hashes']=post
  receipt['pins_unchanged']=all(post[k]==receipt[k]['sha256'] for k in post)
  wc=receipt.get('wp_comparison') or {}
  rp=receipt.get('runtime_post') or {}
  receipt['status']='PASS_ANALYZED' if wc.get('status')=='COMPARED' and receipt.get('pins_unchanged') and rp.get('ok') is True and not receipt['exceptions'] else 'FAIL_PRESERVED'
  receipt['note']='F32 oracle mismatches are recorded but do not block WP comparison; no retries or extra engine calls.'
  with (out/'counterfactual-run-receipt.json').open('x') as f: json.dump(receipt,f,indent=2); f.write('\n')
 print(out/'counterfactual-run-receipt.json')
 return 0 if receipt['status']=='PASS_ANALYZED' else 1
if __name__=='__main__': raise SystemExit(main())
