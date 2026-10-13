#!/usr/bin/env python3
"""Execute actual full UDM melting: fixed production, observer, old-order control.

Manufactured CF=1 isolates the order defect; no partial-cloud/PSD approval.
"""
import argparse, hashlib, importlib.util, json, math, os, re, shutil, struct, sys
from pathlib import Path
sys.dont_write_bytecode=True

def load(p,name):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m

def require(ok,msg):
 if not ok:raise ValueError(msg)

def f32(x):return struct.unpack('!f',struct.pack('!f',x))[0]
def bits(x):return struct.pack('!f',x)

CLEAR='! Clear only after the mass-dependent melt number has consumed the ice.\n         qci(k,i,2) = 0.\n'
START='       if(.not.ifice(k) .and. qci(k,i,2)>0.) then\n'
END='         ncr(k,i,2) = min(ncr(k,i,2) + ni(k),ncmax)\n'
VEC='[qci(k,i,1),qci(k,i,2),t(k,i),ncr(k,i,2),den(k,i),cldf(k),cpm(k,i),xlf0,qcmin,ncmax]'

def observe(raw,fixed):
 s=raw.decode();blocks=[]
 def insert(anchor,body,before=False):
  nonlocal s
  require(s.count(anchor)==1,'ambiguous observer anchor')
  w='! MELT_TEST_BEGIN\n'+body+'! MELT_TEST_END\n';s=s.replace(anchor,w+anchor if before else anchor+w)
 insert('  module module_mp_udm\n','   use udm_test_observer, only: capture\n')
 insert(START,'         call capture("MELT_PRE",i,k,loop,'+VEC+')\n')
 insert(CLEAR if fixed else END,'         call capture("MELT_POST",i,k,loop,'+VEC[:-1]+',ni(k)])\n')
 stripped=re.sub(r'! MELT_TEST_BEGIN\n.*?! MELT_TEST_END\n','',s,flags=re.S)
 require(stripped.encode()==raw,'observer changes production bytes')
 return s.encode()

def analyze(results):
 rows=[]
 for policy in (0,1):
  plain=results['fixed',policy];cur=results['observed',policy];olddata=results['old_order',policy]
  require(plain['outputs']==cur['outputs'] and plain['tags']==cur['tags'],'observer changed full UDM returns')
  obs=cur['observations'];legacy=olddata['observations']
  require(len(obs)==24 and set(obs)==set(legacy),'actual melt branch not reached at all 12 active cells')
  for case in range(1,5):
   for k in range(1,4):
    pre=obs['MELT_PRE',case,1,k,1];post=obs['MELT_POST',case,1,k,1];opre=legacy['MELT_PRE',case,1,k,1];opost=legacy['MELT_POST',case,1,k,1]
    require(pre==opre and pre[5]==1. and pre[1]>0.,'CF=1/positive ice/pre-state differs')
    temp=f32(pre[4]*max(pre[1],pre[8]));temp=f32(math.sqrt(f32(math.sqrt(f32(f32(temp*temp)*temp)))))
    expected=min(max(f32(f32(5.38e7)*temp),1000.),1.e6)
    require(bits(post[10])==bits(expected) and post[10]>1000.,'melt number lost incoming ice dependence')
    require(post[3]==min(f32(pre[3]+post[10]),pre[9]),'native NC increment/cap differs')
    require(post[0:3]==opost[0:3] and post[1]==0.,'mass/latent heat changed in melt block')
    require(opost[10]==1000.,'old-order defect not reproduced')
    require(post[0]==f32(pre[0]+pre[1]),'water transfer')
    latent=f32(f32(f32(pre[7]/pre[6])*pre[1])*pre[5]);require(post[2]==f32(pre[2]-latent),'latent heat update')
    rows.append({'policy':policy,'case':case,'layer':k,'rho':pre[4],'CF':pre[5],'ice_before':pre[1],'new_Nmelt':post[10],'old_Nmelt':opost[10],'NC_after_block':post[3],'NC_final_host':struct.unpack('!f',bytes.fromhex(cur['outputs'][case][36+k-1]))[0]})
  for c in range(1,5):
   low=[r for r in rows if r['policy']==policy and r['case']==c and r['layer']==1][0]
   if c in (2,4):
    prior=[r for r in rows if r['policy']==policy and r['case']==c-1 and r['layer']==1][0];require(low['new_Nmelt']>prior['new_Nmelt'],'ice-mass response absent')
 require(results['observed',0]['observations']==results['observed',1]['observations'],'number bridge changes native melting')
 return rows

