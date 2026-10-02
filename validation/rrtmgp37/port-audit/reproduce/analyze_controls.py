from pathlib import Path
import numpy as np,json,sys
root=Path.cwd();sys.path.insert(0,str(root/'WRF/test/rrtmgp'))
from test_column_replay import read_input
from compare_column_replay import read_result
out=root/'build/port-audit-inputs'
def audit(p):
 lines=p.read_text().splitlines();rec={};i=2
 while i<len(lines):
  t=lines[i].split();i+=1;shape=tuple(map(int,t[2:]));n=int(np.prod(shape));rec[t[0]]=np.array([float(v) for v in lines[i:i+n]]).reshape(shape,order='F');i+=n
 return rec
summary={'source_head':'3a69404fbe06486fcaad7ba063d3d8062dc8f2a4','scenarios':{}}
for scenario in sorted((out/'cases-v2').iterdir()):
 if not scenario.is_dir():continue
 result={}
 for phase in ['LW','SW']:
  actual=[audit(scenario/f'ra{o}/capture/{phase}.audit') for o in [4,37]]
  f=float(np.max(actual[0]['CF']));npositive=int(np.count_nonzero(actual[0]['CF']));assert npositive<=1
  conditioned={}
  for mode in ['clear','allcloud']:
   conditioned[mode]=[audit(out/f'controls/{scenario.name}/{mode}/ra{o}/capture/{phase}.audit') for o in [4,37]]
   # This checks the scratch wrapper against the independent pinned-core reference.
   cap=out/f'controls/{scenario.name}/{mode}/ra37/capture';reference=read_result(out/f'variants/{scenario.name}.{phase.lower()}.{"clear" if mode=="clear" else "allcloud_actual"}.result')['sections']
   for field in ['UP','DN','HR','UPC','DNC','HRC']:
    production=conditioned[mode][1][field];ref=reference[field][:,:,0]
    assert np.allclose(production,ref,atol=1.e-6,rtol=5.e-7),(scenario.name,phase,mode,field,float(abs(production-ref).max()))
  metrics={}
  for label,field,k in [('surface_down','DN',0),('toa_up','UP',-1)]:
   observed=np.array([a[field][0,k] for a in actual]);clear=np.array([a[field][0,k] for a in conditioned['clear']]);cloud=np.array([a[field][0,k] for a in conditioned['allcloud']]);expected=(1-f)*clear+f*cloud;departure=observed-expected
   delta_observed=float(observed[1]-observed[0]);delta_expected=float(expected[1]-expected[0]);delta_sampling=float(departure[1]-departure[0])
   assert abs(delta_observed-delta_expected-delta_sampling)<1e-9
   metrics[label]={'ra4_actual':float(observed[0]),'ra37_actual':float(observed[1]),'ra4_ica_mean':float(expected[0]),'ra37_ica_mean':float(expected[1]),'ra4_sample_departure':float(departure[0]),'ra37_sample_departure':float(departure[1]),'delta_observed_37_minus4':delta_observed,'delta_ica_mean_37_minus4':delta_expected,'delta_sampling_37_minus4':delta_sampling,'fully_cloudy_ra4':float(cloud[0]),'fully_cloudy_ra37':float(cloud[1])}
  # Layer-wise heating is a linear broadband response under one-layer ICA.
  h4=(1-f)*conditioned['clear'][0]['HR']+f*conditioned['allcloud'][0]['HR'];h37=(1-f)*conditioned['clear'][1]['HR']+f*conditioned['allcloud'][1]['HR']
  result[phase]={'cloud_fraction':f,'positive_cloud_layers':npositive,'metrics':metrics,'max_abs_expected_heating_delta_k_day':float(abs(h37-h4).max())}
  m=metrics['surface_down'];print(scenario.name,phase,'observed',round(m['delta_observed_37_minus4'],6),'ICA',round(m['delta_ica_mean_37_minus4'],6),'sampling',round(m['delta_sampling_37_minus4'],6))
 summary['scenarios'][scenario.name]=result
(out/'causal-decomposition.json').write_text(json.dumps(summary,indent=2)+'\n')
