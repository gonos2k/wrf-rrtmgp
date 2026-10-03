#!/usr/bin/env python3
"""Guarded stage/run/compare helper for the current CCN-fixed nested CU trial.

This file supports explicit stage/run actions, but its creation and preflight do
not stage files or launch WRF. Every output root is one-use and collisions fail.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, resource, shutil, signal, subprocess, sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, default_fillvals

ROOT=Path(__file__).resolve().parents[2]; HERE=Path(__file__).resolve().parent
BUILD=ROOT/'build/udm37-ccn-tile-init-gnu-v1'; WRF=BUILD/'source/WRF'
INTEGRITY=ROOT/'build/udm37-ccn-current-runtime-v1/runtime_integrity.py'
PLAN=HERE/'plan.json'; PRECHECK=HERE/'preflight-final.json'
DONOR_RECEIPT=ROOT/'build/udm-seaice-winter-validation-v3/ra37-24h-v1/execution-receipt-v1.json'
DONOR_STAGE=ROOT/'build/udm-seaice-winter-validation-v3/ra37-24h-v1/stage-receipt-v1.json'
DONOR_SHA='150313d70a2a9e3274aed66703e671a22b40338cb5439bb32fb4770324eeabef'
INPUT=ROOT/'build/udm-current-24h-plan/cases/ra37/wrfinput_d01'
BOUNDARY=ROOT/'build/udm-current-24h-plan/cases/ra37/wrfbdy_d01'
EXE=WRF/'main/wrf.exe'; RUN=WRF/'run'
CONFIG=WRF/'configure.wrf'; TIMEKEEPING=WRF/'share/set_timekeeping.F'; TIMEKEEPING_PP=WRF/'share/set_timekeeping.f90'
TABLE=BUILD/'source/validation/rrtmgp37/frozen-optics-lookup/nine-grid-o128-s50/frozen-ice-psd-moments.nc'
TEMPLATE=ROOT/'build/udm-nested-domain-plan/v2/namelist.input'
TEMPLATE_SHA256='83b5e85c423d441a14d7393844eed3ec0a75735c736fd8c6b0cfe5ef37d5827a'
COEFFS=('rrtmgp-gas-lw-g128.nc','rrtmgp-gas-sw-g112.nc','rrtmgp-clouds-lw-bnd.nc','rrtmgp-clouds-sw-bnd.nc')
IOFIELDS='+:h:0:QC_CU,QI_CU,CLDFRA_DP,CLDFRA_SH,mu,mub,dnw,fnm,fnp'
ALLOW_GLOBAL_ATTR_DIFFERENCES={'START_DATE','WRF_ALARM_SECS_TIL_NEXT_RING_55'}
INITIAL_DIAGNOSTIC_RESET_FIELDS={'UDM_CLDFRA','UDM_CF_STEP','UDM_CF_TOP'}
REQUIRED_HISTORY_FIELDS={'Times','XLAT','XLONG','XLAND','SEAICE','SNOW','TSK','SST','ALBEDO',
  'SWDOWN','GLW','OLR','QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL','RAINC','RAINNC',
  'RTHRATLW','RTHRATSW','CLDFRA','UDM_CLDFRA','UDM_CF_TOP','UDM_CF_STEP','QC_CU','QI_CU',
  'CLDFRA_DP','CLDFRA_SH'}
EXPECTED_UNITS={'SWDOWN':'W m-2','GLW':'W m-2','OLR':'W m-2','RTHRATLW':'K s-1','RTHRATSW':'K s-1',
  'QCLOUD':'kg kg-1','QICE':'kg kg-1','QRAIN':'kg kg-1','QSNOW':'kg kg-1','QGRAUP':'kg kg-1',
  'QHAIL':'kg kg-1','QC_CU':'kg kg-1','QI_CU':'kg kg-1','UDM_CLDFRA':'fraction',
  'UDM_CF_STEP':'step','UDM_CF_TOP':'layer','CLDFRA':'','CLDFRA_DP':'','CLDFRA_SH':''}
SURFACE_FIELDS={'XLAT','XLONG','XLAND','SEAICE','SNOW','TSK','SST','ALBEDO','SWDOWN','GLW','OLR','RAINC','RAINNC','UDM_CF_STEP','UDM_CF_TOP'}
VOLUME_FIELDS={'QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL','RTHRATLW','RTHRATSW','CLDFRA','UDM_CLDFRA','QC_CU','QI_CU','CLDFRA_DP','CLDFRA_SH'}

class GateError(RuntimeError): pass
def need(ok,msg):
    if not ok: raise GateError(msg)
def digest(p):
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def pin(p):
    p=Path(p).resolve(strict=True);return {'path':str(p),'size_bytes':p.stat().st_size,'sha256':digest(p)}
def import_integrity():
    sp=importlib.util.spec_from_file_location('ccn_runtime_integrity',INTEGRITY)
    need(sp and sp.loader,'current build-integrity adapter unavailable')
    m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m);return m
def integrity_check():
    m=import_integrity();return {'build':m.verify_build(),'donors':m.verify_donor_inputs(),'adapter':pin(INTEGRITY)}
def verify_pins(snapshot):
    for x in snapshot:
        p=Path(x['path']);need(p.exists() or p.is_symlink(),f"missing staged asset {p}")
        if x.get('directory'):
            need(p.is_dir(),f"staged asset is no longer a directory: {p}")
        else:
            got=digest(p);need(got==x['sha256'],f"asset hash changed: {p}")
        if x['symlink']:need(p.is_symlink() and str(p.resolve())==x['target'],f"symlink target changed: {p}")
        else:need(not p.is_symlink(),f"unexpected symlink: {p}")
def namelist_value(text,key,value,group):
    pat=rf'(?im)(^\s*{re.escape(key)}\s*=\s*[^\n]*$)'
    matches=list(re.finditer(pat,text))
    if matches:
        m=matches[0]
        need(len(matches)==1,f'duplicate namelist assignment {key}')
        text=text[:m.start()]+f' {key} = {value},'+text[m.end():]
        return text
    g=re.search(rf'(?im)^\s*&{re.escape(group)}\b',text)
    need(g is not None,f'missing namelist group {group}')
    end=re.search(r'(?im)^\s*/\s*$',text[g.end():])
    need(end is not None,f'missing terminator for namelist group {group}')
    pos=g.end()+end.start()
    return text[:pos]+f' {key} = {value},\n'+text[pos:]
def make_namelist(template,restart=False):
    s=template.read_text()
    # Exact edits are constrained to the approved plan. Inputs and physics options stay fixed.
    for k,v,g in [
        ('run_days','0','time_control'),('run_hours','0','time_control'),
        ('run_minutes','50' if restart else '120','time_control'),('run_seconds','0','time_control'),
        ('restart','.true.' if restart else '.false.','time_control'),
        ('restart_interval','50' if restart else '10','time_control'),
        ('override_restart_timers','.true.' if restart else '.false.','time_control'),
        ('history_interval','10, 10','time_control'),('frames_per_outfile','1, 1','time_control'),
        ('start_year','2010, 2010','time_control'),('start_month','06, 06','time_control'),
        ('start_day','11, 11','time_control'),('start_hour','01, 01' if restart else '00, 01','time_control'),
        ('start_minute','10, 10' if restart else '00, 00','time_control'),('start_second','00, 00','time_control'),
        ('end_year','2010, 2010','time_control'),('end_month','06, 06','time_control'),
        ('end_day','11, 11','time_control'),('end_hour','02, 02','time_control'),
        ('end_minute','00, 00','time_control'),('end_second','00, 00','time_control'),
        ('numtiles','2','domains'),
        ('cu_rad_feedback','.true., .false.','physics'),
        ('rrtmgp_data_path',f"'{RUN}'",'physics'),
        ('rrtmgp_udm_frozen_table',f"'{TABLE}'",'physics'),
        ('iofields_filename',"'cu_nest_iofields.txt'",'time_control')]:
        s=namelist_value(s,k,v,g)
    if restart:
        s=namelist_value(s,'write_hist_at_0h_rst','.true.','time_control')
    # Ensure immutable plan values have not drifted in the source template.
    for key, vals in {'mp_physics':'27, 27','ra_lw_physics':'37, 37','ra_sw_physics':'37, 37',
                      'cu_physics':'1, 0','input_from_file':'.true., .false.'}.items():
        m=re.search(rf'(?im)^\s*{key}\s*=\s*([^!\n]+)',s);need(m is not None,f'missing {key}')
        need(','.join(m.group(1).strip().rstrip(',').lower().split())==','.join(vals.lower().split()),f'plan option drift: {key}')
    return s

def verify_runtime_assets():
    # Adapter covers source/dependency/input receipts; these are the exact runtime links used here.
    m=integrity_check()
    template=pin(TEMPLATE)
    need(template['sha256']==TEMPLATE_SHA256,'approved nested namelist template changed')
    config_text=CONFIG.read_text(errors='replace')
    source_text=TIMEKEEPING.read_text(errors='replace')
    pp_text=TIMEKEEPING_PP.read_text(errors='replace')
    need('MOVE_NESTS' not in config_text,'MOVE_NESTS unexpectedly enabled in the frozen configure')
    need('#ifdef MOVE_NESTS' in source_text and 'WRFU_AlarmDisable( grid%alarms( COMPUTE_VORTEX_CENTER_ALARM )' in source_text,
         'source no longer documents the disabled non-MOVE_NESTS alarm branch')
    need('CALL WRFU_AlarmDisable( grid%alarms( COMPUTE_VORTEX_CENTER_ALARM )' in pp_text and
         'CALL WRFU_AlarmEnable( grid%alarms( COMPUTE_VORTEX_CENTER_ALARM )' not in pp_text,
         'preprocessed executable source does not prove alarm 55 is disabled')
    alarm_policy={'configure':pin(CONFIG),'source':pin(TIMEKEEPING),'preprocessed_source':pin(TIMEKEEPING_PP),
      'move_nests_enabled':False,'compiled_policy':'COMPUTE_VORTEX_CENTER_ALARM is disabled in the preprocessed source'}
    pinned=[pin(EXE),pin(INPUT),pin(BOUNDARY),pin(TABLE),template]
    coeff=[pin(RUN/x) for x in COEFFS]
    return {'integrity':m,'assets':pinned,'coefficients':coeff,'alarm_55_policy':alarm_policy}
def verify_stage_identity(stage):
    current=verify_runtime_assets()
    need(current['integrity']==stage['integrity'] and current['assets']==stage['runtime_assets'] and
         current['coefficients']==stage['coefficients'] and current['alarm_55_policy']==stage['alarm_55_policy'],
         'current executable/data/source/runtime identity differs from stage receipt')
    return current
def parent_case_assets():
    need(DONOR_RECEIPT.is_file() and digest(DONOR_RECEIPT)==DONOR_SHA,'accepted winter donor receipt pin differs')
    execution=json.loads(DONOR_RECEIPT.read_text())
    need(execution.get('status')=='PASS_RA37_24H','winter donor receipt is not an accepted RA37 run')
    need(execution.get('stage_receipt')==pin(DONOR_STAGE),'winter donor stage receipt does not match accepted run')
    stage=json.loads(DONOR_STAGE.read_text())
    need(stage.get('status')=='STAGED_NOT_RUN','winter donor stage status changed')
    case=stage['case'];src=Path(case['case_path'])
    return src,case['link_names']
def staged_link_plan():
    src,names=parent_case_assets();donor=json.loads(DONOR_STAGE.read_text())
    donor_links={x['name']:x for x in donor['case']['snapshot']['links']}
    excluded={'wrf.exe','wrfinput_d01','wrfinput_d02','wrfbdy_d01',
      'rrtmgp_data','frozen-ice-psd-moments.nc',*COEFFS}
    links=[]
    for name in names:
        if name in excluded:continue
        need(name in donor_links,f'donor stage has no recorded link for {name}')
        target=donor_links[name]['target'];resolved=(src/name).resolve(strict=True)
        need(str(resolved)==donor_links[name]['resolved_target'],f'donor target changed for {name}')
        if target.get('path'):
            need(digest(resolved)==target['sha256'],f'donor static asset changed for {name}')
        elif target.get('directory'):
            need(resolved.is_dir(),f'donor directory asset changed for {name}')
        links.append((name,resolved))
    links += [('wrfinput_d01',INPUT.resolve(strict=True)),('wrfbdy_d01',BOUNDARY.resolve(strict=True)),
      ('wrf.exe',EXE.resolve(strict=True)),*[(name,(RUN/name).resolve(strict=True)) for name in COEFFS],
      ('frozen-ice-psd-moments.nc',TABLE.resolve(strict=True)),('rrtmgp_data',RUN.resolve(strict=True))]
    need(len({name for name,_ in links})==len(links),'duplicate staged asset names')
    by_name=dict(links)
    need(by_name['wrfinput_d01']==INPUT.resolve(),'stage must use the pinned June parent input')
    need(by_name['wrfbdy_d01']==BOUNDARY.resolve(),'stage must use the pinned June boundary input')
    return links
def link_manifest_entry(name,path,dest):
    dest.symlink_to(path)
    entry={'name':name,'path':str(dest),'target':str(path),'symlink':True}
    if path.is_dir():entry.update(directory=True,sha256=None)
    else:entry.update(directory=False,sha256=digest(dest))
    return entry
def make_case(case_dir,template_text,restart_file=None):
    case_dir.mkdir(parents=True,exist_ok=False)
    manifest=[]
    for name,target in staged_link_plan():manifest.append(link_manifest_entry(name,target,case_dir/name))
    for name,content in [('namelist.input',template_text),('cu_nest_iofields.txt',IOFIELDS+'\n')]:
        dest=case_dir/name;dest.write_text(content);manifest.append({'name':name,'path':str(dest),'target':None,'sha256':digest(dest),'symlink':False})
    need(not (case_dir/'wrfinput_d02').exists(),'child input must remain absent for parent interpolation')
    if restart_file:
        name=restart_file.name;dest=case_dir/name;dest.symlink_to(restart_file.resolve(strict=True))
        manifest.append({'name':name,'path':str(dest),'target':str(restart_file.resolve()),'sha256':digest(dest),'symlink':True})
    return manifest

def schedule(domain,restart=False):
    base=datetime(2010,6,11,1 if restart or domain==2 else 0,10 if restart else 0)
    if restart: n=6
    elif domain==1:n=13
    else:base=datetime(2010,6,11,1);n=7
    return [(base+timedelta(minutes=10*k)).strftime('%Y-%m-%d_%H:%M:%S') for k in range(n)]
def read_times(ds):
    a=ds.variables['Times'][:];out=[]
    for row in a:
        b=row.tobytes() if hasattr(row,'tobytes') else bytes(row)
        out.append(b.decode('ascii').replace('\x00','').strip())
    return out
def inspect_numeric_variable(var):
    # Validate both stored values and the netCDF4-decoded/masked representation.
    var.set_auto_mask(True);var.set_auto_scale(False);raw=var[:]
    var.set_auto_maskandscale(True);decoded=var[:]
    var.set_auto_maskandscale(False)
    raw_data=np.asarray(np.ma.getdata(raw));decoded_data=np.asarray(np.ma.getdata(decoded))
    need(raw_data.shape==decoded_data.shape,f'{var.name}: raw/decoded shapes differ')
    sentinels=[]
    for att in ('_FillValue','missing_value'):
        if att in var.ncattrs():sentinels.extend(np.asarray(var.getncattr(att)).reshape(-1).tolist())
    dtype=np.dtype(var.dtype);key=dtype.kind+str(dtype.itemsize)
    if key in default_fillvals:sentinels.append(default_fillvals[key])
    raw_fill=decoded_fill=0
    for fv in sentinels:
        try:
            cast=np.asarray(fv,dtype=dtype)
            raw_fill+=int(np.count_nonzero(raw_data==cast))
            decoded_fill+=int(np.count_nonzero(decoded_data==cast))
        except (TypeError,ValueError,OverflowError):pass
    return {'raw_shape':list(raw_data.shape),'decoded_shape':list(decoded_data.shape),
      'raw_masked':int(np.ma.getmaskarray(raw).sum()),'decoded_masked':int(np.ma.getmaskarray(decoded).sum()),
      'raw_nonfinite':int(np.count_nonzero(~np.isfinite(raw_data))),
      'decoded_nonfinite':int(np.count_nonzero(~np.isfinite(decoded_data))),
      'raw_fill':raw_fill,'decoded_fill':decoded_fill}
def check_dataset(path,domain,restart,expected_times=None,checkpoint=False):
    with Dataset(path) as info_ds:
        variable_count=len(info_ds.variables)
    summary={'path':str(path),'sha256':digest(path),'numeric_variables':0,'variables':variable_count}
    expected_dims={'Time':1,'DateStrLen':19,'west_east':289 if domain==1 else 60,
      'south_north':189 if domain==1 else 60,'bottom_top':39,'west_east_stag':290 if domain==1 else 61,
      'south_north_stag':190 if domain==1 else 61,'bottom_top_stag':40}
    with Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        for k,v in expected_dims.items():need(k in ds.dimensions and len(ds.dimensions[k])==v,f'{path}: dimension {k} mismatch')
        times=read_times(ds);expected_times=expected_times if expected_times is not None else schedule(domain,restart);need(times==expected_times,f'{path}: timestamps {times}, expected {expected_times}')
        need(int(ds.getncattr('GRID_ID'))==domain,f'{path}: GRID_ID mismatch')
        need(int(ds.getncattr('PARENT_ID'))==(0 if domain==1 else 1),f'{path}: PARENT_ID mismatch')
        expected_start=('2010-06-11_01:10:00' if restart else ('2010-06-11_00:00:00' if domain==1 else '2010-06-11_01:00:00'))
        need(str(ds.getncattr('START_DATE'))==expected_start,f'{path}: START_DATE mismatch')
        for k,v in {'MP_PHYSICS':27,'RA_LW_PHYSICS':37,'RA_SW_PHYSICS':37,'CU_PHYSICS':1 if domain==1 else 0,
                    'ICLOUD_CU':2 if domain==1 else 0,'PARENT_GRID_RATIO':1 if domain==1 else 3,
                    'I_PARENT_START':1 if domain==1 else 100,'J_PARENT_START':1 if domain==1 else 80}.items():
            need(k in ds.ncattrs() and int(ds.getncattr(k))==v,f'{path}: {k} mismatch')
        expected_dx=20000.0 if domain==1 else 20000.0/3.0
        for k,v in {'DX':expected_dx,'DY':expected_dx}.items():
            need(k in ds.ncattrs() and abs(float(ds.getncattr(k))-v)<1.e-3,f'{path}: {k} mismatch')
        required=({'QGRAUP','QHAIL','RAINC','RAINNC','Times'} if checkpoint else set(REQUIRED_HISTORY_FIELDS))
        need(required.issubset(ds.variables),f'{path}: missing variables {sorted(required-set(ds.variables))}')
        if not checkpoint:
            for n,units in EXPECTED_UNITS.items():
                if n in required:
                    v=ds.variables[n]
                    need('units' in v.ncattrs() and str(v.getncattr('units')).strip()==units,
                         f'{path}: {n} units differ from expected {units!r}')
            for n in SURFACE_FIELDS & required:
                need(ds.variables[n].dimensions==('Time','south_north','west_east'),
                     f'{path}: {n} surface dimensions differ')
            for n in VOLUME_FIELDS & required:
                need(ds.variables[n].dimensions==('Time','bottom_top','south_north','west_east'),
                     f'{path}: {n} volume dimensions differ')
            need(ds.variables['Times'].dimensions==('Time','DateStrLen'),f'{path}: Times dimensions differ')
        raw_masked=decoded_masked=raw_nonfinite=decoded_nonfinite=raw_fill=decoded_fill=0;cu_positive={}
        for n,var in ds.variables.items():
            dtype=np.dtype(var.dtype)
            if dtype.kind not in 'iuf':continue
            quality=inspect_numeric_variable(var);summary['numeric_variables']+=1
            raw_masked+=quality['raw_masked'];decoded_masked+=quality['decoded_masked']
            raw_nonfinite+=quality['raw_nonfinite'];decoded_nonfinite+=quality['decoded_nonfinite']
            raw_fill+=quality['raw_fill'];decoded_fill+=quality['decoded_fill']
            if domain==1 and n in {'QC_CU','QI_CU'}:cu_positive[n]=int(np.count_nonzero(np.asarray(var[:])>0))
        need(raw_masked==0 and decoded_masked==0 and raw_nonfinite==0 and decoded_nonfinite==0 and raw_fill==0 and decoded_fill==0,
          f'{path}: raw/decoded mask/nonfinite/fill counts {raw_masked}/{decoded_masked}/{raw_nonfinite}/{decoded_nonfinite}/{raw_fill}/{decoded_fill}')
        if domain==1 and not checkpoint:
            for n in ('QC_CU','QI_CU','CLDFRA_DP','CLDFRA_SH'):
                need(ds.variables[n].size>0,f'{path}: empty CU diagnostic {n}')
        if restart and not checkpoint and times==['2010-06-11_01:10:00']:
            for n in INITIAL_DIAGNOSTIC_RESET_FIELDS:
                need(n in ds.variables and np.all(np.asarray(ds.variables[n][:])==-1),
                     f'{path}: initial restart diagnostic {n} is not the expected -1 not-yet-diagnosed sentinel')
        summary.update({'times':times,'raw_masked_numeric_values':raw_masked,'decoded_masked_numeric_values':decoded_masked,
          'raw_nonfinite_numeric_values':raw_nonfinite,'decoded_nonfinite_numeric_values':decoded_nonfinite,
          'raw_default_fill_values':raw_fill,'decoded_default_fill_values':decoded_fill,'cu_positive_counts':cu_positive})
    return summary
def scan_outputs(case,restart):
    out={'domains':{},'cu_positive_totals':{'QC_CU':0,'QI_CU':0}}
    for d in (1,2):
        files=sorted(case.glob(f'wrfout_d{d:02d}_*'))
        expected=schedule(d,restart)
        need([p.name for p in files]==[f'wrfout_d{d:02d}_{t}' for t in expected],f'd{d} history filenames/schedule differ')
        checks=[check_dataset(p,d,restart,[p.name.removeprefix(f'wrfout_d{d:02d}_')]) for p in files]
        for x in checks:
            for k,n in x.get('cu_positive_counts',{}).items():out['cu_positive_totals'][k]+=n
        out['domains'][f'd{d:02d}']={'files':checks,'history_count':len(files),'times':expected}
    if not restart:
        need(any(out['cu_positive_totals'].values()),'no positive parent CU condensate appeared in requested history')
        cpout={}
        for d in (1,2):
            cp=case/f'wrfrst_d{d:02d}_2010-06-11_01:10:00';need(cp.is_file(),f'missing d{d} own checkpoint at 01:10')
            cpout[f'd{d:02d}_0110']=check_dataset(cp,d,False,['2010-06-11_01:10:00'],checkpoint=True)
    else:
        cpout={}
    for d in (1,2):
        cp=case/f'wrfrst_d{d:02d}_2010-06-11_02:00:00';need(cp.is_file(),f'missing d{d} own final checkpoint at 02:00')
        cpout[f'd{d:02d}_0200']=check_dataset(cp,d,restart,['2010-06-11_02:00:00'],checkpoint=True)
    out['checkpoints']=cpout
    return out

def runtime_environment():
    mpiexec=ROOT/'build/deps/mpich-sock/bin/mpiexec'
    env=os.environ.copy()
    cleared=[]
    for k in list(env):
        if k.startswith(('WRF_','GOMP_','KMP_','OMP_','MPICH_','HYDRA_')) or k=='LD_PRELOAD':
            cleared.append(k);env.pop(k,None)
    env.update({'PATH':str(mpiexec.parent)+os.pathsep+env.get('PATH',''),
      'LD_LIBRARY_PATH':':'.join(map(str,[ROOT/'build/deps/netcdf/lib',ROOT/'build/deps/mpich-sock/lib',ROOT/'build/deps/root/usr/lib/x86_64-linux-gnu','/usr/lib/x86_64-linux-gnu'])),
      'MPICH_INTERFACE_HOSTNAME':'127.0.0.1','OMP_NUM_THREADS':'2','OMP_DYNAMIC':'FALSE',
      'OMP_MAX_ACTIVE_LEVELS':'1','OMP_NESTED':'FALSE','OMP_PROC_BIND':'FALSE','OMP_STACKSIZE':'512M',
      'OPENBLAS_NUM_THREADS':'1','LC_ALL':'C'})
    return env,sorted(cleared)

def run_model(case,kind,on_launch=None,timeout=3600):
    mpiexec=ROOT/'build/deps/mpich-sock/bin/mpiexec'
    env,cleared_env=runtime_environment()
    ldd=subprocess.run(['ldd',str(EXE)],env=env,text=True,capture_output=True,check=False)
    need(ldd.returncode==0 and 'not found' not in ldd.stdout,'unresolved WRF shared library')
    ver=subprocess.run([str(mpiexec),'--version'],env=env,text=True,capture_output=True,check=False)
    need(ver.returncode==0 and 'HYDRA' in ver.stdout,'MPICH launcher check failed')
    stack=512*1024*1024
    def preexec():
        _,hard=resource.getrlimit(resource.RLIMIT_STACK)
        if hard!=resource.RLIM_INFINITY and hard<stack:raise RuntimeError('hard stack limit less than 512 MiB')
        resource.setrlimit(resource.RLIMIT_STACK,(stack,hard))
    cmd=[str(mpiexec),'-launcher','fork','-iface','lo','-n','4',str(EXE)]
    log=(case/'run.log').open('xb');proc=subprocess.Popen(cmd,cwd=case,env=env,stdout=log,stderr=subprocess.STDOUT,start_new_session=True,preexec_fn=preexec)
    if on_launch:on_launch(proc.pid)
    try:
        rc=proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        os.killpg(proc.pid,signal.SIGTERM)
        try:proc.wait(timeout=20)
        except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
        rc=124
    finally:log.close()
    ranks={p.name:('SUCCESS COMPLETE WRF' in p.read_text(errors='replace')) for p in sorted(case.glob('rsl.error.*'))}
    allranks=(len(ranks)==4 and all(ranks.values()))
    logtxt='\n'.join(p.read_text(errors='replace') for p in sorted(case.glob('rsl.*')))
    interp=bool(re.search(r'Initializing nest domain #\s*2 by horizontally interpolating parent domain #\s*1\.',logtxt))
    fatal=bool(re.search(r'\bFATAL\b',logtxt,re.IGNORECASE))
    return {'command':cmd,'returncode':rc,'rank_success':ranks,'all_rank_success':allranks,'fatal_present':fatal,
      'parent_interpolation_logged':interp if kind=='continuous' else None,'child_input_absent':not (case/'wrfinput_d02').exists(),
      'environment':{k:env[k] for k in ('MPICH_INTERFACE_HOSTNAME','OMP_NUM_THREADS','OMP_DYNAMIC','OMP_MAX_ACTIVE_LEVELS','OMP_STACKSIZE','LD_LIBRARY_PATH')},
      'cleared_environment_variables':cleared_env,
      'ldd':ldd.stdout,'mpich_version':ver.stdout}

def resolved_libraries():
    env,_=runtime_environment()
    proc=subprocess.run(['ldd',str(EXE)],env=env,text=True,capture_output=True,check=False)
    need(proc.returncode==0 and 'not found' not in proc.stdout,'unresolved WRF shared library')
    paths=set(re.findall(r'=>\s+(/\S+)',proc.stdout))
    paths.update(re.findall(r'^\s*(/\S+)\s+\(',proc.stdout,re.MULTILINE))
    result={}
    for path in sorted(paths):
        p=Path(path).resolve(strict=True)
        need(p.is_file(),f'ldd library is not a file: {path}')
        result[str(p)]={'size_bytes':p.stat().st_size,'sha256':digest(p)}
    need(bool(result),'ldd resolved no shared libraries')
    return result

def _json_value(value):
    arr=np.asarray(value)
    return arr.item() if arr.ndim==0 else arr.tolist()
def _alarm_disabled(ds):
    if 'WRF_ALARM_ISRINGING_55' not in ds.ncattrs():return False
    value=np.asarray(ds.getncattr('WRF_ALARM_ISRINGING_55')).reshape(-1)[0]
    return str(value).strip().lower() in {'0','false','f'}
def expected_alarm_elapsed(domain,restart,timestamp):
    stamp=datetime.strptime(timestamp,'%Y-%m-%d_%H:%M:%S')
    start=datetime(2010,6,11,1,10) if restart else datetime(2010,6,11,0 if domain==1 else 1)
    return float((start-stamp).total_seconds())
def validate_alarm_elapsed(ds,domain,restart,timestamp):
    if 'WRF_ALARM_SECS_TIL_NEXT_RING_55' not in ds.ncattrs():return None
    need(_alarm_disabled(ds),'alarm-55 countdown present while alarm is enabled')
    actual=np.asarray(ds.getncattr('WRF_ALARM_SECS_TIL_NEXT_RING_55')).astype(np.float64).reshape(-1)
    expected=expected_alarm_elapsed(domain,restart,timestamp)
    need(actual.size>0 and np.all(actual==expected),
      f'alarm-55 elapsed anchor differs: domain={domain}, restart={restart}, time={timestamp}, expected={expected}, actual={actual.tolist()}')
    return {'expected_seconds':expected,'actual_seconds':actual.tolist(),'anchor_start':('2010-06-11_01:10:00' if restart else ('2010-06-11_00:00:00' if domain==1 else '2010-06-11_01:00:00'))}
def compare_dataset(a,b,restart_initial=False,domain=1,restart=False,timestamp=None):
    result={'a':pin(a),'b':pin(b),'global_attr_exceptions':[],'initial_diagnostic_resets':[],'variables':[],'passed':True,
            'whole_file_byte_equality_claimed':False}
    with Dataset(a) as x,Dataset(b) as y:
        x.set_auto_maskandscale(False);y.set_auto_maskandscale(False)
        if timestamp:
            alarm_x=validate_alarm_elapsed(x,domain,False,timestamp)
            alarm_y=validate_alarm_elapsed(y,domain,True,timestamp)
            result['alarm_55_elapsed_anchor']={'continuous':alarm_x,'restart':alarm_y}
        need(set(x.dimensions)==set(y.dimensions),'dimension names differ')
        need({k:len(v) for k,v in x.dimensions.items()}=={k:len(v) for k,v in y.dimensions.items()},'dimension lengths differ')
        need(set(x.variables)==set(y.variables),'variable sets differ')
        need((set(x.ncattrs()) ^ set(y.ncattrs())) <= ALLOW_GLOBAL_ATTR_DIFFERENCES,'global attribute sets differ')
        for k in sorted(set(x.ncattrs())|set(y.ncattrs())):
            if k not in x.ncattrs() or k not in y.ncattrs():
                if k=='START_DATE':
                    result['global_attr_exceptions'].append({'name':k,'left':_json_value(x.getncattr(k)) if k in x.ncattrs() else None,'right':_json_value(y.getncattr(k)) if k in y.ncattrs() else None})
                    continue
                raise GateError(f'global attribute {k} missing on one side')
            xv,yv=x.getncattr(k),y.getncattr(k)
            if np.array_equal(np.asarray(xv),np.asarray(yv)):continue
            if k=='START_DATE':
                result['global_attr_exceptions'].append({'name':k,'left':_json_value(xv),'right':_json_value(yv)})
            elif k=='WRF_ALARM_SECS_TIL_NEXT_RING_55':
                need(_alarm_disabled(x) and _alarm_disabled(y),'alarm-55 countdown changed while alarm is enabled')
                need(timestamp is not None,'alarm-55 difference lacks a timestamp for elapsed-anchor validation')
                result['global_attr_exceptions'].append({'name':k,'left':_json_value(xv),'right':_json_value(yv),
                    'interpretation':'elapsed-time anchor for disabled vortex alarm 55; expected absolute seconds are validated separately'})
            else:raise GateError(f'global attribute mismatch: {k}')
        for name in x.variables:
            vx,vy=x.variables[name],y.variables[name]
            need(vx.dimensions==vy.dimensions and vx.dtype==vy.dtype,f'variable metadata shape/type differs: {name}')
            need(set(vx.ncattrs())==set(vy.ncattrs()),f'variable attrs differ: {name}')
            for att in vx.ncattrs():need(np.array_equal(np.asarray(vx.getncattr(att)),np.asarray(vy.getncattr(att))),f'{name} attr differs: {att}')
            ax=np.asarray(vx[:]);ay=np.asarray(vy[:]);equal=ax.shape==ay.shape and ax.dtype==ay.dtype and ax.tobytes()==ay.tobytes()
            special=bool(restart_initial and name in INITIAL_DIAGNOSTIC_RESET_FIELDS)
            if special:
                reset=np.all(ay==-1)
                need(reset,f'initial restarted {name} is not entirely the -1 sentinel')
                result['initial_diagnostic_resets'].append({'timestamp':'2010-06-11_01:10:00','field':name,
                    'continuous_sha256':hashlib.sha256(ax.tobytes()).hexdigest(),
                    'restart_sha256':hashlib.sha256(ay.tobytes()).hexdigest(),'restart_is_minus1_sentinel':bool(reset),
                    'arrays_equal':bool(equal),'reason':'diagnostic state is not checkpointed; first restart-time history is pre-diagnostic'})
                # The expected reset is scoped to these three fields at this one timestamp only.
            elif not equal:
                result['passed']=False
            result['variables'].append({'name':name,'shape':list(ax.shape),'dtype':ax.dtype.str,
                'bitwise_equal':bool(equal),'classification':'initial_diagnostic_reset' if special else ('exact' if equal else 'unexpected_difference')})
    result['scope']='Stored/raw variable arrays and metadata exact except the three explicitly checked initial restart diagnostics; decoded finite/mask/fill validity is checked independently on every output. START_DATE and validated disabled alarm-55 elapsed anchors are separately reported. This is not whole-file byte parity.'
    return result
def compare_cases(root):
    c=root/'continuous';r=root/'restart';pairs=[]
    continuous=json.loads((c/'execution.json').read_text())
    restart=json.loads((r/'execution.json').read_text())
    stage=json.loads((root/'stage.json').read_text())
    need(stage.get('status')=='STAGED_NOT_RUN' and stage.get('runner')==pin(Path(__file__)),
         'stage receipt status/runner provenance mismatch')
    verify_stage_identity(stage)
    need(stage.get('source_template')==pin(TEMPLATE) and stage.get('template_expected_sha256')==TEMPLATE_SHA256,
         'staged namelist-template provenance mismatch')
    verify_pins(stage['continuous_assets']);verify_pins(stage['restart_assets'])
    validate_execution_receipt(continuous,'continuous',root,stage)
    validate_execution_receipt(restart,'restart',root,stage,continuous)
    for run_case in (continuous,restart):
        for kind,entries in [('domains',run_case['output_validation']['domains'].values()),('checkpoints',run_case['output_validation']['checkpoints'].values())]:
            for domain_entry in entries:
                for file_entry in domain_entry.get('files',[]) if kind=='domains' else [domain_entry]:
                    f=Path(file_entry['path']);need(digest(f)==file_entry['sha256'],f'output changed since execution receipt: {f}')
    for d in (1,2):
        for t in schedule(d,True):
            a=c/f'wrfout_d{d:02d}_{t}';b=r/f'wrfout_d{d:02d}_{t}'
            need(a.is_file() and b.is_file(),f'missing comparison history {a} or {b}')
            pairs.append({'artifact':'history','domain':d,'time':t,**compare_dataset(a,b,restart_initial=(t=='2010-06-11_01:10:00'),domain=d,restart=False,timestamp=t)})
        a=c/f'wrfrst_d{d:02d}_2010-06-11_02:00:00';b=r/f'wrfrst_d{d:02d}_2010-06-11_02:00:00'
        need(a.is_file() and b.is_file(),f'missing final checkpoint comparison for d{d}')
        pairs.append({'artifact':'checkpoint','domain':d,'time':'2010-06-11_02:00:00',
          **compare_dataset(a,b,domain=d,restart=False,timestamp='2010-06-11_02:00:00')})
    return {'status':'PASS_SCOPED_RESTART_PARITY' if all(p['passed'] for p in pairs) else 'FAIL_PRESERVED',
      'global_metadata_exceptions':['START_DATE','WRF_ALARM_SECS_TIL_NEXT_RING_55 only when WRF_ALARM_ISRINGING_55 is disabled'],
      'initial_history_diagnostic_exception':{'time':'2010-06-11_01:10:00','fields':sorted(INITIAL_DIAGNOSTIC_RESET_FIELDS),
       'required_restart_values':'all -1 sentinel','all_other_fields':'exact'},
      'whole_file_byte_parity_claimed':False,'comparison_scope':'stored/raw arrays and metadata; decoded validity independently checked; endpoint checkpoints plus shared post-checkpoint histories',
      'pairs':pairs}
def validate_execution_receipt(receipt,kind,root,stage,continuous=None):
    need(receipt.get('kind')==kind and receipt.get('status')==('PASS_CONTINUOUS' if kind=='continuous' else 'PASS_RESTART'),
         f'{kind} execution receipt status mismatch')
    need(receipt.get('runner')==pin(Path(__file__)),'execution receipt runner pin mismatch')
    need(receipt.get('stage')==pin(root/'stage.json'),'execution receipt stage pin mismatch')
    need(receipt.get('before_integrity')==stage['integrity'] and receipt.get('after_integrity')==stage['integrity'],
         'execution source/build/donor integrity differs from stage receipt')
    expected_runtime={'integrity':stage['integrity'],'assets':stage['runtime_assets'],
      'coefficients':stage['coefficients'],'alarm_55_policy':stage['alarm_55_policy']}
    need(receipt.get('before_runtime_identity')==expected_runtime and receipt.get('after_runtime_identity')==expected_runtime,
         'execution receipt lacks matching before/after runtime data and alarm-policy identity')
    need(receipt.get('after_pins_valid') is True and receipt.get('model_invocations')==1 and
         receipt.get('returncode')==0 and receipt.get('all_rank_success') is True and not receipt.get('fatal_present'),
         f'{kind} execution evidence is not an all-rank nonfatal success')
    need(receipt.get('child_input_absent') is True,'child input was unexpectedly present; interpolation contract changed')
    if kind=='continuous':need(receipt.get('parent_interpolation_logged') is True,'parent interpolation evidence missing')
    base=stage['continuous_assets'] if kind=='continuous' else stage['restart_assets']
    assets=receipt.get('assets_before',[])
    need(assets[:len(base)]==base,f'{kind} static staged-asset lineage differs from stage receipt')
    verify_pins(assets)
    if kind=='restart':
        need(continuous is not None,'restart receipt lacks continuous lineage')
        cps=continuous.get('output_validation',{}).get('checkpoints',{})
        for d in (1,2):
            key=f'd{d:02d}_0110';expected=cps.get(key)
            need(expected is not None,f'continuous receipt lacks {key} checkpoint pin')
            name=f'wrfrst_d{d:02d}_2010-06-11_01:10:00';linked=Path(root/'restart'/name)
            need(expected.get('path')==str(root/'continuous'/name),f'continuous receipt checkpoint path mismatch: {key}')
            need(linked.is_symlink() and str(linked.resolve(strict=True))==expected['path'],f'restart does not link its own d{d} checkpoint')
            need(digest(linked)==expected['sha256'],f'restart d{d} checkpoint hash differs from continuous output receipt')
            entry=next((x for x in assets if x['name']==name),None)
            need(entry is not None and entry['sha256']==expected['sha256'] and entry['target']==expected['path'],
                 f'restart asset manifest does not bind continuous checkpoint {key}')
def require_fresh_root(root):
    need(not root.exists() and not root.is_symlink(),f'output root already exists; preserve: {root}')
def main():
    ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('mode',choices=['preflight','stage','run','compare'])
    ap.add_argument('--root',type=Path,required=True);ap.add_argument('--stage-sha');ap.add_argument('--kind',choices=['continuous','restart'])
    ap.add_argument('--execute',action='store_true');ap.add_argument('--stage-go',action='store_true');args=ap.parse_args()
    root=args.root.resolve();need(root!=HERE and HERE not in root.parents,'runtime root must be outside harness directory')
    if args.mode=='preflight':
        data=verify_runtime_assets();require_fresh_root(root)
        result={'status':'READY_NOT_STAGED','integrity':data['integrity'],'runtime_assets':data['assets'],
          'coefficients':data['coefficients'],'alarm_55_policy':data['alarm_55_policy'],
          'plan':json.loads(PLAN.read_text()),'model_invocations':0}
    elif args.mode=='stage':
        data=verify_runtime_assets();require_fresh_root(root)
        if not args.stage_go:
            result={'status':'READY_NOT_STAGED','integrity':data['integrity'],'model_invocations':0}
        else:
            root.parent.mkdir(parents=True,exist_ok=True);root.mkdir()
            template=TEMPLATE
            original=template.read_text();cont=make_namelist(template,False);restart=make_namelist(template,True)
            m0=make_case(root/'continuous',cont);m1=make_case(root/'restart',restart)
            stage={'schema':'udm-cu-nest-runtime-stage-v1','status':'STAGED_NOT_RUN','runner':pin(Path(__file__)),
              'integrity':data['integrity'],'runtime_assets':data['assets'],'coefficients':data['coefficients'],
              'alarm_55_policy':data['alarm_55_policy'],
              'source_template':pin(template),'template_expected_sha256':TEMPLATE_SHA256,
              'template_original_sha256':digest(template),
              'continuous_namelist_sha256':digest(root/'continuous/namelist.input'),
              'restart_namelist_sha256':digest(root/'restart/namelist.input'),
              'continuous_assets':m0,'restart_assets':m1,'model_invocations':0,
              'restart_policy':{'required_checkpoints':['2010-06-11_01:10:00','2010-06-11_02:00:00'],'domains':[1,2],
              'continuous_restart_interval_minutes':10,'restart_continuation_interval_minutes':50,
              'source':'01:10 checkpoints from continuous run; both runs produce final 02:00 checkpoints for endpoint comparison'}}
            (root/'stage.json').write_text(json.dumps(stage,indent=2,sort_keys=True)+'\n')
            result={'status':stage['status'],'stage':pin(root/'stage.json'),'model_invocations':0}
    elif args.mode=='run':
        need(args.stage_sha and args.kind,'run requires --stage-sha and --kind')
        stagepath=root/'stage.json';need(digest(stagepath)==args.stage_sha,'stage receipt SHA mismatch')
        stage=json.loads(stagepath.read_text());need(stage['status']=='STAGED_NOT_RUN','stage not in unused state')
        need(stage['runner']==pin(Path(__file__)),'runner changed after stage')
        runtime_before=verify_stage_identity(stage);live=runtime_before['integrity']
        case=root/args.kind;need(case.is_dir(),f'missing staged case {case}')
        need(not (case/'execution.json').exists() and not (case/'execution.json').is_symlink(),
             'execution receipt collision')
        dynamic_restart=[]
        if args.kind=='restart':
            cont=root/'continuous';need((cont/'execution.json').is_file(),'continuous run must complete first')
            cexec=json.loads((cont/'execution.json').read_text())
            validate_execution_receipt(cexec,'continuous',root,stage)
            checkpoint_pins=cexec.get('output_validation',{}).get('checkpoints',{})
            for d in (1,2):
                rst=cont/f'wrfrst_d{d:02d}_2010-06-11_01:10:00';need(rst.is_file(),f'missing own d{d} checkpoint')
                expected=checkpoint_pins.get(f'd{d:02d}_0110')
                need(expected is not None and expected.get('path')==str(rst) and digest(rst)==expected.get('sha256'),
                     f'd{d} 01:10 checkpoint does not match the accepted continuous receipt')
                dst=case/rst.name
                if dst.exists() or dst.is_symlink():raise GateError(f'restart asset collision: {dst}')
                if args.execute:
                    dst.symlink_to(rst.resolve())
                    dynamic_restart.append({'name':dst.name,'path':str(dst),'target':str(rst.resolve()),'sha256':digest(dst),'symlink':True})
        snapshot=stage['continuous_assets'] if args.kind=='continuous' else stage['restart_assets']+dynamic_restart;verify_pins(snapshot)
        if not args.execute:
            result={'status':'READY_NOT_RUN','model_invocations':0,'kind':args.kind}
        else:
            libs_before=resolved_libraries()
            receipt={'status':'RUNNING','kind':args.kind,'runner':pin(Path(__file__)),'stage':pin(stagepath),
              'before_integrity':live,'before_runtime_identity':runtime_before,
              'resolved_runtime_libraries_before':libs_before,
              'model_invocations':0,'assets_before':snapshot}
            receipt_path=case/'execution.json';receipt_path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
            try:
                def launched(pid):
                    receipt.update(model_invocations=1,process_group_pid=pid)
                    receipt_path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n')
                run=run_model(case,args.kind,on_launch=launched);receipt.update(run)
                output=scan_outputs(case,args.kind=='restart')
                receipt['output_validation']=output
                ok=run['returncode']==0 and run['all_rank_success'] and not run['fatal_present'] and (args.kind!='continuous' or run['parent_interpolation_logged']) and run['child_input_absent'] and receipt['model_invocations']==1
                receipt['status']=('PASS_CONTINUOUS' if args.kind=='continuous' else 'PASS_RESTART') if ok else 'FAIL_PRESERVED'
            except Exception as e:
                receipt['status']='FAIL_PRESERVED';receipt['error']=repr(e)
            finally:
                try:
                    runtime_after=verify_stage_identity(stage);after=runtime_after['integrity']
                    need(after==live,'runtime/build/source assets changed during run')
                    verify_pins(snapshot)
                    libs_after=resolved_libraries();need(libs_after==libs_before,'resolved shared libraries changed during run')
                    receipt['after_integrity']=after;receipt['after_runtime_identity']=runtime_after
                    receipt['resolved_runtime_libraries_after']=libs_after;receipt['after_pins_valid']=True
                except Exception as e:
                    receipt.update(status='FAIL_PRESERVED',after_pins_valid=False,after_integrity_error=repr(e))
            receipt_path.write_text(json.dumps(receipt,indent=2,sort_keys=True)+'\n');result=receipt
    else:
        need(args.stage_sha,'compare requires --stage-sha');need(digest(root/'stage.json')==args.stage_sha,'stage hash mismatch')
        need(not (root/'comparison.json').exists() and not (root/'comparison.json').is_symlink(),
             'comparison receipt collision; preserve existing evidence')
        continuous=json.loads((root/'continuous/execution.json').read_text());restart=json.loads((root/'restart/execution.json').read_text())
        need(continuous['status']=='PASS_CONTINUOUS' and restart['status']=='PASS_RESTART','both run receipts must pass')
        cmp=compare_cases(root);result=cmp
        (root/'comparison.json').write_text(json.dumps(cmp,indent=2,sort_keys=True)+'\n')
    print(json.dumps({'status':result.get('status'),'model_invocations':result.get('model_invocations',0)},indent=2))
    return 0 if result.get('status','').startswith(('PASS','READY','STAGED')) else 1
if __name__=='__main__':
    try:raise SystemExit(main())
    except Exception as e:print(json.dumps({'status':'FAIL_NO_IMPLICIT_ACTION','error':str(e),'model_invocations':0},indent=2),file=sys.stderr);raise SystemExit(2)
