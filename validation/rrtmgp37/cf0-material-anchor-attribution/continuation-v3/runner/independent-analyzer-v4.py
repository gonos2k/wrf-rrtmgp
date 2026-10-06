#!/usr/bin/env python3
"""Independent offline audit of the eight captured-column CF0 sidecar calls.

No solver/build is invoked. The script reads the already-pinned reference outputs,
recomputes the precipitation optical tuples from the compiled helper's documented
coefficients/operation order, reconstructs the pre-delta direct beam, checks
band-to-g-point aggregate moments and flux-divergence heating, and compares held
sections by exact storage bytes.
"""
from __future__ import annotations
import hashlib, importlib.util, json, math, os, sys
from pathlib import Path
import numpy as np
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=ROOT/'build/udm37-cf0-material-anchor-independent-terminal-v1'
ROSTER=ROOT/'build/udm37-cf0-material-anchor-inputs-v1/roster.json'
V1=ROOT/'build/udm37-cf0-material-anchor-runtime-v1'
CONT=ROOT/'build/udm37-cf0-material-anchor-continuation-v3'
EXEC1=V1/'run-v1/execution.json'; EXEC6=CONT/'run-v3/execution.json'
PLAN1=V1/'plan.json'; PLAN6=CONT/'plan.json'
READER=ROOT/'build/cf0-cu-src-v1/WRF/test/rrtmgp/compare_column_replay.py'
REFSRC=ROOT/'build/cf0-cu-src-v1/WRF/test/rrtmgp/reference_column.f90'
PRODSRC=ROOT/'build/cf0-cu-src-v1/WRF/phys/module_ra_rrtmgp_precip.F'
BUILD=ROOT/'build/cf0-cu-build-runner-v2/execution.json'
LWCOEFF=ROOT/'build/udm-cu-optics-design-work/WRF/run/rrtmgp-gas-lw-g128.nc'

# These are the fields allowed to differ when an audit-only optical population
# is inserted before the all-sky solve. Everything else common to baseline and
# increment must be byte-identical. Clear-sky outputs are separately exact.
RESPONSE={'UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF',
          'TOTAL_TAU','TOTAL_SSA','TOTAL_G','WRF_GLW','WRF_OLR','WRF_GSW',
          'WRF_SWDDIR','WRF_SWDDIF'}
AUDIT_LW={'AUDIT_EXTRA_PRECIP_TAU'}
AUDIT_SW={'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW',
          'AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA'}

def sha(path):
 h=hashlib.sha256(); n=0
 with Path(path).open('rb') as f:
  while True:
   b=f.read(1<<20)
   if not b: break
   h.update(b); n+=len(b)
 return h.hexdigest(),n

def pin(path):
 h,n=sha(path); return {'path':str(Path(path).resolve()),'sha256':h,'size_bytes':n}

def need_pin(record,label):
 p=Path(record['path'])
 if not p.is_file() or sha(p)!=(record['sha256'],record.get('size_bytes',record.get('bytes'))):
  raise ValueError(f'{label}: pinned file changed: {p}')

def load_py(path,name):
 spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec)
 sys.modules[name]=mod; spec.loader.exec_module(mod); return mod

reader=load_py(READER,'cf0_independent_result_reader')

def input_file(path):
 lines=Path(path).read_text().splitlines()
 if len(lines)<2: raise ValueError('truncated replay input')
 magic=lines[0].strip(); head=lines[1].split()
 if magic not in {f'RRTMGP_REPLAY_V{i}' for i in (8,9,10,11)} or len(head)<4:
  raise ValueError(f'unsupported input header: {magic}')
 phase=head[0].upper(); nc,nl,overlap=map(int,head[1:4]); seed=int(head[4])
 fields={}; i=2
 while i<len(lines):
  if not lines[i].strip(): i+=1; continue
  w=lines[i].split(); i+=1; name=w[0]; shape=tuple(map(int,w[1:])); n=math.prod(shape); vals=[]
  while len(vals)<n and i<len(lines):
   vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split()); i+=1
  if len(vals)!=n or name in fields: raise ValueError(f'malformed/duplicate input field {name}')
  a=np.asarray(vals,dtype=np.float64).reshape(shape,order='F')
  if not np.isfinite(a).all(): raise ValueError(f'nonfinite input {name}')
  fields[name]=a
 if phase not in ('LW','SW') or nc!=1 or nl<1: raise ValueError('unexpected replay dimensions')
 return {'magic':magic,'phase':phase,'nc':nc,'nl':nl,'overlap':overlap,'seed':seed,'fields':fields}

