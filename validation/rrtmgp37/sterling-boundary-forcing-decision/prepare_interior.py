"""Generate a separate interior geometry from actual global WPS intermediates."""
from pathlib import Path
import importlib.util,json,os,shutil
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent
s=importlib.util.spec_from_file_location('runner',R/'WRF/test/rrtmgp/test_netcdf_zz.py');h=importlib.util.module_from_spec(s);s.loader.exec_module(h)
O=B/'udm37-sterling-interior-wps-v3';O.mkdir(exist_ok=False);W=B/'udm37-sterling-wps-source-v1';I=B/'udm37-sterling-interior-inputs-v1'
for name,p in [('GEOGRID.TBL',W/'geogrid/GEOGRID.TBL.ARW'),('METGRID.TBL',W/'metgrid/METGRID.TBL.ARW')]:
 d=O/('geogrid' if name.startswith('GEO') else 'metgrid');d.mkdir(exist_ok=True);(d/name).symlink_to(p)
(O/'GEOG').symlink_to(I/'geog/WPS_GEOG_LOW_RES')
for p in (I/'intermediate').glob('FILE:*'):(O/p.name).symlink_to(p)
nml=f'''&share
 wrf_core='ARW', max_dom=1,
 start_date='2016-10-06_00:00:00', end_date='2016-10-08_00:00:00',
 interval_seconds=21600, io_form_geogrid=2,
/
&geogrid
 parent_id=1, parent_grid_ratio=1, i_parent_start=1, j_parent_start=1,
 e_we=91, e_sn=144, geog_data_res='lowres', dx=27000, dy=27000,
 map_proj='mercator', ref_lat=28., ref_lon=-75.,
 truelat1=30., truelat2=60., stand_lon=-75.,
 geog_data_path='./GEOG/',
/
&ungrib
 out_format='WPS', prefix='FILE',
/
&metgrid
 fg_name='FILE', io_form_metgrid=2,
/
''';(O/'namelist.wps').write_text(nml)
env={**os.environ,'LD_LIBRARY_PATH':str(B/'deps/netcdf/lib'),'OMP_NUM_THREADS':'1'};runner=h.Runner(O,1800,env,2)
receipt={'status':'STARTING','WPS_commit':'335c76a111f84503e8b963abaf273ea8053645bb','geometry_is_new_configuration':True,'forecast_processes':0,'namelist':h.pin(O/'namelist.wps'),'executables':{n:h.pin(W/n/'src'/f'{n}.exe') for n in ['geogrid','metgrid']},'commands':[]};h.write_json(O/'receipt.json',receipt)
try:
 for n in ['geogrid','metgrid']:
  runner.run([str(W/n/'src'/f'{n}.exe')],O,'official_'+n+'_new_interior_input')
  log=(O/f'{n}.log').read_text();assert 'Successful completion' in log,n
 receipt.update(status='SUCCESS',commands=runner.commands,outputs={p.name:h.pin(p) for p in [O/'geo_em.d01.nc',*sorted(O.glob('met_em.d01.*.nc'))]})
except Exception as e:
 receipt.update(status='FAILED',commands=runner.commands,error=str(e));raise
finally:h.write_json(O/'receipt.json',receipt)
print(receipt['status'])
