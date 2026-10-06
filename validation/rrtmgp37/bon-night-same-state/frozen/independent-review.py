#!/usr/bin/env python3
"""Read-only terminal BON evidence review: no model, compiler or solver launch."""
import csv,datetime,hashlib,importlib.util,json,sys
from pathlib import Path
import numpy as np
sys.dont_write_bytecode=True
ROOT=Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
HERE=Path(__file__).resolve().parent
STAGE=ROOT/'build/udm37-current-bon-night-serial-audit-v2'
def pin(p):
 p=Path(p).absolute();return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size}
def load(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m
def stats(v):
 a=np.asarray(v,dtype=np.float64);assert np.isfinite(a).all();return {'minimum':float(a.min()),'maximum':float(a.max()),'nonzero_count':int(np.count_nonzero(a)),'count':int(a.size)}
def bits(a,b):return np.asarray(a,dtype=np.float64).tobytes()==np.asarray(b,dtype=np.float64).tobytes()
def main():
 before={n:pin(STAGE/n) for n in ['execution-receipt.json','runtime-spec.json','runtime-build-identity.json','readiness-index-v1.json','run_bon_once.py','root-execution-authorization.json','observed-export-selector.json']}
 assert before['execution-receipt.json']['sha256']=='00d7abb5b6f92e1dc4a2b07724fbf1fe6a6c2853c4614d4a59e2af0a71ef6240'
 r=load('bon_terminal_runtime',STAGE/'run_bon_once.py');spec=json.loads((STAGE/'runtime-spec.json').read_text());identity=json.loads((STAGE/'runtime-build-identity.json').read_text());rec=json.loads((STAGE/'execution-receipt.json').read_text())
 assert rec['status']=='PASS_BON_NIGHT_OUTPUT_CAPTURE_AUDIT_LW_EXPORT' and rec['model_invocations']==3 and rec['REAL_solver_build_invocations']==0
 static=r.static(spec,());build=r.build_snapshot(identity);completed=r.completed_pins(rec);_,nc,reader=r.helpers(spec)
 quality=[];comparisons=[];actual_groups={};csvs={};processes=[];warnings={}
 for arm in r.ARMS:
  a=rec['arms'][arm];case=STAGE/'cases'/arm
  assert a['status']=='PASS_ARM' and a['actual_invocations']==1 and a['returncode']==0 and not a['timed_out'] and not a['process_error']
  launch=json.loads((STAGE/f'launch-{arm}.json').read_text());proc=json.loads((STAGE/f'process-{arm}.json').read_text())
  assert launch['pid']==proc['pid']==a['pid'] and proc['returncode']==0 and not proc['timed_out'] and launch['command']==[build['executable']['path']]
  assert a['master_stack_limit_bytes'][0]==536870912 and a['controlled_environment']['OMP_NUM_THREADS']=='1'
  lg=r.log_gate(case);assert lg==a['log_validation']
  warnings[arm]=(case/'wrf.stdout.log').read_text(errors='replace').count('RRTMGP_UDM_DIAGNOSTIC_RESTART_UNAVAILABLE')
  processes.append({'arm':arm,'pid':a['pid'],'returncode':0,'timeout':False,'stack_soft_bytes':536870912,'launch':pin(STAGE/f'launch-{arm}.json'),'durable_process':pin(STAGE/f'process-{arm}.json'),'success_ranks_deduplicated':lg['success_ranks_deduplicated']})
  assert sorted(p.name for p in case.glob('wrfout_d01_*'))==['wrfout_d01_'+t for t in r.TIMES]
  assert sorted(p.name for p in case.glob('wrfrst_d01_*') if p.name!=r.CP_INPUT)==['wrfrst_d01_'+r.TIMES[-1]]
  for n,p in a['outputs'].items():
   q=nc.verify_history(Path(p['path']),n.split('_d01_',1)[1]);assert q['file']==p
   quality.append({'arm':arm,'file':p,'times':q['times'],'variables':q['variables'],'numeric_values_checked':q['numeric_values_checked'],'raw_decoded_finite_no_fill_or_mask':True})
   if arm!='OFF':
    out=nc.compare_netcdf(Path(rec['arms']['OFF']['outputs'][n]['path']),Path(p['path']));assert out['status']=='PASS_EXACT' and out['left']['sha256']==out['right']['sha256']
    comparisons.append({'arm':arm,'file_name':n,'status':out['status'],'whole_file_sha256':p['sha256'],'raw_schema_dtype_dimensions_all_attributes_data_model_equal':True})
  gs=r.capture_roster(case);assert gs==a['captures'];actual_groups[arm]=gs
  if arm!='OFF':
   audit,rows=r.audit_rows(case,arm,gs);assert audit==a['audit'];csvs[arm]=rows
  else:assert not (case/'audit').exists()
 def roster(gs):return {(g['phase'],g['step'],g['source_seconds']):{s:p['sha256'] for s,p in g['files'].items()} for g in gs}
 assert roster(actual_groups['OFF'])==roster(actual_groups['ON_native4_0'])==roster(actual_groups['ON_native4_1'])
 assert len(actual_groups['OFF'])==6 and all(g['phase']=='LW' for g in actual_groups['OFF'])
 sel=r.selector_from_off(actual_groups['OFF']);assert sel==rec['selector'] and sel['selector']=={'domain':1,'i':13,'j':46,'step':721,'source_seconds':43200.}
 keys=set(csvs['ON_native4_0']);assert keys==set(csvs['ON_native4_1']);numeric=['value37','value4','mean37','mean4','sd37','sd4','sd_delta']
 for k in keys:
  a=csvs['ON_native4_0'][k];b=csvs['ON_native4_1'][k]
  assert all(bits([float(a[n])],[float(b[n])]) for n in numeric)
  assert all(float(a[n])==0. for n in ['sd37','sd4','sd_delta'])
 surface=[];toa=[];hr=[]
 for k in sorted(keys):
  ph,step,sec,i,j,metric=k
  if ph!='LW' or (i,j)!=(13,46):continue
  a=csvs['ON_native4_0'][k];x=float(a['value37']);y=float(a['value4']);d=x-y
  row={'step':step,'source_seconds':sec,'engine37_W_m2':x,'engine4_W_m2':y,'delta37_minus4_W_m2':d}
  if metric=='SURFACE_DOWN':surface.append(row)
  elif metric=='TOA_UP':toa.append(row)
  elif metric.startswith('HEAT_'):hr.append({'step':step,'native_layer_1based':int(metric[5:]),'delta37_minus4_K_day':d})
 call_state=[];parsed={}
 for g in actual_groups['OFF']:
  fields={}
  for kind,p in g['files'].items():
   ph,x=r.parse_capture(Path(p['path']),kind);assert ph=='LW';fields[kind]=x
  parsed[g['step']]=fields;inp=fields['input'];res=fields['result'];raw=fields['raw']
  state={'step':g['step'],'source_seconds':g['source_seconds'],'native_layers':32,'engine_layers':inp['PLAY']['shape'][-1],'raw_sections':len(raw),'input_sections':len(inp),'result_sections':len(res),'input':{n:stats(inp[n]['values']) for n in ['CF','LWP','IWP','SWP','RWP','GWP','HWP','CU_LWP','CU_IWP','H2O','CO2','O3','REL','REI','RES','TSFC']},'result':{n:stats(res[n]['values']) for n in ['MASK','NATIVE_CLOUD_TAU','CU_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU','FROZEN_TAU','GRAUPEL_TAU_ABS','HAIL_TAU_ABS']}}
  assert all(state['input'][n]['nonzero_count']==0 for n in ['CF','LWP','IWP','SWP','RWP','CU_LWP','CU_IWP'])
  assert all(state['result'][n]['nonzero_count']==0 for n in ['MASK','NATIVE_CLOUD_TAU','CU_CLOUD_TAU','PRECIP_TAU','PREPARED_TAU'])
  assert bits(res['DN']['values'],res['DNC']['values']) and bits(res['UP']['values'],res['UPC']['values']) and bits(res['HR']['values'],res['HRC']['values'])
  state['allsky_equals_clear_in_captured37_result']=True;call_state.append(state)
 files=list((STAGE/'cases/ON_native4_1/legacy-export').iterdir());assert len(files)==1
 exp=reader.read_export(files[0],expected_phase='LW',expected_context=sel['selector']);ef=exp['fields']
 for n in ['MCICA_MASK','CLDPRMC_TAU','RRTMG_INPUT_CLOUD_TAU']:assert np.count_nonzero(ef[('CLOUD',n)].values)==0
 assert bits(ef[('RESULT','DOWN_FLUX')].values,ef[('RESULT','DOWN_CLEAR_FLUX')].values)
 first=parsed[721];mapping={'PLAY':'PLAY','PLEV':'PLEV','TLAY':'TLAY','TLEV':'TLEV','TSFC':'TSFC','H2O_VMR':'H2O','CO2_VMR':'CO2','O3_VMR':'O3','N2O_VMR':'N2O','CH4_VMR':'CH4','O2_VMR':'O2','CFC11_VMR':'VMR_CFC11','CFC12_VMR':'VMR_CFC12','CFC22_VMR':'VMR_CFC22','CCl4_VMR':'VMR_CCL4','SURFACE_EMISSIVITY':'EMIS'}
 joins=[]
 for legacy,gp in mapping.items():
  a=ef[('INPUT',legacy)];b=first['input'][gp];assert a.shape==tuple(d for d in b['shape'] if d!=1) or len(a.values)==len(b['values'])
  assert bits(a.values,b['values']),legacy
  joins.append({'legacy_field':legacy,'capture_field':gp,'values':len(a.values),'IEEE64_equal':True,'units':a.units})
 lmass=np.asarray(ef[('INPUT','COLDry')].values);gmass=np.asarray(first['result']['GAS_COL_DRY']['values']);assert lmass.shape==gmass.shape
 ratio=lmass/gmass
 assert {n:pin(STAGE/n) for n in before}==before
 report={'schema':'bon-night-independent-terminal-review-v1','status':'PASS_SCOPED_READONLY_TERMINAL','created_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'frozen_inputs':before,'actual_forecasts_this_campaign':3,'actual_compile_REAL_standalone_solver_invocations_from_review':0,'processes':processes,'full_output_quality':quality,'full_output_comparisons':comparisons,'completed_file_pin_check':completed,'source_build_closure':{'head':build['source_head'],'source_files':build['tracked_source_count'],'executable':build['executable'],'runtime_library_count':len(build['runtime_libraries']),'build_receipt':build['build_receipt']},'actual_LW_calls':[{'step':g['step'],'source_seconds':g['source_seconds']} for g in actual_groups['OFF']],'capture_parity':{'files_per_arm':18,'files_total':54,'input_raw_result_bits_equal_all_arms':True,'SW_capture_calls':0},'selector':sel,'csv':{'rows_per_ON_arm':len(keys),'allsky_only':True,'seeds_per_row':128,'all_metric37_and4_statistics_equal_between_radius_arms':True,'all_seed_SD_zero':True,'night_SW_rows_zero_with_no_solver_capture':True},'surface_LW_W_m2':surface,'surface_delta37_minus4_range_W_m2':[min(x['delta37_minus4_W_m2'] for x in surface),max(x['delta37_minus4_W_m2'] for x in surface)],'TOA_LW_W_m2':toa,'native_heating_delta_K_day_max_abs':max(abs(x['delta37_minus4_K_day']) for x in hr),'call_input_state':call_state,'selected_legacy_LW_export':{'file':pin(files[0]),'metadata':exp['metadata'],'fields':len(ef),'matched_input_IEEE64_joins':joins,'cloud_masks_and_optics_zero':True,'allsky_equals_clear_DOWN':True,'dry_molecule_column_units':ef[('INPUT','COLDry')].units,'legacy_over_GP_native32_dry_column_ratio_range':[float(ratio[:32].min()),float(ratio[:32].max())],'legacy_over_GP_extension13_dry_column_ratio_range':[float(ratio[32:].min()),float(ratio[32:].max())],'dry_column_equal':bool(bits(lmass,gmass))},'legacy_checkpoint_missing_CF3_warning_counts_in_unique_stdout':warnings,'scope':['Source/input/observer preservation verified for this three-forecast serial night campaign.','Six captured LW calls have CF/native cloud/CU/precip paths and sampled cloud optical depths exactly zero. Tiny frozen graupel/hail optical depths remain nonzero (maximum 5.6602135279084944e-21); captured allsky/clear DN, UP and HR are bitwise equal, not a proof of exactly zero physical frozen effect.','The same-state 37-minus4 surface contrast is about +1.24 W/m2, without seed spread; changing legacy radius mapping has no effect in this inactive-cloud column.','This demonstrates a clear-column engine/input-construction contrast, not a cloud-radius/McICA explanation for this call. VMR/thermodynamic inputs match but molecular dry-column construction differs.','This one night column does not resolve common observed LW bias across sites/times, physical accuracy, atmospheric/surface/observation mismatch, or distinguish gas construction from spectral/solver effects.','Experimental frozen1/roughness1; 128 seed statistics are descriptive, not an independent sample ensemble. CSV is allsky; no daytime/SW validation or optical truth claim.','Current source f731 is used; old checkpoint CF3 fallback warnings preserved. No exact old diagnostic-state restoration claim.'],'model_count_context':{'root_reported_cumulative_forecasts':97,'this_review_new_forecasts':0}}
 out=HERE/'terminal-review.json'
 with out.open('x') as f:json.dump(report,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n')
 print(json.dumps({'status':report['status'],'review':pin(out),'surface_range':report['surface_delta37_minus4_range_W_m2'],'native_heating_max':report['native_heating_delta_K_day_max_abs']}))
if __name__=='__main__':main()
