"""Stdlib replay of declared coupling, actual native kernel output and actual-run inventories.

Does not rerun WRF/NetCDF or independently re-read uncommitted large histories.
"""
import json,math,struct
from fractions import Fraction as F
def require(ok,msg):
 if not ok:raise ValueError(msg)
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def close(x,y,rel=4e-6,msg='native arithmetic'):
 require(math.isfinite(x) and abs(x-y)<=rel*max(1.,abs(y)),msg)
def compare_inventory(x):
 all_equal=True;pairs=0;bad=[]
 require(len(x['common_times'])>0,'missing common times')
 for t,rows in x['inventories'].items():
  require(t in x['common_times'] and len(rows)==x['variables'],'inventory extent')
  for n,row in rows.items():
   equal=row['continuous_sha256']==row['restart_sha256'];require(equal==row['bitwise_equal'],'array equality falsely reported');all_equal&=equal;pairs+=1
   if not equal:bad.append((t,n))
 require(pairs==x['array_pairs'] and all_equal==x['all_bitwise_equal'],'full restart bitwise promotion')
 require(set(bad)==set((d['time'],d['variable']) for d in x['differences']),'difference roster changed')
 for d in x['differences']:close(abs(d['continuous_at_max']-d['restart_at_max']),d['max_abs'],1e-12,'difference witness changed')
 return all_equal

