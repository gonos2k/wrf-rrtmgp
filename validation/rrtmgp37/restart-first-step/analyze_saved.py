#!/usr/bin/env python3
"""Stdlib replay of the actual first arithmetic witness and original criterion."""
import hashlib,json,math,struct,re
def require(ok,message):
 if not ok:raise ValueError(message)
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def bits(x):return struct.pack('<f',x).hex()
def hex32(x):return f'{struct.unpack("<I",struct.pack("<f",x))[0]:08x}'
def fields(raw):
 out={};pos=0
 while pos<len(raw):
  key,*shape=struct.unpack_from('<32s3i',raw,pos);pos+=44;count=math.prod(shape);values=struct.unpack_from('<'+'f'*count,raw,pos);pos+=4*count;out[key.rstrip().decode()]=(shape,values)
 require(pos==len(raw),'witness binary layout');return out
def at(field,i,j,k=0):
 # File shape is i,k,j for 3-D, i,j,1 for 2-D.
 shape,values=field;offset=i+shape[0]*(j if shape[2]==1 else k+shape[1]*j);return values[offset]
def inventory(row,pairs,delta):
 require(row['variables']==225 and row['array_pairs']==pairs,'original 225-variable criterion changed')
 count=0;different=0
 for time,entries in row['inventory'].items():
  require(len(entries)==225,'excluded history variable')
  for name,e in entries.items():
   same=e['left_sha256']==e['right_sha256'];require(same==e['bitwise_equal'],'false bitwise inventory flag')
   count+=1;different+=not same
 require(count==pairs and different==delta and len(row['differences'])==delta,'history mismatch inventory')
 require(row['all_bitwise_equal']==(different==0),'false full-host restart promotion')
