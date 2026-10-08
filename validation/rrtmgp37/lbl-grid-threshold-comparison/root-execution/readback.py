from pathlib import Path
import gzip,hashlib,importlib.util,json,shutil,struct
BASE=Path(__file__).resolve().parent
PKG=BASE.parent/'udm37-grid-threshold-pr-work/validation/rrtmgp37/lbl-grid-threshold-comparison'
S=importlib.util.spec_from_file_location('core',PKG/'verify_core.py');c=importlib.util.module_from_spec(S);S.loader.exec_module(c)
def sha(v):return hashlib.sha256(v).hexdigest()
def js(p,x):p.write_text(json.dumps(x,indent=2)+'\n')
def gz(p,v):p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(gzip.compress(v,mtime=0))
def records(path):
    with path.open('rb') as f:
        while True:
            marker=f.read(4)
            if not marker:return
            c.require(len(marker)==4,'marker');n=struct.unpack('<i',marker)[0];c.require(0<n<10**8,'record size')
            data=f.read(n);c.require(len(data)==n and f.read(4)==marker,'complete record markers');yield data
# Every process has exited and been reaped before root reads any model output.
for n in ('probe','h-off',*c.ARMS):
    r=json.loads((BASE/f'solver-{n}-result.json').read_text());c.require(r['returncode']==0 and r['process_exit']=='REAPED','completed process')
traces={};mins={};wanted=set()
for arm in c.ARMS:
    traces[arm]=(BASE/f'case-{arm}/UDM37_LAYER_USE').read_text();mins[arm]=(BASE/f'case-{arm}/UDM37_MIN_R3').read_text()
    wanted|={r['record'] for r in c.parse(traces[arm]) if r['tag']=='ENTRY'}
    gz(PKG/f'traces/{arm}.layer.gz',traces[arm].encode());gz(PKG/f'traces/{arm}.min.gz',mins[arm].encode())
# Read actual needed TAPE3 records from held original, not projected roster.
blocks={};payloads=[]
for i,raw in enumerate(records(BASE/'case-h/TAPE3'),1):
    if i in wanted or i+1 in wanted or i==1:
        gz(PKG/f'TAPE3/{i}.bin.gz',raw);payloads.append({'record':i,'bytes':len(raw),'sha256':sha(raw)})
        if i in wanted:blocks[str(i)]=raw
    if i>=max(wanted):break
c.require(set(blocks)=={str(i) for i in wanted},'all needed actual TAPE3 records')
js(PKG/'TAPE3-readback.json',{'actual_root_readback':True,'full_file_roster_repeated':False,'raw_file_sha256':sha((BASE/'case-h/TAPE3').read_bytes()),'data_records':sorted(wanted),'payloads':payloads})
# Actual 81 overlapping layer21 grid samples, no additional interpolation.
nus=[c.TARGET+(j-40)*c.H for j in range(81)];samples={};samplemeta={}
for arm in c.ARMS:
    panels=[];rs=iter(records(BASE/f'case-{arm}/ODexact_021'));filhdr=next(rs);c.require(len(filhdr)==1416,'FILHDR layout')
    for k,(header,payload) in enumerate(zip(rs,rs),1):
        c.require(len(header)==32,'OD panel header');v1,v2,dv,n,pad=struct.unpack('<dddii',header)
        c.require(len(payload)==8*n,'actual OD panel payload')
        panels.append((k,header,payload,v1,v2))
    sm=[];vals=[];saved=set()
    for nu in nus:
        ps=[p for p in panels if p[3]-1e-8<=nu<=p[4]+1e-8];c.require(len(ps)==1,'unique actual panel')
        k,header,payload,lo,hi=ps[0];vals.append(c.sample_od(header,payload,nu));sm.append({'nu':nu,'panel':k})
        if k not in saved:
            gz(PKG/f'OD/{arm}.{k}.header.gz',header);gz(PKG/f'OD/{arm}.{k}.payload.gz',payload);saved.add(k)
    samples[arm]=vals;samplemeta[arm]=sm
js(PKG/'samples.json',samplemeta)
# Whole 45-layer science readback OFF/ON and prior executable probe under same IOD2 input.
files=[];total=0
for layer in range(1,46):
    streams=[list(records(BASE/f'case-{n}/ODexact_{layer:03d}')) for n in ('probe','h-off','h')]
    c.require(all(len(s)==len(streams[0]) for s in streams),'record totals')
    science=all(a==b==d for a,b,d in zip(*(s[1:] for s in streams)));c.require(science,'all actual scientific records passive')
    headers=streams[0][0];c.require(len(headers)==1416,'scope FILHDR')
    diffs={name:[j for j,(a,b) in enumerate(zip(headers,s[0])) if a!=b] for name,s in zip(('probe','h-off','h'),streams)}
    c.require(all(1336<=j<1352 for v in diffs.values() for j in v),'only date/time header differences')
    files.append({'layer':layer,'records':len(streams[0]),'science_identical':science,'header_difference_offsets0':diffs,
      'science_sha256':sha(b''.join(streams[0][1:])),'whole_file_equal':all(s==streams[0] for s in streams)})
    total+=len(streams[0])-1
js(PKG/'passivity.json',{'root_read_all_45_OD_files':True,'saved_CI_reopens_full_OD':False,'science_records':total,'science_identical':True,
  'comparisons':['prior PR164 executable IOD2 probe','new observer OFF','new observer ON'],
  'whole_file_status':'FAIL_PRESERVED_TIMESTAMP_DIFFERENCES','files':files,'production_accepted':False})
arms={a:c.analyze_arm(traces[a],mins[a],blocks,a) for a in c.ARMS}
js(PKG/'contributions.json',{a:v['contributors'] for a,v in arms.items()})
res=c.result(arms,samples);js(PKG/'result.json',res)
for n in ('plan.json','probe.json','preparation.json','execution-identity.json','object-comparison.json','build-result.json','build-launch.json'):
    shutil.copy2(BASE/n,PKG/n)
for name in ('probe','h-off',*c.ARMS):
    for suffix in ('result.json','launch.json','stdout','stderr'):
        p=BASE/f'solver-{name}-{suffix}' if suffix.endswith('.json') else BASE/f'solver-{name}.{suffix}'
        dest=PKG/'runtime'/p.name;dest.parent.mkdir(exist_ok=True);shutil.copy2(p,dest)
    shutil.copy2(BASE/f'case-{name}-inputs.json',PKG/'runtime'/f'case-{name}-inputs.json')
    gz(PKG/f'inputs/{name}.TAPE5.gz',(BASE/f'case-{name}/TAPE5').read_bytes())
    gz(PKG/f'inputs/{name}.TAPE6.gz',(BASE/f'case-{name}/TAPE6').read_bytes())
for n in ('build.stdout','build.stderr','observer.patch'):
    shutil.copy2(BASE/n,PKG/n)
gz(PKG/'source/oprop.observer.f90.gz',(BASE/'oprop.observer.f90').read_bytes())
for n in ('run_common.py','probe.py','prepare.py','execute.py','readback.py'):
    p=PKG/'root-execution'/n;p.parent.mkdir(exist_ok=True);shutil.copy2(BASE/n,p)
print(json.dumps({'arms':res['arms'],'comparisons':res['comparisons'],'passive_science_records':total},indent=2))
