from pathlib import Path
import datetime,gzip,hashlib,importlib.util,json
ROOT=Path(__file__).resolve().parents[2]
B=ROOT/'build/udm37-native-spectral-window-pr-work/validation/rrtmgp37/lbl-native-spectral-window'
P=B.parent/'lbl-grid-threshold-comparison'
s=importlib.util.spec_from_file_location('native_core',B/'analyze_core.py');c=importlib.util.module_from_spec(s);s.loader.exec_module(c)
def j(p):return json.loads(p.read_text())
def write(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def ref(p):b=p.read_bytes();return {'path':str(p.relative_to(P.parent)),'bytes':len(b),'sha256':hashlib.sha256(b).hexdigest()}
def gz(n):return gzip.decompress((P/n).read_bytes())
start=datetime.datetime.now(datetime.timezone.utc)
# Validate the exact sealed PR165 package bytes before selecting new native rows.
m=j(P/'manifest.json')
for r in m['files']:
 b=(P/r['path']).read_bytes();c.require(len(b)==r['bytes'] and hashlib.sha256(b).hexdigest()==r['sha256'],'parent sealed bytes')
ps=j(P/'samples.json');native={};refs=[]
for a in c.RATIOS:
 panel=ps[a][40]['panel'];header=f'OD/{a}.{panel}.header.gz';payload=f'OD/{a}.{panel}.payload.gz';trace=f'traces/{a}.min.gz'
 native[a]=c.extract(gz(header),gz(payload),gz(trace).decode(),a);refs += [ref(P/header),ref(P/payload),ref(P/trace)]
 (B/f'{a}.native.csv').write_bytes(c.csv_bytes(native[a]))
result,shared=c.analyze(native,j(P/'result.json'),ps)
(B/'half-quarter.shared161.csv').write_bytes(c.csv_bytes(shared));write(B/'result.json',result)
refs += [ref(P/n) for n in ('manifest.json','samples.json','result.json','source/oprop.f90.official.gz')]
write(B/'parent-pins.json',{'parent_main_commit':'3e577a5bacc5d189cd2528675255da1c1b3641b6','parent_main_tree':'a63510836516da367aaabda461eacbad6327b047',
 'parent_merged_PR':165,'sealed_parent_package_verified':True,'parent_payloads_modified':False,'files':refs,
 'readback_scope':'Previously saved actual layer21 OD panel payloads and INIT grid metadata; no new full raw OD/TAPE3/solver readback.'})
write(B/'root-readback-receipt.json',{'started_utc':start.isoformat(),'ended_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),
 'process':'Python saved-payload analysis','returncode':0,'native_rows':{a:len(v) for a,v in native.items()},'shared_rows':len(shared),
 'fresh_model_or_compiler_processes':0,'production_accepted':False})
print(json.dumps({'native':{a:{k:v[k] for k in ('native_samples','negative_samples','minimum')} for a,v in result['native'].items()},
 'max161':result['shared161_half_to_quarter'],'extra80':result['additional_shared80'],'groups':result['alignment_group_diagnostics']},indent=2))
