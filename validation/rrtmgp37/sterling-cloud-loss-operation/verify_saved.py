"""Standard-library replay: no WRF, compiler, RTE, Mie or network launch."""
from pathlib import Path
import json,hashlib,tarfile,gzip,io,importlib.util,re,sys
sys.path.insert(0,str(Path(__file__).resolve().parent))
from analyze import require,analyze,f32
from surface import evaluate as surface_evaluate
P=Path(__file__).resolve().parent;R=P.parents[2]
sha=lambda b:hashlib.sha256(b).hexdigest()
def load():
 ident=json.loads((P/'identity.json').read_text());raw=(P/'saved/evidence.tar.gz').read_bytes();require(sha(raw)==ident['archive']['sha256'] and len(raw)==ident['archive']['bytes'],'archive identity')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(raw)),mode='r:') as t:
  require(len(t.getmembers())==len(ident['files']) and set(t.getnames())==set(ident['files']) and all(m.isfile() and not m.name.startswith('/') and '..' not in Path(m.name).parts for m in t.getmembers()),'archive roster/type')
  d={n:t.extractfile(n).read() for n in ident['files']}
 for n,p in ident['files'].items():require(sha(d[n])==p['sha256'] and len(d[n])==p['bytes'],'payload identity '+n)
 for group in ['current_sources','dependencies']:
  for n,p in ident[group].items():require(sha((R/n).read_bytes())==p['sha256'],'current source/dependency '+n)
 for n,p in ident['outputs'].items():require(sha((P/n).read_bytes())==p['sha256'],'output '+n)
 require(d['plan.json']==(P/'plan.json').read_bytes() and d['run/executed-plan.json']==d['plan.json'],'declared plan changed')
 j=lambda n:json.loads(d[n]);run=j('run/receipt.json');build=j('build/receipt.json');pub=j('public-baseline-receipt.json');cold=j('cold-baseline-receipt.json')
 require(run['status']=='SUCCESS' and not run['error'] and len(run['commands'])==1,'bounded WRF process failure/count')
 for c in [*run['commands'],*build['commands']]:require(c['status']=='TERMINAL' and c['actual_returncode']==0 and not c['timed_out'] and c['pid']>0,'actual child not successful')
 require(len(build['commands'])==6 and build['base_library']['sha256']==pub['library']['sha256'],'qualified incremental build base/count')
 require(run['executable']['sha256']==build['executable']['sha256'] and run['initial']['sha256']==cold['initial']['sha256'] and run['forcing']['sha256']==cold['forcing']['sha256'],'different run inputs/executable')
 require(sha(d['run/host/namelist.input'])==run['namelist']['sha256'] and sha(d['run/host/radiation_iofields.txt'])==run['iofields']['sha256'] and sha(d['build/receipt.json'])==run['private_readonly_observer_build']['sha256'],'run asset identity')
 # The checkpoint is the very same cold checkpoint already used by PR202.
 oldident=json.loads((P.parent/'sterling-interior-day-evaluation/identity.json').read_text());oldarchive=P.parent/'sterling-interior-day-evaluation/saved/evidence.tar.gz';ob=oldarchive.read_bytes();require(sha(ob)==oldident['archive']['sha256'],'old campaign archive changed')
 with tarfile.open(fileobj=io.BytesIO(gzip.decompress(ob)),mode='r:') as t:
  olddiag=json.loads(t.extractfile('diagnostic/receipt.json').read());oldnml=t.extractfile('run/host/namelist.input').read().decode();oldpub=t.extractfile('public-baseline-receipt.json').read()
 require(run['checkpoint']['sha256']==olddiag['checkpoint']['sha256'] and run['checkpoint']['path']==olddiag['checkpoint']['path'] and sha(oldpub)==sha(d['public-baseline-receipt.json']),'same cold checkpoint/public library provenance')
 expected_changes={'run_seconds':'25320','start_hour':'11','start_minute':'58','end_day':'06','end_hour':'19','end_minute':'0','end_second':'0','history_begin_s':'120','history_interval_s':'3600','restart_interval_s':'1000000','restart':'.true.','override_restart_timers':'.true.','auxhist7_begin_s':'18120','auxhist7_end_s':'25320','auxhist8_begin_s':'18120','auxhist8_end_s':'25320'}
 require(run['time_IO_changes']==expected_changes,'unexpected physics/time/IO alteration')
 for name,value in expected_changes.items():
  if not re.search(r'(?im)^\s*'+name+r'\s*=',oldnml):oldnml=oldnml.replace('&time_control','&time_control\n '+name+' = '+value+',',1)
  oldnml,n=re.subn(r'(?im)^(\s*'+name+r'\s*=\s*)[^,\n]+',lambda m:m[1]+value,oldnml);require(n==1,'time key')
 require(oldnml==d['run/host/namelist.input'].decode(),'non-time/IO setting changed')
 eq=j('derived/history-comparison.json');require(eq['pairs']==1800 and not eq['differences'] and sorted(eq['inventory'])==[f'2016-10-06_{h:02d}:00:00' for h in range(12,20)],'cold equivalence count/window')
 require(all(len(row)==225 and all(v['equal'] and v['left_sha256']==v['right_sha256'] for v in row.values()) for row in eq['inventory'].values()),'observer changed native arrays')
 spec=importlib.util.spec_from_file_location('cloud_instrument',P/'instrument.py');ins=importlib.util.module_from_spec(spec);spec.loader.exec_module(ins)
 for n,rendered in ins.transform(R).items():
  require(rendered.encode()==d['build/'+n] and sha(d['build/'+n])==build['sources'][n]['sha256'],'transformed source '+n)
  path=R/('WRF/phys/' if 'physics_add' in n else 'WRF/dyn_em/')/n;it=iter(rendered.splitlines())
  require(all(any(v==line for v in it) for line in path.read_text().splitlines() if line.strip()),'native statements deleted or reordered')
 require((P/'probe.f90').read_bytes()==d['build/cloud_loss_probe.f90'],'private observer source changed')
 ex=j('derived/extracted.json');require(ex['native_read'] and sha(d['observer/cloud_operations.txt'])==ex['observer']['sha256'] and sha(d['derived/history-comparison.json'])==ex['history_comparison']['sha256'],'actual extraction identity')
 require(not ident['production_changes'] and not ident['physical_accuracy_approved'] and not ident['global_water_energy_approved'] and not ident['original_seven_conditions_changed'],'scientific scope promotion')
 return d

