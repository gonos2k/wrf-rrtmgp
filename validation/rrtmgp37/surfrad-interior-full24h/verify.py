#!/usr/bin/env python3
"""Offline closed-roster, receipt linkage, and exact SURFRAD reanalysis."""
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def digest(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    root=Path(__file__).resolve().parent
    m=json.loads((root/'manifest.json').read_text())
    roster={p.relative_to(root).as_posix() for p in root.rglob('*')
            if p.is_file() and '__pycache__' not in p.parts and p.name!='manifest.json'}
    assert roster==set(m['files']), 'closed evidence roster differs'
    for rel, item in m['files'].items():
        p=root/rel
        assert p.stat().st_size==item['bytes'] and digest(p)==item['sha256'], rel
    model=json.loads((root/'model-extract.json').read_text())
    inventory=json.loads((root/'runtime-inventory.json').read_text())
    assert model['new_model_solver_build_calls']==0
    for arm, rad in [('ra4',4),('ra37',37)]:
        a=model['arms'][arm]
        receipt=root/'receipts'/f'{arm}-execution-receipt-v1.json'
        stage=root/'receipts'/f'{arm}-stage-receipt-v1.json'
        r=json.loads(receipt.read_text());s=json.loads(stage.read_text())
        assert digest(receipt)==a['execution_receipt']['sha256']
        assert digest(stage)==a['stage_receipt']['sha256']
        assert r['status']==f'PASS_{arm.upper()}_24H' and r['actual_model_invocations']==1
        assert r['model']['returncode']==0 and r['model']['model_completed'] and not r['model']['timed_out']
        assert a['history']['sha256']==r['outputs']['history']['file']['sha256']
        assert a['history']['sha256']==inventory['latest_completed_pair']['arms'][arm]['history']['sha256']
        assert a['executable']['sha256']==inventory['latest_completed_pair']['arms'][arm]['executable']['sha256']
        assert hashlib.sha256(a['namelist'].encode()).hexdigest()==a['namelist_sha256']==s['case']['snapshot']['namelist']['sha256']
        assert a['runtime']['ranks']==4 and a['runtime']['omp_threads']==1
        assert a['attributes']['MP_PHYSICS']==27 and a['attributes']['RA_LW_PHYSICS']==a['attributes']['RA_SW_PHYSICS']==rad
        assert len(a['Times'])==25
        for station, grid in a['grid'].items():
            assert grid['cells_to_nearest_edge']>=5 and not grid['inside_boundary_zone']
            assert all(len(v)==25 for v in a['accumulators_J_m2'][station].values())
        for name in ['wrfinput','wrfbdy']:
            assert a[name]['sha256']==model['arms']['ra4'][name]['sha256']
    for arm in model['arms'].values():
        assert arm['build_receipt']['sha256']==digest(root/'receipts/original-build-result.json')
    assert json.loads((root/'receipts/original-build-result.json').read_text())['status']=='BUILD_FAIL_PRESERVED'
    assert json.loads((root/'receipts/posthoc-build-attestation.json').read_text())['status']=='BUILD_PASS_POSTHOC_ATTESTED'
    with tempfile.TemporaryDirectory() as tmp:
        out=Path(tmp)
        for name in ['raw','metadata']:shutil.copytree(root/name,out/name)
        for name in ['model-extract.json','download_manifest.json']:shutil.copyfile(root/name,out/name)
        subprocess.run([sys.executable,str(root/'analyze.py'),'--root',str(out)],check=True,capture_output=True)
        for name in ['results.json','hourly-comparison.csv']:
            assert digest(out/name)==digest(root/name), 'reanalysis differs: '+name
    subprocess.run([sys.executable,str(root/'test_verify_surfrad.py')],check=True,capture_output=True)
    control=subprocess.run([sys.executable,str(root/'test_hourly_contract.py')],check=True,capture_output=True,text=True)
    assert json.loads(control.stdout)==json.loads((root/'hourly-controls.json').read_text())
    print(json.dumps({'status':'PASS_SCOPED_EVIDENCE_AND_EXACT_REANALYSIS','payload_files':len(roster),
                      'new_model_solver_build_calls':0,'new_downloads':0,
                      'scope':'packaged raw-observation reduction, extracted-value analysis and preserved receipt linkage'}))


if __name__=='__main__':main()
