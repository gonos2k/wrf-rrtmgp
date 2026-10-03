#!/usr/bin/env python3
"""Fresh CCN-init runtime controls. Prepare/run/compare; run requires --execute."""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, os, re, sys
from pathlib import Path
import numpy as np
from netCDF4 import Dataset

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
BASE_PATH=ROOT/'build/udm-cu-current-omp-runtime-v2/runtime.py'
BASE_SHA='126775590ee39f9c9170024f1b498ce2df86eee19654950b89e4ba92fdedb52a'
INTEGRITY_PATH=HERE/'runtime_integrity.py'
if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest()!=BASE_SHA: raise ValueError('pinned shared runtime changed before import')
def load(name,path):
    sp=importlib.util.spec_from_file_location(name,path);mod=importlib.util.module_from_spec(sp);sp.loader.exec_module(mod);return mod
base=load('pinned_cu_runtime',BASE_PATH)
integrity=load('ccn_runtime_integrity',INTEGRITY_PATH)
m=base.m
if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest()!=BASE_SHA: raise ValueError('pinned shared runtime changed')
FRESH=ROOT/'build/udm37-ccn-tile-init-gnu-v1/source/WRF/main/wrf.exe'
PROBE=ROOT/'build/udm-cmake-openmp-full/runtime-preflight-v3/libgomp_probe.so'
PROBE_SHA='b7b691789827e149c9f3f2b0230b594d5e5ae942d669b1def11c7d99b703aedf'
RA4_CONTROL=ROOT/'build/udm-cu-current-omp-ra4-control-v1/control.py'
RA4_CONTROL_SHA='31604049a2c4356927f3aaa8d42e08dbaecc74c94097a48869ca783d34497b2d'
TIMES=['2000-01-24_'+str(h)+':00:00' for h in (12,13,14,15)]
ARMS={'ra37-omp1':('ra37',37,1),'ra37-omp2':('ra37',37,2),'ra37-omp2-probe':('ra37',37,2),'ra4-omp1':('ra4',4,1)}

def pin(path):return m.pin(Path(path))
def require_pin(obj):return m.check_pin(obj)
def no_collision(path):m.collision(path)

def ra4_nml(original):
    text=base.nml(original)
    for k in ('ra_lw_physics','ra_sw_physics'):
        vals=re.findall(r'(?im)^\s*'+k+r'\s*=\s*(\d+)\s*,?',text)
        if vals!=['4']:raise ValueError('RA4 parent namelist binding changed: '+k)
    return text

def parent_data(arm):
    if arm=='ra4':
        if hashlib.sha256(RA4_CONTROL.read_bytes()).hexdigest()!=RA4_CONTROL_SHA:raise ValueError('RA4 control adapter changed')
        control=load('pinned_ra4_control',RA4_CONTROL)
        return control.parent4()
    return base.parent()

def prepare(root):
    root=root.resolve()
    if root.exists():raise FileExistsError('stage output already exists; preserve it: '+str(root))
    build=integrity.verify_build();donors=integrity.verify_donor_inputs()
    m.require_hash(PROBE,PROBE_SHA)
    probe_libs=m.library_pins(PROBE,base.parent()[2].ld_library_path)
    if hashlib.sha256(BASE_PATH.read_bytes()).hexdigest()!=BASE_SHA:raise ValueError('shared runtime changed during preflight')
    root.parent.mkdir(parents=True,exist_ok=True);root.mkdir()
    receipt={'schema':'ccn-tile-init-current-runtime-stage-v1','status':'STAGED_NOT_RUN','runner':pin(Path(__file__)),
             'integrity_module':pin(INTEGRITY_PATH),'build_identity':build,'donor_receipts':donors,
             'shared_runtime':pin(BASE_PATH),'probe':pin(PROBE),'probe_libraries':probe_libs,'arms':{},'model_invocations':0}
    try:
        for name,(arm,rad,threads) in ARMS.items():
            pr,stage,args=parent_data(arm);source_case=Path(stage['case']['case_path']);case=root/name;case.mkdir()
            for item in stage['case']['link_names']:
                target=FRESH if item=='wrf.exe' else (source_case/item).resolve(strict=True)
                (case/item).symlink_to(target)
            original=source_case/'namelist.input';raw=original.read_text()
            edited=base.nml(raw) if rad==37 else ra4_nml(raw)
            (case/'namelist.input').write_text(edited)
            e=dict(stage['case']);e.update({'case_path':str(case),'arm':arm,'radiation':rad,'threads':threads,
               'expected_variable_count':225 if rad==37 else 222,'expected_numeric_count':224 if rad==37 else 221,
               'original_namelist':pin(original),'source_parent_receipt':pin(Path(pr['stage_receipt']['path']))})
            e['snapshot']=m.snapshot_case(e);receipt['arms'][name]=e
        receipt['fresh_executable']=pin(FRESH)
        if any(next(x for x in v['snapshot']['links'] if x['name']=='wrf.exe')['resolved_target'] != str(FRESH.resolve()) for v in receipt['arms'].values()):
            raise ValueError('fresh executable is not bound in every case')
        # Verify named source-case links and stage contents once more before receipt publication.
        for name,e in receipt['arms'].items():
            if m.snapshot_case(e)!=e['snapshot']:raise ValueError('staged case changed during preparation: '+name)
        if integrity.verify_build()['binary']!=receipt['fresh_executable']:raise ValueError('fresh executable changed during stage')
        m.write_json(root/'stage.json',receipt)
    except Exception as exc:
        m.write_json(root/'stage-failure.json',{'status':'STAGE_FAIL_PRESERVED','error':repr(exc),'model_invocations':0})
        raise
    return {'status':'STAGED_NOT_RUN','stage':pin(root/'stage.json'),'arms':sorted(receipt['arms'])}

