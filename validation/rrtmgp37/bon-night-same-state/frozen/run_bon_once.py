#!/usr/bin/env python3
"""One-use three-arm BON audit. Default is pure preflight; no model fallback/retry."""
import argparse,csv,datetime as dt,hashlib,importlib.util,json,math,os,re,resource,signal,subprocess,sys,time
from pathlib import Path
import numpy as np
from netCDF4 import Dataset
sys.dont_write_bytecode=True
HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[1]
BUILD=ROOT/'build/udm37-export-selection-serial-build-v1'
SRC=BUILD/'source'
HEAD='f731bb993a86a1836a64152d9b936edb7c315c19'
ARMS=('OFF','ON_native4_0','ON_native4_1')
PLAN=HERE/'plan.json';MANIFEST=HERE/'stage-manifest.json';READBACK=HERE/'stage-readback.json'
SPEC=HERE/'runtime-spec.json';IDENTITY=HERE/'runtime-build-identity.json';AUTH=HERE/'root-execution-authorization.json'
RECEIPT=HERE/'execution-receipt.json';LOCK=HERE/'.one-use-forecast.lock'
TIMES=('2000-01-25_00:00:00','2000-01-25_01:00:00');CP_INPUT='wrfrst_d01_'+TIMES[0]
MODEL_PATH='/usr/bin:/bin:/usr/sbin:/sbin'
LD_PATH=str(ROOT/'build/deps/netcdf/lib')+':'+str(ROOT/'build/deps/root/usr/lib/x86_64-linux-gnu')
STACK=512*1024*1024
SEL_PREFIX='WRF_RRTMGP_RRTMG4_EXPORT_'
CSV_HEADER='phase,domain,step,source_seconds,i,j,metric,value37,value4,sample_count,mean37,sd37,mean4,sd4,sd_delta,radius_mode,scope'.split(',')

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(p):
 p=Path(p);return {'path':str(p.absolute()),'sha256':sha(p),'size_bytes':p.stat().st_size}
def chk(r):
 if pin(r['path'])!=r:raise RuntimeError('file pin drift '+r['path'])
def atomic(p,obj,exclusive=False):
 p=Path(p)
 if exclusive and (p.exists() or p.is_symlink()):raise FileExistsError(p)
 tmp=p.with_name(p.name+'.tmp.'+str(os.getpid()))
 with tmp.open('x') as f:json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p);fd=os.open(p.parent,os.O_RDONLY)
 try:os.fsync(fd)
 finally:os.close(fd)
def utc():return dt.datetime.now(dt.timezone.utc).isoformat()
def load_module(name,p):
 s=importlib.util.spec_from_file_location(name,p);m=importlib.util.module_from_spec(s);sys.modules[name]=m;s.loader.exec_module(m);return m

def helpers(spec):
 for r in spec['helpers'].values():chk(r)
 return (load_module('bon_stage_helper',HERE/'prepare_stage.py'),load_module('bon_nc_helper',spec['helpers']['original_nc_helper']['path']),load_module('bon_export_reader',HERE/'read_export_context.py'))

