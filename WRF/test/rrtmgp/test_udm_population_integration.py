#!/usr/bin/env python3
"""Actual opt-in UDM integration: exchange, non-dyadic CF, active donor and substeps.

Observer inserts records and a manufactured footprint only, never the candidate
formulation. Unmodified module calls cover the actual cldf_diag path separately.
"""
import argparse,hashlib,importlib.util,json,math,os,re,shutil,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True

def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def f32(x):return struct.unpack('!f',struct.pack('!f',x))[0]
def near(a,b):return abs(a-b)<=16*2**-23*max(abs(a),abs(b),1.e-30)
RATES=('praut','pracw','prevp','ncaut','nraut','nccol','nracw','nrcol')

def observed(raw):
 s=raw.decode()
 def insert(a,b,before=False):
  nonlocal s
  require(s.count(a)==1,'observer anchor '+a)
  m='! INTEGRATION_TEST_BEGIN\n'+b+'! INTEGRATION_TEST_END\n';s=s.replace(a,m+a if before else a+m)
 insert('  module module_mp_udm\n','  use udm_population_test, only: capture,fixed_cf,test_scenario\n')
 state='[ncr(k,i,1),ncr(k,i,2),ncr(k,i,3),qci(k,i,1),qrs(k,i,1),cldf(k),footprint(k)]'
 def rows(tag,extra=''):
  v=state if not extra else state[:-1]+','+extra+']'
  return '   do k=kts,ktopini\n     call capture("'+tag+'",i,k,loop,'+v+')\n   enddo\n'
 insert('   if (present(udm_cldfra)) udm_cldfra(i,kts:kte)=cldf(:)\n','''   cldf(kts:ktopini)=fixed_cf
   if(trim(test_scenario)=="substeps" .and. loop>1) cldf(kts:ktopini)=.8
   if(trim(test_scenario)=="cfzero") cldf(kts:ktopini)=0.
''',True)
 insert('   footprint(:)=cldf(:)\n',rows('GRID'))
 insert('! The ambient/free CCN reservoir remains grid mean.',rows('PHASE_DONE'),True)
 insert('! warm rain processes\n',rows('WARM_LOCAL'))
 insert('! Restore states AND tendencies once, before existing grid donor/update limits.\n',rows('RATES_LOCAL',','.join(n+'(k)' for n in RATES)),True)
 insert('! cold rain processes\n',rows('RATES_GRID',','.join(n+'(k)' for n in RATES)))
 insert('                                        ccn_returned,ccn_clipped)\n','''               call capture("EXCHANGE",i,k,loop, &
                 [ncr(k,i,1),ncr(k,i,3),footprint(k),ccn_returned,ccn_clipped])
''')
 cap='       if (source>hvalue) then\n'
 # Merely observe all original limiter branches.
 s=s.replace(cap,cap+'! INTEGRATION_TEST_BEGIN\n         call capture("LIMIT",i,k,loop,[source,hvalue])\n! INTEGRATION_TEST_END\n')
 require(re.sub(r'! INTEGRATION_TEST_BEGIN\n.*?! INTEGRATION_TEST_END\n','',s,flags=re.S).encode()==raw,'observer must reverse to exact source')
 return s.encode()

