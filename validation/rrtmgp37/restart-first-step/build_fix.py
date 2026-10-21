#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-restart-first-fix-build-v2';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=B/'udm37-specified-number-build-v1';old=json.loads((base/'receipt.json').read_text());r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},4)
(O/'solve_em_public.F').write_bytes((R/'WRF/dyn_em/solve_em.F').read_bytes())
argv=old['commands'][3]['argv'];opts=[x for x in argv[1:-4] if not x.startswith('-J')]+['-J'+str(O)];obj=O/'solve_em.F.o'
r.run(['gfortran',*opts,'-c',R/'WRF/dyn_em/solve_em.F','-o',obj],O,'compile_public_solve')
lib=O/'libWRF_Core.a';shutil.copyfile(base/'libWRF_Core.a',lib);r.run(['ar','r',lib,obj],O,'replace_solve_object')
link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link_fixed_WRF')
h.write_json(O/'receipt.json',{'commands':r.commands,'source':h.pin(R/'WRF/dyn_em/solve_em.F'),'base_library':h.pin(base/'libWRF_Core.a'),'executable':h.pin(O/'wrf'),'production_accepted':False})
print('PUBLIC_MINIMAL_FIX_BUILD_COMPLETE')
