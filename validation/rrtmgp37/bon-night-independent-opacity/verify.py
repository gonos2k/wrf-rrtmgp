#!/usr/bin/env python3
"""Standard-library integrity checks for the independent opacity reconstruction archive."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from pathlib import Path
SIBLING_SHA='ed64b5df20737e7f94e7438d2737d22e041e0e1355f5c2c0c3c1e607a6201fc9'
PLAN_SHA='e032c4df5292d8ab8df31f482d1b43cde5993812096d206617a7f183bf7c4655'
SCRIPT_SHA='23ce2ce520186e98571d40b2ce329862a98ee50b7282bbe40e0bf427fe7789b4'
RESULT_SHA='0a95fefd5f230bac2fc94d8e9590cac8cd04a0d09cd3c9ebb869dee214fb6532'
EXECUTION_SHA='f02f3f577fdcdcdd9a09bd0c35f926c691aa160fb139ef95c9821da3ee4b2a8a'
STATIC_REVIEW_SHA='2330805644761b44ed577f54130e5674135b0e081d32c301acf7be6abb1e447d'
TERMINAL_SHA='7271c613c0fb148f01721828cc890e2c2d56ddb70ee20af8309f789d4df5f7a6'
DATA_JSON_SHA='c29615af763369684e0f577dfa5b4c369a2e99d9aa644da160ac56f720fd1398'
PIN_FILES={'held_input':'data/held-input.txt.gz','captured_n2_result':'data/captured-n2-result.txt.gz','n2_execution_record':'provenance/n2-execution.json','parser':'analysis/angular_reference.py'}
PRODUCTION_KEYS={'production_coefficients','production_frontend','production_kernel','production_adapter','production_constants','production_loader'}
def sha(b):return hashlib.sha256(b).hexdigest()
def fs(p):return sha(Path(p).read_bytes())
def finite(x):
 if isinstance(x,float):return math.isfinite(x)
 if isinstance(x,dict):return all(finite(v) for v in x.values())
 if isinstance(x,list):return all(finite(v) for v in x)
 return True
def verify(package:Path,repo:Path)->dict:
 package=package.resolve();repo=repo.resolve();own=json.loads((package/'manifest.json').read_text());rows={r['path']:r for r in own['payloads']}
 actual={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() and p.relative_to(package).as_posix()!='manifest.json'}
 if actual!=set(rows) or own.get('payload_count')!=len(rows):raise ValueError('package closed roster mismatch')
 for rel,row in rows.items():
  b=(package/rel).read_bytes()
  if len(b)!=row['size_bytes'] or sha(b)!=row['sha256']:raise ValueError('package payload mismatch: '+rel)
 for key,origin in own['origins'].items():
  b=(package/origin['package_path']).read_bytes()
  if origin['encoding']=='gzip-decompressed-content':b=gzip.decompress(b)
  if len(b)!=origin['origin_size_bytes'] or sha(b)!=origin['origin_sha256']:raise ValueError('copied input origin mismatch: '+key)
 sibling=repo/'validation/rrtmgp37/bon-night-independent-pfrac';smb=(package/'receipts/sibling-package-manifest.json').read_bytes()
 if sha(smb)!=SIBLING_SHA or (sibling/'manifest.json').read_bytes()!=smb:raise ValueError('pfrac sibling manifest pin mismatch')
 sm=json.loads(smb);srows={x['path']:x for x in sm['payloads']}
 sactual={p.relative_to(sibling).as_posix() for p in sibling.rglob('*') if p.is_file() and p.relative_to(sibling).as_posix()!='manifest.json'}
 if sactual!=set(srows):raise ValueError('sibling closed roster mismatch')
 for rel,row in srows.items():
  b=(sibling/rel).read_bytes()
  if len(b)!=row['size_bytes'] or sha(b)!=row['sha256']:raise ValueError('sibling payload mismatch: '+rel)
 planb=(package/'analysis/plan.json').read_bytes()
 if sha(planb)!=PLAN_SHA:raise ValueError('plan hash mismatch')
 plan=json.loads(planb)
 if sha((package/'analysis/analyze.py').read_bytes())!=SCRIPT_SHA:raise ValueError('analyzer hash mismatch')
 if set(plan['pins'])!=set(PIN_FILES)|PRODUCTION_KEYS:raise ValueError('plan pin roster mismatch')
 for key,pin in plan['pins'].items():
  if key in PRODUCTION_KEYS:
   marker='/WRF/'
   if marker not in pin['path']:raise ValueError('production path malformed: '+key)
   source=repo/'WRF'/pin['path'].split(marker,1)[1]
   b=source.read_bytes()
  else:
   path=package/PIN_FILES[key];raw=path.read_bytes()
   b=gzip.decompress(raw) if key in {'held_input','captured_n2_result'} else raw
  if len(b)!=pin['bytes'] or sha(b)!=pin['sha256']:raise ValueError('source/input pin mismatch: '+key)
 rb=gzip.decompress((package/'analysis/result.json.gz').read_bytes())
 if sha(rb)!=RESULT_SHA:raise ValueError('saved result hash mismatch')
 result=json.loads(rb)
 if result.get('status')!='PASS_SCOPED' or result.get('plan_sha256')!=PLAN_SHA or result.get('script_sha256')!=SCRIPT_SHA or result.get('pins')!=plan['pins'] or not finite(result):raise ValueError('result provenance/content linkage')
 exb=(package/'receipts/math-execution.json').read_bytes()
 if EXECUTION_SHA and sha(exb)!=EXECUTION_SHA:raise ValueError('execution receipt hash mismatch')
 ex=json.loads(exb)
 if ex.get('exit_code')!=0 or ex.get('result_sha256')!=RESULT_SHA or ex.get('plan_sha256')!=PLAN_SHA or ex.get('script_sha256')!=SCRIPT_SHA:raise ValueError('execution result linkage')
 launch=json.loads((package/'receipts/math-launched.json').read_text())
 if launch.get('pid')!=ex.get('pid') or launch.get('plan_sha256')!=PLAN_SHA or launch.get('script_sha256')!=SCRIPT_SHA:raise ValueError('launch receipt linkage')
 reviewb=(package/'reviews/precalculation-review-v1.json').read_bytes()
 if sha(reviewb)!=STATIC_REVIEW_SHA:raise ValueError('precalculation review pin')
 review=json.loads(reviewb)
 if review.get('blocking_findings') not in ([],None) or review.get('status')!='PASS_SCOPED_PRECALCULATION_SOURCE_MAPPING_INDEXING_AND_FROZEN_PINS':raise ValueError('static review status/findings')
 reviewed=review.get('reviewed',{})
 if reviewed.get('plan',{}).get('sha256')!=PLAN_SHA or reviewed.get('script',{}).get('sha256')!=SCRIPT_SHA:raise ValueError('static review plan/script linkage')
 required=reviewed.get('required_pins',{})
 if set(required)!=set(plan['pins']):raise ValueError('static review pin roster')
 for key,pin in plan['pins'].items():
  row=required[key]
  if (row.get('sha256'),row.get('size_bytes'))!=(pin['sha256'],pin['bytes']):raise ValueError('static review pin mismatch: '+key)
 terminalb=(package/'reviews/terminal-review-v1.json').read_bytes()
 terminal=json.loads(terminalb)
 if sha(terminalb)!=TERMINAL_SHA or not terminal.get('status','').startswith('PASS_SCOPED'):raise ValueError('terminal review pin/status')
 readback=terminal.get('saved_array_readback',{})
 if readback.get('target',{}).get('section')!='GAS_TAU_RAW' or readback.get('zero_mask_differences')!=0:raise ValueError('terminal saved-array readback')
 reviewed=terminal.get('reviewed',{})
 for name,digest in [('plan.json',PLAN_SHA),('analyze.py',SCRIPT_SHA),('execution.json',EXECUTION_SHA),('result.json',RESULT_SHA)]:
  if reviewed.get(name,{}).get('sha256')!=digest:raise ValueError('terminal review artifact linkage: '+name)
 data=repo/'WRF/external/rte_rrtmgp/DATA.json'
 if fs(data)!=DATA_JSON_SHA:raise ValueError('tracked coefficient metadata changed')
 meta=json.loads(data.read_text());coeff=next(x for x in meta['files'] if x['filename']=='rrtmgp-gas-lw-g128.nc')
 p=plan['pins']['production_coefficients']
 if (coeff['sha256'],coeff['size_bytes'])!=(p['sha256'],p['bytes']):raise ValueError('DATA.json coefficient link mismatch')
 return {'status':'PASS_SCOPED_INDEPENDENT_OPACITY_ARCHIVE_INTEGRITY','payload_count':len(rows),'plan_pins_checked':len(plan['pins']),
  'production_source_pins_checked':len(PRODUCTION_KEYS),'saved_result_sha256':RESULT_SHA,'analysis_rerun':False,
  'scope':'Integrity and provenance only; no opacity reconstruction, RTE, compiled replay, WRF or forecast.'}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parent);ap.add_argument('--source-root',type=Path);ap.add_argument('--output',type=Path)
 a=ap.parse_args();pkg=a.package.resolve();repo=a.source_root.resolve() if a.source_root else pkg.parents[2]
 result=verify(pkg,repo);text=json.dumps(result,indent=2,sort_keys=True)+'\n'
 if a.output:
  a.output.parent.mkdir(parents=True,exist_ok=True)
  with a.output.open('x') as f:f.write(text)
 print(json.dumps(result,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
