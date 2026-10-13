#!/usr/bin/env python3
"""Research-only fixed-CF population candidate executed in full actual UDM.

No production edit/namelist switch. Warm cloud and rain share a prescribed
fixed footprint; all cold mass except optional pre-warm melt is absent.
"""
import argparse,hashlib,importlib.util,json,math,os,re,shutil,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True
STATE=('nn','nc','nr','qv','qc','qi','qr','qs','qg','qh','t','p','rho','cf')
RATES=('praut','pracw','prevp','ncaut','nraut','nccol','nracw','nrcol')
STAGES=('ADJUST_IN','ADJUST_OUT','PHASE_GRID','PHASE_LOCAL','PHASE_SLOPE','MELT_PRE','MELT_POST','PHASE_RESTORED','WARM_GRID','WARM_LOCAL','WARM_RATES','WARM_RESTORED','BULK_PRE','BULK_POST','HELPER_IN','HELPER_OUT','LIMIT','AUTO')

def require(ok,msg):
 if not ok:raise ValueError(msg)
def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def f32(x):return struct.unpack('!f',struct.pack('!f',x))[0]
def sha(b):return hashlib.sha256(b).hexdigest()

def snapshot(raw):
 s=raw.decode();patches=[]
 def insert(anchor,body,before=False,count=1,occurrence=None):
  nonlocal s
  require(s.count(anchor)==count,'anchor changed '+repr(anchor))
  marked='! POPULATION_TEST_BEGIN\n'+body+'! POPULATION_TEST_END\n'
  replacement=marked+anchor if before else anchor+marked
  if occurrence is None:s=s.replace(anchor,replacement)
  else:
   positions=[m.start() for m in re.finditer(re.escape(anchor),s)];pos=positions[occurrence-1];s=s[:pos]+replacement+s[pos+len(anchor):]
  patches.append({'anchor':anchor,'before':before,'count':count,'block':marked})
 insert('  module module_mp_udm\n','   use udm_population_test, only: capture, candidate, fixed_cf\n')
 st='[ncr(k,i,1),ncr(k,i,2),ncr(k,i,3),q(k,i),qci(k,i,1),qci(k,i,2),qrs(k,i,1),qrs(k,i,2),qrs(k,i,3),qrs(k,i,4),t(k,i),p(k,i),den(k,i),cldf(k)]'
 def rows(tag,extra='',top='ktopini'):
  vector=st if not extra else st[:-1]+','+extra+']'
  return '   do k=kts,'+top+'\n     call capture("'+tag+'",i,k,loop,'+vector+')\n   enddo\n'
 insert('   call adjust_number_concent(ktopqr,kdim,qrs(:,i,1),ncr(:,i,3),den(:,i),      &\n',rows('ADJUST_IN'),True)
 insert('        pidnc,one_1,qcmin,ncmin,ncmax,di15,  dcmin, dcmax)\n',rows('ADJUST_OUT'))
 insert('   if (present(udm_cldfra)) udm_cldfra(i,kts:kte)=cldf(:)\n','   cldf(kts:ktopini)=fixed_cf\n',True)
 insert('   if (present(udm_cf_top)) udm_cf_top(i)=ktop\n',rows('PHASE_GRID'))
 # Only cloud/rain number in the phase region whose masses are conditioned.
 first='! update the slope parameters for microphysics computation\n'
 convert='   if(candidate) then\n     do k=kts,ktop\n       if(cldf(k)>0.) then\n         ncr(k,i,2)=ncr(k,i,2)/cldf(k)\n         ncr(k,i,3)=ncr(k,i,3)/cldf(k)\n       endif\n     enddo\n   endif\n'
 insert(first,convert+rows('PHASE_LOCAL'))
 insert('! melting/freezing\n',rows('PHASE_SLOPE','rslopec(k),rslope(k,1),dtcld,lamdacmin,lamdacmax,lamdarmin,lamdarmax'))
 insert('       if(.not.ifice(k) .and. qci(k,i,2)>0.) then\n','         call capture("MELT_PRE",i,k,loop,'+st[:-1]+',cpm(k,i),xlf0,dtcld])\n')
 insert('! Clear only after the mass-dependent melt number has consumed the ice.\n         qci(k,i,2) = 0.\n','         call capture("MELT_POST",i,k,loop,'+st[:-1]+',ni(k),cpm(k,i),xlf0,dtcld])\n')
 insert('     qrs(k,i,4) = qrs(k,i,4) * cldf(k)\n','     if(candidate) then\n       ncr(k,i,2)=ncr(k,i,2)*cldf(k)\n       ncr(k,i,3)=ncr(k,i,3)*cldf(k)\n     endif\n')
 insert('! re-define cloud top for numerical efficiencies\n',rows('PHASE_RESTORED'),count=3,occurrence=2)
 # Warm liquid/rain rates must consume local q and N; cold/activation remain grid.
 warm='! update the slope parameters and microphysical parameters\n'
 cond='   if(candidate) then\n     do k=kts,ktopini\n       qci(k,i,1)=qci(k,i,1)/cldf(k)\n       qrs(k,i,1)=qrs(k,i,1)/cldf(k)\n       ncr(k,i,2)=ncr(k,i,2)/cldf(k)\n       ncr(k,i,3)=ncr(k,i,3)/cldf(k)\n     enddo\n   endif\n'
 insert(warm,rows('WARM_GRID')+cond+rows('WARM_LOCAL'))
 rr=','.join(n+'(k)' for n in RATES)
 # Rates become grid tendencies once, before donor limits and native updates.
 restore='   if(candidate) then\n     do k=kts,ktopini\n       qci(k,i,1)=qci(k,i,1)*cldf(k)\n       qrs(k,i,1)=qrs(k,i,1)*cldf(k)\n       ncr(k,i,2)=ncr(k,i,2)*cldf(k)\n       ncr(k,i,3)=ncr(k,i,3)*cldf(k)\n'+''.join('       '+n+'(k)='+n+'(k)*cldf(k)\n' for n in RATES)+'     enddo\n   endif\n'
 insert('! cold rain processes\n',rows('WARM_RATES',rr+',dtcld,rslopec(k),rslope(k,1),cpm(k,i)')+restore+rows('WARM_RESTORED',rr+',dtcld'),True)
 insert('         nraut(k) = min(real(nr_aut),praut(k)/mrmin)\n','         call capture("AUTO",i,k,loop,[n_c,L_c,real(nu_c),real(lamc),real(qc_aut/den(k,i)),real(nc_aut),real(nr_aut),praut(k),ncaut(k),nraut(k),qci(k,i,1)*rdtcld,ncr(k,i,2)*rdtcld,praut(k)/mrmin,lamdacmin,lamdacmax])\n')
 insert('! ccn activaiton and condensation/evaporation of clouds\n',rows('BULK_POST',rr+',dtcld'))
 # Native donor limiting section starts with both phase flags updated above it.
 anchor='! update tendency\n'
 if anchor not in s:
  # Exact one source heading found below during initial implementation.
  anchor='! update mixing ratios\n'
 # Use the original block boundary, not an extra update/reconstructed source.
 boundary='   do k = ktop, kts, -1\n     if(ifice(k)) then\n'
 # There are multiple such loops; use section prefix whose exact bytes are pinned.
 pos=s.index('       hvalue = max(qmin,qci(k,i,1))\n');loopstart=s.rfind('   do k = ktop, kts, -1\n',0,pos)
 line=s[loopstart:s.index('\n',loopstart)+1]
 marker='! POPULATION_TEST_BEGIN\n'+rows('BULK_PRE',rr+',dtcld')+'! POPULATION_TEST_END\n'
 s=s[:loopstart]+marker+s[loopstart:];patches.append({'index_anchor':'bulk donor loop','block':marker})
 caps='       if (source>hvalue) then\n';count=s.count(caps)
 insert(caps,'         call capture("LIMIT",i,k,loop,[source,hvalue])\n',count=count)
 helper='[nc1d(k),qc1d(k),den1d(k),t1d(k),qi1d(k),qs1d(k)]'
 insert('            call udm_mp_effective_radius(t1d,qc1d,qi1d,qs1d,den1d,qmin, t0c    &\n','            do k=kts,kte\n              call capture("HELPER_IN",i,k,0,'+helper+')\n            enddo\n',True)
 insert('                               ,re_qc, re_qi, re_qs, kts, kte, i, j)\n','            do k=kts,kte\n              call capture("HELPER_OUT",i,k,0,'+helper[:-1]+',re_qc(k),re_qi(k),re_qs(k)])\n            enddo\n')
 stripped=re.sub(r'! POPULATION_TEST_BEGIN\n.*?! POPULATION_TEST_END\n','',s,flags=re.S)
 require(stripped.encode()==raw,'research snapshot cannot restore exact production source')
 return s.encode(),patches

