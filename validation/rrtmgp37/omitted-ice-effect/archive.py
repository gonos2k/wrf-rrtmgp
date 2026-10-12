#!/usr/bin/env python3
"""Seal final captures, process accounting and the actually compiled diagnostic source."""
import argparse,re,gzip,hashlib,json,tarfile,shutil,io
from pathlib import Path


def main():
    ap=argparse.ArgumentParser();ap.add_argument('repository',type=Path);ap.add_argument('build_root',type=Path);a=ap.parse_args()
    pkg=a.repository/'validation/rrtmgp37/omitted-ice-effect';saved=pkg/'saved';saved.mkdir(exist_ok=False)
    base=a.build_root
    campaigns=[base/'udm37-omitted-ice-effect-runtime-v1',base/'udm37-omitted-ice-effect-runtime-v2',base/'udm37-omitted-ice-effect-runtime-v3',base/'udm37-omitted-ice-effect-sw-seeds-v1',base/'udm37-omitted-ice-effect-sw-seeds-v2']
    accounting=[]
    for c in campaigns:
        rows=[json.loads(x.read_text()) for x in sorted(c.glob('command-*.json'))]
        accounting.append({'campaign':c.name,'processes':len(rows),'RC0':sum(r['actual_returncode']==0 for r in rows),'nonzero':sum(r['actual_returncode']!=0 for r in rows),'commands':rows})
    (saved/'process-accounting.json').write_text(json.dumps({'campaigns':accounting,'processes':sum(x['processes'] for x in accounting),'new_WRF_processes':0,'physics_approved':False},indent=2)+'\n')
    with tarfile.open(saved/'runtime.tar.gz','w:gz',compresslevel=6) as tar:
        for c in (campaigns[2],campaigns[4]):
            for p in sorted(c.glob('on-*')):
                for file in sorted(p.rglob('*')):
                    if file.is_file():
                        info=tarfile.TarInfo(str(file.relative_to(c)));data=file.read_bytes();info.size=len(data);info.mtime=0;info.mode=0o644
                        tar.addfile(info,io.BytesIO(data))
    blobs={};files={}
    raw_tar=saved/'runtime.tar.gz'
    with tarfile.open(raw_tar) as tar:
        for member in tar:
            data=tar.extractfile(member).read();chunks=[data]
            if member.name.endswith(('.input','.result')) or member.name.endswith('/input'):
                lines=data.splitlines(keepends=True);prefix=b''.join(lines[:2]);body=b''.join(lines[2:])
                starts=[m.start() for m in re.finditer(rb'(?m)^[A-Za-z0-9_+-]+ [0-9]+ [0-9]+(?: [0-9]+)?\n',body)]
                if starts and starts[0]==0:chunks=[prefix]+[body[x:y] for x,y in zip(starts,starts[1:]+[len(body)])]
            keys=[]
            for chunk in chunks:
                key=hashlib.sha256(chunk).hexdigest();blobs.setdefault(key,chunk);keys.append(key)
            files[member.name]={'sha256':hashlib.sha256(data).hexdigest(),'size_bytes':len(data),'blocks':keys}
    with tarfile.open(saved/'runtime-blobs.tar.gz','w:gz',compresslevel=6) as tar:
        for key,data in sorted(blobs.items()):
            info=tarfile.TarInfo(key);info.size=len(data);info.mode=0o644;info.mtime=0;tar.addfile(info,io.BytesIO(data))
    (saved/'runtime-index.json').write_text(json.dumps({'schema':'EXACT_CAPTURE_BLOCK_ARCHIVE_V1','files':files},indent=2)+'\n')
    raw_tar.unlink()
    components=base/'udm37-omitted-ice-components-v1'
    for file in ('src/module_ra_rrtmgp_diagnostic.F','CMakeLists.txt','build/CMakeCache.txt','build.log','build-02.log','build-03.log','build-04.log','configure.log','configure-02.log'):
        p=components/file;(saved/(p.name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    for name in ('baseline','diagnostic'):
        p=components/'build'/name
        (saved/(name+'.gz')).write_bytes(gzip.compress(p.read_bytes(),mtime=0))
    fault=campaigns[3]
    for name in ('command-133.json','command-133.stdout','command-133.stderr'):
        (saved/name).write_bytes((fault/name).read_bytes())
    plan=json.loads((campaigns[2]/'plan.json').read_text())
    plan['compiled_diagnostic_source_sha256']=hashlib.sha256((components/'src/module_ra_rrtmgp_diagnostic.F').read_bytes()).hexdigest()
    plan['actual_final_binary_sha256']=hashlib.sha256((components/'build/diagnostic').read_bytes()).hexdigest()
    plan['main']='36301782b2372b28f942920d5ab7997801b16e3a';plan['main_tree']='0dc41a63e89c8ed77d405aee0805a414474161a4'
    plan['component_builds']={'configure_successes':2,'build_RC2_free_form_preparation':1,'build_successes':3}
    plan['source_files']={str(p.relative_to(a.repository)):hashlib.sha256(p.read_bytes()).hexdigest() for p in (a.repository/'WRF/phys').glob('module_ra_rrtmgp*.F')}
    (saved/'build-and-input-identity.json').write_text(json.dumps(plan,indent=2)+'\n')
    shutil.copyfile(a.repository/'validation/rrtmgp37/research-policy-contract/closure-conditions.json',pkg/'closure-conditions.json')
    print([(x['campaign'],x['processes'],x['RC0']) for x in accounting])

if __name__=='__main__':main()
