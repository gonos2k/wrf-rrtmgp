#!/usr/bin/env python3
"""Stdlib verification of archived N2 evidence; no compiler or solver execution."""
import argparse,gzip,hashlib,importlib.util,json,struct,sys,tempfile
from pathlib import Path
sys.dont_write_bytecode=True
P=Path(__file__).resolve().parent;REPO=P.parents[2]
IDS=('n2-absent-baseline','n2-explicit-zero','n2-0p7808')
HELD={'CLOUD_TAU','CU_CLOUD_TAU','CU_DI_USED','CU_RL_USED','DI_USED','DS_USED','FROZEN_TAU','GAS_COL_DRY','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','MASK','NATIVE_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU','RL_USED'}
RESPONSE={'UP','DN','HR','UPC','DNC','HRC'}
GAS={'GAS_TAU','GAS_TAU_RAW','TOTAL_TAU'}
SOURCE={'SOURCE_LAYER','SOURCE_LEVEL','SOURCE_SURFACE','BAND_LIMITS_GPOINT','BAND_LIMITS_WAVENUMBER','TRANSPORT_POLICY'}
def need(ok,msg):
 if not ok:raise ValueError(msg)
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def bits(x):return struct.pack('>d',float(x))
def same(a,b):return a['shape']==b['shape'] and len(a['values'])==len(b['values']) and all(bits(x)==bits(y) for x,y in zip(a['values'],b['values']))
def must_hold(a,b,names):
 need(set(names)<=set(a) and set(names)<=set(b),'required held field absent')
 for n in names:need(same(a[n],b[n]),'held field changed '+n)
def side_check(s,value):
 need(set(s)==SOURCE|({'N2_OVERRIDE'} if value is not None else set()),'exact N2 sidecar roster')
 shapes={'SOURCE_LAYER':(1,45,128),'SOURCE_LEVEL':(1,46,128),'SOURCE_SURFACE':(1,1,128),'BAND_LIMITS_GPOINT':(2,16,1),'BAND_LIMITS_WAVENUMBER':(2,16,1),'TRANSPORT_POLICY':(1,1,1)}
 for n,sh in shapes.items():need(s[n]['shape']==sh and len(s[n]['values'])==sh[0]*sh[1]*sh[2],'sidecar shape '+n)
 need(s['TRANSPORT_POLICY']['values']==[1.],'default transport policy')
 if value is not None:need(s['N2_OVERRIDE']['shape']==(1,1,1) and s['N2_OVERRIDE']['values']==[value],'exact dry N2 VMR declaration')
