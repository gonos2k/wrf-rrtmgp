"""Standard-library replay; no network, compiler, model, or large NetCDF launch/read."""
from pathlib import Path
import json,hashlib,tarfile,gzip,io,copy,math,struct,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from parse import require,sounding,metars
from analyze import evaluate
P=Path(__file__).resolve().parent;R=P.parents[2]
sha=lambda b:hashlib.sha256(b).hexdigest()
f32=lambda x:struct.unpack('<f',struct.pack('<f',x))[0]
def load():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'] and len(raw)==ident['archive']['bytes'],'archive digest')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  require(set(t.getnames())==set(ident['files']) and len(t.getmembers())==len(ident['files']) and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in t.getmembers()),'archive roster/type')
  data={n:t.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(data[n])==p['sha256'] and len(data[n])==p['bytes'],'payload '+n)
 for group in ['current_sources','unchanged_production_sources','current_documents','dependencies']:
  for n,p in ident[group].items():require(sha((R/n).read_bytes())==p['sha256'],'source/dependency '+n)
 require({p.name for p in (P/'raw').iterdir() if p.is_file()}==set(ident['raw_files']),'raw roster')
 for n,p in ident['raw_files'].items():require(sha((P/'raw'/n).read_bytes())==p['sha256'] and (P/'raw'/n).stat().st_size==p['bytes'],'raw '+n)
 for n,p in ident['outputs'].items():require(sha((P/n).read_bytes())==p['sha256'],'output '+n)
 require(data['plan.json']==(P/'plan.json').read_bytes(),'plan changed')
 require(not ident['production_calculation_changes'] and not ident['physics_or_coefficient_changes'] and not ident['physical_accuracy_approved'] and not ident['original_seven_conditions_changed'],'scope promotion')
 j=lambda n:json.loads(data[n]);http=j('fetch/final-retrieval-receipt.json');retrievals={r['name']:r for r in http['retrievals']+http['additional_retrievals']}
 for n in ['asos.csv','igra-stations.txt','igra-format-v2.txt','igra-metadata-readme.txt','asos-api.html','asos-ceilometer.html']:
  r=retrievals[n];require(r['status']=='SUCCESS' and r['http_status']==200 and r['sha256']==sha((P/'raw'/n).read_bytes()),'actual download linkage '+n)
 require(retrievals['igra-format.txt']['status']=='FAILED' and '404' in retrievals['igra-format.txt']['error'],'failed old format URL hidden')
 require(retrievals['igra-metadata.txt']['sha256']==sha(data['fetch/igra-metadata.txt']),'station history download')
 subset=b''.join(l for l in data['fetch/igra-metadata.txt'].splitlines(keepends=True) if l.startswith(b'USM00072403'));require(subset==(P/'raw/igra-station-history-subset.txt').read_bytes(),'station metadata subset altered')
 selection=j('fetch/selected-soundings.json');require(set(selection)=={'2016100600','2016100612','2016100618','2016100700'},'sounding dates changed')
 for n,row in selection.items():
  b=(P/'raw'/('sounding-'+n+'.txt')).read_bytes();require(sha(b)==row['sha256'] and len(b)==row['bytes'] and b.splitlines()[0].decode()==row['header'],'raw sounding selection')
 require(retrievals['USM00072403-data.txt.zip']['status']=='SUCCESS' and retrievals['USM00072403-data.txt.zip']['bytes']==101775974,'primary full IGRA source retrieval missing')
 before=j('before/config/registration37.json');after=json.loads((R/'config/registration37.json').read_text());name='doc/rrtmgp/UDM_FROZEN_EXPERIMENT.md';doc=(R/'WRF'/name).read_bytes();before['patched_blobs'][name]=hashlib.sha1(b'blob '+str(len(doc)).encode()+b'\0'+doc).hexdigest();require(before==after,'registration altered beyond documented prose digest')
 return data

