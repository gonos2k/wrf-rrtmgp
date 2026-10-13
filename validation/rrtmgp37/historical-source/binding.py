"""Read an explicitly historical source binding without changing its digest."""
import gzip,hashlib,json
from pathlib import Path
B=Path(__file__).resolve().parent

def historical_bytes(repo,name,expected_sha256):
    current=(repo/name).read_bytes()
    if hashlib.sha256(current).hexdigest()==expected_sha256:
        return current
    candidates=[]
    for receipt in (B/'snapshot.json',B/'snapshot-e26ab7ba.json',B/'snapshot-5f7ac64a.json',B/'snapshot-39780e19.json'):
        rows=json.loads(receipt.read_text())['files']
        if name in rows and rows[name]['sha256']==expected_sha256:
            candidates.append(rows[name])
    if len(candidates)!=1:
        raise ValueError('No unique historical source identity: '+name)
    row=candidates[0]
    compressed=(B/row['archive']).read_bytes()
    if hashlib.sha256(compressed).hexdigest()!=row['compressed_sha256']:
        raise ValueError('Historical source archive changed: '+name)
    raw=gzip.decompress(compressed)
    if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=expected_sha256:
        raise ValueError('Historical source bytes changed: '+name)
    return raw
