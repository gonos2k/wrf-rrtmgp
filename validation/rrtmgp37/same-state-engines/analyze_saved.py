"""Pure stdlib analysis of actual paired engine calls, not a new forecast."""
import math,json
from pathlib import Path
MOL=('H2O','CO2','O3','N2O','CH4','O2');CASES=('lw_clear','sw_clear','lw_liquid','sw_liquid','lw_liquid_seed_control','sw_liquid_seed_control')
def require(v,msg):
 if not v:raise ValueError(msg)
def near(x,y,tol,msg):require(abs(x-y)<=tol*max(1.,abs(x),abs(y)),msg)
def parse37(data,kind):
 lines=data.decode().splitlines();magic=lines[0];header=lines[1].split();pos=2;fields={}
 require(magic in (('RRTMGP_REPLAY_V6','RRTMGP_REPLAY_V12') if kind=='input' else ('RRTMGP_RESULT_V1',)),'capture schema')
 while pos<len(lines):
  z=lines[pos].split();pos+=1
  if not z:continue
  name=z[0];shape=list(map(int,z[1:]));count=math.prod(shape);v=[]
  require(shape and min(shape)>0 and name not in fields,'capture dimensions or duplicate')
  while len(v)<count:v.extend(map(float,lines[pos].split()));pos+=1
  require(len(v)==count and all(map(math.isfinite,v)),'capture values')
  fields[name]={'shape':shape,'values':v}
 return header,fields

def parse4(data):
 ls=data.decode().splitlines();require(ls[0]=='RRTMG4_SELECTED_COLUMN_EXPORT_V1','export schema');meta=dict(l.split() for l in ls[1:7]);pos=8;stage=None;fields={}
 require(meta=={'phase':meta['phase'],'domain':'1','step':'6511','source_seconds':ls[4].split()[1],'i':'1','j':'2'} and float(meta['source_seconds'])==65100.,'export source context')
 while pos<len(ls):
  z=ls[pos].split();pos+=1
  if not z:continue
  if z[0]=='stage':stage=z[1];continue
  name,unit=z[:2];shape=list(map(int,z[2:]));count=math.prod(shape);v=[]
  require(stage in ['INPUT','CLOUD','GAS','RESULT'] and shape and min(shape)>0 and (stage,name) not in fields,'export stage/dimensions')
  while len(v)<count:v.extend(map(float,ls[pos].split()));pos+=1
  require(len(v)==count and all(map(math.isfinite,v)),'export values')
  fields[stage,name]={'shape':shape,'values':v,'unit':unit}
 return meta,fields

def native4(data):
 ls=data.decode().splitlines();require(ls[0]=='SAME_STATE_RRTMG4_V1' and list(map(int,ls[1].split()))==[121,59],'native layout')
 const=list(map(float,ls[2].split()));names=('UP','DN','HR','UPC','DNC','HRC','COLDry','gas_bridge','Cstar')
 rows={n:list(map(float,l.split())) for n,l in zip(names,ls[3:])};require(len(rows)==9,'native rows')
 for n,v in rows.items():require(len(v)==(59 if n=='Cstar' else 121 if n in ['HR','HRC','COLDry','gas_bridge'] else 122),'native row extent')
 return const,rows

def target(u,d,h,native_top=59):
 require(native_top==59,'extended TOA is not native top')
 n=[y-x for x,y in zip(u,d)];return {'surface':{'up':u[0],'down':d[0],'net_down':n[0]},'native_top':{'up':u[59],'down':d[59],'net_down':n[59]},'native_column_net_convergence':n[59]-n[0],'heating_K_day':h[:59]}
