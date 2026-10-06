#!/usr/bin/env python3
"""Prepared one-use eight-call driver for the isolated CF0 sidecar reference experiment.
Default mode creates only a pin/argv plan. `--execute` requires an external root
authorization with exact runner/plan/case preflight pins; this file does not create
that authorization and the invocation gate itself is not considered one-use control.
"""
from __future__ import annotations
import argparse, hashlib, importlib.util, json, math, os, pathlib, signal, subprocess, sys, time
from datetime import datetime, timezone
import numpy as np
ROOT=pathlib.Path(__file__).resolve().parents[2]
HERE=pathlib.Path(__file__).resolve().parent
PRO=ROOT/'build/udm37-cf0-precip-audit-patch-proposal-v2'
BASE=ROOT/'build/udm37-cf0-precip-original-baseline-v1/runs-v2'
BUILD=ROOT/'build/udm37-cf0-precip-patch-build-v1'
EXE=BUILD/'reference_column'
DATA=ROOT/'build/udm-cu-optics-design-work/WRF/run'
FROZEN=ROOT/'build/udm-alternate-jan2000-data/paired-forecast-v2/ra37/frozen-ice-psd-moments.nc'
BASE_RECEIPT=BASE/'execution.json'
PROPOSAL_STATUS=PRO/'proposal-status.json'
PLAN=HERE/'invocation-plan.json'
STAGE=HERE/'stage-manifest.json'
EXEC=HERE/'execution.json'
LOCK=HERE/'execution.lock'
GATES=HERE/'gate-receipts'
CASES=HERE/'cases'
ZERO_ORDER=['rain-lw.zero','rain-sw.zero','snow-lw.zero','snow-sw.zero']
POS_ORDER=['rain-lw.positive','rain-sw.positive','snow-lw.positive','snow-sw.positive']
ENV={'PATH':'/usr/bin:/bin','LD_LIBRARY_PATH':str(ROOT/'build/deps/netcdf/lib')+':/usr/lib/x86_64-linux-gnu','OMP_NUM_THREADS':'1','OMP_DYNAMIC':'FALSE','OPENBLAS_NUM_THREADS':'1','WRF_RRTMGP_FROZEN_TABLE':'frozen.nc'}
TOKEN_SECTIONS={'LW':{'AUDIT_EXTRA_PRECIP_TAU'},'SW':{'AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW','AUDIT_EXTRA_PRECIP_SSA','AUDIT_EXTRA_PRECIP_G','AUDIT_DIRECT_PREDELTA'}}
MUTABLE={'LW':{'TOTAL_TAU','UP','DN','HR'},'SW':{'TOTAL_TAU','TOTAL_SSA','TOTAL_G','UP','DN','HR','DIRECT','DIFFUSE','VISDIR','VISDIF','NIRDIR','NIRDIF'}}

def now():return datetime.now(timezone.utc).isoformat()
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def pin(p):
 p=pathlib.Path(p).resolve(strict=True);return {'path':str(p),'size_bytes':p.stat().st_size,'sha256':sha(p)}
def atomic(p,obj):
 p=pathlib.Path(p);tmp=pathlib.Path(str(p)+'.tmp')
 with tmp.open('w') as f:json.dump(obj,f,indent=2,sort_keys=True,allow_nan=False);f.write('\n');f.flush();os.fsync(f.fileno())
 os.replace(tmp,p)
def imports_gate():
 s=importlib.util.spec_from_file_location('cf0_gate',PRO/'invocation_gate.py');m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m
def imports_validator():
 s=importlib.util.spec_from_file_location('cf0_validator',PRO/'validate_sidecar.py');m=importlib.util.module_from_spec(s);sys.modules[s.name]=m;s.loader.exec_module(m);return m

def runtime_closure():
 # Resolve dependencies under the exact minimal environment used by each child.
 if any(k in ENV for k in ('LD_PRELOAD','LD_AUDIT')):
  raise ValueError('dynamic-loader injection is forbidden')
 p=subprocess.run(['/usr/bin/ldd',str(EXE.resolve())],env=ENV,text=True,capture_output=True,check=True)
 resolved=set()
 for line in p.stdout.splitlines():
  if '=>' in line:
   rhs=line.split('=>',1)[1].strip().split()
   candidate=rhs[0] if rhs and rhs[0].startswith('/') else None
  else:
   # ldd reports the ELF interpreter without a `name => path` separator.
   first=line.strip().split()
   candidate=first[0] if first and first[0].startswith('/') else None
  if candidate:
   resolved.add(str(pathlib.Path(candidate).resolve(strict=True)))
 expected={x['path'] for x in json.loads((BUILD/'build-receipt.json').read_text())['resolved_runtime_libraries']}
 if resolved!=expected:
  raise ValueError(f'controlled-environment runtime closure differs from build pins: missing={sorted(expected-resolved)}, extra={sorted(resolved-expected)}')
 libs=[pin(x) for x in sorted(resolved)]
 return {'command':['/usr/bin/ldd',str(EXE.resolve())],'environment':ENV.copy(),'stdout_sha256':hashlib.sha256(p.stdout.encode()).hexdigest(),'resolved_libraries':libs,'count':len(libs)}