def fixture(raw):
 s=raw.decode().replace('module udm_test_observer','module udm_population_test').replace('use udm_test_observer','use udm_population_test')
 s=s.replace('  integer :: case_id=0','  integer :: case_id=0\n  logical :: candidate=.false.\n  real :: fixed_cf=1.')
 s=s.replace('integer::step(1,1),top(1,1),a,b,k,iteration','integer::step(1,1),top(1,1),a,b,k,iteration')
 s=s.replace('character(8)::mode','character(16)::mode,scenario,observe')
 s=s.replace('  call get_command_argument(1,mode)','  call get_command_argument(1,mode)\n  call get_command_argument(2,scenario)\n  call get_command_argument(3,observe)\n  candidate=trim(mode)=="candidate"')
 s=s.replace("  if (trim(mode)/='on'.and.trim(mode)/='off') error stop 'select on/off'",'')
 s=s.replace("observer_enabled=trim(mode)=='on'","observer_enabled=trim(observe)=='on'")
 s=s.replace('do b=1,2','do b=1,3').replace('      target_alpha=.35\n      if(b==2) target_alpha=.65','      fixed_cf=2.**(1-b)\n      target_alpha=fixed_cf').replace('case_id=2*(a-1)+b','case_id=3*(a-1)+b')
 s=s.replace('rh=1.+.0048*exp(log(target_alpha)/.6)','rh=1.')
 s=s.replace('qc=1.e-4; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.','qc=fixed_cf*.008; qi=0.; qr=fixed_cf*.004; qs=0.; qg=0.; qh=0.\n      if(trim(scenario)=="melt") qi=fixed_cf*1.e-5')
 s=s.replace('nn=2.e8; nc=5.e7; nr=0.','nn=2.e8/den; nc=fixed_cf*5.e8/den; nr=fixed_cf*1.e5/den')
 s=s.replace('delt=1.,','delt=.01,').replace('input_density_is_dry=.true.)','input_density_is_dry=.true.,number_policy=1)')
 return s.encode()

