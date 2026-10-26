"""Build a private observed executable from the unchanged corrected public library."""
from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-thermodynamic-build-v1'
def imp(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def main():
 O.mkdir(exist_ok=False);M=O/'modules';M.mkdir();h=imp('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');ins=imp('instrument',P/'instrument.py')
 for n,t in ins.transform(R).items():(O/n).write_text(t)
 shutil.copyfile(P/'probe.f90',O/'thermodynamic_probe.f90');base=B/'udm37-vapor-corrected-public-v2';old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text());opts=['-I'+str(M),'-I'+str(base/'modules')]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
 names=['thermodynamic_probe.f90','module_advect_em.F','module_small_step_em.F','module_em.F','module_physics_addtendc.F','module_first_rk_step_part2.F','solve_em.F'];r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},9)
 for n in names:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_private_observer_'+n)
 lib=O/'libWRF_Core.a';shutil.copyfile(base/'libWRF_Core.a',lib);r.run(['ar','r',lib,*[O/(n+'.o') for n in names]],O,'insert_readonly_observers')
 orig=B/'udm37-specified-number-build-v1';link=[str(x).replace(str(orig/'libWRF_Core.a'),str(lib)).replace(str(orig/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link_private_observed_WRF');h.write_json(O/'receipt.json',{'commands':r.commands,'sources':{n:h.pin(O/n) for n in names},'base_library':h.pin(base/'libWRF_Core.a'),'executable':h.pin(O/'wrf'),'production_changes':False})
if __name__=='__main__':main()
