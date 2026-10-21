#!/usr/bin/env python3
"""One declared nonzero host branch; not a restart equivalence experiment.

Keep the 00/06h endpoints zero, ramp a warm southern patch toward declared
12h eta endpoints, and cross the real 06h record using the fixed 05:59 state.
The endpoint dry densities are a declared conversion donor, not a prediction
of the actual atmosphere at 12h. Interpolation is in native stored S_eta.
"""
from pathlib import Path
from datetime import datetime,timedelta
import importlib.util,json,os,shutil,hashlib
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
O=B/'udm37-restart-first-nonzero-host-v1';O.mkdir(exist_ok=False)
def load(name,path):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');conv=load('convert',R/'WRF/test/rrtmgp/convert_udm_specified.py')
base=B/'udm37-restart-first-fix-run-v2';d=O/'host';d.mkdir()
for f in (base/'restart').iterdir():
 if f.is_symlink() and f.name!='wrfbdy_d01':(d/f.name).symlink_to(f.resolve())
 elif f.name in ['namelist.input','radiation_iofields.txt']:shutil.copyfile(f,d/f.name)
forcing=d/'wrfbdy_d01';shutil.copyfile(base/'continuous/wrfbdy_d01',forcing)
cp=d/'wrfrst_d01_2016-10-06_05:59:00'
with Dataset(cp) as c,Dataset(forcing) as b:
 times=[b''.join(x).decode() for x in b['Times'][:]]
 endtimes=times+[(datetime.strptime(times[-1],'%Y-%m-%d_%H:%M:%S')+timedelta(hours=6)).strftime('%Y-%m-%d_%H:%M:%S')]
 mu=np.concatenate([np.asarray(b['MU_BYS'][:]),np.asarray(b['MU_BYS'][-1:]+21600*b['MU_BTYS'][-1:])],axis=0)
 mass=(c['C1H'][0][None,None,:,None]*(mu[:,:,None,:]+c['MUB'][0,:5,:][None,:,None,:])+c['C2H'][0][None,None,:,None]).astype('f4')
 # Endpoints are native eta; explicit n/rho donors exercise the public writer.
 rho=np.broadcast_to(1/np.asarray(c['ALT'][0,:,:5,:]).transpose(1,0,2)[None],mass.shape).copy()
 temp=(np.asarray(c['T'][0,:2,:5,22:25])+300)*((np.asarray(c['P'][0,:2,:5,22:25])+np.asarray(c['PB'][0,:2,:5,22:25]))/1e5)**(287/1004.5)
 assert temp.min()>273.15
receipt={'executable':h.pin(B/'udm37-restart-first-fix-build-v2/wrf'),'checkpoint':h.pin(cp),'original_forcing':h.pin(base/'continuous/wrfbdy_d01'),'type':'declared nonzero branch; not exact restart validation','patch':{'side':'YS','width_indices_python':[0,4],'vertical_indices_python':[0,1],'x_indices_python':[22,24],'donor_temperature_K':[float(temp.min()),float(temp.max())]},'endpoint_definition':'native eta with explicit fixed 05:59 ALT density donors; n=eta*rho_donor; no assertion of actual future volume concentration','endpoint_times':endtimes,'fields':{},'production_accepted':False}
for field,water,eta_target,q_target in [('QNCLOUD','QCLOUD',1e6,1e-5),('QNRAIN','QRAIN',1e3,1e-6)]:
 eta=np.zeros_like(mass);q=np.zeros_like(mass)
 eta[2:,:,:2,22:25]=eta_target;q[2:,:,:2,22:25]=q_target
 states=mass*q
 with Dataset(forcing,'r+') as b:
  b[water+'_BYS'][:]=states[:-1];b[water+'_BTYS'][:]=np.diff(states,axis=0)/np.float32(21600)
 payload=conv.write_volume_series(forcing,field,'YS',eta.astype(float)*rho.astype(float),rho,mass,endtimes)
 receipt['fields'][field]={'eta_target_kg_dry_1':eta_target,'q_target_kg_kg_dry_1':q_target,'value_record1':payload['values'][1][0][0][23],'slope_record1':payload['tendencies'][1][0][0][23],'endpoint_record2':float(np.float32(mass[2,0,0,23]*eta_target))}
with Dataset(forcing) as new,Dataset(base/'continuous/wrfbdy_d01') as old:
 changed=[];unmodified={}
 for n in old.variables:
  aa=np.asarray(old[n][:]).tobytes();bb=np.asarray(new[n][:]).tobytes()
  if aa!=bb:changed.append(n)
  else:unmodified[n]=hashlib.sha256(aa).hexdigest()
 expected=sorted([f+'_B'+s for f in ['QCLOUD','QRAIN','QNCLOUD','QNRAIN'] for s in ['YS','TYS']]);assert sorted(changed)==expected,changed
receipt.update(changed_forcing_variables=changed,unmodified_forcing_variables=unmodified,forcing=h.pin(forcing),namelist=h.pin(d/'namelist.input'))
runner=h.Runner(O,120,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
log=runner.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',B/'udm37-restart-first-fix-build-v2/wrf'],d,'nonzero_host').read_text(errors='replace')
receipt['commands']=runner.commands;h.write_json(O/'receipt.json',receipt)
assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log
load('nonzero_analysis',P/'analyze_nonzero.py').analyze(O)
