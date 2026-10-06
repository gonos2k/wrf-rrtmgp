#!/usr/bin/env python3
"""Verify the closed shared-source attribution archive (no numerical work)."""
from __future__ import annotations
import argparse, gzip, hashlib, json, math
from pathlib import Path

PLAN_SHA = '486eb3d290d72ca1337f47807bf8348df8d7daaba84b5ca008f49f5c347eaca0'
ANALYZER_SHA = 'a149f6040cbc75c074bc2da980e192604ceb3def81afbf7bf4486a9206fad473'
RESULT_SHA = '22658918f336ab362eaf5b0402318d7ae62b471eca9a5cc6e4ba860f47a02dca'
DRIVER_LOG_SHA = '45dd1d6e2b3057113d39f9f7129758260070ff7b61c61468ed1138e36302fe9f'
EXECUTION_RECEIPT_SHA = '5c2c39569c500c62841b87e32fe165a8ff6f4a054934017cabfc65cbc984d0f5'
LAUNCH_SHA = 'aa4024d1be7744e3dd44d6df6bcf8d6c9c2490e98dd1196ec6d1171b82a71e60'
STATIC_REVIEW_SHA = '8e942a65df817d6f208a337cd9c6d9711f3db87c6ded8ce101df51bcded0e801'
TERMINAL_REVIEW_SHA = 'e4ed19ffea4daeeb3834ddcdbab8953349e309d5b5e8a89fd6d581b929699b84'
SIBLING_MANIFESTS = {
 'common-angle': '1bcb30a3d01f80d9913a276a0964a8979a83f9f07b72cb5918d1aedd9e1c8722',
 'pfrac': 'ed64b5df20737e7f94e7438d2737d22e041e0e1355f5c2c0c3c1e607a6201fc9',
 'planck': '29c21ced5738c122981d3489441a3baa7c22ed8b11e71eae0dd525d74b6f81d8',
}
SIBLING_DIRS = {'common-angle':'bon-night-common-angle','pfrac':'bon-night-independent-pfrac','planck':'bon-night-planck-source'}
PIN_PATHS = {
 'packet':'data/legacy-packet.txt.gz','input':'data/held-input.txt.gz',
 'gp_result':'data/captured-n2-result.txt.gz','gp_source':'data/gp-transport.txt.gz',
 'legacy_helper':'analysis/legacy_lw_replay.py','angular_helper':'analysis/angular_reference.py',
 'common_angle_helper':'analysis/common-angle-analyze.py',
 'common_angle_result':'provenance/common-angle-result.json',
 'independent_pfrac':'provenance/independent-pfrac-result.json',
 'independent_Planck':'provenance/independent-planck-result.json',
 'legacy_source':'provenance/module_ra_rrtmg_lw.F.gz',
 'GP_kernel':'provenance/mo_gas_optics_rrtmgp_kernels.F90.gz',
}
DECOMPRESSED = {'packet','input','gp_result','gp_source','legacy_source','GP_kernel'}
def digest(data: bytes) -> str: return hashlib.sha256(data).hexdigest()
def finite(x):
 if isinstance(x,float): return math.isfinite(x)
 if isinstance(x,dict): return all(finite(v) for v in x.values())
 if isinstance(x,list): return all(finite(v) for v in x)
 return True
def check_sibling(path: Path, expected: str):
 manifest=(path/'manifest.json').read_bytes()
 if digest(manifest)!=expected: raise ValueError(f'sibling manifest SHA mismatch: {path.name}')
 doc=json.loads(manifest); rows={r['path']:r for r in doc['payloads']}
 actual={p.relative_to(path).as_posix() for p in path.rglob('*') if p.is_file() and p.relative_to(path).as_posix()!='manifest.json'}
 if actual!=set(rows) or doc.get('payload_count')!=len(rows): raise ValueError(f'sibling closed roster mismatch: {path.name}')
 for rel,row in rows.items():
  data=(path/rel).read_bytes()
  if len(data)!=row['size_bytes'] or digest(data)!=row['sha256']: raise ValueError(f'sibling payload mismatch: {rel}')
 return manifest

