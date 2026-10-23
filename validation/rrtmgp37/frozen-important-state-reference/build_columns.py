from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-frozen-reference-column-v2';O.mkdir(exist_ok=False);M=O/'modules';M.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
base=(R/'WRF/phys/module_ra_rrtmgp.F').read_text();text=base.replace('MODULE module_ra_rrtmgp','MODULE module_frozen_reference_adapter')
text=text.replace('  USE mo_rte_kind, ONLY: wp, i8','  USE reference_hail_hook,ONLY:apply_reference\n  USE mo_rte_kind, ONLY: wp, i8',1)
needle="    IF(status/=0) CALL require(frozen_error('RRTMGP_FROZEN_LW_HAIL',message,frozen_context))"
assert text.count(needle)==1;text=text.replace(needle,needle+'\n    CALL apply_reference(ht,tlay,hwp,lambda_h)',1)
(O/'module_frozen_reference_adapter.F').write_text(text)
for n in ['hail_hook.f90','column.f90']:shutil.copyfile(P/n,O/n)
(O/'diagnostic_column.f90').write_text((P/'column.f90').read_text().replace('use module_ra_rrtmgp,only:','use module_frozen_reference_adapter,only:',1))
old=json.loads((B/'udm37-specified-number-build-v1/receipt.json').read_text());opts=['-I'+str(M),'-I'+str(B/'udm37-vapor-corrected-public-v2/modules')]+[x for x in old['commands'][3]['argv'][1:-4] if not x.startswith('-J')]+['-J'+str(M)]
r=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},6)
for n in ['hail_hook.f90','module_frozen_reference_adapter.F','column.f90','diagnostic_column.f90']:r.run(['gfortran',*opts,'-c',O/n,'-o',O/(n+'.o')],O,'compile_'+n)
argv=old['commands'][-1]['argv'];libs=[str(x).replace(str(B/'udm37-specified-number-build-v1/libWRF_Core.a'),str(B/'udm37-vapor-corrected-public-v2/libWRF_Core.a')) for x in argv[argv.index('-Wl,--start-group')+1:argv.index('-Wl,--end-group')]]
for name,objects in [('public',['column.f90.o','hail_hook.f90.o']),('diagnostic',['diagnostic_column.f90.o','module_frozen_reference_adapter.F.o','hail_hook.f90.o'])]:r.run(['gfortran','-o',O/name,*[O/n for n in objects],'-Wl,--start-group',*libs,'-Wl,--end-group'],O,'link_'+name)
h.write_json(O/'receipt.json',{'commands':r.commands,'base_adapter':h.pin(R/'WRF/phys/module_ra_rrtmgp.F'),'diagnostic_adapter':h.pin(O/'module_frozen_reference_adapter.F'),'hook':h.pin(O/'hail_hook.f90'),'caller':h.pin(O/'column.f90'),'diagnostic_caller':h.pin(O/'diagnostic_column.f90'),'public_executable':h.pin(O/'public'),'diagnostic_executable':h.pin(O/'diagnostic'),'unchanged_public_library':h.pin(B/'udm37-vapor-corrected-public-v2/libWRF_Core.a'),'production_changes':False})
