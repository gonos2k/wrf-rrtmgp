#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-real-budget-build-v5';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
def imp(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=imp('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');m=imp('ins',P/'instrument.py')
for n,t in m.transform(R).items():(O/n).write_text(t)
base=B/'udm37-specified-number-build-v1';old=json.loads((base/'receipt.json').read_text());fixed=B/'udm37-restart-first-fix-build-v2'
runner=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},8)
shutil.copyfile(P/'probe.f90',O/'probe.f90')
srcs=[O/'probe.f90']+list(O.glob('*.F'))
for src in srcs:
 opts=['-I'+str(M)]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
 runner.run(['gfortran',*opts,'-c',src,'-o',O/(src.name+'.o')],O,'compile_'+src.name)
lib=O/'libWRF_Core.a';shutil.copyfile(fixed/'libWRF_Core.a',lib)
# Archive uses native basename.F.o members, exactly as the production library.
runner.run(['ar','r',lib,*[O/(p.name+'.o') for p in srcs]],O,'replace_private_objects')
link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];runner.run(link,O,'link')
h.write_json(O/'receipt.json',{'commands':runner.commands,'public_sources':{str(p.relative_to(R)):h.pin(p) for p in [R/'WRF/dyn_em/solve_em.F',R/'WRF/dyn_em/module_em.F',*[R/'WRF/phys'/n for n in list(m.transform(R))[1:] if n!='module_em.F']]},'private_sources':{p.name:h.pin(p) for p in srcs},'base_library':h.pin(fixed/'libWRF_Core.a'),'executable':h.pin(O/'wrf')})
print('REAL_BUDGET_PRIVATE_BUILD_COMPLETE')
