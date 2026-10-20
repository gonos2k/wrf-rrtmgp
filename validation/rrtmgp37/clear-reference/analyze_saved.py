"""Stdlib-only stored evidence replay. Does not launch upstream, WRF or quadrature."""
import json,math,importlib.util,struct
from pathlib import Path
P=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('same_state_analysis',P.parent/'same-state-engines/analyze_saved.py');prior=importlib.util.module_from_spec(spec);spec.loader.exec_module(prior)
def require(x,m):
 if not x:raise ValueError(m)
def near(a,b,tol,m):require(abs(a-b)<=tol,m)
def vector(a,b,tol,m):
 require(len(a)==len(b),m+' extent')
 for x,y in zip(a,b):near(x,y,tol,m)
def rows(data):return [list(map(float,l.split())) for l in data.decode().splitlines()]
def target(u,d,C):
 net=[y-x for x,y in zip(u,d)]
 return {'surface_up_down_net':[u[0],d[0],net[0]],'native_top_up_down_net':[u[59],d[59],net[59]],'native_column_convergence':net[59]-net[0],'native_common_heat_K_day':[(net[k+1]-net[k])/C[k]*86400 for k in range(59)]}
def difference(a,b):return {k:([x-y for x,y in zip(a[k],b[k])] if isinstance(a[k],list) else a[k]-b[k]) for k in a}
def analyze(read,plan):
 report=json.loads(read('analysis.json'));port={};res={}
 require(report['production_accepted'] is False,'physical approval promotion')
 for ph in ['lw','sw']:
  u,d,col=rows(read(ph+'/flux.dat'));_,res[ph]=prior.parse37(read(ph+'/adapter.result'),'result');_,inp=prior.parse37(read(ph+'/adapter.input'),'input')
  require(len(u)==122 and len(d)==122 and len(col)==121,'full reference grid')
  err=max(abs(x-y) for a,b in [(u,res[ph]['UP_WP']['values']),(d,res[ph]['DN_WP']['values'])] for x,y in zip(a,b))
  require(err<=plan['port_screen_absolute_W_m2'],'direct upstream does not reproduce adapter')
  vector(col,res[ph]['GAS_COL_DRY']['values'],0,'gas column differs')
  vu,vd,vc=rows(read(ph+'/vendor-flux.dat'));vector(u,vu,1e-9,'upstream/vendor up');vector(d,vd,1e-9,'upstream/vendor down');vector(col,vc,0,'upstream/vendor molecules')
  port[ph]={'max_flux_abs_W_m2':err,'max_molecule_relative_difference':0.0,'pass':True}
  require(inp['CF']['values']==[0.]*121 and inp['LWP']['values']==[0.]*121,'clear input changed')
  if ph=='sw':
   for key,values in zip(['TAU','SSA','G'],rows(read('sw/optics.dat'))):vector(values,res[ph]['GAS_'+key]['values'],0,'direct SW gas optics '+key)
  # Frozen common input and original native results, not an independent new state.
  ls=read(ph+'/input.dat').decode().splitlines()
  require(len(set(ls[7].split()))==1,'fixed reference requires uniform band emissivity')
  for idx,key in [(2,'PLAY'),(3,'PLEV'),(4,'TLAY')]+list(zip(range(8,14),prior.MOL)):
   z=[struct.unpack('f',struct.pack('f',float(x)))[0] for x in ls[idx].split()]
   vector(z,inp[key]['values'],0,'common fixed input '+key)
 history=json.loads(read('angular-history.json'));require([x['order'] for x in history]==plan['angular_orders'][:len(history)],'quadrature order sequence')
 require(len(history)>=2,'no refinement pair');trace=[]
 for n,h in enumerate(history):
  require(all(math.isfinite(x) for a in ['up','dn','pressure_heat_K_day'] for x in h[a]),'nonfinite quadrature')
  require(len(h['up'])==122 and len(h['dn'])==122 and len(h['pressure_heat_K_day'])==121,'quadrature extents')
  changes=None if not n else [max(abs(a-b) for a,b in zip(h[k],history[n-1][k])) for k in ['up','dn','pressure_heat_K_day']]
  trace.append({'order':h['order'],'successive_up_down_W_m2_heat_K_day':changes})
 require(max(trace[-1]['successive_up_down_W_m2_heat_K_day'][:2])<=plan['angular_successive_flux_screen_W_m2'],'angular numerical screen')
 require(report['angular_trace']==trace,'reported angular trace changed')
 one_angle_check(read,plan)
 C=prior.native4(read('lw/native4.txt'))[1]['Cstar'];v4=prior.native4(read('lw/native4.txt'))[1]
 u,d,_=rows(read('lw/flux.dat'));ref=target(history[-1]['up'],history[-1]['dn'],C);one=target(u,d,C);legacy=target(v4['UP'],v4['DN'],C)
 for key,value in [('conditional_reference',ref),('upstream_one_angle',one),('legacy4',legacy)]:
  for k,v in value.items():
   if isinstance(v,list):vector(v,report[key][k],1e-11,'target '+key+' '+k)
   else:near(v,report[key][k],1e-11,'target '+key+' '+k)
 arr=json.loads(read('band-arrays.json'));_,ex=prior.parse4(read('legacy-export4.txt'))
 # Verify physical group intervals are contiguous unions in BOTH spectral grids.
 groups=[]
 for x in report['common_physical_band_upper_DN']:
  lo,hi=x['wavenumber_cm_1'];i=[v-1 for v in x['bands37_one_based']];j=[v-1 for v in x['bands4_one_based']]
  for key,inds in [('bands37',i),('bands4',j)]:
   bb=[arr[key][z] for z in inds];require(bb[0][0]==lo and bb[-1][1]==hi and all(a[1]==b[0] for a,b in zip(bb,bb[1:])),'gpoint/index pairing instead of common physical bands')
  a=sum(arr['dn37'][z][59] for z in i);b=sum(arr['dn4'][z][59] for z in j)
  near(a,x['native_top_DN37'],1e-11,'band37 flux');near(b,x['native_top_DN4'],1e-11,'band4 flux');near(a-b,x['native_top_DN37_minus4'],1e-11,'signed band difference');groups.append(x)
 # Rounded legacy band sum is retained separately from exact broadband observations.
 near(sum(x['native_top_DN37'] for x in groups),d[59],1e-9,'37 band sum')
 require(read('legacy-native4.txt')==read('lw/native4.txt'),'observer changed legacy output')
 producer=json.loads(read('real/number1_input/producer.json'));require(producer['all_arrays_preserved'] is True and producer['boundary_runtime_support'] is False,'producer/support promotion')
 require(producer['production_accepted'] is False,'producer physics approval')
 for name,f in producer['files'].items():
  require(f['checked'] and f['all_variable_array_sha256'],'missing real array inventory')
  for n,z in f['checked'].items():require(z['min']==0 and z['max']==0,'nonzero input accepted')
 real=json.loads(read('real/receipt.json'));require(real['research_number1_boundary']=='REJECTED_BEFORE_HISTORY_BY_EXISTING_GUARD','boundary approval promotion')
 require('SUCCESS COMPLETE WRF' in read('real/legacy_real/combined.log').decode(),'no real legacy completion')
 require('specified/nested boundaries unsupported' in read('real/number1_boundary/combined.log').decode(),'missing actual boundary refusal')
 require(real['short_real_legacy_completed_seconds']==20 and real['production_accepted'] is False,'real run scope promotion')
 decomposition={'one37_minus_angular_reference':difference(one,ref),'angular_reference_minus_4':difference(ref,legacy),'one37_minus4':difference(one,legacy)}
 return {'status':'CONDITIONAL_CLEAR_REFERENCE_AND_REAL_INPUT_PRODUCER_EXECUTED','port':port,'angular_order':history[-1]['order'],'angular_last_change':trace[-1]['successive_up_down_W_m2_heat_K_day'],'LW':{'one37':one,'conditional_angular':ref,'legacy4':legacy,'difference_decomposition':decomposition,'native_top_down_common_bands':groups},'decision':{'port_input_conversion_defect_found':False,'LW_default_angle_explains_native_top_down_gap':False,'dominant_remaining_question':'pinned gas optical/source and spectral/legacy diffusivity definitions in common 1080-1390 cm-1 interval; no molecular spectral truth inferred','conditional_angular_reference_qualified':True,'gas_spectroscopy_physical_accuracy_approved':False,'production_tuning_or_policy_change':False,'real_zero_number_representation':'PRODUCED_WITHOUT_CHANGING_ARRAYS','real_legacy_20s_path':'COMPLETED','number1_specified_boundary_support':'NOT_IMPLEMENTED; actual existing guard rejection preserved','all_warm_real_support':'NOT_APPROVED; initial state includes 192 K','existing_seven_conditions_and_reference_FAILs':'PRESERVED'},'new_model_runs_in_saved_replay':0,'production_accepted':False}