def static(spec,empty_arms=ARMS):
 for r in spec['stage_pins'].values():chk(r)
 for r in spec['helpers'].values():chk(r)
 p=json.loads(PLAN.read_text());m=json.loads(MANIFEST.read_text());r=json.loads(READBACK.read_text())
 if m['plan']['sha256']!=sha(PLAN) or r['plan']['sha256']!=sha(PLAN) or r['manifest']['sha256']!=sha(MANIFEST):raise RuntimeError('stage pin join')
 if p['source_reference']['head']!=HEAD or p['checkpoint']['ITIMESTEP']!=720 or p['checkpoint']['XTIME_minutes']!=720.:raise RuntimeError('source/checkpoint clock')
 # Only pending arms must be output-empty; completed arms still have exact original input pins.
 for a,x in p['arms'].items():
  case=Path(x['case_path'])
  for n,v in x['immutable_entries'].items():
   q=case/n
   if v['kind']=='symlink':
    if not q.is_symlink() or os.readlink(q)!=v['link_text'] or pin(q.resolve(strict=True))!=v['target']:raise RuntimeError('static binding '+a+'/'+n)
   elif q.is_symlink() or pin(q)!=v['pin']:raise RuntimeError('copied input changed '+a+'/'+n)
  if (case/'wrf.exe').exists() or (case/'wrf.exe').is_symlink():raise RuntimeError('no executable link permitted; direct fresh ELF only')
  if a in empty_arms:
   expected=set(x['immutable_entries'])|{'trace'}|({'audit'} if a!='OFF' else set())|({'legacy-export'} if a=='ON_native4_1' else set())
   if {q.name for q in case.iterdir()}!=expected:raise RuntimeError('pending arm contains outputs '+a)
   for folder in ['trace']+(['audit'] if a!='OFF' else [])+(['legacy-export'] if a=='ON_native4_1' else []):
    if any((case/folder).iterdir()):raise RuntimeError('pending capture folder nonempty '+a+'/'+folder)
  nml=(case/'namelist.input').read_text()
  loader=str(SRC/'WRF/run')
  if not re.search(r"(?m)^\s*rrtmgp_data_path\s*=\s*'"+re.escape(loader)+r"'\s*,",nml):raise RuntimeError('actual coefficient loader path')
 # Original donor snapshot binds inputs/links/table, independent of case output state.
 stage=load_module('bon_static_stage',HERE/'prepare_stage.py')
 if stage.donor_snapshot()!=p['donor_snapshot']:raise RuntimeError('donor snapshot changed')
 for r in p['future_build']['actual_fresh_coefficient_files_at_stage'].values():chk(r)
 chk(p['frozen_table']);chk(p['checkpoint']['pin']);chk(p['boundary']['pin'])
 return {'status':'STATIC_STAGE_PASS','pending_output_empty_arms':list(empty_arms),'immutable_entry_counts':{a:v['immutable_entry_count'] for a,v in p['arms'].items()},'checkpoint':p['checkpoint']['pin'],'table':p['frozen_table'],'coefficient_files':p['future_build']['actual_fresh_coefficient_files_at_stage']}

def closure(exe):
 q=subprocess.run(['/usr/bin/ldd',str(exe)],env={'PATH':MODEL_PATH,'LD_LIBRARY_PATH':LD_PATH,'LANG':'C','LC_ALL':'C'},stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,timeout=30)
 if q.returncode or 'not found' in q.stdout:raise RuntimeError('ldd failed or unresolved library')
 libs=[]
 for line in q.stdout.splitlines():
  m=re.match(r'\s*(\S+)\s+=>\s+(/\S+)',line)
  if m:soname,path=m.groups()
  else:
   m=re.match(r'\s*(/\S+)\s+\(',line)
   if not m:continue
   path=m.group(1);soname=Path(path).name
  r=pin(Path(path).resolve());r['soname']=soname;libs.append(r)
 if any('mpi' in r['soname'].lower() or 'gomp' in r['soname'].lower() for r in libs):raise RuntimeError('requires true serial ELF without MPI/OpenMP dynamic closure')
 return sorted(libs,key=lambda r:(r['soname'],r['path']))