def sidecar(path):
 lines=Path(path).read_text().splitlines()
 if len(lines)<4 or lines[0].strip()!='RRTMGP_CF0_PRECIP_AUDIT_V1': raise ValueError('bad sidecar magic')
 h=lines[1].split(); phase=h[0].upper(); nc,native,species=map(int,h[1:4]); occ=float(h[4]); unit=lines[2].strip()
 if unit!='PATH_UNITS_G_M2' or nc!=1 or occ!=1: raise ValueError('bad sidecar unit/column/occurrence')
 out={}; i=3
 while i<len(lines):
  if not lines[i].strip(): i+=1; continue
  w=lines[i].split(); i+=1; name=w[0]; sh=tuple(map(int,w[1:])); n=math.prod(sh); vals=[]
  while len(vals)<n and i<len(lines): vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split()); i+=1
  if len(vals)!=n or name in out: raise ValueError('bad sidecar record')
  out[name]=np.asarray(vals,dtype=np.float64).reshape(sh,order='F')
 if set(out)!={'AUDIT_RWP_GRID','AUDIT_SWP_GRID'}: raise ValueError('sidecar path record set differs')
 if any(a.shape!=(1,native) for a in out.values()): raise ValueError('sidecar native path shape mismatch')
 if any((not np.isfinite(a).all()) or (a<0).any() for a in out.values()): raise ValueError('invalid sidecar paths')
 return phase,native,species,out

def source_precision_constants():
 # The source arrays use unsuffixed default-real literals assigned to wp.
 f32=lambda xs: np.asarray(xs,dtype=np.float32).astype(np.float64)
 return {
 'b0r':f32([.496,.466,.437,.416,.391,.374,.352,.183,.048,.012,0.,0.,0.,0.]),
 'b0s':f32([.460,.460,.460,.460,.460,.460,.460,.460,0.,0.,0.,0.,0.,0.]),
 'b1s':f32([0.,0.,0.,0.,0.,0.,0.,0.,1.62e-5,1.62e-5,0.,0.,0.,0.]),
 'c0r':f32([.980,.975,.965,.960,.955,.952,.950,.944,.894,.884,.883,.883,.883,.883]),
 'c0s':f32([.970,.970,.970,.970,.970,.970,.970,.970,.970,.970,.700,.700,.700,.700])}
C=source_precision_constants()

def expected_lw(rain,snow,res):
 nr,nl=rain.shape; out=np.zeros((nr,nl,16),dtype=np.float64)
 for c in range(nr):
  for k in range(nl):
   tr=0.33e-3*rain[c,k]
   ts=1.5*1.05756*snow[c,k]/res[c,k] if snow[c,k]>0 and res[c,k]>10 else 0.
   out[c,k,:]=tr+ts
 return out

def expected_sw(rain,snow,res):
 nr,nl=rain.shape; nb=14
 tau=np.zeros((nr,nl,nb)); raw=np.zeros_like(tau); ssa=np.zeros_like(tau); gg=np.zeros_like(tau)
 for c in range(nr):
  for k in range(nl):
   tr=rain[c,k]*3.07e-3
   ts=snow[c,k]*1.09087*(1.5/(1.0315*res[c,k])) if snow[c,k]>0 and res[c,k]>10 else 0.
   for b in range(nb):
    sr=tr*(1.-C['b0r'][b]); ar=sr*C['c0r'][b]
    ss=ts*(1.-(C['b0s'][b]+C['b1s'][b]*1.0315*res[c,k])); ass=ss*C['c0s'][b]
    tp=max(1.e-12,tr+ts); sp=max(1.e-12,sr+ss); ap=max(1.e-12,ar+ass)
    asymw=ap/max(1.e-12,sp); ssaw=min(1.-1.e-6,sp/tp)
    raw[c,k,b]=tp; za2=ssaw*asymw*asymw
    tau[c,k,b]=(1.-za2)*tp; ssa[c,k,b]=(ssaw-za2)/(1.-za2); gg[c,k,b]=asymw/(1.+asymw)
 # The adapter's audit gate zeros all audit tuples on layers with no selected path.
 inactive=(rain==0.)&(snow==0.)
 for a in (tau,raw,ssa,gg): a[inactive,:]=0.
 return tau,raw,ssa,gg

