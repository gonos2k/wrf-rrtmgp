from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-kfeta-expiry-probe-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
def imp(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=imp('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');I=imp('budget_i',P.parent/'real-case-budget/instrument.py')
ins=imp('kf_lifetime_instrument',P/'instrument.py');transform=ins.transform
(O/'solve_em.F').write_text(transform(R));shutil.copyfile(P/'probe.f90',O/'probe.f90')
base=B/'udm37-specified-number-build-v1';old=json.loads((base/'receipt.json').read_text());opts=['-I'+str(M)]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},4)
for n in ['probe.f90','solve_em.F']:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_'+n)
lib=O/'libWRF_Core.a';shutil.copyfile(B/'udm37-kfeta-expiry-build-v1/libWRF_Core.a',lib);r.run(['ar','r',lib,O/'probe.f90.o',O/'solve_em.F.o'],O,'replace_read_only_solve')
link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link')
h.write_json(O/'receipt.json',{'commands':r.commands,'public_source':h.pin(R/'WRF/dyn_em/solve_em.F'),'private_source':h.pin(O/'solve_em.F'),'helper':h.pin(O/'probe.f90'),'executable':h.pin(O/'wrf'),'base_library':h.pin(B/'udm37-kfeta-expiry-build-v1/libWRF_Core.a')})
