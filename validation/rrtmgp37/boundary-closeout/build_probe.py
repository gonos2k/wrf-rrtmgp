#!/usr/bin/env python3
"""Compile a read-only private observer against the unchanged PR189 library."""
from pathlib import Path
import importlib.util,json,os,re,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-boundary-closeout-probe-build-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
s=importlib.util.spec_from_file_location('instrument',P/'instrument.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
bc,solve=m.instrument((R/'WRF/share/module_bc.F').read_text(),(R/'WRF/dyn_em/solve_em.F').read_text())
(O/'module_bc_probe.F').write_text(bc);(O/'solve_em_probe.F').write_text(solve)
base=B/'udm37-specified-number-build-v1';old=json.loads((base/'receipt.json').read_text());fixed=B/'udm37-restart-first-fix-build-v2'
runner=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},5)
for source,obj,command in [(P/'probe.f90','probe.o',3),(O/'module_bc_probe.F','module_bc.F.o',0),(O/'solve_em_probe.F','solve_em.F.o',3)]:
 argv=old['commands'][command]['argv'];opts=['-I'+str(M)]+[x for x in argv[1:-4] if not x.startswith('-J')]+['-J'+str(M)]
 runner.run(['gfortran',*opts,'-c',source,'-o',O/obj],O,'compile_'+obj)
lib=O/'libWRF_Core.a';shutil.copyfile(fixed/'libWRF_Core.a',lib);runner.run(['ar','r',lib,O/'module_bc.F.o',O/'solve_em.F.o',O/'probe.o'],O,'replace_private_observer_objects')
link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];runner.run(link,O,'link_private_observer')
h.write_json(O/'receipt.json',{'commands':runner.commands,'public_sources':{n:h.pin(R/n) for n in ['WRF/share/module_bc.F','WRF/dyn_em/solve_em.F','WRF/dyn_em/module_bc_em.F']},'private_sources':{p.name:h.pin(p) for p in [P/'probe.f90',O/'module_bc_probe.F',O/'solve_em_probe.F']},'base_library':h.pin(fixed/'libWRF_Core.a'),'executable':h.pin(O/'wrf'),'production_accepted':False});print('BOUNDARY_CLOSEOUT_PRIVATE_BUILD_COMPLETE')
