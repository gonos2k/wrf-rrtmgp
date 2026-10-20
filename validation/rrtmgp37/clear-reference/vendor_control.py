#!/usr/bin/env python3
"""Direct same-version vendor library control; isolate WRF glue from library differences."""
from pathlib import Path
import os,importlib.util,shutil,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-clear-reference-vendor-v3';O.mkdir(exist_ok=False)
U=B/'official-rrtmgp-reference/source';V=B/'udm37-radiation-options-build-v1/producer/external/rte_rrtmgp';deps=B/'deps/netcdf'
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
runner=h.Runner(O,180,{**os.environ,'LD_LIBRARY_PATH':str(deps/'lib'),'OMP_NUM_THREADS':'1'},6)
opts=['gfortran','-cpp','-O0','-ffree-line-length-none','-fcheck=all','-I'+str(V/'modules'),'-I'+str(deps/'include'),'-I'+str(O),'-J'+str(O)]
for name,f in [('mo_simple_netcdf',U/'examples/mo_simple_netcdf.F90'),('mo_load_coefficients',U/'examples/mo_load_coefficients.F90'),('direct',P/'direct.f90')]:runner.run([*opts,'-c',f,'-o',O/(name+'.o')],O,'compile_'+name)
runner.run(['gfortran','-o',O/'direct',O/'direct.o',O/'mo_load_coefficients.o',O/'mo_simple_netcdf.o',V/'libwrf_rrtmgp.a','-L'+str(deps/'lib'),'-lnetcdff','-lnetcdf'],O,'link')
for ph in ['lw','sw']:
 d=O/ph;d.mkdir();old=B/'udm37-same-state-run-v1'/(ph+'_clear')
 for f in ['input.dat','native4.txt']:shutil.copyfile(old/f,d/f)
 runner.run([O/'direct',R/'WRF/run',d/'input.dat',d/'native4.txt'],d,'direct_'+ph)
h.write_json(O/'receipt.json',{'commands':runner.commands,'pins':[h.pin(V/'libwrf_rrtmgp.a'),h.pin(O/'direct'),h.pin(P/'direct.f90')],'new_WRF_forecasts':0,'direct_vendor_calls':2,'production_accepted':False})
