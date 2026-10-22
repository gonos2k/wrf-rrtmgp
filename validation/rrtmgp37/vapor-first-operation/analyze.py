"""Saved operand analysis. Predictor undershoots are separate from final states."""
import math,struct
from collections import Counter

def require(x,message):
 if not x:raise ValueError(message)
def f32(x):return struct.unpack('f',struct.pack('f',x))[0]
def vapor(text):
 events=[];summaries=[]
 for line in text.splitlines():
  a=line.split();t=int(float(a[0]));tag=a[1];rk=int(a[2])
  if tag.startswith('summary_'):
   summaries.append({'source_s':t,'tag':tag[8:],'rk':rk,'new_negatives':int(a[3]),'minimum':float(a[4])});continue
  v=list(map(float,a[6:]));require(len(v)==10,'vapor operands')
  events.append({'source_s':t,'tag':tag,'rk':rk,'native_i_j_k':list(map(int,a[3:6])),'before':v[0],'after':v[1],'base':v[2],'source':v[3],'advection':v[4],'mapy':v[5],'mass_old':v[6],'mass_new':v[7],'dt':v[8],'native_replay':v[9]})
 finals=[s for s in summaries if (s['tag']=='rk' and s['rk']==3) or s['tag'] in ['pd','micro','final_bdy']]
 return {'events':events,'summaries':summaries,'events_by_tag_rk':dict(Counter(e['tag']+str(e['rk']) for e in events)),
 'final_stage_negative_samples':sum(s['new_negatives'] for s in finals),'final_stage_minimum':min(s['minimum'] for s in finals),
 'predictor_negative_samples':sum(s['new_negatives'] for s in summaries if s['tag']=='rk' and s['rk']<3),
 'source_steps':len({s['source_s'] for s in summaries if s['tag']=='final_bdy'})}
def causes(original_text,components_text):
 v=vapor(original_text);r=next(e for e in v['events'] if e['tag']=='rk' and e['rk']==3)
 require(r['source_s']==60 and r['native_i_j_k']==[7,49,20],'first transport witness changed')
 require(r['after']==r['native_replay'] and r['source']==0,'native transport replay')
 tendency=f32(f32(r['advection']*r['mapy'])+r['source']);numerator=f32(f32(r['mass_old']*r['base'])+f32(r['dt']*tendency))
 require(numerator==-3.725290298461914e-9,'first transport numerator')
 p=next(e for e in v['events'] if e['tag']=='pd')
 require(p['source_s']==42180 and p['native_i_j_k']==[88,98,22],'first PD source witness changed')
 require(p['before']>=0 and p['after']<0 and p['after']==p['native_replay'],'native source replay')
 c={}
 for line in components_text.splitlines():
  a=line.split()
  if float(a[0])==42180:c[a[1]]=float(a[2])
 require(c['pbl_after']>0 and c['CU_after']==c['CU_before'],'earlier physics incorrectly blamed')
 require(c['relax_before']>0 and c['relax_after']==p['source']<0,'relaxation witness detached')
 require(c['spec_before']==c['spec_after']==p['source'],'later specified source changed witness')
 return {'first_final_transport':r,'native_transport_numerator':numerator,'first_PD_source':p,'actual_source_components':c,'original_final_negative_events':v['final_stage_negative_samples'],'original_predictor_negative_events':v['predictor_negative_samples'],'conclusions':['finite-arithmetic saturated PD face flux overdraw','negative external relaxation exchange precedes PD source overdraw'],'CU_or_PBL_cause_at_source_witness':False}
def comparisons(d):
 for name,n in [('original_first',2925),('original_components',1575),('corrected_observer',675),('corrected_restart',450)]:
  x=d[name];require(x['pairs']==n and not x['differences'],name+' history differs')
  require(sum(len(a) for a in x['inventory'].values())==n,name+' array roster')
  for rows in x['inventory'].values():
   require(len(rows)==225,name+' missing arrays')
   for row in rows.values():require(row['equal'] and row.get('left_sha256',row.get('original_sha256'))==row.get('right_sha256',row.get('actual_sha256')),name+' detached equal flag')
 return {n:{'pairs':x['pairs'],'differences':len(x['differences'])} for n,x in d.items()}
def native_source(text):
 rows=[]
 require('NATIVE_SOURCE_EXCHANGE_COMPLETE' in text,'native source fixture incomplete')
 for line in text.splitlines():
  a=line.split()
  if len(a)!=6 or not a[0].isdigit():continue
  i=int(a[0]);v=list(map(float,a[1:]));rows.append([i,*v])
  if i in [1,5]:require(v[3]<0 and v[4]>=0 and v[2]>v[1],'native source limiter failed')
  else:require(v[1]==v[2] and v[3]==v[4],'unaffected source changed')
 require(len(rows)==6,'native source case coverage')
 return rows
def native_transport(text):
 rows=[];require('NATIVE_SHARED_FLUX_COMPLETE' in text,'native shared flux fixture incomplete')
 for line in text.splitlines():
  a=line.split()
  if len(a)!=7 or not a[0].isdigit():continue
  order,mode=map(int,a[:2]);v=list(map(float,a[2:]));rows.append([order,mode,*v])
  require(v[3]>=0,'native final transport numerator negative')
  require(abs(v[1])<=64*2**-23*max(v[4],1e-30),'native periodic divergence not roundoff-sized')
  if mode<=2:require(v[1]==0 and v[2]==0,'constant or zero field changed')
 require(len(rows)==6,'native transport case coverage')
 return rows
def face_replay(text,event):
 rows={}
 for line in text.splitlines():
  a=line.split();require(float(a[0])==60,'first face time changed');rows[a[1]]=list(map(float,a[3:]))
 require(set(rows)=={'before','after','tendency'},'first face stages missing')
 b=rows['before'];a=rows['after'];require(len(a)==len(b)==25,'first face operands')
 require(a[0]==event['base'] and a[:13]==b[:13] and a[19:]==b[19:],'face state or low-order flux changed')
 scale=f32(b[11]/f32(b[12]+f32(1e-20)))
 require(all(f32(x*scale)==y for x,y in zip(b[13:19],a[13:19])),'original actual saturated donor scale')
 sub=lambda x,y:f32(x-y);add=lambda x,y:f32(x+y);mul=lambda x,y:f32(x*y)
 # The native divergence accumulates z, then x, then y; preserve its parentheses.
 diff=lambda h,l,hh,ll:sub(add(sub(h,l),hh),ll)
 t=sub(0,mul(a[9],diff(a[18],a[17],a[24],a[23])))
 t=sub(t,mul(a[5],mul(a[7],diff(a[14],a[13],a[20],a[19]))))
 t=sub(t,mul(a[5],mul(a[8],diff(a[16],a[15],a[22],a[21]))))
 require(t==rows['tendency'][0]==event['advection'],'actual face divergence replay')
 numerator=add(mul(event['mass_old'],event['base']),mul(event['dt'],mul(t,event['mapy'])))
 require(numerator<0 and f32(numerator/event['mass_new'])==event['after'],'face-to-native RK negative witness')
 return {'source_s':60,'native_i_j_k':[7,49,20],'actual_high_order_donor_scale':scale,'actual_divergence_tendency':t,'native_RK_numerator':numerator,'all_six_outgoing_faces_reproduced':True,'low_order_fluxes_preserved':True}