def delta(a,b):return [x-y for x,y in zip(a,b)]
def analyze(read,plan):
 rows={};base_inputs={};num=plan['predeclared_numerical_checks'];maxgas=0.;source_errors={}
 receipt=json.loads(read('runtime/receipt.json'));require(len(receipt['runs'])==6 and len(receipt['commands'])==6,'paired execution count')
 require(all(x['actual_returncode']==0 and not x['timed_out'] for x in receipt['commands']),'unsuccessful process')
 for name in CASES:
  ph=name[:2];arm='liquid' if 'liquid' in name else 'clear';header,inp=parse37(read(name+'/'+ph+'.input'),'input');rh,res=parse37(read(name+'/'+ph+'.result'),'result');meta,exp=parse4(read(name+'/export4.txt'));const,v4=native4(read(name+'/native4.txt'))
  require(meta['phase']==ph,'export phase mismatch')
  require(header[0]==ph.upper() and header[1:3]==['1','121'] and rh==[ph.upper(),'1','121'],'common vertical grid')
  require(read(name+'/before.bin')==read(name+'/after4.bin')==read(name+'/after37.bin'),'diagnostic mutated physical state')
  cf=[0.]*121;lwp=[0.]*121
  if arm=='liquid':cf[29]=1.;lwp[29]=10.
  require(inp['CF']['values']==cf and inp['LWP']['values']==lwp and inp['REL']['values']==[21.5]*121,'explicit diagnostic cloud definition')
  for n in ('IWP','SWP'):require(inp[n]['values']==[0.]*121,'non-liquid hydrometeor')
  # Both spectral grids represent the same deterministic CF0/1 pattern.
  mask=res['MASK'];ng=mask['shape'][-1];require(mask['shape']==[1,121,ng],'37 mask layout')
  require(mask['values']==cf*ng,'37 cloud sample differs')
  for n,vals in [('MCICA_MASK',cf),('CLDPRMC_LWP',lwp)]:
   f=exp['CLOUD',n];ng4=f['shape'][0];require(f['shape']==[ng4,121] and f['values']==[v for v in vals for _ in range(ng4)],'4 cloud sample/path differs')
  require(exp['CLOUD','CLDPRMC_RELIQ']['values']==inp['REL']['values'],'4 radius changed')
  # Common physical inputs, including the shared upper extension.
  for a,b in [('PLAY','PLAY'),('PLEV','PLEV'),('TLAY','TLAY')]+([('TLEV','TLEV'),('TSFC','TSFC')] if ph=='lw' else []):
   if a in inp:require(exp['INPUT',b]['values']==inp[a]['values'],'thermodynamic input mismatch '+a)
  p=inp['PLEV']['values'];c4name='COLDry' if ph=='lw' else 'COLDRY';coldry=exp['INPUT',c4name]['values'];gas37=res['GAS_COL_DRY']['values'];require(coldry==v4['COLDry'],'4 actual gas formula differs from bridge target')
  for x,y in zip(gas37,coldry):
   err=abs(x-y)/max(abs(y),1e-30);maxgas=max(maxgas,err);require(err<=num['gas_relative_match'],'gas molecular column mismatch')
  wkl=exp['INPUT','WKL_MOLECULE_COLUMNS'];nm=wkl['shape'][0];gas_errors={}
  for mol,idx in zip(MOL,[0,1,2,3,5,6]):
   require(exp['INPUT',mol+'_VMR']['values']==inp[mol]['values'],'dry VMR mismatch '+mol)
   err=max(abs(inp[mol]['values'][k]*gas37[k]-wkl['values'][k*nm+idx])/max(abs(wkl['values'][k*nm+idx]),1e-30) for k in range(121));require(err<=num['gas_relative_match'],'consumed gas amount mismatch '+mol);gas_errors[mol]=err
  if ph=='sw':
   for a,b in [('AVDIR','ALBEDO_VIS_DIRECT'),('AVDIF','ALBEDO_VIS_DIFFUSE'),('ANDIR','ALBEDO_NIR_DIRECT'),('ANDIF','ALBEDO_NIR_DIFFUSE'),('MU0','COSZEN'),('SOLAR','SOLAR_CONSTANT')]:require(inp[a]['values']==exp['INPUT',b]['values'],'solar/surface input mismatch '+a)
   require(exp['INPUT','EARTH_SUN_ADJUSTMENT']['values']==[1.],'solar distance mismatch')
  else:require(exp['INPUT','SURFACE_EMISSIVITY']['values']==inp['EMIS']['values']*16,'surface emissivity mismatch')
  require(res['RL_USED']['values']==[21.5]*121,'37 radius clamped unexpectedly')
  if arm=='clear':
   for n in ['CLOUD_TAU']:require(not any(res[n]['values']),'nonzero clear-cloud optics')
  u37=res['UP_WP']['values'];d37=res['DN_WP']['values'];h37=[v*86400 for v in res['HEAT_WP_K_S']['values']];u4=v4['UP'];d4=v4['DN'];h4=v4['HR']
  for n,vs in [('UP_FLUX',u4),('DOWN_FLUX',d4),('HEATING',h4)]:require(exp['RESULT',n]['values'][:len(vs)]==vs,'4 native output differs from actual solve')
  q37=[(d37[k+1]-u37[k+1])-(d37[k]-u37[k]) for k in range(59)];q4=[(d4[k+1]-u4[k+1])-(d4[k]-u4[k]) for k in range(59)]
  Cstar=v4['Cstar'];require(Cstar==list(map(float,read(name+'/input.dat').decode().splitlines()[18].split())),'common heat capacity differs from declared host Cstar')
  require(len(Cstar)==59 and all(x>0 for x in Cstar),'common heat capacity')
  cp=inp['CP_DRY']['values'][0];grav=inp['GRAVITY']['values'][0];C37=[(p[k]-p[k+1])*100*cp/grav for k in range(59)];C4=[(p[k]-p[k+1])*86400/const[0] for k in range(59)]
  original={};math_decomp=[];maxe4=0.;maxe37=0.
  for k in range(59):
   e4=C4[k]*h4[k]/86400-q4[k];e37=C37[k]*h37[k]/86400-q37[k]
   bound4=256*2**-23*max(1.,abs(u4[k])+abs(d4[k])+abs(u4[k+1])+abs(d4[k+1]));bound37=256*2**-52*max(1.,abs(u37[k])+abs(d37[k])+abs(u37[k+1])+abs(d37[k+1]))
   require(abs(e4)<=bound4,'4 flux/heating source screen');require(abs(e37)<=bound37,'37 flux/heating source screen');maxe4=max(maxe4,abs(e4));maxe37=max(maxe37,abs(e37))
   flux=(q37[k]-q4[k])/Cstar[k]*86400;cap37=q37[k]*(1/C37[k]-1/Cstar[k])*86400;cap4=-q4[k]*(1/C4[k]-1/Cstar[k])*86400;arith=e37/C37[k]*86400-e4/C4[k]*86400
   near(h37[k]-h4[k],flux+cap37+cap4+arith,1e-10,'heating difference decomposition')
   math_decomp.append({'layer':k+1,'Q37_W_m2':q37[k],'Q4_W_m2':q4[k],'Cstar_J_m2_K':Cstar[k],'C37_J_m2_K':C37[k],'C4_J_m2_K':C4[k],'common_capacity_radiative_difference_K_day':flux,'capacity37_term_K_day':cap37,'capacity4_term_K_day':cap4,'native_arithmetic_term_K_day':arith,'original_native_heat_difference_K_day':h37[k]-h4[k]})
  common37=[q37[k]/Cstar[k]*86400 for k in range(59)];common4=[q4[k]/Cstar[k]*86400 for k in range(59)]
  t37=target(u37,d37,common37);t4=target(u4,d4,common4)
  dt={where:{n:t37[where][n]-t4[where][n] for n in ('up','down','net_down')} for where in ('surface','native_top')};dt['native_column_net_convergence']=t37['native_column_net_convergence']-t4['native_column_net_convergence'];dt['common_capacity_heating_K_day']=delta(common37,common4)
  source_errors[name]={'max4_W_m2':maxe4,'max37_W_m2':maxe37}
  incident=None
  if ph=='sw':
   requested=inp['SOLAR']['values'][0]*inp['MU0']['values'][0]
   incident={'requested_solar_times_mu0_W_m2':requested,'engine4_actual_top_down_W_m2':d4[-1],'engine37_actual_top_down_W_m2':d37[-1],'engine4_native_spectral_sum_arithmetic_residual_W_m2':d4[-1]-requested,'engine37_residual_W_m2':d37[-1]-requested}
  rows[name]={'incident_solar_boundary':incident,'phase':ph,'arm':arm,'consumed_gas_relative_errors':gas_errors,'surface_native_top_common_heat_37':t37,'surface_native_top_common_heat_4':t4,'signed_difference37_minus4':dt,'native_heating37_K_day':h37[:59],'native_heating4_K_day':h4[:59],'layer_heat_decomposition':math_decomp,'physical_input_and_deterministic_masks_match':True}
  base_inputs[name]=inp
 for ph in ('lw','sw'):
  a=rows[ph+'_liquid'];b=rows[ph+'_liquid_seed_control'];require(a==b,'deterministic cloud seed control differs')
  for k in base_inputs[ph+'_clear']:
   if k in ('CF','LWP'):continue
   require(base_inputs[ph+'_clear'][k]==base_inputs[ph+'_liquid'][k],'cloud arm changed atmospheric/surface input '+k)
 cloud_effect={}
 for ph in ('lw','sw'):
  cloudy=rows[ph+'_liquid'];clear=rows[ph+'_clear'];cloud_effect[ph]={}
  for e in ('37','4'):
   co=cloudy['surface_native_top_common_heat_'+e];cl=clear['surface_native_top_common_heat_'+e]
   d={w:{n:co[w][n]-cl[w][n] for n in ('up','down','net_down')} for w in ('surface','native_top')};d['native_column_net_convergence']=co['native_column_net_convergence']-cl['native_column_net_convergence'];d['heating_K_day']=delta(co['heating_K_day'],cl['heating_K_day']);cloud_effect[ph][e]=d
 return {'status':'EXECUTED_SAME_STATE_ENGINE_DIAGNOSTIC','actual_paired_processes':6,'actual_engine_calls':12,'max_dry_gas_column_relative_difference':maxgas,'source_consistency':source_errors,'cases':rows,'cloud_minus_clear_each_engine':cloud_effect,'decision':{'comparison_implementation':'COMPLETED_FOR_DECLARED_CLEAR_AND_CF1_LIQUID_STATES','physical_accuracy_approval':False,'same_forecast_state_updated':False,'partial_cloud_sampling_approved':False,'new_production_policy_or_guard_removal':False,'full_4_37_coupled_forecast_approved':False,'seven_closure_conditions_and_reference_FAIL':'PRESERVED','engine_difference_includes':'pinned gas/cloud optics, spectral grids, internal background/broadening conventions, transport and native arithmetic; not pure RTE-only error','numerical_uncertainty':'native source residuals retained; no independent total-engine true-error bound or physical acceptance tolerance inferred'},'new_WRF_forecasts':0,'production_accepted':False}
