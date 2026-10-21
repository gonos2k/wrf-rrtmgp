#!/usr/bin/env python3
from pathlib import Path
import importlib.util,json,os
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-boundary-closeout-halo-v1';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=B/'udm37-specified-number-build-v1';rec=json.loads((base/'receipt.json').read_text());opts=[x for x in rec['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(O)]
link=rec['commands'][-1]['argv'];libs=[str(x).replace(str(base/'libWRF_Core.a'),str(B/'udm37-restart-first-fix-build-v2/libWRF_Core.a')) for x in link[link.index('-Wl,--start-group')+1:link.index('-Wl,--end-group')]]
r=h.Runner(O,120,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib')},3)
r.run(['gfortran',*opts,'-c',P/'common_halo.f90','-o',O/'common_halo.o'],O,'compile_native_halo_fixture');r.run(['gfortran','-o',O/'common_halo',O/'common_halo.o','-Wl,--start-group',*libs,'-Wl,--end-group'],O,'link_public_native_halo');text=r.run([O/'common_halo'],O,'native_policies_tiles_and_idempotence').read_text();assert 'COMMON_SPECIFIED_HALO_COMPLETE' in text
h.write_json(O/'receipt.json',{'commands':r.commands,'fixture':h.pin(P/'common_halo.f90'),'library':h.pin(B/'udm37-restart-first-fix-build-v2/libWRF_Core.a'),'public_source':h.pin(R/'WRF/share/module_bc.F'),'output':h.pin(O/'command-03.stdout'),'production_accepted':False});print(text)