def read_result(path):
 lines=pathlib.Path(path).read_text(encoding='ascii').splitlines()
 if len(lines)<2 or lines[0].strip()!='RRTMGP_RESULT_V1':raise ValueError(f'{path}: bad result magic')
 h=lines[1].split()
 if len(h)!=3:raise ValueError(f'{path}: malformed result dimensions')
 phase=h[0];nc,nl=int(h[1]),int(h[2]);sections={};order=[];i=2
 while i<len(lines):
  if not lines[i].strip():i+=1;continue
  head=lines[i].split();i+=1
  if len(head)!=4:raise ValueError(f'{path}: malformed section header')
  name=head[0];shape=tuple(map(int,head[1:]));count=math.prod(shape)
  if name in sections or count<=0:raise ValueError(f'{path}: duplicate/empty section {name}')
  toks=[]
  while len(toks)<count and i<len(lines):
   row=lines[i].split();i+=1
   if not row:continue
   toks.extend(row)
   if len(toks)>count:raise ValueError(f'{path}: excess values for {name}')
  if len(toks)!=count:raise ValueError(f'{path}: truncated {name}')
  vals=np.asarray([float(x.replace('D','E').replace('d','e')) for x in toks],dtype=np.float64)
  if not np.isfinite(vals).all():raise ValueError(f'{path}: nonfinite values in {name}')
  sections[name]={'shape':shape,'tokens':toks,'values':vals.reshape(shape,order='F')};order.append(name)
 if not sections:raise ValueError(f'{path}: empty result')
 return {'phase':phase,'nc':nc,'nl':nl,'order':order,'sections':sections}

def validate_zero_case(approval,c):
 v=imports_validator()
 phase,nc,native_n,species,occ,rain,snow=v.decode(pathlib.Path(c['sidecar']['path']).read_text())
 raw_header,raw=v.parse_raw(pathlib.Path(c['raw']['path']))
 expected_species={'rain':1,'snow':2}[c['species']]
 if phase!=c['phase'] or raw_header[0]!=phase or nc!=1 or native_n!=raw_header[3] or species!=expected_species or occ!=1.0:
  raise ValueError('zero sidecar phase/shape/species/occurrence is not the frozen case')
 if native_n!=c['native_layers'] or c['engine_layers']<native_n:raise ValueError('zero sidecar layer contract mismatch')
 if any(k not in raw or len(raw[k])!=native_n for k in ('CF','RWP_OMITTED','SWP_OMITTED')):raise ValueError('raw capture lacks required native paths/CF')
 if any(not math.isfinite(x) for k in ('CF','RWP_OMITTED','SWP_OMITTED') for x in raw[k]):raise ValueError('raw capture has nonfinite CF/path')
 if any(x<0 for k in ('RWP_OMITTED','SWP_OMITTED') for x in raw[k]):raise ValueError('raw omitted path is negative')
 v.validate_payload(phase,nc,native_n,species,occ,rain,snow,[raw['CF']],c['engine_layers'])
 if any(x!=0.0 for row in rain+snow for x in row):raise ValueError('zero control sidecar contains a nonzero precipitation path')
 if rain!=[[0.0]*native_n] or snow!=[[0.0]*native_n]:raise ValueError('zero control sidecar is not exact all-zero payload')
 if c['species']=='snow':
  rows,cols,res=v.parse_input_matrix(pathlib.Path(c['input']['path']),'RES')
  if rows!=1 or cols!=c['engine_layers'] or res[:native_n]!=raw.get('RES'):
   raise ValueError('zero snow input radius prefix differs from its paired raw capture')
 if approval.get('campaign_mode')!='all-zero-control':raise ValueError('approval mode does not authorize the zero-control validator')
 return {'status':'ZERO_CASE_GATE_PASS','phase':phase,'species':c['species'],'native_layers':native_n,'engine_layers':c['engine_layers'],'all_zero':True,'raw_cf_exact':True}

