#!/usr/bin/env python3
"""Pinned, isolated Intel WRF em_real build; no production edits or installs."""
import concurrent.futures,fcntl,hashlib,json,os,pathlib,resource,signal,subprocess,time
ROOT=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/yhlee/RRTMGP')
TASK=ROOT/'build/udm-workspace-intel-serial'
SOURCE=TASK/'source'
BASE='6f0f3ea3e73fbd43325fdad1050b000eecd70138'
COMP=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/Library/intel/oneapi/compiler/2025.3')
NC=pathlib.Path('/NHNHOME/WORKSPACE/26weather002_A/Library/WRF_LIBS')
inventory=json.loads((ROOT/'build/udm-intel-feasibility/inventory-probe-receipt.json').read_text())
env=os.environ.copy()
cleared={}
selectors={'WRF_CHEM','WRF_KPP','WRFPLUS','WRF_DA_CORE','NETCDFPAR','PNETCDF','HDF5','PHDF5','NETCDF_classic','NETCDF4','WRF_CMAQ','WRFIO_NCD_LARGE_FILE_SUPPORT'}
for k in list(env):
 if k in selectors or k.startswith('WRF_RRTMGP_') or k=='WRF_UDM_BOUNDARY_CAPTURE': cleared[k]=env.pop(k)
env.update(inventory['controlled_environment'])
TASK.mkdir(exist_ok=True)
lock=(TASK/'build.lock').open('w');fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
original_stack=resource.getrlimit(resource.RLIMIT_STACK)
resource.setrlimit(resource.RLIMIT_STACK,(64*1024*1024,original_stack[1]))
def sha(p):
 h=hashlib.sha256()
 with pathlib.Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1<<20),b''):h.update(b)
 return h.hexdigest()
def write(name,v): (TASK/name).write_text(json.dumps(v,indent=2,sort_keys=True)+'\n')
def files_manifest(root,names):
 entries=[]
 for name in sorted(names):
  p=root/name
  if p.is_symlink(): entries.append(dict(path=name,kind='symlink',target=os.readlink(p),sha256=hashlib.sha256(os.readlink(p).encode()).hexdigest()))
  elif p.is_file():entries.append(dict(path=name,kind='file',bytes=p.stat().st_size,sha256=sha(p)))
  else:raise RuntimeError('missing manifest file '+str(p))
 return entries
def changed(manifest,root):
 now={x['path']:x for x in files_manifest(root,[x['path'] for x in manifest])}
 return [dict(before=x,after=now[x['path']]) for x in manifest if now[x['path']]!=x]
