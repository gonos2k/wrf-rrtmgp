from pathlib import Path
import json,sys,numpy as np,netCDF4
root=Path.cwd();sys.path.insert(0,str(root/'WRF/test/rrtmgp'))
from compare_column_replay import read_result
from test_column_replay import read_input,read_raw,compare_input_to_raw
base=root/'build/port-audit-inputs/cases-v2'
def read_audit(p):
 lines=p.read_text().splitlines(); header=lines[1].split();rec={};i=2
 while i<len(lines):
  x=lines[i].split();i+=1;name=x[0];rank=int(x[1]);shape=tuple(map(int,x[2:]));assert len(shape)==rank
  n=int(np.prod(shape));a=np.array([float(v.replace('D','E')) for v in lines[i:i+n]]).reshape(shape,order='F');i+=n
  assert np.isfinite(a).all(),(p,name);rec[name]=a
 return header,rec
summary={'source_head':'3a69404fbe06486fcaad7ba063d3d8062dc8f2a4','cases':{}}
for case in sorted(base.iterdir()):
 if not case.is_dir():continue
 rows={}
 for phase in ['LW','SW']:
  h4,a=read_audit(case/'ra4/capture'/f'{phase}.audit');h37,b=read_audit(case/'ra37/capture'/f'{phase}.audit')
  result=read_result(case/'ra37/capture'/f'{phase.lower()}.result')['sections']
  *_,inp=read_input(case/'ra37/capture'/f'{phase.lower()}.input')
  _,_,_,raw=read_raw(case/'ra37/capture'/f'{phase.lower()}.raw')
  errors=compare_input_to_raw(phase,raw,inp,len(raw['PI']))
  keys=['PLAY','PLEV','TLAY','TLEV','H2O','CO2','O3','N2O','CH4','O2','CF','SOLAR_MU0','TSFC']
  keys += ['EMIS','CFC11','CFC12','CFC22','CCL4'] if phase=='LW' else ['AVDIR','AVDIF','ANDIR','ANDIF','ADJES_DYOFYR']
  diffs={k:float(np.max(np.abs(a[k]-b[k]))) for k in keys}
  active=(a['CF'][0]>0)&((a['LWP'][0]+a['IWP'][0]+a['SWP'][0])>0)
  paths={k:{'ra4':float(a[k].sum()),'ra37':float(b[k].sum()),'max_abs_difference':float(abs(a[k]-b[k]).max())} for k in ['LWP','IWP','SWP','REL','REI','RES']}
  ng=a['MASK'].shape[0];m37=result['MASK'][0]
  layers=[]
  for k in np.where(active)[0]:
   layers.append({'layer':int(k+1),'cf':float(a['CF'][0,k]),'cloud_gpoints4':int(np.count_nonzero(a['MASK'][:,0,k])),'cloud_gpoints37':int(np.count_nonzero(m37[k])),'lwps4_37':[float(a['LWP'][0,k]),float(b['LWP'][0,k])],'iwps4_37':[float(a['IWP'][0,k]),float(b['IWP'][0,k])],'swps4_37':[float(a['SWP'][0,k]),float(b['SWP'][0,k])],'rei4_37':[float(a['REI'][0,k]),float(b['REI'][0,k])],'res4_37':[float(a['RES'][0,k]),float(b['RES'][0,k])]})
  flux={'surface_down4':float(a['DN'][0,0]),'surface_down37':float(b['DN'][0,0]),'surface_down_delta':float(b['DN'][0,0]-a['DN'][0,0]),'toa_up_delta':float(b['UP'][0,-1]-a['UP'][0,-1]),'clear_surface_down_delta':float(b['DNC'][0,0]-a['DNC'][0,0]),'toa_down_delta':float(b['DN'][0,-1]-a['DN'][0,-1])}
  rows[phase]={'unchanged_prepared_input_max_differences':diffs,'cloud_prepared_summary':paths,'ngpt4':ng,'ngpt37':m37.shape[1],'active_layers':layers,'flux':flux,'raw_to_prepared':errors}
  print(case.name,phase,'inputdiff',max(diffs.values()),'iceflag4/37',h4[-2],h37[-2],'flux',flux,'cloudng',[ (x['layer'],x['cloud_gpoints4'],x['cloud_gpoints37']) for x in layers])
 # Instrumentation verification: output arrays through 60s versus preceding valid5min run.
 reg={}
 for option in [4,37]:
  old=root/'build/optics-radiation-comparison'/case.name/f'ra{option}'
  with netCDF4.Dataset(sorted((case/f'ra{option}').glob('wrfout_d01_*'))[-1]) as newds,netCDF4.Dataset(sorted(old.glob('wrfout_d01_*'))[-1]) as oldds:
   mismatch=[];n=0
   for name,var in newds.variables.items():
    if name not in oldds.variables:continue
    x=np.asarray(var[:]);y=np.asarray(oldds[name][:])
    if var.dimensions and var.dimensions[0]=='Time':y=y[:len(x)]
    if x.shape!=y.shape or x.dtype!=y.dtype or x.tobytes()!=y.tobytes():mismatch.append(name)
    n+=1
   reg[str(option)]={'variables_compared':n,'mismatches':mismatch,'status':'PASS' if not mismatch else 'FAIL'}
   assert not mismatch,(case.name,option,mismatch)
 rows['instrumentation_regression']=reg
 summary['cases'][case.name]=rows
(root/'build/port-audit-inputs/analysis.json').write_text(json.dumps(summary,indent=2)+'\n')
print('instrumentation mismatches',[(k,v['instrumentation_regression']) for k,v in summary['cases'].items()])