def parse(text):
 lines=text.splitlines();data={'obs':{},'inputs':{},'outputs':{},'tags':{}};i=0
 while i<len(lines):
  w=lines[i].split();i+=1
  if not w or w[0] not in ('OBS','INPUT','RETURN','TAGS'):continue
  if w[0]=='TAGS':data['tags'][int(w[1])]=list(map(int,w[2:]));continue
  require(i<len(lines),'truncated record');words=lines[i].split();i+=1;require(len(words)==int(w[-1]),'state extent')
  require(all(re.fullmatch('[0-9A-F]{8}',x) for x in words),'REAL32 bits')
  v=[struct.unpack('!f',bytes.fromhex(x))[0] for x in words];require(all(math.isfinite(x) for x in v),'nonfinite value')
  if w[0]=='OBS':
   key=(w[1],*map(int,w[2:6]));require(w[1] in STAGES and key not in data['obs'],'observation roster');data['obs'][key]=v
  elif w[0]=='INPUT':data['inputs'][tuple(map(int,w[1:3]))]=v
  else:data['outputs'][int(w[1])]=words
 require(set(data['inputs'])=={(c,k) for c in range(1,7) for k in range(1,5)},'input roster')
 require(set(data['outputs'])==set(data['tags'])==set(range(1,7)),'return roster')
 return data

