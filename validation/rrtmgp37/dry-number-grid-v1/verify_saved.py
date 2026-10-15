"""Replay the opt-in candidate's saved module/SCM evidence, without a solver."""
import gzip,hashlib,importlib.util,json,math,struct
from pathlib import Path
B=Path(__file__).resolve().parent;ROOT=B.parents[2]
def require(ok,msg):
 if not ok:raise ValueError(msg)
def sha(raw):return hashlib.sha256(raw).hexdigest()
def load(path,name):
 s=importlib.util.spec_from_file_location(name,path);m=importlib.util.module_from_spec(s);s.loader.exec_module(m);return m
def read(name):return gzip.decompress((B/name).read_bytes())
def f32(x):return struct.unpack('<f',struct.pack('<f',x))[0]
def raw_capture(raw):
 lines=raw.decode().splitlines();require(lines[0] in ('RRTMGP_UDM_ENTRY_DENSITY_V2','RRTMGP_UDM_RADIUS_V1'),'capture magic')
 header=list(map(int,lines[1].split()));require(len(header)==6 and header[2:]==[1,1,1,59],'capture coordinates')
 d={};i=2
 while i<len(lines):
  w=lines[i].split();require(len(w)==2 and w[0] not in d,'capture field roster');n=int(w[1]);values=[float(x) for x in lines[i+1:i+1+n]]
  require(len(values)==n and all(math.isfinite(x) for x in values),'capture finite extent');d[w[0]]=values;i+=n+1
 require(d['HOST_NUMBER_POLICY']==[1.],'host encoding is not explicit')
 return header,d