def assert_close(label,actual,expected,ulps=24,absolute_floor=2e-15):
 a=np.asarray(actual,dtype=np.float64); e=np.asarray(expected,dtype=np.float64)
 if a.shape!=e.shape: raise ValueError(f'{label}: shape {a.shape} != {e.shape}')
 if not np.isfinite(a).all() or not np.isfinite(e).all(): raise ValueError(f'{label}: nonfinite')
 scale=np.maximum(np.abs(a),np.abs(e)); tol=np.maximum(absolute_floor,ulps*np.spacing(np.maximum(scale,1.0)))
 d=np.abs(a-e); worst=float(np.max(d)) if d.size else 0.; ratio=float(np.max(d/tol)) if d.size else 0.
 if np.any(d>tol): raise ValueError(f'{label}: residual {worst} exceeds {ulps}-ULP bound; normalized {ratio}')
 return {'shape':list(a.shape),'max_abs_residual':worst,'max_normalized_residual':ratio,'ulps':ulps,'absolute_floor':absolute_floor}

def exact(a,b):
 a=np.asarray(a); b=np.asarray(b)
 return a.shape==b.shape and a.dtype==b.dtype and a.tobytes(order='F')==b.tobytes(order='F')

def audit_paths(call,inp):
 sc=call['sidecar']; phase,native,species,p=sidecar(sc['path'])
 if phase!=inp['phase'] or species!=(1 if call['species']=='rain' else 2):
  raise ValueError(call['call_id']+': sidecar identity mismatch')
 nf=inp['nl']; f=inp['fields']; rain=np.zeros((1,nf)); snow=np.zeros((1,nf))
 rain[:,:native]=p['AUDIT_RWP_GRID']; snow[:,:native]=p['AUDIT_SWP_GRID']
 cf=f['CF']
 active=(rain>0)|(snow>0)
 if np.any(active & (cf!=0.)): raise ValueError(call['call_id']+': sidecar path outside exact CF=0')
 if call['species']=='rain' and np.any(snow): raise ValueError('rain sidecar carries snow path')
 if call['species']=='snow' and np.any(rain): raise ValueError('snow sidecar carries rain path')
 if (rain<0).any() or (snow<0).any(): raise ValueError('negative sidecar path')
 if native>nf: raise ValueError('native sidecar extent exceeds engine levels')
 if 'NATIVE_DRY_LAYER_MASS_KG_M2' in f and f['NATIVE_DRY_LAYER_MASS_KG_M2'].shape[-1]!=native:
  raise ValueError(call['call_id']+': sidecar native extent differs from captured dry-mass extent')
 # The replay field named RWP/SWP is the pre-existing precipitation-optics
 # input; it is not the native UDM mixing-ratio source. Do not conflate it with
 # the separately audited g m-2 sidecar path.
 return rain,snow,{'native_levels':native,'active_native_levels':int(active.sum()),
   'active_k_1based':(np.where(active[0])[0]+1).tolist(),'path_sum_g_m2':float((rain+snow).sum()),
   'path_units':'g m-2','native_q_comparison':'not inferred from legacy RWP/SWP replay fields'}

def gpoint_band_map(fields,nb,ng):
 a=fields['BAND_LIMS_GPOINT'].astype(np.int64)
 if a.shape!=(2,nb): raise ValueError('band map shape mismatch')
 out=np.empty(ng,dtype=np.int64)
 expected=1
 for b in range(nb):
  lo,hi=map(int,a[:,b])
  if lo!=expected or hi<lo or hi>ng: raise ValueError('band intervals not contiguous')
  out[lo-1:hi]=b; expected=hi+1
 if expected!=ng+1: raise ValueError('band intervals do not cover g-points')
 return out

def expand_bands(values,band_map,ng):
 if values.shape[-1]!=len(np.unique(band_map)): raise ValueError('band/g-point expansion shape mismatch')
 return values[:,:,band_map]

