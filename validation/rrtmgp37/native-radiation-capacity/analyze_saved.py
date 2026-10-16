"""One explicit thermodynamic completion and actual positive-cloud optical consumption.

All comparisons use per-layer flux convergence. This is a research candidate,
not a claim that WRF dynamics and all its physics share one thermodynamic potential.
"""
from pathlib import Path
import importlib.util,json,math,collections,struct
r=Path(__file__).resolve().parents[3];spec=importlib.util.spec_from_file_location('old',r/'validation/rrtmgp37/applied-radiation-energy/analyze_saved.py');old=importlib.util.module_from_spec(spec);spec.loader.exec_module(old);f32=old.f32
spec=importlib.util.spec_from_file_location('parser',r/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py');parser=importlib.util.module_from_spec(spec);spec.loader.exec_module(parser)
def capacity_records(data):
 r=old.records(data);ec={};counter=collections.defaultdict(int)
 for line in data.decode().splitlines():
  w=line.split()
  if w and w[0]=='EC':
   phase=w[1];c,k=map(int,w[2:4]);v=list(map(float,w[4:]));
   if k==1:counter[phase]+=1
   ec[phase,counter[phase],c,k]=v
 return r,ec

def host_energy(data,interval,use_capacity):
 r,ec=capacity_records(data);raw=dict(r['EA_RAW']);ei={};C={};err=0.;perlayer=[]
 if len(raw)!=6*4*59:raise ValueError('host record coverage')
 for phase in ['LW','SW']:
  for (call,c,k),v in r['EI_'+phase]:
   step=1+(call-1)//4*interval;idx=(call-1)%4;i=idx%2+1;j=idx//2+1;ei[phase,step,i,j,k]=v
   Q=v[2]-v[4]-v[3]+v[5]
   if k<=59:
    a=raw[step,1,i,j,k];mapped=f32(f32(f32(v[6]*86400.)/86400.)/a[3])
    if phase=='SW':mapped=f32(f32(mapped+a[0])-a[0])
    cap,qv,md=ec[phase,call,c,k];model=md*1004.5*(1+float(f32(f32(461.6)/f32(287.)))*qv)
    if cap!=model:raise ValueError('constant kappa capacity changed')
    C[phase,step,i,j,k]=cap
    denom=cap if use_capacity else (v[0]-v[1])/v[7]*v[8]
   else:denom=(v[0]-v[1])/v[7]*v[8]
   res=denom*v[6]-Q
   if abs(res)>1e-10:raise ValueError('layer flux capacity closure')
   if k<=59 and mapped!=a[0 if phase=='LW' else 1]:raise ValueError('candidate heat does not reach theta adapter')
   if k<=59:perlayer.append({'phase':phase,'step':step,'i':i,'j':j,'k':k,'C_J_m2_K':cap,'Q_W_m2':Q,'heat_K_s':v[6],'residual_W_m2':res})
   err=max(err,abs(res))
 # Accepted actual RK3 adds, with current THM conversion replayed at recorded state.
 rows=collections.defaultdict(lambda:collections.defaultdict(float));dur=collections.defaultdict(float)
 if len(r['EA_APPLY'])!=len(r['EA_ADD']):raise ValueError('application coverage')
 for (key,v),(ak,b) in zip(r['EA_APPLY'],r['EA_ADD']):
  step,rk,it,i,j,k=key
  if ak!=(it,i,j,k) or v[0]!=b[2] or v[3]!=b[4] or v[4]!=b[3]:raise ValueError('source add pairing')
  if f32(b[0]+f32(f32(b[3]*b[4])*b[2]))!=b[1]:raise ValueError('actual RK add arithmetic')
  if rk!=3:continue
  a=raw[step,1,i,j,k];fac=f32(1.+f32(a[10]*a[6]));mass=a[4]
  if v[1]!=f32(fac*f32(mass*a[2])):raise ValueError('THM radiation component differs')
  Tdot=v[1]/mass/fac*a[3];source=1+(step-1)//interval*interval
  cap=C['LW',source,i,j,k];
  if cap!=C['SW',source,i,j,k]:raise ValueError('phase capacity differs')
  E=rows[step,i,j];E['call_capacity_applied_J_m2']+=cap*Tdot*v[3]
  md=-mass*a[5]/a[8];currentC=md*a[9]*(1+a[10]*a[6]);E['current_model_capacity_applied_J_m2']+=currentC*Tdot*v[3]
  for ph in ['LW','SW']:
   vv=ei[ph,source,i,j,k];Q=vv[2]-vv[4]-vv[3]+vv[5];E['flux_convergence_J_m2']+=Q*v[3]
  if k==1:dur[step,i,j]+=v[3]
 for key,dt in dur.items():
  if abs(dt-10)>1e-6:raise ValueError('accepted physical duration')
 summary={n:math.fsum(z[n] for z in rows.values())/4 for n in ['call_capacity_applied_J_m2','current_model_capacity_applied_J_m2','flux_convergence_J_m2']}
 summary['call_capacity_minus_flux_J_m2']=summary['call_capacity_applied_J_m2']-summary['flux_convergence_J_m2'];summary['current_model_capacity_minus_flux_J_m2']=summary['current_model_capacity_applied_J_m2']-summary['flux_convergence_J_m2']
 return {'max_abs_layer_flux_capacity_residual_W_m2':err,'first_column_layers_each_call':[z for z in perlayer if z['i']==1 and z['j']==1], 'checked_native_layer_count':len(perlayer),'summary':summary,'actual_application_rows':[{'step':k[0],'i':k[1],'j':k[2],**dict(v)} for k,v in sorted(rows.items())],'whole_energy_approved':False}

def traces(data,ph):return parser.trace(data,ph)
def analyze(read):
 out={'production_accepted':False,'physics_gates_closed':False}
 for n,idx,interval,enabled in [('legacy',1,1,False),('capacity',2,1,True),('held30s',3,3,True)]:out[n]=host_energy(read(f'host/command-{idx:02d}.stdout'),interval,enabled)
 for ph in ['lw','sw']:
  _,a=traces(read(f'host/legacy/capture/{ph}.input'),'input');_,c=traces(read(f'host/capacity/capture/{ph}.input'),'input');assert a==c
  _,a=traces(read(f'host/legacy/capture/{ph}.result'),'result');_,c=traces(read(f'host/capacity/capture/{ph}.result'),'result')
  for field in ['UP','DN','UPC','DNC','UP_WP','DN_WP','GAS_TAU','MASK']:
   if field in a:assert a[field]==c[field],field
  # Extension untouched; clear/all sky use identical candidate denominator.
  for field in ['HR','HRC']:assert a[field]['values'][59:]==c[field]['values'][59:]
  C=c['NATIVE_CAPACITY_J_M2_K']['values'];up=c['UPC']['values'];dn=c['DNC']['values'];hrc=c['HRC']['values'];clear=[]
  for k,cap in enumerate(C):
   Q=up[k]-dn[k]-up[k+1]+dn[k+1];res=cap*hrc[k]/86400.-Q
   bound=8*2**-24*(abs(up[k])+abs(dn[k])+abs(up[k+1])+abs(dn[k+1])+abs(cap*hrc[k]/86400.))
   if abs(res)>bound:raise ValueError('clear heating capacity mismatch')
   clear.append(res)
  out[ph+'_fixed_first_call']={'input_identical':True,'allsky_clear_flux_and_mask_unchanged':True,'extension_HR_HRC_unchanged':True,'max_abs_clear_closure_after_REAL32_flux_rounding_W_m2':max(map(abs,clear))}
 # Source time10 actual positive cloud, q eta rho -> declared Gamma8 local M0/M2/M3 -> consumed REL.
 cloud={}
 for name in ['cloud_native','cloud_gamma8']:
  cloud[name]={}
  for ph in ['lw','sw']:
   _,raw=traces(read(f'host/{name}/capture/{ph}.raw'),'raw');_,inp=traces(read(f'host/{name}/capture/{ph}.input'),'input');_,res=traces(read(f'host/{name}/capture/{ph}.result'),'result');assert raw['SOURCE_TIME_SECONDS']['values']==[10.]
   table=json.loads(read(f'coefficients/{ph}.json'));optical_error=0.;path_error=0.
   rho=raw['SOURCE_DRY_RHO']['values'];qc=raw['SOURCE_QC']['values'];eta=raw['SOURCE_QNC']['values'];cf=raw['CF']['values'];rel=inp['REL']['values'];rows=[]
   for k,(rh,q,n,f) in enumerate(zip(rho,qc,eta,cf)):
    if q>0 and n>0:
     foot=f if f>0 else 1.;M0=rh*n/foot;M3=3*rh*q/(4*math.pi*1000*foot);lam=(M0*8*9*10/M3)**(1/3);M2=M0*8*9/lam**2;reff=M3/M2*1e6
     if name=='cloud_gamma8' and f32(reff)!=rel[k]:raise ValueError('actual Gamma8 consumed radius mismatch')
     md=inp['NATIVE_DRY_LAYER_MASS_KG_M2']['values'][k];path=1000*md*q/foot;actual_path=inp['LWP']['values'][k]
     path_error=max(path_error,abs(actual_path-path))
     if not math.isclose(actual_path,path,rel_tol=5e-7,abs_tol=1e-10):raise ValueError('same-time cloud path differs')
     rad=rel[k];lo=table['radliq_lwr'];hi=table['radliq_upr'];ngrid=len(table['arrays']['extliq'][0]);step=(hi-lo)/(ngrid-1);rad=max(lo,min(hi,rad));ii=min(math.floor((rad-lo)/step),ngrid-2);fraction=(rad-lo)/step-ii
     for band in range(len(table['arrays']['extliq'])):
      def lut(name):
       v=table['arrays'][name][band];return v[ii]+fraction*(v[ii+1]-v[ii])
      tau=actual_path*lut('extliq');nb=inp['LWP']['shape'][1];index=band*nb+k
      if ph=='sw':
       expected=f32(tau);observed=inp['RAW_CLOUD_TAU']['values'][index]
      else:
       expected=tau-tau*lut('ssaliq')+res['PRECIP_TAU']['values'][index];observed=res['CLOUD_TAU']['values'][index]
      optical_error=max(optical_error,abs(expected-observed))
      if not math.isclose(expected,observed,rel_tol=3e-7,abs_tol=1e-12):raise ValueError('Gamma radius not consumed by exact liquid LUT')
     rows.append({'native_layer_1based':k+1,'qc':q,'eta':n,'rho_d':rh,'footprint':foot,'M0_local':M0,'M2_local':M2,'M3_local':M3,'reff_Gamma8_um':reff,'REL_consumed_um':rel[k]})
   assert rows and any(z>0 for z in res['CLOUD_TAU']['values'])
   cloud[name][ph]={'source_time_seconds':10,'positive_cloud_rows':rows,'max_abs_cloud_path_reconstruction_g_m2':path_error,'max_abs_LUT_optical_reconstruction_error':optical_error,'CLOUD_TAU_max':max(res['CLOUD_TAU']['values']),'HR_abs_max_K_day':max(map(abs,res['HR']['values']))}
 out['cloud']=cloud
 # Prior fluxes: no solver rerun, no column-total rescaling. Same Q at each layer.
 rr=old.records(read('prior178/host/command-02.stdout'));host=dict(rr['EA_RAW']);count=0;maxres=0.;old_model_gap=[];fixed_rows=[]
 for ph in ['LW','SW']:
  for (call,c,k),v in rr['EI_'+ph]:
   if k>59:continue
   step=(call-1)//4+1;idx=(call-1)%4;i=idx%2+1;j=idx//2+1;a=host[step,1,i,j,k]
   md=-a[4]*a[5]/a[8];C=md*a[9]*(1+a[10]*a[6]);Q=v[2]-v[4]-v[3]+v[5];rate=Q/C;res=C*rate-Q
   count+=1;maxres=max(maxres,abs(res));old_model_gap.append((C*v[6]-Q)*10/4)
   if i==1 and j==1:fixed_rows.append({'phase':ph,'step':step,'k':k,'Q_W_m2':Q,'C_J_m2_K':C,'rate_K_s':rate,'residual_W_m2':res})
 out['same_PR178_flux']={'layers_checked':count,'first_column_rows':fixed_rows,'max_abs_layer_residual_W_m2':maxres,'baseline_constant_kappa_ledger_minus_flux_J_m2':math.fsum(old_model_gap),'not_a_new_RTE_run':True}
 out['decision']={'native_capacity':'ADOPT_EXPLICIT_RESEARCH_CONSTANT_KAPPA_CALORIC_COMPLETION','definition':'md*cpd*(1+(Rv/Rd)*qv); fixed composition; condensate heat capacities neglected in this approximation','unique_original_WRF_thermodynamics_proved':False,'all_WRF_physics_thermodynamically_consistent':False,'candidate_in_production':False,'Gamma8_consumer':'ACTUAL_POSITIVE_CLOUD_SOURCE10_PRIVATE_OPTICAL_ADAPTER_CONNECTED','Gamma8_observation_or_original_LUT_PSD_approval':False,'held_theta_policy_changed':False,'whole_energy':'OPEN','PBL_host_water_and_reference_FAILs':'UNCHANGED'}
 return out

if __name__=='__main__':
 import gzip
 B=Path(__file__).resolve().parent
 def read(n):
  p=B.parent/'applied-radiation-energy/saved'/(n[len('prior178/'):]+'.gz') if n.startswith('prior178/') else B/'saved'/(n+'.gz')
  return gzip.decompress(p.read_bytes())
 print(json.dumps(analyze(read),indent=2))
