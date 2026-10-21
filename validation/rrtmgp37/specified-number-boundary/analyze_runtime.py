#!/usr/bin/env python3
"""Read actual NetCDF histories, boundary records and checkpoint identity."""
from pathlib import Path
import json,hashlib,datetime
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-specified-number-analysis-v1';O.mkdir(exist_ok=True)
def sha(a):return hashlib.sha256(np.asarray(a).tobytes()).hexdigest()
def times(d):return [b''.join(x).decode() for x in np.asarray(d['Times'][:])]
def pin(p):return {'path':str(p),'sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'size_bytes':p.stat().st_size}
def compare(pa,pb):
 rows={};differences=[]
 with Dataset(pa) as a,Dataset(pb) as b:
  a.set_auto_mask(False);b.set_auto_mask(False);ta=times(a);tb=times(b);common=[t for t in tb if t in ta];assert set(a.variables)==set(b.variables)
  for t in common:
   rows[t]={};ii=ta.index(t);jj=tb.index(t)
   for n,v in a.variables.items():
    x=np.asarray(v[ii] if v.dimensions[0]=='Time' else v[:]);y=np.asarray(b[n][jj] if v.dimensions[0]=='Time' else b[n][:]);assert x.dtype==y.dtype and x.shape==y.shape
    equal=x.tobytes()==y.tobytes();rows[t][n]={'shape':list(x.shape),'dtype':x.dtype.str,'continuous_sha256':sha(x),'restart_sha256':sha(y),'bitwise_equal':equal}
    if not equal:
     z=np.abs(x.astype(float)-y.astype(float));i=np.unravel_index(np.argmax(z),z.shape);differences.append({'time':t,'variable':n,'max_abs':float(z[i]),'index_zero_based':list(map(int,i)),'continuous_at_max':float(x[i]),'restart_at_max':float(y[i]),'different_elements':int(np.count_nonzero(x!=y))})
 return {'common_times':common,'variables':len(next(iter(rows.values()))),'array_pairs':sum(map(len,rows.values())),'all_bitwise_equal':not differences,'differences':differences,'inventories':rows}
def history(arm):return next((arm).glob('wrfout*'))
actual=B/'udm37-specified-number-run-v2'
report={'original_restart':compare(history(actual/'continuous'),history(actual/'restart')),'restored_observation':compare(history(actual/'continuous'),history(B/'udm37-specified-number-restart-probe-v1')),'production_accepted':False}
if (B/'udm37-specified-number-host-control-v1/receipt.json').exists():
 control=B/'udm37-specified-number-host-control-v1'
 if (control/'restart').exists() and list((control/'restart').glob('wrfout*')):report['number0_host_control']=compare(history(control/'continuous'),history(control/'restart'))
selected={};stats={};boundary=[]
with Dataset(history(actual/'continuous')) as d,Dataset(actual/'encoded/wrfbdy_d01') as b:
 d.set_auto_mask(False);b.set_auto_mask(False);tt=times(d);source_t=times(b)
 m=np.asarray(b['MU_BYS'][:]);mt=np.asarray(b['MU_BTYS'][:]);selected['south_MU_source_records']={'times':source_t,'values':m[:,0,:].astype(float).tolist(),'tendencies':mt[:,0,:].astype(float).tolist()}
 for it,t in enumerate(tt):
  instant=datetime.datetime.strptime(t,'%Y-%m-%d_%H:%M:%S');elapsed=(instant-datetime.datetime(2016,10,6)).total_seconds();record=int(elapsed//21600);dt=elapsed-record*21600
  got=np.asarray(d['MU'][it])[0];expect=np.float32(m[record,0,:]+np.float32(dt)*mt[record,0,:]);stale=np.float32(m[0,0,:]+np.float32(elapsed)*mt[0,0,:]);assert got.tobytes()==expect.tobytes()
  row={'time':t,'elapsed_s':elapsed,'record_zero_based':record,'record_elapsed_s':dt,'max_MU_expected_abs_Pa':float(np.max(abs(got-expect))),'max_MU_stale_abs_Pa':float(np.max(abs(got-stale))),'south_MU':got.astype(float).tolist()}
  stats[t]={};selected[t]={}
  for n in ['QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL','QNCLOUD','QNRAIN','QNCCN']:
   x=np.asarray(d[n][it]);assert np.isfinite(x).all() and np.all(x>=0),n+' '+t
   inside=x[:,5:-5,5:-5];stats[t][n]={'min':float(x.min()),'max':float(x.max()),'interior_positive_count':int(np.count_nonzero(inside>0)),'array_sha256':sha(x)}
   if n in ['QNCLOUD','QNRAIN','QNCCN']:
    edges=np.concatenate([x[:,0,:].ravel(),x[:,-1,:].ravel(),x[:,1:-1,0].ravel(),x[:,1:-1,-1].ravel()])
    selected[t][n]={'edge_values':edges.astype(float).tolist(),'interior_max_index':list(map(int,np.unravel_index(np.argmax(inside),inside.shape))),'interior_max':float(inside.max())}
    if n!='QNCCN':assert np.all(edges==0),'nonzero prescribed number edge';row[n+'_edge_max']=float(edges.max())
  boundary.append(row)
 assert any(x['record_zero_based']==1 and x['max_MU_stale_abs_Pa']>0 for x in boundary)
 assert stats[tt[-1]]['QNCLOUD']['interior_positive_count']>0 and stats[tt[-1]]['QNRAIN']['interior_positive_count']>0
checkpoint=actual/'continuous/wrfrst_d01_2016-10-06_05:59:00'
with Dataset(checkpoint) as d:
 report['checkpoint']={'UDM_NUMBER_POLICY':int(d.UDM_NUMBER_POLICY),'UDM_POPULATION_POLICY':int(d.UDM_POPULATION_POLICY),'UDM_SPECIFIED_NUMBER_CONTRACT':int(d.UDM_SPECIFIED_NUMBER_CONTRACT),'sha256':pin(checkpoint)}
 assert (d.UDM_NUMBER_POLICY,d.UDM_POPULATION_POLICY,d.UDM_SPECIFIED_NUMBER_CONTRACT)==(1,0,1)
report.update(boundary_records=boundary,history_stats=stats,selected_slice_file='selected.json',raw_histories={'continuous':pin(history(actual/'continuous')),'restart':pin(history(actual/'restart')),'restore_observer':pin(history(B/'udm37-specified-number-restart-probe-v1'))})
report['predeclared_full_restart_bitwise_criterion_passed']=report['original_restart']['all_bitwise_equal']
report['boundary_value_tendency_and_record_checks_passed']=True
report['restart_observer_noninterference']=compare(history(actual/'restart'),history(B/'udm37-specified-number-restart-probe-v1'))
report['number0_host_restart_bitwise_mismatch_reproduced']=not report['number0_host_control']['all_bitwise_equal']
report['earliest_arithmetic_cause']='NOT_LOCALIZED; first small W/PH differences at north boundary/relaxation also occur in number0. No new-number-specific cause established.'
report['overall_preregistered_full_validation_passed']=False
report['full_host_restart_bitwise_approved']=False
report['number0_restored_all_225_equal']=all(v['bitwise_equal'] for v in report['number0_host_control']['inventories']['2016-10-06_05:59:00'].values())
report['physical_accuracy_approved']=False
with Dataset(B/'udm37-specified-number-kernel-v4/manufactured.nc') as m:
 manufactured={'source_file':pin(B/'udm37-specified-number-kernel-v4/manufactured.nc'),'times':times(m),'fields':{n:np.asarray(m[n][:]).astype(float).ravel().tolist() for n in ['QNCLOUD_BXS','QNCLOUD_BTXS','QCLOUD_BXS','QCLOUD_BTXS']},'rho_endpoints':[1.,.8,.7],'mass_factors_Pa':[1000.,1200.,1400.],'number_m3_endpoints':[1.e8,1.e8,1.e8]}
(O/'manufactured.json').write_text(json.dumps(manufactured,indent=2)+'\n')
(O/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');(O/'selected.json').write_text(json.dumps(selected,indent=2)+'\n')
print('RESTART_ARRAY_PAIRS',report['original_restart']['array_pairs'],'DIFFERENCES',len(report['original_restart']['differences']))
print('INITIAL_RESTORED_EQUAL',all(x['bitwise_equal'] for x in report['restored_observation']['inventories']['2016-10-06_05:59:00'].values()))
print('ACTUAL_NEXT_RECORD_USED',boundary[-1]['max_MU_stale_abs_Pa'])