def direct_reconstruction(inp,base,inc,raw_tau_band):
 f=inp['fields']; nc,nl=inp['nc'],inp['nl']; ng=f['TOA_GPOINT'].shape[-1]
 bands=gpoint_band_map(f,14,ng); mu=float(f['MU0'].ravel()[0]); overlap=inp['overlap']
 if mu<=0: raise ValueError('SW audit direct diagnostic requires positive mu0')
 # The extra raw precipitation extinction is gray (identical in each SW band).
 # Therefore the entire pre-delta direct profile is multiplied by one exact
 # Beer-Lambert factor per interface. Use the fresh same-executable baseline
 # profile as the unperturbed beam; this avoids reconstructing its absolute
 # extinction from default-real-rounded RAW_GAS/CLOUD trace arrays.
 base_record=base['sections']['DIRECT_PREDELTA'][0,:,0]
 audit_record=inc['sections']['AUDIT_DIRECT_PREDELTA'][0,:,0]
 if base_record.shape!=(nl+1,) or audit_record.shape!=(nl+1,): raise ValueError('direct profile extent mismatch')
 if not np.array_equal(raw_tau_band, np.repeat(raw_tau_band[:,:,:1],raw_tau_band.shape[-1],axis=2)):
  raise ValueError('source-derived added raw precipitation tau is not gray across SW bands')
 layer_raw=raw_tau_band[0,:,0]
 cumulative=np.zeros(nl+1,dtype=np.float64)
 for k in range(nl-1,-1,-1): cumulative[k]=cumulative[k+1]+layer_raw[k]
 checked=[]
 for k in range(nl+1):
  bval=float(base_record[k]); aval=float(audit_record[k])
  if bval<0 or aval<0: raise ValueError('negative direct pre-delta flux')
  expected=bval*math.exp(-cumulative[k]/mu)
  tol=max(2.e-13,1024*np.spacing(max(1.,abs(expected),abs(aval))))
  residual=abs(aval-expected)
  if residual>tol:
   raise ValueError(f'Beer-Lambert direct mismatch at interface {k}: residual {residual} > {tol}')
  checked.append({'interface_1based':k+1,'cumulative_raw_tau':float(cumulative[k]),
                  'expected_direct':expected,'observed_direct':aval,'abs_residual':residual,'tolerance':tol})
 # At the top interface no overlying sidecar path applies, hence the two
 # top-of-atmosphere direct values must agree to rounding.
 top=float(base_record[nl]); top_a=float(audit_record[nl])
 if abs(top-top_a)>max(5.e-14,64*np.spacing(max(1.,abs(top),abs(top_a)))):
  raise ValueError('audit changed the top direct boundary')
 return {'mu0':mu,'gpoints':ng,'checked_interfaces':len(checked),'beer_lambert_exact_gray_increment':checked,
         'top_direct_baseline':top,'top_direct_audit':top_a,
         'surface_direct_baseline':float(base_record[0]),'surface_direct_audit':float(audit_record[0]),
         'note':'the same-executable baseline pre-delta direct profile is attenuated by the independently recomputed gray raw audit tau; no delta-scaled tau is used'}

def heating(inp,r):
 s=r['sections']; f=inp['fields']; g=float(f['GRAVITY'].ravel()[0]); cp=float(f['CP_DRY'].ravel()[0]); p=f['PLEV'].ravel()*100.
 out={}
 for flux,dn,hr in [('UP','DN','HR'),('UPC','DNC','HRC')]:
  up=s[flux][0,:,0]; down=s[dn][0,:,0]; got=s[hr][0,:,0]
  if len(p)!=len(up) or len(got)!=len(p)-1: raise ValueError(f'{hr} extent mismatch')
  dp=np.diff(p); expected=np.diff(up)-np.diff(down)
  expected=expected*g/(cp*dp)*86400.
  d=np.abs(got-expected); maxd=float(d.max())
  if maxd>1.e-9: raise ValueError(f'{hr} flux divergence residual {maxd} K/day')
  out[hr]={'max_abs_residual_K_day':maxd,'tolerance_K_day':1.e-9,'layers':len(got)}
 return out

