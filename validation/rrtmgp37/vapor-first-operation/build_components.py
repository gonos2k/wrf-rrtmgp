from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-vapor-components-build-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
def imp(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=imp('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');I=imp('ins',P/'instrument.py');sl=I.I.SL
solve=I.transform(R).replace('ONLY:begin_step,capture,examine','ONLY:begin_step,capture,examine,point')
for needle,tag in [('CALL relax_bdy_scalar ( moist_tend','relax'),('CALL spec_bdy_scalar  ( moist_tend','spec')]:
 solve=I.I.surround(solve,needle,before=f" IF(im==P_QV)CALL point('{tag}_before',moist_tend({sl},P_QV))\n",after=f" IF(im==P_QV)CALL point('{tag}_after',moist_tend({sl},P_QV))\n")
solve=I.I.surround(solve,'CALL first_rk_step_part2 (',after=f" CALL point('all_coupled_physics',moist_tend({sl},P_QV))\n")
(O/'solve_em.F').write_text(solve);shutil.copyfile(P/'component_probe.f90',O/'probe.f90')
ph=(R/'WRF/phys/module_physics_addtendc.F').read_text().replace('MODULE module_physics_addtendc','MODULE module_physics_addtendc\n USE module_vapor_first_probe,ONLY:point',1)
for name,tag in [('phy_bl_ten','pbl'),('phy_cu_ten','CU')]:
 a,b=I.I.bounds(ph,'CALL '+name+'(');a=ph.rfind('\n   if ',0,a)+1
 ph=ph[:a]+f" CALL point('{tag}_before',moist_tendf(ids:ide-1,kds:kde-1,jds:jde-1,P_QV))\n"+ph[a:b]+f"\n CALL point('{tag}_after',moist_tendf(ids:ide-1,kds:kde-1,jds:jde-1,P_QV))\n"+ph[b:]
(O/'module_physics_addtendc.F').write_text(ph)
old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text());opts=['-I'+str(M)]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},5)
for n in ['probe.f90','solve_em.F','module_physics_addtendc.F']:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_'+n)
lib=O/'libWRF_Core.a';shutil.copyfile(B/'udm37-restart-first-fix-build-v2/libWRF_Core.a',lib);r.run(['ar','r',lib,*[O/(n+'.o') for n in ['probe.f90','solve_em.F','module_physics_addtendc.F']]],O,'replace_observer')
base=B/'udm37-specified-number-build-v1';link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link')
h.write_json(O/'receipt.json',{'commands':r.commands,'sources':{n:h.pin(O/n) for n in ['probe.f90','solve_em.F','module_physics_addtendc.F']},'executable':h.pin(O/'wrf')})
