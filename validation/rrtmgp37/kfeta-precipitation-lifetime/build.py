from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-kfeta-expiry-build-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=B/'udm37-specified-number-build-v1';old=json.loads((base/'receipt.json').read_text());opts=['-I'+str(M)]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},8)
src=R/'WRF/phys/module_physics_addtendc.F';shutil.copyfile(src,O/src.name)
r.run(['gfortran',*opts,'-c',O/src.name,'-o',O/(src.name+'.o')],O,'compile_public_KFETA_fix')
lib=O/'libWRF_Core.a';shutil.copyfile(B/'udm37-restart-first-fix-build-v2/libWRF_Core.a',lib);r.run(['ar','r',lib,O/(src.name+'.o')],O,'replace_public_physics')
link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link_public_WRF')
r.run(['gfortran',*opts,'-c',P/'native.f90','-o',O/'native.o'],O,'compile_native_fixture')
libs=old['commands'][-1]['argv'];libs=libs[libs.index('-Wl,--start-group')+1:libs.index('-Wl,--end-group')]
for name,library in [('before',B/'udm37-restart-first-fix-build-v2/libWRF_Core.a'),('after',lib)]:
 d=O/name;d.mkdir();ll=[str(x).replace(str(base/'libWRF_Core.a'),str(library)) for x in libs]
 r.run(['gfortran','-o',d/'native',O/'native.o','-Wl,--start-group',*ll,'-Wl,--end-group'],d,'link_'+name)
 r.run([d/'native'],d,'actual_advance_ppt_'+name)
h.write_json(O/'receipt.json',{'commands':r.commands,'source':h.pin(src),'fixture':h.pin(P/'native.f90'),'base_library':h.pin(B/'udm37-restart-first-fix-build-v2/libWRF_Core.a'),'library':h.pin(lib),'executable':h.pin(O/'wrf')})
