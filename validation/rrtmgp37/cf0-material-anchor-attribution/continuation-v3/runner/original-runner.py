#!/usr/bin/env python3
"""Single-use, fail-closed preparation/execution runner for eight CF0 anchor calls."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, signal, subprocess, sys, time
from pathlib import Path
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=ROOT/'build/udm37-cf0-material-anchor-runtime-v1'; PLAN=HERE/'plan.json'; PF=HERE/'preflight-v5.json'
ROSTER=ROOT/'build/udm37-cf0-material-anchor-inputs-v1/roster.json'
BUILD=ROOT/'build/cf0-cu-build-runner-v2/execution.json'; REVIEW=ROOT/'build/udm37-rrtmg4-export-independent-review-v1/cf0-cu-postbuild-review-v1/review.json'
EXE=ROOT/'build/cf0-cu-build-v1/cmake-build/reference_column'; DATA=ROOT/'build/udm-cu-optics-design-work/WRF/run'
TABLE=ROOT/'build/udm-alternate-jan2000-data/paired-forecast-v2/ra37/frozen-ice-psd-moments.nc'
READER=ROOT/'build/udm37-phase-diagnostic-contract-pr-work/WRF/test/rrtmgp/compare_column_replay.py'
VALIDATOR=ROOT/'build/cf0-cu-src-v1/WRF/test/rrtmgp/cf0_precip_sidecar.py'
BASELINE=ROOT/'build/udm37-occurrence-clipping-baseline-replay-v1/runs-v1/execution.json'
CTX=HERE/'sidecar-context-preflight.json'; RUN=HERE/'run-v1'; OUT=RUN/'outputs'; LOG=RUN/'logs'; AUTH='cf0-material-anchor-eight-call-authorization-v1'
ORDER=['winter_native_cu-lw-baseline','winter_native_cu-lw-rain-increment','winter_native_cu-sw-baseline','winter_native_cu-sw-rain-increment','material_cf0_snow_low_cloud-lw-baseline','material_cf0_snow_low_cloud-lw-snow-increment','material_cf0_snow_low_cloud-sw-baseline','material_cf0_snow_low_cloud-sw-snow-increment']
ENV={'PATH':'/usr/local/bin:/usr/bin:/bin','LD_LIBRARY_PATH':str(ROOT/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu','NETCDF':str(ROOT/'build/deps/netcdf'),'LANG':'C','LC_ALL':'C','TMPDIR':'/tmp','OPENBLAS_NUM_THREADS':'1','WRF_RRTMGP_FROZEN_TABLE':str(TABLE)}
TIMEOUT=180

def digest(path):
 h=hashlib.sha256(); n=0
 with Path(path).open('rb') as f:
  while b:=f.read(1<<20): h.update(b); n+=len(b)
 return h.hexdigest(),n
sha=digest
def pin(path):
 p=Path(path); h,n=digest(p); return {'path':str(p.resolve()),'sha256':h,'size_bytes':n}
def norm(rec):
 p=Path(rec['path']); p=p if p.is_absolute() else ROOT/p
 return {'path':str(p.resolve()),'sha256':rec['sha256'],'size_bytes':rec.get('size_bytes',rec.get('bytes'))}
def require(rec,label):
 p=Path(rec['path'])
 if not p.is_file() or digest(p)!=(rec['sha256'],rec['size_bytes']): raise RuntimeError(f'pin mismatch {label}: {p}')
def fsyncdir(p):
 fd=os.open(p,os.O_RDONLY|os.O_DIRECTORY); os.fsync(fd); os.close(fd)
def atomic(path,obj):
 path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+'.tmp')
 with tmp.open('w') as f: json.dump(obj,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
 os.replace(tmp,path); fsyncdir(path.parent)
def ldd_pins():
 cp=subprocess.run(['/usr/bin/ldd',str(EXE)],env=ENV,text=True,capture_output=True,check=True); out={}
 for ln in cp.stdout.splitlines():
  if '=>' not in ln: continue
  rhs=ln.split('=>',1)[1].strip().split()
  if rhs and rhs[0].startswith('/'):
   r=pin(Path(rhs[0]).resolve()); out[r['path']]=r
 return sorted(out.values(),key=lambda x:x['path'])
def import_module(path,name):
 spec=importlib.util.spec_from_file_location(name,path); m=importlib.util.module_from_spec(spec); sys.modules[name]=m; spec.loader.exec_module(m); return m
def read_result(path): return import_module(READER,'material_anchor_result_reader').read_result(Path(path))
def read_input(path):
 ls=Path(path).read_text().splitlines()
 if len(ls)<2: raise ValueError('truncated replay input')
 version=ls[0].strip(); h=ls[1].split()
 if version not in {'RRTMGP_REPLAY_V8','RRTMGP_REPLAY_V9','RRTMGP_REPLAY_V10','RRTMGP_REPLAY_V11'} or len(h)<6: raise ValueError('bad replay header')
 phase=h[0].upper(); nc,nl=int(h[1]),int(h[2]); fields={}; i=2
 while i<len(ls):
  if not ls[i].strip(): i+=1; continue
  words=ls[i].split(); i+=1; name=words[0]; dims=tuple(map(int,words[1:])); n=math.prod(dims); vals=[]
  while len(vals)<n and i<len(ls): vals.extend(float(x.replace('D','E').replace('d','e')) for x in ls[i].split()); i+=1
  if len(vals)!=n or name in fields: raise ValueError(f'bad/truncated input field {name}')
  a=np.asarray(vals,dtype=np.float64).reshape(dims,order='F')
  if not np.isfinite(a).all(): raise ValueError(f'nonfinite input {name}')
  fields[name]=(dims,a)
 if phase not in ('LW','SW') or nc<1 or nl<1: raise ValueError('invalid replay dimensions')
 for n in ('GRAVITY','CP_DRY','PLEV'):
  if n not in fields: raise ValueError(f'missing source identity field {n}')
 return version,phase,nc,nl,fields
def section_bytes(a): return np.asarray(a,dtype='>f8').tobytes(order='F')
def finite_result(r):
 if not r.get('sections') or not all(np.isfinite(a).all() for a in r['sections'].values()): raise ValueError('empty/nonfinite output')
def heating_check(case,res):
 version,phase,nc,nl,fields=read_input(case['input']['path']); s=res['sections']; g=float(fields['GRAVITY'][1].ravel()[0]); cp=float(fields['CP_DRY'][1].ravel()[0]); p=fields['PLEV'][1].ravel()
 errors={}
 for flux,hr in [('UP','HR'),('UPC','HRC')]:
  if flux not in s or hr not in s: raise ValueError(f'missing heating/flux identity fields {flux}/{hr}')
  if s[flux].shape!=(nc,nl+1,1) or s[hr].shape!=(nc,nl,1): raise ValueError(f'bad heating interface/layer shape {flux}/{hr}')
  expected=np.empty((nc,nl),dtype=np.float64)
  for k in range(nl):
   dp=p[k+1]*100.0-p[k]*100.0
   if dp==0: raise ValueError('zero pressure interval')
   expected[:,k]=((((s[flux][:,k+1,0]-s[flux][:,k,0])-s['DN' if flux=='UP' else 'DNC'][:,k+1,0])+s['DN' if flux=='UP' else 'DNC'][:,k,0])*g/(cp*dp)*86400.0)
  err=float(np.max(np.abs(s[hr][:,:,0]-expected)))
  if err>1e-9: raise ValueError(f'{hr} flux-divergence residual {err} > 1e-9 K/day')
  errors[hr]={'max_abs_residual_K_day':err,'limit':1e-9}
 return errors

def baseline_sections_from_ref(case):
 r=read_result(case['historical_reference']['path']); finite_result(r)
 if r['phase']!=case['phase']: raise ValueError('historical baseline phase mismatch')
 return r

def run_comparator(case,fresh):
 m=import_module(ROOT/'build/udm37-phase-diagnostic-contract-pr-work/WRF/test/rrtmgp/compare_column_replay.py','material_anchor_comparator')
 captured=read_result(case['result_context']['path'])
 report=m.compare(captured,fresh)
 if not report.get('passed'): raise ValueError(f'captured-trace compatibility failed: {report.get("failed_sections")}')
 return report

def baseline_validate(case,r):
 finite_result(r); ref=baseline_sections_from_ref(case)
 _,_,nc,nl,_=read_input(case['input']['path'])
 if (r['phase'],r['nc'],r['nl'])!=(case['phase'],nc,nl): raise ValueError('fresh baseline header differs from replay input')
 if set(r['sections'])!=set(ref['sections']): raise ValueError('fresh baseline result section roster differs from same-anchor historical reference')
 expected=plan()['baseline_expected_sections'][case['anchor']][case['phase']]
 if len(r['sections'])!=expected: raise ValueError(f'baseline section count {len(r["sections"])} != {expected}')
 comparison=run_comparator(case,r)
 heat=heating_check(case,r)
 return {'sections':sorted(r['sections']),'section_count':len(r['sections']),'captured_trace_comparison':comparison,'heating':heat}
def plan(): return json.loads(PLAN.read_text())
def band_gpoint_limits(phase, fields, nbnd, ngpt):
 if phase=='SW':
  if 'BAND_LIMS_GPOINT' not in fields: raise ValueError('SW captured input lacks its V9/V11 band-to-gpoint map')
  dims,values=fields['BAND_LIMS_GPOINT']
  if dims!=(2,nbnd): raise ValueError('SW band map has wrong shape')
  a=np.asarray(values,dtype=np.int64).reshape(dims,order='F')
  limits=[(int(a[0,b]),int(a[1,b])) for b in range(nbnd)]
 else:
  from netCDF4 import Dataset
  with Dataset(LWCOEFF,'r') as ds: a=np.asarray(ds.variables['bnd_limits_gpt'][:],dtype=np.int64)
  if a.shape!=(nbnd,2): raise ValueError('LW coefficient band map has wrong shape')
  limits=[(int(lo),int(hi)) for lo,hi in a]
 expect=1
 for lo,hi in limits:
  if lo!=expect or hi<lo: raise ValueError('band-to-gpoint map has a gap or overlap')
  expect=hi+1
 if expect!=ngpt+1: raise ValueError('band-to-gpoint map does not span phase gpoints')
 return limits

def expand_bands(a, limits, ngpt):
 out=np.empty((a.shape[0],a.shape[1],ngpt),dtype=np.float64)
 for b,(lo,hi) in enumerate(limits): out[:,:,lo-1:hi]=a[:,:,b,None]
 return out

def check_moment(name,actual,expected):
 d=np.abs(actual-expected); tol=512*np.finfo(np.float64).eps*np.maximum(1.0,np.abs(expected)); peak=float(d.max())
 if np.any(d>tol): raise ValueError(f'{name} combined optical moment failed (max residual {peak})')
 return {'max_abs_residual':peak,'tolerance':'512*binary64 epsilon*max(1,abs(expected))'}

def positive_validate(case,r,base):
 finite_result(r); phase=case['phase']; _,_,nc,nl,fields=read_input(case['input']['path']); s=r['sections']; bs=base['sections']; ngpt,nbnd=(128,16) if phase=='LW' else (112,14)
 audits={'AUDIT_EXTRA_PRECIP_TAU'} if phase=='LW' else {'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA'}
 if set(s)!=(set(bs)|audits): raise ValueError('increment result must contain paired baseline sections plus exact phase audit additions')
 if r['phase']!=phase or (r['nc'],r['nl'])!=(nc,nl): raise ValueError('increment result header differs from input')
 tau=s['AUDIT_EXTRA_PRECIP_TAU']; raw=s.get('AUDIT_EXTRA_PRECIP_TAU_RAW',tau)
 if np.max(tau)<=0 or np.min(tau)<0 or np.min(raw)<0: raise ValueError('audit tau must be finite, nonnegative, and nonzero')
 if s['AUDIT_EXTRA_PRECIP_TAU'].shape!=(nc,nl,nbnd): raise ValueError('audit tau shape mismatch')
 if phase=='SW' and any(s[n].shape!=(nc,nl,nbnd) for n in ('AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G')): raise ValueError('SW audit optical shape mismatch')
 if phase=='SW' and s['AUDIT_DIRECT_PREDELTA'].shape!=(nc,nl+1,1): raise ValueError('SW audit direct pre-delta shape mismatch')
 if phase=='SW' and (np.any(s['AUDIT_EXTRA_PRECIP_SSA']<0) or np.any(s['AUDIT_EXTRA_PRECIP_SSA']>1) or np.any(np.abs(s['AUDIT_EXTRA_PRECIP_G'])>1)):
  raise ValueError('sidecar SSA/g out of physical bounds')
 # Base inputs/components remain exact; only total optics, all-sky outputs, and audit records may change.
 response={'UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF','TOTAL_TAU','TOTAL_SSA','TOTAL_G','WRF_GLW','WRF_OLR','WRF_GSW','WRF_SWDDIR','WRF_SWDDIF'}
 held=set(bs)-response
 for name in sorted(held):
  if section_bytes(s[name])!=section_bytes(bs[name]): raise ValueError(f'increment changed held component/input {name}')
 for name in ('UPC','DNC','HRC','DIRECTC'):
  if name in bs and section_bytes(s[name])!=section_bytes(bs[name]): raise ValueError(f'clear output changed after post-clear insertion: {name}')
 n_native=plan()['phase_dimensions'][case['anchor']]['native_levels']; active=np.zeros(nl,dtype=bool)
 spec=import_module(VALIDATOR,'material_anchor_sidecar_validator'); decoded=spec.decode(Path(case['sidecar']['path']).read_text()); _,_,nn,_,_,rain,snow=decoded
 if nn!=n_native: raise ValueError('sidecar native extent differs from anchor contract')
 active[:nn]=[rain[0][i]>0 or snow[0][i]>0 for i in range(nn)]
 for name in audits & {'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G'}:
  if np.any(s[name][0,~active,:]!=0): raise ValueError(f'{name} changed outside sidecar-active native levels')
 heat=heating_check(case,r)
 moments={}
 limits=band_gpoint_limits(phase,fields,nbnd,ngpt)
 et=expand_bands(tau,limits,ngpt)
 moments['tau']=check_moment('TOTAL_TAU',s['TOTAL_TAU'],bs['TOTAL_TAU']+et)
 if phase=='SW':
  es=expand_bands(s['AUDIT_EXTRA_PRECIP_SSA'],limits,ngpt); eg=expand_bands(s['AUDIT_EXTRA_PRECIP_G'],limits,ngpt)
  scatter=bs['TOTAL_TAU']*bs['TOTAL_SSA']+et*es; gmom=bs['TOTAL_TAU']*bs['TOTAL_SSA']*bs['TOTAL_G']+et*es*eg
  moments['ssa']=check_moment('TOTAL_SSA',s['TOTAL_SSA'],scatter/np.maximum(3*np.finfo(float).tiny,bs['TOTAL_TAU']+et))
  moments['g']=check_moment('TOTAL_G',s['TOTAL_G'],gmom/np.maximum(3*np.finfo(float).tiny,scatter))
 return {'section_count':len(s),'audit_tau_max':float(tau.max()),'audit_tau_sum':float(tau.sum()),'active_native_levels':int(active.sum()),'held_components_exact':sorted(held),'clear_outputs_held_by_postclear_order':['UPC','DNC','HRC','DIRECTC'],'combined_total_optical_moment_checks':moments,'heating':heat}

LWCOEFF=ROOT/'build/udm-cu-optics-design-work/WRF/run/rrtmgp-gas-lw-g128.nc'
def immutable_snapshot():
 p=plan(); fixed=p['fixed_pins']
 for k,r in fixed.items(): require(r,k)
 b=json.loads(BUILD.read_text()); d=b['postflight_pins']
 if b.get('status')!='BUILD_PASS' or b.get('build_returncode')!=0 or b.get('configure_returncode')!=0 or b.get('solver_invocations')!=0: raise RuntimeError('fresh reference build receipt is not passing')
 if b['executable']!=fixed['executable']: raise RuntimeError('BUILD_PASS executable differs from pinned executable')
 libs=ldd_pins()
 if libs!=sorted(d['runtime_libraries_expected'],key=lambda z:z['path']): raise RuntimeError('live 46-library closure mismatch')
 for group in ('source_pins','source_files','data_assets'):
  for r in d[group]:
   if r.get('kind')=='symlink':
    q=Path(r['path'])
    if not q.is_symlink() or os.readlink(q)!=r['target']: raise RuntimeError(f'build symlink changed {q}')
   else: require(r,f'build {group}')
 for r in d['netcdf_include_modules'].values(): require(r,'NetCDF include/module')
 for k in ('dependency_manifest','compiler','cmake','frozen_table_resolved'): require(d[k],f'build {k}')
 link=d['frozen_table_link']; q=Path(link['path'])
 if link.get('kind')=='symlink':
  if not q.is_symlink() or os.readlink(q)!=link['target']: raise RuntimeError('build table link changed')
 else: require(link,'build table link')
 if pin(TABLE)['sha256']!='8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583': raise RuntimeError('captured replay table changed')
 rt=plan()['runtime_table']; tlink=Path(rt['symlink_path'])
 if not tlink.is_symlink() or str(tlink.resolve())!=rt['symlink_target']: raise RuntimeError('captured table link target changed')
 require({'path':rt['path'],'sha256':rt['sha256'],'size_bytes':rt['size_bytes']},'captured runtime table')
 if os.environ.get('WRF_RRTMGP_FROZEN_TABLE') and Path(os.environ['WRF_RRTMGP_FROZEN_TABLE']).resolve()!=TABLE.resolve(): raise RuntimeError('runtime table environment does not resolve to the captured table')
 r=json.loads(ROSTER.read_text())
 for c in r['planned_calls']:
  for k in ('input_pin','raw_pin','result_context_pin'): require(norm(c[k]),c['call_id']+' '+k)
  if c['sidecar']: require(norm(c['sidecar']),c['call_id']+' sidecar')
 for sc in r['sidecars']:
  for k in ('sidecar','replay_input','raw_capture','saved_adapter_result_context'):
   if isinstance(sc.get(k),dict) and 'path' in sc[k]: require(norm(sc[k]),'sidecar '+k)
 for x in r['inherited_historical_baseline_asset_closure']['pins']: require(norm(x),'historical closure')
 return {'plan':pin(PLAN),'runner':pin(__file__),'build_receipt':pin(BUILD),'build_review':pin(REVIEW),'executable':pin(EXE),'runtime_libraries':libs,'runtime_table':pin(TABLE),'build_expanded_table':d['frozen_table_resolved'],'data_path':str(DATA.resolve()),'data_coefficients':[pin(LWCOEFF),pin(ROOT/'build/udm-cu-optics-design-work/WRF/run/rrtmgp-gas-sw-g112.nc')],'source_pins':d['source_pins'],'source_files':d['source_files'],'data_assets':d['data_assets'],'netcdf_include_modules':d['netcdf_include_modules'],'dependency_manifest':d['dependency_manifest'],'compiler':d['compiler'],'cmake':d['cmake'],'historical_receipt':pin(BASELINE),'roster':pin(ROSTER),'historical_reference_outputs':[pin(c['historical_reference']['path']) for c in plan()['cases']]}
def validate_sidecar(c):
 if c['mode']=='baseline': return None
 cmd=['/usr/bin/python3.12','-B',str(VALIDATOR),'--raw',c['raw']['path'],'--input',c['input']['path'],'--sidecar',c['sidecar']['path'],'--species',c['species'],'--engine-layers',str(read_input(c['input']['path'])[3])]
 cp=subprocess.run(cmd,cwd=ROOT,env=ENV,text=True,capture_output=True,timeout=60)
 if cp.returncode: raise RuntimeError(f'{c["call_id"]} sidecar validator failed: {cp.stderr}')
 o=json.loads(cp.stdout)
 if o.get('status')!='PASS_PYTHON_SIDECAR_RAW_CONTRACT': raise RuntimeError('sidecar validator status not PASS')
 ctx=o['replay_context']; want=c['capture_format']; expected_cu=['CU_POPULATION_POLICY','CU_RADIUS_POLICY','CU_OCCURRENCE_POLICY','CU_LWP','CU_IWP','CU_REL','CU_REI'] if c['CU_POPULATION_POLICY'] else []
 if ctx.get('version')!=want or ctx.get('cu_records_preserved')!=expected_cu: raise RuntimeError('sidecar replay version/CU context mismatch')
 return {'validator_command':cmd,'status':o['status'],'replay_context':ctx,'stdout_sha256':hashlib.sha256(cp.stdout.encode()).hexdigest()}
def prepare():
 p=plan()
 if sha(ROSTER)[0]!=p['roster_sha256'] or sha(BUILD)[0]!=p['build_receipt_sha256']: raise RuntimeError('roster/build receipt pin mismatch')
 snapshot=immutable_snapshot(); calls=[]
 roster=json.loads(ROSTER.read_text())
 historical=json.loads(BASELINE.read_text())
 if historical.get('status')!='PASS_SCOPED_SIX_UNMODIFIED_HELD_CAPTURE_BASELINES' or historical.get('new_models')!=0 or historical.get('new_builds')!=0:
  raise RuntimeError('historical baseline receipt is not the accepted completed no-new-model/build campaign')
 old_by={(x['name'],x['phase']):x for x in historical['cases'] if x.get('status')=='PASS_STRICT_HELD_CAPTURE_BASELINE'}
 if len(old_by)<4: raise RuntimeError('historical baseline receipt lacks accepted anchor/phase controls')
 tc=json.loads(p['fixed_pins']['table_context']['path'] and Path(p['fixed_pins']['table_context']['path']).read_text())
 if tc.get('status')!='PASS_CAPTURE_HASH_AND_ACTIVE_QUERY_RANGES_NO_SOLVER' or tc.get('runtime_table',{}).get('sha256')!=p['runtime_table']['sha256']:
  raise RuntimeError('runtime table context receipt does not authenticate the captured table')
 if not all(x.get('lambda_in_table_range') and x.get('temperature_in_table_range') for row in tc['baselines'] for x in row['species'].values()):
  raise RuntimeError('one or more captured frozen-optics active query ranges are outside the runtime table')
 if roster.get('status')!='PREPARED_NO_SOLVER_OR_BUILD' or roster.get('solver_calls_performed')!=0 or roster.get('calls_planned')!=8: raise RuntimeError('input roster is not preparation-only')
 if [c['call_id'] for c in p['cases']]!=ORDER or len(roster['planned_calls'])!=8: raise RuntimeError('case order/count invalid')
 for i,c in enumerate(p['cases']):
  src=roster['planned_calls'][i]
  if c['call_id']!=src['call_id'] or c['anchor']!=src['anchor'] or c['phase']!=src['phase'] or c['capture_format']!=src['capture_format']: raise RuntimeError('plan case differs from roster')
  for k,rk in [('input','input_pin'),('raw','raw_pin'),('result_context','result_context_pin')]:
   if c[k]!=norm(src[rk]): raise RuntimeError('plan case input pin mismatch')
  if c['sidecar']!=(norm(src['sidecar']) if src['sidecar'] else None): raise RuntimeError('plan sidecar pin mismatch')
  expected_species=src.get('species') or ('rain' if 'rain-' in src['call_id'] else 'snow' if 'snow-' in src['call_id'] else 'none')
  if c['species']!=expected_species or c['CU_POPULATION_POLICY']!=src['CU_POPULATION_POLICY']: raise RuntimeError('plan species/CU mismatch')
  if c['mode']!=('positive' if src['sidecar'] else 'baseline'): raise RuntimeError('plan mode mismatch')
  ref=read_result(c['historical_reference']['path']); finite_result(ref); version,phase,nc,nl,input_fields=read_input(c['input']['path'])
  old_name='winter-native-cu' if c['anchor']=='winter_native_cu' else 'ice_clip_low_cloud_proxy'
  saved=old_by[(old_name,c['phase'])]['output_pins'][0]
  if c['historical_reference']!=norm(saved): raise RuntimeError('historical expected schema/result pin is not receipt-bound')
  header=Path(c['input']['path']).read_text().splitlines()[1].split()
  if phase!=c['phase'] or int(header[3])!=int(c['overlap']) or int(header[4])!=int(c['seed']): raise RuntimeError('input phase/overlap/seed differs from frozen roster')
  frozen=input_fields.get('FROZEN_TABLE_SHA256_BYTES')
  if frozen is None or bytes(int(round(x)) for x in frozen[1].ravel()).decode('ascii')!=p['runtime_table']['sha256']: raise RuntimeError('captured input does not require the pinned original runtime table')
  if input_fields.get('FROZEN_MODE',((),np.array([0])))[1].ravel()[0]!=1: raise RuntimeError('captured input does not use frozen optics mode')
  if (ref['phase'],ref['nc'],ref['nl'])!=(c['phase'],nc,nl): raise RuntimeError('historical reference dimensions mismatch')
  if nl!=p['phase_dimensions'][c['anchor']][c['phase']]: raise RuntimeError('input levels differ from anchor phase contract')
  if (c['CU_POPULATION_POLICY']==1)!=(c['capture_format'] in ('RRTMGP_REPLAY_V10','RRTMGP_REPLAY_V11')): raise RuntimeError('CU policy does not match replay generation')
  if len(ref['sections'])!=p['baseline_expected_sections'][c['anchor']][c['phase']]: raise RuntimeError('historical reference section count mismatch')
  if os.path.lexists(c['output']) or os.path.lexists(c['log']): raise RuntimeError('output collision')
  cmd=[str(EXE),str(DATA.resolve()),c['input']['path'],c['output'],'1','']+([c['sidecar']['path']] if c['sidecar'] else [])
  if cmd!=c['argv']: raise RuntimeError('argv mismatch')
  ctx=validate_sidecar(c)
  calls.append({'call_id':c['call_id'],'argv':cmd,'context_validation':ctx,'expected_baseline_sections':p['baseline_expected_sections'][c['anchor']][c['phase']]})
 if OUT.exists() or LOG.exists() or os.path.lexists(RUN): raise RuntimeError('runtime output tree collision')
 return {'status':'PREFLIGHT_PASS_NO_SOLVER','schema':'cf0-material-anchor-preflight-v1','solver_invocations':0,'snapshot':snapshot,'calls':calls}
def check():
 if PF.exists(): raise RuntimeError('preflight file already exists; preserve, no overwrite')
 out=prepare(); out.update({'plan_sha256':digest(PLAN)[0],'runner_sha256':digest(__file__)[0],'generated_unix':time.time()}); atomic(PF,out); return out

def auth_check(path,runner_hash):
 a=json.loads(Path(path).read_text()); p=plan(); pf=json.loads(PF.read_text())
 expected={'schema':AUTH,'approved':True,'runner_sha256':runner_hash,'plan_sha256':digest(PLAN)[0],'preflight_sha256':digest(PF)[0],
           'roster_sha256':digest(ROSTER)[0],'build_receipt_sha256':digest(BUILD)[0],'executable_sha256':p['executable_sha256'],'case_order':ORDER,'max_solver_invocations':8}
 if any(a.get(k)!=v for k,v in expected.items()): raise RuntimeError('authorization mismatch')
 if pf.get('status')!='PREFLIGHT_PASS_NO_SOLVER' or pf.get('solver_invocations')!=0 or pf.get('runner_sha256')!=runner_hash: raise RuntimeError('no matching preflight')
 return pin(path)
def launch(c,cmd,state,index):
 log=Path(c['log']); out=Path(c['output']); log.parent.mkdir(parents=True,exist_ok=True); out.parent.mkdir(parents=True,exist_ok=True)
 if os.path.lexists(log) or os.path.lexists(out): raise RuntimeError('call output collision')
 start=time.time(); proc=None
 with log.open('xb') as fp:
  try:
   proc=subprocess.Popen(cmd,cwd=ROOT,env=ENV,stdout=fp,stderr=subprocess.STDOUT,start_new_session=True)
   state['solver_invocations']+=1; state['calls'][index].update({'status':'RUNNING','pid':proc.pid,'started_unix':start,'argv':cmd})
   atomic(RUN/'execution.json',state)
   timed=False
   try: rc=proc.wait(timeout=TIMEOUT)
   except subprocess.TimeoutExpired:
    timed=True
    try: os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError: pass
    try: rc=proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
     try: os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError: pass
     rc=proc.wait()
   fp.flush();os.fsync(fp.fileno())
   state['calls'][index].update({'returncode':rc,'timed_out':timed,'ended_unix':time.time(),'status':'CHILD_RC_DURABLE'})
   atomic(RUN/'execution.json',state)
  except BaseException:
   if proc is not None and proc.poll() is None:
    try: os.killpg(proc.pid,signal.SIGTERM)
    except ProcessLookupError: pass
    try: proc.wait(timeout=10)
    except subprocess.TimeoutExpired:
     try: os.killpg(proc.pid,signal.SIGKILL)
     except ProcessLookupError: pass
     proc.wait()
    state['calls'][index].update({'returncode':proc.returncode,'ended_unix':time.time(),'status':'CHILD_INTERRUPTED'})
    atomic(RUN/'execution.json',state)
   elif proc is not None:
    state['calls'][index].update({'returncode':proc.returncode,'ended_unix':time.time(),'status':'CHILD_RC_RECOVERY'})
    atomic(RUN/'execution.json',state)
   raise
 if out.is_file() and not out.is_symlink(): state['calls'][index]['output_pin']=pin(out)
 state['calls'][index]['log_pin']=pin(log); atomic(RUN/'execution.json',state)
 return rc,timed

def execute(authpath):
 snap=immutable_snapshot(); p=plan(); runner_hash=digest(__file__)[0]; authpin=auth_check(authpath,runner_hash); pfpin=pin(PF)
 if prepare()['snapshot']!=snap: raise RuntimeError('preflight snapshot changed')
 if os.path.lexists(RUN): raise RuntimeError('one-use runtime path already exists')
 lock=HERE/'execution.lock'; fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 os.write(fd,json.dumps({'runner_sha256':runner_hash,'authorization':authpin,'claimed_unix':time.time()}).encode()+b'\n');os.fsync(fd);os.close(fd);fsyncdir(HERE)
 RUN.mkdir();OUT.mkdir();LOG.mkdir()
 state={'schema':'cf0-material-anchor-eight-call-execution-v1','status':'RUNNING','runner_sha256':runner_hash,'plan_sha256':digest(PLAN)[0],
        'authorization':authpin,'started_unix':time.time(),'environment':ENV,'initial_snapshot':snap,'model_invocations':0,'solver_invocations':0,
        'calls':[{'call_id':cid,'status':'NOT_STARTED'} for cid in ORDER]}; atomic(RUN/'execution.json',state)
 byid={x['call_id']:x for x in p['cases']}; result_objs={}
 try:
  require(authpin,'execution authorization')
  require(pfpin,'execution preflight')
  if immutable_snapshot()!=snap: raise RuntimeError('pre-call snapshot changed')
  for ix,cid in enumerate(ORDER):
   require(authpin,'execution authorization')
   require(pfpin,'execution preflight')
   c=byid[cid]
   for key in ('input','raw','result_context','historical_reference'):
    require(c[key],cid+'.'+key)
   if c['sidecar']: require(c['sidecar'],cid+'.sidecar')
   ctx=validate_sidecar(c)
   state['calls'][ix].update({'status':'PRECALL_VALIDATED','sidecar_context':ctx,'output':c['output'],'log':c['log']});atomic(RUN/'execution.json',state)
   rc,timed=launch(c,c['argv'],state,ix)
   if timed or rc!=0: raise RuntimeError(f'{cid} failed rc={rc}, timeout={timed}; stopped without retry')
   res=read_result(c['output']); finite_result(res)
   if c['mode']=='baseline':
    checks=baseline_validate(c,res); result_objs[cid]=res
   else:
    base=result_objs.get(c['baseline_call_id'])
    if base is None: raise RuntimeError('paired baseline is not already validated')
    checks=positive_validate(c,res,base); result_objs[cid]=res
   state['calls'][ix]['checks']=checks; state['calls'][ix]['status']='CALL_VALIDATED';atomic(RUN/'execution.json',state)
   if immutable_snapshot()!=snap: raise RuntimeError(f'immutable inputs changed after {cid}')
   require(authpin,'execution authorization'); require(pfpin,'execution preflight')
  require(authpin,'execution authorization'); require(pfpin,'execution preflight')
  state['final_snapshot']=immutable_snapshot()
  for row in state['calls']:
   if row.get('status')!='CALL_VALIDATED' or not row.get('output_pin') or not row.get('log_pin'): raise RuntimeError('not all call outputs were durably validated/pinned')
   require(row['output_pin'],row['call_id']+' final output'); require(row['log_pin'],row['call_id']+' final log')
  if state['final_snapshot']!=snap: raise RuntimeError('final snapshot changed')
  state['status']='ALL_EIGHT_VALIDATED';state['ended_unix']=time.time()
 except BaseException as exc:
  state['status']='FAILED_STOPPED';state['error']=repr(exc);state['ended_unix']=time.time()
  try: state['final_snapshot']=immutable_snapshot();state['final_pins_match_initial']=state['final_snapshot']==snap
  except BaseException as post: state['postflight_error']=repr(post);state['final_pins_match_initial']=False
  atomic(RUN/'execution.json',state); raise
 atomic(RUN/'execution.json',state);return state

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--check',action='store_true');ap.add_argument('--execute',action='store_true');ap.add_argument('--authorization',type=Path);a=ap.parse_args()
 if a.execute:
  if a.authorization is None: raise RuntimeError('separate authorization is required')
  r=execute(a.authorization);print(json.dumps({'status':r['status'],'solver_invocations':r['solver_invocations']}));return 0
 if a.check:
  r=check();print(json.dumps({'status':r['status'],'runner_sha256':r['runner_sha256'],'solver_invocations':0}));return 0
 print('preparation only; use --check or --execute with separate authorization',file=sys.stderr);return 2
if __name__=='__main__':
 try: raise SystemExit(main())
 except Exception as e: print('RUNNER_ERROR: '+repr(e),file=sys.stderr); raise