def compare_positive(base_path,out_path,phase):
 b=read_result(base_path);c=read_result(out_path)
 if (b['phase'],b['nc'],b['nl'])!=(c['phase'],c['nc'],c['nl']) or phase!=b['phase']:raise ValueError('positive result identity differs')
 extras=TOKEN_SECTIONS[phase]
 if set(c['sections'])!=set(b['sections'])|extras:raise ValueError(f'positive section set mismatch: missing={sorted(set(b["sections"])-set(c["sections"]))}, extra={sorted(set(c["sections"])-set(b["sections"]))}')
 # Preserve all original result section ordering, allowing only additive audit sections.
 if [n for n in c['order'] if n in b['sections']]!=b['order']:raise ValueError('positive result reordered original sections')
 changed=[]
 for name,old in b['sections'].items():
  cur=c['sections'][name]
  if cur['shape']!=old['shape']:raise ValueError(f'positive shape changed for {name}')
  if name not in MUTABLE[phase] and cur['tokens']!=old['tokens']:
   raise ValueError(f'undeclared positive result change in {name}')
  if cur['tokens']!=old['tokens']:
   changed.append({'section':name,'max_abs_difference':float(np.max(np.abs(cur['values']-old['values']))),'declared_mutable':name in MUTABLE[phase]})
 for name in extras:
  sec=c['sections'][name]; arr=sec['values']
  expected_shape=tuple(b['sections']['PRECIP_TAU']['shape'])
  if name=='AUDIT_DIRECT_PREDELTA':expected_shape=tuple(b['sections']['DIRECT_PREDELTA']['shape'])
  if sec['shape']!=expected_shape:raise ValueError(f'audit section {name} shape {sec["shape"]} != expected {expected_shape}')
  if not np.isfinite(arr).all():raise ValueError(f'audit section {name} contains nonfinite data')
  if name in ('AUDIT_EXTRA_PRECIP_TAU','AUDIT_EXTRA_PRECIP_TAU_RAW') and np.any(arr<0):raise ValueError(f'{name} contains negative extinction')
  if name=='AUDIT_EXTRA_PRECIP_SSA' and np.any((arr<0)|(arr>1)):raise ValueError('audit SSA outside [0,1]')
  if name=='AUDIT_EXTRA_PRECIP_G' and np.any((arr< -1)|(arr>1)):raise ValueError('audit asymmetry outside [-1,1]')
  if not np.any(arr!=0.0):raise ValueError(f'positive sidecar produced an all-zero {name}')
 return {'status':'POSITIVE_OUTPUT_CONTRACT_PASS','phase':phase,'original_sections':len(b['order']),'added_sections':sorted(extras),'declared_changed_sections':changed,'finite':True}

def collect_file_pins(obj, out=None):
 if out is None: out={}
 if isinstance(obj,dict):
  if isinstance(obj.get('path'),str) and isinstance(obj.get('sha256'),str):
   q=str(pathlib.Path(obj['path']).resolve(strict=True));out[q]={'path':q,'sha256':obj['sha256']}
  else:
   for v in obj.values(): collect_file_pins(v,out)
 elif isinstance(obj,list):
  for v in obj: collect_file_pins(v,out)
 return out

def verify_file_pins(records,label):
 for row in records:
  if sha(row['path'])!=row['sha256']:raise ValueError(f'{label} pin drift: {row["path"]}')

def data_tree_inventory():
 rows=[]
 for p in sorted(DATA.iterdir()):
  if p.is_file():rows.append(pin(p))
 return rows

def expected_cases():
 b=json.loads(BASE_RECEIPT.read_text()); manifest=json.loads((PRO/'sidecars-v4/manifest.json').read_text())
 original={(x['anchor'],x['phase'],x['species']):x for x in b['cases']}
 positive={(x['phase'],x['species']):x for x in manifest['cases'] if x['mode']=='positive-omitted-path'}
 cases=[]
 for ident in ZERO_ORDER+POS_ORDER:
  # Explicit names avoid relying on source-manifest order.
  key=ident.removesuffix('.zero').removesuffix('.positive')
  species,phase=key.split('-')
  phase=phase.upper(); mode='all-zero-control' if ident.endswith('.zero') else 'positive-omitted-path'
  entry=next(x for x in manifest['cases'] if x['phase']==phase and x['species']==species and x['mode']==mode)
  anchor=tuple(entry['anchor_ij']); orig_anchor=next(c['anchor'] for c in b['cases'] if c['phase']==phase and c['species']==species)
  orig=original[(orig_anchor,phase,species)]
  double_oracle=orig['exact_double_zero_sidecar_oracle']['result']
  pos=positive[(phase,species)]
  inp=pos['input_path']; raw=entry['raw_path']; side=PRO/'sidecars-v4'/entry['sidecar_path']
  case_dir=CASES/ident; out=case_dir/'result.out'
  argv=[str(EXE.resolve()),'data',str((ROOT/inp).resolve()),str(out.resolve()),'1','',str(side.resolve())]
  cases.append({'case_id':ident,'phase':phase,'species':species,'mode':mode,'anchor_ij':list(anchor),'native_layers':entry['native_layers'],'engine_layers':entry['engine_layers'],'positive_native_layers':entry.get('positive_native_layers',0),'raw':pin(ROOT/raw),'input':pin(ROOT/inp),'sidecar':pin(side),'baseline_result':double_oracle,'case_cwd':str(case_dir.resolve()),'data_binding':str((case_dir/'data').resolve()),'frozen_binding':str((case_dir/'frozen.nc').resolve()),'output':str(out.resolve()),'argv':argv,'environment':ENV.copy(),'gate_approval_required':True})
 return cases

