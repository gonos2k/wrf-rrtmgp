#!/usr/bin/env python3
from pathlib import Path
import importlib.util,shlex,os,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-specified-number-kernel-v4';O.mkdir(exist_ok=False)
def load(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=load('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');c=load('conv',R/'WRF/test/rrtmgp/convert_udm_specified.py')
base=B/'udm37-radiation-options-build-v1/producer';new=B/'udm37-specified-number-build-v1';flags={}
for l in (base/'CMakeFiles/WRF_Core.dir/flags.make').read_text().splitlines():
 if ' = ' in l:k,v=l.split(' = ',1);flags[k]=shlex.split(v)
opts=flags['Fortran_DEFINES']+['-I'+str(new/'modules')]+flags['Fortran_INCLUDES']+[x for x in flags['Fortran_FLAGS'] if not x.startswith('-J')]+['-J'+str(O),'-O0','-ffree-form','-cpp','-ffree-line-length-none','-fcheck=all','-fbacktrace']
link=shlex.split((base/'main/CMakeFiles/wrf.dir/link.txt').read_text());libs=[str(Path(x) if x.startswith('/') else (base/'main'/x).resolve()) for x in link if x.endswith(('.a','.so'))];libs=[str(new/'libWRF_Core.a') if Path(x)==base/'libWRF_Core.a' else x for x in libs]
r=h.Runner(O,180,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},6)
r.run(['gfortran',*opts,'-c',P/'kernel.f90','-o',O/'kernel.o'],O,'compile_native_probe');r.run(['gfortran','-o',O/'kernel',O/'kernel.o','-Wl,--start-group',*libs,'-Wl,--end-group'],O,'link_native_probe')
fixture=load('producer_fixture',P/'test_producer.py');fixture.manufactured(O/'manufactured.nc')
from netCDF4 import Dataset
with Dataset(O/'manufactured.nc') as ds:
 s0=float(ds['QNCLOUD_BXS'][0,0,0,0]);tend=float(ds['QNCLOUD_BTXS'][0,0,0,0])
(O/'endpoints.txt').write_text(f'{s0:.17e} {tend:.17e} 1e8 1000 1200 3600\n')
for arm in ['good','bad_density','missing_density']:
 d=O/arm;d.mkdir();(d/'endpoints.txt').write_bytes((O/'endpoints.txt').read_bytes())
 try:log=r.run([O/'kernel',arm],d,arm).read_text()
 except RuntimeError:log=(O/f'command-{r.attempts:02d}.stdout').read_text()+(O/f'command-{r.attempts:02d}.stderr').read_text()
 if arm=='good':assert 'NATIVE_BOUNDARY_KERNELS_COMPLETE' in log
 else:assert 'NATIVE_BOUNDARY_KERNELS_COMPLETE' not in log and ('invalid inverse dry density' if arm=='bad_density' else 'requires inverse dry density') in log
h.write_json(O/'receipt.json',{'commands':r.commands,'source':h.pin(P/'kernel.f90'),'converter':h.pin(R/'WRF/test/rrtmgp/convert_udm_specified.py'),'executable':h.pin(O/'kernel'),'production_library':h.pin(new/'libWRF_Core.a'),'manufactured_netcdf':h.pin(O/'manufactured.nc'),'new_WRF_runs':0,'production_accepted':False})
print('ACTUAL_NATIVE_BOUNDARY_KERNELS_COMPLETE')
