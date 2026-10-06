#!/usr/bin/env python3
"""Verify a closed evidence roster and reanalyze observations/extracted values."""
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    root=Path(__file__).resolve().parent
    m=json.loads((root/'manifest.json').read_text())
    actual={p.relative_to(root).as_posix() for p in root.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.json'}
    assert actual==set(m['files']), 'closed roster differs'
    for rel, pin in m['files'].items():
        p=root/rel
        assert p.stat().st_size==pin['bytes'] and digest(p)==pin['sha256'], rel
    download=json.loads((root/'download-manifest.json').read_text())
    for row in download['items']:
        if row.get('status')==200:
            assert digest(root/row['path'])==row['sha256']
        else:
            assert 'HTTPError 403' in row['error'] and not (root/row['path']).exists()
    model=json.loads((root/'model-extract.json').read_text())
    assert digest(root/'forecast-execution-receipt.json')==model['execution_receipt_sha256']
    assert digest(root/'forecast-plan.json')==model['plan_sha256']
    for arm, rad in [('ra4',4),('ra37',37)]:
        row=model['arms'][arm]
        assert hashlib.sha256(row['namelist'].encode()).hexdigest()==row['namelist_sha256']
        assert row['attributes']=={'MP_PHYSICS':27,'RA_SW_PHYSICS':rad,'RA_LW_PHYSICS':rad}
        assert len(row['times_utc'])==len(row['ACSWDNB_J_m2'])==49
        assert row['grid']['cells_to_nearest_edge']==2 and row['grid']['inside_boundary_zone']
    with tempfile.TemporaryDirectory() as tmp:
        out=Path(tmp)
        shutil.copytree(root/'raw',out/'raw')
        shutil.copyfile(root/'model-extract.json',out/'model-extract.json')
        subprocess.run([sys.executable,str(root/'analyze.py'),'--root',str(out)],check=True,capture_output=True)
        for file in ['comparison-results.json','hourly-comparison.csv']:
            assert digest(out/file)==digest(root/file), 'reanalysis differs: '+file
    subprocess.run([sys.executable,str(root/'test_time_qc_contract.py')],check=True,capture_output=True)
    print(json.dumps({'status':'PASS_SCOPED_EVIDENCE_AND_REANALYSIS','payload_files':len(actual),
                      'new_model_solver_build_calls':0,'scope':'observation processing and extracted-value analysis only'}))


if __name__=='__main__':main()