def canonical_sha(obj):
 return hashlib.sha256(json.dumps(obj,sort_keys=True,separators=(',',':'),allow_nan=False).encode()).hexdigest()

def collect_file_pins(obj, out=None):
 if out is None: out={}
 if isinstance(obj,dict):
  if isinstance(obj.get('path'),str) and isinstance(obj.get('sha256'),str):
   q=str(pathlib.Path(obj['path']).resolve(strict=True)); row={'path':q,'sha256':obj['sha256']}
   if q in out and out[q]['sha256']!=row['sha256']:raise ValueError(f'conflicting hashes for {q}')
   out[q]=row
  else:
   for v in obj.values():collect_file_pins(v,out)
 elif isinstance(obj,list):
  for v in obj:collect_file_pins(v,out)
 return out

def pin_records(records):
 return [{'path':str(pathlib.Path(x['path']).resolve(strict=True)),'sha256':x['sha256']} for x in records]

def verify_file_pins(records,label):
 for row in records:
  q=pathlib.Path(row['path']).resolve(strict=True)
  if sha(q)!=row['sha256']:raise ValueError(f'{label} pin drift: {q}')

def generated_output_pin(path):
 p=pathlib.Path(path)
 if os.path.islink(p) or not p.is_file():raise ValueError(f'generated output is not a regular non-symlink file: {p}')
 return pin(p)

def verify_generated_outputs(records):
 for row in records:
  p=pathlib.Path(row['path'])
  if os.path.islink(p) or not p.is_file() or p.stat().st_size!=row['size_bytes'] or sha(p)!=row['sha256']:
   raise ValueError(f'generated output changed after its durable pre-validation pin: {p}')

def make_immutable_sets(build,base,closure,cases,data_files):
 baseline137={}
 for row in base['pins_before']:
  baseline137[row['path']]={'path':row['path'],'sha256':row['sha256']}
 for oldcase in base['cases']:
  for row in oldcase.get('output_pins',[]):
   baseline137[row['path']]={'path':row['path'],'sha256':row['sha256']}
  row=oldcase['exact_double_zero_sidecar_oracle']['result']
  baseline137[row['path']]={'path':row['path'],'sha256':row['sha256']}
 if len(baseline137)!=137:raise ValueError(f'expected 137 unique baseline pins, got {len(baseline137)}')
 runtime=pin_records(closure['resolved_libraries'])
 if len(runtime)!=47:raise ValueError(f'expected 47 runtime pins, got {len(runtime)}')
 source_build=collect_file_pins({'inputs':build['inputs_before'],'proposal_artifacts':build['proposal_artifacts_before']})
 source_build.update(collect_file_pins({'build_receipt':pin(BUILD/'build-receipt.json'),'postflight':pin(BUILD/'postflight-attestation.json'),'executable':pin(EXE),'proposal_status':pin(PROPOSAL_STATUS),'proposal_manifest':pin(PRO/'artifact-manifest.json')}))
 source_build=[source_build[k] for k in sorted(source_build)]
 # Explicitly include every case oracle/input/raw/sidecar and every coefficient/table file.
 case_pins=collect_file_pins(cases)
 case_pins.update(collect_file_pins(data_files))
 case_pins=[case_pins[k] for k in sorted(case_pins)]
 immutable=collect_file_pins({'baseline137':list(baseline137.values()),'baseline_receipt':pin(BASE_RECEIPT),'runtime47':runtime,'source_build':source_build,'cases_data':case_pins})
 immutable=[immutable[k] for k in sorted(immutable)]
 return {'baseline137':[baseline137[k] for k in sorted(baseline137)],'runtime47':runtime,'source_build':source_build,'cases_data':case_pins,'all_immutable':immutable}

