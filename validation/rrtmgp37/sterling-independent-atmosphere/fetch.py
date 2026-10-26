"""Fetch bounded primary observations/documentation; never launch a model."""
from pathlib import Path
import urllib.request,urllib.parse,json,hashlib,datetime as dt,concurrent.futures,os,time
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-sterling-independent-atmosphere-fetch-v1'
BASE='https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py'
query=[('station',s) for s in ['IAD','DCA','BWI']]+[('data','all'),('sts','2016-10-06T12:00:00Z'),('ets','2016-10-06T21:00:00Z'),('tz','Etc/UTC'),('format','onlycomma'),('latlon','yes'),('elev','yes'),('missing','M'),('trace','T'),('report_type','3'),('report_type','4')]
JOBS={
 'asos.csv':BASE+'?'+urllib.parse.urlencode(query),
 'igra-stations.txt':'https://www.ncei.noaa.gov/pub/data/igra/igra2-station-list.txt',
 'igra-format-v2.txt':'https://www.ncei.noaa.gov/data/integrated-global-radiosonde-archive/doc/igra2-data-format.txt',
 'USM00072403-data.txt.zip':'https://www.ncei.noaa.gov/pub/data/igra/data/data-por/USM00072403-data.txt.zip',
 'igra-metadata.txt':'https://www.ncei.noaa.gov/pub/data/igra/history/igra2-metadata.txt',
 'igra-metadata-readme.txt':'https://www.ncei.noaa.gov/pub/data/igra/history/igra2-metadata-readme.txt',
 'asos-api.html':BASE+'?help=',
 'asos-ceilometer.html':'https://www.weather.gov/asos/Ceilometer.html',
}
def fetch(name,url):
 start=dt.datetime.now(dt.timezone.utc).isoformat();row={'name':name,'url':url,'started_UTC':start,'status':'STARTED','pid':os.getpid()}
 try:
  req=urllib.request.Request(url,headers={'User-Agent':'WRF-RRTMGP-research-observation/1.0'})
  with urllib.request.urlopen(req,timeout=90) as f:
   row.update(final_url=f.url,http_status=f.status,headers=dict(f.headers));raw=f.read()
  (O/name).write_bytes(raw);row.update(status='SUCCESS',bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest())
 except Exception as e:row.update(status='FAILED',error=repr(e))
 row['finished_UTC']=dt.datetime.now(dt.timezone.utc).isoformat();(O/(name+'.receipt.json')).write_text(json.dumps(row,indent=2)+'\n');return row
if __name__=='__main__':
 O.mkdir(exist_ok=False)
 with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
  results=list(pool.map(lambda kv:fetch(*kv),JOBS.items()))
 (O/'receipt.json').write_text(json.dumps({'retrievals':results,'new_model_runs':0},indent=2)+'\n')
 print(json.dumps([{k:v for k,v in x.items() if k in ['name','status','bytes','error']} for x in results],indent=2))
