"""Verify public archives and safely extract regular data files only."""
from pathlib import Path,PurePosixPath
import tarfile,hashlib,json,shutil
P=Path(__file__).resolve().parent;B=P.parents[2].parent;O=B/'udm37-sterling-interior-inputs-v1';manifest={}
for archive,directory in [('intermediate.tar.gz','intermediate'),('geog.tar.gz','geog'),('grib.tar.gz','grib')]:
 receipt=json.loads((O/(archive+'.receipt.json')).read_text());f=O/archive;assert receipt['complete'] and hashlib.sha256(f.read_bytes()).hexdigest()==receipt['sha256'];dest=O/directory;dest.mkdir(exist_ok=False);files=[];size=0
 with tarfile.open(f) as tar:
  for m in tar:
   name=PurePosixPath(m.name);assert not name.is_absolute() and '..' not in name.parts
   target=dest.joinpath(*name.parts)
   if m.isdir():target.mkdir(parents=True,exist_ok=True);continue
   assert m.isfile() and m.size<1_000_000_000,m.name;size+=m.size;assert size<8_000_000_000
   target.parent.mkdir(parents=True,exist_ok=True);h=hashlib.sha256()
   with tar.extractfile(m) as src,target.open('xb') as out:
    for b in iter(lambda:src.read(1<<20),b''):out.write(b);h.update(b)
   files.append({'name':m.name,'bytes':m.size,'sha256':h.hexdigest()})
 manifest[archive]={'files':files,'total_uncompressed_bytes':size};print('EXTRACTED',archive,len(files),size,flush=True)
(O/'extraction-manifest.json').write_text(json.dumps(manifest,indent=2)+'\n')