def build_snapshot(identity=None):
 if identity is not None:
  chk(identity['runtime_spec']);chk(identity['runner'])
 receipt=BUILD/'build-receipt.json'
 if not receipt.is_file():return {'status':'PENDING_BUILD','reason':'build receipt absent'}
 b=json.loads(receipt.read_text())
 if b.get('status')!='BUILD_PASS':return {'status':'PENDING_BUILD','observed_status':b.get('status')}
 if b.get('returncode')!=0 or b.get('build_invocations')!=1 or b.get('model_invocations')!=0 or not b.get('serial_compile_log_controls'):raise RuntimeError('actual fresh build acceptance')
 manifest=BUILD/'source-manifest.json';tools=BUILD/'toolchain-dependency-inventory.json'
 sm=json.loads(manifest.read_text());ti=json.loads(tools.read_text())
 if sm['commit']!=HEAD or b['source_checks']['source_head']!=HEAD or b['post_source_checks']['source_head']!=HEAD:raise RuntimeError('built source HEAD')
 for k,f in [('source_manifest_sha256',manifest),('toolchain_inventory_sha256',tools)]:
  if sha(f)!=b['source_checks'][k] or sha(f)!=b['post_source_checks'][k]:raise RuntimeError('build inventory digest')
 for r in sm['tracked_files']:
  p=SRC/r['path']
  if r['git_mode']=='120000':
   if not p.is_symlink():raise RuntimeError('tracked symlink type drift '+r['path'])
   data=os.readlink(p).encode()
  else:
   if p.is_symlink() or not p.is_file():raise RuntimeError('tracked regular type drift '+r['path'])
   data=p.read_bytes()
  if hashlib.sha256(data).hexdigest()!=r['sha256'] or len(data)!=r['size_bytes']:raise RuntimeError('tracked built source drift '+r['path'])
 conf=SRC/'WRF/configure.wrf'
 if sha(conf)!=sm['configure_wrf']['sha256'] or sha(conf)!=b['post_source_checks']['configure_sha256']:raise RuntimeError('compiled configuration pin')
 txt=conf.read_text()
 if 'DMPARALLEL      =       # 1' not in txt or 'OMP             =       # -fopenmp' not in txt:raise RuntimeError('serial config')
 exe=SRC/'WRF/main/wrf.exe';er=b['executables']['wrf.exe']
 if Path(er['path'])!=exe or exe.read_bytes()[:4]!=b'\x7fELF' or sha(exe)!=er['sha256'] or exe.stat().st_size!=er['size_bytes']:raise RuntimeError('fresh ELF pin; no fallback')
 for r in ti['runtime_libraries']:
  if pin(r['path'])!={k:r[k] for k in ['path','sha256','size_bytes']}:raise RuntimeError('shared dependency drift')
 for r in ti['tools'].values():
  if sha(r['resolved_path'])!=r['sha256']:raise RuntimeError('build tool drift')
 libs=closure(exe)
 expected=sorted(er['runtime_libraries'],key=lambda r:(r['soname'],r['path']))
 if libs!=expected:raise RuntimeError('actual normalized ELF runtime closure differs from completed build')
 objs={n:pin(SRC/'WRF'/n) for n in ['phys/module_ra_rrtmgp_audit.o','phys/module_radiation_driver.o','phys/module_ra_rrtmg_lw.o','phys/module_ra_rrtmg_sw.o']}
 snap={'status':'BUILD_PASS_LIVE_BOUND','build_receipt':pin(receipt),'source_manifest':pin(manifest),'toolchain_inventory':pin(tools),'source_head':HEAD,'tracked_source_count':len(sm['tracked_files']),'configure':pin(conf),'executable':pin(exe),'runtime_libraries':libs,'observer_driver_objects':objs,'controlled_environment':{'PATH':MODEL_PATH,'LD_LIBRARY_PATH':LD_PATH,'NETCDF':str(ROOT/'build/deps/netcdf')}}
 if identity is not None and snap!=identity['snapshot']:raise RuntimeError('immutable build/source/executable/dependency snapshot changed')
 return snap

