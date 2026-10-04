#!/usr/bin/env python3
"""Focused tamper controls for the package verifier; no model dependencies."""
import csv, hashlib, json, shutil, subprocess, sys, tempfile
from pathlib import Path

PKG = Path(__file__).resolve().parents[1]
VERIFY = PKG / 'verify_artifacts.py'

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        for b in iter(lambda:f.read(1<<20),b''): h.update(b)
    return h.hexdigest()

def clone(tmp, name):
    p=Path(tmp)/name
    shutil.copytree(PKG,p,ignore=shutil.ignore_patterns('__pycache__'))
    return p

def run(pkg):
    return subprocess.run([sys.executable,str(pkg/'verify_artifacts.py'),'--root',str(pkg)],
                          text=True,stdout=subprocess.PIPE,stderr=subprocess.STDOUT)

def refresh_manifest(pkg, rel):
    m=json.loads((pkg/'artifact-manifest.json').read_text())
    entry=next(x for x in m['files'] if x['path']==rel)
    path=pkg/rel
    entry['size_bytes']=path.stat().st_size
    entry['sha256']=sha(path)
    (pkg/'artifact-manifest.json').write_text(json.dumps(m,indent=2,sort_keys=True)+'\n')

def main():
    with tempfile.TemporaryDirectory(prefix='same-state-verifier-') as tmp:
        # Extra payload must fail the exact-roster requirement.
        p=clone(tmp,'extra'); (p/'unexpected.bin').write_bytes(b'extra')
        r=run(p); assert r.returncode and 'manifest does not exactly enumerate' in r.stdout, r.stdout
        # A changed receipt clock with its file hash honestly refreshed still fails roster agreement.
        p=clone(tmp,'clock'); rel='provenance/execution-receipt.json'
        f=p/rel; d=json.loads(f.read_text()); d['actual_call_roster'][0]['source_seconds'] += 60
        f.write_text(json.dumps(d,indent=2,sort_keys=True)+'\n'); refresh_manifest(p,rel)
        reviewer_rel='review/runtime-terminal-review.json'; reviewer=p/reviewer_rel
        review=json.loads(reviewer.read_text()); review['original_receipt']['sha256']=sha(f)
        reviewer.write_text(json.dumps(review,indent=2,sort_keys=True)+'\n'); refresh_manifest(p,reviewer_rel)
        r=run(p); assert r.returncode and 'actual call roster/clock mismatch' in r.stdout, r.stdout
        # Coordinated selected+aggregate CSV mean mutation passes package hashes but fails paired algebra.
        p=clone(tmp,'algebra'); rel='analysis/ON_native4_0-same_state.csv'; f=p/rel
        with f.open(newline='') as src: rows=list(csv.DictReader(src)); fields=rows[0].keys()
        target=('lw','1','2161',' 1.296000000000000E+005','SURFACE_DOWN')
        hit=0
        for row in rows:
            key=(row['phase'],row['domain'],row['step'],row['source_seconds'],row['metric'])
            if key==target:
                row['mean4']=str(float(row['mean4'])+1.0); hit+=1
        assert hit==2, hit
        with f.open('w',newline='') as dst:
            w=csv.DictWriter(dst,fieldnames=fields,lineterminator='\n');w.writeheader();w.writerows(rows)
        refresh_manifest(p,rel)
        r=run(p); assert r.returncode and 'seed mean contrast algebra' in r.stdout, r.stdout
    print('PASS: extra-file, receipt-clock, and coordinated CSV-algebra tampering are rejected')

if __name__=='__main__': main()
