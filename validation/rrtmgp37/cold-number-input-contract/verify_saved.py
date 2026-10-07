#!/usr/bin/env python3
"""Sealed package integrity and receipt scope; no NetCDF/numerical replay."""
import gzip
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent

def require(ok, message):
    if not ok:
        raise ValueError(message)

def verify():
    m = json.loads((ROOT/'manifest.json').read_text())
    roster = {r['path'] for r in m['payloads']}
    actual = {p.relative_to(ROOT).as_posix() for p in ROOT.rglob('*')
              if p.is_file() and p != ROOT/'manifest.json'}
    require(actual == roster and len(roster) == len(m['payloads']), 'payload roster mismatch')
    for row in m['payloads']:
        p = ROOT/row['path']
        require(not p.is_symlink() and p.resolve().is_relative_to(ROOT), 'unsafe payload')
        data = p.read_bytes()
        require(len(data) == row['size_bytes'] and hashlib.sha256(data).hexdigest() == row['sha256'], 'payload hash mismatch')
    require(m['production_accepted'] is False and m['completed_scoped']==15 and m['physical_remaining']==7, 'acceptance scope changed')
    r = json.loads((ROOT/'runtime/receipt.json').read_text())
    require(r['status']=='PASS' and r['production_accepted'] is False and r['physical_units_approved'] is False, 'runtime scope changed')
    require(len(r['commands'])==7 and all(c['status']=='TERMINAL' and c['actual_returncode']==0 for c in r['commands']), 'runtime children failed')
    mappings = json.loads((ROOT/'runtime/file-mapping.json').read_text())
    by_path = {row['original_path']:row for row in mappings}
    require(len(by_path)==len(mappings), 'duplicate mapped input')
    for row in mappings:
        data=gzip.decompress((ROOT/row['archive_path']).read_bytes())
        require(len(data)==row['size_bytes'] and hashlib.sha256(data).hexdigest()==row['uncompressed_sha256'], 'uncompressed hash mismatch')
    for arm in r['arms'].values():
        for key in ('input','log','history','namelist'):
            if key in arm:
                row=by_path[arm[key]['path']]
                require(row['uncompressed_sha256']==arm[key]['sha256'] and row['size_bytes']==arm[key]['size_bytes'], 'receipt mapping mismatch')
        if 'joined_checks' in arm:
            c=arm['joined_checks']
            require(c['input_number_variables']==['QNCCN','QNCLOUD','QNRAIN'] and c['input_number_layers']==59 and c['input_number_comparison']=='REAL32_BITS', 'three-number contract absent')
    n=r['input_contract_negative_controls']
    require(n['status']=='PASS' and n['rejected_count']==7 and len(n['rejections'])==7 and n['additional_model_runs']==0 and n['original_input_unchanged'], 'negative controls incomplete')
    print('PASS_SCOPED_COLD_NUMBER_PACKAGE_INTEGRITY; no independent physical approval')

if __name__=='__main__':
    verify()
