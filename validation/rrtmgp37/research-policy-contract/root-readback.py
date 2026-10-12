from pathlib import Path
import datetime,gzip,hashlib,json,platform
import numpy as np
import netCDF4
R=Path(__file__).resolve().parents[2]
W=R/'build/udm37-research-contract-pr-work'
B=W/'validation/rrtmgp37/research-policy-contract';P=W/'validation/rrtmgp37/connected-host-number/runtime/warm-cloud-on'
variables=('QNCCN','QNCLOUD','QNRAIN','QCLOUD','QICE','QRAIN','QSNOW','QGRAUP','QHAIL','CLDFRA')
meta={'source':'Retained manufactured PR156 connected-host warm-cloud input/history/restart; not a new model run','scope':'Entire small saved arrays at retained times; not every RK/microphysics/radiation call','states':[],'raw_files':[],'fresh_solver_executions':0,'production_accepted':False}
for name,roles in [('wrfinput_d01.gz',['initial_input_before_CF_diagnosis']),('wrfout_d01_1999-10-22_19:00:00.gz',['history_initial_before_CF_diagnosis','history_60s_after_step6']),('wrfrst_d01_1999-10-22_19:01:00.gz',['restart_checkpoint_60s'])]:
 p=P/name;compressed=p.read_bytes();raw=gzip.decompress(compressed)
 meta['raw_files'].append({'path':str(p.relative_to(W)),'compressed_bytes':len(compressed),'compressed_sha256':hashlib.sha256(compressed).hexdigest(),'uncompressed_bytes':len(raw),'uncompressed_sha256':hashlib.sha256(raw).hexdigest()})
 with netCDF4.Dataset('retained',memory=raw) as d:
  for t,role in enumerate(roles):
   arrays=[];units={}
   for n in variables:
    v=d.variables[n];a=np.asarray(v[t]);assert a.dtype==np.dtype('float32') and a.shape==(59,2,2) and np.isfinite(a).all()
    arrays.append(a.astype('<f4',copy=False).tobytes());units[n]=getattr(v,'units','')
   b=b''.join(arrays);out=role+'.bin';(B/out).write_bytes(b)
   step=np.asarray(d['UDM_CF_STEP'][t]) if 'UDM_CF_STEP' in d.variables else None
   meta['states'].append({'role':role,'raw_file':str(p.relative_to(W)),'time_index0':t,'variables':list(variables),'shape_per_variable':[59,2,2],'encoding':'IEEE little-endian binary32','extracted_path':out,'extracted_bytes':len(b),'extracted_sha256':hashlib.sha256(b).hexdigest(),
    'reported_units_attributes':units,'units_attributes_are_not_physical_approval':True,'UDM_CF_STEP_range':None if step is None else [float(step.min()),float(step.max())],'direct_radiation_call_state':False})
(B/'state-readback.json').write_text(json.dumps(meta,indent=2)+'\n')
(B/'readback-environment.json').write_text(json.dumps({'recorded_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'python':platform.python_version(),'numpy':np.__version__,'netCDF4_python':netCDF4.__version__,'netCDF_c':netCDF4.__netcdf4libversion__,'root_actual_saved_NetCDF_decode':True,'new_model_runs':0},indent=2)+'\n')
print(json.dumps({'saved_NetCDF_files':len(meta['raw_files']),'extracted_states':len(meta['states']),'new_model_runs':0}))
