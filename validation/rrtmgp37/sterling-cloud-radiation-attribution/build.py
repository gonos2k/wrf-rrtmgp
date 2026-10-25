from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-cloud-build-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
def imp(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=imp('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');ins=imp('stins',P/'instrument.py');src=ins.transform(R)
for n,text in src.items():(O/n).write_text(text)
shutil.copyfile(P/'probe.f90',O/'sterling_cloud_probe.f90');base=B/'udm37-vapor-corrected-public-v2'
old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text());opts=['-I'+str(M),'-I'+str(base/'modules')]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
names=['sterling_cloud_probe.f90','module_ra_rrtmg_sw.F','module_first_rk_step_part1.F'];r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},5)
for n in names:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_'+n)
lib=O/'libWRF_Core.a';shutil.copyfile(base/'libWRF_Core.a',lib);r.run(['ar','r',lib,*[O/(n+'.o') for n in names]],O,'replace_readonly_cloud_observers')
orig=B/'udm37-specified-number-build-v1';link=[str(x).replace(str(orig/'libWRF_Core.a'),str(lib)).replace(str(orig/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link_observed_WRF')
h.write_json(O/'receipt.json',{'commands':r.commands,'base_library':h.pin(base/'libWRF_Core.a'),'sources':{n:h.pin(O/n) for n in names},'executable':h.pin(O/'wrf'),'production_changes':False})
