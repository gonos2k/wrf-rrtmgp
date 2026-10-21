#!/usr/bin/env python3
"""Replay actual bounded operands; no NetCDF, model, compiler or fitted tolerance."""
import json,math,struct

def require(condition,message):
 if not condition:raise ValueError(message)
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def decode(h):return struct.unpack('<f',struct.pack('<I',int(h,16)))[0]
def bits(x):return f'{struct.unpack("<I",struct.pack("<f",x))[0]:08x}'
def rows(raw):
 result=[]
 for line in raw.decode().splitlines():
  p=line.split();result.append({'kind':p[0],'species':int(p[1]),'rk':int(p[2]),'source_time_s':float(p[3]),'bits':[h.lower() for h in p[4:]],'values':[decode(h) for h in p[4:]]})
 return result

def analyze(read,plan):
 a=json.loads(read('analysis.json'));trace=rows(read('host/boundary-closeout.txt'));require(a['trace_records']==trace,'analysis detached from actual trace')
 require(len(trace)==36,'bounded trace record count')
 positive=[];final=[]
 def find(kind,sp,t):
  found=[r for r in trace if (r['kind'],r['species'],r['source_time_s'])==(kind,sp,t)];require(len(found)==1,'missing/duplicate actual call');return found[0]
 for time in [21540.,21600.,21660.]:
  for sp in [1,2]:
   pre=find('relax-before',sp,time);post=find('relax-after',sp,time);before,model,b,bt,dt,fc,gc,*fl=pre['values']
   require(find('wrapper-before',sp,time)['bits']==pre['bits'][:1] and find('wrapper-after',sp,time)['bits']==post['bits'],'wrapper/core source mismatch')
   target=f32(b+f32(dt*bt));require(bits(f32(target-model))==bits(fl[0]),'actual target/model mismatch')
   lap=fl[1]
   for x in fl[2:]:lap=f32(lap+x)
   lap=f32(lap-f32(4*fl[0]));expected=f32(f32(before+f32(fc*fl[0]))-f32(gc*lap))
   require(bits(expected)==post['bits'][0],'native relaxation arithmetic')
   delta=post['values'][0]-before
   if time>21540:
    require(target>model and delta>0,'positive host relaxation not demonstrated')
    positive.append({'species':sp,'source_time_s':time,'actual_dtbc_s':dt,'S_target':target,'S_model':model,'tendency_before':before,'tendency_after':post['values'][0],'actual_tendency_increment':delta,'units':'Pa kg_dry^-1 s^-1 for tendency; Pa kg_dry^-1 for S'})
   else:require(delta==0,'zero first endpoint changed')
   f=find('final',sp,time);v,vt,fd,bfield,xmu,xmsf,out,mu,c1,c2=f['values']
   require(bits(f32(v+f32(fd*vt)))==bits(bfield),'final bfield native interpolation')
   require(bits(f32(f32(c1*mu)+c2))==bits(xmu),'call-time native mass factor')
   require(bits(f32(f32(xmsf*bfield)/xmu))==bits(out),'native final-value arithmetic')
   sf=find('solve-final',sp,time);require(sf['bits'][0]==bits(out) and sf['bits'][1]==bits(mu),'actual final caller operands')
   h=next(x for x in a['final_vs_history'] if x['species']==sp and x['source_time_s']==time)
   require(h['actual_eta_bits']==bits(out),'actual history differs from final native result')
   _,mut,mu2,mub,hc1,hc2,hd=sf['values'];require(hc1==c1 and hc2==c2 and hd==fd,'final/history clock or coefficients differ')
   require(bits(mu2)==h['history_MU_bits'] and bits(mub)==h['history_MUB_bits'],'final/history physical MU differs')
   histmu=f32(mu2+mub);hista=f32(f32(c1*histmu)+c2);histeta=f32(bfield/hista)
   require(bits(histmu)==h['history_total_mass_bits'] and bits(hista)==h['history_factor_bits'] and bits(histeta)==h['history_eta_reconstruction_bits'],'history reconstruction operands')
   require(h['interior_number_max']>0,'interior number lost')
   if time>21540:require(bits(xmu)!=bits(hista) and bits(out)!=bits(histeta),'reported last-bit distinction missing')
   final.append({'species':sp,'source_time_s':time,'dtbc_s':fd,'actual_eta':out,'actual_eta_bits':bits(out),'call_MU_total_bits':bits(mut),'history_MU_total_bits':bits(histmu),'call_factor_bits':bits(xmu),'history_factor_bits':bits(hista),'call_factor_Pa':xmu,'history_factor_Pa':hista,'history_eta_reconstruction':histeta,'history_eta_reconstruction_bits':bits(histeta)})
 host=json.loads(read('host/receipt.json'));require(host['status']=='SUCCESS' and host['observer_compared_pairs']==675,'observer replay did not complete')
 count=0
 for time,entries in host['observer_inventory'].items():
  require(len(entries)==225,'observer variable exclusion')
  for n,row in entries.items():require(row['reference_sha256']==row['observed_sha256'],'observer changes history');count+=1
 require(count==675,'observer pair count')
 native=read('halo/command-03.stdout').decode();expected={(p,m) for p in [0,1] for m in range(1,5)};seen=set()
 for line in native.splitlines():
  if line.startswith('HALO_POLICY_METHOD_PASS'):_,p,m=line.split();seen.add((int(p),int(m)))
 require(seen==expected and 'COMMON_SPECIFIED_HALO_COMPLETE' in native,'common specified halo coverage')
 fixture=read('halo/common_halo.f90').decode()
 for phrase in ['physical MU modified','halo not newest physical edge','non-idempotent whole halo','tile partition/order changed halo']:require(phrase in fixture,'native property assertion missing')
 for key,n in [('build',5),('host',1),('halo',3)]:
  receipt=json.loads(read(key+'/receipt.json'));require(len(receipt['commands'])==n,'qualified process count '+key)
  for cmd in receipt['commands']:require(cmd['actual_returncode']==0 and not cmd['timed_out'],'qualified command failure '+key)
 require(plan['unchanged_production_source'] is True and plan['physical_accuracy_approved'] is False,'scope promotion')
 return {'status':'BOUNDED_SPECIFIED_BOUNDARY_CLOSEOUT_COMPLETE','actual_positive_host_relaxation_calls':positive,'actual_native_final_values':final,'observer_noninterference_array_pairs':675,'observer_compared_variables':225,'observer_compared_times':3,'common_native_halo_policy_tile_cases':8,'common_native_halo_properties':['physical cells unchanged','newest physical edge copied','repeat call idempotent','whole versus four ordered/decomposed tile methods equal'],'PR189_restart_criterion':'RETAINED_675_PAIR_PASS_NOT_RERUN','production_source_or_defaults_changed':False,'last_bit_explanation':'actual final uses c1*MUTS+c2; history uses c1*fl(MU_2+MUB)+c2; both evaluations reproduce exactly from their different operands','number1_MPI_or_OpenMP_support_added':False,'physical_accuracy_approved':False,'existing_seven_conditions_and_reference_FAILs':'PRESERVED','production_accepted':False,'new_model_runs':0}