def gas_check(a,b,play,trop):
 for n in GAS:need(a[n]['shape']==b[n]['shape']==(1,45,128),'gas/total shape')
 need(len(play)==45 and all(len(a[n]['values'])==len(b[n]['values'])==5760 for n in GAS),'pressure/gas dimension')
 need(same(b['GAS_TAU'],b['GAS_TAU_RAW']) and same(a['GAS_TAU'],a['GAS_TAU_RAW']),'raw gas identity')
 changed=0;maxdelta=0.;maxres=0.
 for q,(x,y,tx,ty) in enumerate(zip(a['GAS_TAU']['values'],b['GAS_TAU']['values'],a['TOTAL_TAU']['values'],b['TOTAL_TAU']['values'])):
  k=q%45;g=q//45+1;delta=y-x
  allowed=1<=g<=26 or (g in (123,124) and play[k]*100.>trop)
  if bits(x)!=bits(y):need(allowed,'gas change outside N2 support');changed+=1
  need(delta>=0,'negative added gas absorption');maxdelta=max(maxdelta,delta);maxres=max(maxres,abs((ty-tx)-delta))
 need(changed>0,'positive N2 response absent')
 need(maxres==0,'TOTAL response differs from gas response in this archive')
 return {'changed_gas_cells':changed,'gas_tau_delta_min':min(y-x for x,y in zip(a['GAS_TAU']['values'],b['GAS_TAU']['values'])),'gas_tau_delta_max':maxdelta,'max_total_minus_gas_delta_residual':maxres}
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);sys.modules[n]=m;s.loader.exec_module(m);return m
def verify():
 manifest=json.loads((P/'artifact-manifest.json').read_text());origin=json.loads((P/'original-payload-roster.json').read_text());listed=[r['path'] for r in manifest['files']]
 expected={f'outputs/{n}.{kind}.gz' for n in IDS for kind in ('result','sidecar')}|{f'logs/{n}.log' for n in IDS}|{f'frozen/{n}' for n in ('compiled-reference_column.f90','compiled-adaptation.json','failed-reference_column.f90','failed-source-adaptation.json','failed-source.patch','cli-negative-checks.json','run_once.py','build_once-v1.py','build_once-v2.py')}|{f'receipts/{n}' for n in ('plan.json','authorization.json','preflight-v1.json','prelaunch-review-v1.json','execution.json','build-plan-v1.json','build-plan-v2.json','build-authorization-v1.json','build-authorization-v2.json','build-receipt-v1.json','build-receipt-v2.json','build-v1.log','build-v2.log','retained-link-dependencies.json','root-metrics-v1.json','terminal-review.json','runtime-README.md')}|{'README.md','verify.py','test_verify.py','summary.json','original-payload-roster.json'}
 actual={f.relative_to(P).as_posix() for f in P.rglob('*') if f.is_file() and f.name!='artifact-manifest.json'}
 need(len(listed)==len(set(listed)) and set(listed)==actual==expected and len(actual)==40,'closed40 payload roster')
 for r in manifest['files']:
  f=P/r['path'];need(not f.is_symlink() and digest(f)==r['sha256'] and f.stat().st_size==r['size_bytes'],'payload pin '+r['path'])
 need(len(origin['files'])==35 and {r['path'] for r in origin['files']}==expected-{'README.md','verify.py','test_verify.py','summary.json','original-payload-roster.json'},'35 original payload roster')
 for r in origin['files']:
  f=P/r['path'];need(digest(f)==r['retained_sha256'] and f.stat().st_size==r['retained_size_bytes'],'retained origin pin');data=f.read_bytes()
  need(r['encoding'] in ('gzip','verbatim'),'origin encoding');raw=gzip.decompress(data) if r['encoding']=='gzip' else data
  need(hashlib.sha256(raw).hexdigest()==r['original']['sha256'] and len(raw)==r['original']['size_bytes'],'original raw pin')
 ref={}
 for n,r in origin['repository_dependencies'].items():
  f=REPO/r['repository_relative_path'];need(digest(f)==r['sha256'] and f.stat().st_size==r['size_bytes'],'reused repository pin '+n);ref[n]=f
 def j(n):return json.loads((P/'receipts'/n).read_text())
 rec=j('execution.json');plan=j('plan.json');auth=j('authorization.json');fail=j('build-receipt-v1.json');build=j('build-receipt-v2.json');review=j('terminal-review.json')
 need(rec['status']=='PASS_THREE_N2_SENSITIVITY_CALLS' and rec['actual_solver_invocations']==3 and rec['WRF_REAL_build_invocations']==0 and rec['before']==rec['after'],'three archived calls and closure')
 need([c['id'] for c in rec['calls']]==list(IDS) and len({c['pid'] for c in rec['calls']})==3 and all(c['pid']>0 and c['returncode']==0 and not c['timed_out'] and c['validated'] for c in rec['calls']),'three unique successful PIDs')
 need(auth['maximum_solver_calls']==3 and auth['retries']==0 and auth['plan_sha256']==digest(P/'receipts/plan.json') and auth['runner_sha256']==digest(P/'frozen/run_once.py'),'run authorization')
 need(rec['plan']['sha256']==auth['plan_sha256'] and rec['runner']['sha256']==auth['runner_sha256'] and rec['authorization']['sha256']==digest(P/'receipts/authorization.json'),'execution provenance')
 for i,b in enumerate((fail,build),1):
  bp=j(f'build-plan-v{i}.json');ba=j(f'build-authorization-v{i}.json');src=P/'frozen'/('failed-reference_column.f90' if i==1 else 'compiled-reference_column.f90');adapt=P/'frozen'/('failed-source-adaptation.json' if i==1 else 'compiled-adaptation.json')
  need(b['actual_compiler_calls']==1 and b['WRF_REAL_solver_calls']==0 and not b['timed_out'],'one compile each/no engine calls')
  need(b['status']==('FAIL_STOPPED_NO_RETRY' if i==1 else 'PASS_PRIVATE_REFERENCE_COMPILE_LINK') and b['returncode']==(1 if i==1 else 0),'preserved failed/successful build labels')
  need(ba['maximum_compiler_calls']==1 and ba['maximum_solver_calls']==0 and ba['plan_sha256']==digest(P/f'receipts/build-plan-v{i}.json') and ba['runner_sha256']==digest(P/f'frozen/build_once-v{i}.py'),'build auth pins')
  need(b['plan']['sha256']==ba['plan_sha256'] and b['runner']['sha256']==ba['runner_sha256'] and b['authorization']['sha256']==digest(P/f'receipts/build-authorization-v{i}.json'),'build receipt joins')
  need(b['argv']==bp['argv'] and bp['source']['path'] in b['argv'] and bp['source']['sha256']==digest(src) and bp['source_adaptation']['sha256']==digest(adapt),'actual compiled source/argv')
  need(b['log']['sha256']==digest(P/f'receipts/build-v{i}.log'),'original compiler log')
 need('Error:' in (P/'receipts/build-v1.log').read_text() and 'READ' in (P/'receipts/build-v1.log').read_text(),'original READ compile failure retained')
 need(build['before']==build['after'] and build['extra_before']==build['extra_after'],'successful build closure')
 need(build['executable']['sha256']==plan['executable']['sha256']==rec['before']['executable']['sha256'],'single executable identity')
 need(plan['build_receipt']['sha256']==digest(P/'receipts/build-receipt-v2.json') and plan['source']['sha256']==digest(P/'frozen/compiled-reference_column.f90'),'runtime build/source pins')
 a=json.loads((P/'frozen/compiled-adaptation.json').read_text());old=json.loads((P/'frozen/failed-source-adaptation.json').read_text())
 need(a['adapted_source']['sha256']==digest(P/'frozen/compiled-reference_column.f90') and a['failed_source']['sha256']==digest(P/'frozen/failed-reference_column.f90') and a['failed_build']['sha256']==digest(P/'receipts/build-receipt-v1.json'),'corrected source preserves original failure')
 need(old['adapted_source']['sha256']==a['failed_source']['sha256'] and old['base_transport_source']['sha256']==digest(ref['angular_source']) and old['patch']['sha256']==digest(P/'frozen/failed-source.patch'),'historical source/base/patch joins')
 parser=load('n2_trace',ref['trace_parser']).read_trace;reader=load('n2_export',ref['export_reader']).read_export
 rawbase=gzip.decompress(ref['baseline'].read_bytes());rawinp=gzip.decompress(ref['input'].read_bytes());rawexp=gzip.decompress(ref['legacy_export'].read_bytes())
 need(hashlib.sha256(rawbase).hexdigest()==plan['matched_dry_baseline_result']['sha256']==plan['prior_angular_policy1_result']['sha256'] and rawbase==gzip.decompress(ref['angular_baseline'].read_bytes()),'two baseline archive joins')
 need(hashlib.sha256(rawinp).hexdigest()==plan['input']['sha256'] and plan['prior_angular_source']['sha256']==digest(ref['angular_source']),'same input/previous source')
 results=[];side=[];metrics=[]
 with tempfile.TemporaryDirectory(prefix='retained-n2-') as td:
  t=Path(td);(t/'input').write_bytes(rawinp);meta,inputs=parser(t/'input','input');need({k:meta[k] for k in ('phase','ncol','nlay')}=={'phase':'LW','ncol':1,'nlay':45} and all(x==0. for x in inputs['CF']['values']),'same input header/inactive clouds')
  (t/'export').write_bytes(rawexp);export=reader(t/'export',expected_phase='LW',expected_context={'domain':1,'i':13,'j':46,'step':721,'source_seconds':43200.});legacy=export['fields']['RESULT','DOWN_FLUX'].values[0]
  for i,(n,c) in enumerate(zip(IDS,rec['calls'])):
   rb=gzip.decompress((P/f'outputs/{n}.result.gz').read_bytes());sb=gzip.decompress((P/f'outputs/{n}.sidecar.gz').read_bytes())
   need(hashlib.sha256(rb).hexdigest()==c['result']['sha256'] and hashlib.sha256(sb).hexdigest()==c['sidecar']['sha256'] and digest(P/f'logs/{n}.log')==c['log']['sha256'],'actual output/log receipt')
   need(c['argv'][0]==plan['executable']['path'] and c['argv'][2]==plan['input']['path'] and c['argv'][3]==c['result']['path'] and c['argv'][4:]==plan['calls'][i]['argv_tail'] and c['n2_argument']==plan['calls'][i]['n2_argument'],'one input/ELF with declared N2-only CLI')
   (t/'result').write_bytes(rb);(t/'side').write_bytes(sb);m,r=parser(t/'result','result');s,sc=parser(t/'side','result');need(m==s=={'phase':'LW','ncol':1,'nlay':45},'result phase/dimensions')
   need(set(r)==HELD|GAS|RESPONSE,'exact24 main sections');side_check(sc,(None,0.,.7808)[i])
   bandfields={'PRECIP_TAU','CLOUD_TAU','NATIVE_CLOUD_TAU','CU_CLOUD_TAU','GRAUPEL_TAU_ABS','HAIL_TAU_ABS','FROZEN_TAU','PREPARED_TAU'}
   for key in HELD:
    shape=(1,45,16) if key in bandfields else (1,45,128) if key=='MASK' else (1,45,1)
    need(r[key]['shape']==shape,'held shape '+key)
   need(all(x==0. for x in r['CLOUD_TAU']['values']+r['PREPARED_TAU']['values']),'inactive cloud optics scope')
   edges=sc['BAND_LIMITS_GPOINT']['values'];mapped=[]
   for band in range(16):
    lo,hi=edges[band*2:band*2+2];need(lo==int(lo) and hi==int(hi),'integer gpoint mapping');mapped.extend((g,band) for g in range(int(lo),int(hi)+1))
   need([g for g,b in mapped]==list(range(1,129)),'complete coefficient gpoint coverage')
   for g,band in mapped:
    for k in range(45):need(bits(r['TOTAL_TAU']['values'][(g-1)*45+k])==bits(r['GAS_TAU']['values'][(g-1)*45+k]+r['FROZEN_TAU']['values'][band*45+k]),'gas plus frozen TOTAL exact in this archive')
   for key in RESPONSE:need(r[key]['shape']==((1,45,1) if key in ('HR','HRC') else (1,46,1)),'full response shape')
   results.append(r);side.append(sc)
   if i<2:need(rb==rawbase,'absent/zero whole baseline bytes')
   if i>0:must_hold(results[0],r,HELD);must_hold(side[0],sc,SOURCE)
   if i==0:need(sb==gzip.decompress(ref['angular_sidecar'].read_bytes()),'prior angular default sidecar bytes')
   metric={'id':n,'surface_dn_Wm2':r['DN']['values'][0],'toa_up_Wm2':r['UP']['values'][-1],'delta_surface_dn_Wm2':r['DN']['values'][0]-results[0]['DN']['values'][0],'delta_toa_up_Wm2':r['UP']['values'][-1]-results[0]['UP']['values'][-1],'surface_dn_minus_legacy4_Wm2':r['DN']['values'][0]-legacy,'max_native32_heating_delta_Kday':max(abs(x-y) for x,y in zip(r['HR']['values'][:32],results[0]['HR']['values'][:32])),'max_full45_heating_delta_Kday':max(abs(x-y) for x,y in zip(r['HR']['values'],results[0]['HR']['values'])),'max_native32_clear_heating_delta_Kday':max(abs(x-y) for x,y in zip(r['HRC']['values'][:32],results[0]['HRC']['values'][:32])),'max_full45_clear_heating_delta_Kday':max(abs(x-y) for x,y in zip(r['HRC']['values'],results[0]['HRC']['values']))}
   metrics.append(metric)
  must_hold(results[0],results[1],HELD|GAS|RESPONSE)
  locality=gas_check(results[0],results[2],inputs['PLAY']['values'],plan['pressure_reference']['press_ref_trop_Pa'])
  need(locality['changed_gas_cells']==rec['calls'][2]['positive_scope']['changed_gas_cells']==1136,'actual changed gas cells')
  need(rec['calls'][2]['positive_scope']['held_sections']==sorted(HELD) and rec['calls'][2]['positive_scope']['held_common_sidecar_sections']==sorted(SOURCE),'receipt exact held roster')
  joins={'surface_down_delta':'delta_surface_dn_Wm2','toa_up_delta':'delta_toa_up_Wm2','native_heating_max_abs_delta':'max_native32_heating_delta_Kday','full_heating_max_abs_delta':'max_full45_heating_delta_Kday'}
  for n,k in joins.items():need(bits(rec['calls'][2]['metrics'][n])==bits(metrics[2][k]),'execution metric recomputation '+n)
 summary=json.loads((P/'summary.json').read_text());need(summary['metrics']==metrics and summary['gas_locality']==locality,'summary independent recomputation')
 # The independent reviewer status/receipt is an archived attestation, not a numerical engine invocation.
 need(review['status']=='PASS_SCOPED_THREE_N2_CALLS' and review['execution_receipt']['sha256']==digest(P/'receipts/execution.json') and review['build_receipt']['sha256']==digest(P/'receipts/build-receipt-v2.json') and review['source']['sha256']==digest(P/'frozen/compiled-reference_column.f90') and review['executable']['sha256']==plan['executable']['sha256'],'independent terminal provenance/status')
 need(review['pids']==[c['pid'] for c in rec['calls']] and review['returncodes']==[0,0,0] and review['solver_invocations']==3 and review['WRF_REAL_build_invocations']==0,'independent call count/PIDs')
 need(review['held_main_sections']==sorted(HELD) and review['common_source_band_sections_exact_across_all_runs']==sorted(SOURCE) and review['gas_tau_locality']['changed_cells']==locality['changed_gas_cells'] and review['gas_tau_locality']['outside_allowed_changes']==0,'independent held/locality join')
 for m,old in zip(metrics,review['independently_recomputed_metrics']):
  joins={'surface_dn_Wm2':'surface_dn_Wm2','toa_up_Wm2':'toa_up_Wm2','surface_dn_minus_legacy4_Wm2':'absolute_surface_dn_residual_vs_legacy_Wm2','max_native32_heating_delta_Kday':'max_native32_heating_delta_vs_absent_Kday','max_full45_heating_delta_Kday':'max_full45_heating_delta_vs_absent_Kday'}
  for k,n in joins.items():need(bits(m[k])==bits(old[n]),'independent terminal metric '+n)
 need(review['source_audit']['sha256']==digest(ref['background_gases_audit']),'historical background audit join')
 return {'schema':'BON_N2_portable_verification_v1','status':'PASS_RETAINED_N2_CONTROLS_LOCALITY_AND_METRICS','manifest_sha256':digest(P/'artifact-manifest.json'),'payload_count':40,'original_payload_count':35,'standalone_calls_recorded':3,'private_compiler_attempts_recorded':2,'compile_failures_preserved':1,'compile_successes':1,'WRF_REAL_calls_recorded':0,'new_engine_calls_from_verifier':0,'held_main_fields':15,'held_source_band_policy_fields':6,'zero_whole_baseline_exact':True,'gas_locality':locality,'metrics':metrics,'scope':'One fixed BON column; declared constant dry N2 VMR, default angular policy. Not measured chemistry, exact legacy parity, physical accuracy or cross-policy interaction. External full source/library closure is archived attestation.'}
def main():
 ap=argparse.ArgumentParser();ap.add_argument('--output',type=Path);args=ap.parse_args();r=verify()
 if args.output:
  o=args.output.resolve();need(P not in o.parents,'output must be outside package');o.parent.mkdir(parents=True,exist_ok=True)
  with o.open('x') as f:json.dump(r,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
 print(json.dumps(r,sort_keys=True,allow_nan=False))
if __name__=='__main__':main()
