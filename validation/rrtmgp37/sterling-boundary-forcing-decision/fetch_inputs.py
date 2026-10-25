"""Bounded public input downloads, isolated in the task build directory."""
from pathlib import Path
import urllib.request,hashlib,json,time,datetime as dt,concurrent.futures
P=Path(__file__).resolve().parent;B=P.parents[2].parent;O=B/'udm37-sterling-interior-inputs-v1';O.mkdir(exist_ok=False)
items=[('intermediate.tar.gz','https://www2.mmm.ucar.edu/wrf/TUTORIAL_DATA/single_domain/FILE.tar.gz',500_000_000),('geog.tar.gz','https://www2.mmm.ucar.edu/wrf/src/wps_files/geog_low_res_mandatory.tar.gz',900_000_000),('grib.tar.gz','https://www2.mmm.ucar.edu/wrf/TUTORIAL_DATA/matthew_1deg.tar.gz',700_000_000)]
def fetch(item):
 name,url,limit=item;record={'url':url,'name':name,'started_utc':dt.datetime.now(dt.timezone.utc).isoformat(),'attempts':1};h=hashlib.sha256();count=0
 try:
  with urllib.request.urlopen(urllib.request.Request(url,headers={'User-Agent':'WRF-UDM-conditional-input-evaluation/1.0'}),timeout=40) as response,(O/name).open('xb') as f:
   record.update(status=response.status,final_url=response.url,headers=dict(response.headers))
   while True:
    b=response.read(1<<20)
    if not b:break
    count+=len(b)
    if count>limit:raise ValueError('bounded download size exceeded')
    f.write(b);h.update(b)
  record.update(bytes=count,sha256=h.hexdigest(),complete=True)
 except Exception as e:record.update(error=repr(e),bytes=count,complete=False)
 record['finished_utc']=dt.datetime.now(dt.timezone.utc).isoformat();(O/(name+'.receipt.json')).write_text(json.dumps(record,indent=2)+'\n');print(name,record['complete'],count,record.get('error',''),flush=True);return record
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:records=list(pool.map(fetch,items))
(O/'download-receipt.json').write_text(json.dumps({'items':records,'new_model_processes':0},indent=2)+'\n')
