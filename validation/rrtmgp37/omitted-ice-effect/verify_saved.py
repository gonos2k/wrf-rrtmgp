#!/usr/bin/env python3
import gzip,hashlib,importlib.util,json,re,tarfile,tempfile
from pathlib import Path

PACKAGE=Path(__file__).resolve().parent
ROOT=PACKAGE.parents[2]
s=importlib.util.spec_from_file_location('ice_analysis',PACKAGE/'analyze.py');a=importlib.util.module_from_spec(s);s.loader.exec_module(a)


def restore(package,output):
    blobs={}
    with tarfile.open(package/'saved/runtime-blobs.tar.gz') as tar:
        for m in tar:
            a.require(m.isfile() and re.fullmatch('[0-9a-f]{64}',m.name),'unsafe blob member')
            data=tar.extractfile(m).read()
            a.require(hashlib.sha256(data).hexdigest()==m.name,'blob changed')
            blobs[m.name]=data
    index=json.loads((package/'saved/runtime-index.json').read_text())
    for name,row in index['files'].items():
        a.require(not Path(name).is_absolute() and '..' not in Path(name).parts,'unsafe file path')
        data=b''.join(blobs[k] for k in row['blocks'])
        a.require(len(data)==row['size_bytes'] and hashlib.sha256(data).hexdigest()==row['sha256'],'capture reassembly changed')
        p=output/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(data)


def verify(package=PACKAGE):
    manifest=json.loads((package/'manifest.json').read_text())
    a.require(manifest['production_accepted'] is False,'false physical approval')
    for name,row in manifest['files'].items():
        p=package/name;a.require(p.is_file() and not p.is_symlink(),'missing evidence')
        a.require(hashlib.sha256(p.read_bytes()).hexdigest()==row['sha256'] and p.stat().st_size==row['size_bytes'],'evidence changed '+name)
    identity=json.loads((package/'saved/build-and-input-identity.json').read_text())
    for name,digest in identity['source_files'].items():
        a.require(hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==digest,'production source changed')
    patched=gzip.decompress((package/'saved/module_ra_rrtmgp_diagnostic.F.gz').read_bytes())
    a.require(hashlib.sha256(patched).hexdigest()==identity['compiled_diagnostic_source_sha256'],'compiled diagnostic source changed')
    a.require(b'diagnostic_raw_ice(c,k,b)' in patched and b'ICE_DIAG_PREDELTA64' in patched,'missing ice raw-direct linkage')
    accounting=json.loads((package/'saved/process-accounting.json').read_text())
    rows=[c for x in accounting['campaigns'] for c in x['commands']]
    a.require(len(rows)==393 and sum(x['actual_returncode']==0 for x in rows)==392,'process count changed')
    a.require(all(x['status']=='TERMINAL' and not x['timed_out'] for x in rows),'nonterminal process')
    fault=json.loads((package/'saved/command-133.json').read_text())
    a.require(fault['actual_returncode']==2 and 'Integer overflow' in (package/'saved/command-133.stderr').read_text(),'failed input evidence changed')
    a.require((package/'closure-conditions.json').read_bytes()==(ROOT/'validation/rrtmgp37/research-policy-contract/closure-conditions.json').read_bytes(),'seven closure conditions changed')
    with tempfile.TemporaryDirectory() as td:
        restore(package,Path(td))
        result,tables=a.analyze(Path(td),json.loads((package/'band-map.json').read_text()))
    a.require(result==json.loads((package/'results/result.json').read_text()),'derived result changed')
    for name,rows in tables.items():a.require(a.emit_csv(rows)==(package/'results'/name).read_text(),'derived table changed '+name)
    return result

if __name__=='__main__':
    r=verify();print(json.dumps({'status':r['status'],'summary':r['summary'],'production_accepted':False},indent=2))