def validate_stage(root,stage_sha):
    root=root.resolve();stage_path=root/'stage.json'
    if pin(stage_path)['sha256']!=stage_sha:raise ValueError('stage receipt pin mismatch')
    s=json.loads(stage_path.read_text())
    if s['status']!='STAGED_NOT_RUN' or s['model_invocations']!=0:raise ValueError('stage has already been used')
    if s['runner']!=pin(Path(__file__)) or s['integrity_module']!=pin(INTEGRITY_PATH) or s['shared_runtime']!=pin(BASE_PATH):raise ValueError('runner/helper changed')
    live=integrity.verify_build()
    if live!=s['build_identity'] or pin(FRESH)!=s['fresh_executable']:raise ValueError('fresh build changed')
    integrity.verify_donor_inputs();require_pin(s['probe']);m.require_hash(PROBE,PROBE_SHA)
    donor_args=base.parent()[2]
    if m.library_pins(PROBE,donor_args.ld_library_path)!=s['probe_libraries']:raise ValueError('observer dependency libraries changed')
    for name,e in s['arms'].items():
        if m.snapshot_case(e)!=e['snapshot']:raise ValueError('case inputs/link bindings changed: '+name)
        m.check_pin(e['original_namelist'])
    return s

def validate_outputs(e):
    case=Path(e['case_path']);rad=e['radiation']
    hist=sorted(case.glob('wrfout_d01_*'));rst=sorted(case.glob('wrfrst_d01_*'))
    if [x.name for x in hist]!=['wrfout_d01_'+TIMES[0]] or [x.name for x in rst]!=['wrfrst_d01_'+TIMES[-1]]:raise ValueError('output files/times unexpected')
    h=m.validate_dataset(hist[0],TIMES,rad);c=m.validate_dataset(rst[0],[TIMES[-1]],rad)
    h['default_fill_check']=base.default_fills(hist[0]);c['default_fill_check']=base.default_fills(rst[0]);c['surface']=m.checkpoint_diagnostics(rst[0])
    good=h['passed'] and c['passed'] and h['variable_count']==e['expected_variable_count'] and h['numeric_variable_count']==e['expected_numeric_count'] and c['numeric_variable_count']==663 and h['default_fill_check']['passed'] and c['default_fill_check']['passed'] and c['surface']['passed']
    if rad==37:
        with Dataset(hist[0]) as ds:
            h['icloud_cu']=int(ds.getncattr('ICLOUD_CU'));h['sw_positive_cells']=[int(np.count_nonzero(ds['SWDOWN'][i]>0)) for i in range(4)]
        with Dataset(rst[0]) as ds:
            ds.set_auto_maskandscale(False);c['cu_positive_cells']={x:int(np.count_nonzero(ds[x][:]>0)) for x in ('QC_CU','QI_CU')}
        good=good and h['icloud_cu']==2 and all(h['sw_positive_cells'][1:]) and all(c['cu_positive_cells'].values())
    return {'passed':bool(good),'history':h,'checkpoint':c}

