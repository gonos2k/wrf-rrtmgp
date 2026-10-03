#!/usr/bin/env python3
"""Authenticate retained text only; no external data/model/build/import calls."""
from pathlib import Path
import argparse,csv,hashlib,json
HERE=Path(__file__).resolve().parent

def require(condition,message):
 if not condition:raise ValueError(message)

def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def verify(root):
 manifest=json.loads((root/'artifact-manifest.json').read_text());seen=set()
 for entry in manifest['files']:
  rel=Path(entry['path']);require(not rel.is_absolute() and '..' not in rel.parts,'unsafe retained path');require(str(rel) not in seen,'duplicate retained path');seen.add(str(rel));p=root/rel
  require(not p.is_symlink() and p.is_file(),'missing or substituted retained payload');require(p.stat().st_size==entry['size_bytes'] and digest(p)==entry['sha256'],'retained payload changed: '+str(rel))
 actual={str(p.relative_to(root)) for p in root.rglob('*') if p.is_file() and p.name!='artifact-manifest.json'}
 require(actual==seen,'extra or missing retained files')
 l=json.loads((root/'four-model-ledger.json').read_text());freeze=json.loads((root/'receipts/root-source-freeze-v2.json').read_text());ci=json.loads((root/'receipts/pr47-ci-final-readback-v1.json').read_text())
 require(l['production7_sha256']==freeze['production'],'source7 pins differ');require(l['code_head_pr47']==ci['headRefOid']=='4394845667db52c258dab62719abc87402dd731f','source head differs');require(len(ci['statusCheckRollup'])==8 and all(x['conclusion']=='SUCCESS' and x['status']=='COMPLETED' for x in ci['statusCheckRollup']),'source CI snapshot invalid')
 require(l['source_entry_count']==6735 and l['source_symlink_count']==17 and l['shared_dependency_entries']==1582,'source/dependency scope differs')
 require(l['original_build_status']=='BUILD_FAIL_PRESERVED' and l['build_eligibility']=='BUILD_PASS_POSTHOC_ATTESTED','build erratum lost')
 require(l['new_model_invocations']==4 and len(l['models'])==4,'model count differs');combinations=set();rows_total=0
 for m in l['models']:
  arm=m['arm'];kind=m['kind'];require(arm in ('ra4','ra37') and kind in ('24h','own12_to13h'),'unexpected arm/kind');combinations.add((arm,kind));count=222 if arm=='ra4' else 225;rad=4 if arm=='ra4' else 37
  require(m['actual_model_invocations']==1 and m['before_pins_valid'] and m['after_pins_valid'],'model provenance gate failed');process=m['model'];require(process['returncode']==0 and not process['timed_out'] and process['model_completed'],'model terminal gate failed');require(len(process['rank_logs'])==4 and all(x['success'] and not x['fatal'] for x in process['rank_logs']),'rank success gate failed');require(process['stack_limit_soft_hard_bytes']==[536870912,536870912] and process['timeout_seconds']==1200,'resource scope differs')
  h=m['history'];require(h['variable_count']==count and h['numeric_variable_count']==count-1 and h['passed'] and h['numeric_variables_all_strict_pass'],'field scope failed');require(h['raw_nonfinite']==h['decoded_nonfinite']==h['mask_hits']==h['explicit_fill_or_missing_hits']==0,'numeric check failed');require(h['physics']=={'MP_PHYSICS':27,'RA_LW_PHYSICS':rad,'RA_SW_PHYSICS':rad} and h['geometry']=={'west_east':73,'south_north':60,'bottom_top':32},'physics/geometry differ')
  if kind=='24h':
   require(len(h['ordered_times'])==25 and h['ordered_times']==h['expected_times'],'continuous clock differs');p=m['history_preservation'];require(p['passed'] and p['whole_file_byte_identity'] and p['all_metadata_equal'] and p['all_variable_raw_bytes_equal'] and not p['raw_mismatches'],'history preservation failed');require(p['candidate']['sha256']==p['baseline']['sha256']==h['file']['sha256'],'whole file pins differ')
   require(len(m['own_checkpoints'])==2,'own checkpoints missing')
   for cp in m['own_checkpoints']:
    require(cp['numeric_variable_count']==663 and cp['passed'] and cp['numeric_variables_all_strict_pass'],'checkpoint checks failed');d=cp['repaired_diagnostics'];require(d['passed'],'repaired diagnostic failed')
    for name in ('QZ0','USTM'):require(d[name]['finite_count']==d[name]['total_count']==4380 and d[name]['negative_count']==0 and d[name]['passed'],'surface diagnostic contract failed')
    require(d['QZ0']['nonzero_count']==0 and d['QZ0']['quantiles']==[0.0]*5,'QZ0 initialization changed')
  else:
   q=m['comparison'];require(q['passed'] and q['variable_count_expected']==q['variable_count_observed']==count and q['reference_index']==13 and q['reference_time']=='2000-01-25_01:00:00','restart reference differs');require(q['all_raw_dtype_shape_dimensions_bytes_equal'] and q['all_metadata_matches_explicit_contract'] and q['all_variable_names_equal'] and q['all_dimensions_match_expected_slice'],'restart contract failed');require(not q['unexplained_global_attribute_differences'] and not q['variable_attribute_differences'] and set(q['global_attribute_differences'])=={'START_DATE'},'restart attribute exception widened')
   require(q['global_attribute_differences']['START_DATE']=={'continuous':{'string':'2000-01-24_12:00:00'},'restart':{'string':'2000-01-25_00:00:00'}},'START_DATE differs');require(q['dimension_differences']=={'Time':{'continuous':{'size':25,'unlimited':True},'restart':{'size':1,'unlimited':True}}},'dimension normalization widened')
   with (root/q['retained_raw_field_pin_table']).open(newline='') as stream:rows=list(csv.DictReader(stream))
   require(len(rows)==count and len({x['variable'] for x in rows})==count and all(x['all_raw_dtype_shape_attributes_equal']=='true' and len(x['raw_sha256'])==64 and len(x['variable_attributes_canonical_sha256'])==64 for x in rows),'retained restart field table invalid');rows_total+=len(rows)
 require(combinations=={('ra4','24h'),('ra37','24h'),('ra4','own12_to13h'),('ra37','own12_to13h')},'model ledger incomplete')
 return {'status':'PASS_RETAINED_ARTIFACTS_AND_INTERNAL_LEDGER','retained_files':len(seen),'models_in_accepted_ledger':4,'restart_raw_fields':rows_total,'scope':'No omitted external data recalculation, WRF build/model or runner invocation'}

if __name__=='__main__':
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--package-root',type=Path,default=HERE);args=p.parse_args();print(json.dumps(verify(args.package_root.resolve(strict=True))))
