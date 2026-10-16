"""Recompute retained warm-input and optical decisions without NumPy/NetCDF."""
import gzip,hashlib,importlib.util,json,math
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
old=load(ROOT/'validation/rrtmgp37/policy2-budget-optics/analyze_saved.py','prior_budget')
require=old.require

def audit_input(h, reference_required=False):
 ratios=[];eos=[];temps=[];base=[];zbase=[]
 for k in range(59):
  for j in range(2):
   for i in range(2):
    md=h.mass(0,k,j,i);alpha=h.at('AL',0,k,j,i)+h.at('ALB',0,k,j,i);phi=lambda kk:h.at('PH',0,kk,j,i)+h.at('PHB',0,kk,j,i);dz=(phi(k+1)-phi(k))/9.810000419616699
    p=h.at('P',0,k,j,i)+h.at('PB',0,k,j,i);theta=h.at('T',0,k,j,i)+300;qv=h.at('QVAPOR',0,k,j,i);T=theta*(p/1e5)**(287/1004.5);expected=287*T*(1+461.6000061035156/287*qv)/p
    ratios.append(dz/alpha/md);eos.append(alpha/expected-1);temps.append(T);base.append(h.at('T_BASE',0,k)-h.at('THM',0,k,j,i));zbase.append(h.at('Z_BASE',0,k)-(phi(k+1)+phi(k))/(2*9.810000419616699))
    require(md>0 and alpha>0 and T>285 and T<305,'warm input state unsupported')
 require(max(abs(x-1) for x in ratios)<1e-5,'pressure mass and geometry do not represent same layer')
 require(max(map(abs,eos))<2e-6,'dry EOS not consistent with pressure/theta/qv')
 pressure_residual=[]
 for j in range(2):
  for i in range(2):
   mu=h.at('MU',0,j,i);mub=h.at('MUB',0,j,i)
   qt=lambda k:sum(h.at(n,0,k,j,i) for n in ['QVAPOR','QCLOUD','QRAIN'])
   for k in range(59):
    q=qt(k) if k==58 else .5*(qt(k)+qt(k+1));f=q/(1+q);f2=1/(1+q);lev=59 if k==58 else k+1
    c1=h.at('C1F',0,lev);c2=h.at('C2F',0,lev);weight=.5*h.at('DNW',0,k) if k==58 else h.at('DN',0,k+1)
    rhs=-(c1*mu+f*(c1*mub+c2))*weight/f2;expected=rhs if k==58 else h.at('P',0,k+1,j,i)+rhs;actual=h.at('P',0,k,j,i);pressure_residual.append(abs(actual-expected))
    if reference_required:require(abs(actual-expected)<32*2**-23*max(abs(actual),abs(expected),1),'condensate-loading hydrostatic pressure mismatch')
 if reference_required:require(max(map(abs,base))==0,'damper reference uses wrong population of theta')
 return {'discrete_pressure_loading_residual_max_Pa':max(pressure_residual),'rhoDz_over_md_min':min(ratios),'rhoDz_over_md_max':max(ratios),'EOS_relative_residual_max':max(map(abs,eos)),'temperature_min_K':min(temps),'temperature_max_K':max(temps),'T_BASE_minus_initial_THM_max_abs_K':max(map(abs,base)),'Z_BASE_minus_initial_mass_height_max_abs_m':max(map(abs,zbase))}

