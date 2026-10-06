#!/usr/bin/env python3
"""Verify published evidence bytes and lossless JSON archive hashes."""
from pathlib import Path
import gzip, hashlib, json
root=Path(__file__).resolve().parent
manifest=json.loads((root/'bundle-manifest.json').read_text())
errors=[]
for name,item in manifest['files'].items():
    path=root/name
    if not path.is_file() or path.stat().st_size!=item['size_bytes'] or hashlib.sha256(path.read_bytes()).hexdigest()!=item['sha256']:
        errors.append(name)
for item in json.loads((root/'compressed-json-manifest.json').read_text())['files']:
    compressed=(root/item['compressed_path']).read_bytes()
    original=gzip.decompress(compressed)
    if hashlib.sha256(compressed).hexdigest()!=item['compressed_sha256'] or hashlib.sha256(original).hexdigest()!=item['original_sha256'] or len(original)!=item['original_size_bytes']:
        errors.append(item['compressed_path']+' decompression hash')
print(json.dumps({'status':'FAIL' if errors else 'PASS','file_count':manifest['file_count'],'errors':errors}))
raise SystemExit(bool(errors))
