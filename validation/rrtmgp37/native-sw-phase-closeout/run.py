"""Observe the missing SW returns on the fixed case; never alter numerical policy."""
from pathlib import Path
import importlib.util,json,os,re,shutil,argparse
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
ap=argparse.ArgumentParser();ap.add_argument('arm',choices=['short','day']);args=ap.parse_args()
O=B/('udm37-native-sw-'+args.arm+'-v2');O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('h',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
prior=B/'udm37-vapor-corrected-day-v2/host'
for p in prior.iterdir():
 if p.is_symlink():(D/p.name).symlink_to(p.resolve())
 elif p.name in ['wrfinput_d01','wrfbdy_d01']:(D/p.name).symlink_to(p.resolve())
 elif p.name=='radiation_iofields.txt':shutil.copyfile(p,D/p.name)
nml=(prior/'namelist.input').read_text()
if args.arm=='short':
 for n,v in dict(run_seconds='120',end_day='06',end_hour='0',end_minute='2',history_interval_s='60',restart_interval_s='1000000').items():
  nml,c=re.subn(r'(?im)^(\s*'+re.escape(n)+r'\s*=\s*)[^,\n]+',lambda m:m[1]+v,nml);assert c==1,(n,c)
(D/'namelist.input').write_text(nml)
exe=B/'udm37-native-sw-build-v4/wrf';runner=h.Runner(O,7200,{**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'},1)
receipt={'arm':args.arm,'source_main':'e5aa8fd55c4752c9c2b23e359cb279c0438493a5','same_original_forcing':True,'initial':h.pin(D/'wrfinput_d01'),'forcing':h.pin(D/'wrfbdy_d01'),'namelist':h.pin(D/'namelist.input'),'baseline_namelist':h.pin(prior/'namelist.input'),'executable':h.pin(exe),'commands':[],'status':'STARTING','new_physical_policy':False,'physical_approval':False}
h.write_json(O/'receipt.json',receipt);error=None
try:runner.run(['bash','-c','ulimit -s unlimited; exec "$@"','wrf-serial',exe],D,'actual_SW_return_'+args.arm)
except Exception as e:error=str(e)
log=(O/'command-01.stdout').read_text(errors='replace');receipt.update(commands=runner.commands,error=error,status='SUCCESS' if not error and 'SUCCESS COMPLETE WRF' in log else 'STOPPED');h.write_json(O/'receipt.json',receipt);print(receipt['status'],error)