def verify():
 d=load();j=lambda n:json.loads(d[n]);source=j('derived/model-profiles.json');enriched=j('derived/enriched.json');obs=[sounding(p.read_bytes()) for p in sorted((P/'raw').glob('sounding-*.txt'))];model=copy.deepcopy(source)
 oldmodel=json.loads((P.parent/'sterling-interior-day-evaluation/result.json').read_text())
 with tarfile.open(P.parent/'sterling-interior-day-evaluation/saved/evidence.tar.gz','r:gz') as t:old=json.loads(t.extractfile('extract/extracted.json').read())
 require(source['native_read'] and source['pid']>0 and source['history']['sha256']==old['model']['history']['sha256'],'native read history not qualified PR202 cold')
 for row in model['profiles']:
  prev=oldmodel['hourly_state'][row['hour_UTC']]['profiles']
  for k,v in enumerate(row['profiles']):
   require(v['dry_theta_K']==prev['T'][k]+300 and v['p_Pa']==f32(prev['P'][k]+prev['PB'][k]) and v['qv_kg_kg']==prev['QVAPOR'][k] and v['QCLOUD']==prev['QCLOUD'][k],'existing sealed native state mismatch')
   # The helper consumes REAL32; NumPy vector power and scalar libm can differ in
   # final REAL64 bits. Check exact equality at the declared native interface.
   require(f32(v['T_K'])==f32(v['dry_theta_K']*(v['p_Pa']/100000)**(287/1004.5)),'drytheta not temperature at native REAL32 interface')
 inputs=j('native/input.json');vals=[list(map(float,l.split())) for l in d['native/command-02.stdout'].decode().splitlines()];require(len(inputs)==len(vals)==339,'actual humidity record count')
 receipt=j('native/receipt.json');require(len(receipt['commands'])==2 and all(c['pid']>0 and c['status']=='TERMINAL' and c['actual_returncode']==0 and not c['timed_out'] for c in receipt['commands']),'native scalar processes')
 require(sha(d['native/native_saturation.f90'])==receipt['source']['sha256'] and sha(d['native/input.txt'])==receipt['input']['sha256'],'native input/helper source')
 native=(R/'WRF/phys/module_mp_udm.F').read_text();a=native.index('   integer, parameter                  ::  nxsvp');params=native[a:native.index('!-------------------------------------------------------------------------------\n! inline expansion table',a)].replace(', private','');routines=native[native.index('   subroutine udm_funct_svp_setup'):native.index('end module module_mp_udm')];prefix='module native_svp\n implicit none\n'+params+'\ncontains\n'+routines+'\nend module\n';require(d['native/native_saturation.f90'].decode().startswith(prefix),'native functions changed')
 expected=[]
 for arm,s in enumerate(obs):
  for l in s['levels']:
   if l['p_Pa'] is None or l['T_K'] is None or l['z_agl_m'] is None or not 0<=l['z_agl_m']<=3000:continue
   for kind in ['T_K','Td_K']:
    if l[kind] is not None:expected.append({'kind':'observation_'+kind,'arm':arm,'record':l['record'],'T_K':l[kind],'p_Pa':l['p_Pa'],'qv_kg_kg':0.})
 for arm,row in enumerate(model['profiles']):
  for l in row['profiles']:
   if 0<=l['z_agl_m']<=3000:expected.append({'kind':'model','arm':arm,'record':l['record'],'T_K':l['T_K'],'p_Pa':l['p_Pa'],'qv_kg_kg':l['qv_kg_kg']})
 require(expected==inputs,'native humidity input selection/units changed')
 for x,v in zip(inputs,vals):
  e,qs,rh=v;pp=f32(x['p_Pa']);q=f32(x['qv_kg_kg']);ep=f32(287./f32(461.6));require(qs==f32(f32(ep*e)/f32(pp-e)) and rh==f32(q/qs),'native saturation conversion replay')
  if x['kind']=='model':model['profiles'][x['arm']]['profiles'][x['record']-1].update(es_water_Pa=e,qs_water_kg_kg=qs,RH_water_ratio=rh)
  else:
   l=obs[x['arm']]['levels'][x['record']-1]
   if x['kind']=='observation_T_K':l.update(es_water_Pa=e,qs_water_kg_kg=qs)
   else:l['qv_from_dewpoint_kg_kg']=qs
 for s in obs:
  for l in s['levels']:l['RH_water_from_dewpoint_ratio']=l['qv_from_dewpoint_kg_kg']/l['qs_water_kg_kg'] if l.get('qv_from_dewpoint_kg_kg') is not None and l.get('qs_water_kg_kg') else None
 require(obs==enriched['soundings'] and model==enriched['model'] and metars((P/'raw/asos.csv').read_bytes())==enriched['surface_reports'],'enriched observations/model replay')
 prior=json.loads((P.parent/'sterling-cloud-loss-operation/result.json').read_text());result=evaluate(enriched,prior);require(result==json.loads((P/'result.json').read_text()),'atmospheric ruling replay')
 return result
if __name__=='__main__':
 r=verify();print(json.dumps({k:r[k] for k in ['status','radiosonde_actual_release_UTC','near_loss_vertical_T_structure','decision','physical_accuracy_approved','new_model_runs_in_saved_replay']},ensure_ascii=False))
