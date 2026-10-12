"""Read an explicitly historical source binding without changing its digest."""
import gzip,hashlib,json
from pathlib import Path
B=Path(__file__).resolve().parent

def historical_bytes(repo,name,expected_sha256):
    current=(repo/name).read_bytes()
    if hashlib.sha256(current).hexdigest()==expected_sha256:
        return current
    rows=json.loads((B/'snapshot.json').read_text())['files']
    if name not in rows:
        raise ValueError('No historical source snapshot: '+name)
    row=rows[name]
    if row['sha256']!=expected_sha256:
        raise ValueError('Historical source identity differs: '+name)
    compressed=(B/row['archive']).read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=row['compressed_sha256']:
        raise ValueError('Historical source archive changed: '+name)
    raw=gzip.decompress(compressed)
    if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError('Historical source bytes changed: '+name)
    return raw
