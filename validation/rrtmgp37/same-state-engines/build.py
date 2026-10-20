#!/usr/bin/env python3
from pathlib import Path
import os,sys,shlex,importlib.util,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;OUT=B/'udm37-same-state-build-v1';OUT.mkdir(exist_ok=False);(OUT/'modules').mkdir()
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
producer=B/'udm37-radiation-options-build-v1/producer';flags={}
for l in (producer/'CMakeFiles/WRF_Core.dir/flags.make').read_text().splitlines():
 if ' = ' in l:k,v=l.split(' = ',1);flags[k]=shlex.split(v)
opts=flags['Fortran_DEFINES']+flags['Fortran_INCLUDES']+[x for x in flags['Fortran_FLAGS'] if not x.startswith('-J')]+['-J'+str(OUT/'modules'),'-I'+str(OUT/'modules'),'-ffree-form','-cpp','-O2','-ffree-line-length-none','-fcheck=all','-fbacktrace']
link=shlex.split((producer/'main/CMakeFiles/wrf.dir/link.txt').read_text());libs=[str(Path(x) if x.startswith('/') else (producer/'main'/x).resolve()) for x in link if x.endswith(('.a','.so'))]
runner=h.Runner(OUT,180,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},2)
runner.run(['gfortran',*opts,'-c',P/'compare.f90','-o',OUT/'compare.o'],OUT,'compile_caller')
runner.run(['gfortran','-o',OUT/'compare',OUT/'compare.o','-Wl,--start-group',*libs,'-Wl,--end-group'],OUT,'link')
h.write_json(OUT/'receipt.json',{'caller':h.pin(P/'compare.f90'),'executable':h.pin(OUT/'compare'),'libraries':[h.pin(Path(x)) for x in libs],'commands':runner.commands,'unchanged_production_library':True})
print('SAME_STATE_BUILD_COMPLETE')
