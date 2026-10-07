#!/usr/bin/env python3
"""Saved-only audit for the authorized positive-NC target-j2 OFF/ON run."""
import hashlib, json, math, pathlib, re, sys
import numpy as np
from netCDF4 import Dataset

ROOT=pathlib.Path(__file__).resolve().parents[2]
STAGE=ROOT/'build/udm37-positive-nc-stage-runtime-2min-v2/stage'
OUT=pathlib.Path(sys.argv[1]) if len(sys.argv)>1 else pathlib.Path(__file__).with_name('result.json')
QNN_RE=re.compile(r'^qnn_d(\d+)_rank(\d+)_tile(\d+)_step(\d+)_rk(\d+)_side(\d+)\.raw$')
NUM_RE=re.compile(r'^number_d(\d+)_tile(\d+)_i(\d+)_j(\d+)_step(\d+)_stage(\d+)_sub(\d+)\.raw$')
BOUNDARY={1:{'dest':(23,1),'source':(23,2),'axis':'Y-start'},2:{'dest':(68,99),'source':(68,98),'axis':'Y-end'},
          3:{'dest':(1,74),'source':(2,74),'axis':'X-start'},4:{'dest':(90,26),'source':(89,26),'axis':'X-end'}}
NUM_STAGES={10:0,11:0,20:0,21:1,23:1,30:1,31:1,40:0,50:0,51:0}

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(p):return {'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def f32(x):return float(np.float32(x))

def audit_qnn():
 files=sorted((STAGE/'on/capture').glob('*.raw'))
 expected={(rank,tile,step,rk,side) for rank,tile,side in [(0,1,1),(1,2,4),(2,1,3),(3,2,2)] for step in (1,2) for rk in (1,2,3)}
 seen=set(); branches={0:0,1:0};rho=[];pins=[];row_count=0;counts_by_side={}
 bounds={1:(1,45,1,25),2:(46,90,76,99),3:(1,45,51,75),4:(46,90,26,50)}
 for p in files:
  m=QNN_RE.fullmatch(p.name)
  if not m:raise ValueError(f'QNN filename {p.name}')
  d,rank,tile,step,rk,side=map(int,m.groups());key=(rank,tile,step,rk,side)
  if d!=1 or key not in expected or key in seen:raise ValueError(f'QNN key {key}')
  seen.add(key);lines=p.read_text().splitlines()
  if lines[0]!='UDM37QNNB1' or len(lines)!=46:raise ValueError(f'QNN packet shape/magic {p.name}')
  h=list(map(int,lines[1].split()));dest=BOUNDARY[side]['dest']
  if h != [1,step,rk,rank,tile,side,*dest,1,44,32,*bounds[side]]:raise ValueError(f'QNN header {p.name}: {h}')
  for k,line in enumerate(lines[2:],1):
   f=line.split()
   if len(f)!=18:raise ValueError(f'QNN row token count {p.name}/{k}')
   it=list(map(int,f[:5]));x=[float(v) for v in f[5:]]
   if it[0]!=k or it[4]!=1 or not all(math.isfinite(v) for v in x):raise ValueError(f'QNN bad row {p.name}/{k}')
   _,br,si,sj,_=it;vel,ccn,q0,q1,nc0,nc1,nr0,nr1,al,alb,saved_sum,saved_rho,source_qnn=x
   if br not in (0,1) or nc0!=nc1 or nr0!=nr1:raise ValueError(f'QNN branch/passivity {p.name}/{k}')
   inflow=vel>=0. if side in (1,3) else vel<=0.
   if br!=int(inflow):raise ValueError(f'QNN velocity branch {p.name}/{k}')
   if br:
    if (si,sj,source_qnn)!=(0,0,0.) or ccn!=1.e8 or q1!=ccn:raise ValueError(f'QNN CCN assignment {p.name}/{k}')
   elif (si,sj)!=BOUNDARY[side]['source'] or q1!=source_qnn:
    raise ValueError(f'QNN source-copy {p.name}/{k}')
   s32=f32(f32(al)+f32(alb));r32=f32(1.0/s32)
   if saved_sum!=s32 or saved_rho!=r32 or s32<=0 or r32<=0:raise ValueError(f'QNN default REAL32 density {p.name}/{k}')
   branches[br]+=1;rho.append(saved_rho)
  row_count+=44;pins.append(pin(p));counts_by_side[str(side)]=counts_by_side.get(str(side),0)+44
 if seen!=expected or len(files)!=24 or row_count!=1056:raise ValueError('QNN packet roster incomplete')
 return {'status':'PASS_SCOPED_QNN_BOUNDARY_ROWS','packet_count':24,'row_count':1056,'keys':'4 selected sides × 2 model steps × 3 RK values; header/file identity exact','branches':{'outflow':branches[0],'inflow':branches[1]},'rows_per_side':counts_by_side,'density_replay':{'source_expression':'default REAL32 sum AL+ALB, then default REAL32 reciprocal','count':len(rho),'min':min(rho),'max':max(rho),'all_1056_exact':True},'capture_pins':pins}

def parse_number(p):
 lines=p.read_text().splitlines()
 if len(lines)!=47 or lines[0]!='UDM37NUM1':raise ValueError(f'number packet shape/magic {p.name}')
 h=list(map(int,lines[1].split()));clock=[float(x) for x in lines[2].split()]
 rows=[]
 for k,line in enumerate(lines[3:],1):
  f=line.split()
  if len(f)!=15 or int(f[0])!=k:raise ValueError(f'number row layout {p.name}/{k}')
  vals=[float(v) for v in f[1:]]
  if not all(math.isfinite(v) and f32(v)==v for v in vals):raise ValueError(f'number finite/default REAL32 {p.name}/{k}')
  rows.append(vals)
 return h,clock,np.asarray(rows,dtype=np.float64)

def audit_number():
 files=sorted((STAGE/'on/number_capture').glob('*.raw'))
 expected={(step,stage,sub) for step in (1,2) for stage,sub in NUM_STAGES.items()}
 seen=set();pack={};clocks={};positive_entry={};positive_helper={};pins=[];optional_masks={};
 for p in files:
  m=NUM_RE.fullmatch(p.name)
  if not m:raise ValueError(f'number filename {p.name}')
  d,tile,i,j,step,stage,sub=map(int,m.groups());key=(step,stage,sub)
  if (d,tile,i,j)!=(1,1,23,2) or key not in expected or key in seen:raise ValueError(f'number identity {p.name}')
  seen.add(key);h,clock,a=parse_number(p)
  if h != [1,step,stage,sub,1,23,2,1,44,32,({10:0,11:0,20:0,21:17,23:17,30:17,31:29,40:0,50:0,51:2}[stage]),int(step==1)]:raise ValueError(f'number header {p.name}: {h}')
  want_clock=[float(step-1),60.,1.e8]
  if clock!=want_clock:raise ValueError(f'number clock {p.name}: {clock}')
  if str(step) in clocks and clocks[str(step)]!=clock:raise ValueError('number step clocks disagree')
  clocks[str(step)]=clock;pack[key]=a;pins.append(pin(p));optional_masks[str(stage)]=h[10]
  wet=(a[:,3]>0)&(a[:,6]>0)
  if stage==20:positive_entry[step]={int(k):bool(v) for k,v in zip(range(1,45),wet)}
  if stage==50:positive_helper[step]={int(k):bool(v) for k,v in zip(range(1,45),wet)}
 if seen!=expected or len(files)!=20:raise ValueError(f'number roster {len(files)}/20')
 # each row is [T,P,QV,QC,QR,QNN,QNC,QNR,DEN,DEND,RE,NC_ACT,PC_ACT,DT]
 init={}; transitions={}
 for step in (1,2):
  a,b=pack[(step,10,0)],pack[(step,11,0)]
  init[str(step)]={'active_flag':int(step==1),'qnn_pre_range':[float(a[:,5].min()),float(a[:,5].max())],
   'qnn_post_range':[float(b[:,5].min()),float(b[:,5].max())],
   'step1_qnn_post_all_ccn':bool(np.all(b[:,5]==np.float32(1.e8))) if step==1 else None,
   'qnn_changed_levels':int(np.count_nonzero(a[:,5]!=b[:,5])),
   'qc_exact':bool(np.array_equal(a[:,3],b[:,3])),'qnc_exact':bool(np.array_equal(a[:,6],b[:,6]))}
  if not init[str(step)]['qc_exact'] or not init[str(step)]['qnc_exact']:raise ValueError('host initializer altered QC/QNC in captured rows')
  transitions[str(step)]={}
  for left,right in [(10,11),(11,20),(20,21),(21,23),(23,30),(30,31),(31,40),(40,50),(50,51)]:
   sub_l=NUM_STAGES[left];sub_r=NUM_STAGES[right];x=pack[(step,left,sub_l)];y=pack[(step,right,sub_r)]
   transitions[str(step)][f'{left}->{right}']={
     'different_elements_by_field':{n:int(np.count_nonzero(x[:,ix]!=y[:,ix])) for ix,n in enumerate(['T','P','QV','QC','QR','QNN','QNC','QNR','DEN','DEND','RE','NC_ACT','PC_ACT','DT'])},
     'exact_fields':[n for ix,n in enumerate(['T','P','QV','QC','QR','QNN','QNC','QNR','DEN','DEND','RE','NC_ACT','PC_ACT','DT']) if np.array_equal(x[:,ix],y[:,ix])]}
  # The activation hooks bracket the loop; report zero activity, not a closure PASS.
  a,b=pack[(step,30,1)],pack[(step,31,1)]
  if not np.all(b[:,11]==0) or not np.all(b[:,12]==0):raise ValueError('activation rates were not zero in this saved case')
  if not np.array_equal(a[:,6],b[:,6]):raise ValueError('zero activation rates yet QNC changed across 30/31')
 # Source-order liquid helper replay in default REAL32; constants from source.
 pi=f32(f32(4.)*f32(math.atan(1.0)));rho_water=f32(1000.);pidnc=f32(f32(pi*rho_water)/f32(6.));obmr=f32(f32(1.)/f32(3.))
 radius={};helper_positives=[]
 for step in (1,2):
  x=pack[(step,50,0)];y=pack[(step,51,0)];qc=x[:,3].astype(np.float32);nc=x[:,6].astype(np.float32);rho=x[:,8].astype(np.float32);actual=y[:,10].astype(np.float32)
  if not np.array_equal(x[:,:9],y[:,:9]):raise ValueError('helper changed an input row across stages50/51')
  expected=np.full(44,np.float32(2.51e-6),dtype=np.float32);wet=[]
  for z in range(44):
   rqc=max(np.float32(1.e-12),np.float32(qc[z]*rho[z]));rnc=max(np.float32(1.e-6),np.float32(nc[z]*rho[z]))
   if rqc>np.float32(1.e-12) and rnc>np.float32(1.e-6):
    # source: lamc=(pidnc*nc/rqc)**obmr; re=.5*(1/lamc), clamped in meters
    ratio=np.float32(np.float32(pidnc*nc[z])/rqc)
    lam=np.float32(np.float32(ratio)**obmr)
    re=np.float32(np.float32(.5)*np.float32(np.float32(1.)/lam))
    expected[z]=max(np.float32(2.51e-6),min(re,np.float32(50.e-6)))
    wet.append(z+1)
  if not np.array_equal(actual,expected):
   raise ValueError(f'helper radius source replay differs at step{step}: {np.flatnonzero(actual!=expected).tolist()}')
  helper_positives.extend((step,k) for k in wet)
  radius[str(step)]={'active_levels_1based':wet,'active_count':len(wet),'output_equals_independent_source_order_float32_replay_all_44':True,
                     'RE_CLOUD_m_min':float(actual.min()),'RE_CLOUD_m_max':float(actual.max()),'clamp_bounds_m':[2.51e-6,50.e-6]}
 if positive_entry.keys()!=positive_helper.keys():raise ValueError('entry/helper step keys differ')
 same=sorted((s,k) for s in positive_entry for k,v in positive_entry[s].items() if v and positive_helper[s][k])
 return {'status':'PASS_SCOPED_NUMBER_STAGE_READBACK','packet_count':20,'row_count':880,'unique_identity':'2 steps × 10 declared stages, all at d1/i23/j2/tile1/k1:44; no invented RK identifier',
  'clocks_minutes':clocks,'history_time_mapping':{'step1':'2016-10-06_00:00:00','step2':'2016-10-06_00:01:00','note':'number packet XTIME is explicit; no stage packet at the final 00:02 history record'},
  'availability_masks':optional_masks,'initializer':init,'stage_field_change_counts':transitions,
  'positive_QC_and_QNC_rows':{'stage20':sum(sum(v.values()) for v in positive_entry.values()),'stage50':sum(sum(v.values()) for v in positive_helper.values()),'same_step_k_intersection':[[s,k] for s,k in same]},
  'activation':{'stage30_to31_QNC_exact_by_step':{str(s):bool(np.array_equal(pack[(s,30,1)][:,6],pack[(s,31,1)][:,6])) for s in (1,2)},'stage31_NC_ACT_RATE_all_zero':True,'stage31_PC_ACT_RATE_all_zero':True,'interpretation':'NON_DISCRIMINATING_ACTIVATION_NOT_OCCURRED; no activation-closure claim.'},
  'liquid_radius':{'source_expression':'REAL32 clamp(0.5 * (1 / ((pidnc * NC / max(1e-12, QC*DEN)) ** REAL32(1/3))), 2.51e-6 m, 50e-6 m); pidnc=REAL32(REAL32(pi*1000)/6), pi=REAL32(4*atan(1))','cases':radius,'output_matches_source_order_replay':True,'physical_unit_authority':False},
  'packet_pins':pins}

def times(ds):
 v=ds.variables['Times'];v.set_auto_maskandscale(False);return [b''.join(x).decode('ascii') for x in np.asarray(v[:])]
def ncattrs_equal(a,b):
 if a.ncattrs()!=b.ncattrs():return False
 for name in a.ncattrs():
  x,y=a.getncattr(name),b.getncattr(name)
  if isinstance(x,np.ndarray) or isinstance(y,np.ndarray):
   if not isinstance(x,np.ndarray) or not isinstance(y,np.ndarray) or x.dtype!=y.dtype or x.shape!=y.shape or x.tobytes()!=y.tobytes():return False
  elif isinstance(x,np.generic) or isinstance(y,np.generic):
   if np.asarray(x).dtype!=np.asarray(y).dtype or np.asarray(x).tobytes()!=np.asarray(y).tobytes():return False
  elif x!=y:return False
 return True
def audit_outputs():
 names=['wrfout_d01_2016-10-06_00:00:00','wrfrst_d01_2016-10-06_00:02:00'];out={}
 for name in names:
  a,b=STAGE/'off'/name,STAGE/'on'/name
  if sha(a)!=sha(b) or a.stat().st_size!=b.stat().st_size:raise ValueError(f'OFF/ON bytes differ for {name}')
  q={'off':pin(a),'on':pin(b),'whole_file_bytes_exact':True}
  with Dataset(a) as da,Dataset(b) as db:
   if list(da.variables)!=list(db.variables):raise ValueError(f'OFF/ON variable roster differs {name}')
   if not ncattrs_equal(da,db):raise ValueError(f'OFF/ON global attributes differ {name}')
   dims_a={k:(len(v),v.isunlimited()) for k,v in da.dimensions.items()}
   dims_b={k:(len(v),v.isunlimited()) for k,v in db.dimensions.items()}
   if dims_a!=dims_b:raise ValueError(f'OFF/ON dimensions differ {name}')
   variable_checks=[]
   for vname in da.variables:
    va,vb=da.variables[vname],db.variables[vname]
    va.set_auto_maskandscale(False);vb.set_auto_maskandscale(False)
    va.set_auto_chartostring(False);vb.set_auto_chartostring(False)
    xa=np.asarray(va[...] if va.ndim==0 else va[:]);xb=np.asarray(vb[...] if vb.ndim==0 else vb[:])
    if va.dimensions!=vb.dimensions or va.dtype!=vb.dtype or xa.shape!=xb.shape or xa.tobytes()!=xb.tobytes():
     raise ValueError(f'OFF/ON array/schema differs {name}/{vname}')
    if not ncattrs_equal(va,vb):raise ValueError(f'OFF/ON variable attributes differ {name}/{vname}')
    variable_checks.append({'name':vname,'dimensions':list(va.dimensions),'dtype':str(va.dtype),'shape':list(xa.shape)})
   q['variable_count']=len(variable_checks);q['global_attribute_count']=len(da.ncattrs());q['dimensions']={k:{'length':v[0],'unlimited':v[1]} for k,v in dims_a.items()}
   q['all_variable_arrays_schema_and_attributes_exact']=True;q['variables']=variable_checks
   if name.startswith('wrfout'):
    ts=times(da)
    if ts!=['2016-10-06_00:00:00','2016-10-06_00:01:00','2016-10-06_00:02:00']:raise ValueError(f'history Times {ts}')
    q['Times']=ts;q['locations']={}
    for i,j,label in [(23,1,'QNN_Y_start_destination'),(23,2,'UDM_target_and_boundary_source')]:
     arr={}
     for namevar in ('QCLOUD','QNCLOUD'):
      x=np.asarray(da.variables[namevar][:,:,j-1,i-1]);arr[namevar]={'positive_levels_by_Time':[int(np.count_nonzero(a>0)) for a in x],
         'minimum_by_Time':[float(a.min()) for a in x],'maximum_by_Time':[float(a.max()) for a in x]}
     q['locations'][label]={'Fortran_ij':[i,j],**arr}
  out[name]=q
 return out

def main():
 ex=json.loads((STAGE/'execution.json').read_text())
 if ex.get('status')!='PASS_PAIRED_POSITIVE_NC_OBSERVER_RUNTIME_SCOPED' or ex.get('model_calls')!=2 or ex.get('scientific_accepted') is not False:raise ValueError('wrong terminal execution scope/status')
 for a in ('off','on'):
  if ex['arms'][a].get('actual_rc')!=0 or ex['arms'][a].get('reaped') is not True:raise ValueError(f'{a} child not RC0/reaped')
 qnn=audit_qnn();number=audit_number();outputs=audit_outputs()
 cv=json.loads((STAGE/'capture-validation.json').read_text());nv=json.loads((STAGE/'number-packet-validation.json').read_text())
 if cv.get('packet_count')!=24 or cv.get('rows')!=1056 or nv.get('count')!=20 or nv.get('rows')!=880:raise ValueError('runner readback roster differs')
 result={'schema':'UDM37_POSITIVE_NC_J2_RUNTIME_SAVED_AUDIT_V1','status':'PASS_SCOPED_SAVED_READBACK','scientific_accepted':False,
  'execution':pin(STAGE/'execution.json'),'execution_summary':{'status':ex['status'],'model_calls':ex['model_calls'],'arms':{a:{k:ex['arms'][a].get(k) for k in ('status','pid','actual_rc','reaped','started_unix','ended_unix')} for a in ('off','on')}},
  'stage_plan':pin(STAGE/'stage-plan.json'),'runner':ex['runner'],'capture_validation':pin(STAGE/'capture-validation.json'),'number_validation':pin(STAGE/'number-packet-validation.json'),
  'qnn_boundary':qnn,'number_stages':number,'off_on_outputs':outputs,
  'scope_limits':['One 2-minute 90x99 domain, four selected QNN boundary columns, and one selected UDM point.',
    'QNN boundary destination j=1 and source j=2 are separate coordinates; no same-call density identity is inferred across observers.',
    'Positive entry/helper co-occurrence at four step-levels is structural evidence only; NC activation rates were all zero, so activation response is non-discriminating.',
    'Exact helper-radius replay authenticates this captured arithmetic path only; it does not settle QNC physical units or input authority.']}
 OUT.write_text(json.dumps(result,indent=2,sort_keys=True,allow_nan=False)+'\n')
 print(json.dumps({'status':result['status'],'qnn_packets':qnn['packet_count'],'qnn_rows':qnn['row_count'],'number_packets':number['packet_count'],'number_rows':number['row_count'],'positive_overlap':number['positive_QC_and_QNC_rows']['same_step_k_intersection'],'radius_replay':number['liquid_radius']['output_matches_source_order_replay'],'history_restart_exact':all(x['whole_file_bytes_exact'] for x in outputs.values()),'scientific_accepted':False,'result':str(OUT)},sort_keys=True))
if __name__=='__main__':main()
