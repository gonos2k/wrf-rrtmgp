#!/usr/bin/env python3
"""RA4 control for the observed RA37 thread-count difference; no source edits."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
import numpy as np
from netCDF4 import Dataset
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
RUNTIME=ROOT/'build/udm-cu-current-omp-runtime-v2/runtime.py';RUNTIME_SHA='126775590ee39f9c9170024f1b498ce2df86eee19654950b89e4ba92fdedb52a'
if hashlib.sha256(RUNTIME.read_bytes()).hexdigest()!=RUNTIME_SHA:raise ValueError('root runtime changed')
s=importlib.util.spec_from_file_location('pinned_cu_omp_runtime',RUNTIME);r=importlib.util.module_from_spec(s);s.loader.exec_module(r);m=r.m
r.PARENT=ROOT/'build/udm-seaice-winter-validation-v3/ra4-24h-v1/execution-receipt-v1.json'
r.PARENT_SHA='4073ad6101c06b0f81ac9e2dd4f2dd94b095dac642a79e1e1fab49133bfa8647'
r.ARMS={'omp1':1,'omp2':2}
def parent4():
    m.require_hash(r.PLAN,r.PLAN_SHA);m.require_hash(r.PARENT,r.PARENT_SHA);p=json.loads(r.PARENT.read_text())
    if p['status']!='PASS_RA4_24H' or p['actual_model_invocations']!=1 or not p['before_pins_valid'] or not p['after_pins_valid']:raise ValueError('requires accepted ownRA4')
    m.check_pin(p['runner']);m.check_pin(p['outputs']['history']['file'])
    stage,sp,args=r.old.invariants(Path(p['stage_receipt']['path']),p['stage_receipt']['sha256'])
    if stage['case']['radiation']!=4 or stage['case']['arm']!='ra4':raise ValueError('wrong controlphysics')
    return p,stage,args
r.parent=parent4
orig_invariants=r.invariants
def invariants4(root,sha,arm):
    stage,e,args=orig_invariants(root,sha,arm)
    if stage['control_adapter']!=m.pin(Path(__file__)):raise ValueError('control adapter differs')
    m.check_pin(stage['root_runtime']);return stage,e,args
r.invariants=invariants4
def output4(e):
    case=Path(e['case_path']);hs=sorted(case.glob('wrfout_d01_*'));cs=sorted(case.glob('wrfrst_d01_*'))
    if [p.name for p in hs]!=['wrfout_d01_'+r.TIMES[0]] or [p.name for p in cs]!=['wrfrst_d01_'+r.TIMES[-1]]:raise ValueError('wrong control outputs')
    h=m.validate_dataset(hs[0],r.TIMES,4);c=m.validate_dataset(cs[0],[r.TIMES[-1]],4)
    h['default_fill_check']=r.default_fills(hs[0]);c['default_fill_check']=r.default_fills(cs[0]);c['surface']=m.checkpoint_diagnostics(cs[0])
    with Dataset(hs[0]) as d:h['icloud_cu']=int(d.getncattr('ICLOUD_CU'));h['sw_positive_cells']=[int(np.count_nonzero(d['SWDOWN'][i]>0)) for i in range(4)]
    with Dataset(cs[0]) as d:
        d.set_auto_maskandscale(False);c['cu_positive_cells']={name:int(np.count_nonzero(d[name][:]>0)) for name in ('QC_CU','QI_CU')}
    good=(h['passed'] and c['passed'] and h['variable_count']==222 and h['numeric_variable_count']==221 and c['numeric_variable_count']==663 and h['icloud_cu']==2 and all(h['sw_positive_cells'][1:]) and all(c['cu_positive_cells'].values()) and c['surface']['passed'] and h['default_fill_check']['passed'] and c['default_fill_check']['passed'])
    return {'history':h,'checkpoint':c,'passed':bool(good)}
r.outputs=output4
def main():
    p=argparse.ArgumentParser();p.add_argument('mode',choices=('prepare','run','compare'));p.add_argument('--root',type=Path,required=True);p.add_argument('--prepare-go',action='store_true');p.add_argument('--stage-sha');p.add_argument('--arm',choices=r.ARMS);p.add_argument('--execute',action='store_true');a=p.parse_args();root=a.root.absolute()
    if a.mode=='prepare':
        result=r.prepare(root,a.prepare_go)
        if a.prepare_go:
            result['control_adapter']=m.pin(Path(__file__));result['root_runtime']=m.pin(RUNTIME);result['scope']='RA4 samebinary/inputs/MPI4/tiles2/daytime3h control of threadcount, not pristineforecastaccuracy';m.write_json(root/'stage.json',result)
    elif a.mode=='run':
        result=r.run(root,a.stage_sha,a.arm,a.execute)
        if a.execute:
            result['control_adapter']=m.pin(Path(__file__));m.write_json(root/a.arm/'execution.json',result)
    else:
        results={}
        for arm in r.ARMS:
            r.invariants(root,a.stage_sha,arm);entry=json.loads((root/arm/'execution.json').read_text())
            if entry['status']!='PASS' or entry['actual_model_invocations']!=1 or entry['control_adapter']!=m.pin(Path(__file__)):raise ValueError('requires terminalcontrolPASS')
            for field in ('history','checkpoint'):m.check_pin(entry['outputs'][field]['file'])
            results[arm]=entry
        pairs=[{'field':f,**r.compare_file(Path(results['omp1']['outputs'][f]['file']['path']),Path(results['omp2']['outputs'][f]['file']['path']))} for f in ('history','checkpoint')]
        result={'status':'PASS' if all(x['passed'] for x in pairs) else 'FAIL_PRESERVED','control_adapter':m.pin(Path(__file__)),'stage':m.pin(root/'stage.json'),'executions':{a:m.pin(root/a/'execution.json') for a in r.ARMS},'pairs':pairs}
        m.collision(root/'comparison.json');m.write_json(root/'comparison.json',result)
    print(json.dumps({'status':result['status'],'actual_model_invocations':result.get('actual_model_invocations',0)}));return 0 if result['status'].startswith(('PASS','READY','STAGED')) else 1
if __name__=='__main__':raise SystemExit(main())