def parse_capture(path,kind,raw_context=(13,46,32)):
 lines=path.read_text().splitlines();magic=lines[0].strip();head=lines[1].split()
 if kind=='raw':
  if magic!='RRTMGP_RAW_V1' or len(head)!=4 or head[0].upper() not in ['LW','SW'] or tuple(map(int,head[1:]))!=raw_context:raise RuntimeError('selected raw schema/native index')
 else:
  if (kind=='result' and magic!='RRTMGP_RESULT_V1') or (kind=='input' and magic not in ['RRTMGP_REPLAY_V8','RRTMGP_REPLAY_V9','RRTMGP_REPLAY_V10','RRTMGP_REPLAY_V11']):raise RuntimeError('production capture schema')
  if head[0].upper() not in ['LW','SW'] or int(head[1])!=1 or int(head[2])<32:raise RuntimeError('production capture selected-column header')
 values={};i=2
 while i<len(lines):
  if not lines[i].strip():i+=1;continue
  h=lines[i].split();i+=1
  if len(h)<2 or h[0] in values:raise RuntimeError('capture record duplicate/header')
  dims=[int(x) for x in h[1:]]
  if any(d<=0 for d in dims):raise RuntimeError('capture record shape')
  count=math.prod(dims);vs=[]
  while len(vs)<count and i<len(lines):
   vs.extend(float(x.replace('D','E').replace('d','e')) for x in lines[i].split());i+=1
  if len(vs)!=count or not np.isfinite(vs).all():raise RuntimeError('capture numeric count/finite')
  values[h[0]]={'shape':dims,'values':vs}
 return head[0].upper(),values

def capture_roster(case):
 folder=case/'trace'; raws=sorted(folder.glob('*.raw'));groups=[];used=set();keys=set()
 for raw in raws:
  phase,data=parse_capture(raw,'raw');step=data['RADIATION_STEP']['values'];secs=data['SOURCE_TIME_SECONDS']['values']
  if len(step)!=1 or step[0]!=int(step[0]) or len(secs)!=1 or not 43200<=secs[0]<=46800:raise RuntimeError('actual raw call clock')
  key=(phase,int(step[0]),secs[0])
  if key in keys:raise RuntimeError('duplicate production call key')
  keys.add(key);files={}
  for suffix in ['raw','input','result']:
   p=raw.with_suffix('.'+suffix);pp,fields=parse_capture(p,suffix)
   if pp!=phase:raise RuntimeError('capture phase joins')
   used.add(p.name);files[suffix]=pin(p)
  groups.append({'phase':phase,'step':key[1],'source_seconds':key[2],'files':files})
 if not groups or not any(g['phase']=='LW' for g in groups):raise RuntimeError('required actual LW production captures absent')
 if {p.name for p in folder.iterdir()}!=used:raise RuntimeError('unmatched capture files')
 return sorted(groups,key=lambda g:(g['source_seconds'],g['step'],g['phase']))

def selector_from_off(groups):
 g=next(g for g in groups if g['phase']=='LW')
 s={'domain':1,'i':13,'j':46,'step':g['step'],'source_seconds':g['source_seconds']}
 if s['step']<1 or not math.isfinite(s['source_seconds']) or s['source_seconds']<0:raise RuntimeError('export selector invalid')
 return {'selector':s,'environment':{SEL_PREFIX+'DOMAIN':'1',SEL_PREFIX+'I':'13',SEL_PREFIX+'J':'46',SEL_PREFIX+'STEP':str(s['step']),SEL_PREFIX+'SECONDS':format(s['source_seconds'],'.17g')},'selection_basis':'first actually captured OFF LW call, sorted by source_seconds/step; no desired flux criterion','off_raw_pin':g['files']['raw']}

