from pathlib import Path
import struct,json,hashlib,gzip,importlib.util
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
def sha(b):return hashlib.sha256(b).hexdigest()
def parse(b):
 r=[];o=0
 while o<len(b):
  n=struct.unpack_from('<i',b,o)[0]
  if n<0 or o+n+8>len(b) or struct.unpack_from('<i',b,o+n+4)[0]!=n:raise ValueError('record marker')
  r.append(b[o+4:o+4+n]);o+=n+8
 if o!=len(b):raise ValueError('trailing bytes')
 return r
names={f'ODdeflt_{n:03d}' for n in range(1,46)}
paths={'ON':BASE/'case-v2-on','OFF':BASE/'case-v2-off','PR161':ROOT/'build/udm37-coupling-generation-v1/case-v2-on'}
if any({p.name for p in d.glob('ODdeflt_*')}!=names for d in paths.values()):raise ValueError('exact OD roster')
files=[];total=0
for name in sorted(names):
 raw={a:(d/name).read_bytes() for a,d in paths.items()};records={a:parse(b) for a,b in raw.items()};ref=records['ON']
 if not all(r[1:]==ref[1:] for r in records.values()):raise ValueError('scientific record changed')
 offsets={a:[i for i,(x,y) in enumerate(zip(r[0],ref[0])) if x!=y] for a,r in records.items() if a!='ON'}
 if not all(len(r[0])==1416 for r in records.values()) or not all(all(1336<=i<1352 for i in x) for x in offsets.values()):raise ValueError('non-date header change')
 total+=len(ref)-1
 files.append({'path':name,'records':len(ref),'scientific_records_equal':True,'whole_file_equal':all(b==raw['ON'] for b in raw.values()),'post_header_sha256':sha(b''.join(ref[1:])),'full_sha256':{a:sha(b) for a,b in raw.items()},'header_difference_offsets0':offsets})
 if name=='ODdeflt_021':
  ex=BASE/'excerpts';ex.mkdir(exist_ok=True)
  entries=[]
  for number,kind in [(1,'file_header'),(28,'panel14_header'),(29,'panel14_OD')]:
   b=ref[number-1];p=ex/(kind+'.bin.gz');p.write_bytes(gzip.compress(b,mtime=0));entries.append({'physical_record_1based':number,'path':str(p.relative_to(BASE)),'bytes':len(b),'sha256':sha(b)})
  (BASE/'OD-readback.json').write_text(json.dumps({'schema':'UDM37_SELECTED_OD_READBACK_V1','source_path':str((paths['ON']/name).resolve()),'source_sha256':sha(raw['ON']),'source_bytes':len(raw['ON']),'all_markers_checked':True,'record_count':len(ref),'selected_panel_ordinal':14,'excerpt_record_origin':'Actual sequential records, not synthetic arrays','excerpts':entries,'physical_reference_accepted':False},indent=2)+'\n')
traces=[]
for name in ['UDM37_MIN_R3','UDM37_LINE_COEFF']:
 new=(paths['ON']/name).read_bytes();old=(paths['PR161']/name).read_bytes()
 if new!=old:raise ValueError('parent trace changed')
 traces.append({'path':name,'bytes':len(new),'sha256':sha(new),'parent_sha256':sha(old),'byte_identical':True})
if total!=53279:raise ValueError('scientific count')
(BASE/'scientific-record-comparison.json').write_text(json.dumps({'schema':'UDM37_FINAL_OD_PASSIVITY_V1','files':files,'scientific_records':total,'all_scientific_records_equal':True,'whole_file_status':'FAIL_PRESERVED_TIMESTAMP_DIFFERENCES','parent_traces':traces,'raw_OD_reopened_by_root':True,'raw_OD_reopened_by_saved_CI':False,'physical_reference_accepted':False,'production_accepted':False},indent=2)+'\n')
sp=importlib.util.spec_from_file_location('core',BASE/'verify_core.py');m=importlib.util.module_from_spec(sp);sp.loader.exec_module(m)
h=gzip.decompress((BASE/'excerpts/panel14_header.bin.gz').read_bytes());d=gzip.decompress((BASE/'excerpts/panel14_OD.bin.gz').read_bytes())
result=m.analyze((BASE/'case-v2-on/UDM37_FINAL_OD').read_text(),h,d)
(BASE/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps({'status':result['status'],'checks':result['exact_arithmetic_and_value_checks'],'selected':result['selected'],'OD_records_compared':total},indent=2))
