#!/usr/bin/env python3
"""One-use two-call same-state SW prepared-cloud band-swap diagnostic.

Default execution is a read-only preflight. The two standalone calls require an
independent root authorization and are intentionally not run while preparing.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, signal, subprocess, sys, time
from pathlib import Path
import numpy as np

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=ROOT/'build/udm37-exact-band-cloud-swap-runtime-v2'
PLAN=HERE/'plan.json'; PREFLIGHT=HERE/'preflight-v3.json'; PREP=ROOT/'build/udm37-same-call-exact-band-cloud-swap-v4/prepared'
PREP_PLAN=PREP/'plan-inputs.json'; GENERATOR=PREP/'generate.py'
RUN=HERE/'run-v1'; OUT=RUN/'outputs'; LOG=RUN/'logs'; TIMEOUT=180
EXE=ROOT/'build/cf0-cu-build-v1/cmake-build/reference_column'
BUILD_RECEIPT=ROOT/'build/cf0-cu-build-runner-v2/execution.json'
BUILD_REVIEW=ROOT/'build/udm37-rrtmg4-export-independent-review-v1/cf0-cu-postbuild-review-v1/review.json'
BASE_RUN=ROOT/'build/udm37-cf0-retained-cu-runtime-v1/run-v1'
BASE_EXEC=BASE_RUN/'execution.json'; BASE_RESULT=BASE_RUN/'outputs/baseline-sw.result'
ASSESSMENT=ROOT/'build/udm37-rrtmg4-export-independent-review-v1/exact-band-cloud-swap-assessment-v1.json'
TABLE=ROOT/'build/udm37-frozen-planck-coverage-v1/runs/frozen-planck-150-330-step5-plus233-v1/frozen-ice-psd-moments.nc'
DATA=ROOT/'build/udm-cu-optics-design-work/WRF/run'
AUTH_SCHEMA='exact-band-cloud-swap-two-call-authorization-v1'
CASE_ORDER=['control-full-prepared','legacy-exact-band-k30-32']
BASELINE_SECTIONS={
 'GAS_COL_DRY','GAS_TAU','GAS_SSA','GAS_G','CLOUD_TAU','CLOUD_SSA','CLOUD_G',
 'NATIVE_CLOUD_TAU','NATIVE_CLOUD_SSA','NATIVE_CLOUD_G','CU_CLOUD_TAU','CU_CLOUD_SSA','CU_CLOUD_G',
 'CU_RL_USED','CU_DI_USED','PRECIP_TAU','PRECIP_SSA','PRECIP_G','PREPARED_TAU','PREPARED_SSA','PREPARED_G',
 'FROZEN_TAU','FROZEN_SSA','FROZEN_G','GRAUPEL_TAU_EXT','GRAUPEL_TAU_SCA','GRAUPEL_TAU_SCA_G',
 'HAIL_TAU_EXT','HAIL_TAU_SCA','HAIL_TAU_SCA_G','GAS_TAU','GAS_SSA','GAS_G',
 'MASK','TOTAL_TAU','TOTAL_SSA','TOTAL_G','RL_USED','DI_USED','DS_USED',
 'UP','DN','HR','UPC','DNC','HRC','DIRECT','DIFFUSE','DIRECTC','VISDIR','VISDIF','NIRDIR','NIRDIF',
 'DIRECT_PREDELTA','DIRECTC_PREDELTA','VISDIR_PREDELTA','NIRDIR_PREDELTA'
}
RESPONSE={'PREPARED_TAU','PREPARED_SSA','PREPARED_G','TOTAL_TAU','TOTAL_SSA','TOTAL_G',
          'UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF'}
ENV={'PATH':'/usr/local/bin:/usr/bin:/bin',
     'LD_LIBRARY_PATH':str(ROOT/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu',
     'NETCDF':str(ROOT/'build/deps/netcdf'),'LANG':'C','LC_ALL':'C','TMPDIR':'/tmp',
     'OPENBLAS_NUM_THREADS':'1','WRF_RRTMGP_FROZEN_TABLE':str(TABLE)}

def sha(path):
    h=hashlib.sha256(); n=0
    with Path(path).open('rb') as f:
        while b:=f.read(1<<20): h.update(b); n+=len(b)
    return h.hexdigest(),n
def pin(path):
    h,n=sha(path); return {'path':str(Path(path).resolve()),'sha256':h,'size_bytes':n}
def resolve_root_path(path):
    p=Path(path)
    return p if p.is_absolute() else ROOT/p
def write_atomic(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True); tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(obj,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path); fd=os.open(path.parent,os.O_RDONLY|os.O_DIRECTORY); os.fsync(fd); os.close(fd)
def require(rec,label):
    p=Path(rec['path'])
    if not p.is_file() or sha(p)!=(rec['sha256'],rec['size_bytes']): raise RuntimeError(f'{label} pin mismatch: {p}')
def resolved_ldd():
    cp=subprocess.run(['/usr/bin/ldd',str(EXE)],env=ENV,text=True,capture_output=True,check=True)
    out=[]
    for line in cp.stdout.splitlines():
        if '=>' not in line: continue
        tail=line.split('=>',1)[1].strip().split()
        if tail and tail[0].startswith('/'): out.append(pin(Path(tail[0]).resolve()))
    return sorted(out,key=lambda x:x['path'])
def load_json(path): return json.loads(Path(path).read_text())
def load_result(path,reader):
    spec=importlib.util.spec_from_file_location('same_state_result_reader',reader)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    return mod.read_result(Path(path))
def binary(a): return np.asarray(a,dtype='>f8').tobytes(order='F')

def read_replay_input(path):
    lines=Path(path).read_text().splitlines()
    if not lines or lines[0].strip()!='RRTMGP_REPLAY_V11' or len(lines)<2: raise ValueError('expected captured SW V11 input')
    h=lines[1].split()
    if len(h)<3 or h[0].upper()!='SW': raise ValueError('invalid SW replay header')
    nc,nl=int(h[1]),int(h[2]); fields={}; i=2
    while i<len(lines):
        if not lines[i].strip(): i+=1; continue
        head=lines[i].split(); i+=1
        if len(head)<2: raise ValueError('malformed SW input field header')
        dims=tuple(int(x) for x in head[1:]); need=math.prod(dims); vals=[]
        while len(vals)<need and i<len(lines):
            vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split()); i+=1
            if len(vals)>need: raise ValueError(f'oversized input field {head[0]}')
        if len(vals)!=need: raise ValueError(f'bad input field length {head[0]}')
        fields[head[0]]=(dims,np.asarray(vals,dtype=np.float64).reshape(dims,order='F'))
    for name in ('GRAVITY','CP_DRY','PLEV','BAND_LIMS_GPOINT'):
        if name not in fields: raise ValueError(f'input missing {name}')
    return nc,nl,fields

def read_override(path):
    lines=Path(path).read_text().splitlines(); i=0
    if lines[i].strip()!='WRF_SW_OPTICS_OVERRIDE_V1': raise ValueError('override magic mismatch')
    i+=1; dims=tuple(int(x) for x in lines[i].split()); i+=1
    if len(dims)!=3: raise ValueError('override dimensions malformed')
    nc,nl,nb=dims
    head=lines[i].split(); i+=1
    if head!=['BAND_LIMITS','2',str(nb)]: raise ValueError('override band header mismatch')
    n=2*nb; vals=[]
    while len(vals)<n and i<len(lines): vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split()); i+=1
    if len(vals)!=n: raise ValueError('override band values truncated or oversized')
    bounds=np.asarray(vals,dtype=np.float64).reshape((2,nb),order='F')
    arrays={}
    for name in ('TAU','SSA','ASYM'):
        head=lines[i].split(); i+=1
        if head!=[name,str(nc),str(nl),str(nb)]: raise ValueError(f'{name} override shape header mismatch')
        n=nc*nl*nb; vals=[]
        while len(vals)<n and i<len(lines): vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split()); i+=1
        if len(vals)!=n: raise ValueError(f'{name} override values truncated or oversized')
        arrays[name]=np.asarray(vals,dtype=np.float64).reshape((nc,nl,nb),order='F')
    if any(x.strip() for x in lines[i:]): raise ValueError('unexpected trailing override data')
    if not all(np.isfinite(x).all() for x in [bounds,*arrays.values()]): raise ValueError('nonfinite override')
    return {'nc':nc,'nl':nl,'nb':nb,'bounds':bounds,**arrays}

def gas_gpoint_limits(plan_inputs,fields,coeff_path):
    with __import__('netCDF4').Dataset(resolve_root_path(coeff_path),'r') as ds:
        bounds=np.asarray(ds.variables['bnd_limits_wavenumber'][:],dtype=np.float64)
        gpts=np.asarray(ds.variables['bnd_limits_gpt'][:],dtype=np.int64)
    expected=np.asarray(plan_inputs['band_contract']['gas_table_bands_cm-1'],dtype=np.float64)
    expected_gp=np.asarray(plan_inputs['band_contract']['gas_table_gpoint_bounds_1based_inclusive'],dtype=np.int64)
    if not np.array_equal(bounds,expected) or not np.array_equal(gpts,expected_gp): raise ValueError('live SW gas coefficient band/gpoint map differs from prepared plan')
    input_bounds=fields['BAND_LIMS_GPOINT'][1].T.astype(np.int64)
    if not np.array_equal(input_bounds,expected_gp): raise ValueError('captured input band-to-gpoint map differs from coefficient table')
    return [(int(lo),int(hi)) for lo,hi in expected_gp]

def validate_override_pair(control,variant):
    target={(0,k,b) for k in (29,30,31) for b in range(2,14)}
    changed={}
    for field in ('TAU','SSA','ASYM'):
        x=control[field]; y=variant[field]
        if x.shape!=(1,45,14) or y.shape!=x.shape or not np.isfinite(x).all() or not np.isfinite(y).all():
            raise ValueError(f'{field} override shape/finiteness failure')
        ax=np.asarray(x,dtype='>f8').view('>u8'); ay=np.asarray(y,dtype='>f8').view('>u8')
        idx=list(zip(*np.where(ax!=ay)))
        if any(tuple(int(z) for z in i) not in target for i in idx):
            raise ValueError(f'{field} override changed outside selected native layers/bands')
        if len(idx)!=36: raise ValueError(f'{field} override changed {len(idx)} cells, expected all 36 selected cells')
        changed[field]=len(idx)
    return changed

def same_bits(a,b): return np.asarray(a).shape==np.asarray(b).shape and binary(a)==binary(b)
def within_roundoff(actual,expected,label):
    d=np.abs(actual-expected); limit=512*np.finfo(np.float64).eps*np.maximum(1.,np.abs(expected))
    m=float(d.max())
    if np.any(d>limit): raise ValueError(f'{label} optical moment closure failed; max abs residual {m}')
    return {'max_abs_residual':m,'bound':'512*binary64 epsilon*max(1,abs(expected))'}

def check_heating(result,fields,nc,nl,up_name='UP',dn_name='DN',hr_name='HR'):
    s=result['sections']; grav=float(fields['GRAVITY'][1].reshape(-1)[0]); cp=float(fields['CP_DRY'][1].reshape(-1)[0]); plev=fields['PLEV'][1].reshape(-1)
    if len(plev)!=nl+1: raise ValueError('pressure interface count mismatch')
    up=s[up_name][:,:,0]; dn=s[dn_name][:,:,0]; hr=s[hr_name][:,:,0]; expect=np.empty((nc,nl),dtype=np.float64)
    for c in range(nc):
        for k in range(nl):
            dp=plev[k+1]*100.-plev[k]*100.
            expect[c,k]=(((up[c,k+1]-up[c,k])-dn[c,k+1])+dn[c,k])*grav/(cp*dp)*86400.
    residual=float(np.max(np.abs(hr-expect)))
    if residual>1e-9: raise ValueError(f'flux/heating identity residual {residual} K/day')
    return residual

def fixed_snapshot(plan):
    # Check every runtime artifact named by the immutable plan and the fresh build closure.
    for name,rec in plan['fixed_pins'].items(): require(rec,name)
    build=load_json(BUILD_RECEIPT)
    if build.get('status')!='BUILD_PASS' or build.get('build_returncode')!=0 or build.get('configure_returncode')!=0 or build.get('solver_invocations')!=0:
        raise RuntimeError('fresh standalone build receipt is not a clean BUILD_PASS')
    require(plan['fixed_pins']['executable'],'live standalone executable')
    require(plan['fixed_pins']['build_receipt'],'standalone build receipt')
    require(plan['fixed_pins']['build_review'],'independent standalone build review')
    dep=build['postflight_pins']; libs=resolved_ldd()
    if libs!=sorted(dep['runtime_libraries_expected'],key=lambda x:x['path']): raise RuntimeError('live 46-library runtime closure differs from build receipt')
    for rec in dep['data_assets']+dep['source_pins']+dep['source_files']:
        if rec.get('kind')=='symlink':
            p=Path(rec['path'])
            if not p.is_symlink() or os.readlink(p)!=rec['target']: raise RuntimeError(f'build link changed: {p}')
        else: require(rec,'build immutable source/data')
    for rec in dep['netcdf_include_modules'].values(): require(rec,'NetCDF include/module')
    require(dep['dependency_manifest'],'build dependency manifest'); require(dep['compiler'],'Fortran compiler'); require(dep['cmake'],'CMake')
    for rec in (dep['frozen_table_link'],dep['frozen_table_resolved']):
        if rec.get('kind')=='symlink':
            p=Path(rec['path'])
            if not p.is_symlink() or os.readlink(p)!=rec['target']: raise RuntimeError(f'frozen table link changed: {p}')
        else: require(rec,'frozen table path')
    # Validate the parent eight-call campaign and its selected baseline record.
    prev=load_json(BASE_EXEC)
    if prev.get('status')!='ALL_EIGHT_CALLS_VALIDATED' or prev.get('solver_invocations')!=8: raise RuntimeError('same-executable baseline campaign is not complete')
    bcall=next((x for x in prev['calls'] if x['case_id']=='baseline-sw'),None)
    if not bcall or bcall.get('status')!='CALL_VALIDATED' or bcall.get('returncode')!=0: raise RuntimeError('baseline SW call not validated')
    return {'executable':pin(EXE),'build_receipt':pin(BUILD_RECEIPT),'build_review':pin(BUILD_REVIEW),
            'baseline_execution':pin(BASE_EXEC),'baseline_result':pin(BASE_RESULT),'runtime_libraries':libs,
            'source_pins':dep['source_pins'],'source_files':dep['source_files'],'data_assets':dep['data_assets'],
            'netcdf_include_modules':dep['netcdf_include_modules'],'dependency_manifest':dep['dependency_manifest'],
            'compiler':dep['compiler'],'cmake':dep['cmake'],'table_link':dep['frozen_table_link'],
            'table_resolved':dep['frozen_table_resolved'],
            'fixed_paths':{k:v for k,v in plan['fixed_pins'].items()}}

def verify_prepared(plan_inputs):
    if plan_inputs.get('status')!='PREPARED_OFFLINE_NO_SOLVER_CALLS': raise RuntimeError('prepared plan is not offline-only')
    if plan_inputs.get('eligibility',{}).get('band_layer_cells')!=36 or plan_inputs['eligibility'].get('expected_band_layer_cells')!=36:
        raise RuntimeError('prepared exact band-layer scope is not 36 cells')
    if plan_inputs['eligibility'].get('property_assignments')!=108 or plan_inputs['eligibility'].get('expected_property_assignments')!=108:
        raise RuntimeError('prepared property assignment scope is not 108')
    if plan_inputs['scope']['native_layers_1based']!=[30,31,32] or plan_inputs['scope']['phase']!='SW': raise RuntimeError('prepared target scope mismatch')
    if len(plan_inputs['band_contract']['exact_matches'])!=12 or plan_inputs['band_contract']['unmatched_gp_band_indices_1based']!=[1,2]:
        raise RuntimeError('physical exact band joins differ from approved 12-of-14 contract')
    if not all(plan_inputs['offline_negative_controls'].values()): raise RuntimeError('prepared generator negative control failed')

def validate_pair(control_case,variant_case,control,variant,pinputs,reader):
    base=load_result(control_case['output'],reader); var=load_result(variant_case['output'],reader)
    baseline=load_result(BASE_RESULT,reader)
    for label,res in [('control',base),('variant',var),('saved baseline',baseline)]:
        if res.get('phase')!='SW' or res.get('nc')!=1 or res.get('nl')!=45: raise ValueError(f'{label} SW result dimensions mismatch')
        if set(res['sections'])!=BASELINE_SECTIONS: raise ValueError(f'{label} result section roster differs from exact 54-field contract')
        if not all(np.isfinite(x).all() for x in res['sections'].values()): raise ValueError(f'{label} has nonfinite result data')
    if sha(control_case['output'])!=sha(BASE_RESULT) or sha(control_case['output'])[0]!=pinputs['pins']['same_executable_baseline_result']['sha256']:
        raise ValueError('full-prepared control output is not byte-identical to fresh saved SW baseline')
    if Path(control_case['output']).read_bytes()!=BASE_RESULT.read_bytes(): raise ValueError('control whole-file bytes differ from same-executable baseline')
    nc,nl,fields=read_replay_input(resolve_root_path(pinputs['pins']['new_on_trace_input']['path']))
    if (nc,nl)!=(1,45): raise ValueError('capture input dimensions changed')
    overrides={name:read_override(resolve_root_path(pinputs['generated_overrides'][name]['path'])) for name in ('full_baseline_prepared_control','legacy_exact_common_band_swap')}
    control_override=overrides['full_baseline_prepared_control']; swap_override=overrides['legacy_exact_common_band_swap']
    for name,source_name in [('PREPARED_TAU','TAU'),('PREPARED_SSA','SSA'),('PREPARED_G','ASYM')]:
        if not same_bits(base['sections'][name],control_override[source_name]): raise ValueError(f'control override does not reproduce baseline {name}')
        if not same_bits(var['sections'][name],swap_override[source_name]): raise ValueError(f'variant {name} differs from exact prepared override')
    limits=gas_gpoint_limits(pinputs,fields,pinputs['pins']['sw_gas_coefficients_executed_tree']['path'])
    allowed={(0,k,b) for k in (29,30,31) for b in range(2,14)}
    changed={}
    for name in ('PREPARED_TAU','PREPARED_SSA','PREPARED_G'):
        a=base['sections'][name]; b=var['sections'][name]
        if a.shape!=(1,45,14) or b.shape!=a.shape: raise ValueError(f'{name} shape mismatch')
        aa=np.asarray(a,dtype='>f8').view('>u8'); bb=np.asarray(b,dtype='>f8').view('>u8')
        delta=(aa!=bb); bad=[]
        for c,k,band in zip(*np.where(delta)):
            if (int(c),int(k),int(band)) not in allowed: bad.append((int(c),int(k),int(band)))
        if bad: raise ValueError(f'{name} changed outside the 36 allowed band/layer cells: {bad[:8]}')
        changed[name]=int(np.count_nonzero(delta))
    if changed['PREPARED_TAU']<1: raise ValueError('variant changed no prepared cloud optical depth')
    mask=baseline['sections']['MASK']
    if not same_bits(base['sections']['MASK'],mask) or not same_bits(var['sections']['MASK'],mask): raise ValueError('MCICA mask changed across control/variant')
    # The baseline is a complete same-executable reference. Hold every diagnostic/input/clear section
    # exactly; only prepared/total all-sky response sections can change.
    held=BASELINE_SECTIONS-RESPONSE
    for name in held:
        if not same_bits(base['sections'][name],baseline['sections'][name]): raise ValueError(f'control changed held {name}')
        if not same_bits(var['sections'][name],baseline['sections'][name]): raise ValueError(f'variant changed held {name}')
    clear=('UPC','DNC','HRC','DIRECTC','DIRECTC_PREDELTA')
    for name in clear:
        if not same_bits(var['sections'][name],baseline['sections'][name]): raise ValueError(f'clear/pre-delta section changed: {name}')
    # Reconstruct selected native layers and exact matched physical bands. Gas and frozen optics
    # remain baseline; native/CU/precipitation component records are held, while their selected
    # contribution inside the combined PREPARED tuple is replaced by the override.
    gpt_limits=limits
    expected_tau=baseline['sections']['TOTAL_TAU'].copy()
    expected_scatter=baseline['sections']['TOTAL_TAU']*baseline['sections']['TOTAL_SSA']
    expected_gmoment=expected_scatter*baseline['sections']['TOTAL_G']
    oldt=base['sections']['PREPARED_TAU']; newt=var['sections']['PREPARED_TAU']
    olds=base['sections']['PREPARED_SSA']; news=var['sections']['PREPARED_SSA']
    oldg=base['sections']['PREPARED_G']; newg=var['sections']['PREPARED_G']
    selected_gpoints=[]
    for b,(lo,hi) in enumerate(gpt_limits):
        if b<2: continue
        gidx=slice(lo-1,hi); selected_gpoints.extend(range(lo,hi+1))
        for k in (29,30,31):
            if not np.all(mask[0,k,gidx]==1.): raise ValueError(f'selected g-points are not all cloudy at layer {k+1}, band {b+1}')
            dt=newt[0,k,b]-oldt[0,k,b]
            ds=newt[0,k,b]*news[0,k,b]-oldt[0,k,b]*olds[0,k,b]
            dg=newt[0,k,b]*news[0,k,b]*newg[0,k,b]-oldt[0,k,b]*olds[0,k,b]*oldg[0,k,b]
            expected_tau[0,k,gidx]+=dt
            expected_scatter[0,k,gidx]+=ds
            expected_gmoment[0,k,gidx]+=dg
    if len(set(selected_gpoints))!=94: raise ValueError('expected exact selected 94 g-points per each of 3 native layers')
    expected_ssa=expected_scatter/np.maximum(np.finfo(np.float64).tiny,expected_tau)
    expected_g=expected_gmoment/np.maximum(np.finfo(np.float64).tiny,expected_scatter)
    closures={n:within_roundoff(var['sections'][n],e,n) for n,e in [('TOTAL_TAU',expected_tau),('TOTAL_SSA',expected_ssa),('TOTAL_G',expected_g)]}
    heat={'all_sky_max_abs_residual_k_day_minus1':check_heating(var,fields,nc,nl),
          'clear_sky_max_abs_residual_k_day_minus1':check_heating(var,fields,nc,nl,'UPC','DNC','HRC')}
    response_diffs={}
    for name in sorted(RESPONSE):
        a=baseline['sections'][name]; b=var['sections'][name]
        response_diffs[name]={'changed_values':int(np.count_nonzero(a!=b)),'max_abs_delta':float(np.max(np.abs(b-a)))}
    if not any(v['changed_values'] for k,v in response_diffs.items() if k in {'UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF'}):
        raise ValueError('variant produced no all-sky flux/heating response')
    return {'control_output_sha256':sha(control_case['output'])[0],
            'variant_output_sha256':sha(variant_case['output'])[0],
            'control_wholefile_identical_to_saved_baseline':True,
            'variant_changed_prepared_cells':changed,'selected_band_layer_cells':36,
            'selected_gp_count_each_native_layer':94,'combined_total_optics_closure':closures,
            'heating_flux_divergence_residuals':heat,
            'all_sky_response_differences_vs_control':response_diffs,
            'all_nonresponse_fields_exact_to_saved_control':True,
            'interpretation':'same-state prepared SW cloud-array sensitivity only; raw direct-beam bookkeeping is held on its original path and is not a fully self-consistent direct-beam attribution'}

def validate_control(case,pinputs,reader):
    result=load_result(case['output'],reader); baseline=load_result(BASE_RESULT,reader)
    if sha(case['output'])!=sha(BASE_RESULT) or Path(case['output']).read_bytes()!=BASE_RESULT.read_bytes():
        raise ValueError('full-prepared control is not whole-file byte-identical to saved same-executable SW baseline')
    if result.get('phase')!='SW' or result.get('nc')!=1 or result.get('nl')!=45:
        raise ValueError('control result dimensions mismatch')
    if set(result['sections'])!=BASELINE_SECTIONS or set(baseline['sections'])!=BASELINE_SECTIONS:
        raise ValueError('control result section roster differs from exact 54-field contract')
    if not all(np.isfinite(x).all() for x in result['sections'].values()):
        raise ValueError('control result contains nonfinite values')
    override=read_override(resolve_root_path(pinputs['generated_overrides']['full_baseline_prepared_control']['path']))
    for name,src in [('PREPARED_TAU','TAU'),('PREPARED_SSA','SSA'),('PREPARED_G','ASYM')]:
        if not same_bits(result['sections'][name],override[src]): raise ValueError(f'control prepared {name} differs from override')
    for name in BASELINE_SECTIONS-RESPONSE:
        if not same_bits(result['sections'][name],baseline['sections'][name]): raise ValueError(f'control changed held {name}')
    return {'whole_file_baseline_identity':True,'section_count':len(result['sections']),
            'prepared_arrays_match_override_bitwise':True,'held_sections_match_baseline_bitwise':True}

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--check',action='store_true'); ap.add_argument('--execute',action='store_true'); ap.add_argument('--authorization',type=Path); a=ap.parse_args()
    if a.check:
        if os.path.lexists(PREFLIGHT): raise RuntimeError('preflight receipt already exists; preserving it')
        p=preflight(); write_atomic(PREFLIGHT,p); print(json.dumps({'status':p['status'],'solver_invocations':0,'runner_sha256':p['runner_sha256']})); return 0
    if a.execute:
        if not a.authorization: raise RuntimeError('separate root authorization required')
        execute(a.authorization); return 0
    print('preparation only; use --check, then --execute with external authorization',file=sys.stderr); return 2

def preflight():
    if not PLAN.is_file() or not PREP_PLAN.is_file(): raise RuntimeError('frozen runtime/preparation plan missing')
    plan=load_json(PLAN); pp=load_json(PREP_PLAN); verify_prepared(pp)
    this_sha=sha(Path(__file__))[0]
    if plan.get('runner_sha256')!=this_sha or plan.get('prepared_plan_sha256')!=sha(PREP_PLAN)[0]: raise RuntimeError('runner/prepared-plan pin mismatch')
    snap=fixed_snapshot(plan)
    if [c.get('case_id') for c in plan.get('cases',[])]!=CASE_ORDER: raise RuntimeError('runtime case order mismatch')
    if plan.get('data_path')!=str(DATA.resolve()):
        raise RuntimeError('standalone data directory differs from captured SW coefficients')
    prep_pins=pp['pins']; output_names=('full_baseline_prepared_control','legacy_exact_common_band_swap')
    for i,c in enumerate(plan['cases']):
        if c.get('phase')!='SW' or c.get('mode')!=('control' if i==0 else 'variant'):
            raise RuntimeError(f'{c.get("case_id")}: phase/mode mismatch')
        if c.get('input')!=plan['fixed_pins']['capture_input'] or c.get('raw')!=plan['fixed_pins']['capture_raw']:
            raise RuntimeError(f'{c.get("case_id")}: capture input/raw differs from pinned preparation')
        expect_ov=pp['generated_overrides'][output_names[i]]
        if c.get('override')!={'path':str(resolve_root_path(expect_ov['path'])),'sha256':expect_ov['sha256'],'size_bytes':expect_ov['size_bytes']}:
            raise RuntimeError(f'{c.get("case_id")}: override does not match the frozen generated artifact')
        if c.get('output')!=str(OUT/f'{c["case_id"]}.result') or c.get('log')!=str(LOG/f'{c["case_id"]}.log'):
            raise RuntimeError(f'{c.get("case_id")}: output/log path mismatch')
    if os.path.lexists(RUN) or os.path.lexists(HERE/'execution.lock'): raise RuntimeError('runtime output directory or one-use lock already exists')
    for c in plan['cases']:
        if os.path.lexists(c['output']) or os.path.lexists(c['log']): raise RuntimeError('planned case output/log collision')
    if plan.get('timeout_seconds')!=TIMEOUT or plan.get('max_solver_invocations')!=2: raise RuntimeError('runtime bounds differ from approved two-call plan')
    base=load_result(BASE_RESULT,plan['fixed_pins']['result_parser']['path'])
    if base.get('phase')!='SW' or base.get('nc')!=1 or base.get('nl')!=45 or set(base.get('sections',{}))!=BASELINE_SECTIONS:
        raise RuntimeError('saved same-executable SW baseline does not match exact 54-section contract')
    if not all(np.isfinite(x).all() for x in base['sections'].values()): raise RuntimeError('saved SW baseline has nonfinite sections')
    nc,nl,fields=read_replay_input(plan['fixed_pins']['capture_input']['path'])
    if (nc,nl)!=(1,45): raise RuntimeError('pinned SW capture input dimensions mismatch')
    limits=gas_gpoint_limits(pp,fields,plan['fixed_pins']['sw_gas_coefficients']['path'])
    mask=fields.get('MCICA_MASK')
    if mask is None or mask[0]!=(1,45,112): raise RuntimeError('captured MCICA mask has wrong shape')
    for b,(lo,hi) in enumerate(limits):
        if b<2: continue
        for k in (29,30,31):
            if not np.all(mask[1][0,k,lo-1:hi]==1.): raise RuntimeError(f'captured mask is not cloudy in matched band {b+1}, layer {k+1}')
    overrides={key:read_override(plan['fixed_pins'][key]['path']) for key in ('control_override','variant_override')}
    for key,section in [('control_override','PREPARED_TAU'),('variant_override','PREPARED_TAU')]:
        if overrides[key]['TAU'].shape!=(1,45,14): raise RuntimeError(f'{key} prepared dimensions mismatch')
    # Offline-only semantic check: the control is the retained prepared baseline, while the variant
    # differs in exactly the approved 3 layers × 12 matched bands and nowhere else.
    changed=validate_override_pair(overrides['control_override'],overrides['variant_override'])
    if not same_bits(overrides['control_override']['TAU'],base['sections']['PREPARED_TAU']):
        raise RuntimeError('control override is not the exact saved baseline PREPARED_TAU')
    for field,section in [('SSA','PREPARED_SSA'),('ASYM','PREPARED_G')]:
        if not same_bits(overrides['control_override'][field],base['sections'][section]): raise RuntimeError(f'control override is not exact baseline {section}')
    return {'schema':'exact-band-cloud-swap-preflight-v3','status':'PREFLIGHT_PASS_NO_SOLVER','runner_sha256':this_sha,
            'plan_sha256':sha(PLAN)[0],'prepared_plan_sha256':sha(PREP_PLAN)[0],'initial_pins':snap,
            'case_order':CASE_ORDER,'calls':0,'solver_invocations':0,
            'offline_override_check':{'changed_cells_per_property':changed,'allowed_cells':36,'calls':0}}

def authorize(authpath):
    plan=load_json(PLAN); a=load_json(authpath); pf=load_json(PREFLIGHT)
    req={'schema':AUTH_SCHEMA,'approved':True,'runner_sha256':sha(Path(__file__))[0],
         'plan_sha256':sha(PLAN)[0],'preflight_sha256':sha(PREFLIGHT)[0],
         'prepared_plan_sha256':sha(PREP_PLAN)[0],'executable_sha256':plan['fixed_pins']['executable']['sha256'],
         'case_order':CASE_ORDER,'max_solver_invocations':2}
    if pf.get('status')!='PREFLIGHT_PASS_NO_SOLVER' or pf.get('solver_invocations')!=0 or pf.get('plan_sha256')!=req['plan_sha256']:
        raise RuntimeError('preflight is missing or stale')
    if set(a)!=set(req): raise RuntimeError('authorization key set mismatch')
    for k,v in req.items():
        if a.get(k)!=v: raise RuntimeError(f'authorization mismatch {k}')
    return pin(authpath)

def child(case,cmd,state,index):
    p=Path(case['output']); log=Path(case['log']); p.parent.mkdir(parents=True,exist_ok=True); log.parent.mkdir(parents=True,exist_ok=True)
    if os.path.lexists(p) or os.path.lexists(log): raise RuntimeError('case output/log collision')
    with log.open('xb') as fp:
        proc=subprocess.Popen(cmd,cwd=ROOT,env=ENV,stdout=fp,stderr=subprocess.STDOUT,start_new_session=True)
        rec=state['calls'][index]; timed=False
        try:
            state['solver_invocations']+=1
            rec.update({'status':'RUNNING','pid':proc.pid,'started_unix':time.time(),'command':cmd})
            write_atomic(RUN/'execution.json',state)
            rc=proc.wait(timeout=TIMEOUT)
        except subprocess.TimeoutExpired:
            timed=True
            try: os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: rc=proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                rc=proc.wait()
        except BaseException:
            try: os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: rc=proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                rc=proc.wait()
            rec.update({'status':'CHILD_INTERRUPTED','returncode':rc,'ended_unix':time.time()}); write_atomic(RUN/'execution.json',state); raise
        fp.flush(); os.fsync(fp.fileno())
        rec.update({'status':'CHILD_RC_RECORDED','returncode':rc,'timed_out':timed,'ended_unix':time.time()}); write_atomic(RUN/'execution.json',state)
    rec['log_pin']=pin(log); rec['output_pin']=pin(p) if p.is_file() else None; write_atomic(RUN/'execution.json',state)
    return rc,timed

def execute(authpath):
    plan=load_json(PLAN); auth=authorize(authpath); snap=fixed_snapshot(plan)
    current=preflight()
    if current['initial_pins']!=load_json(PREFLIGHT)['initial_pins']: raise RuntimeError('preflight snapshot changed')
    if os.path.lexists(RUN): raise RuntimeError('one-use execution directory already exists')
    lock=HERE/'execution.lock'; fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(fd,json.dumps({'runner_sha256':sha(Path(__file__))[0],'authorization':auth,'claimed_unix':time.time()}).encode()+b'\n');os.fsync(fd);os.close(fd)
    dfd=os.open(HERE,os.O_RDONLY|os.O_DIRECTORY);os.fsync(dfd);os.close(dfd)
    RUN.mkdir();(RUN/'outputs').mkdir();(RUN/'logs').mkdir()
    state={'schema':'exact-band-cloud-swap-two-call-execution-v1','status':'RUNNING','runner_sha256':sha(Path(__file__))[0],
           'plan_sha256':sha(PLAN)[0],'authorization':auth,'started_unix':time.time(),'solver_invocations':0,
           'model_invocations':0,'initial_pins':snap,'calls':[{'case_id':c['case_id'],'status':'NOT_STARTED'} for c in plan['cases']]}
    write_atomic(RUN/'execution.json',state)
    try:
        cases=plan['cases']; base=load_result(BASE_RESULT,plan['fixed_pins']['result_parser']['path'])
        for i,c in enumerate(cases):
            for pinname in ('input','raw','override'):
                if c.get(pinname): require(c[pinname],f'{c["case_id"]}.{pinname}')
            cmd=[str(EXE),str(Path(plan['data_path'])),c['input']['path'],c['output'],'1',c['override']['path']]
            state['calls'][i].update({'status':'PREFLIGHT_PASS','command':cmd}); write_atomic(RUN/'execution.json',state)
            rc,timed=child(c,cmd,state,i)
            if rc!=0 or timed: state['calls'][i]['status']='FAILED_CHILD'; raise RuntimeError(f'{c["case_id"]} failed (rc={rc}, timeout={timed}); stopping')
            result=load_result(c['output'],plan['fixed_pins']['result_parser']['path'])
            if i==0:
                state['calls'][i]['validation']=validate_control(c,load_json(PREP_PLAN),plan['fixed_pins']['result_parser']['path'])
            else:
                state['calls'][i]['validation']=validate_pair(cases[0],c,cases[0],result,load_json(PREP_PLAN),plan['fixed_pins']['result_parser']['path'])
            state['calls'][i]['status']='CALL_VALIDATED'; write_atomic(RUN/'execution.json',state)
            if fixed_snapshot(plan)!=snap: raise RuntimeError(f'immutable pins changed after {c["case_id"]}')
        state['final_immutable_snapshot']=fixed_snapshot(plan); state['final_pins_match_initial']=state['final_immutable_snapshot']==snap
        if not state['final_pins_match_initial']: raise RuntimeError('terminal immutable pins differ')
        state['status']='TWO_CALLS_VALIDATED'; state['ended_unix']=time.time()
    except BaseException as e:
        state['status']='FAILED_STOPPED'; state['error']=repr(e); state['ended_unix']=time.time()
        try:
            state['final_immutable_snapshot']=fixed_snapshot(plan); state['final_pins_match_initial']=state['final_immutable_snapshot']==snap
        except BaseException as pe: state['postflight_error']=repr(pe); state['final_pins_match_initial']=False
        write_atomic(RUN/'execution.json',state); raise
    write_atomic(RUN/'execution.json',state); return state

if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc: print(f'RUNNER_ERROR: {exc}',file=sys.stderr); raise
