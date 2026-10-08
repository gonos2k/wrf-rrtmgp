from pathlib import Path
import hashlib,json,struct
BASE=Path(__file__).resolve().parent;ROOT=BASE.parents[1]
DATA=ROOT/'build/udm37-lblrtm-reference-stage-v1/data'
TARGET=b'  618.023668'
def sha(b):return hashlib.sha256(b).hexdigest()
def scan(p):
 h=hashlib.sha256();offset=0;hits=[];headers=[];pending=None;total=0
 with p.open('rb') as f:
  for n,line in enumerate(f,1):
   h.update(line);total=n
   if pending is not None:
    pending['sidecar']={'line_1based':n,'offset0':offset,'bytes':len(line),'sha256':sha(line),'private_raw':line.decode('ascii')};pending=None
   if line.startswith(b'>') and b'02_CO2' in line and b'Orig Line List Name' in line:headers.append({'line_1based':n,'offset0':offset,'source_label':line.decode().split(':',2)[-1].strip()})
   if not line.startswith(b'>') and line[3:15].strip()==b'618.023668':
    row={'line_1based':n,'offset0':offset,'bytes':len(line),'sha256':sha(line),'private_raw':line.decode('ascii')};hits.append(row);pending=row
   offset+=len(line)
 if len(hits)!=1 or pending:raise ValueError('unique adjacent source record')
 return {'path':str(p.resolve()),'bytes':offset,'sha256':h.hexdigest(),'physical_lines':total,'matches':hits,'CO2_source_headers':headers}
combined=scan(DATA/'aer_v_3.8.1/line_file/aer_v_3.8.1');coupled=scan(DATA/'aer_v_3.8.1/lncpl_lines')
a=combined['matches'][0];b=coupled['matches'][0]
if a['private_raw']!=b['private_raw'] or a['sidecar']['private_raw']!=b['sidecar']['private_raw']:raise ValueError('normal and companion equality')
line=a['private_raw'].rstrip('\n');side=a['sidecar']['private_raw'].rstrip('\n')
if len(line)!=100 or len(side)!=100:raise ValueError('F100 width')
def num(x):return float(x.replace('D','E'))
fields={'molecule':int(line[:2]),'isotopologue':int(line[2:3]),'VNU_decimal':line[3:15].strip(),'STRSV_decimal':line[15:25].strip(),'transition_probability_decimal':line[25:35].strip(),'HWHMF_decimal':line[35:40].strip(),'HWHMS_decimal':line[40:45].strip(),'ENERGY_decimal':line[45:55].strip(),'TDEP_decimal':line[55:59].strip(),'SHIFT_decimal':line[59:67].strip(),'IVUP':int(line[67:70]),'IVLO':int(line[70:73]),'CUP':line[73:82],'CLO':line[82:91],'HOL':line[91:98],'IFLGSV':int(line[98:100]),'Y_decimals':[side[2+24*k:15+24*k].strip() for k in range(4)],'G_decimals':[side[15+24*k:26+24*k].strip() for k in range(4)],'sidecar_molecule':int(side[:2]),'sidecar_IFLAG':int(side[98:100])}
# Keep literal publisher records private. Public receipt contains positions, hashes, and scalar facts.
(BASE/'private-source-excerpts.txt').write_text('COMBINED\n'+a['private_raw']+a['sidecar']['private_raw']+'LNCPL_LINES\n'+b['private_raw']+b['sidecar']['private_raw'])
for d in (combined,coupled):
 del d['matches'][0]['private_raw'];del d['matches'][0]['sidecar']['private_raw']
plan=json.loads((ROOT/'build/udm37-lblrtm-common-band-line-generation-v1/plan-v6.json').read_text())
if combined['sha256']!=plan['source_stage']['line_file']['sha256']:raise ValueError('historical line file pin')
tape=(ROOT/'build/udm37-lblrtm-common-band-line-generation-v1/run-v6/TAPE5').read_bytes();rows=tape.decode().splitlines()
if rows[1]!='   475.000  2275.000' or rows[2][47:].strip() or [i+1 for i,x in enumerate(rows[2][:47]) if x=='1']!=[1,2,3,4,6,7,22]:raise ValueError('held LNFL TAPE5')
archive=DATA/'aer_v_3.8.1.tar.gz';hm=hashlib.md5();hs=hashlib.sha256()
with archive.open('rb') as f:
 while data:=f.read(2**20):hm.update(data);hs.update(data)
receipt=json.loads((ROOT/'build/udm37-lblrtm-reference-stage-v1/receipts/aer-line-download.json').read_text())
if hm.hexdigest()!=receipt['publisher_md5'] or hs.hexdigest()!=receipt['archive_sha256']:raise ValueError('download archive pin')
readback={'schema':'UDM37_ASCII_TO_COUPLING_SOURCE_READBACK_V1','files':[combined,coupled],'actual_ascii_reopened_by_root':True,'full_ascii_reopened_by_saved_CI':False,'record_pair_bytes_equal_between_files':True,'archive':{'sha256':hs.hexdigest(),'md5':hm.hexdigest(),'bytes':archive.stat().st_size,'publisher_md5':'12e29cc828b36f78145f6ee874af552b','version_DOI':'10.5281/zenodo.4019178','publisher_url':'https://zenodo.org/records/4019178','actual_hash_rechecked':True},'line_format':'F100 transition and sidecar records; publisher headers are longer','LNFL_TAPE5':{'sha256':sha(tape),'VMIN':475.0,'VMAX':2275.0,'molecule_numbers':[1,2,3,4,6,7,22],'HOLIND':'','F160':False,'NOCPL':False,'physical_output_union':[500.0,2250.0],'margin_each_side_cm1':25.0,'strength_rejection_controls_are_NOT_waived':True},'source_label_authority':'Publisher file header attribution only; not independent reproduction of original mixing generator','paper_2015_link':'https://www.sciencedirect.com/science/article/abs/pii/S0022407314003896','upstream_original_generator_authenticated':False,'full_spectral_reference_accepted':False,'production_accepted':False}
(BASE/'source-fields.json').write_text(json.dumps(fields,indent=2)+'\n');(BASE/'readback.json').write_text(json.dumps(readback,indent=2)+'\n')
print(json.dumps({'status':'ACTUAL_ASCII_SOURCE_PAIR_FOUND','source_fields':fields,'positions':[{k:v for k,v in d['matches'][0].items()} for d in [combined,coupled]],'archive_md5':hm.hexdigest()},indent=2))
