#!/usr/bin/env python3
"""Current CU daytime MPI4/OMP comparison; immutable winter helpers, explicit GO."""
import argparse, hashlib, importlib.util, json, os, re
from pathlib import Path
import numpy as np
from netCDF4 import Dataset, default_fillvals

HERE=Path(__file__).resolve().parent; ROOT=HERE.parents[1]
OLD=ROOT/'build/udm-seaice-winter-validation-v3/run_case_v1.py'
OLD_SHA='5417f705344613301760e2fc6cf9e593f2caba9067563dc48225de550332b083'
PLAN=ROOT/'build/udm-cu-current-omp-plan-v2/plan.json'
PLAN_SHA='323ef06209b5936ad9460d3b2b7fabd8eb3d2af893f376adb4c28038048c392c'
PARENT=ROOT/'build/udm-seaice-winter-validation-v3/ra37-24h-v1/execution-receipt-v1.json'
PARENT_SHA='150313d70a2a9e3274aed66703e671a22b40338cb5439bb32fb4770324eeabef'
PROBE=ROOT/'build/udm-cmake-openmp-full/runtime-preflight-v3/libgomp_probe.so'
PROBE_SHA='b7b691789827e149c9f3f2b0230b594d5e5ae942d669b1def11c7d99b703aedf'
TIMES=['2000-01-24_'+str(h)+':00:00' for h in (12,13,14,15)]
ARMS={'omp1':1,'omp2':2,'omp2-probe':2}
def load(path,sha,name):
    if hashlib.sha256(path.read_bytes()).hexdigest()!=sha: raise ValueError(name+' import pin changed')
    spec=importlib.util.spec_from_file_location(name,path); mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    if hashlib.sha256(path.read_bytes()).hexdigest()!=sha: raise ValueError(name+' changed during import')
    return mod
old=load(OLD,OLD_SHA,'pinned_winter_runner');m=old.m

def parent():
    m.require_hash(PLAN,PLAN_SHA);m.require_hash(PARENT,PARENT_SHA)
    r=json.loads(PARENT.read_text())
    if r['status']!='PASS_RA37_24H' or r['actual_model_invocations']!=1 or not r['before_pins_valid'] or not r['after_pins_valid']:raise ValueError('parent24h not accepted')
    m.check_pin(r['runner']);m.check_pin(r['outputs']['history']['file'])
    stage,sp,args=old.invariants(Path(r['stage_receipt']['path']),r['stage_receipt']['sha256'])
    if stage['case']['arm']!='ra37':raise ValueError('wrong arm')
    return r,stage,args

def nml(original):
    text=original
    for key,before,after in [('run_hours','24','3'),('end_day','25','24'),('end_hour','12','15'),('restart_interval','720','180')]:
        pattern=r'(?im)^(\s*'+key+r'\s*=\s*)'+before+r'(\s*,?\s*)$'
        text,count=re.subn(pattern,lambda x:x[1]+after+x[2],text)
        if count!=1:raise ValueError('base run-control differs: '+key)
    if re.search(r'(?im)^\s*numtiles\s*=',text):raise ValueError('unexpected base numtiles')
    text,count=re.subn(r'(?im)^(\s*max_dom\s*=\s*1\s*,?\s*)$',lambda x:x[0]+'\n numtiles = 2,',text)
    if count!=1:raise ValueError('expected single-domain base')
    return text

def prepare(root,go):
    m.collision(root);p,s,args=parent();m.require_hash(PROBE,PROBE_SHA)
    probe_libs=m.library_pins(PROBE,args.ld_library_path)
    if not go:return {'status':'READY_NOT_STAGED','model_invocations':0,'parent':m.pin(PARENT),'runner':m.pin(Path(__file__))}
    root.parent.mkdir(parents=True,exist_ok=True);root.mkdir()
    receipt={'status':'STAGED_NOT_RUN','runner':m.pin(Path(__file__)),'old_runner':m.pin(OLD),'plan':m.pin(PLAN),'parent':m.pin(PARENT),'probe':m.pin(PROBE),'probe_libraries':probe_libs,'arms':{},'model_invocations':0}
    try:
        original=Path(s['case']['case_path'])/'namelist.input'
        for name,threads in ARMS.items():
            case=root/name;case.mkdir()
            for item in s['case']['link_names']:(case/item).symlink_to((Path(s['case']['case_path'])/item).resolve(strict=True))
            (case/'namelist.input').write_text(nml(original.read_text()))
            e={**s['case'],'case_path':str(case),'threads':threads,'original_namelist':m.pin(original)}
            e['snapshot']=m.snapshot_case(e);receipt['arms'][name]=e
        if len({v['snapshot']['namelist']['sha256'] for v in receipt['arms'].values()})!=1:raise ValueError('namelist mismatch')
        parent();m.write_json(root/'stage.json',receipt)
    except Exception as exc:m.write_json(root/'stage-failure.json',{'status':'FAIL_PRESERVED','error':repr(exc),'model_invocations':0});raise
    return receipt

