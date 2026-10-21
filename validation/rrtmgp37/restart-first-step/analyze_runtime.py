#!/usr/bin/env python3
"""Read the original/fixed actual histories and bounded first-step witnesses."""
from pathlib import Path
import json,hashlib,struct,re,datetime
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-restart-first-analysis-v1';O.mkdir(exist_ok=True)
def pin(p):return {'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
def times(d):return [b''.join(x).decode() for x in d['Times'][:]]
def sha(x):return hashlib.sha256(np.asarray(x).tobytes()).hexdigest()
def hist(p):return next(p.glob('wrfout*'))
def compare(a,b):
 inventory={};differences=[];variables=0
 with Dataset(a) as x,Dataset(b) as y:
  x.set_auto_mask(False);y.set_auto_mask(False);variables=len(x.variables);ta=times(x);tb=times(y);common=[t for t in tb if t in ta];assert set(x.variables)==set(y.variables)
  for t in common:
   inventory[t]={}
   for n,v in x.variables.items():
    aa=np.asarray(v[ta.index(t)] if v.dimensions and v.dimensions[0]=='Time' else v[:]);bb=np.asarray(y[n][tb.index(t)] if v.dimensions and v.dimensions[0]=='Time' else y[n][:]);same=aa.tobytes()==bb.tobytes()
    inventory[t][n]={'shape':list(aa.shape),'dtype':aa.dtype.str,'left_sha256':sha(aa),'right_sha256':sha(bb),'bitwise_equal':same}
    if not same:
     dd=abs(aa.astype(float)-bb.astype(float));ii=np.unravel_index(np.argmax(dd),dd.shape);differences.append({'time':t,'variable':n,'max_abs':float(dd[ii]),'index':list(map(int,ii)),'left':float(aa[ii]),'right':float(bb[ii])})
 return {'left_file':pin(a),'right_file':pin(b),'common_times':common,'variables':variables,'array_pairs':sum(map(len,inventory.values())),'all_bitwise_equal':not differences,'differences':differences,'inventory':inventory}
def probe(p):
 b=p.read_bytes();pos=0;d={}
 while pos<len(b):
  n,*shape=struct.unpack_from('<32s3i',b,pos);pos+=44;count=int(np.prod(shape));d[n.rstrip().decode()]=np.frombuffer(b,dtype='<f4',offset=pos,count=count).reshape(shape,order='F');pos+=count*4
 return d
def hex32(x):return f'{np.float32(x).view("u4"):08x}'
old=B/'udm37-specified-number-run-v2';fixed=B/'udm37-restart-first-fix-run-v2';diag=B/'udm37-restart-first-probe-run-v1'
report={'original_restart':compare(hist(old/'continuous'),hist(old/'restart')),'fixed_restart':compare(hist(fixed/'continuous'),hist(fixed/'restart')),'observer_continuous':compare(hist(old/'continuous'),hist(diag/'continuous')),'observer_restart':compare(hist(old/'restart'),hist(diag/'restart')),'production_accepted':False,'physical_accuracy_approved':False}
c=probe(diag/'continuous/probe-021540-r0-a00-entry.bin');r=probe(diag/'restart/probe-021540-r0-a00-entry.bin');after=[probe(diag/a/'probe-021540-r1-a00-rk_prep.bin') for a in ['continuous','restart']]
physical={}
for n in ['u_2','v_2','w_2','t_2','ph_2','mu_2','mub','p','al','alb','qv','qnc','qnr','qnn']:
 x=c[n];y=r[n]
 if n in ['mu_2','mub']:x=x[:,:8,:];y=y[:,:8,:]
 else:
  kk=45 if n in ['w_2','ph_2'] else 44;jj=9 if n=='v_2' else 8;x=x[:,:kk,:jj];y=y[:,:kk,:jj]
 assert x.tobytes()==y.tobytes(),('first initialized physical inputs differ',n)
 physical[n]={'bytes_equal':True,'sha256':sha(x),'shape':list(x.shape)}
witness={'bounds':{'i':[19,27],'k':[1,45],'j':[92,100]},'physical_inputs':physical,'MU_physical_point_i23_j99':float(c['mu_2'][4,7,0]),'MU_halo_i23_j100':{},'MUV_i23_j100':{},'WW_profile_i23_j99':{},'stage':'rk_step_prep -> calc_ww_cp, before first_rk_step_part1 physics','earlier_scratch_differences':'ru/rv/rw and tendency buffers at entry are recomputed; not promoted to first causal operations'}
for arm,x,y in zip(['continuous','restart'],[c,r],after):
 vals=[x['mu_2'][4,8,0],x['mub'][4,8,0],x['mu_2'][4,7,0],x['mub'][4,7,0]];s=vals[0];partial=[]
 for v in vals[1:]:s=np.float32(s+v);partial.append(hex32(s))
 muv=np.float32(np.float32(.5)*s)
 witness['MU_halo_i23_j100'][arm]={'value':float(vals[0]),'bits':hex32(vals[0])};witness['MUV_i23_j100'][arm]={'operands':list(map(float,vals)),'operand_bits':list(map(hex32,vals)),'partial_sum_bits':partial,'value':float(muv),'bits':hex32(muv)}
 witness['WW_profile_i23_j99'][arm]=[hex32(v) for v in y['ww'][4,:,7]]
report['first_operator_witness']=witness
boundary={};phases={}
with Dataset(fixed/'continuous/wrfrst_d01_2016-10-06_05:59:00') as d:
 report['checkpoint']={n:int(getattr(d,n)) for n in ['UDM_NUMBER_POLICY','UDM_POPULATION_POLICY','UDM_SPECIFIED_NUMBER_CONTRACT']}
with Dataset(fixed/'continuous/wrfbdy_d01') as bd:
 source={'times':times(bd),'MU_values':np.asarray(bd['MU_BYS'][:,0,:]).astype(float).tolist(),'MU_tendencies':np.asarray(bd['MU_BTYS'][:,0,:]).astype(float).tolist()}
 for arm in ['continuous','restart']:
  rows=[]
  with Dataset(hist(fixed/arm)) as d:
   d.set_auto_mask(False)
   for it,t in enumerate(times(d)):
    sec=(datetime.datetime.strptime(t,'%Y-%m-%d_%H:%M:%S')-datetime.datetime(2016,10,6)).total_seconds();rec=int(sec//21600);dt=sec-rec*21600;got=np.asarray(d['MU'][it,0,:]);expected=np.float32(bd['MU_BYS'][rec,0,:]+np.float32(dt)*bd['MU_BTYS'][rec,0,:]);assert got.tobytes()==expected.tobytes()
    edge={};stats={}
    for n in ['QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL','QNCLOUD','QNRAIN','QNCCN']:
     x=np.asarray(d[n][it]);assert np.isfinite(x).all() and np.all(x>=0),(t,n);stats[n]={'min':float(x.min()),'max':float(x.max())}
     if n in ['QNCLOUD','QNRAIN']:
      z=np.concatenate([x[:,0,:].ravel(),x[:,-1,:].ravel(),x[:,1:-1,0].ravel(),x[:,1:-1,-1].ravel()]);assert not np.any(z);edge[n]=0.
    rows.append({'time':t,'elapsed_s':sec,'record':rec,'record_elapsed_s':dt,'south_MU':got.astype(float).tolist(),'NC_NR_edge_max':edge,'finite_nonnegative_stats':stats})
  boundary[arm]=rows
  index=1 if arm=='continuous' else 2;log=(fixed/f'command-{index:02d}.stdout').read_text(errors='replace');phase={kind:[] for kind in ['LW','SW']}
  for line in log.splitlines():
   if 'RRTMGP_UDM_PHASE_PATH phase=LIQ ' in line:
    kind='LW' if ' LW ' in line else 'SW';m=re.search(r'source_time_seconds=\s*([\d.E+\-]+)',line)
    if m and float(m[1])>=21540:phase[kind].append(float(m[1]))
  phases[arm]=phase
report.update(boundary_source=source,boundary=boundary,radiation_phase=phases,full_host_restart_bitwise_criterion_passed=report['fixed_restart']['all_bitwise_equal'],source=pin(R/'WRF/dyn_em/solve_em.F'))
(O/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');print('ORIGINAL_DIFFERENCES',len(report['original_restart']['differences']),'FIXED_DIFFERENCES',len(report['fixed_restart']['differences']),'PAIRS',report['fixed_restart']['array_pairs']);print('RADIATION_PHASE',phases)