def analyze(data):
 rows=[];diagnostics=[]
 for scenario in ('warm','melt'):
  native=data[scenario,'native','off']
  for mode in ('current','candidate'):
   d=data[scenario,mode,'on'];off=data[scenario,mode,'off']
   require(d['outputs']==off['outputs'] and d['tags']==off['tags'],'observer changes full UDM return')
   require(not any(key[0]=='LIMIT' for key in d['obs']),'donor limiter active: fixture is outside declared comparison')
   require(len(d['obs'])== (13*18+8*6 if scenario=='warm' else 15*18+8*6),'stage/cell roster differs')
   for c in range(1,7):
    f=(1.,.5,.25)[(c-1)%3];rho=d['inputs'][c,1][12]
    if f==1.:require(d['outputs'][c]==native['outputs'][c],'CF=1 does not return to actual production UDM')
    for k in range(1,4):
     def get(tag):return d['obs'][tag,c,1,k,1]
     adjusted0,adjusted1=get('ADJUST_IN'),get('ADJUST_OUT')
     require(adjusted0[:13]==adjusted1[:13],'entry number/size adjustment active')
     phase,local=get('PHASE_GRID'),get('PHASE_LOCAL');slopes=get('PHASE_SLOPE')
     restored=get('PHASE_RESTORED');wg,wl,wr,rr,bpre,bpost=map(get,('WARM_GRID','WARM_LOCAL','WARM_RATES','WARM_RESTORED','BULK_PRE','BULK_POST'))
     require(all(x[13]==f for x in (phase,local,slopes,restored,wg,wl,wr,rr,bpre,bpost)),'fixed CF changed')
     for idx in (4,5,6):require(local[idx]==f32(phase[idx]/f),'phase mass condition')
     for idx in (1,2):require(local[idx]==(f32(phase[idx]/f) if mode=='candidate' else phase[idx]),'phase population condition')
     require(phase[0]==local[0]==restored[0] and wg[0]==wl[0]==wr[0]==rr[0],'free CCN was conditioned or altered in warm/phase block')
     for idx in (1,2,4,6):require(wl[idx]==(f32(wg[idx]/f) if mode=='candidate' else wg[idx]),'warm population condition')
     for idx in (1,2,4,6):require(rr[idx]==(f32(wr[idx]*f) if mode=='candidate' else wr[idx]),'warm state restore')
     for n,name in enumerate(RATES):require(rr[14+n]==(f32(wr[14+n]*f) if mode=='candidate' else wr[14+n]),'warm grid rate restore '+name)
     require(rr[14:22]==bpre[14:22]==bpost[14:22],'later donor stage changes warm rates')
     total0=sum(bpre[j] for j in (3,4,6));total1=sum(bpost[j] for j in (3,4,6))
     require(abs(total1-total0)<8.*2.**-23*total0,'warm bulk water closure')
     rate=dict(zip(RATES,rr[14:22]));dt=rr[22]
     # Actual warm branch update expressions: Nc consumes nraut, not diagnostic ncaut.
     deltas={'qc':f32(f32(rate['praut']+rate['pracw'])*dt),'qr':f32(f32(f32(rate['praut']+rate['pracw'])+rate['prevp'])*dt),
             'nc':f32(f32(f32(-rate['nraut']-rate['nccol'])-rate['nracw'])*dt),'nr':f32(f32(rate['nraut']-rate['nrcol'])*dt)}
     expected={4:f32(bpre[4]-deltas['qc']),6:f32(bpre[6]+deltas['qr']),1:f32(bpre[1]+deltas['nc']),2:f32(bpre[2]+deltas['nr'])}
     require(all(0.<expected[i] for i in expected),'zero floor active')
     for idx,value in expected.items():require(bpost[idx]==value,'actual warm update/restore differs')
     require(0.<bpost[1]<3.e10 and 0.<bpost[2]<3.e8,'final warm number cap active')
     au=get('AUTO')
     require(2.<au[2]<15. and au[13]<au[3]<au[14],'Gamma shape/slope limiter active')
     require(au[7]==au[4] and au[8]==au[5] and au[9]==au[6] and au[7]>0.,'autoconversion cap/zero floor active')
     require(.1e-3<wl[6] and .1e-3<local[6],'rain one-moment fallback threshold active')
     for x,nidx,qidx,size in ((local,1,4,slopes[14]),(local,2,6,slopes[15]),(wl,1,4,wr[23]),(wl,2,6,wr[24])):
      require(x[nidx]>0. and x[qidx]>1.e-9 and size>0.,'nonpositive slope population')
      bounds=slopes[17:19] if nidx==1 else slopes[19:21]
      require(1./bounds[1]<size<1./bounds[0],'cloud/rain size clamp active')
     # M3 and M2 of the actual liquid Gamma autoconversion distribution.
     nu=int(au[2]);lam=au[3];rv=((nu+1)*(nu+2)*(nu+3))**(1./3.)/lam;reff=(nu+3)/lam
     helper=d['obs']['HELPER_IN',c,1,k,0];hout=d['obs']['HELPER_OUT',c,1,k,0]
     require(f32(2.51e-6)<hout[6]<f32(50.e-6),'native liquid radius clipping active')
     diagnostics.append({'scenario':scenario,'mode':mode,'case':c,'layer':k,'CF':f,'rho':rho,'phase_cloud_size':slopes[14]*.5,'phase_rain_size':slopes[15],
                         'warm_cloud_size':wr[23]*.5,'warm_rain_size':wr[24],'local_rates':dict(zip(RATES,wr[14:22])),
                         'grid_rates':rate,'bulk_grid_deltas':deltas,'Gamma_nu':nu,'Gamma_rv_m':rv,'Gamma_reff_m':reff,'Gamma_reff_to_rv':reff/rv,'Gamma_M3_mass_to_input':(4.*math.pi/3.*1000.*au[0]*rv**3)/au[1],
                         'NC_after_bulk':bpost[1],'NC_final_host':struct.unpack('!f',bytes.fromhex(d['outputs'][c][36+k-1]))[0],'native_final_radius_m':hout[6]})
     if scenario=='melt':
      pre,post=get('MELT_PRE'),get('MELT_POST');require(pre[5]>0. and post[5]==0.,'melt not executed')
      expected_nc=f32(post[1]*f) if mode=='candidate' else post[1]
      require(restored[1]==expected_nc,'melt number grid restore differs')
      require(restored[4]==f32(post[4]*f),'melt mass grid restore differs')
      rows.append({'scenario':scenario,'mode':mode,'case':c,'layer':k,'CF':f,'Nmelt_local':post[14],'NC_before_phase_grid':phase[1],
                   'NC_after_phase_grid':restored[1],'NC_after_melt_local':post[1],'grid_NC_increment':restored[1]-phase[1]})
     else:require(restored[:13]==phase[:13],'no-process phase bridge changed grid state')
  # The candidate consumes the same local state; comparison is within each rho.
  if scenario=='warm':
   for rho_group in (0,1):
    for k in range(1,4):
     baseline=next(x for x in diagnostics if x['scenario']==scenario and x['mode']=='candidate' and x['case']==1+rho_group*3 and x['layer']==k)
     for cf_index in (1,2):
      row=next(x for x in diagnostics if x['scenario']==scenario and x['mode']=='candidate' and x['case']==1+rho_group*3+cf_index and x['layer']==k)
      for name in ('phase_cloud_size','phase_rain_size','warm_cloud_size','warm_rain_size','local_rates','Gamma_nu','Gamma_rv_m','Gamma_reff_m'):
       require(row[name]==baseline[name],'candidate local PSD/rate depends on CF '+name)
      for name in RATES:require(row['grid_rates'][name]==f32(row['CF']*baseline['grid_rates'][name]),'candidate grid rate area scaling')
  else:
   for rho_group in (0,1):
    for mode in ('current','candidate'):
     for k in range(1,4):
      group=[r for r in rows if r['mode']==mode and r['case'] in range(1+rho_group*3,4+rho_group*3) and r['layer']==k]
      require(len(group)==3 and len({r['Nmelt_local'] for r in group})==1,'melt fit inputs differ across CF')
      for r in group:
       if mode=='candidate':require(r['grid_NC_increment']==r['CF']*group[0]['grid_NC_increment'],'melt grid increment area scaling')
       else:require(r['grid_NC_increment']==f32(r['NC_before_phase_grid']+r['Nmelt_local'])-r['NC_before_phase_grid'],'current melt increment is not the unweighted native addition')
 # Current mixed phase size gives the manufactured f^(-1/3) behavior, not a measured forecast error.
 contrasts=[]
 for c in (2,3,5,6):
  a=next(x for x in diagnostics if x['scenario']=='warm' and x['mode']=='current' and x['case']==c and x['layer']==1)
  b=next(x for x in diagnostics if x['scenario']=='warm' and x['mode']=='candidate' and x['case']==c and x['layer']==1)
  ratio=a['phase_cloud_size']/b['phase_cloud_size'];require(abs(ratio-a['CF']**(-1./3.))<2.e-6,'current phase size counterexample missing')
  require(a['local_rates']['nccol']/a['CF']!=b['local_rates']['nccol'],'current grid-mean warm closure indistinguishable')
  contrasts.append({'case':c,'CF':a['CF'],'phase_cloud_radius_ratio_current_to_candidate':ratio,'current_grid_nccol':a['grid_rates']['nccol'],'candidate_grid_nccol':b['grid_rates']['nccol']})
 return {'diagnostics':diagnostics,'melt_increment_rows':rows,'current_counterexamples':contrasts,'CF1_native_bitwise':True,'candidate_local_warm_rates_invariant':True,'candidate_grid_tendencies_area_scaled':True,'candidate_melt_increment_area_scaled':True,'observer_returns_bitwise_equal':True,'production_accepted':False}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--workdir',required=True,type=Path);args=ap.parse_args()
 root=args.wrf_root.resolve();work=args.workdir.resolve();work.mkdir(parents=True,exist_ok=False);tests=root/'test/rrtmgp';helper=load(tests/'test_netcdf_zz.py','runner')
 script=Path(__file__).read_bytes();(work/'runner_script.py').write_bytes(script)
 raw=(root/'phys/module_mp_udm.F').read_bytes();candidate,patches=snapshot(raw);(work/'production.F').write_bytes(raw);(work/'research.F').write_bytes(candidate);(work/'fixture.f90').write_bytes(fixture((tests/'test_udm_partial_activation.f90').read_bytes()))
 runner=helper.Runner(work,180,{**os.environ,'LC_ALL':'C','OMP_NUM_THREADS':'1'},100);report={'schema':'UDM_FIXED_CF_POPULATION_CANDIDATE_V1','status':'PREPARED','runner_script_sha256':sha(script),'production_source_sha256':sha(raw),'research_source_sha256':sha(candidate),'production_accepted':False,'production_source_changed':False,'WRF_runs':0,'processes':[],'patches':patches,'results':{}}
 def save():report['processes']=runner.commands;helper.write_json(work/'receipt.json',report)
 save()
 try:
  compiler=Path(shutil.which('gfortran')).resolve();runner.run([compiler,'--version'],work,'compiler_version')
  for opt in ('O0','O2'):
   d=work/opt;d.mkdir();flags=['-'+opt,'-g','-ffree-form','-ffree-line-length-none','-fcheck=all','-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-J',str(d),'-I',str(d)]
   stub=d/'errors.f90';stub.write_text('module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\ninteger,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\nsubroutine wrf_error_fatal(text)\ncharacter(*),intent(in)::text\nprint *,text\nerror stop 2\nend subroutine\n');objects=[]
   for p,extra in [(root/'phys/module_gfs_machine.F',['-ffixed-form']),(stub,[]),(root/'phys/module_mp_radar.F',[]),(work/'fixture.f90',['-cpp','-DOBSERVER_ONLY'])]:
    obj=d/(p.stem+'.o');runner.run([compiler,*flags,*extra,'-c',p,'-o',obj],d,'compile_dependency');objects.append(obj)
   data={}
   for variant in ('production','research'):
    obj=d/(variant+'.o');runner.run([compiler,*flags,'-c',work/(variant+'.F'),'-o',obj],d,'compile_'+variant);exe=d/variant;runner.run([compiler,*flags,'-cpp',work/'fixture.f90',*objects,obj,'-o',exe],d,'link_'+variant)
    modes=['native'] if variant=='production' else ['current','candidate']
    for scenario in ('warm','melt'):
     for mode in modes:
      for enabled in (['off'] if variant=='production' else ['on','off']):
       kind=variant+'_'+scenario+'_'+mode+'_'+enabled;out=runner.run([exe,mode,scenario,enabled],d,'UDM_'+kind);data[scenario,mode,enabled]=parse(out.read_text())
   # Reducer is shared with sealed saved replay; results record process decisions.
   report['results'][opt]=analyze(data);save()
  require((root/'phys/module_mp_udm.F').read_bytes()==raw and Path(__file__).read_bytes()==script,'production/script source changed during run')
  require(report['results']['O0']==report['results']['O2'],'optimization changes candidate result')
  report.update(status='PASS_SCOPED_FIXED_CF_POPULATION_CANDIDATE',actual_UDM_calls=120,manufactured_initial_states=12,physical_gate_closed=False);save();print(json.dumps({'status':report['status'],'receipt':str(work/'receipt.json')}))
 except BaseException as e:report.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':main()
