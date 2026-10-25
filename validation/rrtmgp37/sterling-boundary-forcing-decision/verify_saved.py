"""Portable, standard-library evidence replay. No model, WPS, download or NetCDF execution."""
from pathlib import Path
import json,hashlib,tarfile,io,gzip,importlib.util,re
P=Path(__file__).resolve().parent;R=P.parents[2]
def imp(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
A=imp('boundary_analysis',P/'analyze.py');I=imp('boundary_instrumentation',P/'instrument.py');require=A.require;sha=lambda b:hashlib.sha256(b).hexdigest()
def compare_check(c):
 require(c['pairs']==1350 and not c['differences'],'observation changed native state')
 require(set(c['inventory'])=={'2016-10-06_%02d:00:00'%h for h in range(12,18)} and all(len(v)==225 for v in c['inventory'].values()),'actual comparison support')
 require(all(x['equal'] and x['left_sha256']==x['right_sha256'] for r in c['inventory'].values() for x in r.values()),'actual native array mismatch')
def provenance_check(p):
 require(p['status']=='EFFECTIVE_FORCING_CONDENSATE_NOT_PROVIDED_DEFAULT_ZERO' and not p['boundary_zeros_are_valid_external_clear_sky'] and p['effective_preprocessing_absence_does_not_prove_raw_FNL_absence'],'unsupported forcing-truth promotion')
 require(len(p['actual_original_met_em'])==len(p['global_intermediate'])==9 and all(not m['condensate'] and not m['provided_flags'] for m in p['actual_original_met_em']),'actual missing forcing fields/flags')
 require(p['all_variable_arrays_preserved_both_producers'] and p['retained_REAL_condensate_interpolation_section_equals_current'],'zero producer/REAL definition changed')
 for m in p['original_chain']['original_REAL'].values():require(m['condensate'] and all(v['nonzero']==v['nonfinite']==0 for v in m['condensate'].values()),'original REAL condensate was not zero')
 require(len(p['classification'])==6 and all('not provided' in v for v in p['classification'].values()),'missing condensate classification')
def interior_check(p):
 s=p['site'];require(p['status']=='INTERIOR_INPUT_PREPARED_AND_ONE_STEP_SUPPORTED' and s['model_i_j_1based']==[37,119] and s['cells_to_nearest_physical_edge']==s['north_edge_cells']==24 and s['outside_relaxation_zone'] and s['station_lat_lon_height']==[38.97203,-77.4869,85.],'interior geometry/station changed')
 require(p['contracts']=={'UDM_NUMBER_POLICY':1,'UDM_POPULATION_POLICY':0,'UDM_SPECIFIED_NUMBER_CONTRACT':1},'number/CCN support contract changed')
 require(p['actual_times']==['2016-10-06_00:00:00','2016-10-06_00:01:00'] and not p['new_forecast_evaluation'] and not p['optical_code_improvement_claimed'] and p['unprovided_condensate_remains_limitation'],'one-step support promoted to forecast skill')
 require(all(v['finite'] and v['min']>=0 for v in p['water_number_checks'].values()),'one-step invalid water/number')
def unpack(file,index):
 raw=file.read_bytes();require(sha(raw)==index['archive']['sha256'] and len(raw)==index['archive']['bytes'],'archive hash')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  require(len(t.getmembers())==len(index['files']) and set(t.getnames())==set(index['files']) and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in t.getmembers()),'archive roster/type')
  d={n:t.extractfile(n).read() for n in index['files']}
 for n,p in index['files'].items():require(sha(d[n])==p['sha256'] and len(d[n])==p['bytes'],'payload '+n)
 return d

