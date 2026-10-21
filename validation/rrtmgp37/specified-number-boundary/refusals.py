#!/usr/bin/env python3
"""Actual file/config refusal paths, not return-code-only checks."""
from pathlib import Path
import importlib.util,os,shutil,re,json
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-specified-number-refusals-v1';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
r=h.Runner(O,180,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},6);source=B/'udm37-specified-number-run-v2';exe=B/'udm37-specified-number-build-v1/wrf';outcomes=[]
for case in ['missing_initial','noninteger_initial','missing_boundary','missing_restart','missing_scalar_bcs','population2']:
 d=O/case;d.mkdir();restart=case=='missing_restart';template=source/('restart' if restart else 'continuous')
 for p in template.iterdir():
  if p.is_symlink() and not p.name.startswith(('wrfinput','wrfbdy','wrfrst')):(d/p.name).symlink_to(p.resolve())
 shutil.copyfile(template/'radiation_iofields.txt',d/'radiation_iofields.txt')
 for n in ['wrfinput_d01','wrfbdy_d01']:shutil.copyfile(source/'encoded'/n,d/n)
 if restart:
  n='wrfrst_d01_2016-10-06_05:59:00';shutil.copyfile(source/'continuous'/n,d/n)
 text=(template/'namelist.input').read_text()
 if case in ['missing_initial','noninteger_initial','missing_boundary','missing_restart']:
  file=d/('wrfbdy_d01' if case=='missing_boundary' else 'wrfrst_d01_2016-10-06_05:59:00' if restart else 'wrfinput_d01')
  with Dataset(file,'r+') as ds:
   ds.delncattr('UDM_SPECIFIED_NUMBER_CONTRACT')
   if case=='noninteger_initial':ds.setncattr('UDM_SPECIFIED_NUMBER_CONTRACT','1')
 if case=='missing_scalar_bcs':text=re.sub(r'(?m)^(\s*have_bcs_scalar\s*=).*$',r'\g<1> .false.,',text)
 if case=='population2':
  text=re.sub(r'(?m)^(\s*udm_population_policy\s*=).*$',r'\g<1> 2,',text)
  for n in ['wrfinput_d01','wrfbdy_d01']:
   with Dataset(d/n,'r+') as ds:ds.setncattr('UDM_POPULATION_POLICY',__import__('numpy').int32(2))
 (d/'namelist.input').write_text(text)
 try:log=r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],d,case).read_text(errors='replace')
 except RuntimeError:log=(O/f'command-{r.attempts:02d}.stdout').read_text(errors='replace')+(O/f'command-{r.attempts:02d}.stderr').read_text(errors='replace')
 expected='encoded S_eta contract=1' if case.startswith(('missing_initial','noninteger_initial','missing_boundary','missing_restart')) else 'moisture/scalar BCs and research radiation OFF'
 assert expected in log and 'FATAL CALLED' in log and 'SUCCESS COMPLETE WRF' not in log,case+' '+log[-1000:]
 outcomes.append({'case':case,'expected':expected,'actual_returncode':r.commands[-1]['actual_returncode'],'history_files':[p.name for p in d.glob('wrfout*')],'namelist':h.pin(d/'namelist.input')})
h.write_json(O/'receipt.json',{'commands':r.commands,'outcomes':outcomes,'executable':h.pin(exe),'production_accepted':False})
print('ACTUAL_SPECIFIED_NUMBER_REFUSALS_COMPLETE',len(outcomes))
