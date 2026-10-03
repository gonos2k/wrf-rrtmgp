#!/usr/bin/env python3
"""Verify the compact evidence package and its internal receipt/index links."""
import csv, hashlib, json, sys
from pathlib import Path
ROOT=Path(__file__).resolve().parent

def sha(p):
 h=hashlib.sha256()
 with p.open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def main():
 idx=json.loads((ROOT/'artifact-index.json').read_text())
 for row in idx['files']:
  p=ROOT/row['path']
  assert p.is_file(),f'missing {row["path"]}'
  assert p.stat().st_size==row['bytes'],f'byte count mismatch {row["path"]}'
  assert sha(p)==row['sha256'],f'hash mismatch {row["path"]}'
 rec=json.loads((ROOT/'execution/receipt.json').read_text())
 ver=json.loads((ROOT/'execution/independent-verification.json').read_text())
 assert rec['status']=='PASS_32_SEED_PAIRED_REPLAY'
 exe=json.loads((ROOT/'execution/executable-provenance.json').read_text())
 assert exe['status']=='BINARY_NOT_BUNDLED_SCRATCH_RETAINED'
 assert exe['binary_sha256']==rec['hashes']['executable']
 assert exe['binary_bytes']>0 and exe['target']=='reference_column'
 assert sha(ROOT/'execution/reference_column_seed_override.f90')==rec['seed_override_source_sha256']
 assert sha(ROOT/'execution/run_seed_ensemble_bounded.py')==rec['runner_sha256']
 assert json.loads((ROOT/'execution/root-independent-paired-recheck.json').read_text())['status'].upper().startswith('PASS')
 assert sha(ROOT/'captures/sw.input')==rec['hashes']['capture']['SW']['input']
 assert ver['status']=='INDEPENDENT_VERIFY_PASS' and ver['validated_result_pairs']==256
 assert ver['result_file_count']==322
 with (ROOT/'execution/per-seed-paired-deltas.csv').open(newline='') as f: rows=list(csv.DictReader(f))
 assert len(rows)==256
 assert set(r['mode'] for r in rows)=={'cf0_uniform','grid_uniform','ice160','ice140'}
 assert set(r['phase'] for r in rows)=={'LW','SW'}
 for ph,stem in (('LW','lw'),('SW','sw')):
  for suffix in ('input','raw','result'):
   assert sha(ROOT/f'captures/{stem}.{suffix}')==rec['hashes']['capture'][ph][suffix]
 for mode in ('cf0_uniform','grid_uniform','ice160','ice140'):
  for ph,stem in (('LW','lw'),('SW','sw')):
   assert sha(ROOT/f'sidecars/{stem}-{mode}.sidecar')==rec['hashes']['sidecars'][ph][mode]
 print(f"PASS {len(idx['files'])} package files; {len(rows)} paired variant rows; receipt and capture/sidecar hashes consistent")
if __name__=='__main__':main()