def invariants(root,sha,arm):
    m.require_hash(root/'stage.json',sha);r=json.loads((root/'stage.json').read_text());p,s,args=parent()
    if r['status']!='STAGED_NOT_RUN' or r['model_invocations']!=0:raise ValueError('not unrun matrix stage')
    for key in ('runner','old_runner','plan','parent','probe'):m.check_pin(r[key])
    if r['runner']!=m.pin(Path(__file__)) or r['probe']!=m.pin(PROBE) or m.library_pins(PROBE,args.ld_library_path)!=r['probe_libraries']:raise ValueError('runner or observer dependencies changed')
    e=r['arms'][arm]
    m.check_pin(e['original_namelist'])
    if e['threads']!=ARMS[arm] or m.snapshot_case(e)!=e['snapshot'] or (Path(e['case_path'])/'namelist.input').read_text()!=nml(Path(e['original_namelist']['path']).read_text()):raise ValueError('case changed')
    return r,e,args

def default_fills(path):
    hits={}
    with Dataset(path) as ds:
        ds.set_auto_maskandscale(False)
        for name,v in ds.variables.items():
            dtype=np.dtype(v.dtype)
            if dtype.kind not in 'iuf':continue
            key=dtype.kind+str(dtype.itemsize)
            if key in default_fillvals:
                count=int(np.count_nonzero(np.asarray(v[:])==np.asarray(default_fillvals[key],dtype=dtype)))
                if count:hits[name]=count
    return {'hits':hits,'passed':not hits}

def outputs(e):
    case=Path(e['case_path']);histories=sorted(case.glob('wrfout_d01_*'));checkpoints=sorted(case.glob('wrfrst_d01_*'))
    if [p.name for p in histories]!=['wrfout_d01_'+TIMES[0]] or [p.name for p in checkpoints]!=['wrfrst_d01_'+TIMES[-1]]:raise ValueError('wrong output set')
    h=m.validate_dataset(histories[0],TIMES,37);c=m.validate_dataset(checkpoints[0],[TIMES[-1]],37)
    h['default_fill_check']=default_fills(histories[0]);c['default_fill_check']=default_fills(checkpoints[0]);c['surface']=m.checkpoint_diagnostics(checkpoints[0])
    with Dataset(histories[0]) as ds:
        h['icloud_cu']=int(ds.getncattr('ICLOUD_CU'));h['sw_positive_cells']=[int(np.count_nonzero(ds['SWDOWN'][i]>0)) for i in range(4)]
    with Dataset(checkpoints[0]) as ds:
        ds.set_auto_maskandscale(False);c['cu_positive_cells']={name:int(np.count_nonzero(ds[name][:]>0)) for name in ('QC_CU','QI_CU')}
    good=(h['passed'] and c['passed'] and h['variable_count']==225 and h['numeric_variable_count']==224 and c['numeric_variable_count']==663 and h['icloud_cu']==2 and all(h['sw_positive_cells'][1:]) and all(c['cu_positive_cells'].values()) and c['surface']['passed'] and h['default_fill_check']['passed'] and c['default_fill_check']['passed'])
    return {'history':h,'checkpoint':c,'passed':bool(good)}

