from pathlib import Path
import importlib.util,json,os,re,shutil,argparse
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
ap=argparse.ArgumentParser();ap.add_argument('arm',choices=['short_public','short_observed','day','restart']);args=ap.parse_args()
O=B/('udm37-vapor-corrected-'+args.arm+('-v3' if args.arm=='restart' else '-v2'));O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-convective-support-host-v1/host'
for p in prior.iterdir():
 if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 elif p.name in ['wrfinput_d01','wrfbdy_d01']:(D/p.name).symlink_to(p.resolve())
 elif p.name=='radiation_iofields.txt':shutil.copyfile(p,D/p.name)
nml=(prior/'namelist.input').read_text();short=args.arm.startswith('short')
changes={'run_seconds':'120' if short else '86400','end_day':'06' if short else '07','end_hour':'0','end_minute':'2' if short else '0','end_second':'0','history_begin_s':'0','history_interval_s':'60' if short else '3600','restart_interval_s':'21540' if args.arm=='day' else '1000000'}
if args.arm=='restart':
 changes.update(run_seconds='3660',start_hour='5',start_minute='59',end_day='06',end_hour='7',end_minute='0',history_begin_s='60',history_interval_s='3600',restart='.true.',override_restart_timers='.true.')
 cp=B/'udm37-vapor-corrected-day-v2/host/wrfrst_d01_2016-10-06_05:59:00';(D/cp.name).symlink_to(cp)
for n,v in changes.items():
 if n in ['start_minute','restart','override_restart_timers'] and not re.search(r'(?im)^\s*'+n+r'\s*=',nml):
  nml=nml.replace('&time_control','&time_control\n '+n+' = '+v+',',1)
 nml,c=re.subn(r'(?im)^(\s*'+re.escape(n)+r'\s*=\s*)[^,\n]+',lambda m:m[1]+v,nml);assert c==1,(n,c)
(D/'namelist.input').write_text(nml)
kind='public' if args.arm in ['short_public','restart'] else 'observed';exe=B/('udm37-vapor-corrected-'+kind+'-v2/wrf');runner=h.Runner(O,7200,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
receipt={'arm':args.arm,'same_original_forcing':True,'initial':h.pin(D/'wrfinput_d01'),'forcing':h.pin(D/'wrfbdy_d01'),'namelist':h.pin(D/'namelist.input'),'executable':h.pin(exe),'commands':[],'status':'STARTING','physical_approval':False}
if args.arm=='restart':receipt['checkpoint']=h.pin(cp)
h.write_json(O/'receipt.json',receipt);error=None
try:runner.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],D,'corrected_'+args.arm)
except Exception as e:error=str(e)
log=(O/'command-01.stdout').read_text(errors='replace');receipt.update(commands=runner.commands,error=error,status='SUCCESS' if not error and 'SUCCESS COMPLETE WRF' in log else 'STOPPED');h.write_json(O/'receipt.json',receipt);print(receipt['status'],error)
