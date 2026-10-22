from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-vapor-flux-build-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
def imp(n,p):
 s=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
h=imp('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');I=imp('ins',P/'instrument.py')
solve=I.transform(R).replace('ONLY:begin_step,capture,examine','ONLY:begin_step,capture,examine,species')
solve=I.I.surround(solve,'CALL rk_scalar_tend (  im, im,',before=' CALL species(im==P_QV)\n')
(O/'solve_em.F').write_text(solve);shutil.copyfile(P/'flux_probe.f90',O/'probe.f90')
ad=(R/'WRF/dyn_em/module_advect_em.F').read_text().replace('MODULE module_advect_em','MODULE module_advect_em\n USE module_vapor_first_probe,ONLY:want_flux,record_flux',1)
a=ad.index('SUBROUTINE advect_scalar_pd ');b=ad.index('END SUBROUTINE advect_scalar_pd',a);part=ad[a:b]
faces='fqx(7,20,49),fqx(8,20,49),fqy(7,20,49),fqy(7,20,50),fqz(7,20,49),fqz(7,21,49), &\n fqxl(7,20,49),fqxl(8,20,49),fqyl(7,20,49),fqyl(7,20,50),fqzl(7,20,49),fqzl(7,21,49)'
args='field_old(7,20,49),c1(20),c2(20),mu_old(7,49),mub(7,49),msftx(7,49),msfty(7,49), &\n rdx,rdy,rdzw(20),dt,ph_low(7,20,49),flux_out(7,20,49), &\n '+faces
needle='     IF( flux_out(i,k,j) .gt. ph_low(i,k,j) ) THEN';pos=part.rfind('   DO j=',0,part.index(needle));part=part[:pos]+" IF(want_flux())CALL record_flux('before',time_step,[ &\n "+args+"])\n"+part[pos:]
pos=part.index('! add in the pd-limited flux divergence');part=part[:pos]+" IF(want_flux())CALL record_flux('after',time_step,[ &\n "+args+"])\n"+part[pos:]
part += " IF(want_flux())CALL record_flux('tendency',time_step,[tendency(7,20,49)])\n"
ad=ad[:a]+part+ad[b:];(O/'module_advect_em.F').write_text(ad)
old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text());opts=['-I'+str(M)]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},5)
for n in ['probe.f90','solve_em.F','module_advect_em.F']:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_'+n)
lib=O/'libWRF_Core.a';shutil.copyfile(B/'udm37-restart-first-fix-build-v2/libWRF_Core.a',lib);r.run(['ar','r',lib,*[O/(n+'.o') for n in ['probe.f90','solve_em.F','module_advect_em.F']]],O,'replace_observer')
base=B/'udm37-specified-number-build-v1';link=[str(x).replace(str(base/'libWRF_Core.a'),str(lib)).replace(str(base/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link')
h.write_json(O/'receipt.json',{'commands':r.commands,'sources':{n:h.pin(O/n) for n in ['probe.f90','solve_em.F','module_advect_em.F']},'executable':h.pin(O/'wrf')})
