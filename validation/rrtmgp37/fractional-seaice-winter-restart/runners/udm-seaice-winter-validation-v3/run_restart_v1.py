#!/usr/bin/env python3
"""Own222/225-variable restart preflight; root-reviewed --execute only."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;PREPARER=HERE/'prepare_restart_v1.py';PREPARER_SHA='c10df6afef3945c5464533b18e14c726b631f48d9431d7268735ffb0006f142a'
if hashlib.sha256(PREPARER.read_bytes()).hexdigest()!=PREPARER_SHA:raise ValueError('restart preparer changed before import')
s=importlib.util.spec_from_file_location('seaice_restart_preparer',PREPARER);prep=importlib.util.module_from_spec(s);s.loader.exec_module(prep);m=prep.m
if m.digest(PREPARER)!=PREPARER_SHA:raise ValueError('restart preparer changed after import')


def invariants(stage,sha):
    sp=m.require_hash(stage,sha);r=json.loads(Path(stage).read_text())
    if r['status']!='STAGED_NOT_RUN' or r['model_invocations']!=0:raise ValueError('not unrun own restart stage')
    m.check_pin(r['runner']);m.check_pin(r['case_runner'])
    if r['runner']!=m.pin(PREPARER):raise ValueError('restart preparer differs')
    parent,parentstage,cp,h=prep.parent_integrity(r['parent_run']);e=r['case']
    if e['arm']!=parent['arm'] or e['checkpoint']!=cp['file'] or e['expected_variable_count']!=parentstage['case']['expected_variable_count']:raise ValueError('wrong-source or cross-arm checkpoint/reference')
    m.check_pin(e['original_namelist'])
    if m.snapshot_case(e)!=e['snapshot'] or (Path(e['case_path'])/'namelist.input').read_text()!=m.restart_namelist(Path(e['original_namelist']['path']).read_text()):raise ValueError('restart static links/nml/bindings changed')
    ref=r['own_continuous_13h_reference'];m.check_pin(ref['path'])
    if ref['path']!=h['file'] or m.continuous_slice(Path(ref['path']['path']))!=ref:raise ValueError('own continuous reference changed')
    if not m.validate_dataset(Path(e['checkpoint']['path']),[m.RESTART_TIMES[0]],e['radiation'])['passed']:raise ValueError('own checkpoint strict numeric validation fails')
    _,_,runargs=prep.case_runner.invariants(Path(parent['stage_receipt']['path']),parent['stage_receipt']['sha256'])
    return r,sp,runargs


def run(args):
    out=args.stage_receipt.parent/'restart-execution-v1.json';m.collision(out)
    r,sp,runargs=invariants(args.stage_receipt,args.stage_sha);e=r['case'];m.unused_case(e,restart=True)
    if not args.execute:return {'status':'READY_RESTART_NOT_RUN','arm':e['arm'],'model_invocations':0}
    result={'schema':'udm-seaice-own-arm-restart-execution-v1','status':'RUNNING','arm':e['arm'],'stage_receipt':sp,'runner':m.pin(Path(__file__)),'actual_model_invocations':0,'model_launch_attempts':1,'before_pins_valid':True}
    with out.open('x') as f:f.write(json.dumps(result,indent=2)+'\n')
    try:
        def launched(pid):
            result['actual_model_invocations']=1;result['process_group_pid']=pid;m.write_json(out,result)
        result['model']=m.run_one(e,runargs,on_launch=launched);files=sorted(Path(e['case_path']).glob('wrfout_d01_*'))
        if len(files)!=1:raise ValueError('expected exactly one01Z history')
        result['strict_history']=m.validate_dataset(files[0],['2000-01-25_01:00:00'],e['radiation'])
        if result['strict_history']['variable_count']!=e['expected_variable_count'] or result['strict_history']['numeric_variable_count']!=e['expected_numeric_count']:result['strict_history']['passed']=False
        result['own_continuous_comparison']=m.compare_to_own_slice(files[0],r['own_continuous_13h_reference'])
        result['status']='PASS_'+e['arm'].upper()+'_OWN_RESTART13H' if result['model']['model_completed'] and result['strict_history']['passed'] and result['own_continuous_comparison']['passed'] else 'FAIL_PRESERVED'
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