def prepare():
 if any(os.path.lexists(x) for x in (PLAN,STAGE,CASES,EXEC,LOCK,GATES,HERE/'integrity-attestation.json')):raise FileExistsError('campaign preparation exists; refusing overwrite')
 imports_validator()
 ss=importlib.util.spec_from_file_location('cf0_candidate_set',PRO/'validate_candidate_set.py');cm=importlib.util.module_from_spec(ss);sys.modules[ss.name]=cm;ss.loader.exec_module(cm)
 validated=cm.validate(ROOT,PRO/'sidecars-v4')
 closure=runtime_closure()
 build=json.loads((BUILD/'build-receipt.json').read_text());base=json.loads(BASE_RECEIPT.read_text())
 cases=expected_cases(); data_files=data_tree_inventory()
 immutable=make_immutable_sets(build,base,closure,cases,{'data':data_files,'frozen':pin(FROZEN)})
 verify_file_pins(immutable['all_immutable'],'preparation')
 CASES.mkdir(parents=True);GATES.mkdir();stage_entries=[]
 for c in cases:
  d=pathlib.Path(c['case_cwd']);d.mkdir()
  (d/'data').symlink_to(DATA.resolve(),target_is_directory=True)
  (d/'frozen.nc').symlink_to(FROZEN.resolve())
  c['data_binding']=str((d/'data').resolve(strict=True))
  c['frozen_binding']=str((d/'frozen.nc').resolve(strict=True))
  if c['data_binding']!=str(DATA.resolve()) or c['frozen_binding']!=str(FROZEN.resolve()):raise ValueError('staged link resolves to an unexpected target')
  if os.path.lexists(c['output']):raise FileExistsError(c['output'])
  stage_entries.append({'case_id':c['case_id'],'cwd':str(d.resolve()),'data_link_text':os.readlink(d/'data'),'data_resolved':c['data_binding'],'frozen_link_text':os.readlink(d/'frozen.nc'),'frozen_resolved':c['frozen_binding'],'output_absent':True})
 # Bind to the exact post-staging case contracts.
 immutable=make_immutable_sets(build,base,closure,cases,data_files and {'data':data_files,'frozen':pin(FROZEN)})
 verify_file_pins(immutable['all_immutable'],'post-stage')
 approval_example={'schema':'cf0-audit-campaign-authorization-v1','approved':False,'plan_sha256':'ROOT_TO_FILL_AFTER_REVIEW','runner_sha256':'ROOT_TO_FILL_AFTER_REVIEW','cases':{}}
 plan={'schema':'cf0-reference-campaign-invocation-plan-v1','status':'STAGED_NOT_AUTHORIZED_NO_SOLVER_CALLS','created_utc':now(),'solver_invocations':0,'proposal_status':json.loads(PROPOSAL_STATUS.read_text())['status'],'proposal_status_sha256':sha(PROPOSAL_STATUS),'build_receipt':pin(BUILD/'build-receipt.json'),'build_postflight_attestation':pin(BUILD/'postflight-attestation.json'),'executable':pin(EXE),'original_build_source':json.loads((PRO/'build-provenance.json').read_text())['selected_original']['source'],'proposal_source':pin(PRO/'reference_column.proposed.f90'),'original_baseline_receipt':pin(BASE_RECEIPT),'baseline_original_calls':base['reference_calls_attempted'],'baseline_original_status':base['status'],'proposal_manifest':pin(PRO/'artifact-manifest.json'),'runtime_libraries':immutable['runtime47'],'runtime_closure':closure,'immutable_pin_groups':immutable,'data_directory':{'path':str(DATA.resolve()),'files':data_files,'frozen_table':pin(FROZEN)},'sidecar_validation':validated,'order':ZERO_ORDER+POS_ORDER,'calls':cases,'environment':ENV.copy(),'environment_policy':'Each child receives exactly this minimal dictionary. No ambient environment is inherited; no LD_PRELOAD/LD_AUDIT or capture/trace/audit/seed knobs. The 47-library ldd closure is resolved under the same environment and rechecked before/after every child.','launcher_contract':['A separately reviewed root authorization must bind the plan, runner, every complete case contract and every invocation-gate approval; no approval is included.','An O_EXCL execution lock enforces one campaign attempt. No retries or output reuse.','Rehash all 137 baseline artifacts, all 47 libraries, source/build artifacts, case raw/input/sidecar/oracles, and coefficient/table data before and after each call. Re-resolve ldd under the exact child environment.','Each gate approval must bind exact executable/source/build/raw/input/sidecar/data/runtime pins and exact argv; its extra campaign binding hash covers case id, phase/species/mode, cwd, symlink targets, environment, output, expected oracle, and paths.','Write durable call intent before launch, then actual PID/start time; persist actual return code and end time before comparison. Catch errors and finalize a terminal failure receipt with postflight rechecks.','The first four all-zero controls must byte-match their paired saved original double-reference result files and pass full section/order/shape/IEEE-byte checks before any positive call.','Positive outputs must have precisely the phase-specific additional sections with exact expected shapes and finite/physical bounds. Only explicitly declared all-sky optics/flux/heating sections may change; report sensitivities without accuracy claims.'],'call_timeout_seconds':300,'execution_authorization_template':approval_example}
 plan['runner_sha256']=sha(pathlib.Path(__file__))
 atomic(PLAN,plan)
 atomic(STAGE,{'schema':'cf0-reference-campaign-stage-v1','status':'STAGED_NOT_RUN','entries':stage_entries,'solver_calls':0})
 # Supplemental full baseline/runtime attestation: 125 receipt pins + 12 case outputs/oracles and 47 runtime libraries.
 integrity={'schema':'cf0-campaign-integrity-attestation-v1','status':'PASS_OFFLINE_NO_SOLVER','baseline_pin_count':len(immutable['baseline137']),'baseline_pin_sha256':canonical_sha(immutable['baseline137']),'runtime_library_count':len(immutable['runtime47']),'runtime_pin_sha256':canonical_sha(immutable['runtime47']),'all_immutable_pin_count':len(immutable['all_immutable']),'all_immutable_pin_sha256':canonical_sha(immutable['all_immutable']),'plan_sha256':sha(PLAN),'runner_sha256':plan['runner_sha256'],'stage_sha256':sha(STAGE),'solver_invocations':0,'checked_utc':now()}
 atomic(HERE/'integrity-attestation.json',integrity)
 print(json.dumps({'status':plan['status'],'calls':len(cases),'offline_sidecar_validation':validated['status'],'runner_sha256':plan['runner_sha256'],'plan':str(PLAN),'plan_sha256':sha(PLAN),'stage_manifest':str(STAGE),'stage_sha256':sha(STAGE),'integrity_attestation':str(HERE/'integrity-attestation.json'),'baseline_pin_count':integrity['baseline_pin_count'],'runtime_library_count':integrity['runtime_library_count'],'all_immutable_pin_count':integrity['all_immutable_pin_count']},indent=2))

