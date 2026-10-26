"""Copy exact raw IGRA sounding blocks, recording offsets in the fetched member."""
from pathlib import Path
import zipfile,json,hashlib
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;F=B/'udm37-sterling-independent-atmosphere-fetch-v1'
TARGETS={(2016,10,6,0),(2016,10,6,12),(2016,10,6,18),(2016,10,7,0)}
def main():
 out={}
 with zipfile.ZipFile(F/'USM00072403-data.txt.zip') as z:
  assert len(z.namelist())==1;name=z.namelist()[0];off=0
  with z.open(name) as f:
   while True:
    h=f.readline()
    if not h:break
    before=off;off+=len(h);assert h.startswith(b'#')
    date=tuple(map(int,[h[13:17],h[18:20],h[21:23],h[24:26]]));n=int(h[32:36]);lines=[f.readline() for _ in range(n)];off+=sum(map(len,lines))
    if date in TARGETS:
     raw=h+b''.join(lines);key='%04d%02d%02d%02d'%date;dest=P/'raw'/('sounding-'+key+'.txt');dest.write_bytes(raw);out[key]={'member':name,'uncompressed_member_offset':before,'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),'levels':n,'header':h.decode().rstrip()}
 assert len(out)==4
 (F/'selected-soundings.json').write_text(json.dumps(out,indent=2)+'\n');print('EXACT_PRIMARY_SOUNDING_BLOCKS_SELECTED',list(out))
if __name__=='__main__':main()
