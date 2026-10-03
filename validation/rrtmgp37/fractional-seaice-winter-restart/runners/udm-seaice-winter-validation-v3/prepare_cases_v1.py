#!/usr/bin/env python3
"""Independent arm24h input preflight; stage only with --prepare-go."""
import argparse,hashlib,importlib.util,json,shutil
from pathlib import Path
HERE=Path(__file__).resolve().parent;COMMON=HERE/'posthoc_runtime_helper_v1.py';COMMON_SHA='4401937b69c1bcf3cbf48a0856238dd84c9dee3ebbf3c8a807ec53f979493ae3'
if hashlib.sha256(COMMON.read_bytes()).hexdigest()!=COMMON_SHA:raise ValueError('common helper changed before import')
s=importlib.util.spec_from_file_location('seaice_validator',COMMON);m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
if m.digest(COMMON)!=COMMON_SHA:raise ValueError('common helper changed after import')


def prepare(args):
    root=args.stage_root.absolute();m.collision(root)
    bp=m.require_hash(args.build_receipt,args.build_sha);b=m.build_integrity(bp)
    arm=m.historical_arm(args.arm);reference=m.check_pin(json.loads(Path(b['freeze_spec']['path']).read_text())['history_references'][args.arm])
    runtime_manifest=m.pin(m.HIST/'runtime-link-manifest.json')
    if not args.prepare_go:return {'status':'READY_CASE_INPUTS_NOT_STAGED','arm':args.arm,'build':bp,'model_invocations':0}
    root.parent.mkdir(parents=True,exist_ok=True);root.mkdir(exist_ok=False)
    try:
        case=root/'case';case.mkdir();src=Path(arm['source_case']);names=[]
        for linked in arm['runtime_links']:
            (case/linked['name']).symlink_to(linked['resolved_target']);names.append(linked['name'])
        for n in ('wrfinput_d01','wrfbdy_d01','radiation_iofields.txt','rrtmgp_data','frozen-ice-psd-moments.nc'):
            if n not in names:(case/n).symlink_to((src/n).resolve(strict=True));names.append(n)
        (case/'wrf.exe').symlink_to(b['binary']['path']);names.append('wrf.exe')
        shutil.copy2(src/'namelist.input',case/'namelist.input')
        if (case/'namelist.input').read_bytes()!=(src/'namelist.input').read_bytes():raise ValueError('not exact original24h namelist')
        e={'arm':args.arm,'case_path':str(case),'link_names':sorted(names),'expected_variable_count':222 if args.arm=='ra4' else 225,'expected_numeric_count':221 if args.arm=='ra4' else 224,'radiation':4 if args.arm=='ra4' else 37}
        e['snapshot']=m.snapshot_case(e)
        out={'schema':'udm-seaice-winter-arm-stage-v1','status':'STAGED_NOT_RUN','created_utc':m.utc_now(),'model_invocations':0,'runner':m.pin(Path(__file__)),'common_helper':m.pin(COMMON),'build_receipt':bp,'case':e,'history_reference':reference,'historical_arm':arm,'runtime_manifest':runtime_manifest,'runtime':{'ranks':4,'omp_threads':1,'master_stack_bytes':m.STACK_BYTES,'timeout_seconds':m.TIMEOUT,'ld_library_path':b['ld_library_path']}}
        m.build_integrity(bp)
        if m.historical_arm(args.arm)!=arm or m.snapshot_case(e)!=e['snapshot'] or m.check_pin(reference)!=reference or m.pin(m.HIST/'runtime-link-manifest.json')!=runtime_manifest:raise ValueError('case/source/asset changed while staging')
        m.write_json(root/'stage-receipt-v1.json',out);return out
    except Exception as exc:m.write_json(root/'stage-failure-v1.json',{'status':'STAGE_FAILED_PRESERVED','error':f'{type(exc).__name__}: {exc}','model_invocations':0});raise


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--arm',choices=('ra4','ra37'),required=True);p.add_argument('--build-receipt',type=Path,required=True);p.add_argument('--build-sha',required=True);p.add_argument('--stage-root',type=Path,required=True);p.add_argument('--prepare-go',action='store_true');args=p.parse_args()
    try:r=prepare(args)
    except FileExistsError as exc:print(json.dumps({'status':'OUTPUT_COLLISION','error':str(exc)}));return 2
    except Exception as exc:print(json.dumps({'status':'SETUP_FAILED','error':f'{type(exc).__name__}: {exc}'}));return 1
    print(json.dumps({'status':r['status'],'arm':args.arm,'model_invocations':0}));return 0
if __name__=='__main__':raise SystemExit(main())
