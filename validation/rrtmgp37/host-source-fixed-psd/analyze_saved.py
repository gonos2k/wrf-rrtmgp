"""Replay actual source/application boundaries and fixed-M0/M3 PSD effects."""
import gzip,hashlib,importlib.util,json,math,struct
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
old=load(ROOT/'validation/rrtmgp37/policy2-budget-optics/analyze_saved.py','old_budget');require=old.require

def records(data):
 wq={};sq={}
 for l in data.decode().splitlines():
  w=l.split()
  if not w:continue
  if w[0].startswith('WQ_'):
   key=(w[0],*map(int,w[1:6]));z=list(map(float,w[6:]));require(len(z)==15 and key not in wq and all(math.isfinite(x) for x in z),'WQ record');wq[key]=z
  elif w[0].startswith('SQ_'):
   key=(w[0],*map(int,w[1:7]));z=list(map(float,w[7:]));require(len(z)==10 and key not in sq and all(math.isfinite(x) for x in z),'SQ record');sq[key]=z
 return wq,sq

def analyze(read):
 result={'production_accepted':False,'physics_gates_closed':False,'host':{}};prior=ROOT/'validation/rrtmgp37/consistent-warm-input/result.json';baseline=json.loads(prior.read_text())['host']
 for name,idx,dt in [('on_dt10',2,10),('on_dt5',3,5)]:
  raw=read(f'host/command-{idx:02d}.stdout');wq,sq=records(raw);mb=old.micro_records(raw);h=old.History(json.loads(read('host/'+name+'.json')),read('host/'+name+'.bin'));base=old.host_budget(h,mb,dt);require(base=={k:v for k,v in baseline['final-'+name].items() if k!='rk_forcing'},'same-input host changed since PR176')
  require(all(h.at('QCLOUD',6,k,j,i)==0 and h.at('QNCLOUD',6,k,j,i)==0 for k in range(59) for j in range(2) for i in range(2)),'terminal cloud PSD scope changed')
  require(len(wq)==2*(60//dt)*4*59 and len(sq)==(60//dt)*4*59*3*8,'source/update coverage differs');rows=[]
  gamma=(24*2**-24)/(1-24*2**-24)
  for step in range(1,60//dt+1):
   flux=pbl_md=pbl_dp=pd_delta=pd_src=pd_error=rk_delta=rk_src=rk_adv=rk_error=bound=0.
   for j in [1,2]:
    for i in [1,2]:
     a=wq['WQ_PBL',step,1,i,j,1];flux+=a[8]*dt/4
     for k in range(1,60):
      a=wq['WQ_PBL',step,1,i,j,k];require(a[9]>a[10]>0 and a[12]==dt,'PBL pressure/time fields');pbl_md+=a[2]*(a[6]+a[7])*dt/4;pbl_dp+=(a[9]-a[10])/9.810000419616699*(a[6]+a[7])*dt/4
      for im in [2,3,4]:
       x=sq['SQ_PD_PRE',step,3,im,i,j,k];z=sq['SQ_PD_POST',step,3,im,i,j,k];require(x[:2]==z[:2] and x[6]==dt and z[4]==0,'PD mass/time/source changed');actual=x[0]*(z[2]-x[2]);source=x[8]*x[6]*x[4];pd_delta+=actual/4;pd_src+=source/4;pd_error+=(actual-source)/4;bound+=gamma*(abs(x[0]*x[2])+abs(source))/4
       a=sq['SQ_PRE',step,3,im,i,j,k];z=sq['SQ_POST',step,3,im,i,j,k];require(a[:2]==z[:2] and a[2]==z[2] and a[6]==dt,'RK mass/time/baseline changed');actual=a[1]*z[3]-a[0]*a[2];source=a[8]*a[6]*a[4];adv=a[8]*a[6]*a[5]*a[7];rk_delta+=actual/4;rk_src+=source/4;rk_adv+=adv/4;rk_error+=(actual-source-adv)/4;bound+=gamma*(abs(a[0]*a[2])+abs(source)+abs(adv))/4
   require(abs(pd_error)+abs(rk_error)<=bound,'local REAL32 accounting exceeds conservative gamma24 envelope')
   rows.append({'step':step,'source_time_seconds':(step-1)*dt,'surface_QFX_integral_kg_m2':flux,'PBL_host_md_source_kg_m2':pbl_md,'PBL_total_pressure_source_kg_m2':pbl_dp,'PBL_source_minus_surface_kg_m2':pbl_md-flux,'pressure_weight_component_kg_m2':pbl_md-pbl_dp,'PBL_column_operator_component_kg_m2':pbl_dp-flux,'PD_actual_delta_mq_kg_m2':pd_delta,'PD_applied_source_kg_m2':pd_src,'PD_arithmetic_recorded_weight_residual_kg_m2':pd_error,'RK3_actual_delta_mq_kg_m2':rk_delta,'RK3_source_kg_m2':rk_src,'RK3_advective_integral_kg_m2':rk_adv,'RK3_arithmetic_recorded_weight_residual_kg_m2':rk_error,'conservative_local_binary32_envelope_kg_m2':bound})
  sums={k:sum(z[k] for z in rows) for k in rows[0] if k not in ['step','source_time_seconds']};R=base['whole_host_water_residual_kg_m2'];micro=base['sum_micro_native_md_residual_kg_m2'];prediction=sums['PD_actual_delta_mq_kg_m2']+sums['RK3_actual_delta_mq_kg_m2']+micro-base['E_kg_m2'];remainder=R-prediction
  require(abs(sums['surface_QFX_integral_kg_m2']-base['E_kg_m2'])<1e-6*base['E_kg_m2'],'surface time integral differs from ACLHF')
  require(abs(remainder)<sums['conservative_local_binary32_envelope_kg_m2'],'inventory links outside rounding envelope')
  result['host'][name]={'same_PR176_history_budget':base,'steps':rows,'sums':sums,'observed_host_residual_kg_m2':R,'reconstructed_residual_kg_m2':prediction,'unattributed_link_remainder_kg_m2':remainder,'PBL_to_PD_source_link_difference_kg_m2':sums['PD_applied_source_kg_m2']-sums['PBL_host_md_source_kg_m2'],'full_water_physical_approval':False,'full_energy_closed':False}
 parser=load(ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','raw_parser');_,current=parser.trace(read('host/capture/sw.raw'),'raw');require(current['SOURCE_TIME_SECONDS']['values'][0]==50 and max(current['SOURCE_QC']['values'])==0,'current host liquid-free scope changed');require(all(h.at('QCLOUD',6,k,j,i)==0 and h.at('QNCLOUD',6,k,j,i)==0 for k in range(59) for j in range(2) for i in range(2)),'current terminal not liquid free')
 positive=json.loads(read('positive/result.json'));lines=read('positive/command-02.stdout').decode().splitlines();final=None
 for i,line in enumerate(lines):
  if line.startswith('RETURN 1 '):final=[struct.unpack('!f',bytes.fromhex(x))[0] for x in lines[i+1].split()]
 require(final is not None and final[8]==positive['final_qc_kg_kg'] and final[36]==positive['final_eta_kg_dry_inverse'] and final[0]==positive['final_temperature_K'],'actual positive cloud final state differs')
 optical=json.loads(read('psd/moments-optics.json'));M0=positive['rho_call']*positive['final_eta_kg_dry_inverse'];M3=3*positive['rho_call']*positive['final_qc_kg_kg']/(4*math.pi*1000);require(M0==optical['M0'] and M3==optical['M3'],'PSD did not use actual final q eta rho');psds=[]
 for z in optical['PSDs']:
  s=z['shape'];lam=(M0*s*(s+1)*(s+2)/M3)**(1/3);M2=M0*s*(s+1)/lam**2;require(z['M0']==M0 and z['M3']==M3 and z['M2']==M2 and z['reff_um']==M3/M2*1e6,'PSD shape changed number or mass');checks={}
  for band,calcs in z['bands'].items():
   a=calcs['r1024s96'];fine=calcs['r2048s192'];change=max(abs(a[n]/fine[n]-1) for n in ['ext','sca','abs','sca_g']);require(change<.01,'fixed M0 M3 independent optics unresolved');checks[band]={'relative_refinement_change_max':change,'fine':fine}
  psds.append({'shape':s,'M0':M0,'M3':M3,'M2':M2,'reff_um':z['reff_um'],'independent_NIR':checks})
 result['PSD']={'current_host_source50_and_terminal60_liquid_absent':True,'nonzero_diagnostic_uses_separate_actual_UDM_final':True,'PSDs':psds,'reff16_over_reff8':psds[1]['reff_um']/psds[0]['reff_um'],'optical_path_g_m2':optical['optical_path_g_m2'],'full_LUT_PSD_definition_certified':False}
 flux={}
 for ph,mode in [('lw','LUT'),('sw','LUT'),('sw','NIR_Mie')]:
  data={};inputs={}
  for shape in [8,16]:
   tag=f'psd/{ph}-s{shape}-{mode}';_,data[shape]=parser.trace(read(tag+f'/{ph}.result'),'result');_,inputs[shape]=parser.trace(read(tag+'/input'),'input')
  require(set(inputs[8])==set(inputs[16]),'PSD input fields differ')
  for field in inputs[8]:
   if field!='REL':require(inputs[8][field]==inputs[16][field],'PSD changed fixed state '+field)
  for shape in [8,16]:
   row=next(z for z in optical['PSDs'] if z['shape']==shape);require(all(x==row['reff_um'] for x in inputs[shape]['REL']['values']),'wrong PSD radius passed to column');require(sum(inputs[shape]['LWP']['values'])==optical['optical_path_g_m2'],'fixed optical mass changed')
  for field in ['MASK','GAS_TAU','PRECIP_TAU','UPC','DNC','HRC']:require(data[8][field]==data[16][field],'PSD changed held component '+field)
  flux[ph+'-'+mode]={field:max(abs(a-b) for a,b in zip(data[8][field]['values'],data[16][field]['values'])) for field in ['UP','DN','HR','CLOUD_TAU']}
 result['fixed_mass_number_flux_difference']=flux
 result['decisions']={'host_residual_trace':'CLOSED_SCOPED_FIRST_SOURCE_GAP_AT_PBL_RETURN_BEFORE_PD_APPLICATION','PBL_QFX_physical_closure':'NOT_APPROVED_NO_SOURCE_RETAGGING','UDM_density_or_return_scaling':'REJECT_NOT_SUPPORTED','PSD_definition':'RETAIN_RESEARCH_GAMMA8_MAP_FROM_Q_ETA_M0_M3','Gamma16':'SENSITIVITY_BRACKET_NOT_SELECTED_AS_PRODUCTION','optical_shape_irrelevance':'REJECT_FOR_FIXED_MASS_NUMBER','production_radius_or_coefficients_changed':False,'full_energy':'OPEN'}
 return result
if __name__=='__main__':print(json.dumps(analyze(lambda n:gzip.decompress((B/'saved'/(n+'.gz')).read_bytes())),indent=2))
