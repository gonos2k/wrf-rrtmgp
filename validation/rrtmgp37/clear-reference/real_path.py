#!/usr/bin/env python3
"""Bounded current executable real-data smoke and observed research-boundary refusal."""
from pathlib import Path
import os,sys,importlib.util,shutil,re,json
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-clear-reference-real-v3';O.mkdir(exist_ok=False)
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
from zero_number_input import produce
source=B/'udm37-matthew-real-v1/case';exe=B/'udm37-radiation-options-build-v1/producer/main/wrf'
produce(source/'wrfinput_d01',source/'wrfbdy_d01',O/'number1_input')
runner=h.Runner(O,300,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},2)
for name,policy in [('legacy_real',0),('number1_boundary',1)]:
 d=O/name;d.mkdir()
 for f in (R/'WRF/run').iterdir():
  if f.is_file() and f.name!='namelist.input':(d/f.name).symlink_to(f.resolve())
 for f in ['wrfinput_d01','wrfbdy_d01']:
  p=(source if policy==0 else O/'number1_input')/f
  (d/f).symlink_to(p.resolve())
 shutil.copyfile(source/'radiation_iofields.txt',d/'radiation_iofields.txt')
 text=(source/'namelist.input').read_text()
 replacements={'run_hours':'0','run_seconds':'20','end_day':'06','end_hour':'00','time_step':'10','numtiles':'1','ra_lw_physics':'37','ra_sw_physics':'37','scalar_adv_opt':'0','history_interval':'1','iofields_filename':'"radiation_iofields.txt"','rrtmgp_data_path':"'"+str(R/'WRF/run')+"'"}
 for key,val in replacements.items():text=re.sub(r'(?m)^(\s*'+key+r'\s*=).*$',lambda m:m[1]+' '+val+',',text)
 text=text.replace('&time_control','&time_control\n end_minute=0, end_second=20,')
 text=text.replace('&physics',f'&physics\n udm_number_policy={policy}, udm_population_policy=0,\n rrtmgp_capacity_policy=0, rrtmgp_liquid_size_policy=0,')
 (d/'namelist.input').write_text(text)
 # WRF serial fatal can return zero: inspect messages and history, not RC alone.
 try:runner.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-unlimited-stack',exe],d,name)
 except RuntimeError:pass
 logs='\n'.join(x.read_text(errors='replace') for x in d.glob('rsl.*'))
 logs+='\n'+(O/f'command-{runner.attempts:02d}.stdout').read_text(errors='replace')+'\n'+(O/f'command-{runner.attempts:02d}.stderr').read_text(errors='replace')
 (d/'combined.log').write_text(logs)
 if policy==1:
  assert 'specified/nested boundaries unsupported' in logs
  assert not list(d.glob('wrfout*'))
  assert 'SUCCESS COMPLETE WRF' not in logs
 else:
  assert 'SUCCESS COMPLETE WRF' in logs,logs[-2000:]
  assert runner.commands[-1]['actual_returncode']==0 and not runner.commands[-1]['timed_out']
receipt={'commands':runner.commands,'executable':h.pin(exe),'producer':h.pin(P/'zero_number_input.py'),'new_WRF_processes':2,'short_real_legacy_completed_seconds':20,'research_number1_boundary':'REJECTED_BEFORE_HISTORY_BY_EXISTING_GUARD','research_all_warm':'not attempted; initial actual temperature reaches 192 K','production_accepted':False}
h.write_json(O/'receipt.json',receipt)
print('REAL_INPUT_FIRST_BOUNDARY_RECORDED',flush=True)
