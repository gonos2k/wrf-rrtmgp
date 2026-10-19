#!/usr/bin/env python3
"""Verify sealed sustained evidence and replay its assertions; launches no model."""
import gzip
import hashlib
import importlib.util
import json
from functools import lru_cache
from pathlib import Path
B=Path(__file__).resolve().parent

def verify():
    manifest=json.loads((B/'manifest.json').read_text())
    expected=manifest['files']
    actual={str(p.relative_to(B)) for p in (B/'saved').rglob('*') if p.is_file()}
    require=actual=={n for n in expected if n.startswith('saved/')}
    if not require:raise ValueError('saved roster changed')
    for name,digest in expected.items():
        if hashlib.sha256((B/name).read_bytes()).hexdigest()!=digest:
            raise ValueError('sealed artifact differs '+name)
    spec=importlib.util.spec_from_file_location('sustained_analyzer',B/'analyze_saved.py')
    m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    @lru_cache(None)
    def read(name):return gzip.decompress((B/'saved'/(name+'.gz')).read_bytes())
    result=m.analyze(read)
    if result!=json.loads((B/'result.json').read_text()):raise ValueError('saved result changed')
    ident=json.loads((B/'identity.json').read_text());root=B.parents[2]
    binding=json.loads((B/'merge-binding.json').read_text())
    observed=json.loads(read('provenance/pr180-merged.json'))
    if (observed['state']!='MERGED' or observed['isDraft'] or
            observed['headRefOid']!=ident['baseline_commit'] or
            observed['mergeCommit']['oid']!=binding['main_merge_commit'] or
            binding['head_tree']!=ident['baseline_tree'] or
            binding['merged_main_tree']!=ident['baseline_tree']):
        raise ValueError('merged main does not bind the tested tree')
    current=all(hashlib.sha256((root/name).read_bytes()).hexdigest()==digest for name,digest in ident['source_files'].items())
    return {'status':result['status'],'current_runtime_source_equals_frozen_PR180':current,
            'merged_main_commit':binding['main_merge_commit'],
            'new_model_runs':0,'production_accepted':False,'restart':result['restart']}

if __name__=='__main__':print(json.dumps(verify(),indent=2))
