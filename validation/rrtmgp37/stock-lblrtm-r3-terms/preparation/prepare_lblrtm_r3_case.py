import hashlib,json,re,shutil,subprocess,time
from pathlib import Path
R=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
D=R/'build/udm37-lblrtm-r3-term-trace-v1'
old=R/'build/udm37-lblrtm-held-state-paneltrace-cpl-od-run-v1'
new=R/'build/udm37-lblrtm-held-state-r3terms-cpl-od-run-v1'
assert not new.exists();new.mkdir()
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
bp=json.loads((D/'build-postflight.json').read_text());assert bp['actual_child_returncode']==0
exe=bp['executable'];p=json.loads((old/'plan.json').read_text())
p['executable']=exe;p['deck']['path']=str(new/'TAPE5')
scope='one R3-term instrumented GNU-double LBLRTM OD-only run; original coupling; ICNTNM=1; SAMPLE4; layer21 accounting'
p['authorization']['scope']=scope;p['runtime']['cwd']=str(new/'runs/od-v1')
p['purpose']='Add observational R3 source-term accounting to the reviewed PANEL trace; same full-continuum SAMPLE4 captured45layer inputs, all45 spectral identity required.'
p['scope']='Diagnostic instrumented build; not unchanged stock executable'
p['instrumentation']={'build_postflight_sha256':sha(D/'build-postflight.json'),'source_patch_sha256':sha(D/'instrumentation.patch'),'source_sha256':sha(D/'source/LBLRTM/src/oprop.f90'),'source_preflight_review_sha256':sha(R/'build/udm37-lblrtm-r3-term-preflight-review-v1/review.json'),'supplemental_source_review_sha256':sha(R/'build/udm37-lblrtm-r3-term-preflight-review-v1/review-v2.json'),'reference_status':'Original negative-OD FAILs unchanged','noninterference_required':'all45 spectra and panel headers exact; sole HTIME exception source-proved'}
shutil.copyfile(old/'TAPE5',new/'TAPE5');assert sha(new/'TAPE5')==p['deck']['sha256']
code=(old/'runner.py').read_text().replace('fba4575973146b95658366343d1fccb0332c159a5705558c61d2efff86751ac4',exe['sha256'])
oldscope=re.search(r'if auth.get\("scope"\) != "([^"]+)":',code).group(1);code=code.replace(oldscope,scope)
(new/'runner.py').write_text(code);(new/'plan.json').write_text(json.dumps(p,indent=2,sort_keys=True)+'\n')
cmd=['/usr/bin/python3','-I','-S',str(new/'runner.py'),'--prepare'];run=subprocess.run(cmd,capture_output=True,text=True)
with (new/'prepare-execution.json').open('x') as f:json.dump({'actual_child_returncode':run.returncode,'command':cmd,'solver_invocations':0},f,indent=2);f.write('\n')
(new/'prepare-stdout.log').write_text(run.stdout);(new/'prepare-stderr.log').write_text(run.stderr);assert run.returncode==0,run.stderr
prep=json.loads((new/'runs/od-v1/prepared.json').read_text());base=json.loads((old/'runs/od-v1/prepared.json').read_text());assert prep['inputs']==base['inputs'] and prep['input_count']==38
auth={'schema':'UDM_LBLRTM_SINGLE_RUN_AUTH_V1','authorized':True,'plan_sha256':sha(new/'plan.json'),'runner_sha256':sha(new/'runner.py'),'prepared_sha256':sha(new/'runs/od-v1/prepared.json'),'scope':scope,'max_invocations':1,'source_review_sha256':p['instrumentation']['source_preflight_review_sha256'],'supplemental_source_review_sha256':p['instrumentation']['supplemental_source_review_sha256'],'build_postflight_sha256':sha(D/'build-postflight.json'),'new_physics_acceptance_authorized':False,'created_epoch':time.time()}
(new/'root-run-authorization.json').write_text(json.dumps(auth,indent=2)+'\n')
(D/'case-prepared.json').write_text(json.dumps({'status':'ONE_R3_TERM_CASE_PREPARED_NOT_RUN','case':str(new),'same38staged_inputs':True,'same_TAPE5_TAPE3':True,'only_runtime_change':'diagnostic executable','baseline_stock_run':str(R/'build/udm37-lblrtm-held-state-continuum-od-run-v1/runs/od-v1'),'parent_PANEL_run':str(old/'runs/od-v1'),'source_kind':'instrumented not unchanged stock','solver_invocations':0,'plan_sha256':sha(new/'plan.json'),'runner_sha256':sha(new/'runner.py'),'root_authorization_sha256':sha(new/'root-run-authorization.json')},indent=2)+'\n')
print('prepared1 case,0 solves',exe['sha256'])
