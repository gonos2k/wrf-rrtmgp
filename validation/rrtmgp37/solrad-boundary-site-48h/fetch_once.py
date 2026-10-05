#!/usr/bin/env python3
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor
import urllib.request, hashlib, json, datetime
root=Path(__file__).resolve().parent
assert not (root/'download-manifest.json').exists(), 'single campaign already attempted'
items=[(f'raw/{s}16{day}.dat', f'https://gml.noaa.gov/aftp/data/radiation/solrad/{s}/2016/{s}16{day}.dat') for s in ['ort','ste','tlh'] for day in [280,281,282]]
items += [('sources/README_SOLRAD.txt','https://gml.noaa.gov/aftp/data/radiation/solrad/README_SOLRAD.txt'),('sources/network.html','https://gml.noaa.gov/grad/solrad/'),('sources/problems.html','https://gml.noaa.gov/grad/solrad/problems.html')]
items += [(f'sources/{s}.html',f'https://gml.noaa.gov/grad/solrad/{s}.html') for s in ['ort','ste','tlh']]
items += [('sources/dataset-ste-2016.html','https://gml.noaa.gov/data/dataset.php?item=ste-solrad-2016')]
def fetch(item):
 name,url=item; out={'path':name,'requested_url':url,'started_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'attempts':1}
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'WRF-UDM-radiation-validation/1.0'}),timeout=30) as r:
   data=r.read(5_000_001);assert len(data)<=5_000_000
   out.update(status=r.status,final_url=r.url,headers=dict(r.headers),bytes=len(data),sha256=hashlib.sha256(data).hexdigest())
   p=root/name;assert not p.exists();p.write_bytes(data)
 except Exception as e: out['error']=repr(e)
 out['finished_utc']=datetime.datetime.now(datetime.timezone.utc).isoformat()
 return out
with ThreadPoolExecutor(max_workers=4) as ex: rows=list(ex.map(fetch,items))
(root/'download-manifest.json').write_text(json.dumps({'schema':'bounded-solrad-download-v1','items':rows,'new_model_or_solver_calls':0},indent=2)+'\n')
for x in rows: print(x['path'],x.get('status'),x.get('bytes'),x.get('error',''))
