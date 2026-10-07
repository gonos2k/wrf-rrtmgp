#!/usr/bin/env python3
"""Independent saved-output audit for the private two-arm fractional-CF observer run."""
import hashlib,json,math,pathlib,re,struct,sys,os,subprocess
import numpy as np
from netCDF4 import Dataset
BASE=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
ROOT=BASE/'build/udm37-fractional-cf-population-runtime-v1'
EXEC=ROOT/'execution.json'
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def f32(x):return struct.unpack('<f',struct.pack('<f',float(x)))[0]
def is32(x):return math.isfinite(x) and f32(x)==x
def parse_rows(directory,pattern,magic,expected_keys,head_count,value_count,clock_values):
 files=sorted(directory.glob(pattern));got={}
 if len(files)!=len(expected_keys):raise ValueError(f'{directory}: file count {len(files)} != {len(expected_keys)}')
 for path in files:
  lines=path.read_text().splitlines()
  if len(lines)!=head_count+3+44:raise ValueError(f'{path.name}: line count')
  if lines[0]!=magic:raise ValueError(f'{path.name}: magic')
  h=[int(x) for x in lines[1].split()]
  c=[float(x) for x in lines[2].split()]
  if len(c)!=len(clock_values):raise ValueError(f'{path.name}: clock width')
  if not all(is32(x) for x in c):raise ValueError(f'{path.name}: non-native REAL32 clock')
  rows=[]
  for lineno,line in enumerate(lines[3:],1):
   t=line.split()
   nints=3 if magic=='UDM37CFPOP1' else 1
   ints=list(map(int,t[:nints]));vals=list(map(float,t[nints:]))
   if len(vals)!=value_count or not all(is32(x) for x in vals):raise ValueError(f'{path.name}: invalid row values')
   rows.append((ints,vals))
  nameparts=path.stem.split('_')
  if magic=='UDM37CFPOP1':
   mm=re.fullmatch(r'population_d(\d+)_tile(\d+)_i(\d+)_j(\d+)_step(\d+)_sub(\d+)_phase(\d+)',path.stem)
   if not mm:raise ValueError('CF filename')
   d,tile,i,j,step,sub,phase=map(int,mm.groups());key=(step,sub,phase)
   if c != [float(step-1),60.,60.]:raise ValueError('CF clock-step association')
   if h != [1,step,phase,sub,1,23,2,1,44,32,*h[10:]] or len(h)!=13 or (d,tile,i,j)!=(1,1,23,2):raise ValueError('CF identity header')
   top,qct, qit=h[10:]
   if not (0<=top<=44 and 0<=qct<=44 and 0<=qit<=44 and top==max(qct,qit)):raise ValueError('CF top bounds')
   for k,(ints,vals) in enumerate(rows,1):
    kk,applied,diagnosed=ints
    if kk!=k or diagnosed!=int(k<=top) or applied!=int(k<=top and vals[0]>0):raise ValueError('CF diagnosed/applied flag')
    if not 0<=vals[0]<=1 or vals[13]<=0 or (k>top and vals[0]!=1.):raise ValueError('CF bounds/above-top default')
  else:
   mm=re.fullmatch(r'number_d(\d+)_tile(\d+)_i(\d+)_j(\d+)_step(\d+)_stage(\d+)_sub(\d+)',path.stem)
   if not mm:raise ValueError('NUMBER filename')
   d,tile,i,j,step,stage,sub=map(int,mm.groups());key=(step,stage,sub)
   if c != [float(step-1),60.,1.e8]:raise ValueError('NUMBER clock/source')
   avail=17 if stage in (21,23,30) else 29 if stage==31 else 2 if stage==51 else 0
   if len(h)!=12 or h[:10]!=[1,step,stage,sub,1,23,2,1,44,32] or h[10:]!=[avail,int(step==1)] or (d,tile,i,j)!=(1,1,23,2):raise ValueError('NUMBER identity/availability')
  if key in got:raise ValueError('duplicate packet key')
  got[key]={'path':str(path),'sha256':sha(path),'size_bytes':path.stat().st_size,'header':h,'clock':c,'rows':rows}
 if set(got)!=set(expected_keys):raise ValueError(f'{magic}: missing/extra roster')
 return got