def data():
 ident=json.loads((P/'identity.json').read_text());d=unpack(P/'saved/evidence.tar.gz',ident['evidence']);inputs=unpack(P/'saved/interior-input.tar.gz',ident['interior_input'])
 for group in ['current_sources','dependencies']:
  for n,p in ident[group].items():require(sha((R/n).read_bytes())==p['sha256'],'current source/evidence '+n)
 for n,p in ident['outputs'].items():require(sha((P/n).read_bytes())==p['sha256'],'output '+n)
 require(d['plan.json']==(P/'plan.json').read_bytes(),'plan mismatch');j=lambda n:json.loads(d[n])
 run=j('run/receipt.json');build=j('build/receipt.json');pub=j('baseline-public-receipt.json');day=j('baseline-day-receipt.json')
 require(run['status']=='SUCCESS' and not run['error'] and run['executable']['sha256']==build['executable']['sha256'],'bounded run identity/status')
 require(build['base_library']['sha256']==pub['library']['sha256'] and run['initial']['sha256']==day['initial']['sha256'] and run['forcing']['sha256']==day['forcing']['sha256'],'baseline source/input/forcing changed')
 vi=json.loads((P.parent/'vapor-first-operation/identity.json').read_text());require(sha(d['baseline-public-receipt.json'])==vi['files']['public/receipt.json']['sha256'] and sha(d['baseline-day-receipt.json'])==vi['files']['day/receipt.json']['sha256'],'current public baseline receipt changed')
 for n,text in I.transform(R).items():require(d['build/'+n]==text.encode(),'unrelated private observation edits')
 require(d['build/sterling_boundary_probe.f90']==(P/'probe.f90').read_bytes(),'compiled helper mismatch')
 for n,p in build['sources'].items():require(sha(d['build/'+n])==p['sha256'],'compiled source pin')
 require(d['old-optional-input.F']==(R/'WRF/share/module_optional_input.F').read_bytes(),'original REAL optional-field semantics differ')
 require(sha(d['baseline-day.namelist'])==day['namelist']['sha256'],'original namelist identity')
 expected=d['baseline-day.namelist'].decode()
 forecast,n=re.subn(r'(?m)^(\s*e_sn\s*=\s*)[^,\n]+',r'\g<1>144',expected);require(n==1 and inputs['namelist.input'].decode()==forecast,'new forecast changed non-geometry configuration')
 changes=dict(run_seconds='18120',start_hour='11',start_minute='58',end_day='06',end_hour='17',end_minute='0',end_second='0',history_begin_s='120',history_interval_s='3600',restart_interval_s='1000000',restart='.true.',override_restart_timers='.true.')
 for name,value in changes.items():
  if not re.search(r'(?im)^\s*'+name+r'\s*=',expected):expected=expected.replace('&time_control','&time_control\n '+name+' = '+value+',',1)
  expected,n=re.subn(r'(?im)^(\s*'+name+r'\s*=\s*)[^,\n]+',lambda m:m[1]+value,expected);require(n==1,'runtime key')
 require(d['run/host/namelist.input'].decode()==expected,'bounded observation changed physics/forcing configuration')
 p=j('provenance.json')['original_chain']['specified_contract']
 require(p['wrfinput_d01']['sha256']==run['initial']['sha256'] and p['wrfbdy_d01']['sha256']==run['forcing']['sha256'],'provenance not actual original forcing')

 for label in ['run','build','wps','real','preflight']:
  receipt=j(label+'/receipt.json')
  if label in ['wps','real']:require(receipt['status']=='SUCCESS','failed input producer')
  for c in receipt['commands']:require(c['actual_returncode']==0 and not c['timed_out'],'qualified command failed')
 compare_check(j('history-comparison.json'));require(j('history-comparison.json')['files'][0]['sha256']=='3da760fb50fa18b5ead1248ca684f72e22625524896d37a1bc2aa432c01fd72c','wrong original cold history')
 provenance_check(j('provenance.json'));interior_check(j('preflight/receipt.json'))
 original=json.loads((P.parent/'real-output-independent-comparison/result.json').read_text());result=json.loads((P/'result.json').read_text());require(result['original_24h_statistics']==original['statistics'] and result['original_observed_site']==original['site'] and not result['original_scores_changed'],'original station/score changed')
 for n in ['wrfinput_d01','wrfbdy_d01']:
  require(sha(inputs[n])==j('real/receipt.json')['encoded_outputs'][n]['sha256'],'prepared input files changed')
  require(sha(inputs[n])!=j('provenance.json')['original_chain']['specified_contract'][n]['sha256'],'old cropped input substituted')
 require(inputs['namelist.input']==d['real/forecast.namelist.input'] and inputs['input-use-decision.json']==(P/'input-use-decision.json').read_bytes(),'ready input config/contract changed')
 require(j('preflight/receipt.json')['executable']['sha256']==pub['executable']['sha256'],'preflight used different public executable')
 require(not ident['production_changes'] and not ident['physical_accuracy_approved'] and not ident['original_seven_conditions_changed'],'scope promotion')
 return d,inputs,result

def verify():
 d,inputs,result=data();actual=A.evaluate(d['native/sterling-boundary.txt'])
 require(all(result[k]==v for k,v in actual.items()),'native replay result mismatch')
 require(actual['original_site_condensate_direct_removal_count']==0,'direct removal decision contradicted')
 require(result['forcing_classification']==json.loads(d['provenance.json'])['classification'] and result['hourly_native_saturation_summary']==json.loads(d['thermodynamics.json'])['summary'],'provenance/thermodynamic decision changed')
 require(result['interior_site']==json.loads(d['preflight/receipt.json'])['site'],'input decision not actual geometry')
 require(all(v is False for v in result['scientific_approval'].values()) and not result['original_seven_conditions_changed'],'scientific scope promotion')
 return result
if __name__=='__main__':
 r=verify();print(json.dumps({k:r[k] for k in ['status','actual_core_records','actual_full_source_PD_updates_replayed','actual_observer_native_array_pairs_equal','original_site_condensate_direct_removal_count','interior_input_status','production_changes']}));print('new_model_runs=0')
