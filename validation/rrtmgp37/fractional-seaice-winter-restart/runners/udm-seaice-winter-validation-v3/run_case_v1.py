#!/usr/bin/env python3
"""One independent root-reviewed24h arm; preflight default, --execute explicit."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
from types import SimpleNamespace
HERE=Path(__file__).resolve().parent;COMMON=HERE/'posthoc_runtime_helper_v1.py';COMMON_SHA='4401937b69c1bcf3cbf48a0856238dd84c9dee3ebbf3c8a807ec53f979493ae3'
if hashlib.sha256(COMMON.read_bytes()).hexdigest()!=COMMON_SHA:raise ValueError('common helper changed before import')
s=importlib.util.spec_from_file_location('seaice_validator',COMMON);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
if m.digest(COMMON)!=COMMON_SHA:raise ValueError('common helper changed after import')


def invariants(stage,sha):
    sp=m.require_hash(stage,sha);r=json.loads(Path(stage).read_text())
    if r['status']!='STAGED_NOT_RUN' or r['model_invocations']!=0:raise ValueError('not unrun arm stage')
    m.check_pin(r['runner']);m.check_pin(r['common_helper']);b=m.build_integrity(r['build_receipt'])
    if r['common_helper']!=m.pin(COMMON):raise ValueError('common helper differs from staged helper')
    e=r['case']
    if e['arm'] not in ('ra4','ra37') or m.snapshot_case(e)!=e['snapshot'] or m.historical_arm(e['arm'])!=r['historical_arm']:raise ValueError('case inputs or original bindings changed')
    m.check_pin(r['history_reference']);m.check_pin(r['runtime_manifest'])
    return r,sp,SimpleNamespace(mpiexec=m.MPIEXEC,ld_library_path=b['ld_library_path'],timeout=m.TIMEOUT)


def outputs(r):
    e=r['case'];case=Path(e['case_path']);files=sorted(case.glob('wrfout_d01_*'))
    if len(files)!=1:raise ValueError('expected one exact original25-frame history file')
    history=m.validate_dataset(files[0],m.TIMES,e['radiation'])
    if history['variable_count']!=e['expected_variable_count'] or history['numeric_variable_count']!=e['expected_numeric_count']:history['passed']=False
    restartfiles=sorted(case.glob('wrfrst_d01_*'))
    if [p.name for p in restartfiles]!=['wrfrst_d01_'+t for t in m.RESTART_TIMES]:raise ValueError('missing/extra own12h/24h checkpoint')
    checkpoints=[]
    for p,t in zip(restartfiles,m.RESTART_TIMES):
        c=m.validate_dataset(p,[t],e['radiation']);c['repaired_diagnostics']=m.checkpoint_diagnostics(p);c['passed']=c['passed'] and c['repaired_diagnostics']['passed'];checkpoints.append(c)
    preservation=m.compare_datasets(files[0],Path(r['history_reference']['path']))
    return {'history':history,'own_checkpoints':checkpoints,'history_preservation':preservation,'passed':history['passed'] and all(x['passed'] for x in checkpoints) and preservation['passed']}


def run(args):
    root=args.stage_receipt.parent;out=root/'execution-receipt-v1.json';m.collision(out)
    r,sp,runargs=invariants(args.stage_receipt,args.stage_sha);m.unused_case(r['case'])
    if not args.execute:return {'status':'READY_MODEL_NOT_RUN','stage_receipt':sp,'model_invocations':0,'production7':m.build_integrity(r['build_receipt'])['production7']}
    result={'schema':'udm-seaice-winter-arm-execution-v1','status':'RUNNING','stage_receipt':sp,'runner':m.pin(Path(__file__)),'arm':r['case']['arm'],'actual_model_invocations':0,'model_launch_attempts':1,'before_pins_valid':True}
    with out.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    try:
        def launched(pid):
            result['actual_model_invocations']=1;result['process_group_pid']=pid;m.write_json(out,result)
        result['model']=m.run_one(r['case'],runargs,on_launch=launched);result['outputs']=outputs(r)
        result['status']='PASS_'+r['case']['arm'].upper()+'_24H' if result['model']['model_completed'] and result['outputs']['passed'] else 'FAIL_PRESERVED'
    except Exception as exc:result['status']='FAIL_PRESERVED';result['error']=f'{type(exc).__name__}: {exc}'
    finally:
        try:invariants(args.stage_receipt,args.stage_sha);m.check_pin(result['runner']);result['after_pins_valid']=True
        except Exception as exc:result['after_pins_valid']=False;result['pin_error']=str(exc);result['status']='FAIL_PRESERVED'
        m.write_json(out,result)
    return result


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--stage-receipt',type=Path,required=True);p.add_argument('--stage-sha',required=True);p.add_argument('--execute',action='store_true');args=p.parse_args()
    try:r=run(args)
    except FileExistsError as exc:print(json.dumps({'status':'OUTPUT_COLLISION','error':str(exc)}));return 2
    except Exception as exc:print(json.dumps({'status':'SETUP_FAILED','error':f'{type(exc).__name__}: {exc}'}));return 1
    print(json.dumps({'status':r['status'],'actual_model_invocations':r.get('actual_model_invocations',0)}));return 0 if r['status'].startswith(('READY_','PASS_')) else 1
if __name__=='__main__':raise SystemExit(main())