def audit_rows(case,arm,groups):
 p=case/'audit/same_state.csv'
 with p.open() as f:
  q=csv.DictReader(f)
  if q.fieldnames!=CSV_HEADER:raise RuntimeError('audit CSV schema')
  rows=list(q)
 if not rows:raise RuntimeError('empty audit CSV')
 indexed={};calls={};clockset={(g['step'],g['source_seconds']) for g in groups if g['phase']=='LW'}
 for r in rows:
  nums={n:float(r[n]) for n in CSV_HEADER if n not in ['phase','metric','scope']}
  if not all(math.isfinite(v) for v in nums.values()) or any(nums[n]<0 for n in ['sd37','sd4','sd_delta']):raise RuntimeError('audit finite/SD')
  if any(nums[n]!=int(nums[n]) for n in ['domain','step','i','j','sample_count','radius_mode']):raise RuntimeError('CSV integer context')
  phase=r['phase'].upper();point=(int(nums['i']),int(nums['j']));clock=(int(nums['step']),nums['source_seconds'])
  if phase not in ['LW','SW'] or int(nums['domain'])!=1 or point not in [(13,46),(0,0)] or r['scope']!='selected_column' or nums['sample_count']!=128 or nums['radius_mode']!=int(arm[-1]) or clock not in clockset:raise RuntimeError('audit context/samples/radius/actual call join')
  key=(phase,*clock,*point,r['metric'])
  if key in indexed:raise RuntimeError('duplicate audit metric')
  indexed[key]=r;calls.setdefault((phase,*clock,*point),set()).add(r['metric'])
 for (ph,step,sec,i,j),metrics in calls.items():
  want={'SURFACE_DOWN','TOA_UP'}|{f'HEAT_{k}' for k in range(1,33)}|({'SW_NET','SW_DIRECT'} if ph=='SW' else set())
  if metrics!=want:raise RuntimeError('audit metric roster incomplete')
 for clock in clockset:
  for phase in ['LW','SW']:
   if not all((phase,*clock,*point) in calls for point in [(13,46),(0,0)]):raise RuntimeError('audit missing paired cell/mean call')
 rawkeys={(g['phase'],g['step'],g['source_seconds']) for g in groups};csvkeys={(ph,step,sec) for ph,step,sec,i,j in calls}
 missing=csvkeys-rawkeys
 if any(ph!='SW' for ph,_,_ in missing) or rawkeys-csvkeys:raise RuntimeError('CSV vs production capture clock mismatch')
 for k,r in indexed.items():
  if k[:3] in missing and any(float(r[n])!=0. for n in ['value37','value4','mean37','sd37','mean4','sd4','sd_delta']):raise RuntimeError('uncaptured SW must be zero-valued night audit, not synthesized daylight')
 return {'file':pin(p),'row_count':len(rows),'calls':[list(k) for k in sorted(csvkeys)],'night_SW_zero_calls_without_capture':[list(k) for k in sorted(missing)],'scope':'allsky audit; SW no solver/capture at night according to source guard'},indexed

def clean_env(arm,plan,identity,sel):
 e={'PATH':MODEL_PATH,'LD_LIBRARY_PATH':LD_PATH,'NETCDF':str(ROOT/'build/deps/netcdf'),'HOME':os.environ.get('HOME','/home/korea_keun'),'LANG':'C','LC_ALL':'C','OMP_NUM_THREADS':'1','OPENBLAS_NUM_THREADS':'1','OMP_NESTED':'FALSE'}
 e.update(plan['arms'][arm]['environment_overrides_pending_runtime_closure'])
 if arm=='ON_native4_1':
  if sel is None:raise RuntimeError('no frozen observed OFF selector')
  e.update(sel['environment']);e[SEL_PREFIX+'DIR']=str(HERE/'cases'/arm/'legacy-export')
 return e

def auth(spec,identity):
 a=json.loads(AUTH.read_text())
 expected={'schema':'BON_NIGHT_SERIAL_AUDIT_AUTH_V2','status':'AUTHORIZED_ONCE','runner_sha256':sha(__file__),'runtime_spec_sha256':sha(SPEC),'runtime_identity_sha256':sha(IDENTITY),'plan_sha256':sha(PLAN),'arm_names':list(ARMS),'maximum_model_invocations':3,'timeout_per_arm_seconds':600}
 for k,v in expected.items():
  if a.get(k)!=v:raise RuntimeError('authorization binding '+k)
 return pin(AUTH)

def stop(proc):
 if proc is None:return None
 if proc.poll() is None:
  try:os.killpg(proc.pid,signal.SIGTERM)
  except ProcessLookupError:pass
  try:return proc.wait(timeout=15)
  except subprocess.TimeoutExpired:
   try:os.killpg(proc.pid,signal.SIGKILL)
   except ProcessLookupError:pass
 return proc.wait()

