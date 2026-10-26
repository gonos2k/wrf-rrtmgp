"""One bounded observed restart from the qualified cold11:58 checkpoint."""
from pathlib import Path
import importlib.util,json,os,re
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
def main():
 O=B/'udm37-sterling-thermodynamic-run-v1';O.mkdir(exist_ok=False);D=O/'host';D.mkdir();C=B/'udm37-sterling-interior-day-v1/host'
 s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
 cp=C/'wrfrst_d01_2016-10-06_11:58:00';assert cp.exists();(D/cp.name).symlink_to(cp)
 for p in C.iterdir():
  if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 io='\n'.join(x for x in (C/'radiation_iofields.txt').read_text().splitlines() if x.strip())+'\n';assert all(io.splitlines());(D/'radiation_iofields.txt').write_text(io)
 nml=(C/'namelist.input').read_text();changes={'run_seconds':'18120','start_hour':'11','start_minute':'58','end_day':'06','end_hour':'17','end_minute':'0','end_second':'0','history_begin_s':'120','history_interval_s':'3600','restart_interval_s':'1000000','restart':'.true.','override_restart_timers':'.true.','auxhist7_begin_s':'1000000','auxhist7_end_s':'1000001','auxhist8_begin_s':'1000000','auxhist8_end_s':'1000001'}
 for name,value in changes.items():
  if not re.search(r'(?im)^\s*'+name+r'\s*=',nml):nml=nml.replace('&time_control','&time_control\n '+name+' = '+value+',',1)
  nml,count=re.subn(r'(?im)^(\s*'+name+r'\s*=\s*)[^,\n]+',lambda m:m[1]+value,nml);assert count==1,name
 (D/'namelist.input').write_text(nml);exe=B/'udm37-sterling-thermodynamic-build-v1/wrf';env={k:v for k,v in os.environ.items() if not k.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_RESEARCH_','WRF_RADIATION_ENERGY'))};env.update(LD_LIBRARY_PATH=str(B/'deps/netcdf/lib'),OMP_NUM_THREADS='1')
 run=h.Runner(O,2400,env,1);receipt={'status':'STARTING','checkpoint':h.pin(cp),'initial':h.pin(D/'wrfinput_d01'),'forcing':h.pin(D/'wrfbdy_d01'),'namelist':h.pin(D/'namelist.input'),'iofields':h.pin(D/'radiation_iofields.txt'),'executable':h.pin(exe),'time_IO_changes':changes,'commands':[],'production_changes':False,'private_readonly_build':h.pin(exe.parent/'receipt.json'),'new_bounded_WRF_processes':1,'cold24h_repeated':False};h.write_json(O/'receipt.json',receipt);error=None
 try:run.run(['bash','-c','ulimit -s unlimited; exec "$@"','thermodynamic',exe],D,'bounded_actual_temperature_vapor_tendencies')
 except Exception as e:error=str(e)
 text=(O/'command-01.stdout').read_text(errors='replace');receipt.update(status='SUCCESS' if not error and 'SUCCESS COMPLETE WRF' in text else 'STOPPED',error=error,commands=run.commands);h.write_json(O/'receipt.json',receipt);print(receipt['status'],error)
if __name__=='__main__':main()