def verify(package: Path, repo: Path):
 package=package.resolve(); repo=repo.resolve()
 mb=(package/'manifest.json').read_bytes(); manifest=json.loads(mb)
 rows={r['path']:r for r in manifest.get('payloads',[])}
 actual={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() and p.relative_to(package).as_posix()!='manifest.json'}
 if actual!=set(rows) or manifest.get('payload_count')!=len(rows): raise ValueError('package closed roster mismatch')
 for rel,row in rows.items():
  data=(package/rel).read_bytes()
  if len(data)!=row['size_bytes'] or digest(data)!=row['sha256']: raise ValueError(f'package payload mismatch: {rel}')
 planb=(package/'analysis/plan.json').read_bytes(); scriptb=(package/'analysis/analyze.py').read_bytes()
 if digest(planb)!=PLAN_SHA or digest(scriptb)!=ANALYZER_SHA: raise ValueError('frozen plan/analyzer hash mismatch')
 plan=json.loads(planb); origins=json.loads((package/'provenance/package-origins.json').read_text())['origins']
 if set(plan['pins'])!=set(PIN_PATHS): raise ValueError('plan pin roster mismatch')
 if set(origins)!=(set(PIN_PATHS)|{k+'_sibling_manifest' for k in SIBLING_MANIFESTS}): raise ValueError('origin roster mismatch')
 for key,pin in plan['pins'].items():
  data=(package/PIN_PATHS[key]).read_bytes()
  if key in DECOMPRESSED: data=gzip.decompress(data)
  if (len(data),digest(data))!=(pin['bytes'],pin['sha256']): raise ValueError(f'plan pin mismatch: {key}')
  origin=origins[key]
  if origin['package_path']!=PIN_PATHS[key] or (origin['origin_sha256'],origin['origin_size_bytes'])!=(pin['sha256'],pin['bytes']): raise ValueError(f'origin metadata mismatch: {key}')
 for name,expected in SIBLING_MANIFESTS.items():
  sibling=repo/f"validation/rrtmgp37/{SIBLING_DIRS[name]}"
  sibmanifest=check_sibling(sibling,expected)
  rel=f'receipts/{name}-manifest.json'; stored=(package/rel).read_bytes()
  if stored!=sibmanifest: raise ValueError(f'archived sibling manifest differs: {name}')
  o=origins[name+'_sibling_manifest']
  if digest(stored)!=o['origin_sha256'] or len(stored)!=o['origin_size_bytes']: raise ValueError(f'sibling-origin receipt mismatch: {name}')
 # Check the archived, portable copies against their owning sibling archives.
 joins={
  'analysis/legacy_lw_replay.py':repo/'validation/rrtmgp37/bon-night-common-angle/analysis/legacy_lw_replay.py',
  'analysis/angular_reference.py':repo/'validation/rrtmgp37/bon-night-common-angle/analysis/angular_reference.py',
  'analysis/common-angle-analyze.py':repo/'validation/rrtmgp37/bon-night-common-angle/analysis/analyze.py',
  'provenance/independent-pfrac-result.json':repo/'validation/rrtmgp37/bon-night-independent-pfrac/analysis/result.json',
  'provenance/independent-planck-result.json':repo/'validation/rrtmgp37/bon-night-planck-source/analysis/result.json',
 }
 for rel,src in joins.items():
  if (package/rel).read_bytes()!=src.read_bytes(): raise ValueError(f'sibling payload join mismatch: {rel}')
 angle=gzip.decompress((repo/'validation/rrtmgp37/bon-night-common-angle/analysis/result.json.gz').read_bytes())
 if (package/'provenance/common-angle-result.json').read_bytes()!=angle: raise ValueError('common-angle result join mismatch')
 for key,rel in [('legacy_source','WRF/phys/module_ra_rrtmg_lw.F'),('GP_kernel','WRF/external/rte_rrtmgp/rrtmgp-kernels/mo_gas_optics_rrtmgp_kernels.F90')]:
  data=(repo/rel).read_bytes()
  if (len(data),digest(data))!=(plan['pins'][key]['bytes'],plan['pins'][key]['sha256']): raise ValueError(f'tracked source mismatch: {key}')
 resultb=(package/'analysis/result.json').read_bytes()
 if digest(resultb)!=RESULT_SHA: raise ValueError('saved result hash mismatch')
 result=json.loads(resultb)
 if result.get('status')!='PASS_SCOPED' or result.get('plan_sha256')!=PLAN_SHA or result.get('script_sha256')!=ANALYZER_SHA or result.get('pins')!=plan['pins'] or not finite(result): raise ValueError('saved result linkage/content mismatch')
 exb=(package/'receipts/execution.json').read_bytes(); ex=json.loads(exb)
 if digest(exb)!=EXECUTION_RECEIPT_SHA: raise ValueError('execution receipt hash')
 if ex.get('exit_code')!=0 or ex.get('status')!='PASS_SCOPED' or ex.get('result_sha256')!=RESULT_SHA or ex.get('plan_sha256')!=PLAN_SHA or ex.get('script_sha256')!=ANALYZER_SHA: raise ValueError('execution/result linkage mismatch')
 launchb=(package/'receipts/launched.json').read_bytes(); launch=json.loads(launchb)
 if digest(launchb)!=LAUNCH_SHA: raise ValueError('launch receipt hash')
 if launch.get('pid')!=ex.get('pid') or launch.get('plan_sha256')!=PLAN_SHA or launch.get('script_sha256')!=ANALYZER_SHA: raise ValueError('launch/execution linkage mismatch')
 if digest((package/'receipts/driver.log').read_bytes())!=DRIVER_LOG_SHA: raise ValueError('driver log hash mismatch')
 staticb=(package/'reviews/precalculation-review-v1.json').read_bytes(); static=json.loads(staticb)
 if digest(staticb)!=STATIC_REVIEW_SHA: raise ValueError('precalculation review hash')
 if static.get('status')!='PASS_SCOPED_STATIC_NO_BLOCKING_FINDING' or static.get('blocking_findings') not in ([],None): raise ValueError('precalculation review status')
 reviewed=static.get('reviewed',{})
 if reviewed.get('plan',{}).get('sha256')!=PLAN_SHA or reviewed.get('analyzer',{}).get('sha256')!=ANALYZER_SHA: raise ValueError('precalculation review linkage')
 terminalb=(package/'reviews/terminal-review-v1.json').read_bytes(); terminal=json.loads(terminalb)
 if digest(terminalb)!=TERMINAL_REVIEW_SHA: raise ValueError('terminal review hash')
 tp=terminal.get('pins',{})
 expected_terminal={'plan':PLAN_SHA,'analyzer':ANALYZER_SHA,'result':RESULT_SHA,'execution':EXECUTION_RECEIPT_SHA,'launch':LAUNCH_SHA,'driver_log':DRIVER_LOG_SHA}
 for name,expected in expected_terminal.items():
  if tp.get(name,{}).get('sha256')!=expected: raise ValueError(f'terminal review linkage: {name}')
 if terminal.get('status')!='PASS_SCOPED_SAVED_RESULT_REVIEW' and not terminal.get('status','').startswith('PASS_SCOPED'): raise ValueError('terminal review status')
 return {'status':'PASS_SCOPED_SHARED_SOURCE_ARCHIVE_INTEGRITY','payload_count':len(rows),'plan_pins_checked':len(plan['pins']),'sibling_archives_checked':3,'saved_result_sha256':RESULT_SHA,'analysis_rerun':False,'scope':'Archive, provenance, and receipt integrity only; no angular integration or solver run.'}
def main():
 ap=argparse.ArgumentParser(description=__doc__); ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parent); ap.add_argument('--source-root',type=Path); ap.add_argument('--output',type=Path)
 a=ap.parse_args(); pkg=a.package.resolve(); repo=a.source_root.resolve() if a.source_root else pkg.parents[2]
 out=verify(pkg,repo); text=json.dumps(out,indent=2,sort_keys=True)+'\n'
 if a.output:
  a.output.parent.mkdir(parents=True,exist_ok=True)
  with a.output.open('x') as f:f.write(text)
 print(json.dumps(out,sort_keys=True)); return 0
if __name__=='__main__': raise SystemExit(main())
