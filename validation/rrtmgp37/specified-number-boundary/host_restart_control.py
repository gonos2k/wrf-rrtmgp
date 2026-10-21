#!/usr/bin/env python3
"""Counterfactual old number0 path for a newly observed full-host restart difference."""
from pathlib import Path
import os,importlib.util,shutil,re,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-specified-number-host-control-v1';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
source=B/'udm37-matthew-real-v1/case';actual=B/'udm37-specified-number-run-v2';exe=B/'udm37-specified-number-build-v1/wrf'
r=h.Runner(O,900,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},2);receipt={'hypothesis':'same host full-array restart question in number0, not an acceptance-tolerance change','runs':[],'production_accepted':False}
for arm in ['continuous','restart']:
 d=O/arm;d.mkdir();template=actual/arm
 for p in template.iterdir():
  if p.is_symlink() and not p.name.startswith(('wrfinput','wrfbdy','wrfrst')):(d/p.name).symlink_to(p.resolve())
 for n in ['wrfinput_d01','wrfbdy_d01']:(d/n).symlink_to((source/n).resolve())
 if arm=='restart':
  n='wrfrst_d01_2016-10-06_05:59:00';(d/n).symlink_to((O/'continuous'/n).resolve(strict=True))
 shutil.copyfile(template/'radiation_iofields.txt',d/'radiation_iofields.txt')
 text=(template/'namelist.input').read_text()
 for key,val in [('udm_number_policy','0'),('have_bcs_scalar','.false.'),('have_bcs_moist','.false.')]:text=re.sub(r'(?m)^(\s*'+key+r'\s*=).*$',lambda m:m[1]+' '+val+',',text)
 if arm=='restart':text=text.replace('&time_control','&time_control\n write_hist_at_0h_rst=.true.,')
 (d/'namelist.input').write_text(text);log=r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],d,arm).read_text();assert 'SUCCESS COMPLETE WRF' in log and 'FATAL CALLED' not in log
 receipt['runs'].append(arm);receipt['commands']=r.commands;h.write_json(O/'receipt.json',receipt);print('HOST_CONTROL_COMPLETE',arm,flush=True)