def analyze(read,plan):
 a=json.loads(read('analysis.json'));selected=json.loads(read('selected.json'));mf=json.loads(read('manufactured.json'));native=[list(map(float,x.split())) for x in read('kernel/good/kernel.txt').decode().splitlines()]
 require(a['production_accepted'] is False and a['physical_accuracy_approved'] is False,'physical approval promotion')
 # Actual REAL32 NetCDF payload: eta -> native mass coupling -> stored endpoint difference.
 n=[F(str(x)) for x in mf['number_m3_endpoints']];rho=[F(str(x)) for x in mf['rho_endpoints']];mass=[F(str(x)) for x in mf['mass_factors_Pa']]
 states=[f32(f32(float(aa))*f32(float(nn/rr))) for nn,rr,aa in zip(n,rho,mass)]
 expected=[f32(f32(states[k+1]-states[k])/f32(3600.)) for k in range(2)]
 require(mf['fields']['QNCLOUD_BXS']==states[:2],'stored native mass-number values')
 require(mf['fields']['QNCLOUD_BTXS']==expected,'stored coupled endpoint tendencies')
 require(expected[0]>0 and (n[1]-n[0])==0,'density/mass tendency term omitted')
 endpoint=list(map(float,read('kernel/good/endpoints.txt').decode().split()));require(endpoint[:2]==[states[0],expected[0]],'native kernel not fed actual NetCDF payload')
 require(native[0]==[62500000.,50000000.,62500000.,50000000.,70000000.],'dry CCN inflow/outflow or interior reservoir overwritten')
 require(native[1]==[50000000.] and native[2][:4]==[50000000.,62500000.,50000000.,62500000.],'legacy/reversed-flow CCN contract')
 require(native[3][0]==expected[0] and native[3][2]==0,'specified tendency or interior modification')
 mid=(states[0]+1800*expected[0])/1100;end=(states[0]+3600*expected[0])/1200
 close(native[4][0],mid,msg='coupled midpoint uncoupling');require(native[4][1]==1.e8,'specified operation erased interior')
 close(native[5][0],end,msg='actual RK endpoint uncoupling')
 # Actual time-varying MU demonstrates the SECOND real file record, not stale extrapolation.
 src=selected['south_MU_source_records'];used=[]
 for row in a['boundary_records']:
  rec=row['record_zero_based'];dt=row['record_elapsed_s'];got=row['south_MU'];m=src['values'][rec];t=src['tendencies'][rec]
  want=[f32(x+f32(dt*y)) for x,y in zip(m,t)];require(got==want,'actual second boundary record not applied')
  stale=[f32(x+f32(row['elapsed_s']*y)) for x,y in zip(src['values'][0],src['tendencies'][0])]
  require(row['max_MU_expected_abs_Pa']==0,'nonzero native boundary residual')
  close(max(abs(x-y) for x,y in zip(got,stale)),row['max_MU_stale_abs_Pa'],1e-12,'stale-record witness')
  used.append(rec)
  for field in ['QNCLOUD','QNRAIN']:
   require(not any(selected[row['time']][field]['edge_values']),'prescribed zero-number edge changed')
 require(used==[0,0,1,1,1] and a['boundary_records'][-1]['max_MU_stale_abs_Pa']>0,'record crossing not demonstrated')
 last='2016-10-06_06:02:00'
 for n in ['QNCLOUD','QNRAIN','QNCCN']:require(a['history_stats'][last][n]['interior_positive_count']>0 and selected[last][n]['interior_max']>0,'interior number erased')
 for rows in a['history_stats'].values():
  for v in rows.values():require(v['min']>=0 and math.isfinite(v['max']),'invalid sampled history')
 # Keep the preregistered whole-host exact-restart FAILURE, despite successful I/O and boundary checks.
 require(not compare_inventory(a['original_restart']),'expected recorded full-host mismatch changed')
 require(not compare_inventory(a['restored_observation']),'observation must retain integrated mismatch')
 require(not compare_inventory(a['number0_host_control']),'number0 counterfactual evidence changed')
 require(compare_inventory(a['restart_observer_noninterference']),'observer altered trajectory')
 restored=a['restored_observation']['inventories']['2016-10-06_05:59:00'];require(len(restored)==225 and all(v['bitwise_equal'] for v in restored.values()),'checkpoint state not restored exactly')
 require(a['predeclared_full_restart_bitwise_criterion_passed'] is False and a['overall_preregistered_full_validation_passed'] is False and a['full_host_restart_bitwise_approved'] is False,'full restart criterion falsely promoted')
 cp=a['checkpoint'];require([cp[n] for n in ['UDM_NUMBER_POLICY','UDM_POPULATION_POLICY','UDM_SPECIFIED_NUMBER_CONTRACT']]==[1,0,1],'checkpoint policy contract lost')
 for key in ['integration','restore_observer','number0_control']:
  receipt=json.loads(read(key+'/receipt.json'));require(all(c['actual_returncode']==0 and not c['timed_out'] for c in receipt['commands']),'unsuccessful claimed trajectory')
 legacy=json.loads(read('legacy_regression/receipt.json'));require(legacy['same_arrays']==225 and legacy['times']==3,'changed-boundary default regression missing')
 refusals=json.loads(read('refusals/receipt.json'));require(len(refusals['outcomes'])==6,'refusal campaign extent')
 for k,row in enumerate(refusals['outcomes'],1):
  log=read(f'refusals/command-{k:02d}.stdout').decode(errors='replace')
  require(row['expected'] in log and 'FATAL CALLED' in log and 'SUCCESS COMPLETE WRF' not in log,'metadata refusal not exercised')
 return {'status':'IMPLEMENTED_SCOPED_SPECIFIED_NUMBER_BOUNDARIES_WITH_OPEN_HOST_RESTART','native_coupled_endpoints_REAL32':states,'native_tendencies_REAL32':expected,'CCN_flow_checks':'PASS_VOLUME_INFLOW_TO_ETA_AND_ZERO_GRADIENT_ETA_OUTFLOW','nonzero_native_kernel_checks':'PASS_STORED_VALUES_TENDENCY_RELAXATION_AND_RK_UNCOUPLING','actual_forcing_record_indices':used,'next_record_max_stale_MU_difference_Pa':a['boundary_records'][-1]['max_MU_stale_abs_Pa'],'interior_number_preserved':True,'checkpoint_restored_equal_arrays':225,'original_restart_compared_array_pairs':a['original_restart']['array_pairs'],'original_restart_differing_array_pairs':len(a['original_restart']['differences']),'full_host_restart_bitwise_criterion_passed':False,'same_kind_bitwise_mismatch_also_observed_in_number0':True,'first_arithmetic_cause':'not localized; no new-number-specific cause established','default_regression_arrays':225,'default_regression_times':3,'actual_file_configuration_refusals':6,'scope':'single serial specified domain, number1/population0, scalar_adv_opt0, moisture/scalar BCs; capacity0/size0; selected real trajectory needs existing experimental frozen1','production_defaults_changed':False,'optics_coefficients_or_density_tuned':False,'physical_accuracy_approved':False,'overall_preregistered_full_validation_passed':False,'existing_seven_closure_conditions_and_reference_FAILs':'PRESERVED','fresh_model_runs_in_saved_replay':0,'production_accepted':False}
