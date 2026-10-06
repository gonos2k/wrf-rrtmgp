#!/usr/bin/env python3
"""Verify retained transport evidence; never invoke a numerical executable."""
import argparse,gzip,hashlib,importlib.util,json,math,struct,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;REPO=P.parents[2]
HELD={'CLOUD_TAU','CU_CLOUD_TAU','CU_DI_USED','CU_RL_USED','DI_USED','DS_USED','FROZEN_TAU','GAS_COL_DRY','GAS_TAU','GAS_TAU_RAW','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','MASK','NATIVE_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU','RL_USED','TOTAL_TAU'}
RESPONSE={'UP','DN','HR','UPC','DNC','HRC'}
SOURCE={'SOURCE_LAYER','SOURCE_LEVEL','SOURCE_SURFACE','BAND_LIMITS_GPOINT','BAND_LIMITS_WAVENUMBER'}
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def need(ok,msg):
 if not ok:raise ValueError(msg)
def bits(x):return struct.pack('>d',float(x))
def same(a,b):return a['shape']==b['shape'] and len(a['values'])==len(b['values']) and all(bits(x)==bits(y) for x,y in zip(a['values'],b['values']))
def must_hold(reference,candidate,names):
 need(set(names)<=set(reference) and set(names)<=set(candidate),'required held fields absent')
 for n in names:need(same(reference[n],candidate[n]),'held field changed: '+n)