def verify(package=B):
 require(package==B,'fixed candidate replay package')
 manifest=json.loads((B/'manifest.json').read_text());require(manifest['production_accepted'] is False,'false production approval')
 actual={str(p.relative_to(B)) for p in B.rglob('*') if p.is_file() and p.name!='manifest.json' and '__pycache__' not in p.parts}
 require(actual==set(manifest['files']),'package file roster')
 for name,row in manifest['files'].items():
  p=B/name;require(not p.is_symlink() and len(p.read_bytes())==row['bytes'] and sha(p.read_bytes())==row['sha256'],'sealed file changed '+name)
 history=load(ROOT/'validation/rrtmgp37/historical-source/binding.py','history')
 identity=json.loads((B/'saved/build/identity.json').read_text());require(identity['production_accepted'] is False,'false execution approval')
 for name,row in identity['source_files'].items():
  require(sha(history.historical_bytes(ROOT,name,row['sha256']))==row['sha256'],'retained candidate source differs '+name)
  require(sha(read('saved/current-source/'+name+'.gz'))==row['sha256'],'compiled-source snapshot differs')
 corpus=json.loads((ROOT/'validation/rrtmgp37/connected-host-number/source/tracked-WRF-corpus.json').read_text())
 changed=set(identity['source_files']);require(len(changed)==7,'candidate source scope')
 supporting=identity['supporting_test_files']
 for name,row in supporting.items():require(sha(history.historical_bytes(ROOT,name,row['sha256']))==row['sha256'],'retained fixture stub differs')
 changed |= set(supporting)
 for row in corpus['files']:
  if row['path'] not in changed:require(sha(history.historical_bytes(ROOT,row['path'],row['sha256']))==row['sha256'],'retained unlisted production source changed')
 require(sha(read('saved/build/wrf.gz'))==identity['executable']['sha256'],'executed binary changed')
 require(sha(read('saved/build/ideal.gz'))==identity['ideal_executable']['sha256'],'ideal binary changed')
 dependencies=json.loads((B/'saved/test-source-pins.json').read_text())
 for name,digest in dependencies.items():require(sha(history.historical_bytes(ROOT,name,digest))==digest,'retained test dependency changed')
 bridge=load(ROOT/'WRF/test/rrtmgp/test_udm_dry_number_bridge.py','bridge');partial=load(ROOT/'WRF/test/rrtmgp/test_udm_partial_activation.py','partial')
 module=json.loads((B/'saved/module/receipt.json').read_text());require(module['status']=='PASS_SCOPED_DRY_NUMBER_BRIDGE','module status')
 require(module['source_sha256']==identity['source_files']['WRF/phys/module_mp_udm.F']['sha256'],'module/current source mismatch')
 rows=0
 for opt in ('O0','O2'):
  commands=module['processes'];start=0
  for case in ('wet','dry','cold','bounds'):
   data={}
   for policy in (0,1):
    matches=[(n,c) for n,c in enumerate(commands,1) if c['kind']=='actual_UDM_'+case+'_policy'+str(policy) and ('/'+opt+'/') in c['argv'][0]]
    require(len(matches)==1,'paired command roster')
    number,cmd=matches[0];require(cmd['status']=='TERMINAL' and cmd['actual_returncode']==0 and not cmd['timed_out'],'fixture not successful')
    d=partial.parse(read(f'saved/module/command-{number:02d}.stdout.gz').decode())
    d['returns']={c:[struct.unpack('!f',bytes.fromhex(x))[0] for x in v] for c,v in d['outputs'].items()};data[policy]=d
   computed=bridge.compare(data[0],data[1],case);require(computed==module['results'][opt][case]['rows'],'declared paired results differ');rows+=len(computed)
   if case=='wet':require(len(partial.check(data[0]))==12,'partial-CF/activation evidence')
 require(rows==32 and module['UDM_calls']==64,'module execution count')
 scm=json.loads((B/'saved/scm/receipt.json').read_text());require(scm['status']=='PASS_SCOPED_POLICY1_SCM_RESTART' and scm['history_variables_compared']==211,'SCM restart comparison')
 require(scm['executable']['sha256']==identity['executable']['sha256'],'SCM executable/source mismatch')
 for number,cmd in enumerate(scm['processes'],1):
  text=read(f'saved/scm/command-{number:02d}.stdout.gz').decode(errors='replace')
  if number<=2:require('SUCCESS COMPLETE WRF' in text and 'FATAL CALLED' not in text,'SCM not successful')
  else:require(('UDM number representation differs' in text or 'Malformed UDM number policy metadata' in text) and 'FATAL CALLED' in text,'representation rejection not exercised')
 require(len(scm['processes'])==6,'SCM command count')
 live=json.loads((B/'saved/live/receipt.json').read_text());require(live['history_bytes_equal'] is True and live['executable']['sha256']==identity['executable']['sha256'],'live noninterference or identity')
 require(read('saved/scm/control/wrfout_d01_1999-10-22_19:00:00.gz')==read('saved/live/trace/wrfout_d01_1999-10-22_19:00:00.gz'),'raw history noninterference')
 cold=0;radius=0;max_relative=0.
 for step in range(1,13):
  he,e=raw_capture(read(f'saved/live/capture/udm_entry_density_d1_i1_j1_step{step}.raw.gz'))
  hr,r=raw_capture(read(f'saved/live/capture/udm_radius_d1_i1_j1_step{step}.raw.gz'));require(he==hr and he[1]==step,'call/coordinate linkage')
  require(e['DEN_PASSED_KG_M3']==r['SOURCE_RHO'],'one-call density differs')
  if step==1:
   require(e['NN_RAW']==[f32(1.e8/x) for x in e['DEN_PASSED_KG_M3']],'cold eta background');cold=len(e['NN_RAW'])
  require(r['NATIVE_NC_RECONSTRUCTED']==[f32(n*x) for n,x in zip(r['SOURCE_QNC'],r['SOURCE_RHO'])],'native number reconstruction')
  for qc,nc,rho,rec in zip(r['SOURCE_QC'],r['NATIVE_NC_RECONSTRUCTED'],r['SOURCE_RHO'],r['SOURCE_RE_CLOUD']):
   if qc*rho>1.e-12 and nc*rho>1.e-6:
    expected=max(f32(2.51e-6),min(.5/(math.pi*1000./6.*nc/(qc*rho))**(1./3.),f32(50.e-6)))
    relative=abs(expected-rec)/rec;require(relative<2.e-6,'radius consumes wrong number scale');radius+=1;max_relative=max(max_relative,relative)
 legacy=json.loads((B/'saved/legacy/receipt.json').read_text());require(legacy['variables_bitwise_equal']==211 and legacy['all_13_times_compared'] is True,'default legacy regression')
 ideal=json.loads((B/'saved/ideal-guard/receipt.json').read_text());require(ideal['status']=='PASS_SCOPED_UNIMPLEMENTED_PRODUCER_REFUSAL','producer status')
 require('input/boundary producer is not implemented' in read('saved/ideal-guard/command-01.stdout.gz').decode(errors='replace'),'producer falsely labels eta')
 closure=json.loads((B/'closure-conditions.json').read_text());old=json.loads((ROOT/'validation/rrtmgp37/omitted-ice-effect/closure-conditions.json').read_text());require(closure==old,'seven original conditions changed')
 policy=json.loads((B/'policy.json').read_text());require(policy['id']=='dry-number-grid-v1' and policy['implementation']=='OPT_IN_RESEARCH_CANDIDATE' and policy['production_accepted'] is False,'candidate wrongly promoted')
 return {'status':'PASS_SCOPED_DRY_NUMBER_GRID_V1_CANDIDATE','manufactured_module_pairs':rows,'manufactured_UDM_calls':64,'SCM_restart_variables_bitwise_equal':211,'legacy_default_variables_bitwise_equal':211,'live_calls':12,'cold_background_layers':cold,'radius_layers_checked':radius,'radius_reconstruction_max_relative_difference':max_relative,'expected_representation_rejections':4,'ideal_producer_refused':True,'CI_fresh_solver_runs':0,'source_scope':'historical_snapshot','current_fix_certified':False,'physical_gate_closed':False,'production_accepted':False}
if __name__=='__main__':print(json.dumps(verify()))
