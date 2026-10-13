#!/usr/bin/env python3
"""Actual UDM diagnosed-clear residual transition and warm mass/latent budget."""
import argparse,hashlib,importlib.util,json,math,os,re,shutil,struct,sys
from pathlib import Path
sys.dont_write_bytecode=True

def load(p,n):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(b):return hashlib.sha256(b).hexdigest()
def near(a,b,scale=1.):return abs(a-b)<=32*2**-23*max(abs(a),abs(b),abs(scale),1.e-30)

def fixture(root):
 old=load(root/'test/rrtmgp/test_udm_population_integration.py','setup');s=old.fixture(root).decode()
 s=s.replace('  pol=0\n  if(candidate) pol=1','  pol=2\n  if(trim(mode)=="strict") pol=1')
 s=s.replace('      fixed_cf=2.**(1-b)\n      if(b==3) fixed_cf=.7','      fixed_cf=1.')
 s=s.replace('      rh=1.','      rh=.5')
 s=s.replace('      if(trim(scenario)=="evap") then','''      qc=0.; qr=1.e-4
      if(b==2) qc=5.e-7
      if(b==3) then
        qc=5.e-7; qr=0.
      endif
      if(trim(scenario)=="evap") then''')
 s=s.replace('      nn=2.e8/den; nc=fixed_cf*5.e8/den; nr=fixed_cf*1.e5/den','      nn=2.e8/den; nc=5.e5/den; nr=1.e5/den')
 return s.encode()

def observer(raw):
 s=raw.decode();s=s.replace('  module module_mp_udm\n','  module module_mp_udm\n! CF0_TEST_BEGIN\n  use udm_population_test,only:capture\n! CF0_TEST_END\n')
 state='[q(k,i),qci(k,i,1),qrs(k,i,1),ncr(k,i,1),ncr(k,i,2),ncr(k,i,3),t(k,i),cpm(k,i),xlv(k,i),dtcld,prevp(k),praut(k),pracw(k),cldf(k),footprint(k)]'
 def rows(tag):return '   do k=kts,ktopini\n     call capture("'+tag+'",i,k,loop,'+state+')\n   enddo\n'
 def add(a,b,before=False):
  nonlocal s
  require(s.count(a)==1,'observer anchor');block='! CF0_TEST_BEGIN\n'+b+'! CF0_TEST_END\n';s=s.replace(a,block+a if before else a+block)
 add('   footprint(:)=cldf(:)\n',rows('CF_BEFORE'))
 add('! update the slope parameters for microphysics computation\n',rows('CF_AFTER'))
 pos=s.index('       hvalue = max(qmin,qci(k,i,1))\n');pos=s.rfind('   do k = ktop, kts, -1\n',0,pos)
 s=s[:pos]+'! CF0_TEST_BEGIN\n'+rows('BULK_BEFORE')+'! CF0_TEST_END\n'+s[pos:]
 add('! ccn activaiton and condensation/evaporation of clouds\n',rows('BULK_AFTER'))
 require(re.sub(r'! CF0_TEST_BEGIN\n.*?! CF0_TEST_END\n','',s,flags=re.S).encode()==raw,'observer not reversible')
 return s.encode()

def parse(text):
 d={};out={};lines=text.splitlines();i=0
 while i<len(lines):
  w=lines[i].split();i+=1
  if not w or w[0] not in ('OBS','RETURN'):continue
  words=lines[i].split();i+=1;require(len(words)==int(w[-1]),'record size')
  v=[struct.unpack('!f',bytes.fromhex(x))[0] for x in words];require(all(math.isfinite(x) for x in v),'nonfinite actual values')
  if w[0]=='OBS':d[w[1],*map(int,w[2:6])]=v
  else:out[int(w[1])]=words
 require(len(out)==6,'six successful cases missing');return d,out

