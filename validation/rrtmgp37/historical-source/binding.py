"""Read an explicitly historical source binding without changing its digest."""
import gzip,hashlib,json
from pathlib import Path
B=Path(__file__).resolve().parent

def historical_bytes(repo,name,expected_sha256):
    current=(repo/name).read_bytes()
    if hashlib.sha256(current).hexdigest()==expected_sha256:
        return current
    candidates=[]
    for receipt in (B/'snapshot.json',B/'snapshot-e26ab7ba.json',B/'snapshot-5f7ac64a.json',B/'snapshot-39780e19.json',B/'snapshot-17668732.json',B/'snapshot-3485400c.json',B/'snapshot-d0058087.json',B/'snapshot-3ad2efd1.json',B/'snapshot-4bb3f428.json',B/'snapshot-11eb25c8.json',B/'snapshot-d2223f13.json'):
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

class HistoricalRoot:
    """Read-only path view for reconstructing a pinned historical observer.

    It cannot turn old model evidence into current-source evidence. Callers
    separately report current-source matches; only exact retained digests read.
    """
    def __init__(self, repo, pins, name=''):
        self.repo=repo; self.pins=pins; self.key=name

    def __truediv__(self, part):
        return HistoricalRoot(self.repo,self.pins,str(Path(self.key)/part))

    @property
    def name(self):
        return Path(self.key).name

    def read_bytes(self):
        if self.key not in self.pins:
            raise ValueError('Unpinned historical observer input: '+self.key)
        return historical_bytes(self.repo,self.key,self.pins[self.key]['sha256'])

    def read_text(self):
        return self.read_bytes().decode()
