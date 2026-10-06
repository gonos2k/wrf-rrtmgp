#!/usr/bin/env python3
"""Standard-library integrity and metadata joins for the RFMIP lineage archive."""
from __future__ import annotations
import argparse, hashlib, json, math
from pathlib import Path

def sha(b): return hashlib.sha256(b).hexdigest()
def get_values(doc):
 if not isinstance(doc,dict) or not isinstance(doc.get('values'),list): raise ValueError('malformed Handle response')
 return {x.get('type'):x.get('data',{}).get('value') for x in doc['values']}
def verify(package:Path):
 package=package.resolve();mb=(package/'manifest.json').read_bytes();m=json.loads(mb)
 rows={x['path']:x for x in m.get('files',[])}
 actual={x.relative_to(package).as_posix() for x in package.rglob('*') if x.is_file() and x.relative_to(package).as_posix()!='manifest.json'}
 if actual!=set(rows) or m.get('file_count')!=len(rows):raise ValueError('closed package file roster mismatch')
 for rel,row in rows.items():
  b=(package/rel).read_bytes()
  if (len(b),sha(b))!=(row['size_bytes'],row['sha256']):raise ValueError('payload hash/size mismatch: '+rel)
 # Confirm package-origin index agrees with the sealed file records.
 origin=json.loads((package/'receipts/origin-inventory.json').read_text())
 origin_rows={x['package_path']:x for x in origin.get('origins',[])}
 # The origin inventory cannot hash itself without a recursive definition.
 if not set(origin_rows)<=set(rows)-{'receipts/origin-inventory.json'}:raise ValueError('origin inventory contains an unsealed path')
 for rel,o in origin_rows.items():
  row=rows[rel]
  o=origin_rows[rel]
  if (o.get('sha256'),o.get('size_bytes'))!=(row['sha256'],row['size_bytes']):raise ValueError('origin inventory mismatch: '+rel)
 # PID response joins: dataset RSD PID points to the file PID; that file PID is RSU.
 rsd=json.loads((package/'pid/ESGF-RSD-dataset-PID.response').read_text());rsu=json.loads((package/'pid/SW-reference-PID.response').read_text())
 rv=get_values(rsd);uv=get_values(rsu)
 if rsd.get('responseCode')!=1 or rsu.get('responseCode')!=1:raise ValueError('PID response unsuccessful')
 if rv.get('VERSION_NUMBER')!='20191007' or rv.get('AGGREGATION_LEVEL')!='DATASET':raise ValueError('RSD dataset PID version/level mismatch')
 if rv.get('HAS_PARTS')!='hdl:'+rsu.get('handle'):raise ValueError('RSD dataset HAS_PARTS does not join captured FILE PID')
 if uv.get('AGGREGATION_LEVEL')!='FILE' or uv.get('FILE_NAME')!='rsu_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc':raise ValueError('FILE PID does not identify RSU')
 if uv.get('FILE_SIZE')!='485284' or uv.get('CHECKSUM_METHOD')!='SHA256' or uv.get('CHECKSUM')!='0ea3f4272d9ef088db6ffd07153587863a052e3cf8b3bf04bfb7c9288ed8b324':raise ValueError('RSU PID checksum/size/method mismatch')
 capture=json.loads((package/'receipts/SW-reference-PID-capture.json').read_text())
 raw=(package/'pid/SW-reference-PID.response').read_bytes()
 if capture.get('http_status')!=200 or capture.get('handle')!=rsu.get('handle') or capture.get('raw_sha256')!=sha(raw) or capture.get('raw_bytes')!=len(raw):raise ValueError('raw PID capture receipt mismatch')
 retrieval=json.loads((package/'receipts/ESGF-RSD-replica-retrieval-v1.json').read_text())
 replica=next((x for x in retrieval if x.get('name')=='ESGF-RSD-replica'),None)
 if not replica or replica.get('http_status')!=200 or not replica.get('matches_retained_RSD_bytes'):raise ValueError('RSD replica retrieval receipt mismatch')
 # Reference output inventory separates exact Git snapshot identity from update chronology.
 join=json.loads((package/'joins/reference-byte-join-v1.json').read_text());jrows=join.get('rows',[])
 if {r.get('variable') for r in jrows}!={'rld','rlu','rsd','rsu'}:raise ValueError('reference byte-join row set mismatch')
 by={r['variable']:r for r in jrows}
 pinned=json.loads((package/'source/pinned-data-tree.json').read_text())
 if pinned.get('sha')!='ea788bb39876948fa8d2c235665ccff19b4686b5':raise ValueError('pinned data-tree root mismatch')
 pinned_blobs={x.get('path'):x.get('sha') for x in pinned.get('tree',[]) if x.get('type')=='blob'}
 for v,r in by.items():
  path='examples/rfmip-clear-sky/reference/'+v+'_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
  if (r.get('pinned_data_tree_blob'),r.get('git_blob_sha1'))!=(pinned_blobs.get(path),pinned_blobs.get(path)):
   raise ValueError('reference blob does not match actual pinned data-tree entry: '+v)
 if not all(r.get('local_to_pinned_snapshot_exact') for r in jrows):raise ValueError('retained reference not joined to pinned snapshot')
 if not all(by[v].get('local_to_20230621_commit_exact') for v in ('rsd','rsu')):raise ValueError('SW files not joined to June 2023 replacement')
 if any(by[v].get('local_to_20230621_commit_exact') for v in ('rld','rlu')):raise ValueError('LW history misattributed to June 2023')
 if {v:by[v]['bytes'] for v in by}!={'rld':484462,'rlu':484460,'rsd':485284,'rsu':485284}:raise ValueError('reference sizes mismatch')
 if by['rsd']['sha256']!=replica.get('sha256') or by['rsd']['bytes']!=replica.get('bytes'):raise ValueError('RSD replica receipt does not join byte inventory')
 # Official v1.0 SW coefficient receipt authenticates that release file, not the output generator.
 coeff=json.loads((package/'joins/authentic-coefficient-retrieval-v1.json').read_text())
 if coeff.get('status')!='PASS_OFFICIAL_RELEASE_FILE_BYTE_PROVENANCE' or not coeff.get('official_tree_blob_matches'):raise ValueError('historical coefficient byte provenance')
 if coeff.get('source_commit')!='ed5b0113109fcd23a010a90c61f21bad551146ef' or coeff.get('git_blob_sha1')!='63bc19ec5388da186a582cd69224711fe14d30fa':raise ValueError('coefficient source commit/blob mismatch')
 tree=json.loads((package/'source/v1.0-tree.json').read_text())
 trows=tree.get('tree',[])
 target='rrtmgp/data/rrtmgp-data-sw-g224-2018-12-04.nc'
 if tree.get('sha')!='ed5b0113109fcd23a010a90c61f21bad551146ef' or not any(x.get('path')==target and x.get('sha')==coeff['git_blob_sha1'] and x.get('type')=='blob' for x in trows):raise ValueError('official coefficient blob absent from pinned release tree')
 # The solar and variable-intersection receipts assert the limited data comparisons.
 cp=json.loads((package/'joins/coefficient-payload-join-v1.json').read_text())
 if cp.get('status')!='READ_ONLY_COEFFICIENT_PAYLOAD_INTERSECTION_COMPARISON' or cp.get('common_non_solar_variables')!=29 or cp.get('different_common_variable_names')!=[]:raise ValueError('common coefficient-array comparison receipt')
 solar=json.loads((package/'joins/solar-vector-join-v1.json').read_text())
 checks=solar.get('checks',{})
 if solar.get('status')!='READ_ONLY_OFFICIAL_RELEASE_SOLAR_VECTOR_JOIN' or checks.get('original_solar_vs_counterfactual_quiet_exact_values') is not True:raise ValueError('historical solar-vector join')
 if checks.get('band_gpoint_bounds_exact_all_three') is not True or checks.get('physical_band_limits_exact_all_three') is not True:raise ValueError('solar-vector coordinate join')
 # The Git commit chronology and source-label interpretation remain explicitly qualified.
 june=json.loads((package/'source/actual-reference-commit.json').read_text())
 if june.get('sha')!='162f494ed3950009c465372018cb6286b7d441c9':raise ValueError('June 2023 source commit pin')
 june_files={x.get('filename'):x.get('sha') for x in june.get('files',[])}
 for v in ('rsd','rsu'):
  path='examples/rfmip-clear-sky/reference/'+v+'_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
  if june_files.get(path)!=by[v].get('reference_update_commit_blob') or june_files.get(path)!=by[v].get('git_blob_sha1'):
   raise ValueError('June 2023 commit file blob mismatch: '+v)
 for v in ('rld','rlu'):
  path='examples/rfmip-clear-sky/reference/'+v+'_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
  if june_files.get(path)!=by[v].get('reference_update_commit_blob'):
   raise ValueError('June 2023 LW file-history blob mismatch: '+v)
 lw1=json.loads((package/'source/LW-reference-single-level-commit.json').read_text())
 lw2=json.loads((package/'source/LW-reference-quadrature-commit.json').read_text())
 if lw1.get('sha')!='41d3fa4fd1c363a084d311015fabcf60c9745708' or lw2.get('sha')!='8695c5c0184023daaaed51a24c7ab1ab0891a1f2':raise ValueError('May 2024 LW commit pins')
 if lw2.get('parents',[{}])[0].get('sha')!=lw1.get('sha'):raise ValueError('May 2024 LW commit chronology mismatch')
 for doc in (lw1,lw2):
  for v in ('rld','rlu'):
   path='examples/rfmip-clear-sky/reference/'+v+'_Efx_RTE-RRTMGP-181204_rad-irf_r1i1p1f1_gn.nc'
   match=next((x for x in doc.get('files',[]) if x.get('filename')==path),None)
   if not match:raise ValueError('LW update commit lacks reference file row: '+v)
   if doc is lw2 and match.get('sha')!=by[v].get('git_blob_sha1'):raise ValueError('latest LW update blob does not match pinned output: '+v)
 inv=json.loads((package/'receipts/causal-inventory.json').read_text())
 gate=inv.get('strict_gate',{}); failures=gate.get('failures',{})
 expected={'rsd':52972,'rsu':51099,'rld':0,'rlu':0}
 if {k:failures.get(k,{}).get('failed_cells') for k in expected}!=expected:
  raise ValueError('inherited strict-gate failure counts mismatch')
 selector=inv.get('v4_failure_selector_and_v5_diagnostic',{}).get('v4_selector',{}).get('selected_failure_counts',{})
 if selector!={'rsd':116,'rsu':39,'total':155}:
  raise ValueError('inherited v4 selector counts mismatch')
 report=(package/'report.md').read_text()
 if '104,071' not in report or '155 failures' not in report:raise ValueError('report omits inherited strict-gate counts')
 review=json.loads((package/'reviews/provenance-independent-review.json').read_text())
 if review.get('status')!='PASS_SCOPED_PROVENANCE_JOINS_NO_MATERIAL_OVERCLAIM':raise ValueError('independent provenance review scope/status')
 return {'status':'PASS_SCOPED_RFMIP_LINEAGE_ARCHIVE','files_checked':len(rows),'pid_joins_checked':2,'reference_git_rows_checked':4,'authenticated_official_coeff_file':True,'non_solar_intersection_count':29,'strict_gate_failure_counts':expected,'selected_v4_failure_counts':selector,'reference_data_included':False,'network_or_numerical_work':False,'scope':'Metadata, byte receipts and lineage joins only; exact historical output generator remains unauthenticated.'}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parent);a=ap.parse_args()
 print(json.dumps(verify(a.package),sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
