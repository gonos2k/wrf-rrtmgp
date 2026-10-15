"""Replay actual host ledgers and independent optical diagnostics, using stdlib only."""
import gzip,hashlib,importlib.util,json,math,struct
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def load(path,name):
 spec=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m

def micro_records(data):
 out={}
 for line in data.decode().splitlines():
  w=line.split()
  if w and w[0] in ('MB_PRE','MB_POST'):
   key=(w[0],*map(int,w[1:5]));v=list(map(float,w[5:]));require(key not in out and len(v)==25 and all(math.isfinite(x) for x in v),'actual micro record structure');out[key]=v
 return out

class History:
 def __init__(self,index,payload):
  self.index=index;self.payload=payload;self.rows={r['variable']:r for r in index['records']};self.cache={}
  require(hashlib.sha256(payload).hexdigest()==index['payload_sha256'],'history payload differs')
 def values(self,n):
  if n not in self.cache:
   row=self.rows[n];part=self.payload[row['offset']:row['offset']+row['bytes']];require(hashlib.sha256(part).hexdigest()==row['sha256'],'history variable differs '+n)
   code={'<f4':'f','<f8':'d','<i4':'i','<i8':'q'}.get(row['dtype'])
   self.cache[n]=struct.unpack('<'+str(row['bytes']//struct.calcsize(code))+code,part) if code else part
  return self.cache[n]
 def at(self,n,*indices):
  shape=self.rows[n]['shape'];require(len(shape)==len(indices),'history rank '+n);idx=0
  for dim,i in zip(shape,indices):require(0<=i<dim,'history index');idx=idx*dim+i
  return self.values(n)[idx]
 def mass(self,t,k,j,i):
  mu=self.at('MU',t,j,i)+self.at('MUB',t,j,i)
  return -(self.at('C1H',t,k)*mu+self.at('C2H',t,k))*self.at('DNW',t,k)/9.810000419616699

def water_inventory(h,t):
 total=area=0.
 for j in range(2):
  for i in range(2):
   A=h.at('AREA2D',t,j,i);area+=A
   for k in range(59):total+=A*h.mass(t,k,j,i)*sum(h.at(n,t,k,j,i) for n in ('QVAPOR','QCLOUD','QRAIN'))
 return total/area

def check_native_mass(row):
 expected=-(row[22]*row[21]+row[23])*row[24]/row[14]
 require(abs(row[0]-expected)<=8*2**-23*max(abs(row[0]),abs(expected)),'pressure dry mass replaced by another carrier')

def host_budget(h,records,dt):
 steps=[];thermal=throughput=0.;up=down=0;all_rho_res=[]
 for step in range(1,60//dt+1):
  dW=dV=P=heat=heat_abs=0.;areas=0.;f0=fp=0;ratios=[]
  hist_time=step*dt//10
  for j in range(1,3):
   for i in range(1,3):
    a=records['MB_PRE',step,i,j,1];z=records['MB_POST',step,i,j,1];A=a[13];areas+=A;P+=A*(z[10]-a[10])
    require(abs(a[20]-a[18]*2501000.)<=3e-6*max(abs(a[20]),1.),'LH/QFX conversion changed')
    for k in range(1,60):
     a=records['MB_PRE',step,i,j,k];z=records['MB_POST',step,i,j,k];require(a[:3]==z[:3] and a[13]==z[13],'micro carrier changed within call')
     check_native_mass(a)
     delta=sum(z[4:7])-sum(a[4:7]);dW+=A*a[0]*delta;dV+=A*a[1]*a[2]*delta;ratios.append(a[1]*a[2]/a[0])
     cp=a[15]*(1-a[4])+a[16]*a[4];lv=a[17]-(4190-a[16])*(a[3]-273.15)
     heat+=A*a[0]*(cp*(z[3]-a[3])+lv*(z[4]-a[4]));heat_abs+=abs(A*a[0]*lv*(z[4]-a[4]))
     if step>1 and z[6]>0.:
      up+=a[11]==0. and z[11]>0.;down+=a[11]>0. and z[11]==0.
     f0+=z[11]==0. and z[6]>0.;fp+=z[11]>0. and z[6]>0.
  row={'clock_start_s':(step-1)*dt,'clock_end_s':step*dt,'delta_water_native_md_kg_m2':dW/areas,'delta_water_rhoDz_kg_m2':dV/areas,'micro_precip_kg_m2':P/areas,'micro_residual_native_md_kg_m2':(dW+P)/areas,'micro_residual_rhoDz_kg_m2':(dV+P)/areas,'carrier_difference_term_kg_m2':(dW-dV)/areas,'native_thermal_rule_residual_J_m2':heat/areas,'latent_throughput_J_m2':heat_abs/areas,'rhoDz_over_md_min':min(ratios),'rhoDz_over_md_max':max(ratios),'CF0_rain_cells':int(f0),'positive_CF_rain_cells':int(fp)}
  steps.append(row);thermal+=row['native_thermal_rule_residual_J_m2'];throughput+=row['latent_throughput_J_m2'];all_rho_res.append(row['micro_residual_rhoDz_kg_m2'])
 initial=water_inventory(h,0);final=water_inventory(h,6)
 def area_mean(n,t):
  return sum(h.at(n,t,j,i)*h.at('AREA2D',t,j,i) for j in range(2) for i in range(2))/sum(h.at('AREA2D',t,j,i) for j in range(2) for i in range(2))
 precip=sum(area_mean(n,6)-area_mean(n,0) for n in ('RAINC','RAINNC'));evap=(area_mean('ACLHF',6)-area_mean('ACLHF',0))/2501000.;R=final-initial-evap+precip;micro=sum(x['micro_residual_native_md_kg_m2'] for x in steps)
 radiation=sum(sign*(area_mean(n,6)-area_mean(n,0)) for n,sign in [('ACSWDNT',1),('ACSWUPT',-1),('ACSWDNB',-1),('ACSWUPB',1),('ACLWDNT',1),('ACLWUPT',-1),('ACLWDNB',-1),('ACLWUPB',1)])
 top_w=max(abs(h.at('W',t,59,j,i)) for t in range(7) for j in range(2) for i in range(2))
 return {'dt_seconds':dt,'physical_top_W_max_m_s':top_w,'relative_eta_boundary_flux_assumption':'zero imposed ww boundary, not zero physical W','W_initial_kg_m2':initial,'W_final_kg_m2':final,'P_kg_m2':precip,'E_kg_m2':evap,'whole_host_water_residual_kg_m2':R,'sum_micro_native_md_residual_kg_m2':micro,'sum_micro_rhoDz_residual_kg_m2':sum(all_rho_res),'remaining_nonmicro_or_time_split_kg_m2':R-micro,'CF0_to_positive_rain_cells_excluding_initialization':int(up),'positive_to_CF0_rain_cells_excluding_initialization':int(down),'native_thermal_rule_residual_J_m2':thermal,'native_latent_throughput_J_m2':throughput,'surface_sensible_J_m2':area_mean('ACHFX',6)-area_mean('ACHFX',0),'surface_latent_J_m2':area_mean('ACLHF',6)-area_mean('ACLHF',0),'TOA_minus_surface_radiative_net_J_m2':radiation,'radiative_net_is_exact_native_column_energy_source':False,'full_energy_closed':False,'steps':steps}

def rk_forcing(data):
 rows={}
 for line in data.decode().splitlines():
  w=line.split()
  if w and w[0] in ('RF_PRE','RF_POST'):
   key=(w[0],*map(int,w[1:6]));values=list(map(float,w[6:]));require(key not in rows and len(values)==12 and key[2]==1,'RK forcing record');rows[key]=values
 total=0.;count=0
 for key,a in rows.items():
  if key[0]!='RF_PRE':continue
  z=rows['RF_POST',*key[1:]];require(a[1:]==z[1:],'forcing probe changed state')
  pi=(a[3]/1.e5)**(a[9]/a[8]);virtual=1+a[10]/a[9]*a[5]
  total+=(-a[2]/a[7])*(z[0]-a[0])*a[8]*pi/virtual*a[6]*a[11];count+=1
 return {'first_RK_cell_records':count,'additional_forcing_temperature_equivalent_J_m2':total/(4*16000000.),'includes_Rayleigh_and_explicit_diffusion':True,'exact_total_energy_source':False}

def analyze(read):
 result={'production_accepted':False,'physical_gates_closed':False,'host':{}}
 for dt,label,index in ((10,'on_dt10',2),(5,'on_dt5',3)):
  h=History(json.loads(read('host/'+label+'.json')),read('host/'+label+'.bin'));rec=micro_records(read(f'host/command-{index:02d}.stdout'));require(len(rec)==2*(60//dt)*4*59,'actual cell/step coverage differs');result['host'][label]=host_budget(h,rec,dt);result['host'][label]['rk_forcing']=rk_forcing(read(f'host/command-{index:02d}.stdout'));require(result['host'][label]['rk_forcing']['first_RK_cell_records']==(60//dt)*4*59,'RK source coverage differs')
 switch=json.loads(read('switch/result.json'));require(switch['actual_UDM_calls']==36 and switch['CF_forced'] is False,'CF probe changed scope')
 pairs=[]
 for dt in (.01,10.):
  for c in (1,4):
   a=next(x for x in switch['rows'] if x['case']==c and x['dt_seconds']==dt);b=next(x for x in switch['rows'] if x['case']==c+1 and x['dt_seconds']==dt)
   require(a['footprint']==1. and b['footprint']==.5,'actual CF boundary not crossed')
   ratio=b['grid_nr_self_collection_rate']/a['grid_nr_self_collection_rate'];require(math.isclose(ratio,2.,rel_tol=2e-6),'actual nonlinear rain rate differs')
   require(a['rain_inverse_slope']==b['rain_inverse_slope'] and a['grid_rain_evaporation_rate']==b['grid_rain_evaporation_rate'],'linear vs nonlinear rain process separation differs')
   pairs.append({'dt_seconds':dt,'density_case':1 if c==1 else 2,'grid_rain_self_collection_ratio':ratio,'rain_slope_and_evaporation_rate_equal':True})
 result['actual_CF_boundary_pairs']=pairs
 mie=json.loads(read('mie/result.json'));checks=[]
 for row in mie['records']:
  fine=row['calculations']['r2048_s96']['Planck'];coarse=row['calculations']['r1024_s48']['Planck'];lut=row['LUT'];require(all(fine[k]>=0. for k in ('ext','sca','abs','sca_g')) and fine['sca']<=fine['ext'] and 0<=fine['g']<=1.,'unphysical Mie moments')
  convergence=max(abs(fine[k]-coarse[k])/max(abs(fine[k]),1e-30) for k in ('ext','sca','abs','sca_g'));require(convergence<.01,'independent Mie not numerically resolved')
  checks.append({'phase':row['phase'],'band':row['band'],'reff_um':row['reff_um'],'relative_refinement_change_max':convergence,'relative_Mie_minus_LUT':{k:(fine[k]-lut[k])/lut[k] for k in ('ext','sca','abs','sca_g')},'g_difference':fine['g']-lut['g']})
 result['independent_Mie']=checks
 parser=load(ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','p2_trace');flux={}
 for phase in ('lw','sw'):
  _,a=parser.trace(read(f'flux/{phase}-baseline/{phase}.result'),'result');_,b=parser.trace(read(f'flux/{phase}-mie_band6/{phase}.result'),'result');_,ai=parser.trace(read(f'flux/{phase}-baseline/input'),'input');_,bi=parser.trace(read(f'flux/{phase}-mie_band6/input'),'input');require(ai==bi,'independent coefficient comparison changed state')
  for n in ('MASK','GAS_TAU','PRECIP_TAU','UPC','DNC','HRC'):require(a[n]==b[n],'independent optical probe changed held component '+n)
  metrics={}
  for n in ('UP','DN','HR','CLOUD_TAU','PREPARED_TAU'):
   d=[y-x for x,y in zip(a[n]['values'],b[n]['values'])];idx=max(range(len(d)),key=lambda k:abs(d[k]));metrics[n]={'max_abs':abs(d[idx]),'index_from_1':idx+1,'signed_at_max':d[idx],'surface_delta':d[0] if n in ('UP','DN') else None}
  flux[phase]=metrics

 _,original=parser.trace(read('retained_PR174/lw.raw'),'raw');moments=json.loads(read('retained_PR174/moments.json'))['cases'][0]['records'];mass=original['DRY_LAYER_MASS_KG_M2']['values'];q=original['SOURCE_QC']['values'];total=sum(x*y for x,y in zip(mass,q));outside=sum(mass[i]*q[i] for i,x in enumerate(moments) if x.get('reff_um',0)>21.5)
 result['Gamma_outside_upper_LUT_liquid_path_fraction']=outside/total
 result['Gamma_LUT_outside_levels']=[x['native_level'] for x in moments if x.get('reff_um',0)>21.5]
 for phase in ('lw','sw'):
  _,native=parser.trace(read(f'retained_PR174/{phase}-native.input'),'input');_,gamma=parser.trace(read(f'retained_PR174/{phase}-gamma_v01.input'),'input');_,subset=parser.trace(read(f'flux/{phase}-baseline/input'),'input');eligible=json.loads(read(f'flux/{phase}.scope.json'))['eligible_native_levels']
  for field in native:
   if field!='REL':require(subset[field]==native[field],'PSD subset changed another input '+field)
  for i,x in enumerate(subset['REL']['values']):
   require(x==(gamma if i+1 in eligible else native)['REL']['values'][i],'excluded optical layer changed its native radius')
  require(all(9.5<=subset['REL']['values'][i-1]<=20.5 and i<=58 for i in eligible),'PSD subset scope changed')
 result['independent_band6_flux_sensitivity_scoped']=flux
 result['decisions']={'population_policy2':'RETAIN_RESEARCH_ONLY_NO_POLICY3','original_manufactured_host_budget':'NOT_APPROVED_NATIVE_MD_AND_RHODZ_CARRIERS_DIFFER','energy':'NATIVE_THERMAL_RULE_OBSERVED_FULL_HOST_ENERGY_OPEN','Gamma_candidate':'RETAIN_CONDITIONAL_298K_SPHERICAL_DIAGNOSTIC','Gamma_fixed_LUT_equivalence':'NOT_CERTIFIED_SOME_ABSORPTION_SCREENS_FAIL','production_radius_changed':False}
 return result
