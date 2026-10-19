#!/usr/bin/env python3
"""Verify retained contributions/source terms without launching scientific models."""
from functools import lru_cache
import gzip
import hashlib
import importlib.util
import json
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def verify():
    expected=json.loads((B/'manifest.json').read_text())['files']
    roster={str(p.relative_to(B)) for p in (B/'saved').rglob('*') if p.is_file()}
    if roster!={n for n in expected if n.startswith('saved/')}:raise ValueError('saved roster differs')
    for n,digest in expected.items():
        if hashlib.sha256((B/n).read_bytes()).hexdigest()!=digest:raise ValueError('sealed evidence differs '+n)
    refs=json.loads((B/'prior-evidence.json').read_text())
    for n,row in refs.items():
        p=(ROOT/row['path']).resolve()
        if not p.is_relative_to(ROOT) or hashlib.sha256(p.read_bytes()).hexdigest()!=row['gzip_sha256']:raise ValueError('prior binding differs '+n)
    @lru_cache(None)
    def prior(n):return gzip.decompress((ROOT/refs[n]['path']).read_bytes())
    @lru_cache(None)
    def read(n):return gzip.decompress((B/'saved'/(n+'.gz')).read_bytes())
    s=importlib.util.spec_from_file_location('exposure_analysis',B/'analyze_saved.py');m=importlib.util.module_from_spec(s);s.loader.exec_module(m)
    result=m.analyze(read,prior)
    if result!=json.loads((B/'result.json').read_text()):raise ValueError('retained analysis differs')
    ident=json.loads((B/'identity.json').read_text())
    same=all(hashlib.sha256((ROOT/n).read_bytes()).hexdigest()==digest for n,digest in ident['source_files'].items())
    return {'status':result['status'],'current_runtime_source_matches':same,'new_model_runs':0,'production_accepted':False,'decisions':result['decisions']}
if __name__=='__main__':print(json.dumps(verify(),indent=2))
