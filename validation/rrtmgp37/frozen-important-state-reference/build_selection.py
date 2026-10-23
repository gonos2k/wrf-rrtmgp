from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-frozen-selected-build-v1';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=B/'udm37-vapor-corrected-observed-v2';text=(base/'module_ra_rrtmg_lw.F').read_text()
text=text.replace(' USE module_real_budget_probe,ONLY:column,frozen',' USE module_real_budget_probe,ONLY:column,frozen\n USE module_frozen_selection_probe,ONLY:select_column',1)
needle='         IF(gp_batch_enabled) THEN';pos=text.index(needle,text.index('gp_seed=rrtmgp_column_seed'))
text=text[:pos]+'''         IF(run_rrtmgp.AND.gp_frozen)CALL select_column(i,j,audit_time,tlay(1,kts:kte), &
          gp_hwp(1,kts:kte),gp_lambda_h(1,kts:kte))
'''+text[pos:]
(O/'module_ra_rrtmg_lw.F').write_text(text);shutil.copyfile(P/'selection_probe.f90',O/'selection_probe.f90')
old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text());opts=['-I'+str(M),'-I'+str(base/'modules'),'-I'+str(B/'udm37-vapor-corrected-public-v2/modules')]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},4)
for n in ['selection_probe.f90','module_ra_rrtmg_lw.F']:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_'+n)
lib=O/'libWRF_Core.a';shutil.copyfile(base/'libWRF_Core.a',lib);r.run(['ar','r',lib,O/'selection_probe.f90.o',O/'module_ra_rrtmg_lw.F.o'],O,'replace_selection_observer')
orig=B/'udm37-specified-number-build-v1';link=[str(x).replace(str(orig/'libWRF_Core.a'),str(lib)).replace(str(orig/'wrf'),str(O/'wrf')) for x in old['commands'][-1]['argv']];r.run(link,O,'link_observed_WRF')
h.write_json(O/'receipt.json',{'commands':r.commands,'base_library':h.pin(base/'libWRF_Core.a'),'base_LW_source':h.pin(base/'module_ra_rrtmg_lw.F'),'observer_source':h.pin(O/'module_ra_rrtmg_lw.F'),'helper':h.pin(O/'selection_probe.f90'),'executable':h.pin(O/'wrf'),'production_changes':False})
