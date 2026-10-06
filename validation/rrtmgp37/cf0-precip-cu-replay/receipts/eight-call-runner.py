#!/usr/bin/env python3
"""Single-use, no-retry runner for the frozen CF0 retained-CU 8-call campaign.

Default mode is read-only preflight. Numerical execution requires a separate,
exact root authorization JSON and is intentionally not authorized by this file.
"""
from __future__ import annotations
import argparse, hashlib, json, math, os, signal, struct, subprocess, sys, time
from pathlib import Path
import numpy as np

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=ROOT/'build/udm37-cf0-retained-cu-runtime-v1'
PLAN=HERE/'plan.json'; PREFLIGHT=HERE/'preflight-v4.json'
ROSTER=ROOT/'build/udm37-cf0-retained-cu-eight-inputs-v1/roster.json'
BUILD_RECEIPT=ROOT/'build/cf0-cu-build-runner-v2/execution.json'
BUILD_REVIEW=ROOT/'build/udm37-rrtmg4-export-independent-review-v1/cf0-cu-postbuild-review-v1/review.json'
EXE=ROOT/'build/cf0-cu-build-v1/cmake-build/reference_column'
RESULT_READER=ROOT/'build/cf0-cu-src-v1/WRF/test/rrtmgp/compare_column_replay.py'
CONTEXT_VALIDATOR=ROOT/'build/cf0-cu-src-v1/WRF/test/rrtmgp/cf0_precip_sidecar.py'
CTX_RECEIPT=ROOT/'build/cf0-cu-build-runner-v2/root-six-sidecar-readback-v1.json'
DATA=ROOT/'build/udm-cu-optics-design-work/WRF/run'
TABLE=ROOT/'build/udm37-frozen-planck-coverage-v1/runs/frozen-planck-150-330-step5-plus233-v1/frozen-ice-psd-moments.nc'
LW_GAS_COEFF=DATA/'rrtmgp-gas-lw-g128.nc'
STAGE=ROOT/'build/udm37-cf0-retained-cu-eight-inputs-v1'
RUN=HERE/'run-v1'; OUT=RUN/'outputs'; LOG=RUN/'logs'
AUTH_SCHEMA='cf0-cu-retained-eight-call-authorization-v1'
ORDER=['baseline-lw','baseline-sw','zero-lw','zero-sw','rain-lw','rain-sw','snow-lw','snow-sw']
BASELINE_SECTIONS={
 'LW':{'CLOUD_TAU','CU_CLOUD_TAU','CU_DI_USED','CU_RL_USED','DI_USED','DN','DNC','DS_USED','FROZEN_TAU','GAS_COL_DRY','GAS_TAU','GAS_TAU_RAW','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','HR','HRC','MASK','NATIVE_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU','RL_USED','TOTAL_TAU','UP','UPC'},
 'SW':{'CLOUD_G','CLOUD_SSA','CLOUD_TAU','CU_CLOUD_G','CU_CLOUD_SSA','CU_CLOUD_TAU','CU_DI_USED','CU_RL_USED','DIFFUSE','DIRECT','DIRECTC','DIRECTC_PREDELTA','DIRECT_PREDELTA','DI_USED','DN','DNC','DS_USED','FROZEN_G','FROZEN_SSA','FROZEN_TAU','GAS_COL_DRY','GAS_G','GAS_SSA','GAS_TAU','GRAUPEL_TAU_EXT','GRAUPEL_TAU_SCA','GRAUPEL_TAU_SCA_G','HAIL_TAU_EXT','HAIL_TAU_SCA','HAIL_TAU_SCA_G','HR','HRC','MASK','NATIVE_CLOUD_G','NATIVE_CLOUD_SSA','NATIVE_CLOUD_TAU','NIRDIF','NIRDIR','NIRDIR_PREDELTA','PRECIP_G','PRECIP_SSA','PRECIP_TAU','PREPARED_G','PREPARED_SSA','PREPARED_TAU','RL_USED','TOTAL_G','TOTAL_SSA','TOTAL_TAU','UP','UPC','VISDIF','VISDIR','VISDIR_PREDELTA'},
}
ENV={'PATH':'/usr/local/bin:/usr/bin:/bin',
     'LD_LIBRARY_PATH':str(ROOT/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu',
     'NETCDF':str(ROOT/'build/deps/netcdf'),'LANG':'C','LC_ALL':'C','TMPDIR':'/tmp',
     'OPENBLAS_NUM_THREADS':'1','WRF_RRTMGP_FROZEN_TABLE':str(TABLE)}
TIMEOUT=180

def sha(path):
    h=hashlib.sha256(); n=0
    with Path(path).open('rb') as f:
        while b:=f.read(1<<20): h.update(b); n+=len(b)
    return h.hexdigest(),n
def pin(path):
    h,n=sha(path); return {'path':str(Path(path).resolve()),'sha256':h,'size_bytes':n}
def fsync_dir(path):
    fd=os.open(path,os.O_RDONLY|os.O_DIRECTORY); os.fsync(fd); os.close(fd)
def write_atomic(path,obj):
    path=Path(path); path.parent.mkdir(parents=True,exist_ok=True)
    tmp=path.with_name(path.name+'.tmp')
    with tmp.open('w',encoding='utf-8') as f:
        json.dump(obj,f,sort_keys=True,indent=2,allow_nan=False); f.write('\n'); f.flush(); os.fsync(f.fileno())
    os.replace(tmp,path); fsync_dir(path.parent)
def same_pin(rec):
    p=Path(rec['path']); return p.is_file() and sha(p)==(rec['sha256'],rec['size_bytes'])
def require_pin(rec,label):
    if not same_pin(rec): raise RuntimeError(f'pin mismatch: {label}: {rec.get("path")}')
def normalized_ldd():
    cp=subprocess.run(['/usr/bin/ldd',str(EXE)],env=ENV,text=True,capture_output=True,check=True)
    libs={}
    for line in cp.stdout.splitlines():
        if '=>' not in line: continue
        rhs=line.split('=>',1)[1].strip().split()
        if rhs and rhs[0].startswith('/'):
            p=Path(rhs[0]).resolve(); rec=pin(p); libs[rec['path']]=rec
    return sorted(libs.values(),key=lambda x:x['path'])

def immutable_snapshot():
    plan=json.loads(PLAN.read_text())
    expected=plan.get('fixed_pins',{})
    for key,path in [('build_receipt',BUILD_RECEIPT),('build_review',BUILD_REVIEW),('context_receipt',CTX_RECEIPT),('readme',HERE/'README.md'),
                     ('offline_controls',HERE/'offline-controls-v3.json'),
                     ('roster',ROSTER),('result_reader',RESULT_READER),('sidecar_validator',CONTEXT_VALIDATOR),('table',TABLE),('executable',EXE),('lw_gas_coeff',LW_GAS_COEFF)]:
        rec=expected.get(key)
        if not rec or (rec.get('sha256'),rec.get('size_bytes'))!=sha(path):
            raise RuntimeError(f'plan does not bind current immutable {key}')
    build=json.loads(BUILD_RECEIPT.read_text()); dep=build['postflight_pins']
    if build.get('status')!='BUILD_PASS' or build.get('build_returncode')!=0 or build.get('configure_returncode')!=0:
        raise RuntimeError('fresh reference-column build receipt is not BUILD_PASS')
    if build.get('solver_invocations')!=0: raise RuntimeError('build receipt reports solver use')
    ex=build['executable']
    if Path(ex['path'])!=EXE or (ex['sha256'],ex['size_bytes'])!=('353333cc96bce44d26c02ca7585c0ddef8996fc74a05904220fba83db76cd97f',1040232):
        raise RuntimeError('unexpected fresh executable identity')
    require_pin(expected['executable'],'live fresh executable')
    require_pin(expected['build_receipt'],'build receipt')
    require_pin(expected['build_review'],'postbuild independent review')
    require_pin(expected['context_receipt'],'V10/V11 sidecar context proof')
    ctx=json.loads(CTX_RECEIPT.read_text())
    if ctx.get('status')!='PASS_SIX_SOURCE_CONTEXT_CONTROLS_NO_SOLVER' or ctx.get('roster_sha256')!=sha(ROSTER)[0]:
        raise RuntimeError('V10/V11 six-sidecar context proof mismatch')
    review=json.loads(BUILD_REVIEW.read_text())
    if not all(review.get('checks',{}).values()): raise RuntimeError('independent fresh-build review has a failed check')
    libs=normalized_ldd()
    expected_libs=sorted(dep['runtime_libraries_expected'],key=lambda x:x['path'])
    if libs!=expected_libs: raise RuntimeError('fresh executable normalized runtime closure differs from BUILD_PASS')
    table_pin=pin(TABLE)
    if table_pin['sha256']!='ebeafb9746164d5414a45eab4061c5c855f0f91e92be77003b3829722514fe6a' or table_pin['size_bytes']!=163599:
        raise RuntimeError('expanded runtime Planck table identity mismatch')
    for key,path in [('result_reader',RESULT_READER),('sidecar_validator',CONTEXT_VALIDATOR)]: require_pin(expected[key],key)
    offline=json.loads((HERE/'offline-controls-v3.json').read_text())
    if offline.get('status')!='PASS_NO_SOLVER' or offline.get('runner_sha256')!=sha(Path(__file__))[0] or offline.get('solver_invocations')!=0:
        raise RuntimeError('offline validator controls do not bind this runner or report a solver call')
    # Include every staged input/raw/sidecar and all data/table/runtime files from successful build pins.
    roster=json.loads(ROSTER.read_text())
    stage_pins=[]
    for case in roster['cases']:
        for k in ('input','raw','sidecar'):
            rec=case.get(k)
            if rec:
                require_pin(rec,f'{case["case_id"]}.{k}'); stage_pins.append(dict(rec))
    for rec in dep['data_assets']:
        if rec.get('kind')=='symlink':
            p=Path(rec['path'])
            if not p.is_symlink() or os.readlink(p)!=rec.get('target'): raise RuntimeError(f'data symlink changed: {p}')
        else: require_pin(rec,'build data asset')
    for rec in dep['source_pins']:
        if rec.get('kind')=='symlink':
            p=Path(rec['path'])
            if not p.is_symlink() or os.readlink(p)!=rec.get('target'): raise RuntimeError(f'source symlink changed: {p}')
        else: require_pin(rec,'build source pin')
    for rec in (dep['frozen_table_link'],dep['frozen_table_resolved']):
        if rec.get('kind')=='symlink':
            p=Path(rec['path'])
            if not p.is_symlink() or os.readlink(p)!=rec['target']: raise RuntimeError(f'frozen table link drift: {p}')
        else: require_pin(rec,'frozen table link/target')
    require_pin(dep['dependency_manifest'],'dependency manifest')
    for rec in dep['source_files']:
        require_pin(rec,'compiled source file')
    for rec in dep['netcdf_include_modules'].values():
        require_pin(rec,'NetCDF include/module')
    require_pin(dep['cmake'],'CMake')
    require_pin(dep['compiler'],'Fortran compiler')
    # Bind the actual runtime table symlink and its resolved target separately;
    # the build receipt's table identity alone does not prove the live loader path.
    if dep['frozen_table_link'].get('kind')=='symlink':
        p=Path(dep['frozen_table_link']['path'])
        if not p.is_symlink() or os.readlink(p)!=dep['frozen_table_link']['target']:
            raise RuntimeError('frozen table link target changed')
    else:
        require_pin(dep['frozen_table_link'],'frozen table link')
    require_pin(dep['frozen_table_resolved'],'resolved frozen table')
    return {'executable':pin(EXE),'build_receipt':pin(BUILD_RECEIPT),'build_review':pin(BUILD_REVIEW),
            'context_receipt':pin(CTX_RECEIPT),'roster':pin(ROSTER),'plan':pin(PLAN),
            'runtime_table':table_pin,'runtime_libraries':libs,'reader':pin(RESULT_READER),
            'sidecar_validator':pin(CONTEXT_VALIDATOR),'context_validator':pin(CONTEXT_VALIDATOR),
            'readme':pin(HERE/'README.md'),'offline_controls':pin(HERE/'offline-controls-v3.json'),
            'source_pins':dep['source_pins'],'data_assets':dep['data_assets'],
            'dependency_manifest':dep['dependency_manifest'],'compiled_source_files':dep['source_files'],
            'netcdf_include_module_review':dep['netcdf_include_module_review'],
            'netcdf_include_modules':dep['netcdf_include_modules'],'compiler':dep['compiler'],'cmake':dep['cmake'],
            'frozen_table_link':dep['frozen_table_link'],'frozen_table_resolved':dep['frozen_table_resolved'],
            'stage_files':sorted(stage_pins,key=lambda x:x['path']),
            'tools':{x:pin(x) for x in ['/usr/bin/python3.12','/usr/bin/ldd']}}

def check_roster():
    d=json.loads(ROSTER.read_text())
    if d.get('status')!='PREPARED_INPUTS_ONLY_NOT_EXECUTED' or d.get('solver_invocations')!=0 or d.get('wrf_forecasts')!=0:
        raise RuntimeError('input roster is not preparation-only')
    if d.get('case_order')!=ORDER: raise RuntimeError('case order differs from fixed eight-call protocol')
    cases={c['case_id']:c for c in d['cases']}
    if set(cases)!=set(ORDER): raise RuntimeError('roster case set mismatch')
    derived=[]
    for cid in ORDER:
        c=cases[cid]
        phase='LW' if cid.endswith('lw') else 'SW'
        if c['phase']!=phase: raise RuntimeError(f'{cid}: phase mismatch')
        if len(c['argv']) not in (6,7): raise RuntimeError(f'{cid}: argv arity mismatch')
        if c['argv'][0]!=str(EXE) or c['argv'][1]!=str(DATA) or c['argv'][2]!=c['input']['path']:
            raise RuntimeError(f'{cid}: executable/data/input argv mismatch')
        if c['argv'][4]!='1' or c['argv'][5]!='': raise RuntimeError(f'{cid}: SW policy/override contract mismatch')
        if c['mode']=='baseline':
            if c['sidecar'] is not None or len(c['argv'])!=6: raise RuntimeError(f'{cid}: baseline sidecar unexpected')
        else:
            if not c['sidecar'] or len(c['argv'])!=7 or c['argv'][6]!=c['sidecar']['path']:
                raise RuntimeError(f'{cid}: sidecar argv mismatch')
        expected_out=OUT/f'{cid}.result'; expected_log=LOG/f'{cid}.log'
        if Path(c['output'])!=expected_out or Path(c['log'])!=expected_log:
            raise RuntimeError(f'{cid}: output/log destinations not the frozen runtime paths')
        # Roster argv[3] was generated against obsolete staging/runs. Derive corrected immutable command here.
        argv=[str(EXE),str(DATA),c['input']['path'],c['output'],'1','']
        if c['sidecar']: argv.append(c['sidecar']['path'])
        derived.append({'case_id':cid,'argv':argv,'roster_argv_output_token':c['argv'][3],
                        'corrected_output':c['output'],'log':c['log']})
    return d,derived

def parse_input(path):
    lines=Path(path).read_text().splitlines(); first=lines[0].strip(); h=lines[1].split()
    if first not in {'RRTMGP_REPLAY_V10','RRTMGP_REPLAY_V11'}: raise ValueError('expected V10/V11 retained-CU input')
    phase=h[0].upper(); nc=int(h[1]); nl=int(h[2])
    fields={}; pos=2
    while pos<len(lines):
        if not lines[pos].strip(): pos+=1; continue
        head=lines[pos].split(); pos+=1
        if len(head)<2: raise ValueError(f'bad input section at line {pos}')
        name=head[0]; dims=tuple(int(x) for x in head[1:]); count=math.prod(dims); vals=[]
        while len(vals)<count and pos<len(lines):
            vals.extend(float(x.replace('D','E').replace('d','e')) for x in lines[pos].split()); pos+=1
        if len(vals)!=count: raise ValueError(f'bad size for input field {name}')
        fields[name]=(dims,vals)
    if 'GRAVITY' not in fields or 'CP_DRY' not in fields or 'PLEV' not in fields: raise ValueError('input lacks heating identity metadata')
    return phase,nc,nl,fields

def read_result(path, reader):
    import importlib.util
    spec=importlib.util.spec_from_file_location('cf0_column_result_reader',reader)
    mod=importlib.util.module_from_spec(spec); sys.modules[spec.name]=mod; spec.loader.exec_module(mod)
    return mod.read_result(Path(path))

def section_bytes(arr):
    # Exact binary64 representation preserves signed zero as required.
    return arr.astype('>f8',copy=False).tobytes(order='F')

def validate_result(case, result, baseline=None):
    sections=result['sections']; phase=case['phase']; mode=case['mode']; species=case['species']
    required_audit={'AUDIT_EXTRA_PRECIP_TAU'} if phase=='LW' else {'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA'}
    if mode=='baseline':
        if required_audit & sections.keys(): raise ValueError('baseline unexpectedly contains CF0 audit output')
        if set(sections)!=BASELINE_SECTIONS[phase]:
            raise ValueError(f'{phase} baseline section inventory differs from the pinned 24/54 contract')
        return {'mode':mode,'all_sections_finite':True,'sections':sorted(sections)}
    if mode=='zero':
        if baseline is None: raise ValueError('zero-control baseline missing')
        if sha(case['output'])[0] != baseline['_file_sha256']:
            raise ValueError('zero sidecar whole result file is not byte-identical to baseline')
        if sections.keys()!=baseline['sections'].keys(): raise ValueError('zero-control result section set changed')
        for name in sections:
            if section_bytes(sections[name])!=section_bytes(baseline['sections'][name]):
                raise ValueError(f'zero sidecar is not byte-identical at result section {name}')
        return {'mode':mode,'all_sections_finite':True,'sections':sorted(sections),
                'whole_file_sha256_identical_to_baseline':True}
    if not required_audit.issubset(sections): raise ValueError('CF0 output missing phase audit records')
    tau=sections['AUDIT_EXTRA_PRECIP_TAU']
    if not (float(abs(tau).max())>0): raise ValueError('positive sidecar produced zero audit optical depth')
    if baseline is not None:
        # All baseline optical/input sections must remain identical; only response outputs
        # and the explicitly defined audit additions may differ.
        audit_names={'AUDIT_EXTRA_PRECIP_TAU'} if phase=='LW' else {'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA'}
        if set(sections)!=(set(baseline['sections'])|audit_names):
            raise ValueError('positive result does not contain exactly baseline plus expected audit sections')
        response={'UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF',
                  'TOTAL_TAU','TOTAL_SSA','TOTAL_G',
                  'WRF_GLW','WRF_OLR','WRF_GSW','WRF_SWDDIR','WRF_SWDDIF'}
        if set(sections)-set(baseline['sections']) != audit_names:
            raise ValueError('positive result section roster differs beyond defined audit additions')
        if set(baseline['sections'])-set(sections):
            raise ValueError('positive result omitted a section present in its baseline')
        held=set(baseline['sections'])-response
        for n in sorted(held & sections.keys()):
            if n not in baseline['sections'] or section_bytes(sections[n])!=section_bytes(baseline['sections'][n]):
                raise ValueError(f'positive audit changed held input/optical section {n}')
        for n in ('UPC','DNC','HRC','DIRECTC'):
            if n not in sections:
                continue
            if n not in baseline['sections'] or section_bytes(sections[n])!=section_bytes(baseline['sections'][n]):
                raise ValueError(f'clear-sky output changed: {n}')
    return {'mode':mode,'species':species,'all_sections_finite':True,'sections':sorted(sections),
            'audit_tau_max_abs':float(abs(tau).max()),'audit_tau_sum':float(tau.sum()),
            'clear_outputs_identical_by_insertion_order':['UPC','DNC','HRC','DIRECTC'] if baseline is not None else []}

def zero_sidecar_validate(case, validator):
    if case['mode']!='zero': return None
    # Run the frozen Python raw/context validator before each Fortran sidecar call.
    cmd=['/usr/bin/python3.12','-B',str(validator),'--raw',case['raw']['path'],'--input',case['input']['path'],
         '--sidecar',case['sidecar']['path'],'--species',case['species'],'--engine-layers',str(parse_input(case['input']['path'])[2]),'--zero-control']
    p=subprocess.run(cmd,cwd=ROOT,env=ENV,capture_output=True,text=True,timeout=60)
    if p.returncode!=0: raise RuntimeError(f'zero sidecar context validation failed: {p.stderr}')
    return {'command':cmd,'returncode':p.returncode,'stdout_sha256':hashlib.sha256(p.stdout.encode()).hexdigest()}

def validate_sidecar_context(case, validator):
    if case['mode']=='baseline': return None
    zero=case['mode']=='zero'
    cmd=['/usr/bin/python3.12','-B',str(validator),'--raw',case['raw']['path'],'--input',case['input']['path'],
         '--sidecar',case['sidecar']['path'],'--species',case['species'],'--engine-layers',str(parse_input(case['input']['path'])[2])]
    if zero: cmd.append('--zero-control')
    p=subprocess.run(cmd,cwd=ROOT,env=ENV,capture_output=True,text=True,timeout=60)
    if p.returncode!=0: raise RuntimeError(f'{case["case_id"]}: raw/context sidecar validator failed: {p.stderr}')
    obj=json.loads(p.stdout)
    if obj.get('status')!='PASS_PYTHON_SIDECAR_RAW_CONTRACT': raise RuntimeError('sidecar validator did not return PASS')
    ctx=obj.get('replay_context') or {}
    expected_version='RRTMGP_REPLAY_V10' if case['phase']=='LW' else 'RRTMGP_REPLAY_V11'
    expected_cu=['CU_POPULATION_POLICY','CU_RADIUS_POLICY','CU_OCCURRENCE_POLICY','CU_LWP','CU_IWP','CU_REL','CU_REI']
    if ctx.get('version')!=expected_version or ctx.get('cu_records_preserved')!=expected_cu:
        raise RuntimeError(f'{case["case_id"]}: validated replay context lacks the frozen CU bundle')
    return {'returncode':p.returncode,'report':obj}

def band_gpoint_limits(phase, fields, nbnd, ngpt):
    if phase=='SW':
        dims,vals=fields['BAND_LIMS_GPOINT']
        if dims!=(2,nbnd): raise ValueError('V11 band-to-gpoint map has wrong shape')
        arr=np.asarray(vals,dtype=np.int64).reshape(dims,order='F')
        limits=[(int(arr[0,b]),int(arr[1,b])) for b in range(nbnd)]
    else:
        from netCDF4 import Dataset
        with Dataset(LW_GAS_COEFF,'r') as ds:
            arr=np.asarray(ds.variables['bnd_limits_gpt'][:],dtype=np.int64)
        if arr.shape!=(nbnd,2): raise ValueError('pinned LW coefficient gpoint map has wrong shape')
        limits=[(int(lo),int(hi)) for lo,hi in arr]
    expect=1
    for lo,hi in limits:
        if lo!=expect or hi<lo: raise ValueError('band-to-gpoint map has a gap or overlap')
        expect=hi+1
    if expect!=ngpt+1: raise ValueError('band-to-gpoint map does not span the phase gpoints')
    return limits

def expand_bands(values, limits, ngpt):
    out=np.empty((values.shape[0],values.shape[1],ngpt),dtype=np.float64)
    for band,(lo,hi) in enumerate(limits): out[:,:,lo-1:hi]=values[:,:,band,None]
    return out

def moment_residual(actual, expected, name):
    residual=np.abs(actual-expected)
    bound=512.0*np.finfo(np.float64).eps*np.maximum(1.0,np.abs(expected))
    maxres=float(residual.max())
    if np.any(residual>bound): raise ValueError(f'{name} combined-optics moment closure failed: max={maxres}')
    return {'max_abs_residual':maxres,'tolerance_rule':'512*binary64_epsilon*max(1,abs(expected))'}

def validate_positive_shapes_and_heat(case, result, baseline=None):
    phase,nc,nl,fields=parse_input(case['input']['path']); s=result['sections']; errors={}
    if result.get('phase')!=phase or result.get('nc')!=nc or result.get('nl')!=nl:
        raise ValueError('result phase/dimensions differ from the paired replay input')
    if not all(npfinite(a) for a in s.values()): raise ValueError('nonfinite result values')
    for name in ('UP','DN','UPC','DNC'):
        if name not in s or s[name].shape!=(nc,nl+1,1): raise ValueError(f'{name} result shape mismatch')
    for name in ('HR','HRC'):
        if name not in s or s[name].shape!=(nc,nl,1): raise ValueError(f'{name} result shape mismatch')
    if phase=='LW':
        needed={'UP','DN','HR','UPC','DNC','HRC'}
        if not needed<=s.keys(): raise ValueError('incomplete LW records')
    else:
        needed={'UP','DN','HR','UPC','DNC','HRC','DIRECT','DIFFUSE','DIRECTC'}
        if not needed<=s.keys(): raise ValueError('incomplete SW records')
    ngpt,nbnd=(128,16) if phase=='LW' else (112,14)
    interface={'UP','DN','UPC','DNC','DIRECT','DIRECTC','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF',
               'DIRECT_PREDELTA','DIRECTC_PREDELTA','VISDIR_PREDELTA','NIRDIR_PREDELTA','AUDIT_DIRECT_PREDELTA'}
    layer={'HR','HRC'}
    scalar={'GAS_COL_DRY','RL_USED','DI_USED','DS_USED','CU_RL_USED','CU_DI_USED'}
    gpoint={'GAS_TAU','GAS_TAU_RAW','GAS_SSA','GAS_G','MASK','TOTAL_TAU','TOTAL_SSA','TOTAL_G'}
    band={n for n in s if n in {'CLOUD_TAU','CLOUD_SSA','CLOUD_G','NATIVE_CLOUD_TAU','NATIVE_CLOUD_SSA','NATIVE_CLOUD_G',
                                 'CU_CLOUD_TAU','CU_CLOUD_SSA','CU_CLOUD_G','PREPARED_TAU','PREPARED_SSA','PREPARED_G',
                                 'PRECIP_TAU','PRECIP_SSA','PRECIP_G','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','GRAUPEL_TAU_EXT',
                                 'GRAUPEL_TAU_SCA','GRAUPEL_TAU_SCA_G','HAIL_TAU_EXT','HAIL_TAU_SCA','HAIL_TAU_SCA_G',
                                 'FROZEN_TAU','FROZEN_SSA','FROZEN_G','AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW',
                                 'AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G'}}
    for n in interface & s.keys():
        if s[n].shape!=(nc,nl+1,1): raise ValueError(f'{n} must have exact interface shape')
    for n in layer & s.keys():
        if s[n].shape!=(nc,nl,1): raise ValueError(f'{n} must have exact layer shape')
    for n in scalar & s.keys():
        if s[n].shape!=(nc,nl,1): raise ValueError(f'{n} must have exact scalar profile shape')
    for n in gpoint & s.keys():
        if s[n].shape!=(nc,nl,ngpt): raise ValueError(f'{n} must have exact {ngpt}-gpoint shape')
    for n in band:
        if s[n].shape!=(nc,nl,nbnd): raise ValueError(f'{n} must have exact {nbnd}-band shape')
    positive_checks={}
    if case['mode']=='positive':
        if np.any(s['AUDIT_EXTRA_PRECIP_TAU']<0): raise ValueError('negative audit tau')
        if 'AUDIT_EXTRA_PRECIP_TAU_RAW' in s and np.any(s['AUDIT_EXTRA_PRECIP_TAU_RAW']<0): raise ValueError('negative raw audit tau')
        if 'AUDIT_EXTRA_PRECIP_SSA' in s and (np.any(s['AUDIT_EXTRA_PRECIP_SSA']<0) or np.any(s['AUDIT_EXTRA_PRECIP_SSA']>1)):
            raise ValueError('audit SSA outside [0,1]')
        if 'AUDIT_EXTRA_PRECIP_G' in s and np.any(np.abs(s['AUDIT_EXTRA_PRECIP_G'])>1): raise ValueError('audit g outside [-1,1]')
        if baseline is None: raise ValueError('positive sidecar requires baseline total optics')
        helper_spec=__import__('importlib.util').util.spec_from_file_location('cf0_sidecar_context',CONTEXT_VALIDATOR)
        helper=__import__('importlib.util').util.module_from_spec(helper_spec);helper_spec.loader.exec_module(helper)
        decoded=helper.decode(Path(case['sidecar']['path']).read_text())
        _,_,native_n,_,_,rain,snow=decoded
        active=np.zeros(nl,dtype=bool)
        active[:native_n]=[bool(rain[0][i]>0 or snow[0][i]>0) for i in range(native_n)]
        for n in ('AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G'):
            if n in s and np.any(s[n][0,~active,:]!=0): raise ValueError(f'{n} is nonzero outside sidecar-active native CF0 rows')
        limits=band_gpoint_limits(phase,fields,nbnd,ngpt)
        extra_tau=expand_bands(s['AUDIT_EXTRA_PRECIP_TAU'],limits,ngpt)
        b=baseline['sections']; mcheck={}
        expected_tau=b['TOTAL_TAU']+extra_tau
        mcheck['TOTAL_TAU']=moment_residual(s['TOTAL_TAU'],expected_tau,'TOTAL_TAU')
        if phase=='SW':
            extra_ssa=expand_bands(s['AUDIT_EXTRA_PRECIP_SSA'],limits,ngpt)
            extra_g=expand_bands(s['AUDIT_EXTRA_PRECIP_G'],limits,ngpt)
            expected_scatter=b['TOTAL_TAU']*b['TOTAL_SSA']+extra_tau*extra_ssa
            expected_gmoment=b['TOTAL_TAU']*b['TOTAL_SSA']*b['TOTAL_G']+extra_tau*extra_ssa*extra_g
            expected_ssa=expected_scatter/np.maximum(3.0*np.finfo(np.float64).tiny,expected_tau)
            expected_g=expected_gmoment/np.maximum(3.0*np.finfo(np.float64).tiny,expected_scatter)
            mcheck['TOTAL_SSA']=moment_residual(s['TOTAL_SSA'],expected_ssa,'TOTAL_SSA')
            mcheck['TOTAL_G']=moment_residual(s['TOTAL_G'],expected_g,'TOTAL_G')
        positive_checks={'band_to_gpoint_limits':limits,'combined_total_optics_moment_checks':mcheck,
                         'active_native_layers':int(active.sum())}
    # Source identity check: heating uses flux divergence and captured gravity/cp/pressure interfaces.
    g=fields['GRAVITY'][1][0]; cp=fields['CP_DRY'][1][0]; plev=fields['PLEV'][1]
    if len(plev)!=nl+1: raise ValueError('PLEV extent does not match flux interfaces')
    if 'HR' in s:
        # Keep the source operation ordering. HR shape is nc x nl x 1.
        expected=[]; actual=s['HR'][:, :, 0]
        up=s['UP'][:,:,0]; dn=s['DN'][:,:,0]
        for k in range(nl):
            # source converts hPa to Pa before pressure difference and applies sec/day afterward
            dp=plev[k+1]*100.0-plev[k]*100.0
            if dp==0: raise ValueError('zero pressure thickness in captured PLEV')
            for c in range(nc): expected.append((((up[c,k+1]-up[c,k])-dn[c,k+1])+dn[c,k])*g/(cp*dp)*86400.0)
        ev=np.asarray(expected).reshape((nc,nl),order='F')
        errors={'max_abs_hr_flux_divergence_residual':float(np.max(np.abs(actual-ev))),
                'threshold_k_day_minus1':1.0e-9}
        if errors['max_abs_hr_flux_divergence_residual']>errors['threshold_k_day_minus1']:
            raise ValueError(f'heating/flux-divergence residual exceeded {errors}')
    return {'finite':True,'phase':phase,'nc':nc,'nl':nl,**errors,**positive_checks}

def npfinite(a):
    import numpy as np
    return bool(np.isfinite(a).all())

def preflight():
    if not HERE.is_dir(): raise RuntimeError('runtime directory missing')
    if not PLAN.is_file(): raise RuntimeError('frozen plan missing')
    plan=json.loads(PLAN.read_text())
    if plan.get('roster_sha256')!=sha(ROSTER)[0]: raise RuntimeError('plan does not bind exact frozen roster')
    if plan.get('executable_sha256')!='353333cc96bce44d26c02ca7585c0ddef8996fc74a05904220fba83db76cd97f': raise RuntimeError('plan executable pin mismatch')
    if plan.get('runner_sha256')!=sha(Path(__file__))[0]: raise RuntimeError('plan runner hash mismatch')
    if PREFLIGHT.exists():
        pf=json.loads(PREFLIGHT.read_text())
        if (pf.get('plan_sha256')!=sha(PLAN)[0] or pf.get('runner_sha256')!=sha(Path(__file__))[0]
                or pf.get('status')!='PREFLIGHT_PASS_NO_SOLVER'): raise RuntimeError('preflight does not bind current plan')
    snap=immutable_snapshot(); roster,commands=check_roster()
    if plan.get('derived_commands')!=commands: raise RuntimeError('plan corrected command vectors differ from runtime derivation')
    for c in roster['cases']:
        if os.path.lexists(c['output']) or os.path.lexists(c['log']): raise RuntimeError(f'planned output/log already exists: {c["case_id"]}')
    if os.path.lexists(OUT) or os.path.lexists(LOG): raise RuntimeError('output/log root collision')
    return {'snapshot':snap,'commands':commands,'case_count':len(commands),'solver_invocations':0,'model_invocations':0}

def persist_preflight():
    if os.path.lexists(PREFLIGHT):
        prior=json.loads(PREFLIGHT.read_text())
        if (prior.get('status')=='PREFLIGHT_PASS_NO_SOLVER' and prior.get('plan_sha256')==sha(PLAN)[0]
                and prior.get('runner_sha256')==sha(Path(__file__))[0] and prior.get('solver_invocations')==0):
            return prior
        raise RuntimeError('preflight receipt collision or stale preflight; preserving existing file')
    p=preflight(); p.update({'schema':'cf0-cu-retained-capture-preflight-v1','status':'PREFLIGHT_PASS_NO_SOLVER',
                             'plan_sha256':sha(PLAN)[0],'runner_sha256':sha(Path(__file__))[0],
                             'preflight_generated_unix':time.time()})
    write_atomic(PREFLIGHT,p); return p

def authorize(authpath, runner_sha):
    a=json.loads(Path(authpath).read_text()); plan=json.loads(PLAN.read_text())
    pf=json.loads(PREFLIGHT.read_text())
    if (pf.get('status')!='PREFLIGHT_PASS_NO_SOLVER' or pf.get('plan_sha256')!=sha(PLAN)[0]
            or pf.get('runner_sha256')!=runner_sha or pf.get('solver_invocations')!=0):
        raise RuntimeError('no current clean preflight receipt')
    req={'schema':AUTH_SCHEMA,'approved':True,'runner_sha256':runner_sha,'plan_sha256':sha(PLAN)[0],
         'preflight_sha256':sha(PREFLIGHT)[0],
         'roster_sha256':sha(ROSTER)[0],'build_receipt_sha256':sha(BUILD_RECEIPT)[0],
         'executable_sha256':plan['executable_sha256'],'case_order':ORDER,'max_solver_invocations':8}
    for k,v in req.items():
        if a.get(k)!=v: raise RuntimeError(f'authorization mismatch: {k}')
    return pin(authpath)

def run_child(case, cmd, state, n):
    log=Path(case['log']); out=Path(case['output']); log.parent.mkdir(parents=True,exist_ok=True); out.parent.mkdir(parents=True,exist_ok=True)
    if os.path.lexists(log) or os.path.lexists(out): raise RuntimeError(f'output collision before {case["case_id"]}')
    with log.open('xb') as fp:
        proc=subprocess.Popen(cmd,cwd=ROOT,env=ENV,stdout=fp,stderr=subprocess.STDOUT,start_new_session=True)
        state['solver_invocations']=state.get('solver_invocations',0)+1
        state['calls'][n].update({'status':'RUNNING','pid':proc.pid,'started_unix':time.time(),'command':cmd})
        write_atomic(RUN/'execution.json',state)
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
        except BaseException:
            try: os.killpg(proc.pid,signal.SIGTERM)
            except ProcessLookupError: pass
            try: rc=proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                try: os.killpg(proc.pid,signal.SIGKILL)
                except ProcessLookupError: pass
                rc=proc.wait()
            state['calls'][n].update({'returncode':rc,'timed_out':False,'ended_unix':time.time(),
                                      'status':'CHILD_INTERRUPTED'})
            write_atomic(RUN/'execution.json',state)
            raise
        fp.flush(); os.fsync(fp.fileno())
        state['calls'][n].update({'returncode':rc,'timed_out':timed,'ended_unix':time.time(),
                                  'status':'CHILD_RC_RECORDED'})
        write_atomic(RUN/'execution.json',state)
        fp.flush(); os.fsync(fp.fileno())
    state['calls'][n]['log_pin']=pin(log)
    if out.is_file() and not out.is_symlink(): state['calls'][n]['output_pin']=pin(out)
    write_atomic(RUN/'execution.json',state)
    if rc!=0 or timed: return rc,timed
    return rc,timed

def execute(authpath):
    # Immutable checks and all collisions precede claiming the one-use directory.
    snap=immutable_snapshot(); roster,derived=check_roster(); plan=json.loads(PLAN.read_text())
    pf=json.loads(PREFLIGHT.read_text())
    if (pf.get('status')!='PREFLIGHT_PASS_NO_SOLVER' or pf.get('plan_sha256')!=sha(PLAN)[0]
            or pf.get('runner_sha256')!=sha(Path(__file__))[0] or pf.get('snapshot')!=snap
            or pf.get('commands')!=derived):
        raise RuntimeError('preflight is stale or differs from current immutable state/commands')
    if plan.get('derived_commands')!=derived: raise RuntimeError('plan command vector mismatch')
    thissha=sha(Path(__file__))[0]; authpin=authorize(authpath,thissha)
    if os.path.lexists(RUN): raise RuntimeError('execution root already exists; no overwrite')
    lock=HERE/'execution.lock'
    fd=os.open(lock,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
    os.write(fd,json.dumps({'runner_sha256':thissha,'authorization':authpin,'claimed_unix':time.time()}).encode()+b'\n');os.fsync(fd);os.close(fd);fsync_dir(HERE)
    RUN.mkdir();OUT.mkdir();LOG.mkdir()
    case_map={c['case_id']:c for c in roster['cases']}; derived_map={x['case_id']:x for x in derived}
    state={'schema':'cf0-cu-retained-cu-eight-call-execution-v1','status':'RUNNING','runner_sha256':thissha,
           'plan_sha256':sha(PLAN)[0],'authorization':authpin,'started_unix':time.time(),
           'environment':ENV,'initial_pins':snap,'model_invocations':0,'solver_invocations':0,
           'calls':[{'case_id':x,'status':'NOT_STARTED'} for x in ORDER]}
    write_atomic(RUN/'execution.json',state)
    try:
        # Recheck immediately before any process; runner never rewrites the frozen input roster.
        if immutable_snapshot()!=snap: raise RuntimeError('immutable pre-call snapshot changed')
        for ix,cid in enumerate(ORDER):
            c=case_map[cid]; cmd=derived_map[cid]['argv']
            for k in ('input','raw','sidecar'):
                rec=c.get(k)
                if rec: require_pin(rec,f'{cid}.{k} before child')
            context=validate_sidecar_context(c,CONTEXT_VALIDATOR)
            n=ix; state['calls'][n].update({'status':'PREFLIGHT_PASS','sidecar_context':context,
                                             'output_path':c['output'],'log_path':c['log']})
            write_atomic(RUN/'execution.json',state)
            rc,to=run_child(c,cmd,state,n)
            if to or rc!=0:
                state['calls'][n]['status']='FAILED_CHILD'; state['status']='FAILED_STOPPED';
                raise RuntimeError(f'{cid} failed or timed out (rc={rc}, timeout={to}); no retry/later calls')
            result=read_result(c['output'],RESULT_READER)
            result['_file_sha256']=sha(c['output'])[0]
            baseline=None
            if cid.startswith('zero-'):
                baseline=read_result(case_map['baseline-'+cid[-2:]]['output'],RESULT_READER)
                baseline['_file_sha256']=sha(case_map['baseline-'+cid[-2:]]['output'])[0]
            if cid in ('rain-lw','rain-sw','snow-lw','snow-sw'):
                baseline=read_result(case_map['baseline-'+cid[-2:]]['output'],RESULT_READER)
                baseline['_file_sha256']=sha(case_map['baseline-'+cid[-2:]]['output'])[0]
            state['calls'][n]['result_checks']=validate_result(c,result,baseline)
            state['calls'][n]['source_equation_checks']=validate_positive_shapes_and_heat(c,result,baseline)
            state['calls'][n]['status']='CALL_VALIDATED'
            write_atomic(RUN/'execution.json',state)
            # The zero control is a hard gate before any positive sidecar invocation.
            if cid=='zero-sw' and not all(state['calls'][j]['status']=='CALL_VALIDATED' for j in range(4)):
                raise RuntimeError('zero-control gate incomplete')
            if immutable_snapshot()!=snap: raise RuntimeError(f'immutable post-call snapshot changed after {cid}')
        # Keep final immutable postflight inside the protected block: a late
        # hash/read failure must produce a durable terminal failure receipt.
        state['final_immutable_snapshot']=immutable_snapshot()
        state['final_pins_match_initial']=state['final_immutable_snapshot']==snap
        if not state['final_pins_match_initial']:
            raise RuntimeError('final immutable snapshot differs from initial pins')
        state['status']='ALL_EIGHT_CALLS_VALIDATED'; state['ended_unix']=time.time();state['model_invocations']=0;state['solver_invocations']=8
    except BaseException as e:
        state['status']='FAILED_STOPPED';state['error']=repr(e);state['ended_unix']=time.time()
        state['model_invocations']=0
        try:
            state['final_immutable_snapshot']=immutable_snapshot()
            state['final_pins_match_initial']=state['final_immutable_snapshot']==snap
        except BaseException as pe:
            state['postflight_error']=repr(pe);state['final_pins_match_initial']=False
        write_atomic(RUN/'execution.json',state)
        raise
    write_atomic(RUN/'execution.json',state)
    return state

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument('--check',action='store_true',help='write an immutable no-solver preflight receipt')
    ap.add_argument('--execute',action='store_true',help='requires separate root-issued authorization')
    ap.add_argument('--authorization',type=Path)
    a=ap.parse_args()
    if a.execute:
        if a.authorization is None: print('authorization required; no solver invoked',file=sys.stderr); return 2
        result=execute(a.authorization); print(json.dumps({'status':result['status'],'solver_invocations':result['solver_invocations']}));return 0
    if a.check:
        result=persist_preflight();print(json.dumps({'status':result['status'],'runner_sha256':result['runner_sha256'],'solver_invocations':0}));return 0
    print('preparation only; use --check, then --execute with external authorization',file=sys.stderr);return 2
if __name__=='__main__':
    try: raise SystemExit(main())
    except Exception as exc:
        print(f'PREPARATION_OR_EXECUTION_ERROR: {exc}',file=sys.stderr);raise
