"""Read original time headers and humidity availability, not filenames alone."""
from common import *
import json
from netCDF4 import Dataset,chartostring
def main():
 ex=json.loads((B/'udm37-sterling-low-level-extract-v2/extracted.json').read_text());rows=[]
 sys.path.insert(0,str(B/'udm37-sterling-low-level-python-deps'));import eccodes as e
 for f in ex['forcing']:
  met=Path(f['met_em']['pin']['path']);im=Path(f['intermediate_pin']['path']);gr=Path(f['GRIB_pin']['path'])
  with Dataset(met) as d:
   times=chartostring(d['Times'][:]).astype(str).tolist();vars={n:n in d.variables for n in ['RH','QVAPOR','QV','SPECHUMD']}
  with im.open('rb') as fd:
   n=struct.unpack('>I',fd.read(4))[0];fd.seek(n+4,1);n=struct.unpack('>I',fd.read(4))[0];header=fd.read(n);hdate=header[:24].decode().strip('\0 ');xfcst=struct.unpack('>f',header[24:28])[0]
  selected={r['source_message_sha256'] for r in f['GRIB']['rows']};records=[]
  with gr.open('rb') as fd:
   while True:
    g=e.codes_grib_new_from_file(fd)
    if g is None:break
    try:
     digest=hashlib.sha256(e.codes_get_message(g)).hexdigest()
     if digest in selected:records.append({'message_sha256':digest,**{k:e.codes_get(g,k) for k in ['dataDate','dataTime','validityDate','validityTime','stepRange','shortName','level','typeOfLevel']}})
    finally:e.codes_release(g)
  require(times==[f['time_UTC']] and hdate==f['time_UTC'] and xfcst==0,'actual met/intermediate timestamp mismatch')
  require(len(records)==len(selected) and all(str(r['stepRange'])=='0' and r['dataDate']==r['validityDate'] and r['dataTime']==r['validityTime'] for r in records),'not same-time analyzed GRIB')
  rows.append({'hour_UTC':f['hour_UTC'],'met_em_times':times,'met_em_humidity_variable_presence':vars,'intermediate_hdate':hdate,'intermediate_forecast_hour':xfcst,'selected_GRIB_analysis_messages':records})
 with Dataset(ex['boundary']['path']) as d:btime=chartostring(d['Times'][:]).astype(str).tolist()
 with Dataset(ex['input']['path']) as d:itime=chartostring(d['Times'][:]).astype(str).tolist()
 result={'pid':__import__('os').getpid(),'native_metadata_read':True,'forcing':rows,'initial_times':itime,'boundary_record_times':btime,'new_model_runs':0};(B/'udm37-sterling-low-level-extract-v2/support-audit.json').write_text(json.dumps(result,indent=2)+'\n');print('ORIGINAL_TIME_AND_HUMIDITY_HEADERS_AUDITED',len(rows))
if __name__=='__main__':main()
