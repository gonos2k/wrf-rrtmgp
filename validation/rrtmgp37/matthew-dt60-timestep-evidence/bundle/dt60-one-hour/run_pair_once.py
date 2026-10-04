#!/usr/bin/env python3
"""Hash-gated two-arm launcher. Requires a separate root authorization file."""
from __future__ import annotations
import datetime as dt, hashlib, json, os, signal, subprocess, sys
from pathlib import Path

ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=ROOT/'build/udm37-matthew-dt60-pair-v1'
PLAN=HERE/'plan.json'; MANIFEST=HERE/'manifest.json'; AUTH=HERE/'root-authorization.json'
RECEIPT=HERE/'execution-receipt.json'; LOCK=HERE/'.one-use.lock'
SELF=HERE/'run_pair_once.py'; VALIDATOR=HERE/'validate_case.py'
ANALYZER=HERE/'analyze_native_ww.py'; COMPARATOR=HERE/'compare_pair.py'; SELFTEST=HERE/'selftest.py'
FATAL=('fatal called','mpi_abort','error: fatal','rrtmgp_fatal','application called mpi_abort','dp_hpa_not_finite')

def sha(p:Path)->str:
    h=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''):h.update(b)
    return h.hexdigest()
def pin(p:Path)->dict:
    p=Path(p).resolve(strict=True);return {'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def utc()->str:return dt.datetime.now(dt.timezone.utc).isoformat()
def atomic(p:Path,o:dict):
    q=p.with_name(p.name+f'.tmp.{os.getpid()}')
    with q.open('x') as f:json.dump(o,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
    os.replace(q,p);fd=os.open(p.parent,os.O_DIRECTORY);os.fsync(fd);os.close(fd)
def check_file(path:Path,rec:dict,label:str):
    got=pin(path)
    if got['sha256']!=rec['sha256'] or got['size_bytes']!=rec['size_bytes']:raise RuntimeError(label+' hash/size changed')
    return got

def snapshot(plan,manifest):
    out={'plan':pin(PLAN),'manifest':pin(MANIFEST),'runner':pin(SELF),'validator':pin(VALIDATOR),
         'analyzer':pin(ANALYZER),'comparator':pin(COMPARATOR),'selftest':pin(SELFTEST),
         'executable':check_file(Path(plan['executable']['path']),plan['executable'],'source executable'),
         'table':check_file(Path(plan['frozen_table']['path']),plan['frozen_table'],'frozen table'),
         'launcher':check_file(Path(plan['mpi_launcher']['path']),plan['mpi_launcher'],'MPI launcher'),
         'inputs':{},'coefficients':{},'libraries':{},'cases':{}}
    for name,x in plan['pairing']['common_inputs'].items():
        # Verify both staged copies independently against the shared pin.
        for arm in ('ra4','ra37'):
            p=Path(plan['arms'][arm]['case_dir'])/name
            check_file(p,x,f'{arm}/{name}')
        out['inputs'][name]=x
    for x in plan['coefficients']:
        out['coefficients'][x['name']]=check_file(Path(x['path']),x,x['name'])
    for x in plan['runtime_libraries']:
        out['libraries'][x['soname']]=check_file(Path(x['path']),x,x['soname'])
    for arm in ('ra4','ra37'):
        case=Path(plan['arms'][arm]['case_dir']); recs=manifest['cases'][arm]; found={}
        for name,expected in recs.items():
            p=case/name
            if expected['link_text'] is not None and (not p.is_symlink() or os.readlink(p)!=expected['link_text']):
                raise RuntimeError(f'{arm}/{name} symlink text changed')
            got=pin(p)
            if (got['sha256'],got['size_bytes'])!=(expected['resolved']['sha256'],expected['resolved']['size_bytes']):
                raise RuntimeError(f'{arm}/{name} staged file changed')
            found[name]={'link_text':os.readlink(p) if p.is_symlink() else None,'resolved':got}
        out['cases'][arm]=found
    # The root-pinned native donor and failed forensic inputs are provenance, not runtime inputs.
    out['donor_execution']=check_file(Path(plan['donor']['execution']['path']),plan['donor']['execution'],'donor receipt')
    out['donor_manifest']=check_file(Path(plan['donor']['manifest']['path']),plan['donor']['manifest'],'donor manifest')
    return out

def scan(case:Path):
    rows=[]; fatal=[]; success=[]
    logs=[case/f'rsl.{kind}.{rank:04d}' for kind in ('error','out') for rank in range(4)]+[case/'wrf.stdout.log']
    for p in logs:
        if not p.is_file():rows.append({'name':p.name,'missing':True});continue
        lines=p.read_text(errors='replace').splitlines(); fl=[]; sl=[]
        for n,line in enumerate(lines,1):
            low=line.lower()
            if any(t in low for t in FATAL):fl.append({'line':n,'text':line[:1200]})
            if 'wrf: success complete wrf' in low:sl.append(n)
        fatal.extend({'file':p.name,**x} for x in fl);success.extend({'file':p.name,'line':n} for n in sl)
        rows.append({'name':p.name,'sha256':sha(p),'size_bytes':p.stat().st_size,'fatal':fl,'success_lines':sl,'last_lines':lines[-8:]})
    return {'expected_logs':9,'present_logs':sum(not r.get('missing',False) for r in rows),'rows':rows,
            'fatal_count':len(fatal),'fatal':fatal,'success_markers':success}

def main():
    if '--execute' not in sys.argv:
        print('PREPARED_ONLY: no model launched; execution requires a root authorization bound to plan, manifest, and runner.');return 0
    if not AUTH.is_file():raise SystemExit('root authorization absent')
    if RECEIPT.exists() or LOCK.exists():raise SystemExit('one-use receipt/lock exists; refusing retry')
    plan=json.loads(PLAN.read_text());manifest=json.loads(MANIFEST.read_text());auth=json.loads(AUTH.read_text())
    if plan['status']!='STAGED_NOT_AUTHORIZED_NOT_RUN' or plan['model_invocations']!=0:raise RuntimeError('stage is not untouched')
    expected_runner=plan['execution']['runner_sha256']; expected_validator=plan['execution']['validator_sha256']
    if expected_runner!=sha(SELF) or expected_validator!=sha(VALIDATOR):raise RuntimeError('runner/validator hash mismatch')
    if manifest['plan_sha256']!=sha(PLAN):raise RuntimeError('plan/manifest mismatch')
    if auth.get('status')!='AUTHORIZED' or auth.get('plan_sha256')!=sha(PLAN) or auth.get('manifest_sha256')!=sha(MANIFEST) or auth.get('runner_sha256')!=sha(SELF) or auth.get('validator_sha256')!=sha(VALIDATOR) or auth.get('max_model_invocations')!=2:
        raise RuntimeError('authorization does not pin exact two-arm stage')
    if any(any((Path(plan['arms'][a]['case_dir'])/g).glob(pat)) for a in ('ra4','ra37') for g,pat in [('', 'rsl.*'),('', 'wrfout_d01_*'),('', 'wrfrst_d01_*')]):
        raise RuntimeError('runtime outputs already exist; refusing invocation')
    with LOCK.open('x') as f:f.write(f'pid={os.getpid()}\ncreated={utc()}\n');f.flush();os.fsync(f.fileno())
    receipt={'schema':'matthew-dt60-pair-execution-v1','status':'PREFLIGHT','plan_sha256':sha(PLAN),'manifest_sha256':sha(MANIFEST),
             'runner_sha256':sha(SELF),'validator_sha256':sha(VALIDATOR),'authorization_sha256':sha(AUTH),
             'model_invocations':0,'forecast_invocations':0,'arms':[],'started_utc':utc()}
    try:
        receipt['preflight']=snapshot(plan,manifest);atomic(RECEIPT,receipt)
        for arm in ('ra4','ra37'):
            case=Path(plan['arms'][arm]['case_dir'])
            if any(case.glob('rsl.*')) or any(case.glob('wrfout_d01_*')) or any(case.glob('wrfrst_d01_*')):
                raise RuntimeError(f'{arm}: existing runtime outputs; refusing invocation')
            env=os.environ.copy()
            for k in list(env):
                if k.startswith(tuple(plan['environment']['strip_prefixes'])) or k in plan['environment']['strip_names']:env.pop(k,None)
            env['LD_LIBRARY_PATH']=':'.join(plan['ld_library_path']);env['MPICH_INTERFACE_HOSTNAME']='127.0.0.1'
            env['OMP_NUM_THREADS']='2';env['OMP_STACKSIZE']='512M'
            if arm=='ra37':env['WRF_RRTMGP_BATCH_SIZE']='32'
            cmd=[plan['mpi_launcher']['path'],'-launcher','fork','-iface','lo','-n','4',str(case/'wrf.exe')]
            row={'arm':arm,'command':cmd,'cwd':str(case),'launched_utc':None,'launcher_pid':None,'returncode':None,'timed_out':False}
            receipt['arms'].append(row);receipt['status']='RUNNING';atomic(RECEIPT,receipt)
            proc=None
            try:
                with (case/'wrf.stdout.log').open('xb') as out:
                    proc=subprocess.Popen(cmd,cwd=case,env=env,stdout=out,stderr=subprocess.STDOUT,start_new_session=True)
                    receipt['model_invocations']+=1;receipt['forecast_invocations']+=1
                    row['launcher_pid']=proc.pid;row['launched_utc']=utc();atomic(RECEIPT,receipt)
                    try:row['returncode']=proc.wait(timeout=3600)
                    except subprocess.TimeoutExpired:
                        row['timed_out']=True
                        try:os.killpg(proc.pid,signal.SIGTERM)
                        except ProcessLookupError:pass
                        try:row['returncode']=proc.wait(timeout=20)
                        except subprocess.TimeoutExpired:
                            try:os.killpg(proc.pid,signal.SIGKILL)
                            except ProcessLookupError:pass
                            row['returncode']=proc.wait()
            except BaseException as e:
                if proc is not None and proc.poll() is None:
                    try:os.killpg(proc.pid,signal.SIGTERM);proc.wait(timeout=20)
                    except Exception:
                        try:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
                        except Exception:pass
                row['launch_error']=f'{type(e).__name__}: {e}'
                if proc is not None and row['returncode'] is None and proc.poll() is not None:row['returncode']=proc.returncode
            row['ended_utc']=utc();receipt['status']='PROCESS_COMPLETE_PENDING_SCAN';atomic(RECEIPT,receipt)
            row['logs']=scan(case)
            good=(row['returncode']==0 and not row['timed_out'] and 'launch_error' not in row and row['logs']['present_logs']==9
                  and row['logs']['fatal_count']==0 and len(row['logs']['success_markers'])==4)
            if good:
                valfile=HERE/f'{arm}-validation.json'
                p=subprocess.run([sys.executable,'-B',str(VALIDATOR),'--case-dir',str(case),'--arm',arm,'--receipt',str(valfile)],
                                 cwd=HERE,env={**env,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=180)
                row['validator']={'returncode':p.returncode,'stdout':p.stdout[-2000:],'stderr':p.stderr[-2000:],
                                  'receipt':pin(valfile) if valfile.is_file() else None}
                good=p.returncode==0
                if good:
                    hist=next(case.glob('wrfout_d01_*'))
                    analysis=HERE/f'{arm}-native-ww-analysis.json'
                    ap=subprocess.run([sys.executable,'-B',str(ANALYZER),str(hist),'--output',str(analysis)],
                                      cwd=HERE,env={**env,'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=120)
                    analysis_result=json.loads(analysis.read_text()) if analysis.is_file() else {}
                    row['native_ww_analysis']={'returncode':ap.returncode,'status':analysis_result.get('status'),
                                               'stdout':ap.stdout[-2000:],'stderr':ap.stderr[-2000:],
                                               'receipt':pin(analysis) if analysis.is_file() else None}
                    good=ap.returncode==0 and analysis_result.get('status')=='ANALYZED_NO_ACCEPTANCE_THRESHOLD'
                    atomic(RECEIPT,receipt)
            if not good:
                row['status']='FAIL_PRESERVED';receipt['status']='FAIL_PRESERVED';atomic(RECEIPT,receipt)
                # The two arms are independent fresh forecasts. Preserve a failing RA4
                # record and continue to RA37 only while staged inputs remain pinned.
                try:
                    after_arm=snapshot(plan,manifest)
                    if after_arm != receipt.get('preflight'):
                        receipt['postflight']=after_arm
                        receipt['inputs_assets_stable']=False
                        receipt['status']='FAIL_PRESERVED'
                        atomic(RECEIPT,receipt)
                        break
                except BaseException as e:
                    receipt.setdefault('errors',[]).append(f'post-arm immutable check failed: {type(e).__name__}: {e}')
                    receipt['status']='FAIL_PRESERVED';atomic(RECEIPT,receipt)
                    break
                continue
            row['status']='PASS_STRICT_ONE_HOUR_HISTORY';atomic(RECEIPT,receipt)
        receipt['postflight']=snapshot(plan,manifest)
        receipt['inputs_assets_stable']=receipt['postflight']==receipt['preflight']
        if not receipt['inputs_assets_stable']:
            receipt['status']='FAIL_PRESERVED';receipt['postflight_error']='immutable input/runtime snapshot changed'
        elif len(receipt['arms'])==2 and all(x.get('status')=='PASS_STRICT_ONE_HOUR_HISTORY' for x in receipt['arms']):
            cmpout=HERE/'paired-descriptive-differences.json'
            cp=subprocess.run([sys.executable,'-B',str(COMPARATOR),'--ra4',str(Path(plan['arms']['ra4']['case_dir'])/'wrfout_d01_2016-10-06_00:00:00'),
                               '--ra37',str(Path(plan['arms']['ra37']['case_dir'])/'wrfout_d01_2016-10-06_00:00:00'),'--output',str(cmpout)],
                              cwd=HERE,env={'PYTHONDONTWRITEBYTECODE':'1'},capture_output=True,text=True,timeout=180)
            receipt['paired_comparison']={'returncode':cp.returncode,'stdout':cp.stdout[-2000:],'stderr':cp.stderr[-2000:],
                                          'receipt':pin(cmpout) if cmpout.is_file() else None}
            receipt['status']='PASS_TWO_ARM_DT60_DIAGNOSTIC' if cp.returncode==0 else 'FAIL_PRESERVED'
        else:receipt['status']='FAIL_PRESERVED'
    except BaseException as e:
        receipt.setdefault('errors',[]).append(f'{type(e).__name__}: {e}')
        receipt['status']='FAIL_PRESERVED'
        try:receipt['postflight']=snapshot(plan,manifest);receipt['inputs_assets_stable']=receipt.get('postflight')==receipt.get('preflight')
        except BaseException as x:receipt['postflight_error']=f'{type(x).__name__}: {x}'
    receipt['finished_utc']=utc();atomic(RECEIPT,receipt)
    print(json.dumps({'status':receipt['status'],'model_invocations':receipt['model_invocations'],'receipt':str(RECEIPT)},indent=2))
    return 0 if receipt['status']=='PASS_TWO_ARM_DT60_DIAGNOSTIC' else 1
if __name__=='__main__':raise SystemExit(main())