def one_angle_check(read,plan):
 ls=read('lw/source.dat').decode().splitlines();nl,ng=map(int,ls[0].split());require((nl,ng)==(121,128),'source extent')
 tau,lay,lev,surf=[list(map(float,z.split())) for z in ls[1:5]]
 require([len(z) for z in [tau,lay,lev,surf]]==[nl*ng,nl*ng,(nl+1)*ng,ng],'source layout')
 require(all(math.isfinite(z) for arr in [tau,lay,lev,surf] for z in arr) and min(tau)>=0,'invalid source/optics')
 raw=prior.parse37(read('lw/adapter.result'),'result')[1]['GAS_TAU']['values'];vector(tau,raw,0,'source gas tau')
 emis=float(read('lw/input.dat').decode().splitlines()[7].split()[0]);mu=.6096748751;up=[0.]*(nl+1);dn=[0.]*(nl+1)
 for g in range(ng):
  trans=[];su=[];sd=[]
  for k in range(nl):
   x=tau[g*nl+k]/mu;t=math.exp(-x);f=(1-t)/x-t if x>2**-13 else x*(.5+x*(-1/3+x/8))
   q=lay[g*nl+k];l=lev[g*(nl+1)+k];h=lev[g*(nl+1)+k+1]
   trans.append(t);su.append((1-t)*h+2*f*(q-h));sd.append((1-t)*l+2*f*(q-l))
  d=[0.]*(nl+1)
  for k in range(nl-1,-1,-1):d[k]=trans[k]*d[k+1]+sd[k]
  u=[d[0]*(1-emis)+emis*surf[g]]
  for k in range(nl):u.append(trans[k]*u[k]+su[k])
  for k in range(nl+1):up[k]+=math.pi*u[k];dn[k]+=math.pi*d[k]
 expected=rows(read('lw/flux.dat'));vector(up,expected[0],plan['angular_reconstruction_absolute_W_m2'],'independent one-angle reconstruction up');vector(dn,expected[1],plan['angular_reconstruction_absolute_W_m2'],'independent one-angle reconstruction down')
