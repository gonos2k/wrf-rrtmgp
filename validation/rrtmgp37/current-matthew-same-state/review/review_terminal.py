#!/usr/bin/env python3
"""Read-only independent terminal review. Writes only its own review file once."""
import pathlib,json,hashlib,datetime,csv,collections,runpy
import numpy as np
from netCDF4 import Dataset
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP');P=ROOT/'build/udm37-current-matthew-serial-audit-v1';O=pathlib.Path(__file__).resolve().parent/'runtime-terminal-review.json'
def sha(p):return hashlib.sha256(pathlib.Path(p).read_bytes()).hexdigest()
def pin(p):p=pathlib.Path(p);return {'path':str(p),'sha256':sha(p),'size_bytes':p.stat().st_size}
def av(v):
 a=np.asarray(v);return (str(a.dtype),a.shape,a.tobytes()) if a.dtype.kind!='O' else repr(v)
def attrs(obj):return {k:av(obj.getncattr(k)) for k in obj.ncattrs()}
r=json.loads((P/'execution-receipt.json').read_text());ident=json.loads((P/'runtime-build-identity-v1.json').read_text());auth=json.loads((P/'root-authorization.json').read_text());assert r['status']=='PASS_SERIAL_AUDIT_OUTPUTS_AND_CAPTURE_PARITY' and r['model_invocations']==3 and r['counts']=={'REAL':0,'compile':0,'model':3};assert sha(P/'root-authorization.json')==r['authorization_sha256'];m=runpy.run_path(str(P/'run_serial_audit_once.py'),run_name='read_only_review');m['verify_runtime'](json.loads((P/'plan.json').read_text()),ident,auth);m['verify_stage'](json.loads((P/'plan.json').read_text()),json.loads((P/'stage-manifest.json').read_text()),json.loads((P/'stage-readback-v1.json').read_text()),ident)
arms={};qualities=[];comp=[]
for arm in m['ARMS']:
 a=r['arms'][arm];assert a['returncode']==0 and not a['timed_out'] and a['status']=='PASS_ARM' and a['model_invocations']==1;assert m['scan_logs'](P/arm)['success_ranks']==[0] and not m['scan_logs'](P/arm)['fatal_markers'];sec=(datetime.datetime.fromisoformat(a['ended_utc'])-datetime.datetime.fromisoformat(a['started_utc'])).total_seconds();assert 0<sec<600
 arms[arm]={'returncode':0,'timed_out':False,'actual_invocations':1,'process_elapsed_seconds':sec,'status':'PASS_ARM'}
 for q in a['quality']+a['restart_outputs']:
  f=pathlib.Path(q['file']['path']);assert pin(f)==q['file'];numeric=0
  with Dataset(f) as d:
   for name,v in d.variables.items():
    v.set_auto_maskandscale(False);x=np.asarray(v[:]);
    if x.dtype.kind in 'fciu':
     numeric+=1;assert np.isfinite(x).all(),(f,name)
     for flag in ['_FillValue','missing_value']:
      if flag in v.ncattrs():assert not np.isin(x,np.asarray(v.getncattr(flag))).any(),(f,name,flag)
    v.set_auto_maskandscale(True);x=v[:];assert not (np.ma.isMaskedArray(x) and np.ma.getmaskarray(x).any()),(f,name)
    z=np.asarray(x.data if np.ma.isMaskedArray(x) else x);assert z.dtype.kind not in 'fciu' or np.isfinite(z).all(),(f,name)
   qualities.append({'arm':arm,'file':f.name,'variables':len(d.variables),'numeric_variables':numeric,'data_model':d.data_model,'file_pin':pin(f)})
for name in r['arms']['OFF']['history_filenames']+r['arms']['OFF']['restart_filenames']:
 for arm in m['ARMS'][1:]:
  left=P/'OFF'/name;right=P/arm/name
  with Dataset(left) as a,Dataset(right) as b:
   assert a.data_model==b.data_model;assert {k:(len(v),v.isunlimited()) for k,v in a.dimensions.items()}=={k:(len(v),v.isunlimited()) for k,v in b.dimensions.items()};assert set(a.variables)==set(b.variables);assert attrs(a)==attrs(b)
   for n in a.variables:
    x,y=a[n],b[n];assert (x.dimensions,x.shape,str(x.dtype))==(y.dimensions,y.shape,str(y.dtype));assert attrs(x)==attrs(y);x.set_auto_maskandscale(False);y.set_auto_maskandscale(False);assert np.asarray(x[:]).tobytes()==np.asarray(y[:]).tobytes(),(arm,name,n)
   comp.append({'arm':arm,'file':name,'fields':len(a.variables),'all_raw_schema_full_attributes_equal':True,'whole_file_equal':sha(left)==sha(right)})