def verify_runtime_closure(plan):
 fresh=runtime_closure()
 expect={(x['path'],x['sha256']) for x in plan['immutable_pin_groups']['runtime47']}
 got={(x['path'],x['sha256']) for x in fresh['resolved_libraries']}
 if got!=expect:raise ValueError('runtime library path/hash closure changed')
 return fresh

def approval_contract(approval,c,plan):
 if approval.get('schema')!='cf0-audit-invocation-approval-v1' or approval.get('approved') is not True:raise ValueError('per-call approval schema/status invalid')
 if approval.get('case_id')!=c['case_id'] or approval.get('phase')!=c['phase'] or approval.get('species')!=c['species']:raise ValueError('approval case identity mismatch')
 if approval.get('argv')!=c['argv']:raise ValueError('approval argv mismatch')
 if approval.get('campaign_binding_sha256')!=canonical_sha(c):raise ValueError('approval does not bind the full frozen case contract')
 for field in ('case_cwd','data_binding','frozen_binding','output','environment','baseline_result','mode'):
  if approval.get(field)!=c[field]:raise ValueError(f'approval {field} differs from frozen case contract')
 expected_mode='all-zero-control' if c['mode']=='all-zero-control' else 'positive-omitted-path'
 if approval.get('campaign_mode')!=expected_mode:raise ValueError('approval mode differs from frozen campaign case')
 expected={
  'executable':(plan['executable']['path'],plan['executable']['sha256']),
  'source':(plan['proposal_source']['path'],plan['proposal_source']['sha256']),
  'source_manifest':(plan['proposal_manifest']['path'],plan['proposal_manifest']['sha256']),
  'build_manifest':(plan['build_receipt']['path'],plan['build_receipt']['sha256']),
  'raw':(c['raw']['path'],c['raw']['sha256']),
  'input':(c['input']['path'],c['input']['sha256']),
  'sidecar':(c['sidecar']['path'],c['sidecar']['sha256'])}
 for key,(path,digest) in expected.items():
  rec=approval.get(key)
  if not isinstance(rec,dict) or not isinstance(rec.get('path'),str):raise ValueError(f'approval {key} pin missing')
  if str((ROOT/rec['path']).resolve())!=str(pathlib.Path(path).resolve()) or rec.get('sha256')!=digest:raise ValueError(f'approval {key} path/hash differs from campaign plan')
 def group_paths(field):
  rows=approval.get(field)
  if not isinstance(rows,list):raise ValueError(f'approval {field} is not a list')
  return {(str((ROOT/x['path']).resolve()),x['sha256']) for x in rows}
 expected_data={(x['path'],x['sha256']) for x in plan['data_directory']['files']}|{(plan['data_directory']['frozen_table']['path'],plan['data_directory']['frozen_table']['sha256'])}
 if group_paths('data_files')!=expected_data:raise ValueError('approval coefficient/frozen data pins mismatch')
 if group_paths('runtime_files')!={(x['path'],x['sha256']) for x in plan['immutable_pin_groups']['runtime47']}:raise ValueError('approval runtime pins mismatch')
 if approval.get('engine_layers')!=c['engine_layers']:raise ValueError('approval engine layer count mismatch')

def exactpath(plan,c,key):
 return {'source':plan['proposal_source']['path'],'source_manifest':plan['proposal_manifest']['path'],'build_manifest':plan['build_receipt']['path'],'raw':c['raw']['path'],'input':c['input']['path'],'sidecar':c['sidecar']['path']}[key]

