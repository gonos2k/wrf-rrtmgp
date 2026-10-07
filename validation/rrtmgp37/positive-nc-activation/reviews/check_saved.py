#!/usr/bin/env python3
import pathlib,json,hashlib,struct,math,ctypes,re,datetime
import numpy as np
from netCDF4 import Dataset
B=pathlib.Path.cwd(); R=B/'build/udm37-activation-supersat-runtime-v4'; O=pathlib.Path(__file__).resolve().parent
P=json.loads((R/'stage-plan.json').read_text()); E=json.loads((R/'execution.json').read_text()); V=json.loads((R/'activation-packet-validation.json').read_text())
def pin(p):
 p=pathlib.Path(p);h=hashlib.sha256(p.read_bytes()).hexdigest();return {'path':str(p),'sha256':h,'size_bytes':p.stat().st_size}
def f(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def add(x,y):return f(f(x)+f(y))
def sub(x,y):return f(f(x)-f(y))
def mul(x,y):return f(f(x)*f(y))
def div(x,y):return f(f(x)/f(y))
lib=ctypes.CDLL('libm.so.6')
for n,k in [('powf',2),('expf',1),('logf',1),('atanf',1)]:
 fn=getattr(lib,n);fn.argtypes=[ctypes.c_float]*k;fn.restype=ctypes.c_float
xa=div(-sub(f(1870),f(4190)),f(461.5));xb=add(xa,div(f(2501000),mul(f(461.5),f(273.16))))
xinc=div(f(150),f(7500));c1=sub(f(1),div(f(180),xinc));c2=div(f(1),xinc)
def qs(T,p):
 xj=min(max(add(c1,mul(c2,T)),f(1)),f(7501));j=min(int(xj),7500);frac=sub(xj,f(j))
 def node(j):
  x=add(f(180),mul(f(j-1),xinc));tr=div(f(273.16),x)
  return mul(mul(f(610.78),lib.powf(tr,xa)),lib.expf(mul(xb,sub(f(1),tr))))
 lo,hi=node(j),node(j+1);es=add(lo,mul(frac,sub(hi,lo)));cap=mul(f(.99),p);esc=min(es,cap)
 return max(div(mul(div(f(287),f(461.6)),esc),sub(p,esc)),f(1e-15)),{'j':j,'fraction':frac,'es':es,'cap':cap,'cap_active':esc!=es}
D=pathlib.Path(P['cases']['on']['number_capture_directory']);got={};pins=[]
for path in sorted(D.glob('*.raw')):
 lines=path.read_text().splitlines();assert len(lines)==47 and lines[0]=='UDM37NUM1'
 h=list(map(int,lines[1].split()));c=list(map(float,lines[2].split()));assert len(h)==12 and h[0]==1 and h[4:10]==[1,23,2,1,44,32]
 name=f'number_d1_tile1_i23_j2_step{h[1]}_stage{h[2]}_sub{h[3]}.raw';assert name==path.name
 rows=[]
 for k,line in enumerate(lines[3:],1):
  a=line.split();assert len(a)==15 and int(a[0])==k
  x=list(map(float,a[1:]));assert all(math.isfinite(v) and f(v)==v for v in x);rows.append(x)
 key=(h[1],h[2],h[3]);assert key not in got;got[key]=(h,c,rows);pins.append(pin(path))
assert set(got)=={(step,s,1 if s in (21,23,30,31) else 0) for step in (1,2) for s in (10,11,20,21,23,30,31,40,50,51)}
reports=[];checks=0
pi=mul(f(4),lib.atanf(f(1)));actr=f(1.5e-6)
for step in (1,2):
 a=got[(step,30,1)];z=got[(step,31,1)];entry=got[(step,21,1)];assert a[1]==z[1]==entry[1]==[float(step-1),60.,1e8]
 pre=a[2][6];post=z[2][6];cache=entry[2][6];q_sat,info=qs(pre[0],pre[1]);rh=max(div(pre[2],q_sat),f(1e-15));rdt=div(f(1),post[13])
 if rh>1:
  ratio=div(sub(rh,f(1)),f(.0048));temp=min(f(1),lib.expf(mul(lib.logf(ratio),f(.6))))
  uncapped=mul(max(f(0),sub(mul(add(pre[5],pre[6]),temp),pre[6])),rdt)
  ncap=mul(max(pre[5],f(0)),rdt);nr=min(uncapped,ncap)
  pr=div(mul(mul(mul(mul(f(4),pi),f(1000)),lib.expf(mul(lib.logf(actr),f(3)))),nr),mul(f(3),pre[8]));mcap=mul(max(pre[2],f(0)),rdt);pr=min(pr,mcap)
 else:ratio=None;temp=f(0);uncapped=ncap=nr=pr=mcap=f(0)
 assert nr==post[11] and pr==post[12],(step,nr,post[11],pr,post[12]);checks+=2
 cachedq=max(cache[2],f(1e-15));cv=mul(f(4),f(461.6));cpm=add(mul(f(1004.5),sub(f(1),cachedq)),mul(cachedq,cv));xlv=sub(f(2500000),mul(sub(f(4190),cv),sub(cache[0],f(273.15))))
 dn=mul(post[11],post[13]);dm=mul(post[12],post[13]);expected={5:max(sub(pre[5],dn),f(5e7)),6:max(add(pre[6],dn),f(1e-3)),2:max(sub(pre[2],dm),f(0)),3:max(add(pre[3],dm),f(0)),0:add(pre[0],mul(div(mul(post[12],xlv),cpm),post[13]))}
 for i,x in expected.items():assert x==post[i],(step,i,x,post[i]);checks+=1
 # Source postreturn copy → helper input and helper read-only state; later processes need not equal activation poststate.
 r40=got[(step,40,0)][2];r50=got[(step,50,0)][2];r51=got[(step,51,0)][2]
 assert np.array_equal(np.array(r40)[:,:9],np.array(r50)[:,:9]);assert np.array_equal(np.array(r50)[:,:9],np.array(r51)[:,:9]);checks+=44*9*2
 target=r50[6]
 reports.append({'step':step,'qsat_libm_binary32':q_sat,'RH':rh,'svp':info,'supersaturation_ratio_to_satmax':ratio,'activation_fraction':temp,'NC_ACT_uncapped':uncapped,'NC_ACT_NN_cap':ncap,'NC_ACT_observed':post[11],'NC_ACT_second_cap_active':uncapped>ncap,'PC_ACT_observed':post[12],'PC_ACT_QV_cap_active':pr==mcap if rh>1 else False,'CPM_cached':cpm,'XLV_cached':xlv,'NC_stored_increment':post[6]-pre[6],'NN_raw_pre_floor':sub(pre[5],dn),'NN_floor_active':sub(pre[5],dn)<f(5e7),'NNNC_total_stored_change':post[5]+post[6]-pre[5]-pre[6],'post31_QC':post[3],'post31_NC':post[6],'helper50_QC':target[3],'helper50_NC':target[6],'helper50_T':target[0],'helper50_DEN':target[8],'helper51_RE_cloud_m':r51[6][10],'post31_to_helper50_identical_QC_NC':[post[3]==target[3],post[6]==target[6]]})
assert E['model_calls']==2 and E['status']=='PASS_PAIRED_ACTIVATION_OBSERVER_RUNTIME_SCOPED' and E['inputs_before']==E['inputs_after']
for arm in ('off','on'):
 assert E['arms'][arm]['actual_rc']==0 and E['arms'][arm]['reaped'] and E['arms'][arm]['models']==1
assert E['scientific_accepted']==False
# Whole-file equality proves stored arrays/schema/attributes; metadata and bounded selected profiles independently opened.
comparisons=[]
for old in E['off_on_comparisons']:
 left=pathlib.Path(old['left']['path']);right=pathlib.Path(old['right']['path']);hl=hashlib.sha256();hr=hashlib.sha256();size=0
 with left.open('rb') as a,right.open('rb') as z:
  while True:
   x=a.read(1<<20);y=z.read(1<<20);assert x==y
   if not x:break
   hl.update(x);hr.update(y);size+=len(x)
 assert hl.hexdigest()==old['left']['sha256']==hr.hexdigest()==old['right']['sha256']
 with Dataset(left) as ds:
  times=[''.join(np.asarray(row).astype('S1').tobytes().decode('ascii')) for row in ds['Times'][:]]
  n=len(ds.variables);assert n==len(old['variables'])
  if left.name.startswith('wrfout'):
   for step in (1,2):
    helper=got[(step,50,0)][2]
    for name,idx in [('QCLOUD',3),('QNCLOUD',6),('QNRAIN',7),('QRAIN',4),('QVAPOR',2),('QNCCN',5)]:
     v=ds[name];v.set_auto_maskandscale(False);x=np.asarray(v[step,:,1,22]);assert np.array_equal(x,np.asarray(helper)[:,idx]),(step,name)
     checks+=44
 comparisons.append({'kind':left.name,'sha256':hl.hexdigest(),'whole_file_bytes':size,'variables':n,'times':times,'entire_file_exact':True,'claim_scope':'Complete encoded file equality proves all stored variable/schema/attribute bytes; bounded profiles separately read.'})
out={'status':'PASS_SCOPED_SAVED_ACTIVATION_AND_PASSIVITY_REVIEW','execution':pin(R/'execution.json'),'activation_report':pin(R/'activation-packet-validation.json'),'plan':pin(R/'stage-plan.json'),'packet_count':len(got),'packet_rows':len(got)*44,'packet_pins':pins,'source_equation_checks':checks,'selected_steps':reports,'whole_output_comparisons':comparisons,'actual_model_outcomes':[{'arm':a,'pid':E['arms'][a]['pid'],'actual_rc':E['arms'][a]['actual_rc'],'reaped':E['arms'][a]['reaped']} for a in ('off','on')],'scientific_accepted':False,'reviewer_new_models':0,'reviewer_new_compilers':0,'limits':['RH target1.003 was an input hypothesis; actual step1 RH1.01349 hits activation_fraction=1 saturation branch.','NC_ACT rate and stored changes reflect native binary32 rounding plus CCN floor; stored total count is not conserved by this floor operation.','Matched helper input at later stage does not mean stage31 state survives unchanged: intervening UDM processes act.','Source loaded states and exact numerical operations do not establish number units, PSD validity, physical accuracy, restart basis, or forecast relevance.','libm float32 reconstruction is observed equal for these selected values only; not a universal compiler intrinsic guarantee.','MPI launcher reap is recorded by root runner; independent /proc descendant audit belongs to root.']}
(O/'saved-review-details.json').write_text(json.dumps(out,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':out['status'],'step_metrics':reports,'output_comparisons':comparisons,'checks':checks}))