def baseline_to_reference(base,case):
 hist=reader.read_result(Path(case['historical_reference']['path']))
 if set(hist['sections'])!=set(base['sections']): raise ValueError(case['call_id']+': baseline historical result section set differs')
 bad=[k for k in hist['sections'] if not exact(hist['sections'][k],base['sections'][k])]
 if bad: raise ValueError(case['call_id']+': fresh baseline differs bitwise from saved reference: '+','.join(bad))
 return {'section_count':len(base['sections']),'all_sections_bitwise_equal_to_saved_reference':True}

def analyze_pair(base_call,inc_call,cases_by_id):
 inp=input_file(base_call['input']['path']); incinp=input_file(inc_call['input']['path'])
 if (inp['phase'],inp['nc'],inp['nl'],inp['seed'],inp['overlap']) != (incinp['phase'],incinp['nc'],incinp['nl'],incinp['seed'],incinp['overlap']):
  raise ValueError('baseline/increment inputs not same-state')
 base=reader.read_result(Path(base_call['output'])); inc=reader.read_result(Path(inc_call['output']))
 for label,r in [('baseline',base),('increment',inc)]:
  if r['phase']!=inp['phase'] or (r['nc'],r['nl'])!=(inp['nc'],inp['nl']): raise ValueError(label+' result/input dimensions mismatch')
  if not r['sections'] or not all(np.isfinite(a).all() for a in r['sections'].values()): raise ValueError(label+' result nonfinite/empty')
 if inc['sections'].keys()!=base['sections'].keys()| (AUDIT_LW if inp['phase']=='LW' else AUDIT_SW):
  raise ValueError('increment sections differ from exact baseline plus audit roster')
 resp=RESPONSE
 held=set(base['sections'])-resp
 changed=[]
 for name in sorted(held):
  if not exact(base['sections'][name],inc['sections'][name]): changed.append(name)
 if changed: raise ValueError('held sections changed: '+','.join(changed))
 clear_names=[n for n in ('UPC','DNC','HRC','DIRECTC') if n in base['sections']]
 clear_changed=[n for n in clear_names if not exact(base['sections'][n],inc['sections'][n])]
 if clear_changed: raise ValueError('clear outputs changed: '+','.join(clear_changed))
 if inc['sections']['HR'].shape!=base['sections']['HR'].shape: raise ValueError('HR dimensions differ')
 rain,snow,pathcheck=audit_paths(inc_call,incinp)
 # Radius is the recorded native RES used by compiled precipitation helper.
 res=incinp['fields']['RES']
 if res.shape!=(1,incinp['nl']): raise ValueError('RES extent differs from input engine levels')
 if inp['phase']=='LW':
  expected=expected_lw(rain,snow,res)
  observed=inc['sections']['AUDIT_EXTRA_PRECIP_TAU']
  optical={'AUDIT_EXTRA_PRECIP_TAU':assert_close('LW audit tau from captured paths/radius',observed,expected,ulps=16,absolute_floor=2e-15)}
  raw_tau=expected
 else:
  et,er,es,eg=expected_sw(rain,snow,res)
  optical={}
  for n,e in [('AUDIT_EXTRA_PRECIP_TAU',et),('AUDIT_EXTRA_PRECIP_TAU_RAW',er),('AUDIT_EXTRA_PRECIP_SSA',es),('AUDIT_EXTRA_PRECIP_G',eg)]:
   optical[n]=assert_close('independent SW '+n,inc['sections'][n],e,ulps=16,absolute_floor=2e-15)
  raw_tau=er
  limits=gpoint_band_map(incinp['fields'],14,112)
  ex_tau=expand_bands(et,limits,112); ex_ssa=expand_bands(es,limits,112); ex_g=expand_bands(eg,limits,112)
  bs=base['sections']; xs=inc['sections']
  total_tau=bs['TOTAL_TAU']+ex_tau
  scatter=bs['TOTAL_TAU']*bs['TOTAL_SSA']+ex_tau*ex_ssa
  gmom=bs['TOTAL_TAU']*bs['TOTAL_SSA']*bs['TOTAL_G']+ex_tau*ex_ssa*ex_g
  optical['TOTAL_TAU_moment']=assert_close('combined tau',xs['TOTAL_TAU'],total_tau,ulps=128)
  denom=np.maximum(3*np.finfo(np.float64).tiny,total_tau)
  optical['TOTAL_SSA_moment']=assert_close('combined scattering moment',xs['TOTAL_SSA'],scatter/denom,ulps=128)
  gden=np.maximum(3*np.finfo(np.float64).tiny,scatter)
  optical['TOTAL_G_moment']=assert_close('combined asymmetry moment',xs['TOTAL_G'],gmom/gden,ulps=128)
  optical['SW_band_to_gpoint_map']={'band_count':14,'gpoint_count':112,'first_gpoint_by_band':(np.where(np.r_[True,limits[1:]!=limits[:-1]])[0]+1).tolist()}
  optical['direct_beer_lambert']=direct_reconstruction(incinp,base,inc,raw_tau)
 heat=heating(incinp,inc)
 response_delta={}
 for name in sorted(RESPONSE & set(base['sections'])):
  a=base['sections'][name]; b=inc['sections'][name]
  if a.shape!=b.shape: raise ValueError('response shape changed: '+name)
  d=b-a
  response_delta[name]={'max_abs':float(np.max(np.abs(d))), 'mean_signed':float(np.mean(d)), 'shape':list(d.shape)}
 return {'call_id':inc_call['call_id'],'anchor':inc_call['anchor'],'phase':inp['phase'],'species':inc_call['species'],
         'sidecar_paths':pathcheck,'baseline_against_saved_reference':baseline_to_reference(base,base_call),
         'held_sections_exact':sorted(held),'clear_outputs_exact':clear_names,'optical_checks':optical,
         'heating_checks':heat,'response_deltas':response_delta,
         'baseline_pin':pin(base_call['output']),'increment_pin':pin(inc_call['output']),
         'input_pin':pin(inc_call['input']['path']),'raw_pin':pin(inc_call['raw']['path']),
         'sidecar_pin':pin(inc_call['sidecar']['path'])}