def analyze(read,plan):
 a=json.loads(read('analysis.json'));w=a['first_operator_witness']
 require(plan['original_restart_seconds']==21540 and plan['original_end_seconds']==21720,'original restart time changed')
 inventory(a['original_restart'],675,23);inventory(a['fixed_restart'],675,0)
 inventory(a['observer_continuous'],1125,0);inventory(a['observer_restart'],675,0)
 expected_times=['2016-10-06_06:00:00','2016-10-06_06:01:00','2016-10-06_06:02:00']
 require(a['fixed_restart']['common_times']==expected_times,'restart witness times changed')
 require(a['full_host_restart_bitwise_criterion_passed'] is True,'fixed criterion is not passed')
 profiles={};entry={}
 for arm in ['continuous','restart']:
  entry[arm]=fields(read('witness/'+arm+'/probe-021540-r0-a00-entry.bin'))
  after=fields(read('witness/'+arm+'/probe-021540-r1-a00-rk_prep.bin'))
  profiles[arm]=[hex32(at(after['ww'],4,7,k)) for k in range(45)]
  require(profiles[arm]==w['WW_profile_i23_j99'][arm],'recorded WW differs from actual stencil')
  e=entry[arm];mu=at(e['mu_2'],4,8);physical=at(e['mu_2'],4,7)
  require(hex32(mu)==w['MU_halo_i23_j100'][arm]['bits'],'MU halo bit witness')
  require(physical==w['MU_physical_point_i23_j99'],'physical edge witness')
  values=[mu,at(e['mub'],4,8),physical,at(e['mub'],4,7)];v=values[0];partial=[]
  for x in values[1:]:v=f32(v+x);partial.append(hex32(v))
  require(partial==w['MUV_i23_j100'][arm]['partial_sum_bits'],'first native mass addition changed')
  require(hex32(f32(.5*v))==w['MUV_i23_j100'][arm]['bits'],'MUV arithmetic')
 require(w['MU_halo_i23_j100']['continuous']['bits']=='45000f90' and w['MU_halo_i23_j100']['restart']['bits']=='45000f91','stale halo not isolated')
 require(w['MUV_i23_j100']['continuous']['partial_sum_bits'][0]=='47b7ad8a' and w['MUV_i23_j100']['restart']['partial_sum_bits'][0]=='47b7ad8b','first sum witness')
 for name in entry['continuous']:
  c=entry['continuous'][name];r=entry['restart'][name];require(c[0]==r[0],'input shape')
  ii,kk,jj=c[0];physical=[]
  for j in range(8 if jj==1 else (9 if name=='v_2' else 8)):
   for k in range(1 if jj==1 else (45 if name in ['w_2','ph_2'] else 44)):
    for i in range(ii):
     x=at(c,i,j,k);y=at(r,i,j,k);require(bits(x)==bits(y),'initialized physical input differs: '+name);physical.append(x)
 require(profiles['continuous']!=profiles['restart'],'original WW divergence missing')
 native=read('native/command-03.stdout').decode();require('ACTUAL_FIRST_WW_REPLAY_COMPLETE' in native,'native first-operation replay did not complete')
 got={1:[],2:[],3:[]}
 for line in native.splitlines():
  if line.startswith('WW '):_,arm,k,h=line.split();got[int(arm)].append(h.lower())
 require(got[1]==profiles['continuous'] and got[2]==profiles['restart'],'native old/restart replay')
 require(got[3]==profiles['restart'],'native halo repair did not recover all WW bits')
 fixture=read('native/replay.f90').decode();require("error stop 'physical mass changed'" in fixture,'native physical mass preservation assertion missing')
 require(a['checkpoint']=={'UDM_NUMBER_POLICY':1,'UDM_POPULATION_POLICY':0,'UDM_SPECIFIED_NUMBER_CONTRACT':1},'checkpoint contract')
 src=a['boundary_source']
 for arm,rows in a['boundary'].items():
  for row in rows:
   sec=row['elapsed_s'];rec=int(sec//21600);dt=sec-rec*21600
   require(rec==row['record'] and dt==row['record_elapsed_s'],'boundary record clock')
   target=[f32(x+f32(dt*y)) for x,y in zip(src['MU_values'][rec],src['MU_tendencies'][rec])]
   require(target==row['south_MU'],'next actual boundary record not applied')
   require(row['NC_NR_edge_max']=={'QNCLOUD':0.,'QNRAIN':0.},'zero original prescribed number changed')
  require(rows[-1]['record']==1,'second forcing record not reached')
 require(a['radiation_phase']['continuous']==a['radiation_phase']['restart']=={'LW':[21600.0],'SW':[]},'actual radiation phase differs')
 for key,commands in [('build',3),('probe_build',4),('native',3),('fixed',2),('probe',2),('nonzero',1)]:
  receipt=json.loads(read(key+'/receipt.json'));require(len(receipt['commands'])==commands,'qualified command count '+key)
  for c in receipt['commands']:require(c['actual_returncode']==0 and not c['timed_out'],'qualified process failure '+key)
 for arm in ['continuous','restart']:
  nml=read('fixed/'+arm+'/namelist.input').decode();require(re.search(r'\btime_step\s*=\s*60,',nml),'time step changed')
  require(re.search(r'\brrtmgp_udm_frozen_optics\s*=\s*1,',nml),'experimental frozen configuration changed')
  log=read('fixed/command-0'+('1' if arm=='continuous' else '2')+'.stdout').decode()
  require('SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log,'real fixed WRF did not complete')
 nz=json.loads(read('nonzero/receipt.json'));require(nz['status']=='SUCCESS' and len(nz['observed'])==3,'nonzero branch not executed')
 require(sorted(nz['changed_forcing_variables'])==sorted(['QCLOUD_BYS','QCLOUD_BTYS','QRAIN_BYS','QRAIN_BTYS','QNCLOUD_BYS','QNCLOUD_BTYS','QNRAIN_BYS','QNRAIN_BTYS']),'nonselected forcing changed')
 for row in nz['observed']:
  require(row['record']==1,'nonzero next record not used');dt=row['record_elapsed_s']
  for name,values in row['numbers'].items():
   require(values['interior_max']>0,'internal number erased')
   payload=nz['fields'][name];s=f32(payload['value_record1']+f32(dt*payload['slope_record1']))
   require(s==values['coupled'][0][1],'nonzero stored S interpolation')
   require(all(math.isfinite(v) and (v>0 if dt else v==0) for level in values['actual'] for v in level),'nonzero actual host boundary value')
 require(nz['patch']['donor_temperature_K'][0]>273.15,'manufactured patch not warm')
 return {'status':'FIRST_NATIVE_WW_DIVERGENCE_LOCALIZED_AND_ORIGINAL_RESTART_FIXED','first_cause':'final specified MU left stale physical halo; calc_ww_cp consumes it before physics','first_witness_Fortran':{'i':23,'j':99,'halo_j':100},'first_MU_sum_bits_continuous_restart':['47b7ad8a','47b7ad8b'],'original_differing_array_pairs':23,'fixed_differing_array_pairs':0,'compared_array_pairs':675,'full_host_restart_bitwise_criterion_passed':True,'observer_noninterference_array_pairs':1800,'native_WW_profile_levels_per_arm':45,'nonzero_actual_host_record_transition':'EXPLICIT_WARM_PATCH_OUTER_VALUES_AND_INTERNAL_PRESERVATION_OBSERVED','nonzero_relaxation_strip':'zero in these three samples; no separate positive relaxation-source validation claimed','physical_accuracy_approved':False,'production_defaults_changed':False,'existing_seven_conditions_and_reference_FAILs':'PRESERVED','production_accepted':False,'new_model_runs':0}
