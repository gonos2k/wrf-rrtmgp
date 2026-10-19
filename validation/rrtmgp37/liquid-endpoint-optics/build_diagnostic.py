#!/usr/bin/env python3
"""Build isolated renamed adapter with exactly four pre-scaling liquid hooks."""
from pathlib import Path
import os,sys,shlex,importlib.util,json,hashlib
ROOT=Path(__file__).resolve().parents[3];B=ROOT.parent;P=Path(__file__).resolve().parent
sys.path.insert(0,str(ROOT/'WRF/test/rrtmgp'))
s=importlib.util.spec_from_file_location('runner',ROOT/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
OUT=B/(sys.argv[1] if len(sys.argv)>1 else 'udm37-endpoint-column-v1');OUT.mkdir(exist_ok=False);(OUT/'modules').mkdir()
base=(ROOT/'WRF/phys/module_ra_rrtmgp.F').read_text();patched=base.replace('MODULE module_ra_rrtmgp','MODULE module_endpoint_adapter')
patched=patched.replace('  USE mo_rte_kind, ONLY: wp, i8','  USE endpoint_optics, ONLY: endpoint_lw,endpoint_sw\n  USE mo_rte_kind, ONLY: wp, i8')
changes=[]
for ph in ['lw','sw']:
 for path,ice in [('lwp','iwp'),('uniform_lwp','zero')]:
  old=f'      CALL require(cloud_{ph}%cloud_optics(REAL({path},wp),'+('REAL(iwp,wp)' if ice=='iwp' else 'zero')+',rl,di,clouds))'
  assert patched.count(old)==1,(ph,path)
  new=old+f'\n      CALL endpoint_{ph}(REAL({path},wp),'+('REAL(iwp,wp)' if ice=='iwp' else 'zero')+",clouds,'"+('NATIVE' if path=='lwp' else 'UNIFORM')+"')"
  patched=patched.replace(old,new);changes.append({'anchor':old,'addition':new[len(old):]})
(OUT/'module_endpoint_adapter.F').write_text(patched)
caller=(ROOT/'WRF/test/rrtmgp/lut_path_attribution.f90').read_text().replace('use module_ra_rrtmgp, only:','use module_endpoint_adapter, only:')
caller=caller.replace('  use mo_rte_kind, only: wp','  use endpoint_optics, only: endpoint_load\n  use mo_rte_kind, only: wp').replace('character(1024) :: data,input','character(1024) :: data,input,optics')
caller=caller.replace('  call trace_start(phase,1,1)','  call get_command_argument(3,optics)\n  call endpoint_load(trim(optics))\n  call trace_start(phase,1,1)')
(OUT/'caller.f90').write_text(caller)
build=B/'udm37-radiation-options-build-v1';producer=build/'producer'
flags={}
for l in (producer/'CMakeFiles/WRF_Core.dir/flags.make').read_text().splitlines():
 if ' = ' in l:
  k,v=l.split(' = ',1);flags[k]=shlex.split(v)
opts=flags['Fortran_DEFINES']+flags['Fortran_INCLUDES']+[x for x in flags['Fortran_FLAGS'] if not x.startswith('-J')]+['-J'+str(OUT/'modules'),'-I'+str(OUT/'modules'),'-ffree-form','-cpp','-O2','-ftree-vectorize','-funroll-loops','-ffree-line-length-none','-fallow-argument-mismatch','-fallow-invalid-boz']
link=shlex.split((producer/'main/CMakeFiles/wrf.dir/link.txt').read_text());libs=[str(Path(x) if x.startswith('/') else (producer/'main'/x).resolve()) for x in link if x.endswith(('.a','.so'))]
runner=h.Runner(OUT,180,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},4)
for src,obj in [(P/'endpoint_optics.f90','endpoint.o'),(OUT/'module_endpoint_adapter.F','adapter.o'),(OUT/'caller.f90','caller.o')]:
 runner.run(['gfortran',*opts,'-c',src,'-o',OUT/obj],OUT,'compile_'+obj)
runner.run(['gfortran','-o',OUT/'column',OUT/'caller.o',OUT/'adapter.o',OUT/'endpoint.o','-Wl,--start-group',*libs,'-Wl,--end-group'],OUT,'link')
h.write_json(OUT/'receipt.json',{'base_source':h.pin(ROOT/'WRF/phys/module_ra_rrtmgp.F'),'diagnostic_adapter':h.pin(OUT/'module_endpoint_adapter.F'),'caller':h.pin(OUT/'caller.f90'),'hook_source':h.pin(P/'endpoint_optics.f90'),'executable':h.pin(OUT/'column'),'library':h.pin(producer/'libWRF_Core.a'),'insertion_changes':changes,'commands':runner.commands,'runtime_production_source_modified':False})
print('DIAGNOSTIC_BUILD_COMPLETE')
