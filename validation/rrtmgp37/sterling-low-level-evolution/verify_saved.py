"""Standard-library replay; no network, model, native scalar or large source read."""
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from common import *
from analyze import analyze
import json,io,gzip,tarfile,copy,csv
sha=lambda x:hashlib.sha256(x).hexdigest()
def load():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'] and len(raw)==ident['archive']['bytes'],'archive identity')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  require(set(t.getnames())==set(ident['files']) and len(t.getmembers())==len(ident['files']) and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in t),'archive roster/type')
  data={n:t.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(data[n])==p['sha256'] and len(data[n])==p['bytes'],'payload '+n)
 for group in ['current_sources','unchanged_production_sources','dependencies']:
  for n,p in ident[group].items():require(sha((R/n).read_bytes())==p['sha256'],'source/dependency '+n)
 for n,p in ident['outputs'].items():require(sha((P/n).read_bytes())==p['sha256'],'output '+n)
 require(data['plan.json']==(P/'plan.json').read_bytes(),'plan drift')
 require(not any(ident[k] for k in ['production_calculation_changes','coefficient_or_policy_changes','original_seven_conditions_changed','physical_accuracy_approved','new_model_runs_in_saved_replay','new_WRF_WPS_REAL_RTE_Mie_processes','new_compile_processes']),'scope promotion')
 return data