def run(root,stage_sha,arm,execute):
    root=root.resolve();out=root/arm/'execution.json'
    if out.exists():raise FileExistsError('execution receipt already exists; preserve it')
    s=validate_stage(root,stage_sha);e=s['arms'][arm];donor=parent_data(e['arm'])[2]
    m.unused_case(e)
    if not execute:return {'status':'READY_NOT_RUN','actual_model_invocations':0}
    r={'status':'RUNNING','runner':pin(Path(__file__)),'stage':pin(root/'stage.json'),'arm':arm,'actual_model_invocations':0,'before_pins_valid':True}
    with out.open('x') as f:f.write(json.dumps(r,indent=2)+'\n')
    probe_log=Path(e['case_path'])/'gomp-workers.log'
    try:
        original_env=m._original.clean_run_env
        def env(*args):
            v,cleared=original_env(*args); extra=[k for k in v if k.startswith(('WRF_UDM_','WRF_OMP_','GOMP_','KMP_'))]
            for k in extra:v.pop(k,None)
            v.update({'OMP_NUM_THREADS':str(e['threads']),'OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1','OMP_NESTED':'FALSE','OMP_PROC_BIND':'FALSE','OPENBLAS_NUM_THREADS':'1'})
            if arm=='ra37-omp2-probe':v.update({'LD_PRELOAD':str(PROBE),'WRF_OMP_PROBE_LOG':str(probe_log)})
            r['runtime_env']={k:x for k,x in v.items() if k.startswith(('OMP_','WRF_','GOMP_','KMP_')) or k in ('LD_PRELOAD','LD_LIBRARY_PATH','MPICH_INTERFACE_HOSTNAME','OPENBLAS_NUM_THREADS')}
            return v,sorted(set(cleared+extra))
        m._original.clean_run_env=env
        def launched(pid):r.update(actual_model_invocations=1,process_group_pid=pid);m.write_json(out,r)
        r['model']=m.run_one(e,donor,on_launch=launched);r['outputs']=validate_outputs(e)
        r['status']='PASS' if r['model']['model_completed'] and r['outputs']['passed'] else 'FAIL_PRESERVED'
        if arm=='ra37-omp2-probe':r['observer_log']=pin(probe_log)
    except Exception as exc:r['status']='FAIL_PRESERVED';r['error']=repr(exc)
    finally:
        m._original.clean_run_env=original_env
        try:validate_stage(root,stage_sha);r['after_pins_valid']=True
        except Exception as exc:r.update(status='FAIL_PRESERVED',after_pins_valid=False,pin_error=repr(exc))
        m.write_json(out,r)
    return r

def compare(root,stage_sha):
    s=validate_stage(root,stage_sha);done={}
    for arm in ARMS:
        p=root/arm/'execution.json';r=json.loads(p.read_text())
        if r['status']!='PASS' or not r['before_pins_valid'] or not r.get('after_pins_valid') or r['actual_model_invocations']!=1:raise ValueError('all four accepted arm runs required')
        done[arm]=r
        for field in ('history','checkpoint'):
            m.check_pin(r['outputs'][field]['file'])
    pairs=[]
    for left,right in [('ra37-omp1','ra37-omp2'),('ra37-omp2','ra37-omp2-probe')]:
        for field in ('history','checkpoint'):
            a=Path(done[left]['outputs'][field]['file']['path']);b=Path(done[right]['outputs'][field]['file']['path'])
            pairs.append({'pair':[left,right],'field':field,**base.compare_file(a,b)})
    # RA4 is compared to its previously accepted exact-configuration OMP1 control.
    old=ROOT/'build/udm-cu-current-omp-ra4-control-v1/cases/omp1'
    if hashlib.sha256(RA4_CONTROL.read_bytes()).hexdigest()!=RA4_CONTROL_SHA:raise ValueError('RA4 control adapter changed')
    ra4parent=parent_data('ra4')
    for field,glob in [('history','wrfout_d01_2000-01-24_12:00:00'),('checkpoint','wrfrst_d01_2000-01-24_15:00:00')]:
        new=Path(done['ra4-omp1']['outputs'][field]['file']['path']);prior=old/glob
        if not prior.is_file():raise ValueError('missing historical RA4 comparison file: '+str(prior))
        # Verify original RA4 parent and same namelist science controls.
        m.check_pin(done['ra4-omp1']['outputs'][field]['file'])
        pairs.append({'pair':['ra4-omp1','accepted-old-ra4-omp1'],'field':field,**base.compare_file(new,prior)})
    result={'status':'PASS' if all(p['passed'] for p in pairs) else 'FAIL_PRESERVED','stage':pin(root/'stage.json'),'runner':pin(Path(__file__)),'pairs':pairs}
    m.collision(root/'comparison.json');m.write_json(root/'comparison.json',result);return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('mode',choices=('preflight','prepare','run','compare'));ap.add_argument('--root',type=Path,required=True);ap.add_argument('--stage-sha');ap.add_argument('--arm',choices=ARMS);ap.add_argument('--execute',action='store_true');a=ap.parse_args()
    if a.mode=='preflight':r={'status':'READY_NOT_STAGED','build':integrity.verify_build(),'donors':integrity.verify_donor_inputs(),'model_invocations':0}
    elif a.mode=='prepare':r=prepare(a.root)
    elif a.mode=='run':r=run(a.root,a.stage_sha,a.arm,a.execute)
    else:r=compare(a.root,a.stage_sha)
    print(json.dumps({'status':r['status'],'actual_model_invocations':r.get('actual_model_invocations',0)},indent=2));return 0 if r['status'].startswith(('PASS','READY','STAGED')) else 1
if __name__=='__main__':raise SystemExit(main())
