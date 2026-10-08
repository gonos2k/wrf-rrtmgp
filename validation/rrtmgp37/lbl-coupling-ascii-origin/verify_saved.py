#!/usr/bin/env python3
"""Replay decoded-source facts against actual included TAPE3; no raw ASCII read."""
from pathlib import Path
import json,gzip,hashlib,importlib.util,sys,subprocess
BASE=Path(__file__).resolve().parent
spec=importlib.util.spec_from_file_location('upstream_core',BASE/'verify_core.py');core=importlib.util.module_from_spec(spec);spec.loader.exec_module(core)
def main():
    manifest=json.loads((BASE/'manifest.json').read_text());actual={str(p.relative_to(BASE)) for p in BASE.rglob('*') if p.is_file() and p!=BASE/'manifest.json' and '__pycache__' not in p.parts}
    core.require(len(manifest['files'])==len(actual) and {x['path'] for x in manifest['files']}==actual,'manifest roster')
    core.require(manifest['production_accepted'] is False,'manifest gate')
    for x in manifest['files']:
        p=BASE/x['path'];core.require(p.stat().st_size==x['bytes'] and hashlib.sha256(p.read_bytes()).hexdigest()==x['sha256'],'package bytes')
    parent=BASE.parent/'lbl-coupling-generation';subprocess.run([sys.executable,'-I','-S',str(parent/'verify_saved.py')],check=True)
    raw=gzip.decompress((parent/'excerpts/line_data.bin.gz').read_bytes())
    result=core.verify(json.loads((BASE/'source-fields.json').read_text()),json.loads((BASE/'readback.json').read_text()),raw)
    core.require(result==json.loads((BASE/'result.json').read_text()),'saved joins')
    print(json.dumps(result))
if __name__=='__main__':main()
