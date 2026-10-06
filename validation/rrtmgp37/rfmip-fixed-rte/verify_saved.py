#!/usr/bin/env python3
"""Verify the closed saved fixed-RTE evidence package; launches no model or solver."""
from __future__ import annotations
import argparse,gzip,hashlib,json,math,struct,subprocess,sys,tempfile
from pathlib import Path
NLEV=61

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def check_file(p,rec):
 p=Path(p)
 if not p.is_file():raise RuntimeError(f'missing file: {p}')
 if p.stat().st_size!=rec['size_bytes'] or sha(p)!=rec['sha256']:raise RuntimeError(f'pin mismatch: {p}')
def main():
 ap=argparse.ArgumentParser(description=__doc__)
 ap.add_argument('--package-dir',type=Path,default=Path(__file__).resolve().parent)
 a=ap.parse_args(); pkg=a.package_dir.resolve(); manifest_path=pkg/'package-manifest.json'
 m=json.loads(manifest_path.read_text()); repo=Path(__file__).resolve().parents[3]
 if m.get('schema')!='RFMIP_FIXED_RTE_EVIDENCE_PACKAGE_V1':raise RuntimeError('package schema mismatch')
 if m.get('package_root')!='validation/rrtmgp37/rfmip-fixed-rte':raise RuntimeError('package location identity mismatch')
 # Closed file set, including the verbatim harness kept at the requested WRF test path.
 expected=set(m['files'])
 actual=set()
 for p in pkg.rglob('*'):
  if p.is_file() and p!=manifest_path:
   actual.add((Path(m['package_root'])/p.relative_to(pkg)).as_posix())
 if actual!={p for p in expected if p.startswith(m['package_root']+'/')}:
  missing=sorted({p for p in expected if p.startswith(m['package_root']+'/')}-actual)
  extra=sorted(actual-{p for p in expected if p.startswith(m['package_root']+'/')})
  raise RuntimeError(f'package file closure mismatch missing={missing} extra={extra}')
 for rel,rec in m['files'].items():check_file(repo/rel,rec)
 # Validate terminal receipt and actual run's five saved child statuses.
 epath=pkg/'execution-v4/execution.json'; ex=json.loads(epath.read_text())
 if ex.get('status')!='PASS_SCOPED_FIXED_RTE_BASELINE_REPRODUCTION':raise RuntimeError('execution is not scoped PASS')
 if ex.get('gas_optics_calls')!=0 or ex.get('model_forecasts')!=0 or ex.get('rte_calls_expected')!=40:raise RuntimeError('execution scope mismatch')
 if len(ex.get('children',[]))!=5 or any(c.get('returncode')!=0 or not c.get('reaped') or c.get('timed_out') for c in ex['children']):raise RuntimeError('child terminal status mismatch')
 if ex.get('strict_rfmip_gate_changed') is not False or ex.get('physical_accuracy_claim') is not False:raise RuntimeError('strict/accuracy claim changed')
 # Verify portable compressed subset payloads, record keys, finite values and common source.
 sm=json.loads((pkg/'inputs/source-subset-manifest.json').read_text())
 keys=[tuple(map(int,x.split())) for x in (pkg/'inputs/profiles20.txt').read_text().splitlines()]
 if [list(k) for k in keys]!=m['keys_one_based'] or len(keys)!=20 or keys!=sorted(keys) or len(set(keys))!=20:raise RuntimeError('profile selector mismatch')
 payloads={}
 nvals={'current_optics':60*224*3,'historical_optics':60*224*3,'current_source_post':224,'historical_source_post':224,'current_solver':122,'current_written':122,'historical_solver':122,'historical_written':122}
 if set(sm['streams'])!=set(nvals):raise RuntimeError('eight capture stream roster mismatch')
 for name,nval in nvals.items():
  z=pkg/'inputs/streams'/f'{name}.bin.gz'; raw=gzip.decompress(z.read_bytes())
  expected=sm['streams'][name]
  if len(raw)!=expected['size_bytes'] or hashlib.sha256(raw).hexdigest()!=expected['sha256']:raise RuntimeError(f'raw stream mismatch: {name}')
  recsize=8+8*nval
  if len(raw)!=20*recsize:raise RuntimeError(f'wrong stream size: {name}')
  for i,key in enumerate(keys):
   off=i*recsize
   if struct.unpack_from('<ii',raw,off)!=key:raise RuntimeError(f'wrong stream key/order: {name} {i}')
   if not all(math.isfinite(v[0]) for v in struct.iter_unpack('<d',raw[off+8:off+recsize])):raise RuntimeError(f'nonfinite stream record: {name} {key}')
  payloads[name]=raw
 if payloads['current_source_post']!=payloads['historical_source_post']:raise RuntimeError('source_post arrays differ')
 # Repeat the saved-only stream comparison; current arm is exact, historical arm descriptive.
 cmd=[sys.executable,'-B',str(pkg/'validate_replay.py'),'--profiles',str(pkg/'inputs/profiles20.txt'),
  '--current-solver',str(pkg/'execution-v4/replay_current_solver.bin'),'--current-written',str(pkg/'execution-v4/replay_current_written.bin'),
  '--historical-solver',str(pkg/'execution-v4/replay_historical_solver.bin'),'--historical-written',str(pkg/'execution-v4/replay_historical_written.bin'),
  '--current-solver-reference',str(pkg/'references/current_solver.bin'),'--current-written-reference',str(pkg/'references/current_written.bin'),
  '--historical-solver-reference',str(pkg/'references/historical_solver.bin'),'--historical-written-reference',str(pkg/'references/historical_written.bin')]
 p=subprocess.run(cmd,cwd='/tmp',text=True,capture_output=True,check=False)
 if p.returncode!=0:raise RuntimeError(f'saved validator failed rc={p.returncode}: {p.stderr}')
 validation=json.loads(p.stdout)
 if validation!=ex.get('validation_result'):raise RuntimeError('saved validator output differs from terminal receipt')
 # Reproduce analysis bytes into /tmp and require byte identity to the included JSON.
 with tempfile.TemporaryDirectory(prefix='rfmip-fixed-rte-verify-') as td:
  generated=Path(td)/'analysis.json'
  q=subprocess.run([sys.executable,'-B',str(pkg/'analyze_fixed_rte.py'),'--output',str(generated)],cwd='/tmp',text=True,capture_output=True,check=False)
  if q.returncode!=0:raise RuntimeError(f'analysis regeneration failed rc={q.returncode}: {q.stderr}')
  expected_analysis=(pkg/'fixed-rte-component-analysis.json').read_bytes()
  if generated.read_bytes()!=expected_analysis:raise RuntimeError('analysis JSON is not byte-reproducible')
 analysis=json.loads((pkg/'fixed-rte-component-analysis.json').read_text())
 if analysis.get('status')!='PASS_SCOPED_DECOMPOSITION_NOT_STRICT_PASS':raise RuntimeError('analysis scope/status mismatch')
 if analysis['all_level_component_metrics']['closure']['n']!=2440 or analysis['all_level_component_metrics']['closure']['max_abs']!=0:raise RuntimeError('component closure mismatch')
 if analysis['strict_failure_cells']['count']!=21 or analysis['strict_failure_cells']['threshold_changed'] is not False:raise RuntimeError('strict-cell analysis mismatch')
 print(json.dumps({'status':'PASS_SAVED_PACKAGE_INTEGRITY_AND_REPRODUCIBILITY','fixed_rte_execution_status':ex['status'],'profile_count':20,'subset_stream_count':8,'analysis_cells':2440,'analysis_bytes_reproduced':True,'strict_gate_changed':False,'solver_or_model_calls':0},sort_keys=True))
 return 0
if __name__=='__main__':raise SystemExit(main())