def replay(data):
 j=lambda n:json.loads(data[n]);ex=j('read/extracted.json');out=copy.deepcopy(ex)
 prior=json.loads((P.parent/'sterling-interior-day-evaluation/result.json').read_text())
 with tarfile.open(P.parent/'sterling-interior-day-evaluation/saved/evidence.tar.gz','r:gz') as t:oldhistory=json.loads(t.extractfile('extract/extracted.json').read())['model']['history']
 require(ex['native_read'] and ex['pid']>0 and ex['history']['sha256']==oldhistory['sha256'],'not qualified actual cold read')
 real=j('provenance/existing-REAL-receipt.json');wps=j('provenance/existing-WPS-receipt.json')
 for k,n in [('input','wrfinput_d01'),('boundary','wrfbdy_d01')]:require(ex[k]['sha256']==real['encoded_outputs'][n]['sha256'],'actual encoded input linkage')
 require(ex['forecast_namelist']['sha256']==sha(data['provenance/forecast.namelist.input'])==real['forecast_namelist']['sha256'],'forecast namelist linkage')
 nam=data['provenance/REAL-namelist.output'].decode();require('RH2QV_METHOD=1' in nam and 'RH2QV_WRT_LIQUID=T' in nam and 'USE_THETA_M=1' in nam,'actual REAL humidity/theta branch')
 for m in ex['model']:
  old=prior['hourly_state'][m['hour_UTC']]['profiles']
  for k,l in enumerate(m['profiles']):
   require(l['p_Pa']==f32(old['P'][k]+old['PB'][k]) and l['dry_theta_K']==old['T'][k]+300 and l['qv_kg_kg']==old['QVAPOR'][k],'sealed model state changed')
   require(f32(l['T_K'])==f32(l['dry_theta_K']*(l['p_Pa']/100000)**(287/1004.5)),'theta interpreted as temperature')
   for n in ['QCLOUD','QRAIN','QICE','QSNOW','QGRAUP','QHAIL']:require(l[n]==old[n][k],'sealed species changed')
 audit=j('read/support-audit.json');require(audit['native_metadata_read'] and audit['pid']>0 and audit['initial_times']==['2016-10-06_00:00:00'],'actual metadata read')
 for f in ex['forcing']:
  actual=next(r for r in audit['forcing'] if r['hour_UTC']==f['hour_UTC']);require(actual['met_em_times']==[f['time_UTC']] and actual['intermediate_hdate']==f['time_UTC'] and actual['intermediate_forecast_hour']==0,'native source time support')
  require(actual['met_em_humidity_variable_presence']=={'RH':True,'QVAPOR':False,'QV':False,'SPECHUMD':False},'source humidity availability')
  require(len(actual['selected_GRIB_analysis_messages'])==len(f['GRIB']['rows']),'actual GRIB time roster')
  for r in actual['selected_GRIB_analysis_messages']:
   old=next(x for x in f['GRIB']['rows'] if x['source_message_sha256']==r['message_sha256']);require(r['dataDate']==r['validityDate']==old['date']==int(f['time_UTC'][:10].replace('-','')) and r['dataTime']==r['validityTime']==old['time']==int(f['time_UTC'][11:13])*100 and str(r['stepRange'])=='0','source analysis/valid time mismatch')
  name='met_em.d01.'+f['time_UTC']+'.nc';require(f['met_em']['pin']['sha256']==wps['outputs'][name]['sha256'],'actual met_em linkage')
  for g in f['GRIB']['rows']:
   require(g['bilinear_value']==bilinear(g['corners'],*ex['fixed_lat_lon']),'GRIB spatial sampling')
   require(g['p_Pa']%100==0 and g['grid']['Ni']==360 and g['grid']['Nj']==181 and g['source_message_bytes']>0,'GRIB field metadata')
  for im in f['intermediate']:require(im['bilinear_value']==bilinear(im['corners'],*ex['fixed_lat_lon']),'intermediate spatial sampling')
  for row in f['met_em']['profiles']:require(row['qv_kg_kg_REAL_method1_diagnostic']==real_qv(row['T_K'],row['p_Pa'],row['source_RH_percent']),'source RH conversion')
 bc=ex['boundary_data'];require(bc['use_theta_m']==1,'boundary theta branch')
 for v in bc['coupling_validation_at_initial_time']:
  target=next(r for r in bc['targets'] if r['side']==v['side'] and r['hour_UTC']==0);raw=target['raw_coupled'];require(raw['MU']==target['interpolated_coupled_target']['MU'],'initial MU')
  for k,row in enumerate(v['decoded']):
   a=f32(f32(f32(bc['C1H'][k])*f32(raw['MU']))+f32(f32(f32(bc['C1H'][k])*f32(target['MUB_Pa']))+f32(bc['C2H'][k])))
   require(f32(f32(v['input_qv'][k])*a)==raw['QVAPOR'][k] and f32(f32(v['input_THM_pert_K'][k])*a)==raw['T'][k],'native initial boundary coupling')
  require(v['q_coupled_exact_REAL32'] and v['THM_pert_coupled_exact_REAL32'],'coupling qualification')
 for target in bc['targets']:
  ix=target['record_start_hour']//6;require(audit['boundary_record_times'][ix]==('2016-10-06_'+f'{target["record_start_hour"]:02d}'+':00:00' if ix<4 else '2016-10-07_00:00:00'),'boundary actual record time')
  raw=target['raw_coupled'];bt=target['coupled_tendencies_per_second'];dtbc=target['dtbc_s'];require(dtbc==(target['hour_UTC']-target['record_start_hour'])*3600,'dtbc not record-relative seconds')
  actual={n:([f32(x+f32(dtbc*y)) for x,y in zip(raw[n],bt[n])] if n!='MU' else f32(raw[n]+f32(dtbc*bt[n]))) for n in raw}
  require(actual==target['interpolated_coupled_target'],'native coupled time interpolation')
  require(decode_boundary(actual,target['MUB_Pa'],bc['C1H'],bc['C2H'])==target['decoded'],'moist/dry boundary decoding')
 inputs=j('native/input.json');vals=[list(map(float,l.split())) for l in data['native/stdout.txt'].decode().splitlines()];require(len(inputs)==len(vals),'scalar row count')
 receipt=j('native/receipt.json');dev=j('execution/development-native-receipt.json');oldhelper=j('provenance/prior-native-helper-receipt.json')
 require(receipt['returncode']==dev['returncode']==0 and receipt['pid']>0 and dev['pid']>0 and receipt['pid']!=dev['pid'],'actual two scalar processes')
 require(receipt['executed_existing_binary']['sha256']==oldhelper['executable']['sha256'] and receipt['helper_source']['sha256']==oldhelper['source']['sha256']==sha(data['native/native_saturation.f90']),'unchanged prior scalar executable/helper')
 require(sha(data['native/input.txt'])==receipt['input']['sha256'] and sha(data['provenance/REAL-namelist.output'])==ex['real_namelist_output']['sha256'],'native/REAL input identity')
 groups={'model':out['model'],'transect':out['transect'],'initial':[out['initial']]};expected=[]
 for group,rows in groups.items():
  for arm,row in enumerate(rows):
   for l in row['profiles']:
    if 0<=l['z_agl_m']<=3000:expected.append({'group':group,'arm':arm,'record':l['record'],'T_K':l['T_K'],'p_Pa':l['p_Pa'],'qv_kg_kg':l['qv_kg_kg']})
 for arm,row in enumerate(out['forcing']):
  for l in row['met_em']['profiles']:expected.append({'group':'met_em','arm':arm,'record':l['record'],'T_K':l['T_K'],'p_Pa':l['p_Pa'],'qv_kg_kg':l['qv_kg_kg_REAL_method1_diagnostic']})
 require(inputs==expected,'scalar actual input selection')
 for x,v in zip(inputs,vals):
  e,qs,rh=v;eps=f32(287./f32(461.6));require(qs==f32(f32(eps*e)/f32(f32(x['p_Pa'])-e)) and rh==f32(f32(x['qv_kg_kg'])/qs),'native REAL32 qsat/RH arithmetic')
  if x['group'] in groups:row=groups[x['group']][x['arm']]['profiles'][x['record']-1]
  else:row=next(r for r in out['forcing'][x['arm']]['met_em']['profiles'] if r['record']==x['record'])
  row.update(es_water_Pa=e,qs_water_kg_kg=qs,RH_water_ratio=rh)
 out['native_helper']=receipt;require(out==j('read/enriched.json'),'enrichment replay');return out
def verify():
 data=load();out=replay(data)
 with tarfile.open(P.parent/'sterling-independent-atmosphere/saved/evidence.tar.gz','r:gz') as t:obs=json.loads(t.extractfile('derived/enriched.json').read())
 old=json.loads((P.parent/'sterling-independent-atmosphere/result.json').read_text());result=analyze(out,obs,old);require(result==json.loads((P/'result.json').read_text()),'state-chain ruling replay')
 with (P/'hourly-pressure.csv').open() as f:rows=list(csv.DictReader(f))
 expect=[dict(hour_UTC=r['hour_UTC'],**p) for r in result['hourly_profiles'] for p in r['pressure_rows']];require(len(rows)==len(expect),'hourly CSV count')
 for a,b in zip(rows,expect):
  for n,v in b.items():require(a[n]==('' if v is None else str(v)),'hourly CSV value '+n)
 return result
if __name__=='__main__':
 r=verify();print(json.dumps({k:r[k] for k in ['status','development_ruling','decision','physical_accuracy_approved','new_model_runs_in_saved_replay']}))