def fixture(root):
 old=load(root/'test/rrtmgp/test_udm_partial_population.py','old_generator')
 s=old.fixture((root/'test/rrtmgp/test_udm_partial_activation.f90').read_bytes()).decode()
 s=s.replace('  real :: fixed_cf=1.','  real :: fixed_cf=1.\n  character(16) :: test_scenario="warm"')
 s=s.replace('  candidate=trim(mode)=="candidate"','  candidate=trim(mode)=="candidate"\n  test_scenario=scenario')
 s=s.replace('fixed_cf=2.**(1-b)','fixed_cf=2.**(1-b)\n      if(b==3) fixed_cf=.7')
 s=s.replace('integer::step(1,1),top(1,1),a,b,k,iteration','integer::step(1,1),top(1,1),a,b,k,iteration,pol\n  real :: call_dt')
 s=s.replace('       udm_funct_lb2017_setup,fsvp_water','       udm_funct_lb2017_setup,fsvp_water,udm_return_rain_ccn,udm_warm_representation')
 s=s.replace('  real :: call_dt','  real :: call_dt,ccn_probe,rain_probe,returned_probe,clipped_probe,f_probe,original(4),state_probe(4)')
 s=s.replace('  call udm_funct_lb2017_setup','  call udm_funct_lb2017_setup\n  call_dt=10.\n  if(trim(scenario)=="substeps") call_dt=360.\n  pol=0\n  if(candidate) pol=1')
 s=s.replace('      rh=1.','      rh=1.\n      if(trim(scenario)=="evap") rh=.1')
 s=s.replace('      if(trim(scenario)=="melt") qi=fixed_cf*1.e-5','''      if(trim(scenario)=="evap") then
        qc=0.; qr=fixed_cf*1.e-7
      endif
      if(trim(scenario)=="reject") qi=fixed_cf*1.e-5
''')
 s=s.replace('delt=.01,','delt=call_dt,').replace('number_policy=1)','number_policy=1,population_policy=pol)')
 s=s.replace('  do a=1,2',"""  ! Direct production exchange and representation helpers, including cap.
  do a=1,4
    f_probe=real(a)*.25
    if(a==3) f_probe=.7
    do b=1,2
      ccn_probe=2.e8
      if(b==2) ccn_probe=2.e10-4096.
      rain_probe=10000.
      call udm_return_rain_ccn(ccn_probe,rain_probe,f_probe,returned_probe,clipped_probe)
      if(rain_probe/=0.) error stop 'rain exchange incomplete'
      if(abs(returned_probe+clipped_probe-f_probe*10000.)>.002) error stop 'exchange accounting'
      if(b==1 .and. clipped_probe/=0.) error stop 'unexpected CCN clipping'
      if(b==2 .and. a>1 .and. clipped_probe<=0.) error stop 'cap not tested'
      write(*,'(A,2I3,5ES20.10)') 'EXCHANGE_PROBE',a,b,f_probe,ccn_probe,rain_probe,returned_probe,clipped_probe
    enddo
  enddo
  original=[.004,.002,5.e8,1.e5];state_probe=original
  ! No-process re-expression .5 -> .8 -> .7: always start from grid state.
  do a=1,3
    f_probe=.5
    if(a==2) f_probe=.8
    if(a==3) f_probe=.7
    call udm_warm_representation(state_probe(1),state_probe(2),state_probe(3),state_probe(4),f_probe,.true.)
    call udm_warm_representation(state_probe(1),state_probe(2),state_probe(3),state_probe(4),f_probe,.false.)
    if(any(abs(state_probe-original)>16.*epsilon(1.)*original)) error stop 'artificial representation source'
  enddo
  print *, 'REPRESENTATION_PROBE_PASS'
  do a=1,2""")
 return s.encode()

def parse(text):
 obs={};out={};w=text.splitlines();i=0
 while i<len(w):
  a=w[i].split();i+=1
  if not a or a[0] not in ('OBS','RETURN'):continue
  b=w[i].split();i+=1;require(len(b)==int(a[-1]),'record size')
  v=[struct.unpack('!f',bytes.fromhex(x))[0] for x in b];require(all(math.isfinite(x) for x in v),'nonfinite actual output')
  if a[0]=='RETURN':out[int(a[1])]=b
  else:obs[a[1],*map(int,a[2:6])]=v
 require(len(out)==6,'six actual calls missing');return obs,out