def main():
 ap=argparse.ArgumentParser();ap.add_argument('wrf_root',type=Path);ap.add_argument('--workdir',required=True,type=Path);args=ap.parse_args()
 root=args.wrf_root.resolve();work=args.workdir.resolve();work.mkdir(parents=True,exist_ok=False)
 tests=root/'test/rrtmgp';partial=load(tests/'test_udm_partial_activation.py','partial');bridge=load(tests/'test_udm_dry_number_bridge.py','bridge');helper=load(tests/'test_netcdf_zz.py','helper')
 partial.STAGES=('MELT_PRE','MELT_POST')
 raw=(root/'phys/module_mp_udm.F').read_bytes();s=raw.decode();require(s.count(CLEAR)==1,'fixed clear absent')
 old=s.replace(CLEAR,'').replace('         t(k,i) = t(k,i) - xlf0/cpm(k,i)*qci(k,i,2)*cldf(k)\n','         t(k,i) = t(k,i) - xlf0/cpm(k,i)*qci(k,i,2)*cldf(k)\n         qci(k,i,2) = 0.\n').encode()
 # Unchanged full public wrapper; warm positive ice reaches actual native melt.
 fixture=bridge.fixture((tests/'test_udm_partial_activation.f90').read_bytes(),'wet').decode()
 fixture=fixture.replace('rh=1.+.0048*exp(log(target_alpha)/.6)','rh=1.')
 fixture=fixture.replace('qc=1.e-4; qi=0.; qr=0.; qs=0.; qg=0.; qh=0.','qc=1.e-3; qi=1.e-5; qr=0.; qs=0.; qg=0.; qh=0.\n      if(b==2) qi=1.e-4')
 (work/'fixture.f90').write_text(fixture)
 variants={'fixed':raw,'observed':observe(raw,True),'old_order':observe(old,False)}
 for name,code in variants.items():(work/(name+'.F')).write_bytes(code)
 runner=helper.Runner(work,120,{**os.environ,'LC_ALL':'C','OMP_NUM_THREADS':'1'},100)
 report={'schema':'UDM_ICE_MELT_ORDER_V1','status':'PREPARED','source_sha256':hashlib.sha256(raw).hexdigest(),'production_accepted':False,'full_WRF_runs':0,'results':{},'processes':[]}
 def save():report['processes']=runner.commands;helper.write_json(work/'receipt.json',report)
 save()
 try:
  compiler=Path(shutil.which('gfortran')).resolve();runner.run([compiler,'--version'],work,'compiler_version')
  for opt in ('O0','O2'):
   d=work/opt;d.mkdir();flags=['-'+opt,'-g','-ffree-form','-ffree-line-length-none','-fcheck=all','-finit-real=snan','-ffpe-trap=invalid,zero,overflow','-J',str(d),'-I',str(d)]
   stub=d/'errors.f90';stub.write_text('module module_wrf_error\ncontains\nsubroutine wrf_debug(level,text)\ninteger,intent(in)::level\ncharacter(*),intent(in)::text\nend subroutine\nend module\nsubroutine wrf_error_fatal(text)\ncharacter(*),intent(in)::text\nprint *,text\nerror stop 2\nend subroutine\n')
   objects=[]
   for p,extra in [(root/'phys/module_gfs_machine.F',['-ffixed-form']),(stub,[]),(root/'phys/module_mp_radar.F',[]),(work/'fixture.f90',['-cpp','-DOBSERVER_ONLY'])]:
    obj=d/(p.stem+'.o');runner.run([compiler,*flags,*extra,'-c',p,'-o',obj],d,'compile_dependency');objects.append(obj)
   results={}
   for name in variants:
    obj=d/(name+'.o');runner.run([compiler,*flags,'-c',work/(name+'.F'),'-o',obj],d,'compile_'+name)
    exe=d/name;runner.run([compiler,*flags,'-cpp',work/'fixture.f90',*objects,obj,'-o',exe],d,'link_'+name)
    for policy in (0,1):
     out=runner.run([exe,'on',str(policy)],d,'UDM_'+name+'_policy'+str(policy));results[name,policy]=partial.parse(out.read_text())
   rows=analyze(results)
   report['results'][opt]={'rows':rows,'observer_returns_bitwise_equal':True,'mass_and_temperature_block_bitwise_equal_to_old_order':True,'both_number_policies_native_equal':True};save()
  require(report['results']['O0']==report['results']['O2'],'optimization changes diagnostics')
  require((root/'phys/module_mp_udm.F').read_bytes()==raw,'source changed during test')
  report.update(status='PASS_SCOPED_ACTUAL_UDM_MELT_ORDER',UDM_calls=48,limits=['Actual full UDM manufactured calls, CF=1, two densities and two ice amounts; not WRF forecast or physical Nmelt calibration.','Old-order control changes only clear location; later processes may modify final NC.','Partial-CF population, species PSD/LUT, independent accuracy remain open.']);save();print(json.dumps({'status':report['status'],'receipt':str(work/'receipt.json')}))
 except BaseException as e:report.update(status='FAIL_PRESERVED',error=repr(e));save();raise
if __name__=='__main__':main()
