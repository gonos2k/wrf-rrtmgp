from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-vapor-corrected-observed-v2';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
def imp(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=imp('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');bud=imp('bud',P.parent/'convective-support/instrument.py');vap=imp('vap',P/'instrument.py')
src=bud.transform(R);src['solve_em.F']=vap.transform(R,src['solve_em.F'])
for n,t in src.items():(O/n).write_text(t)
shutil.copyfile(P.parent/'convective-support/probe.f90',O/'budget_probe.f90');shutil.copyfile(P/'probe.f90',O/'vapor_probe.f90')
old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text());opts=['-I'+str(M),'-I'+str(B/'udm37-vapor-corrected-public-v2/modules')]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
names=['budget_probe.f90','vapor_probe.f90',*src]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},len(names)+2)
for n in names:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_'+n)
lib=O/'libWRF_Core.a';base_lib=B/'udm37-vapor-corrected-public-v2/libWRF_Core.a';shutil.copyfile(base_lib,lib);r.run(['ar','r',lib,*[O/(n+'.o') for n in names]],O,'replace_readonly_observers')
base=B/'udm37-specified-number-build-v1';link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link_observed_WRF')
h.write_json(O/'receipt.json',{'commands':r.commands,'sources':{n:h.pin(O/n) for n in names},'public_sources':{str(p.relative_to(R)):h.pin(p) for p in [R/'WRF/dyn_em/solve_em.F',R/'WRF/dyn_em/module_bc_em.F',R/'WRF/dyn_em/module_advect_em.F',R/'WRF/phys/module_physics_addtendc.F']},'base_public_library':h.pin(base_lib),'executable':h.pin(O/'wrf')})