def analyze(read):
 result={'production_accepted':False,'physics_gates_closed':False,'input':{},'host':{}}
 for tag in ['canonical','theta_reference','final']:
  h=old.History(json.loads(read('host/'+tag+'-input.json')),read('host/'+tag+'-input.bin'));result['input'][tag]=audit_input(h,tag=='final')
  for dt,label,index in [(10,'on_dt10',2),(5,'on_dt5',3)]:
   prefix='host/'+tag+'-'+label;hist=old.History(json.loads(read(prefix+'.json')),read(prefix+'.bin'));text=read(f'host/{tag}/command-{index:02d}.stdout');records=old.micro_records(text);require(len(records)==2*(60//dt)*4*59,'cell/time record missing');budget=old.host_budget(hist,records,dt);budget['rk_forcing']=old.rk_forcing(text);require(budget['rk_forcing']['first_RK_cell_records']==(60//dt)*4*59,'RK coverage differs');result['host'][tag+'-'+label]=budget
 require(result['input']['final']['T_BASE_minus_initial_THM_max_abs_K']==0,'final damper uses wrong reference representation')
 optical=json.loads(read('mie/result.json'));rows=[]
 for row in optical['records']:
  fine=row['calculations']['r2048s192'];coarse=row['calculations']['r1024s96'];lut=row['LUT_raw'];a=fine['Planck5780'];change=max(abs(coarse['Planck5780'][n]/a[n]-1) for n in ['ext','sca','abs','sca_g']);require(change<.01,'two-band numerical refinement unresolved')
  require(a['ext']>=a['sca']>=0 and a['abs']>=0,'nonphysical optical moment')
  require(math.isclose(a['delta_ext']*(1-a['delta_ssa']),a['abs'],rel_tol=2e-11),'raw and delta absorption stages mixed')
  rows.append({'band':row['band'],'case':row['case'],'relative_refinement_max':change,'Mie_over_LUT':{n:a[n]/lut[n] for n in ['ext','sca','abs','sca_g']},'uniform_over_Planck_abs':fine['uniform_wavenumber']['abs']/a['abs']})
 result['two_band_optics']=rows
 parser=load(ROOT/'validation/rrtmgp37/radiation-occurrence-runtime/verify_saved.py','trace')
 data={m:parser.trace(read('flux/'+m+'/sw.result'),'result')[1] for m in ['LUT','Hale','Segelstein']};inputs={m:parser.trace(read('flux/'+m+'/input'),'input')[1] for m in data};require(inputs['LUT']==inputs['Hale']==inputs['Segelstein'],'thin optical pair changed state')
 inp=inputs['LUT'];require(sum(x!=0 for x in inp['LWP']['values'])==1 and inp['CF']['values'][29]==1 and all(x==12. for x in inp['REL']['values']),'thin probe scope changed')
 for n in ['RWP','IWP','SWP','UNIFORM_LWP','UNIFORM_RWP']:
  if n in inp:require(all(x==0 for x in inp[n]['values']),'another hydrometeor in thin optical probe')
 flux={}
 for mode in ['Hale','Segelstein']:
  for n in ['MASK','GAS_TAU','PRECIP_TAU','UPC','DNC','HRC']:require(data[mode][n]==data['LUT'][n],'held component changed '+n)
  flux[mode]={n:max(abs(a-z) for a,z in zip(data[mode][n]['values'],data['LUT'][n]['values'])) for n in ['UP','DN','HR','CLOUD_TAU']}
  require(flux[mode]['HR']>0 and flux[mode]['DN']>0,'thin probe does not resolve optical difference')
 result['thin_SW_sensitivity']=flux
 result['decisions']={'coupling_density_overwrite':'NOT_JUSTIFIED_BY_CONSISTENT_INPUT','warm_research_input':'ADOPT_NARROW_DISCRETE_HYDROSTATIC_THETAM_REFERENCE','whole_host_water':'NONMICRO_RESIDUAL_REMAINS_UNAPPROVED','whole_host_energy':'OPEN','Gamma':'RETAIN_CONDITIONAL_CANDIDATE','LUT_generation_RI_PSD_weighting':'NOT_CERTIFIED','optical_cause':'RI_TABLE_AND_INTERPOLATION_DOMINATE_TESTED_PSD_SHAPE_CHANGE','production_policy_changed':False}
 return result
if __name__=='__main__':
 read=lambda n:gzip.decompress((B/'saved'/(n+'.gz')).read_bytes());print(json.dumps(analyze(read),indent=2))
