from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-vapor-roundoff-build-v2';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text());opts=['-I'+str(M)]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},3)
src=R/'WRF/dyn_em/module_advect_em.F';shutil.copyfile(src,O/src.name)
r.run(['gfortran',*opts,'-c',O/src.name,'-o',O/(src.name+'.o')],O,'compile_public_roundoff_candidate')
lib=O/'libWRF_Core.a';base_lib=B/'udm37-vapor-first-build-v1/libWRF_Core.a';shutil.copyfile(base_lib,lib);r.run(['ar','r',lib,O/(src.name+'.o')],O,'replace_public_advection')
base=B/'udm37-specified-number-build-v1';link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link')
h.write_json(O/'receipt.json',{'commands':r.commands,'source':h.pin(src),'base_observer_library':h.pin(base_lib),'executable':h.pin(O/'wrf')})
