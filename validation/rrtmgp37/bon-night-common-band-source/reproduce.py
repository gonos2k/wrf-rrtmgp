#!/usr/bin/env python3
"""Opt-in isolated rerun of the saved Python analysis (never an RTE call)."""
from __future__ import annotations
import argparse,gzip,hashlib,json,os,shutil,subprocess,sys,time,importlib.util
from pathlib import Path
sys.dont_write_bytecode=True
_spec=importlib.util.spec_from_file_location("bon_package_verify",Path(__file__).resolve().with_name("verify.py"))
_verify=importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_verify)
verify_tree=_verify.verify_tree

def sha(b): return hashlib.sha256(b).hexdigest()
def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--run',action='store_true',help='run the pinned NumPy/SciPy Python analysis once in an isolated output directory')
    ap.add_argument('--root',type=Path,default=Path(__file__).resolve().parent)
    ap.add_argument('--output-dir',type=Path,help='new directory for staged inputs, rewritten plan, logs and result (required with --run; must not exist)')
    args=ap.parse_args(); root=args.root.resolve(); verify_tree(root)
    if not args.run:
        if args.output_dir: raise SystemExit('--output-dir is only valid with --run')
        print('Verified. No analysis executed. Pass --run and --output-dir to create a new isolated output directory and run once.')
        return 0
    if not args.output_dir: raise SystemExit('--run requires --output-dir')
    output=args.output_dir.absolute()
    output.mkdir(parents=True,exist_ok=False)
    manifest=json.loads((root/'manifest.json').read_text()); origins=manifest['origins']
    proc=None
    try:
        tmp=output/'stage'; tmp.mkdir()
        plan=json.loads((root/'analysis/plan.json').read_text())
        for key,rec in origins.items():
            data=(root/rec['package_path']).read_bytes()
            if rec['encoding']=='gzip': data=gzip.decompress(data)
            target=tmp/('payload-'+key+'.dat')
            with target.open('xb') as f: f.write(data); f.flush(); os.fsync(f.fileno())
            if sha(data)!=rec['origin_sha256']: raise ValueError('pin mismatch while staging '+key)
            if key in plan['pins']: plan['pins'][key]['path']=str(target)
        helper_targets={
          'legacy_helper':tmp/'legacy_lw_replay.py',
          'angular_helper':tmp/'angular_reference.py',
          'analysis':tmp/'analyze.py'}
        for key,target in helper_targets.items():
            src=root/origins[key]['package_path']; shutil.copyfile(src,target)
            plan['pins'][key]['path']=str(target)
        # The four large artifacts and the pinned JSON context assets retain their
        # original SHA/size fields; only absolute paths are redirected to this temp.
        plan_path=tmp/'plan.json'
        with plan_path.open('x') as f: f.write(json.dumps(plan,indent=2,sort_keys=True)+'\n'); f.flush(); os.fsync(f.fileno())
        launch={'status':'LAUNCHED','started_epoch':time.time(),'executable':sys.executable,'script':str(tmp/'analyze.py'),'pid':None}
        proc=subprocess.Popen([sys.executable,str(tmp/'analyze.py')],cwd=tmp,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
        launch['pid']=proc.pid
        with (output/'launch.json').open('x') as f: json.dump(launch,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
        stdout,stderr=proc.communicate(); rc=proc.returncode
        for name,contents in [('stdout.log',stdout),('stderr.log',stderr)]:
            with (output/name).open('x') as f: f.write(contents); f.flush(); os.fsync(f.fileno())
        result=tmp/'result.json'
        compare={'status':'NOT_COMPARED'}
        if rc==0 and result.is_file():
            archived=json.loads((root/'analysis/result.json').read_text()); reproduced=json.loads(result.read_text())
            def compare_values(a,b,path=''):
                errors=[]
                if isinstance(a,dict) and isinstance(b,dict):
                    if set(a)!=set(b): return [path+': key set differs']
                    for k in a:
                        if path=='' and k=='plan_sha256': continue
                        errors.extend(compare_values(a[k],b[k],path+'/'+k))
                elif isinstance(a,list) and isinstance(b,list):
                    if len(a)!=len(b): return [path+': list length differs']
                    for i,(x,y) in enumerate(zip(a,b)): errors.extend(compare_values(x,y,path+f'/{i}'))
                elif isinstance(a,(int,float)) and not isinstance(a,bool) and isinstance(b,(int,float)) and not isinstance(b,bool):
                    if not (math.isfinite(float(a)) and math.isfinite(float(b)) and abs(float(a)-float(b))<=1e-9): errors.append(path+': numeric difference exceeds abs tolerance 1e-9')
                elif a!=b: errors.append(path+': value differs')
                return errors
            import math
            errs=compare_values(archived,reproduced)
            compare={'status':'PASS_SUBSTANTIVE_FIELDS_WITHIN_ABS_1E-9' if not errs else 'FAIL_SUBSTANTIVE_COMPARISON','absolute_tolerance':1e-9,'error_count':len(errs),'first_errors':errs[:20]}
            shutil.copyfile(result,output/'result.json')
        status='PASS_OPT_IN_ANALYSIS_REPRODUCED' if rc==0 and result.is_file() and compare['status'].startswith('PASS') else 'FAIL_PRESERVED'
        receipt={'status':status,'started_epoch':launch['started_epoch'],'ended_epoch':time.time(),'pid':proc.pid,'returncode':rc,'result_sha256':sha(result.read_bytes()) if result.is_file() else None,'substantive_comparison':compare,'scope':'Python-only band transport; no compiled RTE/WRF/forecast call.'}
        with (output/'execution-receipt.json').open('x') as f: json.dump(receipt,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
        print(json.dumps(receipt,sort_keys=True))
        return 0 if status.startswith('PASS') else 1
    except Exception as exc:
        # Preserve the exclusive output directory and failure details for review.
        fail={'status':'FAIL_PRESERVED','error':type(exc).__name__+': '+str(exc),
              'pid':proc.pid if proc is not None else None,
              'returncode':proc.poll() if proc is not None else None,
              'scope':'No automatic retry; null PID/returncode means not launched or not observed complete.'}
        if not (output/'execution-receipt.json').exists():
            with (output/'execution-receipt.json').open('x') as f: json.dump(fail,f,indent=2,sort_keys=True); f.write('\n'); f.flush(); os.fsync(f.fileno())
        raise
if __name__=='__main__': raise SystemExit(main())