def analyze(on,off):
 obs,out=on;require(out==off[1],'observer changes UDM return');count=0;max_water=0.;max_latent=0.
 for c in range(1,7):
  for k in range(1,4):
   pre=obs['CF_BEFORE',c,1,k,1];post=obs['CF_AFTER',c,1,k,1]
   require(pre[13]==0. and post[13]==0. and post[14]==1.,'clear cloud CF or residual footprint differs')
   require(pre[:10]==post[:10],'CF0 resolution introduced water/number/temperature source')
   a=obs['BULK_BEFORE',c,1,k,1];b=obs['BULK_AFTER',c,1,k,1];water=sum(b[:3])-sum(a[:3]);max_water=max(max_water,abs(water))
   require(near(sum(b[:3]),sum(a[:3]),sum(a[:3])),'warm bulk water budget')
   expected=a[8]/a[7]*a[10]*a[9];actual=b[6]-a[6];max_latent=max(max_latent,abs(actual-expected))
   require(near(actual,expected,a[6]),'warm bulk latent budget')
   count+=1
 return {'status':'PASS_SCOPED_ACTUAL_CF0_TRANSITION','states':['rain_only','residual_cloud_and_rain','residual_cloud_only'],'active_cell_budgets':count,'max_bulk_water_residual_kg_kg':max_water,'max_bulk_temperature_rounding_residual_K':max_latent,'cloud_CF_unchanged':True,'resolution_has_no_artificial_source':True,'production_accepted':False}

def main():
 ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--workdir',required=True,type=Path);a=ap.parse_args();root=a.wrf_root.resolve();b=a.workdir.resolve();b.mkdir(parents=True,exist_ok=False);raw=(root/'phys/module_mp_udm.F').read_bytes();(b/'production.F').write_bytes(raw);(b/'observed.F').write_bytes(observer(raw));(b/'fixture.f90').write_bytes(fixture(root))
 helpers=load(root/'test/rrtmgp/test_netcdf_zz.py','runner');runner=helpers.Runner(b,180,{**os.environ,'OMP_NUM_THREADS':'1'},40);r={'schema':'ACTUAL_CF0_TRANSITION_V1','source_sha256':sha(raw),'script_sha256':sha(Path(__file__).read_bytes()),'results':{},'processes':[],'production_accepted':False}
 def save():r['processes']=runner.commands;helpers.write_json(b/'receipt.json',r)
 try:
  fc=Path(shutil.which('gfortran')).resolve()
  for opt in ('O0','O2'):
   d=b/opt;d.mkdir();f=['-'+opt,'-g','-ffree-form','-ffree-line-length-none','-fcheck=all','-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-J',str(d),'-I',str(d)]
   stub=d/'errors.f90';stub.write_text('module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\ninteger,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\nsubroutine wrf_error_fatal(text)\ncharacter(*),intent(in)::text\nprint *,text\nerror stop 2\nend subroutine\n');objects=[]
   for p,extra in [(root/'phys/module_gfs_machine.F',['-ffixed-form']),(stub,[]),(root/'phys/module_mp_radar.F',[]),(b/'fixture.f90',['-cpp','-DOBSERVER_ONLY'])]:
    obj=d/(p.stem+'.o');runner.run([fc,*f,*extra,'-c',p,'-o',obj],d,'compile_dependency');objects.append(obj)
   data={}
   for name in ('production','observed'):
    obj=d/(name+'.o');runner.run([fc,*f,'-c',b/(name+'.F'),'-o',obj],d,'compile_'+name);exe=d/name;runner.run([fc,*f,'-cpp',b/'fixture.f90',*objects,obj,'-o',exe],d,'link_'+name)
    for enabled in (['off'] if name=='production' else ['on','off']):
     p=runner.run([exe,'candidate','warm',enabled],d,'UDM_'+name+'_'+enabled);data[name,enabled]=parse(p.read_text())
   require(data['production','off'][1]==data['observed','off'][1],'unmodified production return differs')
   r['results'][opt]=analyze(data['observed','on'],data['observed','off']);save()
  require(r['results']['O0']==r['results']['O2'],'optimization changes result');r.update(status='PASS_SCOPED_ACTUAL_CF0_TRANSITION',actual_UDM_calls=36);save();print(json.dumps({'status':r['status'],'receipt':str(b/'receipt.json')}))
 except BaseException as e:r.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':main()
