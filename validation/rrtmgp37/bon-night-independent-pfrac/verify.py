#!/usr/bin/env python3
"""Standard-library archive and provenance checks for the held-column pfrac result."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math
from pathlib import Path
SIBLING_SHA='b3f839f7b9a64dfc8ee58415dbc11d5d9d20ec31d356f708b124cc029028ba48'
PLAN_SHA='46893f3864ec5e6ab9e68e5b2a9544b496e9119c6a2823bb71e3a47e26dff6dc'
SCRIPT_SHA='71ea81f2cb09abacdd0855cdf56cacb08d3a90e662e6ea8e4fd2fb11dc089493'
RESULT_SHA='67d000a0582de7de935e64951e2e7c6a609b793187646b7162bca1e7cb9a2862'
EXECUTION_SHA='4d69e2d0ff033e6e9fa9b68bf925f724be834eeb432f4b808e8bdb18244239e0'
STATIC_REVIEW_SHA='01cb396ccf49f192b371e24f6ee3f469d07e9e85a8e4e0b85bb1a9b786d57cf4'
TERMINAL_SHA='5938c4062127c5005ddf2360510576711f991731241e52b3964d5833d7602a7f'
DATA_JSON_SHA='c29615af763369684e0f577dfa5b4c369a2e99d9aa644da160ac56f720fd1398'
PIN_FILES={
 'captured_n2_result':'data/captured-n2-result.txt.gz',
 'captured_n2_sidecar':'data/captured-n2-sidecar.txt.gz',
 'held_input':'data/held-input.txt.gz',
 'n2_execution_record':'provenance/n2-execution.json',
 'n2_plan':'provenance/n2-plan.json',
 'n2_runner':'provenance/n2-runner.py',
 'replay_build_plan':'provenance/replay-build-plan.json',
 'replay_build_receipt':'provenance/replay-build-receipt.json',
 'replay_reader_source':'provenance/replay-reader-source.f90',
 'design':'provenance/design.json',
 'parser':'analysis/angular_reference.py',
}
PRODUCTION_KEYS={'production_adapter','production_coefficients','production_frontend','production_kernel','production_constants'}
def sha(b:bytes)->str:return hashlib.sha256(b).hexdigest()
def fs(p:Path)->str:return sha(p.read_bytes())
def finite(x):
 if isinstance(x,float):return math.isfinite(x)
 if isinstance(x,dict):return all(finite(v) for v in x.values())
 if isinstance(x,list):return all(finite(v) for v in x)
 return True
def check_pin_bytes(path:Path,pin:dict,key:str)->bytes:
 b=path.read_bytes()
 if len(b)!=pin['bytes'] or sha(b)!=pin['sha256']:raise ValueError('plan pin mismatch: '+key)
 return b
def verify(package:Path,repo:Path)->dict:
 package=package.resolve();repo=repo.resolve()
 own=json.loads((package/'manifest.json').read_text())
 rows={r['path']:r for r in own['payloads']}
 actual={p.relative_to(package).as_posix() for p in package.rglob('*') if p.is_file() and p.relative_to(package).as_posix()!='manifest.json'}
 if actual!=set(rows) or own.get('payload_count')!=len(rows):raise ValueError('package closed roster mismatch')
 for rel,row in rows.items():
  b=(package/rel).read_bytes()
  if len(b)!=row['size_bytes'] or sha(b)!=row['sha256']:raise ValueError('package payload mismatch: '+rel)
 for key,origin in own['origins'].items():
  b=(package/origin['package_path']).read_bytes()
  if origin['encoding']=='gzip-decompressed-content':b=gzip.decompress(b)
  if len(b)!=origin['origin_size_bytes'] or sha(b)!=origin['origin_sha256']:raise ValueError('copied origin mismatch: '+key)
 sibling=repo/'validation/rrtmgp37/bon-night-common-band-source'
 smbytes=(package/'receipts/sibling-package-manifest.json').read_bytes()
 if sha(smbytes)!=SIBLING_SHA or (sibling/'manifest.json').read_bytes()!=smbytes:raise ValueError('sibling manifest pin mismatch')
 sm=json.loads(smbytes);srows={x['path']:x for x in sm['payloads']}
 sactual={p.relative_to(sibling).as_posix() for p in sibling.rglob('*') if p.is_file() and p.relative_to(sibling).as_posix()!='manifest.json'}
 if sactual!=set(srows):raise ValueError('sibling closed roster mismatch')
 for rel,row in srows.items():
  b=(sibling/rel).read_bytes()
  if len(b)!=row['size_bytes'] or sha(b)!=row['sha256']:raise ValueError('sibling payload mismatch: '+rel)
 planbytes=(package/'analysis/plan.json').read_bytes()
 if sha(planbytes)!=PLAN_SHA:raise ValueError('frozen plan hash mismatch')
 plan=json.loads(planbytes)
 if sha((package/'analysis/analyze.py').read_bytes())!=SCRIPT_SHA:raise ValueError('frozen analyzer hash mismatch')
 if set(plan['pins'])!=set(PIN_FILES)|PRODUCTION_KEYS:raise ValueError('plan pin roster changed')
 for key,pin in plan['pins'].items():
  if key in PRODUCTION_KEYS:
   marker='/WRF/'
   if marker not in pin['path']:raise ValueError('production path mapping invalid: '+key)
   path=repo/'WRF'/pin['path'].split(marker,1)[1]
  else:
   path=package/PIN_FILES[key]
   if key in {'captured_n2_result','captured_n2_sidecar','held_input'}:
    compressed=path.read_bytes();expected_origin=own['origins'][key]
    raw=gzip.decompress(compressed)
    if sha(raw)!=expected_origin['origin_sha256']:raise ValueError('decompressed input origin mismatch: '+key)
    # Analyzer staging consumes the decompressed bytes; attest those bytes to its pin.
    if len(raw)!=pin['bytes'] or sha(raw)!=pin['sha256']:raise ValueError('raw plan pin mismatch: '+key)
    continue
  check_pin_bytes(path,pin,key)
 if set(plan['provenance_only_pins'])!={'replay_executable'}:raise ValueError('provenance-only pin roster')
 staticbytes=(package/'reviews/precalculation-static-review-v1.json').read_bytes()
 if sha(staticbytes)!=STATIC_REVIEW_SHA:raise ValueError('precalculation review pin')
 static=json.loads(staticbytes)
 if static.get('status')!='PASS_SCOPED_PRECALCULATION_ALGORITHM_SOURCE_INDEXING_AND_PINS':raise ValueError('precalculation review status')
 reviewed={(x['group'],x['name']):(x['sha256'],x['size_bytes']) for x in static['verified_pins']}
 for group in ('pins','provenance_only_pins'):
  for key,pin in plan[group].items():
   if reviewed.get((group,key))!=(pin['sha256'],pin['bytes']):raise ValueError('review does not attest '+group+'/'+key)
 resultb=(package/'analysis/result.json').read_bytes()
 if sha(resultb)!=RESULT_SHA:raise ValueError('result pin mismatch')
 result=json.loads(resultb)
 if result.get('status')!='PASS_SCOPED' or result.get('plan_sha256')!=PLAN_SHA or result.get('script_sha256')!=SCRIPT_SHA:raise ValueError('result provenance linkage')
 if result.get('pins')!=plan['pins'] or result.get('scope')!=plan['scope'] or not finite(result):raise ValueError('result content/pin check')
 exb=(package/'receipts/math-execution.json').read_bytes()
 if sha(exb)!=EXECUTION_SHA:raise ValueError('execution receipt pin')
 ex=json.loads(exb)
 if ex.get('exit_code')!=0 or ex.get('result_sha256')!=RESULT_SHA or ex.get('plan_sha256')!=PLAN_SHA or ex.get('script_sha256')!=SCRIPT_SHA:raise ValueError('execution/result linkage')
 launch=json.loads((package/'receipts/math-launched.json').read_text())
 if launch.get('pid')!=ex.get('pid') or launch.get('script_sha256')!=SCRIPT_SHA or launch.get('plan_sha256')!=PLAN_SHA:raise ValueError('launch record linkage')
 rb=(package/'reviews/independent-result-readback-v1.json').read_bytes()
 rd=json.loads(rb)
 if rd.get('status')!='PASS_SCOPED' or rd.get('saved_arrays_only') is not True or rd.get('additional_calculation_calls')!=0 or rd.get('result_sha256')!=RESULT_SHA or rd.get('execution_sha256')!=EXECUTION_SHA:raise ValueError('independent readback linkage')
 tb=(package/'reviews/terminal-review-v1.json').read_bytes()
 if sha(tb)!=TERMINAL_SHA or not json.loads(tb).get('status','').startswith('PASS_SCOPED'):raise ValueError('terminal review status/pin')
 rdata=repo/'WRF/external/rte_rrtmgp/DATA.json'
 if fs(rdata)!=DATA_JSON_SHA:raise ValueError('tracked RTE DATA.json changed')
 meta=json.loads(rdata.read_text());coeff=next(x for x in meta['files'] if x['filename']=='rrtmgp-gas-lw-g128.nc')
 cp=plan['pins']['production_coefficients']
 if (coeff['sha256'],coeff['size_bytes'])!=(cp['sha256'],cp['bytes']):raise ValueError('coefficient DATA.json provenance mismatch')
 return {'status':'PASS_SCOPED_INDEPENDENT_PFRAC_ARCHIVE_INTEGRITY','payload_count':len(rows),'analysis_rerun':False,
  'source_pins_checked':len(PRODUCTION_KEYS),'required_plan_pins_checked':len(plan['pins']),
  'provenance_only_binary_distributed':False,'result_sha256':RESULT_SHA,'scope':plan['scope'],
  'limitations':'Integrity/provenance only; no pfrac recalculation, compiled RTE, WRF, forecast, or accuracy verdict.'}
def main():
 ap=argparse.ArgumentParser(description=__doc__);ap.add_argument('--package',type=Path,default=Path(__file__).resolve().parent);ap.add_argument('--source-root',type=Path);ap.add_argument('--output',type=Path)
 a=ap.parse_args();pkg=a.package.resolve();repo=a.source_root.resolve() if a.source_root else pkg.parents[2]
 out=verify(pkg,repo);text=json.dumps(out,indent=2,sort_keys=True)+'\n'
 if a.output:
  a.output.parent.mkdir(parents=True,exist_ok=True)
  with a.output.open('x') as f:f.write(text)
 print(json.dumps(out,sort_keys=True));return 0
if __name__=='__main__':raise SystemExit(main())
