from pathlib import Path
import struct,json,hashlib,gzip
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
def sha(data):return hashlib.sha256(data).hexdigest()
p=BASE/'case-v2-on/TAPE3';data=p.read_bytes();records=[];o=0
while o<len(data):
 n=struct.unpack_from('<i',data,o)[0];assert n>=0 and o+8+n<=len(data) and struct.unpack_from('<i',data,o+4+n)[0]==n;records.append({'number':len(records)+1,'offset0':o,'bytes':n,'payload':data[o+4:o+4+n]});o+=n+8
assert o==len(data) and len(records)==6259
excerpts=BASE/'excerpts';excerpts.mkdir(exist_ok=True)
chosen=[]
for idx,kind in [(0,'file_header'),(519,'line_block_header'),(520,'line_data')]:
 r=records[idx];outfile=excerpts/(kind+'.bin.gz');outfile.write_bytes(gzip.compress(r['payload'],mtime=0));chosen.append({k:v for k,v in r.items() if k!='payload'}|{'kind':kind,'payload_sha256':sha(r['payload']),'included_gzip':str(outfile.relative_to(BASE))})
block=records[520]['payload'];assert len(block)==39000
fields=['SP','ALFA0','EPP','MOL','HWHMS','TMPALF','PSHIFT','IFLG']
def slot(i):
 j=i-1
 d={'slot':i,'VNU':struct.unpack_from('<d',block,8*j)[0]}
 for a,n in enumerate(fields):d[n]=struct.unpack_from('<i' if n in ('MOL','IFLG') else '<f',block,2000+1000*a+4*j)[0]
 d['MOL_as_float32']=struct.unpack_from('<f',block,5000+4*j)[0]
 d['brd_mol_flg_in']=[struct.unpack_from('<i',block,10000+4*(m+7*j))[0] for m in range(7)]
 d['brd_mol_dat']=[struct.unpack_from('<f',block,17000+4*(m+21*j))[0] for m in range(21)]
 d['speed_dep']=struct.unpack_from('<f',block,38000+4*j)[0]
 return d
hdr=struct.unpack('<ddii',records[519]['payload'])
result={'schema':'UDM37_COUPLING_TAPE3_READBACK_V1','source':{'path':str(p.resolve()),'sha256':sha(data),'bytes':len(data),'physical_sequential_records':len(records),'marker_format':'little-endian int32 leading/trailing; all checked'},'file_header_molecule2_ascii':records[0]['payload'][88:96].decode('ascii'),'optional_negative_EPP_header':records[0]['payload'][48+7:48+8]==b'^','record_numbering':'1-based physical sequential Fortran records including file header; not database-global line ID','block_ordinal':260,'block_header_record':520,'block_data_record':521,'block_header':{'VMIN':hdr[0],'VMAX':hdr[1],'NREC':hdr[2],'NWDS':hdr[3]},'selected_line':slot(124),'coupling_sidecar':slot(125),'excerpts':chosen,'upstream_HITRAN_or_AER_database_record_authenticated':False,'physical_reference_accepted':False}
(BASE/'line-readback.json').write_text(json.dumps(result,indent=2)+'\n')
# Actual raw OD record comparison, distinct from future saved metadata validation.
files=[];total=0
for p in sorted((BASE/'case-v2-on').glob('ODdeflt_*')):
 arms={'ON':p,'OFF':BASE/'case-v2-off'/p.name,'PR160':ROOT/'build/udm37-minimal-r3-observation-v1/case-v3-on'/p.name}
 parsed={};raws={}
 for arm,q in arms.items():
  raw=q.read_bytes();raws[arm]=raw;o=0;r=[]
  while o<len(raw):
   n=struct.unpack_from('<i',raw,o)[0];assert n>=0 and o+n+8<=len(raw) and struct.unpack_from('<i',raw,o+n+4)[0]==n;r.append(raw[o+4:o+4+n]);o+=n+8
  assert o==len(raw);parsed[arm]=r
 assert all(len(r)==len(parsed['ON']) for r in parsed.values())
 assert all(r[1:]==parsed['ON'][1:] for r in parsed.values())
 diffs={arm:[i for i,(a,b) in enumerate(zip(r[0],parsed['ON'][0])) if a!=b] for arm,r in parsed.items() if arm!='ON'}
 assert all(len(r[0])==1416 for r in parsed.values()) and all(all(1336<=i<1352 for i in d) for d in diffs.values())
 total+=len(parsed['ON'])-1
 files.append({'path':p.name,'records':len(parsed['ON']),'scientific_records_equal':True,'post_header_sha256':sha(b''.join(parsed['ON'][1:])),'full_sha256':{a:sha(v) for a,v in raws.items()},'header_difference_offsets0':diffs,'whole_file_equal':all(raw==raws['ON'] for raw in raws.values())})
assert len(files)==45 and total==53279
new=(BASE/'case-v2-on/UDM37_MIN_R3').read_bytes();old=(ROOT/'build/udm37-minimal-r3-observation-v1/case-v3-on/UDM37_MIN_R3').read_bytes();assert new==old
proof={'schema':'UDM37_COEFFICIENT_CAPTURE_PASSIVITY_V1','files':files,'scientific_records':total,'all_scientific_records_equal':True,'whole_file_status':'FAIL_PRESERVED_TIMESTAMP_DIFFERENCES','minimal_trace':{'new_sha256':sha(new),'PR160_sha256':sha(old),'bytes':len(new),'byte_identical':True},'raw_OD_reopened_by_root':True,'raw_OD_reopened_by_saved_CI':False,'physical_reference_accepted':False}
(BASE/'scientific-record-comparison.json').write_text(json.dumps(proof,indent=2)+'\n')
print('Root readback PASS',result['selected_line']['VNU'],result['file_header_molecule2_ascii'],total)
