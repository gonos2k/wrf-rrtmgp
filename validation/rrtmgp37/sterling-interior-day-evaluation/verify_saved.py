"""Standard-library replay of the new campaign, preserving the original scoring contract."""
from pathlib import Path
import json,hashlib,tarfile,io,gzip,importlib.util
P=Path(__file__).resolve().parent;R=P.parents[2]
s=importlib.util.spec_from_file_location('interior_analysis',P/'analyze.py');A=importlib.util.module_from_spec(s);s.loader.exec_module(A);require=A.require
sha=lambda b:hashlib.sha256(b).hexdigest()
def data():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'] and len(raw)==ident['archive']['bytes'],'archive identity')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  require(len(t.getmembers())==len(ident['files']) and set(t.getnames())==set(ident['files']) and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in t.getmembers()),'archive roster/type');d={n:t.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(d[n])==p['sha256'] and len(d[n])==p['bytes'],'payload '+n)
 for group in ['dependencies','current_sources','coefficient_repo_files']:
  for n,p in ident[group].items():require(sha((R/n).read_bytes())==p['sha256'],'source/dependency '+n)
 for n,p in ident['outputs'].items():require(sha((P/n).read_bytes())==p['sha256'],'output '+n)
 require(d['plan.json']==(P/'plan.json').read_bytes(),'plan changed');j=lambda n:json.loads(d[n]);run=j('run/receipt.json');pub=j('public-baseline-receipt.json');prior=json.loads((P.parent/'sterling-boundary-forcing-decision/identity.json').read_text())
 require(run['status']=='SUCCESS' and not run['error'] and len(run['commands'])==1,'actual campaign failure/count')
 c=run['commands'][0];require(c['actual_returncode']==0 and c['status']=='TERMINAL' and not c['timed_out'] and c['pid']>0,'actual process not terminal success')
 require(sha(d['public-baseline-receipt.json'])==prior['evidence']['files']['baseline-public-receipt.json']['sha256'],'tested public baseline receipt changed')
 require(run['executable']['sha256']==pub['executable']['sha256'],'public executable changed')
 require(run['initial']['sha256']==prior['interior_input']['files']['wrfinput_d01']['sha256'] and run['forcing']['sha256']==prior['interior_input']['files']['wrfbdy_d01']['sha256'],'prepared input/forcing changed')
 require(sha(d['prepared-forecast.namelist'])==prior['interior_input']['files']['namelist.input']['sha256'],'wrong forecast/preflight namelist')
 expected=d['prepared-forecast.namelist'].decode().replace('&time_control','&time_control\n'+''.join(' '+n+' = '+v+',\n' for n,v in run['IO_only_additions'].items()),1)
 require(d['run/host/namelist.input'].decode()==expected and sha(d['run/host/namelist.input'])==run['namelist']['sha256'],'non-IO forecast alteration')
 require(sha(d['run/host/radiation_iofields.txt'])==run['iofields']['sha256'],'IO field source mismatch')
 diagnostic=j('diagnostic/receipt.json');require(diagnostic['status']=='SUCCESS' and not diagnostic['error'] and len(diagnostic['commands'])==1,'diagnostic recovery process')
 dc=diagnostic['commands'][0];require(dc['actual_returncode']==0 and not dc['timed_out'],'diagnostic recovery failed')
 require(diagnostic['executable']['sha256']==run['executable']['sha256'] and diagnostic['initial']['sha256']==run['initial']['sha256'] and diagnostic['forcing']['sha256']==run['forcing']['sha256'],'diagnostic trajectory inputs changed')
 require(diagnostic['checkpoint']['path'].endswith('udm37-sterling-interior-day-v1/host/wrfrst_d01_2016-10-06_11:58:00'),'wrong diagnostic checkpoint')
 fixed='\n'.join(x for x in d['run/host/radiation_iofields.txt'].decode().splitlines() if x.strip())+'\n'
 require(d['diagnostic/host/radiation_iofields.txt'].decode()==fixed and all(x.strip() for x in fixed.splitlines()),'diagnostic IO changed beyond blank removal')
 c=j('diagnostic/history-comparison.json');require(c['pairs']==1350 and not c['differences'] and sorted(c['inventory'])==['2016-10-06_%02d:00:00'%h for h in range(12,18)] and all(len(v)==225 for v in c['inventory'].values()),'diagnostic not same cold arrays/support')
 require(all(v['equal'] and v['left_sha256']==v['right_sha256'] for row in c['inventory'].values() for v in row.values()),'diagnostic native array changed')
 expected_diag=d['run/host/namelist.input'].decode()
 import re
 for name,value in diagnostic['time_IO_changes'].items():
  if not re.search(r'(?im)^\s*'+name+r'\s*=',expected_diag):expected_diag=expected_diag.replace('&time_control','&time_control\n '+name+' = '+value+',',1)
  expected_diag,n=re.subn(r'(?im)^(\s*'+name+r'\s*=\s*)[^,\n]+',lambda m:m[1]+value,expected_diag);require(n==1,'diagnostic time key')
 require(d['diagnostic/host/namelist.input'].decode()==expected_diag,'diagnostic changed non-time/IO configuration')
 executed=d['development/executed-run.py'].decode();future=executed.replace("io=(prior/'radiation_iofields.txt').read_text();io+=", "io=(prior/'radiation_iofields.txt').read_text().rstrip();io+=").replace("(D/'radiation_iofields.txt').write_text(io)", "assert all(x.strip() for x in io.splitlines());(D/'radiation_iofields.txt').write_text(io)")
 require(future==(P/'run.py').read_text(),'future runner changed beyond IO blank fix')

 for n,p in run['coefficient_files'].items():require(p['sha256']==ident['coefficient_repo_files']['WRF/run/'+n]['sha256'],'gas/cloud coefficient changed')
 require(run['frozen_table']['sha256']==ident['coefficient_repo_files']['validation/rrtmgp37/frozen-planck-coverage/expanded/frozen-ice-psd-moments.nc']['sha256'],'frozen coefficient changed')
 ex=j('extract/extracted.json');require(ex['run_summary']['executable']==run['executable'] and ex['run_summary']['input']==run['initial'] and ex['run_summary']['forcing']==run['forcing'] and ex['run_summary']['namelist']==run['namelist'],'extraction not actual process')
 require(ex['model']['history']==ex['history']['history']==j('extract/receipt.json')['history'],'native output readback identity')
 require(ex['run_summary']['diagnostic_receipt']==diagnostic and ex['run_summary']['diagnostic_overlap_comparison']==c and c['files'][0]['sha256']==ex['model']['history']['sha256'],'diagnostic not linked to actual cold history')
 require(ex['run_summary']['runtime_assets_unchanged_after'],'assets changed during run')
 expected={n:run[n] for n in ['initial','forcing','executable','frozen_table','namelist','iofields','prepared_forecast_namelist']};expected.update({'coefficient/'+n:p for n,p in run['coefficient_files'].items()})
 require(set(expected)==set(ex['run_summary']['postflight_assets']) and all(ex['run_summary']['postflight_assets'][n]['sha256']==p['sha256'] for n,p in expected.items()),'postflight assets mismatch')
 require(j('extract/receipt.json')['native_read'] and j('extract/receipt.json')['records']==25,'native output not read')
 old=json.loads((P.parent/'real-output-independent-comparison/result.json').read_text());previous=json.loads((P.parent/'sterling-cloud-radiation-attribution/result.json').read_text());ctx=j('extract/old-context.json')
 require(ctx=={'statistics':old['statistics'],'original_16_17UTC_direct_W_m2':previous['original_site']['physical_horizontal_direct_held_W_m2'],'observed_16_17UTC_horizontal_direct_W_m2':previous['observed_hour_components']['horizontal_direct_W_m2'],'observed_16_17UTC_components':previous['observed_hour_components']},'original comparison redefined')
 require(not ident['production_changes'] and not ident['physical_accuracy_approved'] and not ident['original_seven_conditions_changed'],'scope promotion')
 blobs=[(P.parent/f'solrad-boundary-site-48h/raw/ste16{n}.dat').read_bytes() for n in [280,281]]
 return ex,blobs,j('plan.json'),ctx,j('input-contrast.json')

def verify():
 ex,obs,plan,old,contrast=data();r=A.evaluate(ex,obs,plan,old);r['input_contrast']=contrast
 require(r==json.loads((P/'result.json').read_text()),'actual campaign replay mismatch')
 require(contrast['original_station_cell_coordinates_bitwise_equal'] and contrast['nominal_overlap_nearest_rows_and_columns_confirmed'] and not contrast['isolated_domain_effect_measured'],'initial input contrast scope')
 return r
if __name__=='__main__':
 r=verify();print(json.dumps({k:r[k] for k in ['status','hourly_water_number_valid','new_all_hour_RMSE_lower','physical_accuracy_approved','production_changes','new_model_runs_in_saved_replay']}));print(json.dumps(r['statistics']['primary']))