def run_authorized(auth_path):
 if not PLAN.is_file() or not STAGE.is_file():raise ValueError('campaign must be prepared first')
 if os.path.lexists(EXEC) or os.path.lexists(LOCK):raise FileExistsError('one-use execution receipt/lock already exists; refusing any repeat')
 plan=json.loads(PLAN.read_text());auth_path=pathlib.Path(auth_path).resolve(strict=True);auth=json.loads(auth_path.read_text())
 if auth.get('schema')!='cf0-audit-campaign-authorization-v1' or auth.get('approved') is not True:raise ValueError('explicit root campaign authorization missing')
 if auth.get('plan_sha256')!=sha(PLAN) or auth.get('runner_sha256')!=sha(pathlib.Path(__file__)):raise ValueError('authorization does not match frozen plan and runner')
 cases=plan['calls'];permits=auth.get('cases',{})
 if [c['case_id'] for c in cases]!=ZERO_ORDER+POS_ORDER or set(permits)!={c['case_id'] for c in cases}:raise ValueError('authorization must cover exactly the eight ordered cases')
 fd=os.open(LOCK,os.O_CREAT|os.O_EXCL|os.O_WRONLY,0o600)
 with os.fdopen(fd,'w') as f:f.write(json.dumps({'pid':os.getpid(),'created_utc':now(),'plan_sha256':sha(PLAN)})+'\n');f.flush();os.fsync(f.fileno())
 execution={'schema':'cf0-reference-campaign-execution-v2','status':'RUNNING','created_utc':now(),'runner_sha256':sha(pathlib.Path(__file__)),'plan_sha256':sha(PLAN),'authorization_sha256':sha(auth_path),'calls_completed':0,'solver_invocations':0,'calls':[],'generated_outputs':[]}
 atomic(EXEC,execution);failure=None
 try:
  gate=imports_gate()
  verify_file_pins(plan['immutable_pin_groups']['all_immutable'],'pre-campaign')
  verify_runtime_closure(plan)
  for idx,c in enumerate(cases):
   row={'index':idx+1,'case_id':c['case_id'],'status':'PREFLIGHT_RUNNING','started_utc':now(),'command':c['argv'],'cwd':c['case_cwd'],'environment':ENV.copy(),'output':c['output']}
   execution['calls'].append(row);atomic(EXEC,execution)
   verify_file_pins(plan['immutable_pin_groups']['all_immutable'],'pre-call')
   verify_runtime_closure(plan)
   case_dir=pathlib.Path(c['case_cwd']).resolve(strict=True);out=pathlib.Path(c['output'])
   if case_dir!=pathlib.Path(HERE/'cases'/c['case_id']).resolve(strict=True):raise ValueError('case cwd escaped campaign root')
   if os.readlink(case_dir/'data')!=str(DATA.resolve()) or (case_dir/'data').resolve(strict=True)!=pathlib.Path(c['data_binding']):raise ValueError('data binding drift')
   if os.readlink(case_dir/'frozen.nc')!=str(FROZEN.resolve()) or (case_dir/'frozen.nc').resolve(strict=True)!=pathlib.Path(c['frozen_binding']):raise ValueError('frozen-table binding drift')
   if os.path.lexists(out) or out.parent.resolve(strict=True)!=case_dir:raise ValueError('output is not a fresh file directly under its case directory')
   argv=c['argv']
   if argv!=[str(EXE.resolve()),'data',str(pathlib.Path(c['input']['path']).resolve()),str(out),'1','',str(pathlib.Path(c['sidecar']['path']).resolve())]:raise ValueError('fixed argv contract drift')
   if c['environment']!=ENV or ENV!=plan['environment']:raise ValueError('controlled environment mismatch')
   permit=permits[c['case_id']]
   approval_path=(ROOT/permit['path']).resolve(strict=True)
   if sha(approval_path)!=permit['sha256']:raise ValueError('approval file hash mismatch')
   approval=json.loads(approval_path.read_text());approval_contract(approval,c,plan)
   gr=GATES/f'{c["case_id"]}.json'
   if os.path.lexists(gr):raise FileExistsError(f'gate receipt exists: {gr}')
   if permit.get('campaign_binding_sha256')!=canonical_sha(c):raise ValueError('authorization permit is not bound to this frozen case')
   if c['mode']=='all-zero-control':
    zero_gate=validate_zero_case(approval,c)
    atomic(gr,{'schema':'cf0-zero-control-preflight-v1','status':'ZERO_CONTROL_GATE_PASS_NO_SOLVER','case_id':c['case_id'],'campaign_binding_sha256':canonical_sha(c),'validation':zero_gate,'solver_invocations':0})
   else:
    gate.preflight(approval,ROOT,gr)
   log=case_dir/'stdout.log'
   if os.path.lexists(log):raise FileExistsError(f'log exists: {log}')
   with log.open('xb') as f:
    row['status']='LAUNCHING';row['gate_receipt']=str(gr);row['log']=str(log);row['launch_intent_utc']=now();atomic(EXEC,execution)
    proc=subprocess.Popen(argv,cwd=case_dir,env=ENV,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
    execution['solver_invocations']+=1;row.update(status='RUNNING',pid=proc.pid,pid_recorded_utc=now());atomic(EXEC,execution)
    try:rc=proc.wait(timeout=300)
    except subprocess.TimeoutExpired:
     row['timed_out']=True;os.killpg(proc.pid,signal.SIGTERM)
     try:rc=proc.wait(timeout=10)
     except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);rc=proc.wait()
   row.update(returncode=rc,ended_utc=now(),stdout_sha256=sha(log));atomic(EXEC,execution)
   if os.path.lexists(out):
    row['generated_output_pin']=generated_output_pin(out)
    execution['generated_outputs'].append(row['generated_output_pin'])
    atomic(EXEC,execution)
   verify_file_pins(plan['immutable_pin_groups']['all_immutable'],'post-child')
   post_closure=verify_runtime_closure(plan)
   row['post_child_integrity']={'immutable_pin_count':len(plan['immutable_pin_groups']['all_immutable']),'runtime_library_count':post_closure['count'],'runtime_closure_sha256':canonical_sha(post_closure['resolved_libraries']),'ldd_stdout_sha256':post_closure['stdout_sha256']}
   atomic(EXEC,execution)
   if rc!=0 or not out.is_file():raise RuntimeError(f'child failed rc={rc}, output_exists={out.is_file()}')
   if c['mode']=='all-zero-control':
    b=pathlib.Path(c['baseline_result']['path'])
    if sha(out)!=c['baseline_result']['sha256'] or out.read_bytes()!=b.read_bytes():raise ValueError('zero-sidecar output differs bytewise from exact saved original double-reference result')
    validation={'status':'ZERO_SIDECAR_EXACT_DOUBLE_ORACLE_BYTE_PASS','baseline_sha256':sha(b),'output_sha256':sha(out)}
   else:validation=compare_positive(c['baseline_result']['path'],out,c['phase'])
   row.update(status='CALL_VALIDATED',validation=validation);execution['calls_completed']+=1;atomic(EXEC,execution)
   if idx==3 and execution['calls_completed']!=4:raise ValueError('positive stage cannot start until all four zero controls pass')
  execution['status']='PASS_ALL_EIGHT_CALLS'
 except Exception as e:
  failure=f'{type(e).__name__}: {e}';execution['status']='FAILED_CAMPAIGN_PRESERVED';execution['failure']=failure
  if execution['calls'] and execution['calls'][-1].get('status') not in ('CALL_VALIDATED',):execution['calls'][-1].update(status='FAILED_PRESERVED',failure=failure)
 finally:
  post={'checked_utc':now(),'immutable_pin_count':len(plan['immutable_pin_groups']['all_immutable'])}
  try:verify_generated_outputs(execution['generated_outputs']);post['generated_outputs_unchanged']=True
  except Exception as e:post.update(generated_outputs_unchanged=False,generated_output_error=f'{type(e).__name__}: {e}');execution['status']='FAILED_POSTFLIGHT_PRESERVED'
  try:verify_file_pins(plan['immutable_pin_groups']['all_immutable'],'postflight');post['immutable_pins_unchanged']=True
  except Exception as e:post.update(immutable_pins_unchanged=False,immutable_pin_error=f'{type(e).__name__}: {e}');execution['status']='FAILED_POSTFLIGHT_PRESERVED'
  try:post['runtime_closure']=verify_runtime_closure(plan);post['runtime_closure_unchanged']=True
  except Exception as e:post.update(runtime_closure_unchanged=False,runtime_error=f'{type(e).__name__}: {e}');execution['status']='FAILED_POSTFLIGHT_PRESERVED'
  execution['postflight']=post;execution['finished_utc']=now();atomic(EXEC,execution)
 print(json.dumps({'status':execution['status'],'solver_invocations':execution['solver_invocations'],'calls_completed':execution['calls_completed'],'failure':failure,'receipt':str(EXEC)},indent=2))
 if execution['status']!='PASS_ALL_EIGHT_CALLS':raise SystemExit(1)

def main():
 ap=argparse.ArgumentParser();g=ap.add_mutually_exclusive_group(required=True);g.add_argument('--prepare',action='store_true');g.add_argument('--execute',action='store_true');ap.add_argument('--authorization',type=pathlib.Path)
 a=ap.parse_args()
 if a.prepare:prepare();return 0
 if not a.authorization:raise SystemExit('--execute requires a separate root authorization JSON')
 run_authorized(a.authorization);return 0
if __name__=='__main__':raise SystemExit(main())