def log_gate(case):
 logs=sorted(case.glob('rsl.*')); stdout=case/'wrf.stdout.log'; allpaths=[stdout]+logs
 hits=[];ranks=set()
 for p in allpaths:
  text=p.read_text(errors='replace')
  if any(t in text for t in ['FATAL CALLED FROM FILE','APPLICATION CALLED MPI_ABORT','ERROR: FATAL','RRTMGP_FATAL','RRTMGP_TRACE_']):hits.append(p.name)
  if 'SUCCESS COMPLETE WRF' in text:
   if p==stdout:ranks.add(0)
   else:
    m=re.search(r'(\d+)$',p.name)
    if m:ranks.add(int(m.group(1)))
 if hits or ranks!={0}:raise RuntimeError('fatal log/unique serial success gate')
 return {'success_ranks_deduplicated':sorted(ranks),'logs':[pin(p) for p in allpaths]}

def validate_arm(arm,receipt,spec,identity,nc,reader,selector):
 case=HERE/'cases'/arm; rec=receipt['arms'][arm]
 rec['log_validation']=log_gate(case)
 histories=sorted(case.glob('wrfout_d01_*'));newcp=sorted(p for p in case.glob('wrfrst_d01_*') if p.name!=CP_INPUT)
 want=['wrfout_d01_'+t for t in TIMES]
 if [p.name for p in histories]!=want or [p.name for p in newcp]!=['wrfrst_d01_'+TIMES[-1]]:raise RuntimeError('exact output filename/time roster')
 rec['quality']=[nc.verify_history(p,p.name.split('_d01_',1)[1]) for p in histories+newcp]
 rec['captures']=capture_roster(case)
 rec['outputs']={p.name:pin(p) for p in histories+newcp}
 if arm=='OFF':
  if (case/'audit').exists():raise RuntimeError('OFF audit directory/CSV forbidden')
 else:
  rec['audit'],rows=audit_rows(case,arm,rec['captures'])
  off=receipt['arms']['OFF']
  for n,r in rec['outputs'].items():
   q=nc.compare_netcdf(Path(off['outputs'][n]['path']),Path(r['path']))
   q['whole_file_equal']=off['outputs'][n]['sha256']==r['sha256']
   rec.setdefault('OFF_output_comparisons',[]).append(q)
   if q['status']!='PASS_EXACT' or not q['whole_file_equal']:raise RuntimeError('no-feedback full NetCDF/wholefile parity')
  def digest_roster(gs):return {(g['phase'],g['step'],g['source_seconds']):{s:p['sha256'] for s,p in g['files'].items()} for g in gs}
  if digest_roster(off['captures'])!=digest_roster(rec['captures']):raise RuntimeError('production capture no-feedback roster/fullbytes')
  if arm=='ON_native4_1':
   prev,a0=audit_rows(HERE/'cases/ON_native4_0','ON_native4_0',receipt['arms']['ON_native4_0']['captures'])
   if set(rows)!=set(a0):raise RuntimeError('radius CSV keysets')
   for k,r in rows.items():
    for n in ['value37','mean37','sd37']:
     if np.float64(float(r[n])).tobytes()!=np.float64(float(a0[k][n])).tobytes():raise RuntimeError('same37 mismatch between radius modes')
   exps=sorted((case/'legacy-export').glob('*'))
   if len(exps)!=1:raise RuntimeError('exactly one LW export expected; no night SW export')
   x=reader.read_export(exps[0],expected_phase='LW',expected_context=selector['selector'])
   rec['legacy_export']=reader.inventory(x);rec['legacy_export']['file']=pin(exps[0]);rec['same37_between_radius_arms']='PASS_BITWISE_SELECTED_CSV_FIELDS'
 rec['status']='PASS_ARM'