def run(root,sha,arm,execute):
    out=root/arm/'execution.json';m.collision(out);stage,e,args=invariants(root,sha,arm);m.unused_case(e)
    probe_log=Path(e['case_path'])/'gomp-workers.log';m.collision(probe_log)
    if not execute:return {'status':'READY_NOT_RUN','actual_model_invocations':0}
    r={'status':'RUNNING','runner':m.pin(Path(__file__)),'stage':m.pin(root/'stage.json'),'arm':arm,'actual_model_invocations':0,'before_pins_valid':True}
    with out.open('x') as f:f.write(json.dumps(r,indent=2)+'\n')
    original_env=m._original.clean_run_env
    def env_adapter(*a):
        env,cleared=original_env(*a)
        extra=[k for k in env if k.startswith(('WRF_UDM_','WRF_OMP_','GOMP_','KMP_'))]
        for k in extra:env.pop(k)
        env.update({'OMP_NUM_THREADS':str(ARMS[arm]),'OMP_DYNAMIC':'FALSE','OMP_MAX_ACTIVE_LEVELS':'1','OMP_NESTED':'FALSE','OMP_PROC_BIND':'FALSE','OPENBLAS_NUM_THREADS':'1'})
        if arm=='omp2-probe':env.update({'LD_PRELOAD':str(PROBE),'WRF_OMP_PROBE_LOG':str(probe_log)})
        r['runtime_env']={k:v for k,v in env.items() if k.startswith(('OMP_','WRF_','GOMP_','KMP_')) or k in ('LD_PRELOAD','LD_AUDIT','LD_LIBRARY_PATH','MPICH_INTERFACE_HOSTNAME','OPENBLAS_NUM_THREADS')}
        return env,sorted(set(cleared+extra))
    try:
        def launched(pid):r.update(actual_model_invocations=1,process_group_pid=pid);m.write_json(out,r)
        m._original.clean_run_env=env_adapter
        r['model']=m.run_one(e,args,on_launch=launched);r['outputs']=outputs(e)
        r['status']='PASS' if r['model']['model_completed'] and r['outputs']['passed'] else 'FAIL_PRESERVED'
        if arm=='omp2-probe':r['observer_log']=m.pin(probe_log)
    except Exception as exc:r['status']='FAIL_PRESERVED';r['error']=repr(exc)
    finally:
        m._original.clean_run_env=original_env
        try:invariants(root,sha,arm);m.check_pin(r['runner']);r['after_pins_valid']=True
        except Exception as exc:r['status']='FAIL_PRESERVED';r['after_pins_valid']=False;r['pin_error']=repr(exc)
        m.write_json(out,r)
    return r

def compare_file(a,b):
    ledger=[]
    with Dataset(a) as x,Dataset(b) as y:
        x.set_auto_maskandscale(False);y.set_auto_maskandscale(False);meta=m.metadata(x)==m.metadata(y)
        if set(x.variables)!=set(y.variables):raise ValueError('variable names differ')
        for n in x.variables:
            xa,ya=np.asarray(x[n][:]),np.asarray(y[n][:]);eq=xa.dtype==ya.dtype and xa.shape==ya.shape and xa.tobytes()==ya.tobytes()
            ledger.append({'name':n,'dtype':xa.dtype.str,'shape':list(xa.shape),'equal':eq,'left_sha':hashlib.sha256(xa.tobytes()).hexdigest(),'right_sha':hashlib.sha256(ya.tobytes()).hexdigest()})
    return {'left':m.pin(a),'right':m.pin(b),'metadata_equal':meta,'ledger':ledger,'whole_file_equal':m.digest(a)==m.digest(b),'passed':meta and all(z['equal'] for z in ledger)}

def compare(root,sha):
    results={}
    for arm in ARMS:
        invariants(root,sha,arm);p=root/arm/'execution.json';r=json.loads(p.read_text());m.check_pin(r['runner'])
        if r['status']!='PASS' or r['actual_model_invocations']!=1 or not r['before_pins_valid'] or not r['after_pins_valid']:raise ValueError('requires three accepted runs')
        for field in ('history','checkpoint'):m.check_pin(r['outputs'][field]['file'])
        results[arm]=r
    pairs=[]
    for left,right in [('omp2','omp2-probe'),('omp1','omp2')]:
        for field in ('history','checkpoint'):
            pairs.append({'pair':[left,right],'field':field,**compare_file(Path(results[left]['outputs'][field]['file']['path']),Path(results[right]['outputs'][field]['file']['path']))})
        if not all(x['passed'] for x in pairs):break
    r={'status':'PASS' if len(pairs)==4 and all(x['passed'] for x in pairs) else 'FAIL_PRESERVED','runner':m.pin(Path(__file__)),'stage':m.pin(root/'stage.json'),'executions':{arm:m.pin(root/arm/'execution.json') for arm in ARMS},'pairs':pairs}
    m.collision(root/'comparison.json');m.write_json(root/'comparison.json',r);return r

def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','run','compare'));p.add_argument('--root',type=Path,required=True);p.add_argument('--prepare-go',action='store_true');p.add_argument('--stage-sha');p.add_argument('--arm',choices=ARMS);p.add_argument('--execute',action='store_true');a=p.parse_args()
    if a.mode=='prepare':r=prepare(a.root.absolute(),a.prepare_go)
    elif a.mode=='run':r=run(a.root.absolute(),a.stage_sha,a.arm,a.execute)
    else:r=compare(a.root.absolute(),a.stage_sha)
    print(json.dumps({'status':r['status'],'actual_model_invocations':r.get('actual_model_invocations',0)}));return 0 if r['status'].startswith(('PASS','READY','STAGED')) else 1
if __name__=='__main__':raise SystemExit(main())
