#!/usr/bin/env python3
"""Own-arm12→13h preparation only after that arm's full24h/checkpoint PASS."""
import argparse,hashlib,importlib.util,json
from pathlib import Path
HERE=Path(__file__).resolve().parent;CASE_RUNNER=HERE/'run_case_v1.py';CASE_RUNNER_SHA='5417f705344613301760e2fc6cf9e593f2caba9067563dc48225de550332b083'
if hashlib.sha256(CASE_RUNNER.read_bytes()).hexdigest()!=CASE_RUNNER_SHA:raise ValueError('arm runner changed before import')
s=importlib.util.spec_from_file_location('seaice_arm_runner',CASE_RUNNER);case_runner=importlib.util.module_from_spec(s);s.loader.exec_module(case_runner);m=case_runner.m
if m.digest(CASE_RUNNER)!=CASE_RUNNER_SHA:raise ValueError('arm runner changed after import')


def parent_integrity(parent_pin):
    m.check_pin(parent_pin);r=json.loads(Path(parent_pin['path']).read_text());arm=r['arm']
    if arm not in ('ra4','ra37') or r['status']!='PASS_'+arm.upper()+'_24H' or r['actual_model_invocations']!=1 or not r['before_pins_valid'] or not r['after_pins_valid']:raise ValueError('requires own terminal24h/checkpoint PASS')
    m.check_pin(r['runner']);stage,sp,args=case_runner.invariants(Path(r['stage_receipt']['path']),r['stage_receipt']['sha256'])
    history=r['outputs']['history'];m.check_pin(history['file'])
    if not history['passed'] or history['variable_count']!=stage['case']['expected_variable_count']:raise ValueError('wrong own continuous history')
    cp=next(c for c in r['outputs']['own_checkpoints'] if c['ordered_times']==[m.RESTART_TIMES[0]])
    m.check_pin(cp['file'])
    if not cp['passed'] or not m.checkpoint_diagnostics(Path(cp['file']['path']))['passed']:raise ValueError('own12h checkpoint cannot restart')
    return r,stage,cp,history


def prepare(args):
    root=args.stage_root.absolute();m.collision(root)
    pp=m.require_hash(args.parent_run,args.parent_sha);parent,stage,cp,history=parent_integrity(pp)
    reference=m.continuous_slice(Path(history['file']['path']))
    if reference['zero_based_time_index']!=13 or len(reference['all_raw_variable_slice_pins'])!=stage['case']['expected_variable_count']:raise ValueError('wrong own222/225 continuous13h slice')
    if not args.prepare_go:return {'status':'READY_RESTART_INPUTS_NOT_STAGED','arm':parent['arm'],'model_invocations':0}
    root.parent.mkdir(parents=True,exist_ok=True);root.mkdir(exist_ok=False)
    try:
        case=root/'case';case.mkdir();entry=stage['case'];names=list(entry['link_names'])
        for name in names:(case/name).symlink_to((Path(entry['case_path'])/name).resolve(strict=True))
        checkpoint=Path(cp['file']['path']);(case/checkpoint.name).symlink_to(checkpoint);names.append(checkpoint.name)
        original=Path(entry['case_path'])/'namelist.input';(case/'namelist.input').write_text(m.restart_namelist(original.read_text()))
        e={'arm':parent['arm'],'case_path':str(case),'link_names':sorted(names),'expected_variable_count':entry['expected_variable_count'],'expected_numeric_count':entry['expected_numeric_count'],'radiation':entry['radiation'],'checkpoint':cp['file'],'original_namelist':m.pin(original)};e['snapshot']=m.snapshot_case(e)
        result={'schema':'udm-seaice-own-arm-restart-stage-v1','status':'STAGED_NOT_RUN','model_invocations':0,'created_utc':m.utc_now(),'runner':m.pin(Path(__file__)),'case_runner':m.pin(CASE_RUNNER),'parent_run':pp,'build_receipt':stage['build_receipt'],'case':e,'own_continuous_13h_reference':reference,'run_control_changes_only':['run_hours24→1','start_day24→25','start_hour12→00','end_hour12→01','restart.FALSE.→.TRUE.'],'expected_history_times':['2000-01-25_01:00:00'],'expected_global_difference_only':{'START_DATE':['2000-01-24_12:00:00','2000-01-25_00:00:00']}}
        parent_integrity(pp)
        if m.snapshot_case(e)!=e['snapshot'] or m.continuous_slice(Path(history['file']['path']))!=reference:raise ValueError('restart inputs changed while staging')
        m.write_json(root/'restart-stage-v1.json',result);return result
    except Exception as exc:m.write_json(root/'restart-stage-failure-v1.json',{'status':'FAIL_PRESERVED','error':f'{type(exc).__name__}: {exc}','model_invocations':0});raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--parent-run',type=Path,required=True);p.add_argument('--parent-sha',required=True);p.add_argument('--stage-root',type=Path,required=True);p.add_argument('--prepare-go',action='store_true');args=p.parse_args()
    try:r=prepare(args)
    except FileExistsError as exc:print(json.dumps({'status':'OUTPUT_COLLISION','error':str(exc)}));return 2
    except Exception as exc:print(json.dumps({'status':'SETUP_FAILED','error':f'{type(exc).__name__}: {exc}'}));return 1
    print(json.dumps({'status':r['status'],'model_invocations':0}));return 0
if __name__=='__main__':raise SystemExit(main())