def completed_pins(receipt):
 # Generated references are immutable too: authenticate completed arms before subsequent launches.
 pins=[]
 for rec in receipt['arms'].values():
  pins.extend(rec.get('outputs',{}).values())
  for group in rec.get('captures',[]):pins.extend(group['files'].values())
  pins.extend(rec.get('log_validation',{}).get('logs',[]))
  if 'audit' in rec:pins.append(rec['audit']['file'])
  if 'legacy_export' in rec:pins.append(rec['legacy_export']['file'])
 if 'selector_pin' in receipt:pins.append(receipt['selector_pin'])
 for p in pins:chk(p)
 return {'status':'COMPLETED_OUTPUT_PINS_PASS','pin_count':len(pins)}


def execute(spec,identity):
 static(spec,ARMS);snap=build_snapshot(identity)
 if snap['status']!='BUILD_PASS_LIVE_BOUND':raise RuntimeError('no completed fresh build')
 ap=auth(spec,identity)
 if any(p.exists() for p in [LOCK,RECEIPT,HERE/'observed-export-selector.json']):raise FileExistsError('one-use claim exists; no retries')
 fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600);os.write(fd,(str(os.getpid())+'\n').encode());os.fsync(fd);os.close(fd)
 plan=json.loads(PLAN.read_text());_,nc,reader=helpers(spec)
 receipt={'schema':'bon-night-serial-audit-execution-v2','status':'RUNNING','started_utc':utc(),'authorization':ap,'runtime_identity':pin(IDENTITY),'model_invocations':0,'REAL_solver_build_invocations':0,'arms':{},'selector':None,'no_retries':True,'allsky_CSV_only':True}
 atomic(RECEIPT,receipt,exclusive=True);proc=None;arm=None
 try:
  for i,arm in enumerate(ARMS):
   proc=None
   receipt['arms'][arm]={'status':'PRELAUNCH_INVARIANT_PENDING','actual_invocations':0,'pid':None,'returncode':None,'timed_out':False}
   static(spec,ARMS[i:]);build_snapshot(identity);completed_pins(receipt);chk(ap)
   rec={'status':'PRELAUNCH','actual_invocations':0,'pid':None,'returncode':None,'timed_out':False,'started_utc':utc(),'controlled_environment':clean_env(arm,plan,identity,receipt['selector'])}
   receipt['arms'][arm]=rec;atomic(RECEIPT,receipt)
   exe=Path(identity['snapshot']['executable']['path']);case=HERE/'cases'/arm
   soft,hard=resource.getrlimit(resource.RLIMIT_STACK)
   if hard!=resource.RLIM_INFINITY and hard<STACK:raise RuntimeError('stack hard limit insufficient')
   resource.setrlimit(resource.RLIMIT_STACK,(STACK,hard));rec['master_stack_limit_bytes']=list(resource.getrlimit(resource.RLIMIT_STACK))
   error=None;rc=None
   try:
    with (case/'wrf.stdout.log').open('xb') as log:
     proc=subprocess.Popen([str(exe)],cwd=case,env=rec['controlled_environment'],stdout=log,stderr=subprocess.STDOUT,start_new_session=True)
     rec['pid']=proc.pid;rec['actual_invocations']=1;receipt['model_invocations']+=1;rec['status']='RUNNING'
     atomic(HERE/f'launch-{arm}.json',{'pid':proc.pid,'arm':arm,'actual_invocations':1,'command':[str(exe)],'started_utc':rec['started_utc']},exclusive=True);atomic(RECEIPT,receipt)
     try:rc=proc.wait(timeout=600)
     except subprocess.TimeoutExpired:rec['timed_out']=True;rc=stop(proc)
   except BaseException as e:error=repr(e);rc=stop(proc)
   rec.update({'returncode':rc,'ended_utc':utc(),'status':'PROCESS_COMPLETE','process_error':error})
   # Durable actual PID/RC/timeout precede every log hash, parse, postflight and scientific check.
   atomic(HERE/f'process-{arm}.json',{'arm':arm,'pid':rec['pid'],'returncode':rc,'timed_out':rec['timed_out'],'process_error':error,'ended_utc':rec['ended_utc']},exclusive=True);atomic(RECEIPT,receipt)
   if error or rc!=0 or rec['timed_out']:raise RuntimeError('model launch/returncode/timeout failed')
   static(spec,ARMS[i+1:]);build_snapshot(identity);completed_pins(receipt);chk(ap)
   validate_arm(arm,receipt,spec,identity,nc,reader,receipt['selector'])
   if arm=='OFF':
    sel=selector_from_off(rec['captures']);atomic(HERE/'observed-export-selector.json',sel,exclusive=True);receipt['selector']=sel;receipt['selector_pin']=pin(HERE/'observed-export-selector.json')
   else:chk(receipt['selector_pin'])
   static(spec,ARMS[i+1:]);build_snapshot(identity);completed_pins(receipt);atomic(RECEIPT,receipt)
  if receipt['model_invocations']!=3 or any(receipt['arms'][a]['actual_invocations']!=1 for a in ARMS):raise RuntimeError('actual three invocation count')
  static(spec,());build_snapshot(identity);receipt['final_completed_output_pins']=completed_pins(receipt);chk(ap);chk(receipt['selector_pin'])
  receipt.update({'status':'PASS_BON_NIGHT_OUTPUT_CAPTURE_AUDIT_LW_EXPORT','ended_utc':utc(),'final_immutable_snapshot':'PASS','interpretation':'selected nocturnal onehour allsky experiment; source-consistent diagnostic comparisons, not optical truth/observed bias causality'})
  atomic(RECEIPT,receipt);return 0
 except BaseException as e:
  rc=stop(proc)
  if arm and receipt['arms'][arm]['returncode'] is None and proc is not None:
   receipt['arms'][arm]['returncode']=rc;atomic(HERE/f'exception-process-{arm}.json',{'arm':arm,'pid':proc.pid,'returncode':rc,'error':repr(e)},exclusive=True)
  receipt.update({'status':'FAIL_PRESERVED_STOPPED_NO_RETRY','error':repr(e),'ended_utc':utc()})
  if arm:receipt['arms'][arm]['status']='FAIL_PRESERVED'
  try:receipt['finally_stage']=static(spec,());receipt['finally_build']=build_snapshot(identity);receipt['finally_completed_output_pins']=completed_pins(receipt)
  except BaseException as pe:receipt['finally_immutable_error']=repr(pe)
  atomic(RECEIPT,receipt);print(json.dumps({'status':receipt['status'],'error':repr(e),'model_invocations':receipt['model_invocations']}));return 1