def verify():
 d=load();a=analyze(d['observer/cloud_operations.txt'].decode());require(a==json.loads(d['derived/analysis.json']),'actual operator analysis replay')
 ex=json.loads(d['derived/extracted.json']);old=json.loads((P.parent/'sterling-interior-day-evaluation/result.json').read_text());obs=[(P.parent/f'solrad-boundary-site-48h/raw/ste16{n}.dat').read_bytes() for n in [280,281]];sf=surface_evaluate(ex,obs,old)
 from summarize import summarize
 thermo=json.loads(d['thermo/result.json'])
 require(len(thermo['commands'])==2 and all(c['actual_returncode']==0 and not c['timed_out'] and c['pid']>0 for c in thermo['commands']),'native saturation process failure')
 require(sha(d['thermo/native_saturation.f90'])==thermo['helper']['sha256'] and sha((R/'WRF/phys/module_mp_udm.F').read_bytes())==thermo['native_source']['sha256'],'native saturation source')
 from analyze import parse
 rec,_,_=parse(d['observer/cloud_operations.txt'].decode())
 require(len(thermo['states'])==480,'native saturation support')
 for state in thermo['states']:
  t,k,stage=state['source_seconds'],state['k'],state['stage'];th,pi,p=rec[t,'micro_env_'+stage,0,0,k];q=rec[t,'micro_'+stage,0,1,k][0]
  require(state['actual_T_from_native_product_K']==f32(th*pi) and state['p_Pa']==p and state['qv']==q,'thermodynamic input not actual observed state')
  e=state['es_water_Pa'];ep=f32(287./f32(461.6));qs=f32(f32(ep*e)/f32(p-e))
  require(qs==state['qs_water_kg_kg'] and f32(q/qs)==state['RH_water_ratio'],'native saturation scalar conversion')
 r=summarize(a,sf,thermo,ex)
 require(r==json.loads((P/'result.json').read_text()),'decision and result replay')
 return r
if __name__=='__main__':
 r=verify();print(json.dumps({k:r[k] for k in ['status','decision','native_replay_counts','cold_array_pairs_equal','production_changes','physical_accuracy_approved','new_model_runs_in_saved_replay']},ensure_ascii=False))
