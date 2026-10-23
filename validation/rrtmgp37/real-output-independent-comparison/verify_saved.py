"""Portable actual independent comparison; no NumPy, NetCDF or model process."""
from pathlib import Path
import json,hashlib,io,tarfile,gzip,importlib.util,re,csv
P=Path(__file__).resolve().parent;R=P.parents[2]
def load(p):
 s=importlib.util.spec_from_file_location('external_comparison',p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=load(P/'analyze.py');require=A.require
sha=lambda b:hashlib.sha256(b).hexdigest()
def data():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'] and len(raw)==ident['archive']['bytes'],'archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as tar:
  require(set(tar.getnames())==set(ident['files']),'archive roster');d={n:tar.extractfile(n).read() for n in ident['files']}
 for n,info in ident['files'].items():require(sha(d[n])==info['sha256'] and len(d[n])==info['bytes'],'payload '+n)
 for n,info in ident['outputs'].items():require(sha((P/n).read_bytes())==info['sha256'],'output artifact '+n)
 for family in ['existing_observation_evidence','dependencies','current_sources']:
  for n,info in ident[family].items():require(sha((R/n).read_bytes())==info['sha256'] and (R/n).stat().st_size==info['bytes'],'source/evidence '+n)
 require(sha((P/'plan.json').read_bytes())==ident['plan']['sha256'],'predeclared plan changed')
 old=P.parent/'solrad-boundary-site-48h';old_manifest=json.loads((old/'manifest.json').read_text());download=json.loads((old/'download-manifest.json').read_text())
 for n in ['raw/ste16280.dat','raw/ste16281.dat']:
  b=(old/n).read_bytes();require(sha(b)==old_manifest['files'][n]['sha256'],'original observation changed')
  entry=next(x for x in download['items'] if x['path']==n);require(entry['status']==200 and entry['sha256']==sha(b) and entry['requested_url'].startswith('https://gml.noaa.gov/'),'observation provenance')
 selection=json.loads((old/'station-selection.json').read_text());require([x['site'] for x in selection['sites'] if x['scored']]==['ste'],'station selection not original all-eligible inventory')
 previous=P.parent/'vapor-first-operation';v=json.loads((previous/'identity.json').read_text());require(sha(d['baseline-day-receipt.json'])==v['files']['day/receipt.json']['sha256'],'wrong corrected day')
 with tarfile.open(previous/'saved/evidence.tar.gz') as tar:
  hb=tar.extractfile('history.json').read();require(sha(hb)==v['files']['history.json']['sha256'],'original history inventory changed');history=json.loads(hb)['history']
 model=json.loads(d['model-extract.json']);receipt=json.loads(d['extraction-receipt.json']);day=json.loads(d['baseline-day-receipt.json'])
 require(model['history']==history and receipt['history_sha256']==history['sha256'],'extraction of another trajectory')
 require(receipt['source_sha256']==sha((P/'extract.py').read_bytes()) and receipt['status']=='SUCCESS' and receipt['native_history_read'] and receipt['records']==25 and receipt['new_WRF_Mie_RTE_processes']==0,'actual extraction receipt')
 require(day['status']=='SUCCESS' and not day['error'] and all(x['actual_returncode']==0 and not x['timed_out'] for x in day['commands']),'original corrected run failed')
 require(model['executable']==day['executable'] and model['namelist_sha256']==sha(d['namelist.input'])==day['namelist']['sha256'],'model input identity')
 nml=d['namelist.input'].decode()
 for name,value in [('numtiles',1),('udm_number_policy',1),('udm_population_policy',0),('rrtmgp_capacity_policy',0),('rrtmgp_liquid_size_policy',0),('rrtmgp_udm_frozen_optics',1),('scalar_adv_opt',0),('spec_bdy_width',5)]:
  require(re.search(r'(?im)^\s*'+name+r'\s*=\s*'+str(value)+r'\s*,',nml) is not None,'fixed baseline policy '+name)
 for name in ['vapor-first-operation','native-sw-phase-closeout','frozen-important-state-reference']:
  package=P.parent/name;identity=json.loads((package/'identity.json').read_text())
  for n,info in identity['current_sources'].items():require(sha((R/n).read_bytes())==info['sha256'],'baseline source no longer current '+n)
 vapor=json.loads((previous/'result.json').read_text());sw=json.loads((P.parent/'native-sw-phase-closeout/result.json').read_text());fr=json.loads((P.parent/'frozen-important-state-reference/result.json').read_text())
 require(vapor['vapor_final_nonnegative_criterion_passed'] and vapor['KFETA_expired_rate_criterion_passed'] and vapor['corrected_period_seconds']==86400 and vapor['history_records']==25,'engineering day criteria changed')
 require(vapor['history_comparisons']['corrected_restart']['pairs']==450,'engineering restart criterion changed')
 require(sw['missing_phase_seconds']==sw['partially_observed_seconds']==0 and sw['actual_SW_calls']==144 and sw['current_runtime_source_matches'],'engineering SW closure changed')
 require(fr['reference_LW_bands']==16 and fr['only_selected_hail_absorption_changed'] and not fr['frozen_real_particle_accuracy_approved'],'conditional frozen scope changed')
 require(not ident['production_changes'] and not ident['original_seven_conditions_changed'] and ident['new_model_build_solver_processes']==0,'scope promotion')
 return model,json.loads(d['grid.json']),[(old/f'raw/ste16{n}.dat').read_bytes() for n in [280,281]],json.loads((P/'plan.json').read_text())
if __name__=='__main__':
 r=A.evaluate(*data());require(r==json.loads((P/'result.json').read_text()),'comparison results changed')
 buf=io.StringIO(newline='');writer=csv.DictWriter(buf,fieldnames=list(r['hourly'][0]),lineterminator='\n');writer.writeheader();writer.writerows(r['hourly']);require(buf.getvalue()==(P/'hourly-comparison.csv').read_text(),'CSV does not represent actual support-matched comparison')
 print(json.dumps({'status':r['status'],'complete_hours':r['complete_hours'],'primary_all':r['statistics']['primary']['all'],'primary_daylight':r['statistics']['primary']['daylight'],'engineering_baseline_scope_closed':True,'general_forecast_accuracy_approved':False,'new_model_build_solver_processes':0}))
