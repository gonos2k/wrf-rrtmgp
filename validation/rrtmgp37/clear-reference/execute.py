#!/usr/bin/env python3
"""Pinned standalone reference calls; never modifies forecast state or production source."""
from pathlib import Path
import importlib.util,os,shutil,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
O=B/'udm37-clear-reference-run-v4';O.mkdir(exist_ok=False);D=O/'build';D.mkdir()
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
U=B/'official-rrtmgp-reference/source';libs=[U/'build/librrtmgp.a',U/'build/librte.a'];deps=B/'deps/netcdf'
env={**os.environ,'LD_LIBRARY_PATH':str(deps/'lib'),'OMP_NUM_THREADS':'1'}
run=h.Runner(O,180,env,8);pins=[h.pin(P/'direct.f90'),h.pin(P/'plan.json')]
opts=['gfortran','-cpp','-O0','-ffree-line-length-none','-fcheck=all','-fbacktrace','-I'+str(U/'build'),'-I'+str(deps/'include'),'-J'+str(D),'-I'+str(D)]
# The precision kind comes from the pinned upstream module.
for name in ['mo_simple_netcdf','mo_load_coefficients']:
 f=U/'examples'/(name+'.F90');pins.append(h.pin(f));run.run([*opts,'-c',f,'-o',D/(name+'.o')],D,'compile_'+name)
run.run([*opts,'-c',P/'direct.f90','-o',D/'direct.o'],D,'compile_direct')
run.run(['gfortran','-o',D/'direct',D/'direct.o',D/'mo_load_coefficients.o',D/'mo_simple_netcdf.o','-Wl,--start-group',*libs,'-Wl,--end-group','-L'+str(deps/'lib'),'-lnetcdff','-lnetcdf'],D,'link_direct')
for ph in ['lw','sw']:
 d=O/ph;d.mkdir();old=B/'udm37-same-state-run-v1'/(ph+'_clear')
 for f in ['input.dat','native4.txt']:shutil.copyfile(old/f,d/f)
 before=h.pin(d/'input.dat');run.run([D/'direct',R/'WRF/run',d/'input.dat',d/'native4.txt'],d,'direct_'+ph)
 assert before==h.pin(d/'input.dat')
 for f in ['input.dat','native4.txt']:pins.append(h.pin(d/f))
# One diagnostic source export at exactly the old clear LW state.
d=O/'legacy_source';d.mkdir();(d/'export4').mkdir();(d/'capture').mkdir()
for f in ['RRTMG_LW_DATA','RRTMG_SW_DATA']:(d/f).symlink_to((R/'WRF/run'/f).resolve())
shutil.copyfile(B/'udm37-same-state-run-v1/lw_clear/input.dat',d/'input.dat')
run.environment.update(WRF_RRTMGP_CAPTURE_DIR=str(d/'capture'),WRF_RRTMGP_CAPTURE_CALL='1',WRF_RRTMGP_RRTMG4_EXPORT_DIR=str(d/'export4'),WRF_RRTMGP_RRTMG4_EXPORT_DOMAIN='1',WRF_RRTMGP_RRTMG4_EXPORT_I='1',WRF_RRTMGP_RRTMG4_EXPORT_J='2',WRF_RRTMGP_RRTMG4_EXPORT_STEP='6511',WRF_RRTMGP_RRTMG4_EXPORT_SECONDS='65100',WRF_RRTMGP_RRTMG4_EXPORT_LW_SOURCE='1')
run.run([B/'udm37-same-state-build-v1/compare',R/'WRF/run',d/'input.dat'],d,'legacy_source')
assert (d/'native4.txt').read_bytes()==(B/'udm37-same-state-run-v1/lw_clear/native4.txt').read_bytes()
assert (d/'before.bin').read_bytes()==(d/'after4.bin').read_bytes()==(d/'after37.bin').read_bytes()
pins += [h.pin(x) for x in libs]+[h.pin(D/'direct'),h.pin(B/'udm37-same-state-build-v1/compare')]
h.write_json(O/'receipt.json',{'commands':run.commands,'pins':pins,'new_WRF_forecasts':0,'direct_upstream_calls':2,'additional_paired_calls':2,'production_accepted':False})
print('CLEAR_REFERENCE_EXECUTION_COMPLETE',flush=True)