receipt=dict(status='STAGING',base_commit=BASE,launcher_sha256=sha(__file__),controlled_environment=inventory['controlled_environment'],inherited_selector_keys_cleared=sorted(cleared),original_stack_bytes=original_stack,stack_bytes=resource.getrlimit(resource.RLIMIT_STACK),commands=[])
write('build-receipt.json',receipt)
def logged(argv,log,cwd,input_bytes=None,timeout=2700):
 started=time.monotonic(); timed_out=False
 with (TASK/log).open('wb') as f:
  proc=subprocess.Popen(argv,cwd=cwd,env=env,stdin=subprocess.PIPE if input_bytes else subprocess.DEVNULL,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
  try:proc.communicate(input_bytes,timeout=timeout)
  except subprocess.TimeoutExpired:
   timed_out=True;os.killpg(proc.pid,signal.SIGTERM)
   try:proc.wait(timeout=10)
   except subprocess.TimeoutExpired:os.killpg(proc.pid,signal.SIGKILL);proc.wait()
 step=dict(argv=argv,cwd=str(cwd),stdin=input_bytes.decode() if input_bytes else None,returncode=proc.returncode,timed_out=timed_out,elapsed_s=time.monotonic()-started,log=log,log_sha256=sha(TASK/log))
 receipt['commands'].append(step);write('build-receipt.json',receipt)
 return step
try:
 if SOURCE.exists():raise RuntimeError('fresh source required')
 stage=logged(['git','-C',str(ROOT/'build/udm-workspace-selected-work'),'worktree','add','--detach',str(SOURCE),BASE],'stage.log',ROOT,timeout=120)
 if stage['returncode']:raise RuntimeError('worktree staging failed')
 actual=subprocess.check_output(['git','rev-parse','HEAD'],cwd=SOURCE,text=True).strip();assert actual==BASE
 assert not subprocess.check_output(['git','status','--porcelain'],cwd=SOURCE,text=True)
 names=[x for x in subprocess.check_output(['git','ls-files','-z'],cwd=SOURCE).decode().split('\0') if x]
 source_manifest=files_manifest(SOURCE,names);write('source-manifest.json',dict(base_commit=BASE,files=source_manifest))
 receipt['source_manifest_sha256']=sha(TASK/'source-manifest.json')
 dep_paths=set(inventory['dependencies'])
 # Include all supplied NetCDF/HDF5 headers/modules/libraries, compiler helpers,
 # and Intel compiler runtime libraries that this controlled toolchain exposes.
 for d in [NC/'include',NC/'lib',COMP/'bin',COMP/'lib']:
  for p in d.rglob('*'):
   if p.is_file():dep_paths.add(str(p))
 def entry(p):return (p,dict(resolved=str(pathlib.Path(p).resolve()),bytes=pathlib.Path(p).stat().st_size,sha256=sha(p)))
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:deps=dict(pool.map(entry,sorted(dep_paths)))
 write('shared-dependencies-before.json',deps);receipt['shared_dependencies_before_sha256']=sha(TASK/'shared-dependencies-before.json')
 receipt['source_files']=len(source_manifest);receipt['shared_dependency_files']=len(deps);receipt['status']='CONFIGURING';write('build-receipt.json',receipt)
 print('source',len(source_manifest),'dependencies',len(deps),'configure serial76/nest0',flush=True)
 cfg=logged(['./configure'],'configure-serial76.log',SOURCE/'WRF',input_bytes=b'76\n0\n',timeout=120)
 if cfg['returncode']:raise RuntimeError('configure failed')
 text=(SOURCE/'WRF/configure.wrf').read_text();assert '# Compiler choice: 76' in text;assert '# Nesting option: 0' in text
 import re
 for pattern in [r'^SFC\s*=\s*ifx\s*$',r'^SCC\s*=\s*icx\s*$',r'^DMPARALLEL\s*=\s*# 1\s*$',r'^OMP\s*=\s*# -qopenmp -fpp -auto\s*$',r'^NATIVE_RWORDSIZE\s*=\s*4\s*$']:
  assert re.search(pattern,text,re.M),pattern
 receipt['configure_sha256']=sha(SOURCE/'WRF/configure.wrf');receipt['status']='BUILDING';write('build-receipt.json',receipt)
 print('configure PASS; compile starting',flush=True)
 build=logged(['csh','-f','./compile','-j','12','em_real'],'build-em_real.log',SOURCE/'WRF')
 receipt['source_files_modified_or_missing']=changed(source_manifest,SOURCE)
 with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:deps_after=dict(pool.map(entry,sorted(dep_paths)))
 write('shared-dependencies-after.json',deps_after);receipt['shared_dependencies_after_sha256']=sha(TASK/'shared-dependencies-after.json');receipt['shared_dependencies_unchanged']=deps==deps_after
 receipt['configure_after_sha256']=sha(SOURCE/'WRF/configure.wrf')
 receipt['executables']={}
 for name in ['wrf.exe','real.exe','ndown.exe','tc.exe']:
  p=SOURCE/'WRF/main'/name
  receipt['executables'][name]=dict(exists=p.is_file(),sha256=sha(p) if p.is_file() else None,bytes=p.stat().st_size if p.is_file() else None)
  if p.is_file():
   step=logged(['ldd',str(p)],'ldd-'+name+'.log',TASK,timeout=30)
   if step['returncode'] or 'not found' in (TASK/step['log']).read_text():raise RuntimeError('unresolved executable dependencies')
 receipt['vendor_objects_expected']=subprocess.check_output(['make','-s','-C',str(SOURCE/'WRF/external/rte_rrtmgp/build'),'print-wrf-objects'],env=env,text=True).splitlines()
 receipt['vendor_objects_actual']=sorted(p.name for p in (SOURCE/'WRF/external/rte_rrtmgp/build').glob('*.o'))
 if build['returncode'] or build['timed_out']:raise RuntimeError('compile failed')
 if receipt['source_files_modified_or_missing'] or not receipt['shared_dependencies_unchanged'] or receipt['configure_after_sha256']!=receipt['configure_sha256']:raise RuntimeError('source/config/dependencies changed')
 if not all(v['exists'] for v in receipt['executables'].values()):raise RuntimeError('missing em_real executable')
 if receipt['vendor_objects_actual']!=sorted(receipt['vendor_objects_expected']):raise RuntimeError('vendor object inventory differs')
 build_text=(TASK/'build-em_real.log').read_text(errors='replace')
 if 'The following indicate the compilers selected to build the WRF system' not in build_text or 'WRF CONFIGURATION ERROR' in build_text:raise RuntimeError('configcheck output missing or error reported')
 receipt['status']='BUILD_PASS'
except Exception as error:
 receipt['status']='BUILD_FAIL';receipt['error']=repr(error)
 if (TASK/'source-manifest.json').exists():
  try:receipt['source_files_modified_or_missing']=changed(json.loads((TASK/'source-manifest.json').read_text())['files'],SOURCE)
  except Exception as e:receipt['source_check_error']=repr(e)
finally:
 write('build-receipt.json',receipt);print(receipt['status'],receipt.get('error',''),flush=True)
raise SystemExit(0 if receipt['status']=='BUILD_PASS' else 1)
