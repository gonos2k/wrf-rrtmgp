from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-native-sw-build-v4';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
def imp(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=imp('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');ins=imp('sw_ins',P/'instrument.py')
src=ins.transform(R)
# Reuse the completed actual budget/vapor observer build. Only SW and solve calls are new.
for n in ['solve_em.F','module_ra_rrtmg_sw.F','module_first_rk_step_part1.F']:(O/n).write_text(src[n])
shutil.copyfile(P/'probe.f90',O/'sw_phase_probe.f90')
old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text())
opts=['-I'+str(M),'-I'+str(B/'udm37-vapor-corrected-observed-v2/modules'),'-I'+str(B/'udm37-vapor-corrected-public-v2/modules')]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
names=['sw_phase_probe.f90','module_ra_rrtmg_sw.F','module_first_rk_step_part1.F','solve_em.F']
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},6)
for n in names:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_'+n)
lib=O/'libWRF_Core.a';base_lib=B/'udm37-vapor-corrected-observed-v2/libWRF_Core.a';shutil.copyfile(base_lib,lib)
r.run(['ar','r',lib,*[O/(n+'.o') for n in names]],O,'replace_readonly_SW_observers')
base=B/'udm37-specified-number-build-v1';link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link_observed_WRF')
h.write_json(O/'receipt.json',{'commands':r.commands,'sources':{n:h.pin(O/n) for n in names},'public_sources':{str(p.relative_to(R)):h.pin(p) for p in [R/'WRF/dyn_em/solve_em.F',R/'WRF/phys/module_ra_rrtmg_sw.F']},'base_observed_library':h.pin(base_lib),'executable':h.pin(O/'wrf')})
