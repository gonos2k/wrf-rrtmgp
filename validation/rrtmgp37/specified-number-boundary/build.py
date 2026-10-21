#!/usr/bin/env python3
"""Incrementally compile current public boundary sources into an isolated library."""
from pathlib import Path
import shlex,os,importlib.util,shutil,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-specified-number-build-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=B/'udm37-radiation-options-build-v1/producer';flags={}
for l in (base/'CMakeFiles/WRF_Core.dir/flags.make').read_text().splitlines():
 if ' = ' in l:k,v=l.split(' = ',1);flags[k]=shlex.split(v)
# Current source include directories take precedence over retained build snapshots.
incs=[f'-I{M}',f'-I{R}/WRF/share',f'-I{R}/WRF/dyn_em',f'-I{R}/WRF/phys',f'-I{R}/WRF/inc',f'-I{R}/WRF/frame']+flags['Fortran_INCLUDES']
opts=flags['Fortran_DEFINES']+incs+[x for x in flags['Fortran_FLAGS'] if not x.startswith('-J')]+[f'-J{M}','-O2','-ffree-form','-cpp','-ffree-line-length-none','-fallow-argument-mismatch','-fallow-invalid-boz']
runner=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},8)
lib=O/'libWRF_Core.a';shutil.copyfile(base/'libWRF_Core.a',lib)
files=['share/module_bc.F','share/input_wrf.F','share/output_wrf.F','dyn_em/solve_em.F'];objects=[]
for f in files:
 src=R/'WRF'/f;obj=O/(Path(f).name+'.o');objects.append(obj);runner.run(['gfortran',*opts,'-c',src,'-o',obj],O,'compile_'+Path(f).stem)
runner.run(['ar','r',lib,*objects],O,'replace_current_objects')
link=shlex.split((base/'main/CMakeFiles/wrf.dir/link.txt').read_text());libs=[str(Path(x) if x.startswith('/') else (base/'main'/x).resolve()) for x in link if x.endswith(('.a','.so'))];libs=[str(lib) if Path(x)==base/'libWRF_Core.a' else x for x in libs]
main=[base/'main/CMakeFiles/wrf.dir/wrf.F.o',base/'main/CMakeFiles/wrf.dir/module_wrf_top.F.o']
runner.run(['gfortran','-o',O/'wrf',*main,'-Wl,--start-group',*libs,'-Wl,--end-group'],O,'link_general_WRF')
h.write_json(O/'receipt.json',{'commands':runner.commands,'base_library':h.pin(base/'libWRF_Core.a'),'base_executable':h.pin(base/'main/wrf'),'sources':{f:h.pin(R/'WRF'/f) for f in files},'library':h.pin(lib),'executable':h.pin(O/'wrf'),'objects_rebuilt':files,'remaining_objects':'unchanged inherited PR180/187 general serial build; not a fresh full WRF build'})
print('GENERAL_SPECIFIED_NUMBER_BUILD_COMPLETE')
