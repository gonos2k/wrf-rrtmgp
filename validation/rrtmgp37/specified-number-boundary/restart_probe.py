#!/usr/bin/env python3
"""Observe the restored checkpoint state before its first integrated step."""
from pathlib import Path
import os,importlib.util,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-specified-number-restart-probe-v1';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
seed=B/'udm37-specified-number-run-v2/restart'
for p in seed.iterdir():
 if p.is_symlink():(O/p.name).symlink_to(p.resolve())
 elif p.name in ['namelist.input','radiation_iofields.txt']:shutil.copyfile(p,O/p.name)
text=(O/'namelist.input').read_text().replace('&time_control','&time_control\n write_hist_at_0h_rst=.true.,');(O/'namelist.input').write_text(text)
r=h.Runner(O,180,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
log=r.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',B/'udm37-specified-number-build-v1/wrf'],O,'observe_restore').read_text();assert 'SUCCESS COMPLETE WRF' in log
h.write_json(O/'receipt.json',{'commands':r.commands,'executable':h.pin(B/'udm37-specified-number-build-v1/wrf'),'namelist':h.pin(O/'namelist.input'),'purpose':'first-restored-state localization; does not erase original non-bitwise restart','production_accepted':False})