def policy_check(side,policy):
 need(set(side)==SOURCE|{'TRANSPORT_POLICY'}|({ 'LW_DIFFUSIVITY_ANGLE'} if policy==2 else {'GAUSS_ANGLE_COUNT'} if policy==3 else set()),'exact sidecar roster')
 want={'SOURCE_LAYER':(1,45,128),'SOURCE_LEVEL':(1,46,128),'SOURCE_SURFACE':(1,1,128),'BAND_LIMITS_GPOINT':(2,16,1),'BAND_LIMITS_WAVENUMBER':(2,16,1),'TRANSPORT_POLICY':(1,1,1)}
 for n,shape in want.items():need(side[n]['shape']==shape,'sidecar shape '+n)
 need(side['TRANSPORT_POLICY']['values']==[float(policy)],'policy label')
 if policy!=1:
  n,value=('LW_DIFFUSIVITY_ANGLE',1.66) if policy==2 else ('GAUSS_ANGLE_COUNT',4.)
  need(side[n]['shape']==(1,1,1) and side[n]['values']==[value],'policy-specific argument')
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def verify():
 manifest=json.loads((P/'artifact-manifest.json').read_text());files=manifest['files'];listed=[r['path'] for r in files];origin=json.loads((P/'original-payload-roster.json').read_text())
 expected={f'outputs/policy{i}.{kind}.gz' for i in (1,2,3) for kind in ('result','sidecar')}|{f'logs/policy{i}.log' for i in (1,2,3)}|{f'frozen/{n}' for n in ('reference_column.f90','reference_column.patch','adaptation.json','cli-negative-checks.json','run_once.py','build_once.py')}|{f'receipts/{n}' for n in ('plan.json','build-plan.json','authorization.json','build-authorization.json','preflight-v2.json','prelaunch-review-v2.json','terminal-review.json','build-receipt.json','build.log','execution.json')}|{f'audits/source-contract/{n}' for n in ('audit.json','precision-addendum.json','README.md','audit.py','precision_addendum.py')}|{f'audits/background-gases/{n}' for n in ('audit.json','README.md','audit.py')}|{'README.md','verify.py','test_verify.py','summary.json','original-payload-roster.json'}
 actual={x.relative_to(P).as_posix() for x in P.rglob('*') if x.is_file() and x!=P/'artifact-manifest.json'}
 need(len(listed)==len(set(listed)) and set(listed)==actual==expected and len(actual)==38,'closed38 payload roster')
 for r in files:
  f=P/r['path'];need(not f.is_symlink() and digest(f)==r['sha256'] and f.stat().st_size==r['size_bytes'],'payload hash '+r['path'])
 need(len(origin['files'])==33 and {r['path'] for r in origin['files']}==expected-{'README.md','verify.py','test_verify.py','summary.json','original-payload-roster.json'},'33 origin copies')
 for r in origin['files']:
  f=P/r['path'];need(digest(f)==r['retained_sha256'] and f.stat().st_size==r['retained_size_bytes'],'retained origin pin')
  data=f.read_bytes();data=gzip.decompress(data) if r['encoding']=='gzip' else data;need(r['encoding'] in ('gzip','verbatim') and hashlib.sha256(data).hexdigest()==r['original']['sha256'] and len(data)==r['original']['size_bytes'],'original decompressed pin')
 deps=origin['repository_dependencies'];ref={}
 for n,r in deps.items():
  f=REPO/r['repository_relative_path'];need(digest(f)==r['sha256'] and f.stat().st_size==r['size_bytes'],'repository dependency '+n);ref[n]=f
 def j(n):return json.loads((P/'receipts'/n).read_text())
 rec=j('execution.json');plan=j('plan.json');auth=j('authorization.json');build=j('build-receipt.json');ba=j('build-authorization.json');review=j('terminal-review.json')
 need(rec['status']=='PASS_THREE_FIXED_INPUT_TRANSPORT_POLICIES' and rec['actual_solver_invocations']==3 and rec['WRF_REAL_build_invocations']==0 and rec['before']==rec['after'],'archived three-call status/closure')
 need([c['policy'] for c in rec['calls']]==[1,2,3] and len({c['pid'] for c in rec['calls']})==3 and all(c['pid']>0 and c['returncode']==0 and not c['timed_out'] for c in rec['calls']),'three unique successful calls')
 need(auth['maximum_solver_calls']==3 and auth['retries']==0 and auth['plan_sha256']==digest(P/'receipts/plan.json') and auth['runner_sha256']==digest(P/'frozen/run_once.py'),'run authorization binding')
 need(rec['plan']['sha256']==auth['plan_sha256'] and rec['runner']['sha256']==auth['runner_sha256'] and rec['authorization']['sha256']==digest(P/'receipts/authorization.json'),'run receipt joins')
 need(build['status']=='PASS_PRIVATE_REFERENCE_COMPILE_LINK' and build['actual_compiler_calls']==1 and build['WRF_REAL_solver_calls']==0 and build['returncode']==0 and not build['timed_out'] and build['before']==build['after'] and build['extra_before']==build['extra_after'],'one private compile attestation')
 need(ba['maximum_compiler_calls']==1 and ba['maximum_solver_calls']==0 and ba['retries']==0 and ba['plan_sha256']==digest(P/'receipts/build-plan.json') and ba['runner_sha256']==digest(P/'frozen/build_once.py'),'build authorization binding')
 need(build['plan']['sha256']==ba['plan_sha256'] and build['runner']['sha256']==ba['runner_sha256'] and build['authorization']['sha256']==digest(P/'receipts/build-authorization.json') and plan['build_receipt']['sha256']==digest(P/'receipts/build-receipt.json'),'build receipt joins')
 need(review['status']=='PASS_SCOPED_THREE_CALLS' and review['execution_receipt']['sha256']==digest(P/'receipts/execution.json') and review['build_receipt_sha256']==digest(P/'receipts/build-receipt.json'),'terminal review provenance')
 need(review['execution_receipt']['pids']==[c['pid'] for c in rec['calls']] and review['execution_receipt']['returncodes']==[0,0,0],'terminal pid joins')
 bplan=j('build-plan.json');need(bplan['argv']==build['argv'] and bplan['source']['path'] in build['argv'] and bplan['source']['sha256']==digest(P/'frozen/reference_column.f90') and bplan['source_adaptation']['sha256']==digest(P/'frozen/adaptation.json'),'actual compile source/argv binding')
 adapted=json.loads((P/'frozen/adaptation.json').read_text());need(adapted['adapted_source']['sha256']==digest(P/'frozen/reference_column.f90')==plan['source']['sha256'] and adapted['base_source']['sha256']==digest(ref['current_reference_source']) and adapted['patch']['sha256']==digest(P/'frozen/reference_column.patch'),'source snapshot/patch/base pins')
 need(review['executable_sha256']==build['executable']['sha256']==plan['executable']['sha256'],'archived executable identity')
 parser=load('transport_trace',ref['trace_parser']).read_trace;reader=load('transport_export',ref['export_reader']).read_export
 baseline=gzip.decompress(ref['baseline'].read_bytes());inp=gzip.decompress(ref['input'].read_bytes());exp=gzip.decompress(ref['legacy_export'].read_bytes())
 need(hashlib.sha256(baseline).hexdigest()==plan['baseline_result']['sha256']==review['baseline_result_sha256'] and hashlib.sha256(inp).hexdigest()==plan['input']['sha256'] and hashlib.sha256(exp).hexdigest()==plan['legacy_export']['sha256']==review['legacy_export_sha256'],'reused baseline/input/export hashes')
 results={};sidecars={};metrics=[]
 with tempfile.TemporaryDirectory(prefix='retained-transport-') as td:
  t=Path(td);(t/'export').write_bytes(exp);legacy=reader(t/'export',expected_phase='LW',expected_context=plan['context']);f4=legacy['fields']['RESULT','DOWN_FLUX'].values[0]
  for i,call in zip((1,2,3),rec['calls']):
   data=gzip.decompress((P/f'outputs/policy{i}.result.gz').read_bytes());side=gzip.decompress((P/f'outputs/policy{i}.sidecar.gz').read_bytes());need(hashlib.sha256(data).hexdigest()==call['result']['sha256'] and hashlib.sha256(side).hexdigest()==call['transport_source']['sha256'] and digest(P/f'logs/policy{i}.log')==call['log']['sha256'],'call output/log pins')
   need(call['input']['sha256']==plan['input']['sha256'] and call['argv'][0]==plan['executable']['path'] and call['argv'][2]==plan['input']['path'] and call['argv'][3]==call['result']['path'] and call['argv'][4:]==['1','','',str(i)],'same input/executable and only transport policy command')
   (t/'result').write_bytes(data);(t/'side').write_bytes(side);meta,results[i]=parser(t/'result','result');sm,sidecars[i]=parser(t/'side','result');need(meta==sm=={'phase':'LW','ncol':1,'nlay':45},'45layer phase headers')
   need(set(results[i])==HELD|RESPONSE,'24 result sections');policy_check(sidecars[i],i)
   for n in RESPONSE:need(results[i][n]['shape']==((1,45,1) if n in ('HR','HRC') else (1,46,1)),'response dimension '+n)
   if i==1:need(data==baseline,'whole baseline byte equality')
   else:must_hold(results[1],results[i],HELD);must_hold(sidecars[1],sidecars[i],SOURCE)
   need(call['metrics']['held_main_sections']==sorted(HELD) and call['metrics']['held_source_sections']==sorted(SOURCE),'held declared roster')
   a=results[i];b=results[1];f=a['DN']['values'][0]
   metric={'policy':i,'surface_dn_Wm2':f,'toa_up_Wm2':a['UP']['values'][-1],'delta_vs_default_Wm2':f-b['DN']['values'][0],'delta_vs_legacy4_Wm2':f-f4,'max_native32_heating_delta_Kday':max(abs(x-y) for x,y in zip(a['HR']['values'][:32],b['HR']['values'][:32])),'max_full45_engine_heating_delta_Kday':max(abs(x-y) for x,y in zip(a['HR']['values'],b['HR']['values'])),'max_native32_clear_heating_delta_Kday':max(abs(x-y) for x,y in zip(a['HRC']['values'][:32],b['HRC']['values'][:32])),'max_full45_clear_heating_delta_Kday':max(abs(x-y) for x,y in zip(a['HRC']['values'],b['HRC']['values']))}
   old=review['metrics_independently_recomputed'][i-1]
   for n in old:need(bits(metric[n])==bits(old[n]),'terminal metric exact '+n)
   joins={'surface_down_W_m2':'surface_dn_Wm2','relative_to_default_W_m2':'delta_vs_default_Wm2','minus_actual_legacy4_W_m2':'delta_vs_legacy4_Wm2','TOA_up_W_m2':'toa_up_Wm2','max_native_heating_response_K_day':'max_native32_heating_delta_Kday','max_full_engine_heating_response_K_day':'max_full45_engine_heating_delta_Kday'}
   for n,k in joins.items():need(bits(call['metrics'][n])==bits(metric[k]),'execution metric exact '+n)
   metrics.append(metric)
 summary=json.loads((P/'summary.json').read_text());need(summary['metrics']==metrics,'archived package summary recomputation')
 background=json.loads((P/'audits/background-gases/audit.json').read_text());need(background['status']=='CONFIRMED_UNAVAILABLE_N2_MINOR_INTERVALS_REMOVED' and background['new_model_build_solver_calls']==0 and background['N2_unique_gpoint_counts']=={'lower':28,'upper':26},'source-only N2 finding scope')
 source=json.loads((P/'audits/source-contract/audit.json').read_text());need(source['new_model_build_solver_calls']==0 and len(source['input_joins'])==16 and all(r['byte_identical'] for r in source['source_pins']),'source audit scope')
 return {'schema':'BON_LW_transport_portable_verification_v1','status':'PASS_RETAINED_THREE_CALLS_HELD_SOURCE_OPTICS_AND_METRICS','manifest_sha256':digest(P/'artifact-manifest.json'),'payload_count':38,'original_payload_count':33,'standalone_calls_recorded':3,'private_compiler_calls_recorded':1,'WRF_REAL_calls_recorded':0,'new_engine_calls_from_verifier':0,'main_held_fields':18,'source_band_held_fields':5,'baseline_whole_file_exact':True,'metrics':metrics,'scope':'One matched-dry BON input, angular sensitivity only; N2 omitted in all three modes. Not exact legacy parity, physical accuracy or pure spectral attribution. External source/library closure is archived attestation.'}
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',type=Path);a=p.parse_args();r=verify()
 if a.output:
  o=a.output.resolve();need(P not in o.parents,'output must be outside package');o.parent.mkdir(parents=True,exist_ok=True)
  with o.open('x') as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
 print(json.dumps(r,sort_keys=True,allow_nan=False))
if __name__=='__main__':main()
