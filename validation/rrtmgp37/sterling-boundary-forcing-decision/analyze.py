"""Replay actual pressure-coupled five-point source; no inferred wind gating or water-budget closure."""
import math,struct,collections,json
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def parse(blob,complete=True):
 tags={'context':15,'core':29,'accepted':6,'pd_before':7,'pd_after':7};out={n:{} for n in tags}
 for line in blob.decode().splitlines():
  w=line.split();t=float(w[0]);tag=w[1];x=list(map(float,w[2:]));require(tag in tags and len(x)==tags[tag] and all(math.isfinite(v) for v in x),'record schema/finite')
  require(t in range(57600,61200,60),'wrong source time')
  key=(t,int(x[0])) if tag=='context' else (t,*map(int,x[:3]));require(key not in out[tag],'duplicate record');out[tag][key]=x
 if complete:
  steps=range(57600,61200,60);sp=range(1,8);layers=range(1,45)
  require(set(out['context'])=={(t,s) for t in steps for s in sp},'missing context')
  wanted={(t,s,j,k) for t in steps for s in sp for j in range(95,99) if j==97 or t%600==0 for k in layers}
  for tag in ['accepted','pd_before','pd_after']:require(set(out[tag])==wanted,'missing '+tag)
  # Actual relax_zone4 visits north rows96:98; coefficient5=0 is retained in context, not a fictitious core call at95.
  require(set(out['core'])=={key for key in wanted if key[2]>=96},'missing/unexpected actual north core')
 return out

def evaluate(blob,complete=True):
 r=parse(blob,complete);groups={};core_exact=error_exact=pd_exact=0;limited=0;pd_source_diff=0
 for (t,sp),x in r['context'].items():
  require(x[:7]==[sp,1.,60.,20.,1.,4.,0.],'actual RK/step/zone metadata differs')
  require(x[10]==x[14]==0. and x[7]>x[8]>x[9]>0 and x[11]>x[12]>x[13]>0,'actual coefficient ramp/inner zero')
 for key,x in r['core'].items():
  t,sp,j,k=key;_,_,_,b,dtbc,F,G,before,after=x[:9];S=x[9:14];B=x[14:19];BT=x[19:24];E=x[24:29];ctx=r['context'][t,sp]
  require(int(b)==100-j and F==ctx[7+int(b)-2] and G==ctx[11+int(b)-2],'actual coefficient/index mismatch')
  target=[f32(z+f32(dtbc*bt)) for z,bt in zip(B,BT)];want=[f32(b-s) for b,s in zip(target,S)];require(want==E,'five-point interpolated error mismatch');error_exact+=5
  lap=f32(f32(f32(f32(E[1]+E[2])+E[3])+E[4])-f32(4.*E[0]))
  expected=f32(f32(before+f32(F*E[0]))-f32(G*lap));require(expected==after,'native source arithmetic mismatch');core_exact+=1
  ac=r['accepted'][key];require(ac[3]>0,'nonpositive pressure coupling');require(ac[5]==after or sp==1,'condensate accepted source changed after raw core');limited+=int(ac[5]!=after)
  if sp>1:require(all(z==0 for z in B+BT),'nonzero actual condensate boundary target')
  g=groups.setdefault((sp,j),{'samples':0,'raw_positive':0,'raw_negative':0,'raw_zero':0,'accepted_positive':0,'accepted_negative':0,'S_center_nonzero':0,'fivepoint_S_nonzero':0,'max_center_pressure_q':0.,'max_neighbour_pressure_q':0.,'min_raw_delta_Pa_q_per_s':0.,'max_raw_delta_Pa_q_per_s':0.,'min_accepted_delta_Pa_q_per_s':0.,'max_accepted_delta_Pa_q_per_s':0.,'zeroth_term_min':0.,'zeroth_term_max':0.,'spatial_term_min':0.,'spatial_term_max':0.})
  delta=after-before;accepted=ac[5]-before;zero=F*E[0];spatial=-G*(math.fsum(E[1:])-4*E[0]);g['samples']+=1;g['raw_positive']+=delta>0;g['raw_negative']+=delta<0;g['raw_zero']+=delta==0;g['accepted_positive']+=accepted>0;g['accepted_negative']+=accepted<0;g['S_center_nonzero']+=S[0]!=0;g['fivepoint_S_nonzero']+=any(z!=0 for z in S);g['max_center_pressure_q']=max(g['max_center_pressure_q'],S[0]);g['max_neighbour_pressure_q']=max(g['max_neighbour_pressure_q'],*S[1:])
  for name,val in [('raw_delta_Pa_q_per_s',delta),('accepted_delta_Pa_q_per_s',accepted)]:
   g['min_'+name]=min(g['min_'+name],val);g['max_'+name]=max(g['max_'+name],val)
  for name,val in [('zeroth_term',zero),('spatial_term',spatial)]:g[name+'_min']=min(g[name+'_min'],val);g[name+'_max']=max(g[name+'_max'],val)
 for key,x in r['pd_before'].items():
  y=r['pd_after'][key];require(x[:5]==y[:5] and x[3]==60. and x[4]>0 and y[6]==0.,'actual PD dt/coupling/reset')
  numerator=f32(f32(x[4]*x[5])+f32(x[3]*x[6]));require(f32(numerator/x[4])==y[5],'actual full PD source update mismatch');pd_exact+=1
  # Source observed here includes all earlier physics/boundary operations, not only relaxation.
  pd_source_diff+=x[6]!=r['accepted'][key][5]
 names=['QVAPOR','QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL'];summary=[{'species':names[s-1],'j':j,**g} for (s,j),g in sorted(groups.items())]
 site=[g for g in summary if g['j']==97 and g['species']!='QVAPOR'];removed=sum(g['accepted_negative'] for g in site)
 return {'status':'ACTUAL_FIVE_POINT_BOUNDARY_ATTRIBUTION_COMPLETE' if complete else 'PARTIAL_DEVELOPMENT_ONLY','actual_context_records':len(r['context']),'actual_core_records':len(r['core']),'actual_error_operands_replayed':error_exact,'actual_raw_tendency_updates_replayed':core_exact,'actual_full_source_PD_updates_replayed':pd_exact,'actual_QV_wrapper_limited_records':limited,'PD_source_not_equal_to_post_relax_records':pd_source_diff,'runtime':{'spec_zone':1,'relax_zone':4,'spec_exp':0,'dt_seconds':60,'relax_rk_step':1,'relax_rk_dt_seconds':20,'source_application_rk_step':3,'source_dt_seconds':60,'north_core_rows':[96,97,98],'row95_coefficient5_F_G':[0,0],'row95_core_called':False},'groups':summary,'original_site_condensate_direct_removal_count':removed,'scope':'original i37,j97 all60 source steps, all44layers and7water species; j96/98 only six600s source phases; j95 accepted andPD observed but outside actual core; no independent face flux or kg/m2 budget inferred from Pa-coupled tendencies','component_terms_float64_diagnostics':'F*E0 and -G*fivepointLaplacian evaluated from actual operands; native REAL32 update is separately replayed exactly','boundary_causality_proven':False,'optical_change_justified':False,'production_changes':False}
