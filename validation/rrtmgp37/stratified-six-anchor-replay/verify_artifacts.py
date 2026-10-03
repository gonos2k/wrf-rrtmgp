#!/usr/bin/env python3
"""Portable stdlib-only hash/schema/mapping verifier; never accesses original outputs or engines."""
import hashlib,json,math,struct
from pathlib import Path
HERE=Path(__file__).resolve().parent

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads((HERE/p).read_text())
def close(a,b,rtol,atol,label):
 assert len(a)==len(b),label+':shape'
 for x,y in zip(a,b):
  assert math.isfinite(x) and math.isfinite(y),label+':finite'
  assert abs(x-y)<=atol+rtol*abs(y),(label,x,y)
def f32(x):return struct.unpack('f',struct.pack('f',x))[0]
def finite_tree(x):
 if isinstance(x,float):assert math.isfinite(x)
 elif isinstance(x,dict):
  for y in x.values():finite_tree(y)
 elif isinstance(x,list):
  for y in x:finite_tree(y)

def main():
 manifest=read('manifest.json');items=manifest['artifacts']
 canonical=json.dumps(items,sort_keys=True,separators=(',',':')).encode()
 assert hashlib.sha256(canonical).hexdigest()==manifest['canonical_artifacts_sha256']
 for name,pin in items.items():
  path=HERE/name;assert Path(name).is_relative_to('.') and '..' not in Path(name).parts and path.is_file() and not path.is_symlink()
  assert path.resolve().is_relative_to(HERE) and path.stat().st_size==pin['bytes'] and sha(path)==pin['sha256'],name
 assert {str(p.relative_to(HERE)) for p in HERE.rglob('*') if p.is_file()}==set(items)|{'manifest.json'}
 index=read('index.json');assert index['future_git_base_commit']=='22ab474286c7b808d6f81e08ce457ddf6ba8e9cb'
 assert index['canonical_count']==6 and index['historical_audit_count']==2
 assert index['total_actual_calls']==dict(WRF=8,LW=8,SW=7,strict_reference=15)
 assert index['total_full_LW_SW']==7 and index['total_LW_only_night']==1
 assert index['new_model_or_reference_calls']==index['source_edits']==0 and not index['publication']
 rows=index['rows'];assert len(rows)==8 and len({(r['i'],r['j']) for r in rows})==8
 counts=dict(canonical=0,historical_audit=0);phasecounts=dict(LW=0,SW=0)
 for row in rows:
  counts[row['role']]+=1
  assert row['history_file_sha256']=='7a76a430f1d37ba88ee2692c5cb076a271f3d525a1190b5cd824df3790225025'
  assert row['history_geometry']==[289,189,39] and row['history_physics']==[27,37,37]
  assert row['pins_unchanged'] and row['history_all_numeric_raw_decoded_finite_unmasked'] and row['numeric_history_variables']==210
  original=read(row['original_execution_receipt']);assert original['returncode']==0 and original['history_sha256']==row['history_file_sha256'] and original['postflight_pins_unchanged']
  for phase,evidence in row['phases'].items():
   if evidence['status']!='STRICT_PASS':
    assert row['role']=='historical_audit' and row['case']=='unclipped_cloud_control' and (row['i'],row['j'])==(22,37) and phase=='SW'
    assert evidence['status']=='SW_NOT_RUN_AT_NIGHT_EXPECTED_PRODUCTION_GATE' and evidence['actual_reference_calls']==evidence['strict_sections']==0 and row['history_COSZEN']<0
    assert not (HERE/f"evidence/{row['role']}/{row['case']}/profiles-sw.json").exists()
    continue
   phasecounts[phase]+=1
   report=read(evidence['strict_report']);compare=report['reference_comparison']
   assert compare['passed'] and compare['sections_compared']==(20 if phase=='LW' else 46)
   assert not compare['failed_sections'] and not compare['missing_sections']
   assert report['captured_column']==dict(i=row['i'],j=row['j'])
   finite_tree(compare['max_differences'])
   p=read(evidence['actual_profile_snapshot']);finite_tree(p)
   assert (p['case'],p['phase'],p['i'],p['j'],p['native_layers'])==(row['case'],phase,row['i'],row['j'],39)
   assert p['adapter_layers']==(47 if phase=='LW' else 40) and p['input_header']==('RRTMGP_REPLAY_V8' if phase=='LW' else 'RRTMGP_REPLAY_V9')
   assert p['step']==721 and p['source_seconds']==43200 and p['captured_MP_PHYSICS']==27
   assert p['frozen_mode']==p['frozen_occurrence']==1 and p['table_sha256']=='8cb00850c3f885f5ec0306563c1ec0a55b512478a7395d626c1c99cebf280583'
   cf=p['raw_CF'];mass=p['native_dry_mass_kg_m2'];assert len(cf)==len(mass)==39 and all(0<=x<=1 for x in cf) and all(x>0 for x in mass)
   a=p['adapter'];close(a['CF'][:39],cf,0,0,'CF raw/input')
   q=p['corrected_native_q'];assert all(len(x)==39 and all(y>=0 for y in x) for x in q.values())
   stats=p['actual_eligibility_and_mass'];assert stats==evidence['actual_eligibility_and_mass']
   for species,values in q.items():
    grid=[x*m*1000 for x,m in zip(values,mass)]
    close([stats['actual_cf0_grid_phase_mass_g_m2'][species]],[sum(x for x,c in zip(grid,cf) if c==0)],5.e-7,1.e-12,species+' CF0 grid mass')
    close([stats['actual_cf_positive_grid_phase_mass_g_m2'][species]],[sum(x for x,c in zip(grid,cf) if c>0)],5.e-7,1.e-12,species+' CFpositive grid mass')
   for species,field in [('QR','actual_raw_omitted_rain_g_m2'),('QS','actual_raw_omitted_snow_g_m2')]:
    close([stats[field]],[stats['actual_cf0_grid_phase_mass_g_m2'][species]],5.e-7,1.e-12,species+' actual omission/native mass')
   for path,species in [('LWP','QC'),('IWP','QI'),('RWP','QR'),('SWP','QS')]:
    expected=[x*m*1000/c if c>0 else 0. for x,m,c in zip(q[species],mass,cf)]
    close(a[path][:39],expected,5.e-7,1.e-12,path+' native/CF')
   for path,species in [('GWP','QG'),('HWP','QH')]:
    raw=p['raw_frozen_phase_paths'];expected=[x*m*1000 for x,m in zip(q[species],mass)]
    close(raw[path+'_GRID'],expected,1.e-6,1.e-12,path+' native mass')
    close(raw[path+'_RADIATION'],raw[path+'_GRID'],0,0,path+' GRID/RADIATION')
    close(a[path][:39],raw[path+'_RADIATION'],0,0,path+' RADIATION/adapter')
    assert all(x==0 for x in raw[path+'_OMITTED']) and all(x==0 for x in a[path][39:])
   for radius,source,species,bg in [('REL','SOURCE_RE_CLOUD','QC',2.49e-6),('REI','SOURCE_RE_ICE','QI',4.99e-6),('RES','SOURCE_RE_SNOW','QS',9.99e-6)]:
    close(a[radius][:39],p['raw_mapped_radius_um'][radius],0,0,radius+' mapped/adapter')
    assert p['radius_capability'][{'REL':'HAS_REQC','REI':'HAS_REQI','RES':'HAS_REQS'}[radius]]==1
    expected=[]
    for k,x in enumerate(p['native_source_radius_m'][source]):
     fallback=f32(x)==f32(bg) and p['raw_native_q'][species][k]>0 and cf[k]>0
     expected.append(p['host_fallback_radius_um']['FALLBACK_'+radius][k] if fallback else x*1.e6)
    close(a[radius][:39],expected,5.e-7,1.e-7,radius+' native/background mapping')
   close(p['production_RL_USED_um'],[max(2.5,min(21.5,x)) for x in a['REL'][:39]],5.e-7,1.e-7,'liquid RL_USED radius')
   close(p['production_DI_USED_um'],[max(10.,min(180.,2*x)) for x in a['REI'][:39]],5.e-7,1.e-7,'cloudice DI_USED diameter')
   assert evidence['recorded_MASK_exact_equal_reference'] and evidence['actual_reference_calls']==1
  if row['role']=='canonical':assert all(x['status']=='STRICT_PASS' for x in row['phases'].values())
 assert counts==dict(canonical=6,historical_audit=2) and phasecounts==dict(LW=8,SW=7)
 for f in index['retained_failed_receipts']:assert read(f)['status'] in {'FAIL_PRESERVED','RECOVERY_FAIL_PRESERVED'}
 print(f"PASS: {len(items)} retained artifacts; six canonical two-phase + two historical audit sites; 8 LW/7 SW receipts. Zero engines; original outputs/executables/data not read.")
if __name__=='__main__':main()
