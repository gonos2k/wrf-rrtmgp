from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-vapor-corrected-public-v2';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=B/'udm37-specified-number-build-v1';old=json.loads((base/'receipt.json').read_text());opts=['-I'+str(M)]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},8)
sources=[]
for n in ['module_bc_em.F','module_advect_em.F','solve_em.F']:
 src=R/'WRF/dyn_em'/n;sources.append(src);shutil.copyfile(src,O/n);r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_public_'+n)
lib=O/'libWRF_Core.a';base_lib=B/'udm37-kfeta-expiry-build-v1/libWRF_Core.a';shutil.copyfile(base_lib,lib)
r.run(['ar','r',lib,*[O/(p.name+'.o') for p in sources]],O,'replace_public_objects')
link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link_public_WRF')
r.run(['gfortran',*opts,'-c',P/'native_source.f90','-o',O/'native.o'],O,'compile_native_source_fixture')
libs=old['commands'][-1]['argv'];libs=libs[libs.index('-Wl,--start-group')+1:libs.index('-Wl,--end-group')];ll=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)) for x in libs]
r.run(['gfortran','-o',O/'native',O/'native.o','-Wl,--start-group',*ll,'-Wl,--end-group'],O,'link_native_source_fixture');r.run([O/'native'],O,'native_source_exchange')
h.write_json(O/'receipt.json',{'commands':r.commands,'sources':{str(p.relative_to(R)):h.pin(p) for p in sources},'fixture':h.pin(P/'native_source.f90'),'base_KFETA_library':h.pin(base_lib),'library':h.pin(lib),'executable':h.pin(O/'wrf')})