def main():
 ap=argparse.ArgumentParser();ap.add_argument('--bind-build',action='store_true');ap.add_argument('--execute',action='store_true');args=ap.parse_args()
 if args.bind_build and args.execute:raise RuntimeError('binding and execution are separate operations')
 spec=json.loads(SPEC.read_text());checks=static(spec,ARMS)
 snap=build_snapshot()
 if args.bind_build:
  if snap['status']!='BUILD_PASS_LIVE_BOUND':raise RuntimeError('binding requires completed fresh BUILD_PASS')
  obj={'schema':'bon-night-runtime-build-identity-v2','snapshot':snap,'runtime_spec':pin(SPEC),'runner':pin(__file__)};atomic(IDENTITY,obj,exclusive=True);print(json.dumps({'status':'BUILD_IDENTITY_BOUND_NO_MODEL','identity':pin(IDENTITY)}));return 0
 if args.execute:
  if not IDENTITY.is_file():raise RuntimeError('no frozen completed build identity')
  identity=json.loads(IDENTITY.read_text())
  if identity['runtime_spec']!=pin(SPEC) or identity['runner']!=pin(__file__):raise RuntimeError('runtime identity binding')
  return execute(spec,identity)
 print(json.dumps({'status':'READY_STATIC_WAITING_BUILD_BINDING_AND_ROOT_REVIEW' if snap['status']!='BUILD_PASS_LIVE_BOUND' or not IDENTITY.exists() else 'READY_NOT_RUN','stage':checks,'build':snap['status'],'model_invocations':0,'execution_disabled_without_bound_identity_and_root_auth':True}));return 0
if __name__=='__main__':raise SystemExit(main())
