"""Same-state signed endpoint decomposition. Pure stdlib retained-evidence replay."""
import importlib.util,json,math,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3]
s=importlib.util.spec_from_file_location('endpoint_trace',ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py');parser=importlib.util.module_from_spec(s);s.loader.exec_module(parser)
CASES=('night_peak_lw','day_peak_lw','day_peak_sw')
MODES=('A','B_coarse','B','C_coarse','C')
MOMENTS=('ext','sca','abs','sca_g')
def require(ok,msg):
 if not ok:raise ValueError(msg)
def close(a,b,msg,tol=2e-12):
 require(abs(a-b)<=tol*max(1.,abs(a),abs(b)),msg)
def summary(values,shape):
 i=max(range(len(values)),key=lambda j:abs(values[j]));return {'max_abs':abs(values[i]),'signed_at_max':values[i],'flat_index_0based':i,'shape':list(shape),'position_1based':i+1}
def decomposition(a,b,c,shape):
 d=[y-x for x,y in zip(a,b)];r=[z-y for y,z in zip(b,c)];t=[z-x for x,z in zip(a,c)]
 err=max(abs(x+y-z) for x,y,z in zip(d,r,t));require(err<=1e-10,'signed decomposition fails')
 return {'definition_B_minus_A':summary(d,shape),'radius_C_minus_B':summary(r,shape),'total_C_minus_A':summary(t,shape),'identity_max_abs':err,'signed_definition':d,'signed_radius':r,'signed_total':t}
def parse_coeff(data):
 lines=data.decode().splitlines();ph,nl,nb=lines[0].split();nl=int(nl);nb=int(nb);mask=list(map(int,lines[1].split()))
 require(len(mask)==nl and set(mask)<={0,1},'coefficient mask')
 rows=[list(map(float,l.split())) for l in lines[2:] if l.strip()]
 require(len(rows)==nl*nb and all(len(r)==4 for r in rows),'coefficient dimensions')
 require(all(math.isfinite(v) and v>=0 for r in rows for v in r),'coefficient finite/positive')
 return ph,nl,nb,mask,rows

def analyze(read,prior,plan):
 mie=json.loads(read('mie/result.json'));require(mie['plan_sha256']==hashlib.sha256(read('executed/plan.json')).hexdigest(),'predeclared plan binding')
 require(mie['water_sha256']==hashlib.sha256(read('water/Segelstein.yml')).hexdigest(),'refractive index binding')
 require(json.loads(read('mie/plan.json'))==plan,'saved/current plan differs')
 numerical=plan['numerical_criteria'];records=mie['records'];unresolved=[];refinement={}
 require(len(records)==152,'independent radius/band record coverage')
 for rec in records:
  grids=rec['grids'];require(len(grids)>=2,'missing numerical refinement')
  for v in grids:
   require(all(v[k]>=0 and math.isfinite(v[k]) for k in MOMENTS),'nonphysical independent moment')
   close(v['ext'],v['sca']+v['abs'],'independent energy moments')
   close(v['g'],v['sca_g']/v['sca'],'independent asymmetry moment')
  a,b=grids[-2:]
  ok=all(abs(a[k]-b[k])<=numerical['coefficient_relative']*max(abs(b[k]),numerical['coefficient_absolute_floor_m2_g']) for k in MOMENTS) and abs(a['g']-b['g'])<=numerical['g_absolute']
  require(ok==rec['converged'],'coefficient convergence classification')
  refinement[str((b['nr'],b['ns']))]=refinement.get(str((b['nr'],b['ns'])),0)+1
  if not ok:unresolved.append({'phase':rec['phase'],'band':rec['band'],'reff_um':rec['reff_um'],'relative_change':{k:abs(a[k]-b[k])/max(abs(b[k]),1e-8) for k in MOMENTS}})
 require(mie['all_coefficients_converged']==(not unresolved),'campaign convergence flag')
 results={};transport_ok=True
 for case in CASES:
  ph=case.rsplit('_',1)[1];nb=16 if ph=='lw' else 14
  original={k:parser.trace(prior(case+'/'+k),k)[1] for k in ('input','result','raw')};inp=original['input'];base=original['result'];raw=original['raw'];nl=inp['REL']['shape'][1]
  require(raw['SOURCE_TIME_SECONDS']['values']==[54300. if case.startswith('night') else 65100.],'source time')
  require(raw['RRTMGP_RESEARCH_POLICIES']['values']==[1.,1.],'source policy')
  selected=[k for k,r in enumerate(inp['REL']['values']) if r>21.5 and inp['LWP']['values'][k]>0]
  for k,q in enumerate(raw['SOURCE_QC']['values']):
   if q<=0:continue
   rho=raw['SOURCE_DRY_RHO']['values'][k];eta=raw['SOURCE_QNC']['values'][k];f=inp['CF']['values'][k] or 1.
   M0=rho*eta/f;M3=3*rho*q/(4*math.pi*1000*f);lam=(M0*720/M3)**(1/3);M2=M0*72/lam**2
   require(parser.f32(M3/M2*1e6)==inp['REL']['values'][k],'same-time Gamma8 final moment connection')
  require(all(inp[n]['values'][k]==0 for n in ['IWP','SWP'] for k in selected),'selected non-liquid unsupported')
  require(selected==([0,22] if case.startswith('night') else [0,1,22]),'selected actual layers')
  variants={};inputs={};coefficients={};layer_rows={};optics_moments={}
  for mode in MODES:
   name=case+'_'+mode;ar=parser.trace(read(name+'/'+ph+'.input'),'input')[1];res=parser.trace(read(name+'/'+ph+'.result'),'result')[1]
   require(read(name+'/input.dat')==prior(case+'/input.dat'),'physical caller input changed')
   for field,v in inp.items():
    if field in ('RAW_CLOUD_TAU','RAW_NATIVE_CLOUD_TAU'):continue # selected derived liquid extinction
    if field=='EMIS':require(len(set(v['values']))==1 and ar[field]['values']==[v['values'][0]],'grey emissivity')
    else:require(ar[field]==v,'physical input changed '+field)
   for field in ('UPC','DNC','HRC','GAS_COL_DRY','GAS_TAU','GAS_TAU_RAW','GAS_SSA','GAS_G','VMR_N2','MASK','PRECIP_TAU','PRECIP_SSA','PRECIP_G','NATIVE_CAPACITY_J_M2_K','RL_USED','DI_USED','DS_USED'):
    if field in base:require(res[field]==base[field],'unselected control changed '+field)
   if mode=='A':
    for field,v in base.items():
     if not field.startswith('WRF_'):require(res[field]==v,'A fails original capture '+field)
   cph,cnl,cnb,mask,coef=parse_coeff(read(name+'/optics.dat'));require((cph,cnl,cnb)==(ph.upper(),nl,nb),'optics layout')
   require(mask==[int(k in selected and mode!='A') for k in range(nl)],'unselected optical coefficient overwrite')
   for b in range(nb):
    for k in range(nl):
     c=coef[b*nl+k]
     if not mask[k]:require(c==[0.,0.,0.,0.],'unselected coefficient nonzero');continue
     radius=21.5 if mode.startswith('B') else inp['REL']['values'][k]
     rec=next(r for r in records if r['phase']==ph and r['band']==b+1 and r['reff_um']==radius)
     v=rec['grids'][-2 if mode.endswith('coarse') else -1]
     require(c==[v[m] for m in MOMENTS],'radius/definition mapping differs')
   variants[mode]=res;inputs[mode]=ar;coefficients[mode]=coef
  # Verify raw selected moments and the one delta scale, plus untouched layers.
  for mode in MODES:
   res=variants[mode];a=variants['A'];coef=coefficients[mode];moment_rows=[]
   for k in range(nl):
    for b in range(nb):
     idx=b*nl+k
     rawname='ENDPOINT_NATIVE_RAW_LIQUID_'+('ABS_TAU' if ph=='lw' else 'EXT_TAU')
     if k not in selected or mode=='A':
      if k not in selected:
       for field in [rawname,'CLOUD_TAU','CLOUD_SSA','CLOUD_G','PREPARED_TAU','PREPARED_SSA','PREPARED_G']:
        if field in res:require(res[field]['values'][idx]==a[field]['values'][idx],'unselected liquid optics changed '+field)
      continue
     ext,sca,absorp,sg=coef[idx];path=inp['LWP']['values'][k];tau=path*ext;ssa=sca/ext;g=sg/sca
     close(res[rawname]['values'][idx],path*(absorp if ph=='lw' else ext),'raw liquid optical depth')
     if ph=='sw':
      close(res['ENDPOINT_NATIVE_RAW_LIQUID_SSA']['values'][idx],ssa,'raw SSA')
      close(res['ENDPOINT_NATIVE_RAW_LIQUID_G']['values'][idx],g,'raw g')
      d=1-ssa*g*g;td=tau*d;sd=ssa*(1-g*g)/d;gd=g/(1+g)
      pt=res['PRECIP_TAU']['values'][idx];ps=res['PRECIP_SSA']['values'][idx];pg=res['PRECIP_G']['values'][idx]
      total=td+pt;sct=td*sd+pt*ps;sgt=td*sd*gd+pt*ps*pg
      close(res['CLOUD_TAU']['values'][idx],total,'SW exactly one delta scaling')
      close(res['CLOUD_SSA']['values'][idx],sct/total,'SW scaled mixture SSA')
      close(res['CLOUD_G']['values'][idx],sgt/sct,'SW scaled mixture g')
     else:
      pt=res['PRECIP_TAU']['values'][idx];close(res['CLOUD_TAU']['values'][idx],path*absorp+pt,'LW absorption plus preserved precipitation')
     moment_rows.append({'native_layer':k+1,'band':b+1,'raw_path_g_m2':path,'ext_tau':tau,'sca_tau':path*sca,'abs_tau':path*absorp,'sca_g_tau':path*sg})
   layer_rows[mode]=moment_rows
   # Uniform rain/clear-warm component is untouched for these upper captures.
   for field in a:
    if field.startswith(('UNIFORM_','ENDPOINT_UNIFORM_')):require(res[field]==a[field],'uniform component changed')
  # Signed raw optical-moment decomposition, layer/band order retained.
  for m in MOMENTS:
   aa=[];bb=[];cc=[]
   for k in selected:
    for b in range(nb):
     idx=b*nl+k;path=inp['LWP']['values'][k]
     if ph=='sw':
      tau=variants['A']['ENDPOINT_NATIVE_RAW_LIQUID_EXT_TAU']['values'][idx];ssa=variants['A']['ENDPOINT_NATIVE_RAW_LIQUID_SSA']['values'][idx];g=variants['A']['ENDPOINT_NATIVE_RAW_LIQUID_G']['values'][idx]
      val={'ext':tau,'sca':tau*ssa,'abs':tau*(1-ssa),'sca_g':tau*ssa*g}[m]
     else:
      # Original raw LW only exposes absorption. Other raw LUT moments use pinned endpoint table.
      table=json.loads(prior('coefficients/lw'))['arrays'];e=table['extliq'][b][-1];s=table['ssaliq'][b][-1];g=table['asyliq'][b][-1]
      val=path*{'ext':e,'sca':e*s,'abs':e*(1-s),'sca_g':e*s*g}[m]
      if m=='abs':close(val,variants['A']['ENDPOINT_NATIVE_RAW_LIQUID_ABS_TAU']['values'][idx],'LW LUT raw endpoint')
     aa.append(val);bb.append(path*coefficients['B'][idx][MOMENTS.index(m)]);cc.append(path*coefficients['C'][idx][MOMENTS.index(m)])
   optics_moments[m]=decomposition(aa,bb,cc,(len(selected),nb))
  diffs={};conv={}
  for field in ('UP_WP','DN_WP','HEAT_WP_K_S','UP','DN','HR'):
   # Only native boundaries/layers: no extended-atmosphere TOA attribution.
   extent=59 if field in ('HR','HEAT_WP_K_S') else 60
   vals={mode:variants[mode][field]['values'][:extent] for mode in MODES}
   factor=86400 if field=='HEAT_WP_K_S' else 1
   vals={mode:[v*factor for v in a] for mode,a in vals.items()}
   diffs[field]=decomposition(vals['A'],vals['B'],vals['C'],(1,extent,1))
   if field in ('UP_WP','DN_WP','HEAT_WP_K_S'):
    threshold=numerical['transport_refinement_max_heat_K_day'] if field=='HEAT_WP_K_S' else numerical['transport_refinement_max_flux_W_m2']
    conv[field]={mode:summary([x-y for x,y in zip(vals[mode],vals[mode+'_coarse'])],(1,extent,1)) for mode in ('B','C')}
    transport_ok=transport_ok and all(v['max_abs']<=threshold for v in conv[field].values())
  results[case]={'source_time_seconds':raw['SOURCE_TIME_SECONDS']['values'][0],'native_selected_layers':[k+1 for k in selected],'actual_radius_um':[inp['REL']['values'][k] for k in selected],'selected_path_g_m2':[inp['LWP']['values'][k] for k in selected],'native_transport':diffs,'transport_refinement':conv,'raw_optical_flat_position_mapping':[{'position_1based':i+1,'native_layer':k+1,'band':b+1} for i,(k,b) in enumerate((k,b) for k in selected for b in range(nb))],'transport_position_mapping':'native boundaries1..60 for flux, native layers1..59 for heating; HEAT_WP_K_S values multiplied by86400 to K/day','raw_selected_optical_moments':optics_moments,'independent_layer_moments':layer_rows,'all_physical_inputs_and_unselected_controls_preserved':True,'A_exact_array_matches_original_capture':True}
 return {'status':'COMPLETED_SAME_STATE_ENDPOINT_DECOMPOSITION','numerical':{'coefficient_all_converged':not unresolved,'unresolved_coefficients':unresolved,'final_grid_counts':refinement,'transport_refinement_passed':transport_ok},'cases':results,'decisions':{'endpoint_clamp':'RETAIN_RESEARCH_NUMERICAL_GUARD','outside_range_scientific_application':'WITHHELD','independent_coefficients_production_replacement':'NOT_AUTHORIZED_BY_THIS_DIAGNOSTIC','reason':'Explicit 25C Gamma8/band-weight diagnostic does not certify original LUT definition, temperature dependence, observed PSD, or physical acceptance tolerance. Definition and radius effects are reported separately. Numerical failures, if any, remain visible.','new_policy_or_empirical_correction':False,'existing_reference_FAIL_and_host_budget_OPEN':'PRESERVED'},'new_WRF_runs':0,'new_public_column_processes':15,'production_accepted':False}
