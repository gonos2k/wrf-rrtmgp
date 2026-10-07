#!/usr/bin/env python3
"""Strict saved-only temporary-CF source checkpoint joins; no physical approval."""
import argparse,hashlib,json,math,pathlib,re,struct,sys
sys.dont_write_bytecode=True
CFNAME=re.compile(r'^population_d(\d+)_tile(\d+)_i(\d+)_j(\d+)_step(\d+)_sub(\d+)_phase(\d+)\.cfpop$')
NUMNAME=re.compile(r'^number_d(\d+)_tile(\d+)_i(\d+)_j(\d+)_step(\d+)_stage(\d+)_sub(\d+)\.raw$')
CFEXPECTED={(step,1,phase) for step in (1,2) for phase in (1,2,3,4)}
NUMEXPECTED={(step,stage,1 if stage in (21,23,30,31) else 0) for step in (1,2) for stage in (10,11,20,21,23,30,31,40,50,51)}
# CF real indices: CF,T,P,QV,QC,QI,QR,QS,QG,QH,NN,NC,NR,DEN
MASS=range(4,10);NUMBERS=(10,11,12);COMMON=(1,2,3,13)
NUM_TO_CF=(1,2,3,4,6,10,11,12,13)
def f32(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def bits(x):return struct.pack('<f',x)
def same(a,b):return bits(a)==bits(b)
def pin(p):
 b=p.read_bytes();return {'path':str(p.resolve()),'sha256':hashlib.sha256(b).hexdigest(),'size_bytes':len(b)}
def values(tokens):
 a=[float(x) for x in tokens]
 if not all(math.isfinite(v) and f32(v)==v for v in a):raise ValueError('nonfinite or not promoted nativeREAL32')
 return a
def parse_cf(path):
 m=CFNAME.fullmatch(path.name)
 if not m:raise ValueError('invalid CF filename')
 d,tile,i,j,step,sub,phase=map(int,m.groups());lines=path.read_text().splitlines()
 if len(lines)!=47 or lines[0]!='UDM37CFPOP1':raise ValueError('CF magic/row count')
 h=[int(x) for x in lines[1].split()];clock=values(lines[2].split())
 if len(h)!=13 or h[:10]!=[1,step,phase,sub,1,23,2,1,44,32] or (d,tile,i,j)!=(1,1,23,2):raise ValueError('CF identity/header')
 if (step,sub,phase) not in CFEXPECTED:raise ValueError('CF step/substep/phase')
 if clock!=[float(step-1),60.,60.]:raise ValueError('CF clock must be same-step1min, driver/substep60s')
 top,qctop,qitop=h[10:]
 if not (0<=top<=44 and 0<=qctop<=44 and 0<=qitop<=44) or top!=max(qctop,qitop):raise ValueError('CF top bounds/association')
 rows=[]
 for k,line in enumerate(lines[3:],1):
  t=line.split()
  if len(t)!=17:raise ValueError('CF row token count')
  kr,applied,diagnosed=map(int,t[:3]);v=values(t[3:])
  if kr!=k or diagnosed!=int(k<=top) or applied!=int(k<=top and v[0]>0):raise ValueError('CF row identity/mask')
  if not 0<=v[0]<=1 or v[13]<=0:raise ValueError('CF/rho bound')
  if k>top and not same(v[0],1.):raise ValueError('Above-top CF working-default sentinel')
  rows.append({'mask':applied,'diagnosed':diagnosed,'v':v})
 return {'key':(step,sub,phase),'header':h,'clock':clock,'rows':rows,'pin':pin(path)}
def parse_number(path):
 m=NUMNAME.fullmatch(path.name)
 if not m:raise ValueError('invalid NUMBER filename')
 d,tile,i,j,step,stage,sub=map(int,m.groups());lines=path.read_text().splitlines()
 if len(lines)!=47 or lines[0]!='UDM37NUM1':raise ValueError('NUMBER magic/row count')
 h=[int(x) for x in lines[1].split()];clock=values(lines[2].split())
 if len(h)!=12 or h[:10]!=[1,step,stage,sub,1,23,2,1,44,32] or (d,tile,i,j)!=(1,1,23,2):raise ValueError('NUMBER identity/header')
 key=(step,stage,sub)
 if key not in NUMEXPECTED:raise ValueError('NUMBER stage/step/substep')
 available=17 if stage in (21,23,30) else 29 if stage==31 else 2 if stage==51 else 0
 if h[10:]!=[available,int(step==1)] or clock!=[float(step-1),60.,1.e8]:raise ValueError('NUMBER availability/initializer/clock')
 rows=[]
 for k,line in enumerate(lines[3:],1):
  tokens=line.split()
  if len(tokens)!=15 or int(tokens[0])!=k:raise ValueError('NUMBER row schema/k')
  rows.append(values(tokens[1:]))
 return {'key':key,'header':h,'clock':clock,'rows':rows,'pin':pin(path)}
def collect(directory,pattern,parser,expected):
 got={}
 for p in sorted(directory.glob(pattern)):
  q=parser(p)
  if q['key'] in got:raise ValueError('duplicate packet identity')
  got[q['key']]=q
 if set(got)!=expected:raise ValueError('missing/extra packet identities: '+str((set(got)-expected,expected-set(got))))
 return got
def validate(directory):
 directory=pathlib.Path(directory).resolve()
 cf=collect(directory,'*.cfpop',parse_cf,CFEXPECTED)
 num=collect(directory,'*.raw',parse_number,NUMEXPECTED)
 transformation_checks=0;unchanged_number_checks=0;entry_joins=0;helper_joins=0;discriminating=[];process_changes=[];radius=[]
 for step in (1,2):
  a,b,c,d=[cf[(step,1,p)] for p in (1,2,3,4)]
  # cldf/ktop arrays have no writer between diagnosis and restoration.
  for q in (b,c,d):
   if q['header'][10:]!=a['header'][10:] or q['clock']!=a['clock']:raise ValueError('same-call top/clock changed')
   if not all(same(x['v'][0],y['v'][0]) for x,y in zip(a['rows'],q['rows'])):raise ValueError('same-call CF changed')
  for before,after,operation in ((a,b,'divide'),(c,d,'multiply')):
   for k,(x,y) in enumerate(zip(before['rows'],after['rows']),1):
    for n in MASS:
     z=x['v'][n]
     if x['mask']:z=f32(z/x['v'][0]) if operation=='divide' else f32(z*x['v'][0])
     if not same(y['v'][n],z):raise ValueError(f'{operation}: mass[{n}] source operation mismatch step{step}/k{k}')
     transformation_checks+=1
    for n in NUMBERS:
     if not same(x['v'][n],y['v'][n]):raise ValueError(f'{operation}: number changed step{step}/k{k}')
     unchanged_number_checks+=1
    for n in COMMON:
     if not same(x['v'][n],y['v'][n]):raise ValueError(f'{operation}: context changed step{step}/k{k}')
  source23=num[(step,23,1)]
  if source23['clock'][0:2]!=a['clock'][0:2]:raise ValueError('CF/NUMBER23 clock mismatch')
  for k,(x,y) in enumerate(zip(a['rows'],source23['rows']),1):
   if not all(same(x['v'][ci],y[ni]) for ni,ci in enumerate(NUM_TO_CF)):raise ValueError(f'CFpre/NUMBER23 input join mismatch step{step}/k{k}')
   entry_joins+=1
  for stages in ((40,50),(50,51)):
   x,y=(num[(step,stage,0)] for stage in stages)
   if x['clock']!=y['clock']:raise ValueError('return/helper clock mismatch')
   for k,(u,v) in enumerate(zip(x['rows'],y['rows']),1):
    if not all(same(aa,bb) for aa,bb in zip(u[:9],v[:9])):raise ValueError('return/helper state changed')
    helper_joins+=1
  x=a['rows'][6];helper=num[(step,50,0)]['rows'][6];out=num[(step,51,0)]['rows'][6]
  actual=x['diagnosed']==1 and x['v'][4]>0 and x['v'][11]>0 and 0<x['v'][0]<1
  helper_positive=helper[3]>0 and helper[6]>0
  if actual and helper_positive:
   if out[10]<=0:raise ValueError('positive helper input has no positive returned cloud radius')
   discriminating.append({'domain':1,'tile':1,'i':23,'j':2,'k':7,'step':step,'substep':1,'XTIME_minutes':float(step-1),'predivision_CF':x['v'][0],'predivision_QC':x['v'][4],'predivision_NC_raw':x['v'][11],'helper_QC':helper[3],'helper_NC_raw':helper[6],'returned_RE_cloud_m':out[10]})
  process_changes.append({'step':step,'changed_mass_fields':sum(not same(u['v'][n],v['v'][n]) for u,v in zip(b['rows'],c['rows']) for n in MASS),'changed_number_fields':sum(not same(u['v'][n],v['v'][n]) for u,v in zip(b['rows'],c['rows']) for n in NUMBERS),'scope':'Descriptive phase2→3 only; no inverse or invariance gate.'})
  radius.append({'step':step,'helper_input_positive_QC_and_NC':helper_positive,'returned_RE_cloud_m':out[10]})
 return {'status':'PASS_DISCRIMINATING_FRACTIONAL_CF_SOURCE_RELATIONS' if discriminating else 'NON_DISCRIMINATING_FRACTIONAL_CF_NOT_OBSERVED','CF_packet_count':8,'CF_row_count':352,'NUMBER_packet_count':20,'NUMBER_row_count':880,'transformation_checks':transformation_checks,'unchanged_number_checks':unchanged_number_checks,'predivision_NUMBER23_joins':entry_joins,'return_helper_state_joins':helper_joins,'discriminating_selected_levels':discriminating,'intervening_process_changes':process_changes,'helper':radius,'packet_pins':[x['pin'] for x in cf.values()]+[x['pin'] for x in num.values()],'scientific_accepted':False,'limits':['Raw NN/NC/NR source values; no unit authority.','Predivision CF is earlier than final helper state; no contemporaneousCF recompute claimed.','Source operation mapping, not PSD/LUT/radius formula physical validation.','No rerun or retuning if NON_DISCRIMINATING.']}
def main():
 a=argparse.ArgumentParser();a.add_argument('directory',type=pathlib.Path);a.add_argument('--output',type=pathlib.Path,required=True);q=a.parse_args()
 if q.output.exists():raise FileExistsError(q.output)
 r=validate(q.directory);q.output.write_text(json.dumps(r,indent=2)+'\n');return 0 if r['status'].startswith('PASS') else 2
if __name__=='__main__':raise SystemExit(main())