def main():
 plan1=json.loads(PLAN1.read_text()); plan6=json.loads(PLAN6.read_text())
 e1=json.loads(EXEC1.read_text()); e6=json.loads(EXEC6.read_text()); roster=json.loads(ROSTER.read_text())
 build=json.loads(BUILD.read_text()); post=build.get('postflight_pins',{})
 if build.get('status')!='BUILD_PASS' or build.get('build_returncode')!=0 or build.get('solver_invocations')!=0:
  raise ValueError('pinned reference build receipt is not successful/no-solver')
 compiled_source_files={x['path']:x for x in post.get('source_files',[])}
 ref_record=compiled_source_files.get(str(REFSRC))
 if ref_record is None: raise ValueError(f'actual compiled reference source is absent from build source_files: {REFSRC}')
 need_pin(ref_record,'actual compiled reference source')
 # The helper is part of the immutable linked-source manifest, not the small
 # postflight source_files list of changed test-package files. Verify its
 # actual compiled-tree copy byte-identical to the source-manifest record.
 precip_sha,precip_n=sha(PRODSRC)
 precip_record=next((x for x in post.get('source_pins',[]) if x['path'].endswith('/WRF/phys/module_ra_rrtmgp_precip.F')),None)
 if precip_record is None or (precip_sha,precip_n)!=(precip_record['sha256'],precip_record['size_bytes']):
  raise ValueError('actual compiled-tree precipitation helper does not match immutable linked-source manifest')
 compiled_sources=[{'role':'actual compiled reference_column source_files record',**ref_record},
                   {'role':'actual compiled-tree precip helper; hash matched linked-source manifest',
                    'path':str(PRODSRC.resolve()),'sha256':precip_sha,'size_bytes':precip_n,
                    'linked_source_manifest_record':precip_record}]
 if e1.get('status')!='FAILED_STOPPED' or e1.get('solver_invocations')!=2:
  raise ValueError('historical two-call failure receipt changed')
 if e6.get('status')!='ALL_SIX_NEW_CALLS_VALIDATED' or e6.get('solver_invocations')!=6 or e6.get('new_solver_invocations')!=6:
  raise ValueError('six-call continuation is not terminal PASS')
 if len(plan1['cases'])!=8 or len(plan6['cases'])!=6 or roster.get('solver_calls_performed')!=0:
  raise ValueError('frozen roster/call count mismatch')
 # First two successful children were reused, not run again. Independently validate saved files.
 v1cases={c['call_id']:c for c in plan1['cases']}
 c1exec={x['call_id']:x for x in e1['calls']}
 c6plan={c['call_id']:c for c in plan6['cases']}; c6exec={x['call_id']:x for x in e6['calls']}
 rows=[]
 for c in plan1['cases'][:2]:
  q=c1exec[c['call_id']]
  if q.get('returncode')!=0 or q.get('output_pin') is None: raise ValueError('reused first-two output lacks durable successful child record')
  if sha(c['output'])!=(q['output_pin']['sha256'],q['output_pin']['size_bytes']): raise ValueError('first-two output changed')
 for c in plan6['cases']:
  q=c6exec[c['call_id']]
  if q.get('status')!='CALL_VALIDATED' or q.get('returncode')!=0: raise ValueError('continuation case not CALL_VALIDATED')
  if sha(c['output'])!=(q['output_pin']['sha256'],q['output_pin']['size_bytes']): raise ValueError('continuation output changed')
 calls={**{c['call_id']:c for c in plan1['cases'][:2]},**c6plan}
 for c in list(plan1['cases'][:2])+list(plan6['cases']):
  for key in ('input','raw','result_context','historical_reference'):
   if key in c: need_pin(c[key],c['call_id']+' '+key)
  if c.get('sidecar'): need_pin(c['sidecar'],c['call_id']+' sidecar')
  execution_row=(c6exec if c['call_id'] in c6exec else c1exec)[c['call_id']]
  for file_key in ('output_pin','log_pin'):
   if execution_row.get(file_key): need_pin(execution_row[file_key],c['call_id']+' '+file_key)
 # Rebind actual output/log paths from cases and pair per anchor/phase.
 for anchor,species in [('winter_native_cu','rain'),('material_cf0_snow_low_cloud','snow')]:
  for phase in ('LW','SW'):
   base_id=f'{anchor}-{phase.lower()}-baseline'
   inc_id=f'{anchor}-{phase.lower()}-{species}-increment'
   b=dict(calls[base_id]); i=dict(calls[inc_id])
   # V1/continuation plan paths differ; output/input/raw records are each frozen in the chosen call.
   rows.append(analyze_pair(b,i,calls))
 receipt={
  'schema':'cf0-material-anchor-independent-terminal-review-v1',
  'status':'PASS_SCOPED_INDEPENDENT_OPTICS_DIRECT_HEATING_AND_HELD_FIELDS',
  'scope':'four prescribed occurrence-one single-species sidecar increments on two captured one-column states; no domain or physical-policy inference',
  'independent_checker_solver_calls':0,'builds':0,'forecasts':0,
  'historical_process_accounting':{'original_v1_children':2,'continuation_v3_children':6,
    'total_distinct_reference_children':8,'original_v1_execution_failure_preserved':True,
    'original_v1_failure_reason':'the old result parser rejected the positive LW audit section after its child returned 0'},
  'historical_v1_failure_preserved':pin(EXEC1),
  'continuation_execution':pin(EXEC6),'continuation_terminal_receipt':pin(CONT/'root-tool-terminal-receipt-v1.json'),
  'roster':pin(ROSTER),'reference_reader':pin(READER),'reference_column_source':pin(REFSRC),
  'production_precip_source':pin(PRODSRC),'compiled_source_records':compiled_sources,
  'build_receipt':pin(BUILD),'analyzer':pin(__file__),
  'four_pairs':rows,
  'limitations':['reference implementation is a transcribed independent optical formula, not external optical truth; source also carries the same precip formula',
                 'occurrence=1 on CF=0 is an experimental sidecar counterfactual, not production policy',
                 'only two single-column states; no domain-wide bound or forecast impact claim']}
 return receipt

def main_cli():
 out=HERE/'independent-terminal-review-v4.json'
 if out.exists(): raise SystemExit('output collision; refusing to overwrite')
 data=main(); tmp=out.with_suffix('.json.tmp')
 tmp.write_text(json.dumps(data,sort_keys=True,indent=2,allow_nan=False)+'\n'); os.replace(tmp,out)
 print(json.dumps({'status':data['status'],'review':str(out),'pairs':len(data['four_pairs'])}))
if __name__=='__main__': main_cli()
