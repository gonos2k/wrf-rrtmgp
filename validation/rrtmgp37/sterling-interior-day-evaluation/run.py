"""Run prepared PR201 cold24h once, unchanged executable/physics; bounded native IO only."""
from pathlib import Path
import importlib.util,json,os,shutil,re
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-interior-day-v1';O.mkdir(exist_ok=False);D=O/'host';D.mkdir()
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
I=B/'udm37-sterling-interior-real-v1';prior=B/'udm37-vapor-corrected-day-v2/host';inputs=json.loads((I/'receipt.json').read_text());prepared=json.loads((P.parent/'sterling-boundary-forcing-decision/input-use-decision.json').read_text())
for n in ['wrfinput_d01','wrfbdy_d01']:
 p=I/'encoded'/n;assert h.pin(p)['sha256']==prepared['inputs'][n]['sha256'];(D/n).symlink_to(p)
for p in prior.iterdir():
 if p.is_symlink() and not p.name.startswith(('wrfinput','wrfbdy','wrfrst')):(D/p.name).symlink_to(p.resolve())
original=(I/'forecast.namelist.input').read_text();assert h.pin(I/'forecast.namelist.input')['sha256']==inputs['forecast_namelist']['sha256']
extras=dict(auxhist7_outname="'sterling_surface_<domain>_<date>'",auxhist7_interval_s='60',auxhist7_begin_s='57600',auxhist7_end_s='61200',frames_per_auxhist7='1000',io_form_auxhist7='2',auxhist8_outname="'sterling_state_<domain>_<date>'",auxhist8_interval_s='600',auxhist8_begin_s='57600',auxhist8_end_s='61200',frames_per_auxhist8='1000',io_form_auxhist8='2')
assert all(not re.search(r'(?im)^\s*'+n+r'\s*=',original) for n in extras)
nml=original.replace('&time_control','&time_control\n'+''.join(' '+n+' = '+v+',\n' for n,v in extras.items()),1);(D/'namelist.input').write_text(nml)
io=(prior/'radiation_iofields.txt').read_text().rstrip();io+='\n+:h:7:SWDNB,SWDNBC,SWDDIR,SWDDIRC,SWDDIF,SWDDNI,COSZEN,ACSWDNB,ACSWDNBC\n+:h:8:CLDFRA,UDM_CLDFRA,QCLOUD,QICE,QRAIN,QSNOW,QGRAUP,QHAIL,QC_CU,QI_CU,PH,PHB,ALT\n';assert all(x.strip() for x in io.splitlines());(D/'radiation_iofields.txt').write_text(io)
exe=B/'udm37-vapor-corrected-public-v2/wrf';pub=json.loads((B/'udm37-vapor-corrected-public-v2/receipt.json').read_text());assert h.pin(exe)['sha256']==pub['executable']['sha256']
env={k:v for k,v in os.environ.items() if not k.startswith(('WRF_RRTMGP_','WRF_UDM_','WRF_RESEARCH_','WRF_RADIATION_ENERGY'))};env.update(LD_LIBRARY_PATH=str(B/'deps/netcdf/lib'),OMP_NUM_THREADS='1')
runner=h.Runner(O,7200,env,1);receipt={'status':'STARTING','initial':h.pin(D/'wrfinput_d01'),'forcing':h.pin(D/'wrfbdy_d01'),'prepared_forecast_namelist':h.pin(I/'forecast.namelist.input'),'namelist':h.pin(D/'namelist.input'),'iofields':h.pin(D/'radiation_iofields.txt'),'executable':h.pin(exe),'frozen_table':h.pin(Path(re.search(r"rrtmgp_udm_frozen_table\s*=\s*'([^']+)'",nml)[1])),'coefficient_files':{p.name:h.pin(p.resolve()) for p in D.glob('rrtmgp-*.nc')},'IO_only_additions':extras,'commands':[],'production_changes':False,'new_24h_WRF_processes':1};h.write_json(O/'receipt.json',receipt);error=None
try:runner.run(['bash','-c','ulimit -s unlimited; exec "$@"','interior-day',exe],D,'prepared_interior_fixed_physics_cold24h')
except Exception as e:error=str(e)
log=(O/'command-01.stdout').read_text(errors='replace');receipt.update(status='SUCCESS' if not error and 'SUCCESS COMPLETE WRF' in log else 'STOPPED',error=error,commands=runner.commands);h.write_json(O/'receipt.json',receipt);print(receipt['status'],error)
