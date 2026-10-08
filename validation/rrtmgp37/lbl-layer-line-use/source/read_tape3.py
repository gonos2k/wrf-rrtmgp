from pathlib import Path
import struct,gzip,json,hashlib
BASE=Path(__file__).resolve().parent
trace=(BASE/'case-v3-on/UDM37_LAYER_USE').read_text()
needed={int(l.split()[4]) for l in trace.splitlines() if l.startswith('ENTRY')}
selected=needed|{n-1 for n in needed}|{1}
p=(BASE/'case-v3-on/TAPE3').resolve();ex=BASE/'excerpts';ex.mkdir(exist_ok=True);rows=[]
with p.open('rb') as f:
 n=0
 while x:=f.read(4):
  size=struct.unpack('<i',x)[0];n+=1
  if size<0:raise ValueError('negative marker')
  if n in selected:
   v=f.read(size);(ex/(str(n)+'.bin.gz')).write_bytes(gzip.compress(v,mtime=0))
   rows.append({'record':n,'bytes':size,'sha256':hashlib.sha256(v).hexdigest()})
  else:f.seek(size,1)
  if struct.unpack('<i',f.read(4))[0]!=size:raise ValueError('record markers')
if {r['record'] for r in rows}!=selected:raise ValueError('exact excerpt roster')
(BASE/'TAPE3-readback.json').write_text(json.dumps({'raw_TAPE3':str(p),'raw_sha256':hashlib.sha256(p.read_bytes()).hexdigest(),'record_markers_scanned':n,'payload_records_read':len(rows),'data_records':sorted(needed),'payloads':rows,'root_actual_readback':True,'full_roster_revalidated':False,'physical_reference_accepted':False},indent=2)+'\n')
print('Read',len(rows),'selected TAPE3 payloads, not a full line roster')
