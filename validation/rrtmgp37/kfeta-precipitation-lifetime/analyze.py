import math
def require(x,m):
 if not x:raise ValueError(m)
def native_rows(text):
 out={}
 for l in text.splitlines():
  a=l.split()
  if a and a[0]=='NATIVE':out[(int(a[1]),int(a[2]))]=list(map(float,a[3:]))
 require(len(out)==15 and 'NATIVE_LIFETIME_COMPLETE' in text,'native coverage')
 return out
def analyze(d):
 old=native_rows(d['native/command-06.stdout'].decode());new=native_rows(d['native/command-08.stdout'].decode())
 for scheme in [11,10]:
  require(d[f'native/before/scheme-{scheme}.bin']==d[f'native/after/scheme-{scheme}.bin'],'non-KF scheme changed')
  require(all(old[(scheme,s)]==new[(scheme,s)] for s in range(1,6)),'non-KF trace changed')
 for s in [1,2]:
  require(old[(1,s)][0]==new[(1,s)][0] and old[(1,s)][4]==new[(1,s)][4],'last valid precipitation lost')
 require(new[(1,2)][1:4]==[15.,0.,0.],'last valid RAINCV must outlive expired rate')
 require(new[(1,3)][0]==40 and new[(1,3)][1:4]==[0.,0.,0.],'inactive rate reused')
 require(new[(1,3)][6]==45,'last valid surface delivery lost')
 require(new[(1,4)][0]==70 and new[(1,4)][1]==30 and new[(1,4)][2]==0,'reactivation interval lost')
 require(new[(1,5)][0]==70 and new[(1,5)][6]==75,'reactivation surface delivery or repeated rain')
 rows={}
 for l in d['host/observed/kfeta-lifetime.txt'].decode().splitlines():
  a=l.split();key=(int(float(a[0])),a[1]);require(key not in rows,'duplicate host record');rows[key]=list(map(float,a[2:]))
 times=sorted(t for t,k in rows if k=='ppt_after');require(times==list(range(21540,21960,60)),'short host timing changed')
 expired=[];reactivated=[]
 for t in times:
  post=rows[(t,'ppt_after')];pre=rows[(t,'ppt_before')];physical=rows[(t,'physics_before')]
  require(all(x==0 for x in post[6:9]),'native accumulated/interval arithmetic mismatch')
  require(post[11]==0 and post[13]==0,'expiry rate not cleared or active rate changed')
  require(physical[4]==0,'next surface input differs from last valid interval')
  if post[9]>0:
   require(post[10]>0 and post[12]>0,'no positive expiry/last surface interval witness')
   expired.append({'source_time_s':t,'columns':int(post[9]),'prior_rate_sum_mm_s':post[10],'expired_rate_sum_after':post[11],'last_valid_RAINCV_sum_mm':post[12]})
  if rows[(t,'physics_after')][5]>0:reactivated.append({'source_time_s':t,'columns':int(rows[(t,'physics_after')][5])})
 require(expired and any(x['source_time_s']==21840 for x in reactivated),'actual scheduled reactivation absent')
 import json
 history=json.loads(d['host/history-comparison.json']);require(history['pairs']==1575 and len(history['inventory'])==7,'observer coverage')
 require(not history['differences'],'observer changed candidate')
 for a in history['inventory'].values():
  require(len(a)==225,'history omission')
  require(all(v['equal'] and v['public_sha256']==v['observed_sha256'] for v in a.values()),'observer array changed')
 return {'status':'KFETA_PRECIPITATION_LIFETIME_FIXED_IN_BOUNDED_TESTS','native_public_calls':30,'unmodified_MSKF_KFCUP_fixture_arrays':True,'actual_host_seconds':420,'actual_host_expirations':expired,'actual_scheduled_reactivations':reactivated,'observer_equal_array_pairs':1575,'original_24h_result':'historical PR192 evidence retained; no corrected 24h forecast claimed here','negative_vapor':'separate investigation; not fixed or masked here','scientific_water_conservation_approved':False,'frozen_accuracy_approved':False,'production_defaults_changed':False,'original_seven_conditions_changed':False,'new_model_runs_in_saved_replay':0}
