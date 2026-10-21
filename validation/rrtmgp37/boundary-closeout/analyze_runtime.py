#!/usr/bin/env python3
"""Read bounded host operands and compare call-time/history-time mass factors."""
from pathlib import Path
from datetime import datetime,timedelta
import json,struct
import numpy as np
from netCDF4 import Dataset
P=Path(__file__).resolve().parent;R=P.parents[2];B=R.parent;O=B/'udm37-boundary-closeout-analysis-v1';O.mkdir(exist_ok=True)
def value(h):return struct.unpack('<f',struct.pack('<I',int(h,16)))[0]
def bits(x):return f'{struct.unpack("<I",struct.pack("<f",x))[0]:08x}'
trace=B/'udm37-boundary-closeout-host-v1/host/boundary-closeout.txt';rows=[]
for line in trace.read_text().splitlines():
 s=line.split();rows.append({'kind':s[0],'species':int(s[1]),'rk':int(s[2]),'source_time_s':float(s[3]),'bits':[h.lower() for h in s[4:]],'values':[value(h) for h in s[4:]]})
final=[];hist=next((B/'udm37-boundary-closeout-host-v1/host').glob('wrfout*'))
with Dataset(hist) as d:
 d.set_auto_mask(False);times=[b''.join(t).decode() for t in d['Times'][:]]
 for row in rows:
  if row['kind']!='solve-final':continue
  output_time=(datetime(2016,10,6)+timedelta(seconds=row['source_time_s']+60)).strftime('%Y-%m-%d_%H:%M:%S');it=times.index(output_time);field='QNCLOUD' if row['species']==1 else 'QNRAIN'
  eta=np.float32(d[field][it,0,0,23]);mu=np.float32(d['MU'][it,0,23]);mub=np.float32(d['MUB'][it,0,23]);c1=np.float32(d['C1H'][it,0]);c2=np.float32(d['C2H'][it,0]);mass=np.float32(c1*np.float32(mu+mub)+c2)
  native=next(r for r in rows if r['kind']=='final' and r['species']==row['species'] and r['source_time_s']==row['source_time_s']);bfield=np.float32(native['values'][3]);reconstructed=np.float32(bfield/mass)
  assert bits(eta)==row['bits'][0]==native['bits'][6]
  final.append({'field':field,'time':output_time,'source_time_s':row['source_time_s'],'species':row['species'],'actual_eta_bits':bits(eta),'history_MU_bits':bits(mu),'history_MUB_bits':bits(mub),'history_C1H_bits':bits(c1),'history_C2H_bits':bits(c2),'history_total_mass_bits':bits(np.float32(mu+mub)),'history_factor_bits':bits(mass),'history_eta_reconstruction_bits':bits(reconstructed),'actual_eta':float(eta),'history_eta_reconstructed':float(reconstructed),'history_factor_Pa':float(mass),'call_factor_Pa':native['values'][4],'call_MU_total_Pa':row['values'][1],'history_MU_total_Pa':float(np.float32(mu+mub)),'relaxation_strip_number':np.asarray(d[field][it,:2,1:5,22:25]).astype(float).tolist(),'interior_number_max':float(np.asarray(d[field][it,:,5:-5,5:-5]).max())})
report={'trace_records':rows,'final_vs_history':final,'interpretation':'The native final call consumes c1*MUTS+c2; history reconstruction consumes c1*fl(MU_2+MUB)+c2. Actual operands differ and fully explain the recorded last-bit differences. No fitted tolerance or production change.','physical_accuracy_approved':False}
(O/'analysis.json').write_text(json.dumps(report,indent=2)+'\n');print('BOUNDED_HOST_OPERANDS_EXTRACTED',len(rows),'records',len(final),'final/history comparisons')
