#!/usr/bin/env python3
"""Standard-library checks for the common-angle attribution archive."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from pathlib import Path
COMMON_MANIFEST_SHA='b3f839f7b9a64dfc8ee58415dbc11d5d9d20ec31d356f708b124cc029028ba48'
PFRAC_MANIFEST_SHA='ed64b5df20737e7f94e7438d2737d22e041e0e1355f5c2c0c3c1e607a6201fc9'
PLAN_SHA='34ca6fe02230cb01ea97eef4a47943d337b50c1be6786fae04b8c595b8707962'
SCRIPT_SHA='05bb1bcac5d3a03f79c2df3dffff4bb0acf42c92e4e7369d2c094c2a22fe3ea2'
RESULT_SHA='bd6495bfde4848306f176a759e74106dbd3a30a2ac01ab665207b75fcc9219c5'
EXECUTION_SHA='6dc3a15493e2ca5a6c721887292471c167cffc8520fe67b5fa030d9452b1ae3a'
STATIC_SHA='8b8b5d558afca63a7f0012c5d112618d80d8d0866124f7ec172f59b77d816296'
TERMINAL_SHA='760a3ac94f01806ff123e99d60bdf47e411529be5b8680e9c65fead9caf51db4'
PIN_FILES={'packet':'data/legacy-packet.txt.gz','input':'data/held-input.txt.gz','gp_result':'data/captured-n2-result.txt.gz','gp_source':'data/gp-transport.txt.gz','legacy_helper':'analysis/legacy_lw_replay.py','angular_helper':'analysis/angular_reference.py','legacy_actual_replay':'provenance/legacy-native-angle-replay.json','legacy_actual_review':'provenance/legacy-native-angle-review.json','common_result':'provenance/common-band-result.json','optical_scope':'provenance/optical-scope-addendum.json'}
def sha(b):return hashlib.sha256(b).hexdigest()
def fs(p):return sha(Path(p).read_bytes())
def finite(x):
 if isinstance(x,float):return math.isfinite(x)
 if isinstance(x,dict):return all(finite(v) for v in x.values())
 if isinstance(x,list):return all(finite(v) for v in x)
 return True
def check_archive(package,sibling,expected_manifest):
 mb=(package/'manifest.json').read_bytes()
 if sha(mb)!=expected_manifest:raise ValueError('sibling manifest pin mismatch')
 m=json.loads(mb);rows={x['path']:x for x in m['payloads']}
 actual={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() and p.relative_to(package).as_posix()!='manifest.json'}
 if actual!=set(rows):raise ValueError('sibling closed roster mismatch')
 for rel,row in rows.items():
  b=(package/rel).read_bytes()
  if len(b)!=row['size_bytes'] or sha(b)!=row['sha256']:raise ValueError('sibling payload mismatch '+rel)
 return m
def verify(package:Path,repo:Path):
 package=package.resolve();repo=repo.resolve();own=json.loads((package/'manifest.json').read_text());rows={x['path']:x for x in own['payloads']}
 actual={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() and p.relative_to(package).as_posix()!='manifest.json'}
 if actual!=set(rows) or own.get('payload_count')!=len(rows):raise ValueError('package closed roster mismatch')
 for rel,row in rows.items():
  b=(package/rel).read_bytes()
  if len(b)!=row['size_bytes'] or sha(b)!=row['sha256']:raise ValueError('payload mismatch '+rel)
 for key,o in own['origins'].items():
  b=(package/o['package_path']).read_bytes()
  if o['encoding']=='gzip-decompressed-content':b=gzip.decompress(b)
  if (len(b),sha(b))!=(o['origin_size_bytes'],o['origin_sha256']):raise ValueError('package origin mismatch '+key)
 common=repo/'validation/rrtmgp37/bon-night-common-band-source';pfrac=repo/'validation/rrtmgp37/bon-night-independent-pfrac'
 cm=check_archive(common,common,COMMON_MANIFEST_SHA);pm=check_archive(pfrac,pfrac,PFRAC_MANIFEST_SHA)
 for filename,arch in [('common-band-source-manifest.json',common),('independent-pfrac-manifest.json',pfrac)]:
  if (package/'receipts'/filename).read_bytes()!=(arch/'manifest.json').read_bytes():raise ValueError('archived sibling manifest differs '+filename)
 copy_map={'data/legacy-packet.txt.gz':common/'data/legacy-lw-packet.txt.gz','data/held-input.txt.gz':pfrac/'data/held-input.txt.gz','data/captured-n2-result.txt.gz':pfrac/'data/captured-n2-result.txt.gz','data/gp-transport.txt.gz':pfrac/'data/captured-n2-sidecar.txt.gz','analysis/legacy_lw_replay.py':common/'analysis/legacy_lw_replay.py','analysis/angular_reference.py':common/'analysis/angular_reference.py','provenance/common-band-result.json':common/'analysis/result.json'}
 for rel,source in copy_map.items():
  if (package/rel).read_bytes()!=source.read_bytes():raise ValueError('copied verified sibling payload differs '+rel)
 planb=(package/'analysis/plan.json').read_bytes()
 if sha(planb)!=PLAN_SHA:raise ValueError('plan hash mismatch')
 plan=json.loads(planb)
 if sha((package/'analysis/analyze.py').read_bytes())!=SCRIPT_SHA:raise ValueError('analyzer hash mismatch')
 if set(plan['pins'])!=set(PIN_FILES)|{'legacy_source'}:raise ValueError('plan pin roster mismatch')
 for key,pin in plan['pins'].items():
  if key=='legacy_source':source=repo/'WRF/phys/module_ra_rrtmg_lw.F';b=source.read_bytes()
  else:
   q=package/PIN_FILES[key];b=q.read_bytes()
   if key in {'packet','input','gp_result','gp_source'}:b=gzip.decompress(b)
  if (len(b),sha(b))!=(pin['bytes'],pin['sha256']):raise ValueError('input/source pin mismatch '+key)
 resultb=gzip.decompress((package/'analysis/result.json.gz').read_bytes())
 if sha(resultb)!=RESULT_SHA:raise ValueError('saved result hash mismatch')
 result=json.loads(resultb)
 if result.get('status')!='PASS_SCOPED' or result.get('plan_sha256')!=PLAN_SHA or result.get('script_sha256')!=SCRIPT_SHA or result.get('pins')!=plan['pins'] or not finite(result):raise ValueError('result linkage/content mismatch')
 exb=(package/'receipts/execution.json').read_bytes()
 if sha(exb)!=EXECUTION_SHA:raise ValueError('execution receipt hash')
 ex=json.loads(exb)
 if ex.get('exit_code')!=0 or ex.get('result_sha256')!=RESULT_SHA or ex.get('plan_sha256')!=PLAN_SHA or ex.get('script_sha256')!=SCRIPT_SHA:raise ValueError('execution/result linkage')
 launch=json.loads((package/'receipts/launched.json').read_text())
 if launch.get('pid')!=ex.get('pid') or launch.get('plan_sha256')!=PLAN_SHA or launch.get('script_sha256')!=SCRIPT_SHA:raise ValueError('launch/execution linkage')
 sb=(package/'reviews/static-review-v1.json').read_bytes();static=json.loads(sb)
 if sha(sb)!=STATIC_SHA or static.get('status')!='PASS_SCOPED_STATIC_ANALYTIC_CLOSURE_SOURCE_UNITS_AND_INDEXING' or static.get('blocking_findings') not in ([],None):raise ValueError('static review')
 sr=static.get('reviewed',{})
 if sr.get('plan',{}).get('sha256')!=PLAN_SHA or sr.get('script',{}).get('sha256')!=SCRIPT_SHA or set(sr.get('pins',{}))!=set(plan['pins']):raise ValueError('static review plan/pin set')
 for k,pin in plan['pins'].items():
  if (sr['pins'][k].get('sha256'),sr['pins'][k].get('size_bytes'))!=(pin['sha256'],pin['bytes']):raise ValueError('static review pin '+k)
 tb=(package/'reviews/terminal-review-v1.json').read_bytes();term=json.loads(tb)
 if sha(tb)!=TERMINAL_SHA or not term.get('status','').startswith('PASS_SCOPED'):raise ValueError('terminal review')
 reviewed=term.get('reviewed',{})
 for name,digest in [('plan.json',PLAN_SHA),('analyze.py',SCRIPT_SHA),('execution.json',EXECUTION_SHA),('result.json',RESULT_SHA)]:
  if reviewed.get(name,{}).get('sha256')!=digest:raise ValueError('terminal artifact linkage '+name)
 return {'status':'PASS_SCOPED_COMMON_ANGLE_ARCHIVE_INTEGRITY','payload_count':len(rows),'plan_pins_checked':len(plan['pins']),
  'sibling_archives_checked':2,'saved_result_sha256':RESULT_SHA,'analysis_rerun':False,
  'scope':'Archive/provenance only; no angular integration, RTE, compiled replay, WRF or forecast.'}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parent);ap.add_argument('--source-root',type=Path);ap.add_argument('--output',type=Path)
 a=ap.parse_args();pkg=a.package.resolve();repo=a.source_root.resolve() if a.source_root else pkg.parents[2]
 out=verify(pkg,repo);text=json.dumps(out,indent=2,sort_keys=True)+'\n'
 if a.output:
  a.output.parent.mkdir(parents=True,exist_ok=True)
  with a.output.open('x') as f:f.write(text)
 print(json.dumps(out,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