def main():
 execution=json.loads(EXEC.read_text());plan=json.loads((ROOT/'stage-plan.json').read_text())
 if execution['status']!='PASS_PAIRED_FRACTIONAL_CF_OBSERVER_RUNTIME_SCOPED' or execution['model_calls']!=2:raise ValueError('execution is not terminal scoped pass')
 arms=execution['arms']
 if any(a['actual_rc']!=0 or not a['reaped'] or a['status']!='PASS_RUNTIME_SCOPED' for a in arms.values()):raise ValueError('child result')
 if any(a['ended_unix']-a['started_unix']>300 for a in arms.values()):raise ValueError('timeout bound')
 if execution['scientific_accepted'] is not False:raise ValueError('scientific acceptance must stay false')
 post=json.loads((ROOT/'root-process-group-postflight.json').read_text())
 if post['execution_sha256']!=sha(EXEC) or post['actual_rc']!=[0,0] or post['reaped']!=[True,True] or post['process_group_members']!={str(a['pid']):[] for a in arms.values()} or post['status']!='PASS_EMPTY_GROUPS':raise ValueError('postflight receipt')
 expectedcf={(s,1,p) for s in (1,2) for p in (1,2,3,4)}
 expectednum={(s,stage,1 if stage in (21,23,30,31) else 0) for s in (1,2) for stage in (10,11,20,21,23,30,31,40,50,51)}
 cf=parse_rows(pathlib.Path(plan['cases']['on']['number_capture_directory']),'*.cfpop','UDM37CFPOP1',expectedcf,0,14,[0.,60.,60.])
 num=parse_rows(pathlib.Path(plan['cases']['on']['number_capture_directory']),'number_*.raw','UDM37NUM1',expectednum,0,14,[0.,60.,1.e8])
 # Reader independently confirms the native source arithmetic around the two cloud-fraction transformations.
 mass=range(4,10);numbers=(10,11,12);common=(1,2,3,13);transforms=unchanged=0
 for step in (1,2):
  a,b,c,d=(cf[(step,1,p)] for p in (1,2,3,4))
  if not (a['header'][10:]==b['header'][10:]==c['header'][10:]==d['header'][10:]):raise ValueError('CF top changed across snapshots')
  for x,y in zip(a['rows'],b['rows']):
   cfv=x[1][0]
   for n in mass:
    expected=f32(x[1][n]/cfv) if x[0][1] else x[1][n]
    if f32(y[1][n])!=expected:raise ValueError('source divide relation')
    transforms+=1
   for n in numbers:
    if x[1][n]!=y[1][n]:raise ValueError('number changed in divide snapshot')
    unchanged+=1
   for n in common:
    if x[1][n]!=y[1][n]:raise ValueError('common state changed in divide snapshot')
  for x,y in zip(c['rows'],d['rows']):
   cfv=x[1][0]
   for n in mass:
    expected=f32(x[1][n]*cfv) if x[0][1] else x[1][n]
    if f32(y[1][n])!=expected:raise ValueError('source multiply relation')
    transforms+=1
   for n in numbers:
    if x[1][n]!=y[1][n]:raise ValueError('number changed in multiply snapshot')
    unchanged+=1
   for n in common:
    if x[1][n]!=y[1][n]:raise ValueError('common state changed in multiply snapshot')
  # predivision snapshot to existing NUMBER stage 23 and helper return state to history.
  for x,y in zip(a['rows'],num[(step,23,1)]['rows']):
   if [x[1][i] for i in (1,2,3,4,6,10,11,12,13)] != [y[1][i] for i in range(9)]:raise ValueError('CF/NUMBER stage23 crossjoin')
 # Positive fraction and positive same-step helper input at k=7, without unit interpretation.
 wet=[]
 for step in (1,2):
  cfrow=cf[(step,1,1)]['rows'][6][1]
  helper=num[(step,50,0)]['rows'][6][1]
  result=num[(step,51,0)]['rows'][6][1]
  if not (0<cfrow[0]<1 and cfrow[4]>0 and cfrow[11]>0 and helper[3]>0 and helper[6]>0 and result[10]>0):raise ValueError('fractional CF / helper positive probe')
  wet.append({'step':step,'XTIME_minutes':cf[(step,1,1)]['clock'][0],'k':7,'CF':cfrow[0],'QC_predivision':cfrow[4],'NC_raw_predivision':cfrow[11],'QC_helper':helper[3],'NC_raw_helper':helper[6],'RE_cloud_m':result[10]})
 # QNN packet set, headers, finite columns and source/branch context independently re-read.
 capdir=pathlib.Path(plan['cases']['on']['capture_directory']);qfiles=sorted(capdir.glob('*.raw'))
 if len(qfiles)!=24:raise ValueError('QNN packet count')
 qnn_rows=0;inflow=outflow=0;qnnpins=[]
 expected_cols={(0,1):(23,1,(1,45,1,25),(23,2)),(1,4):(90,26,(46,90,26,50),(89,26)),(2,3):(1,74,(1,45,51,75),(2,74)),(3,2):(68,99,(46,90,76,99),(68,98))}
 qkeys=set()
 for f in qfiles:
  mm=re.fullmatch(r'qnn_d(\d+)_rank(\d+)_tile(\d+)_step(\d+)_rk(\d+)_side(\d+)\.raw',f.name)
  if not mm:raise ValueError('QNN filename')
  dom,rank,tile,step,rk,side=map(int,mm.groups());lines=f.read_text().splitlines()
  if lines[0]!='UDM37QNNB1' or len(lines)!=46:raise ValueError('QNN shape/magic')
  hdr=list(map(int,lines[1].split()));
  if len(hdr)!=15:raise ValueError('QNN header')
  i,j,bounds,source=expected_cols[(rank,side)]
  if hdr != [1,step,rk,rank,tile,side,i,j,1,44,32,*bounds]:raise ValueError('QNN header identity/bounds')
  key=(rank,side,tile,step,rk);qkeys.add(key)
  for k,line in enumerate(lines[2:],1):
   z=line.split();ints=list(map(int,z[:5]));vals=list(map(float,z[5:]))
   if len(ints)!=5 or len(vals)!=13 or ints[0]!=k or ints[1] not in (0,1) or ints[4]!=1 or not all(math.isfinite(v) for v in vals):raise ValueError('QNN row')
   vel,ccn,qnn0,qnn1,nc0,nc1,nr0,nr1,al,alb,density,rho,qnnsrc=vals
   if f32(f32(al)+f32(alb))!=density or f32(1./f32(density))!=rho or not (nc0==nc1 and nr0==nr1):raise ValueError('QNN dry density/passivity')
   inflowbit=vel>=0 if side in (1,3) else vel<=0
   if ints[1]!=int(inflowbit):raise ValueError('QNN branch sign')
   if ints[1]:
    inflow+=1
    if (ints[2],ints[3],qnnsrc)!=(0,0,0.) or qnn1!=ccn or ccn!=1.e8:raise ValueError('QNN inflow assignment')
   else:
    outflow+=1
    if (ints[2],ints[3])!=source or qnn1!=qnnsrc:raise ValueError('QNN boundary source copy')
   qnn_rows+=1
  qnnpins.append({'path':f.name,'sha256':sha(f),'size_bytes':f.stat().st_size})
 expected_qkeys={(rank,side,tile,step,rk) for rank,side,tile in ((0,1,1),(1,4,2),(2,3,1),(3,2,2)) for step in (1,2) for rk in (1,2,3)}
 if qkeys!=expected_qkeys or qnn_rows!=1056 or inflow<=0:raise ValueError('QNN coverage/nonzero-inflow')
 # Rebind runtime execution to root authorization, staged inputs, source/build and runtime libraries.
 def exact_pin(q,want):
  q=pathlib.Path(q)
  return q.is_file() and q.stat().st_size==want['size_bytes'] and sha(q)==want['sha256'] and str(q.resolve())==want['path']
 auth=json.loads((ROOT/'root-authorization.json').read_text())
 if auth['stage_plan_sha256']!=sha(ROOT/'stage-plan.json') or auth['runner_sha256']!=sha(BASE/'build/udm37-fractional-cf-population-runtime-runner-v1.py') or auth['max_models']!=2 or auth['timeout_seconds_each']!=300:raise ValueError('authorization binding')
 if execution['stage_pins']!={n:{'path':str((ROOT/n).resolve()),'sha256':sha(ROOT/n),'size_bytes':(ROOT/n).stat().st_size,'link':None} for n in ('stage-plan.json','verify_stage.py','root-authorization.json')}:raise ValueError('stage pins')
 if execution['inputs_before']!=execution['inputs_after']:raise ValueError('staged inputs changed')
 for arm,c in plan['cases'].items():
  if execution['inputs_before'][arm]!=c['files']:raise ValueError('staged input snapshot differs from plan')
  for name,want in c['files'].items():
   if not exact_pin(pathlib.Path(c['directory'])/name,want):raise ValueError('staged file pin '+arm+'/'+name)
  gate=(pathlib.Path(c['number_capture_directory']),pathlib.Path(c['capture_directory']))
  if arm=='off' and any(any(x.iterdir()) for x in gate):raise ValueError('OFF produced captures')
 source=BASE/'build/udm37-fractional-cf-population-observer-source-v1'
 for name,want in execution['selected_source_pins'].items():
  if not exact_pin(source/name,want):raise ValueError('source pin '+name)
 if subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD'],text=True).strip()!=execution['source']['head'] or subprocess.check_output(['git','-C',str(source),'rev-parse','HEAD^{tree}'],text=True).strip()!=execution['source']['tree'] or subprocess.check_output(['git','-C',str(source),'status','--porcelain'],text=True).strip():raise ValueError('source checkout drift')
 build_result=BASE/'build/udm37-fractional-cf-population-observer-build-v1/result.json'
 if not exact_pin(build_result,execution['build_result']) or execution['build_result']!=plan['build_result']:raise ValueError('build receipt binding')
 libpins=execution['library_pins']
 for path,want in libpins.items():
  if not exact_pin(path,want):raise ValueError('runtime library pin '+path)
 if len(libpins)!=50 or not exact_pin(execution['MPI']['path'],execution['MPI']) or execution['MPI']!=plan['MPI_executable']:raise ValueError('MPI/runtime library closure')
 for arm,row in arms.items():
  if row['models']!=1 or row['actual_rc']!=0 or not row['reaped'] or row.get('timed_out') or row.get('cleanup_errors') or row['ended_unix']-row['started_unix']>300:raise ValueError('arm terminal/timeout receipt')
  d=pathlib.Path(row['cwd'])
  if not all('SUCCESS COMPLETE WRF' in (d/f'rsl.out.{rank:04d}').read_text(errors='replace') for rank in range(4)):raise ValueError('rank success markers')
  # Whole-file hashes, complete NetCDF rosters and time axes; equal hashes prove each entire pair byte-identical.
 pairreports=[]
 for kind in ('wrfout_d01_2016-10-06_00:00:00','wrfrst_d01_2016-10-06_00:02:00'):
  left=ROOT/'stage/off'/kind;right=ROOT/'stage/on'/kind
  hl,hr=sha(left),sha(right)
  with Dataset(left) as a,Dataset(right) as b:
   if list(a.variables)!=list(b.variables) or len(a.variables) not in (231,668):raise ValueError('NetCDF roster')
   if {k:(len(v),bool(v.isunlimited())) for k,v in a.dimensions.items()}!={k:(len(v),bool(v.isunlimited())) for k,v in b.dimensions.items()}:raise ValueError('NetCDF dimensions')
   if kind.startswith('wrfout'):
    ts=[b''.join(x).decode('ascii') for x in a['Times'][:]]
    if ts!=plan['cases']['off']['expected_history_times']:raise ValueError('history Times')
   else:
    ts=[b''.join(x).decode('ascii') for x in a['Times'][:]]
    if ts!=['2016-10-06_00:02:00']:raise ValueError('restart time')
   nvars=len(a.variables)
  if hl!=hr or left.stat().st_size!=right.stat().st_size:raise ValueError('OFF/ON full-file mismatch')
  pairreports.append({'kind':kind,'sha256':hl,'size_bytes':left.stat().st_size,'variables':nvars,'times':ts,'byte_identical':True})
 # Same-source-step selected profile joins to output history for helper and CF.
 history=ROOT/'stage/on/wrfout_d01_2016-10-06_00:00:00';joins=[]
 varmap={'QCLOUD':3,'QNCLOUD':6,'QNRAIN':7,'QRAIN':4,'QVAPOR':2,'QNCCN':5}
 with Dataset(history) as ds:
  for step in (1,2):
   helper=num[(step,50,0)]['rows']
   for name,idx in varmap.items():
    v=ds[name];v.set_auto_maskandscale(False);actual=np.asarray(v[step,:,1,22]);want=np.asarray([r[1][idx] for r in helper],dtype=np.float32)
    if actual.dtype!=np.dtype('float32') or actual.shape!=(44,) or actual.tobytes()!=want.tobytes():raise ValueError('history/helper profile '+name)
    joins.append({'step':step,'variable':name,'levels':44,'exact':True})
   packet=cf[(step,1,1)];v=ds['UDM_CLDFRA'];v.set_auto_maskandscale(False);actual=np.asarray(v[step,:,1,22]);want=np.asarray([r[1][0] for r in packet['rows']],dtype=np.float32)
   if actual.tobytes()!=want.tobytes():raise ValueError('history/CF profile')
   if int(ds['UDM_CF_STEP'][step,1,22])!=step or int(ds['UDM_CF_TOP'][step,1,22])!=packet['header'][10]:raise ValueError('history CF step/top')
   joins.append({'step':step,'variable':'UDM_CLDFRA','levels':44,'exact':True})
 result={'schema':'UDM37_FRACTIONAL_CF_RUNTIME_INDEPENDENT_TERMINAL_REVIEW_V1','status':'PASS_SCOPED_SAVED_RUNTIME_AUDIT','execution_sha256':sha(EXEC),'execution_status':execution['status'],'model_calls':execution['model_calls'],'children':{k:{'pid':v['pid'],'actual_rc':v['actual_rc'],'reaped':v['reaped'],'duration_s':v['ended_unix']-v['started_unix']} for k,v in arms.items()},'postflight_sha256':sha(ROOT/'root-process-group-postflight.json'),'empty_process_groups':True,'packet_counts':{'cf':len(cf),'cf_rows':sum(len(x['rows']) for x in cf.values()),'number':len(num),'number_rows':sum(len(x['rows']) for x in num.values()),'qnn':len(qfiles),'qnn_rows':qnn_rows,'qnn_inflow_rows':inflow,'qnn_outflow_rows':outflow},'CF_source_relations':{'mass_transform_checks':transforms,'unchanged_number_checks':unchanged,'CF_number23_join_levels':88,'fractional_positive_helper_levels':wet,'helper_history_CF_profile_joins':joins,'status':'PASS_DISCRIMINATING_FRACTIONAL_CF_SOURCE_RELATIONS'},'full_output_pairs':pairreports,'qnn_packet_pins':qnnpins,'source_and_build_pins':{'source_commit':execution['source']['head'],'source_tree':execution['source']['tree'],'selected_source_pins':execution['selected_source_pins'],'build_result':execution['build_result'],'runtime_library_count':len(libpins),'runtime_library_pins':libpins,'mpi':execution['MPI']},'authorization_and_prelaunch':{'authorization_sha256':sha(ROOT/'root-authorization.json'),'stage_plan_sha256':sha(ROOT/'stage-plan.json'),'runner_sha256':sha(BASE/'build/udm37-fractional-cf-population-runtime-runner-v1.py'),'validator_sha256':sha(BASE/'build/udm37-fractional-cf-population-runtime-preparation-v1/validate_cf_population.py'),'prelaunch_review_sha256':sha(BASE/'build/udm37-fractional-cf-population-runtime-independent-review-v1/review.json')},'scope':{'off_on_all_history_and_restart_bytes_equal':True,'physical_units_or_PSD_authority':False,'scientific_accepted':False},'limits':['One private 2-minute, MPI4/OMP2, dt60 case on the derived input only.','CF phases record source state; above-top CF=1 is initialized working value and not a fresh diagnosis.','Predivision CF and later helper source state are separate same-step snapshots; no unit or physical accuracy approval.','The exact OFF/ON comparison is observer passivity for the captured outputs, not source physics correctness.']}
 result['audit_script']={'path':str(pathlib.Path(__file__).resolve()),'sha256':sha(pathlib.Path(__file__).resolve()),'size_bytes':pathlib.Path(__file__).stat().st_size}
 out=pathlib.Path(__file__).with_name('review.json');out.write_text(json.dumps(result,indent=2,sort_keys=True)+'\n');print(json.dumps({'status':result['status'],'output':str(out),'hash':sha(out),'packets':result['packet_counts'],'wet':wet,'fullpairs':pairreports},indent=2))
if __name__=='__main__':main()
