#!/usr/bin/env python3
"""Verify the evidence index, source hashes, receipts, and retained execution scripts."""
import hashlib,json
from pathlib import Path
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
def sha(path):
 h=hashlib.sha256()
 with Path(path).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
idx=json.loads((HERE/'artifact-index.json').read_text())
for name,meta in idx.items():
 p=HERE/name
 if not p.is_file() or p.stat().st_size!=meta['bytes'] or sha(p)!=meta['sha256']:
  raise SystemExit('artifact index mismatch: '+name)
sources=json.loads((HERE/'source-sha256.json').read_text())
for item in sources['files']:
 p=ROOT/item['path']
 if not p.is_file() or p.stat().st_size!=item['bytes'] or sha(p)!=item['sha256']:
  raise SystemExit('source hash mismatch: '+item['path'])
execs=json.loads((HERE/'execution-scripts.json').read_text())
checks=[('stage_integrated_source.py','original_path','original_sha256'),('build_serial_em_real.sh','executed_path','executed_sha256'),('run_integrated_candidate.py','executed_path','executed_sha256')]
if sha(HERE/'summarize_phase_path.py')!=execs['summarize_phase_path.py']['sha256']:
 raise SystemExit('summary parser hash mismatch')
for name,path_key,hash_key in checks:
 rec=execs[name]
 if sha(HERE/name)!=rec['sha256'] or sha(rec[path_key])!=rec[hash_key] or rec['sha256']!=rec[hash_key]:
  raise SystemExit('execution script provenance mismatch: '+name)
summary=json.loads((HERE/'phase-path-validation-summary.json').read_text())
for phase in ('ra37','ra4'):
 rec=json.loads((HERE/f'{phase}-run-receipt.json').read_text())
 if rec['status']!='COMPLETE_BITWISE_PASS' or rec['comparison_status']!='BITWISE_PASS':
  raise SystemExit(phase+' receipt is not PASS')
 if sha(Path(rec['run'])/'wrf.stdout.log')!=rec['log_sha256']:
  raise SystemExit(phase+' full stdout hash mismatch')
 if summary['cases'][phase]['comparison_status']!='BITWISE_PASS':raise SystemExit(phase+' summary mismatch')
print(f'PASS evidence artifacts={len(idx)} source_files={len(sources["files"])} two_run_receipts=verified scripts=verified')