groups={arm:m['capture_map'](m['capture_groups'](P/arm)) for arm in m['ARMS']};assert all(groups[arm]==groups['OFF'] for arm in m['ARMS']);keys=sorted(groups['OFF']);assert [{'phase':k[0],'radiation_step':k[1],'source_seconds':k[2]} for k in keys]==r['actual_call_roster'];csvrows={};csvsummary={}
for arm in m['ARMS'][1:]:
 rows=list(csv.DictReader((P/arm/'audit/same_state.csv').open()));keycols=['phase','domain','step','source_seconds','i','j','metric'];m['audit_roster'](P/arm,arm);assert len(rows)==1128
 for x in rows:
  for k in ['value37','value4','mean37','sd37','mean4','sd4','sd_delta']:assert np.isfinite(float(x[k]));assert float(x['sample_count'])==128;assert float(x['sd37'])>=0 and float(x['sd4'])>=0
 keyed={tuple(x[k] for k in keycols):x for x in rows};assert len(keyed)==len(rows);csvrows[arm]=keyed
 actual={(x['phase'].upper(),int(x['step']),float(x['source_seconds'])) for x in rows if (x['i'],x['j'])==('24','55')};assert actual==set(keys)
 csvsummary[arm]={'rows':len(rows),'selected_rows':sum(x['i']=='24' and x['j']=='55' for x in rows),'aggregate_rows':sum(x['i']=='0' and x['j']=='0' for x in rows),'sample_count_each':128,'call_keys':len(actual),'csv_pin':pin(P/arm/'audit/same_state.csv')}
assert set(csvrows[m['ARMS'][1]])==set(csvrows[m['ARMS'][2]])
for k,x in csvrows[m['ARMS'][1]].items():
 y=csvrows[m['ARMS'][2]][k]
 for col in ['value37','mean37','sd37']:assert np.float64(x[col]).tobytes()==np.float64(y[col]).tobytes(),(k,col)
start=datetime.datetime(2016,10,6)
roster=[{'phase':k[0],'radiation_step':k[1],'source_seconds':k[2],'calendar':(start+datetime.timedelta(seconds=k[2])).strftime('%Y-%m-%d_%H:%M:%S')} for k in keys]
assert all('2016-10-07_12:' in k['calendar'] for k in roster)
report={'status':'PASS_SCOPED_INDEPENDENT_TERMINAL_SERIAL_AUDIT','observed_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'original_receipt':pin(P/'execution-receipt.json'),'authorization':pin(P/'root-authorization.json'),'review_script':pin(__file__),'radius_comparison':pin(P/'radius-arm-comparison.json'),'arms':arms,'output_quality':qualities,'exact_output_comparisons':comp,'capture_parity':{'groups_per_arm':len(keys),'phases':{'LW':6,'SW':6},'records_per_group':3,'complete_raw_input_result_roster_equal':True,'all_group_bytes_equal':True},'observed_call_roster':roster,'csv':csvsummary,'engine37_reference_between_native4_arms':{'matching_rows':1128,'fields':['value37','mean37','sd37'],'exact_parsed_float64_bytes':True},'counts':{'original_model_invocations':3,'review_model_REAL_compile_solver_analyzer_invocations':0},'limitations':['All-sky CSV only; no paired clear CSV.','564 selected rows plus564 aggregate rows per arm are not1128 independent samples.','128-seed spread is descriptive, not IID confidence.','Same-state wrapper controls retain each engine input/optics/sampling policy; no pure engine or physical accuracy attribution.','Observed sixLW and sixSW calls12:00 through12:50 are results, not a forced schedule.']}
assert not O.exists();O.write_text(json.dumps(report,indent=2,sort_keys=True)+'\n');print(O,sha(O))