def analyze(records):
 decisions={};exchanges=0;limits=0;comparisons=0
 for scenario in ('warm','evap','substeps'):
  d,outputs=records[scenario,'candidate','on'];off=records[scenario,'candidate','off'][1]
  require(outputs==off,'observer ON/OFF changes actual return')
  current=records[scenario,'current','off'][1]
  for c in (1,4):
   # Fixed diagnostic CF changes after first substep only in substeps case.
   if scenario!='substeps':require(outputs[c]==current[c],'CF1 reduction differs')
  exchanges+=sum(k[0]=='EXCHANGE' for k in d)
  limits+=sum(k[0]=='LIMIT' for k in d)
  for key,v in d.items():
   if key[0]!='RATES_LOCAL':continue
   _,c,i,k,loop=key;g=d['RATES_GRID',c,i,k,loop];f=v[6]
   require(v[5]==f,'snapshot differs from diagnosed CF')
   for slot in (1,2,3,4,*range(7,15)):
    require(near(g[slot],f32(v[slot]*f)),'state/rate restored with wrong CF');comparisons+=1
   require(g[0]==v[0],'ambient CCN conditioned')
  if scenario=='evap':require(any(k[0]=='EXCHANGE' for k in d),'complete evaporation branch not reached')
  if scenario=='substeps':
   require({key[-1] for key in d if key[0]=='GRID'}=={1,2},'two actual substeps missing')
   require(all(v[6]==f32(.8) for key,v in d.items() if key[0]=='GRID' and key[-1]==2),'next CF not rediagnosed')
  decisions[scenario]={'UDM_calls':18,'observer_preserves_return':True}
 require(limits>0,'real-dt donor limiting never exercised')
 return {'status':'PASS_SCOPED_ACTUAL_POPULATION_INTEGRATION','comparisons':comparisons,'complete_evaporation_records':exchanges,'active_donor_records':limits,'scenarios':decisions,'production_accepted':False}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--workdir',required=True,type=Path);a=ap.parse_args();root=a.wrf_root.resolve();work=a.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
 raw=(root/'phys/module_mp_udm.F').read_bytes();(work/'production.F').write_bytes(raw);(work/'observed.F').write_bytes(observed(raw));(work/'fixture.f90').write_bytes(fixture(root))
 runner_mod=load(root/'test/rrtmgp/test_netcdf_zz.py','runner');runner=runner_mod.Runner(work,180,{**os.environ,'OMP_NUM_THREADS':'1'},80)
 report={'schema':'UDM_POPULATION_INTEGRATION_V1','source_sha256':sha(raw),'script_sha256':sha(Path(__file__).read_bytes()),'processes':[],'results':{},'production_accepted':False}
 def save():report['processes']=runner.commands;runner_mod.write_json(work/'receipt.json',report)
 try:
  fc=Path(shutil.which('gfortran')).resolve()
  for opt in ('O0','O2'):
   d=work/opt;d.mkdir();flags=['-'+opt,'-g','-ffree-form','-ffree-line-length-none','-fcheck=all','-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-J',str(d),'-I',str(d)]
   stub=d/'errors.f90';stub.write_text('module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\ninteger,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\nsubroutine wrf_error_fatal(text)\ncharacter(*),intent(in)::text\nprint *,text\nerror stop 2\nend subroutine\n');objects=[]
   for p,extra in [(root/'phys/module_gfs_machine.F',['-ffixed-form']),(stub,[]),(root/'phys/module_mp_radar.F',[]),(work/'fixture.f90',['-cpp','-DOBSERVER_ONLY'])]:
    obj=d/(p.stem+'.o');runner.run([fc,*flags,*extra,'-c',p,'-o',obj],d,'compile_dependency');objects.append(obj)
   data={}
   for variant in ('production','observed'):
    obj=d/(variant+'.o');runner.run([fc,*flags,'-c',work/(variant+'.F'),'-o',obj],d,'compile_'+variant);exe=d/variant;runner.run([fc,*flags,'-cpp',work/'fixture.f90',*objects,obj,'-o',exe],d,'link_'+variant)
    for scenario in (['warm'] if variant=='production' else ['warm','evap','substeps']):
     for mode in (['candidate'] if variant=='production' else ['current','candidate']):
      for enabled in (['off'] if variant=='production' or mode=='current' else ['on','off']):
       output=runner.run([exe,mode,scenario,enabled],d,'UDM_'+variant+'_'+scenario+'_'+mode+'_'+enabled)
       text=output.read_text();require(text.count('EXCHANGE_PROBE')==8 and 'REPRESENTATION_PROBE_PASS' in text,'actual helper probes missing');parsed=parse(text)
       if variant=='production':report.setdefault('production_returns',{})[opt]=parsed[1]
       data[scenario,mode,enabled]=parsed
   report['results'][opt]=analyze(data)
   for c in (1,4):require(report['production_returns'][opt][c]==data['warm','candidate','off'][1][c],'CF1 actual unmodified diagnostic path differs')
   for scenario,message in [('reject','warm-only column required'),('cfzero','CF0 condensate unsupported')]:
    try:
     runner.run([d/'observed','candidate',scenario,'on'],d,'UDM_expected_reject_'+scenario)
     raise ValueError('unsupported state accepted')
    except RuntimeError:
     text=(work/f'command-{len(runner.commands):02d}.stdout').read_text()
     require(message in text and 'RETURN ' not in text and runner.commands[-1]['actual_returncode']!=0,'wrong unsupported-state rejection')
   save()
  require((root/'phys/module_mp_udm.F').read_bytes()==raw and sha(Path(__file__).read_bytes())==report['script_sha256'],'source changed during experiment')
  require(report['results']['O0']==report['results']['O2'],'optimization result differs')
  report.update(status=report['results']['O2']['status'],actual_UDM_calls=120,expected_scope_rejections=4,physical_gate_closed=False);save();print(json.dumps({'status':report['status'],'receipt':str(work/'receipt.json')}))
 except BaseException as e:report.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':main()
