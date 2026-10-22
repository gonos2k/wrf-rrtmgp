from pathlib import Path
import importlib.util,json,os
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-vapor-native-transport-v2';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=B/'udm37-specified-number-build-v1';old=json.loads((base/'receipt.json').read_text());M=B/'udm37-vapor-corrected-public-v2/modules';opts=['-I'+str(M)]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},3)
r.run(['gfortran',*opts,'-c',P/'native_transport.f90','-o',O/'native.o'],O,'compile_actual_transport_fixture')
libs=old['commands'][-1]['argv'];libs=libs[libs.index('-Wl,--start-group')+1:libs.index('-Wl,--end-group')];lib=B/'udm37-vapor-corrected-public-v2/libWRF_Core.a';ll=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)) for x in libs]
r.run(['gfortran','-o',O/'native',O/'native.o','-Wl,--start-group',*ll,'-Wl,--end-group'],O,'link_actual_transport_fixture');r.run([O/'native'],O,'native_shared_flux')
h.write_json(O/'receipt.json',{'commands':r.commands,'fixture':h.pin(P/'native_transport.f90'),'public_library':h.pin(lib)})
