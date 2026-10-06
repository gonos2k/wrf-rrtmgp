#!/usr/bin/env python3
"""Portable integrity verification for the finite-band Planck evidence archive."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from pathlib import Path
SIBLING_MANIFEST_SHA256='b3f839f7b9a64dfc8ee58415dbc11d5d9d20ec31d356f708b124cc029028ba48'
PRIVATE_RESULT_SHA256='53e9513bf41a5e5054906bc7ee4ebbc9b9e9c83890d61ac18f9cbdd6634d44df'
FROZEN={
 'analysis/plan.json':'0e2318115830885c995f1049cd784920304ba2f589e2079537c5346f3541e475',
 'analysis/analyze.py':'7c9fa552b81f2be0f673e1f01a6b33531db6bf023d7bbc5121c6e8e466694b51',
 'analysis/precalculation-pins-v1.json':'07818fa437bbd48abf809f76637af6260fa3387fe1eef48cfc1ecdd37ed8d5ac',
 'analysis/precalculation-pins-v2.json':'d6f288d2168219f8851a79f3b7bf3a5a137463d52eb3ef7d02bbbf0452c26fbf',
 'design/v1/plan.json':'abe0b6a96eb353e09cd7370c71405bed8399433b7a9f275f467c12d1976f2c79',
 'design/v2/plan.json':'013cf8f99e7d3c02d3a0de8f4b47fa0b596e6d74538d88f4141c885d9e5bc587',
 'analysis/angular_reference.py':'a64dfa9f3ff90cc788028c1cb0f5ab4d0be1316c49ef74e833b8dddc4eb5cb48',
 'analysis/legacy_lw_replay.py':'691497decf3992435ada71b6af84e25e88773f534f385c1a56050e370a1aea00',
 'reviews/static-review-v1.json':'68e5a9cf025a60c56111192555e8b06797f69d2a7136ea1d9a12460d8399eb08',
 'reviews/terminal-review-v1.json':'828ecc354085e8e3a6623d35634004170cf5744b34e45ba76a534cf196c99710',
 'reviews/result-readback-v1.json':'b927f5fa297dac62a68dcdc2f28b5e29a1b70b0f2a5ae9f52106f59ab4aaa46d',
 'reviews/environment-v1.json':'5afef7c5bd30252313f6f34a9ef34ac076addce4657668dd11664568da4b5225',
 'receipts/driver.log':'', 'receipts/execution.json':'', 'receipts/launched.json':'',
}
DATA={
 'data/legacy-lw-packet.txt.gz':('legacy-lw-packet.txt.gz','7513b105ae08de1fceed56b833d25133bcc097929f2bcddfcd9b84c4e50221db','bd614b57362b48ab8e00b179fc3464925b9c49a8eef0a472489f87fd89e15c7f'),
 'data/matched-gp-input.txt.gz':('matched-gp-input.txt.gz','d58e42fcac9b8d2e7efb8b6d615e1de8c1ab1f91ba735c6a3674ca8c0b99bd79','292f9569b059c373c9cb14f1574cb8835627331574592a19d641ef07c21ec918'),
 'data/gp-lw-transport.txt.gz':('gp-lw-transport.txt.gz','4e2b1ed21315317e7621daae250c2b9e1d668bde3a7beeede7bfa49a3ba4f353','bb53daf55ea9b6f91c9d0dbc4f132eff11b3ab76fd278bacb327571a1642e792')}
def sha(b):return hashlib.sha256(b).hexdigest()
def file_sha(p):return sha(Path(p).read_bytes())
def finite_tree(x):
 if isinstance(x,float):return math.isfinite(x)
 if isinstance(x,dict):return all(finite_tree(v) for v in x.values())
 if isinstance(x,list):return all(finite_tree(v) for v in x)
 return True
def verify_package(package:Path,repo:Path)->dict:
 package,repo=package.resolve(),repo.resolve()
 archive=json.loads((package/'manifest.json').read_text())
 rows={x['path']:x for x in archive['payloads']}
 actual={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() and p.relative_to(package).as_posix()!='manifest.json'}
 if actual!=set(rows):raise ValueError('closed archive roster mismatch')
 if archive.get('payload_count')!=len(rows):raise ValueError('archive payload count mismatch')
 for rel,row in rows.items():
  b=(package/rel).read_bytes()
  if len(b)!=row['size_bytes'] or sha(b)!=row['sha256']:raise ValueError('archive payload hash mismatch '+rel)
 # Cross-check exact source-copy origins recorded in the manifest.
 for key,origin in archive['origins'].items():
  b=(package/origin['package_path']).read_bytes()
  if origin['encoding']=='gzip-decompressed-content':b=gzip.decompress(b)
  if len(b)!=origin['origin_size_bytes'] or sha(b)!=origin['origin_sha256']:
   raise ValueError('origin hash mismatch '+key)
 sibling=repo/'validation/rrtmgp37/bon-night-common-band-source'
 sibling_manifest=(package/'receipts/sibling-package-manifest.json').read_bytes()
 if sha(sibling_manifest)!=SIBLING_MANIFEST_SHA256:raise ValueError('archived sibling manifest hash changed')
 live_manifest=(sibling/'manifest.json').read_bytes()
 if live_manifest!=sibling_manifest:raise ValueError('live PR90 sibling manifest differs from archived pin')
 sibman=json.loads(sibling_manifest); sibrows={x['path']:x for x in sibman['payloads']}
 sibactual={p.relative_to(sibling).as_posix() for p in sibling.rglob('*') if p.is_file() and p.relative_to(sibling).as_posix()!='manifest.json'}
 if sibactual!=set(sibrows):raise ValueError('sibling package roster mismatch')
 for rel,row in sibrows.items():
  b=(sibling/rel).read_bytes()
  if len(b)!=row['size_bytes'] or sha(b)!=row['sha256']:raise ValueError('sibling payload mismatch '+rel)
 for rel,digest in FROZEN.items():
  b=(package/rel).read_bytes()
  if digest and sha(b)!=digest:raise ValueError('frozen artifact hash mismatch '+rel)
 for rel,(sibling_name,compressed_sha,origin_sha) in DATA.items():
  b=(package/rel).read_bytes()
  if b!=(sibling/'data'/sibling_name).read_bytes() or sha(b)!=compressed_sha:raise ValueError('input archive differs from verified sibling '+rel)
  if sha(gzip.decompress(b))!=origin_sha:raise ValueError('input origin mismatch '+rel)
 for rel in ('analysis/angular_reference.py','analysis/legacy_lw_replay.py'):
  if (package/rel).read_bytes()!=(sibling/rel).read_bytes():raise ValueError('helper differs from sibling '+rel)
 plan_bytes=(package/'analysis/plan.json').read_bytes();plan=json.loads(plan_bytes)
 base='build/udm37-bon-common-band-source-pr-work/';source_keys=('coefficients','gp_kernel','gp_frontend','gp_loader','legacy_source');source_checks={}
 for key in source_keys:
  pin=plan['pins'][key];name=pin['path']
  if not name.startswith(base):raise ValueError('unexpected frozen source pin '+key)
  path=repo/Path(name[len(base):]);b=path.read_bytes()
  if len(b)!=pin['bytes'] or sha(b)!=pin['sha256']:raise ValueError('tracked source/coefficient mismatch '+key)
  source_checks[key]=pin['sha256']
 result_bytes=(package/'analysis/result.json').read_bytes()
 if sha(result_bytes)!=PRIVATE_RESULT_SHA256:raise ValueError('private numerical result hash mismatch')
 result=json.loads(result_bytes)
 if result.get('plan_sha256')!=sha(plan_bytes):raise ValueError('result/plan SHA linkage')
 if result.get('script_sha256')!=sha((package/'analysis/analyze.py').read_bytes()):raise ValueError('result/analyzer SHA linkage')
 if result.get('pins')!=plan.get('pins'):raise ValueError('result/frozen plan pin map differs')
 if not finite_tree(result) or len(result.get('bands',[]))!=11:raise ValueError('result finite/profile roster check')
 if [b.get('band') for b in result['bands']]!=list(range(3,14)):raise ValueError('common-band result labels')
 ex=json.loads((package/'receipts/execution.json').read_text());launch=json.loads((package/'receipts/launched.json').read_text())
 if ex.get('status')!='PASS_EXECUTION' or ex.get('returncode')!=0 or ex.get('result_sha256')!=PRIVATE_RESULT_SHA256:raise ValueError('execution receipt does not attest archived result')
 if launch.get('pid')!=ex.get('pid') or launch.get('script_sha256')!=sha((package/'analysis/analyze.py').read_bytes()):raise ValueError('launch/execution linkage')
 readback=json.loads((package/'reviews/result-readback-v1.json').read_text())
 if readback.get('result_sha256')!=PRIVATE_RESULT_SHA256:raise ValueError('independent result readback linkage')
 result_origin=json.loads((package/'receipts/result-origin-v1.json').read_text())
 if result_origin.get('sha256')!=PRIVATE_RESULT_SHA256 or result_origin.get('status')!='ROOT_RESULT_AND_TERMINAL_REVIEW_AVAILABLE':raise ValueError('result origin receipt linkage')
 for rel in ('reviews/static-review-v1.json','reviews/terminal-review-v1.json'):
  review=json.loads((package/rel).read_text())
  if review.get('blocking_findings') not in ([],None):raise ValueError('review has blocking findings: '+rel)
 terminal=json.loads((package/'reviews/terminal-review-v1.json').read_text())
 if not str(terminal.get('status','')).startswith('PASS_SCOPED'):raise ValueError('terminal review status')
 data_json=repo/'WRF/external/rte_rrtmgp/DATA.json'
 if sha(data_json.read_bytes())!='c29615af763369684e0f577dfa5b4c369a2e99d9aa644da160ac56f720fd1398':raise ValueError('tracked RTE DATA.json pin changed')
 data_meta=json.loads(data_json.read_text())
 coeff=next(x for x in data_meta['files'] if x['filename']=='rrtmgp-gas-lw-g128.nc')
 if coeff['sha256']!=plan['pins']['coefficients']['sha256'] or coeff['size_bytes']!=plan['pins']['coefficients']['bytes']:
  raise ValueError('RTE DATA.json coefficient provenance mismatch')
 return {'status':'PASS_PLANCK_EVIDENCE_PACKAGE_INTEGRITY','payload_count':len(rows),
  'analysis_rerun':False,'source_coefficient_checks':source_checks,'sibling_manifest_sha256':SIBLING_MANIFEST_SHA256,
  'result_sha256':PRIVATE_RESULT_SHA256,'scope':'Archive/provenance checks only; no Planck integration or radiative-transfer recurrence.'}

def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parent);ap.add_argument('--source-root',type=Path);ap.add_argument('--output',type=Path)
 a=ap.parse_args();package=a.package.resolve();repo=a.source_root.resolve() if a.source_root else package.parents[2]
 out=verify_package(package,repo);data=json.dumps(out,indent=2,sort_keys=True)+'\n'
 if a.output:
  a.output.parent.mkdir(parents=True,exist_ok=True)
  with a.output.open('x') as f:f.write(data)
 print(json.dumps(out,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
